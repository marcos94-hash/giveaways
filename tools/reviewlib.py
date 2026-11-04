"""Shared review-queue logic: listing validation, review-log statuses, retries, claims.

Review log (data/review_log.json, version 2) keeps one item per candidate key:

  status        listed | rejected | ended | blocked | needs_review | parked | in_progress | interrupted
  reason_code   short machine code (see REJECT_CODES / RETRY_CODES)
  reason        one plain sentence
  attempts      failed tries so far (blocked / needs_review)
  next_retry_at when a blocked / needs_review / unverified-listed item may be tried again
  claim         {run, expires_at, prev} while a run is working on it

Permanent: rejected, ended. Retryable: blocked, needs_review (backoff 1, 2, 4 days,
then parked). Listed items whose listing still needs a rules check come back every
3 days so they can be upgraded to verified.
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scraper"))
from finder import norm_url  # noqa: E402

ET = dt.timezone(dt.timedelta(hours=-5))  # EST; good enough for dates and backoff
LIMITS = {"once", "daily", "rolling24", "rolling"}
CATS = {"cash", "gift_card", "electronics", "trip", "mixed", "other"}
VSTATUS = {"verified", "needs_rules_check"}
CONFIRM_KEYS = ("eligibility", "free_entry", "deadline", "entry_limit")
REJECT_CODES = {"ended", "not_open_to_nj", "restricted_group", "purchase_required", "no_free_online_entry",
                "social_only", "duplicate", "not_running", "invalid_link", "under_age_for_everyone", "other"}
RETRY_CODES = {"unreadable_page", "robots_blocked", "js_only", "no_rules_found", "incomplete_info",
               "conflicting_info", "possible_membership", "other"}
STATUSES = {"listed", "rejected", "ended", "blocked", "needs_review", "parked", "in_progress", "interrupted"}
BACKOFF_DAYS = [1, 2, 4]          # after 1st, 2nd, 3rd failed attempt; 4th -> parked
RECHECK_UNVERIFIED_DAYS = 3
CLAIM_HOURS = 3
RETRY_SHARE = 0.3                 # at most this share of a batch goes to retries while new items wait


def now():
    return dt.datetime.now(ET).replace(microsecond=0)


def iso(t):
    return t.isoformat() if t else None


def parse(s):
    if not s:
        return None
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=ET)


def load(name, default):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(name, data):
    p = os.path.join(DATA, name)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def key_of(url_or_key):
    return norm_url(url_or_key) if "://" in str(url_or_key) else str(url_or_key)


# ------------------------------------------------------------------ review log
def load_log():
    raw = load("review_log.json", {"version": 2, "items": {}})
    if raw.get("version") == 2:
        return raw
    # v1 -> v2: {"reviewed": {key: {verdict, name, reason, date}}}
    items = {}
    for k, v in raw.get("reviewed", {}).items():
        if v.get("verdict") == "accepted":
            items[k] = {"name": v.get("name", ""), "status": "listed", "decided_at": v.get("date"), "attempts": 0}
        else:
            items[k] = {"name": v.get("name", ""), "status": "rejected", "reason_code": guess_code(v.get("reason", "")),
                        "reason": v.get("reason", ""), "decided_at": v.get("date"), "attempts": 0}
    return {"version": 2, "items": items}


def guess_code(reason):
    r = reason.lower()
    for code, pat in [("ended", r"ended|not open until|closed"), ("duplicate", r"duplicate"),
                      ("not_open_to_nj", r"new jersey|only open to|excludes nj|states"),
                      ("purchase_required", r"purchase"), ("not_running", r"no contest|not running"),
                      ("restricted_group", r"wedding|members only|employees|students")]:
        if re.search(pat, r):
            return code
    return "other"


def save_log(log):
    log["version"] = 2
    log["items"] = dict(sorted(log["items"].items()))
    save("review_log.json", log)


# ------------------------------------------------------------------ listings
def validate_listing(g, t=None):
    t = t or now()
    errs = []
    for f in ("id", "name", "prize", "entry_url", "ends", "limit", "verification"):
        if not g.get(f):
            errs.append(f"missing {f}")
    if g.get("entry_url") and not str(g["entry_url"]).startswith("https://"):
        errs.append("entry_url must be https")
    try:
        e = parse(g["ends"])
        if not re.search(r"[+-]\d\d:\d\d$|Z$", g["ends"]):
            errs.append("ends needs a UTC offset, e.g. -05:00")
        elif e <= t:
            errs.append("already ended")
    except Exception:
        errs.append("ends is not ISO 8601")
    lim = g.get("limit") or {}
    if lim.get("type") not in LIMITS:
        errs.append(f"limit.type must be one of {sorted(LIMITS)}")
    if lim.get("type") == "daily" and not lim.get("reset_tz"):
        errs.append("daily limit needs reset_tz")
    if lim.get("type") == "rolling" and not lim.get("hours"):
        errs.append("rolling limit needs hours")
    if int(g.get("min_age", 18)) not in (18, 19, 21):
        errs.append("min_age must be 18, 19 or 21")
    if g.get("category", "other") not in CATS:
        errs.append(f"category must be one of {sorted(CATS)}")
    for p in list(g.get("match", [])) + list(g.get("frames", [])):
        if " " in p or "." not in p.split("/")[0] or p.startswith("http"):
            errs.append(f"bad match/frames pattern {p!r} (use host/path, no scheme)")
    v = g.get("verification") or {}
    if v:
        if v.get("status") not in VSTATUS:
            errs.append(f"verification.status must be one of {sorted(VSTATUS)}")
        try:
            parse(v.get("checked_at"))
            if not v.get("checked_at"):
                raise ValueError
        except Exception:
            errs.append("verification.checked_at must be an ISO date or time")
        if v.get("status") == "verified":
            if not str(v.get("rules_source") or "").startswith("http"):
                errs.append("verified needs rules_source: the sponsor rules URL you actually read")
            conf = v.get("confirmed") or {}
            missing = [k for k in CONFIRM_KEYS if conf.get(k) is not True]
            if missing:
                errs.append(f"verified needs confirmed {missing} from the sponsor rules")
        if v.get("status") == "needs_rules_check" and not v.get("reason"):
            errs.append("needs_rules_check needs a reason")
    return errs


def finalize_listing(g, today):
    g.setdefault("flags", {})
    g.setdefault("notes", "")
    g.setdefault("min_age", 18)
    g.setdefault("category", "other")
    g.setdefault("added", today)
    g.setdefault("source", f"Claude review {today}")
    if not g.get("id"):
        g["id"] = slug(g.get("name", "giveaway"))
    if not g.get("match"):
        g["match"] = [norm_url(g["entry_url"]).split("://", 1)[-1].split("?")[0]]
    if int(g.get("min_age", 18)) >= 21:
        g["flags"]["age21"] = True
    v = g.get("verification") or {}
    g["rules_checked"] = "full" if v.get("status") == "verified" else "partial"  # older extension builds
    return g


def upsert_listing(data, g, t=None):
    """Insert or refresh a listing. Returns (listing, 'added'|'updated') or raises ValueError."""
    t = t or now()
    today = t.date().isoformat()
    gs = data.setdefault("giveaways", [])
    g = dict(g)
    key = norm_url(g["entry_url"])
    old = next((x for x in gs if norm_url(x["entry_url"]) == key), None)
    if old:
        g = {**old, **{k: v for k, v in g.items() if v not in (None, "", {}, [])}}
        g["id"], g["added"] = old["id"], old.get("added", today)
    g = finalize_listing(g, today)
    errs = validate_listing(g, t)
    if errs:
        raise ValueError(f"{g.get('name')}: " + "; ".join(errs))
    if old:
        gs[gs.index(old)] = g
        return g, "updated"
    ids = {x["id"] for x in gs}
    base, n = g["id"], 2
    while g["id"] in ids:
        g["id"] = f"{base}-{n}"
        n += 1
    gs.append(g)
    return g, "added"


def listing_keys(data):
    """Keys and path prefixes that mean 'this promotion is already listed'."""
    keys, prefixes = set(), []
    for g in data.get("giveaways", []):
        keys.add(norm_url(g["entry_url"]))
        if g.get("rules_url"):
            keys.add(norm_url(g["rules_url"]))
        prefixes += [m.lower().rstrip("*") for m in g.get("match", []) if "/" in m]
    return keys, prefixes


def already_listed(k, keys, prefixes):
    if k in keys:
        return True
    bare = k.split("://", 1)[-1]
    return any(bare == p or bare.startswith(p + "/") for p in prefixes)


# ------------------------------------------------------------------ queue
def record(log, key, status, reason_code="", reason="", evidence=None, t=None, listing_id=None, verified=None):
    t = t or now()
    allowed = STATUSES - {"in_progress", "interrupted"}
    if status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    it = log["items"].get(key) or {"attempts": 0}
    prev = it.get("claim", {}).get("prev") if it.get("status") == "in_progress" else None
    it.pop("claim", None)
    it.pop("interrupted_at", None)
    it["status"] = status
    it["reason_code"] = reason_code
    it["reason"] = reason
    it["last_attempt_at"] = iso(t)
    if evidence:
        it["evidence"] = sorted(set((it.get("evidence") or []) + list(evidence)))
    if status == "rejected":
        if reason_code not in REJECT_CODES:
            raise ValueError(f"rejected needs reason_code in {sorted(REJECT_CODES)}")
        it["next_retry_at"] = None
        it["decided_at"] = iso(t)
    elif status in ("blocked", "needs_review"):
        if reason_code not in RETRY_CODES:
            raise ValueError(f"{status} needs reason_code in {sorted(RETRY_CODES)}")
        it["attempts"] = int((prev or it).get("attempts", 0)) + 1
        if it["attempts"] > len(BACKOFF_DAYS):
            it["status"] = "parked"
            it["next_retry_at"] = None
        else:
            it["next_retry_at"] = iso(t + dt.timedelta(days=BACKOFF_DAYS[it["attempts"] - 1]))
    elif status == "listed":
        it["listing_id"] = listing_id
        it["decided_at"] = iso(t)
        it["next_retry_at"] = None if verified else iso(t + dt.timedelta(days=RECHECK_UNVERIFIED_DAYS))
    log["items"][key] = it
    return it


def release_expired(log, t=None):
    """Hand back claims from runs that died. Returns the keys, which get resumed first."""
    t = t or now()
    resumed = []
    for k, it in list(log["items"].items()):
        if it.get("status") == "in_progress" and parse(it["claim"]["expires_at"]) <= t:
            prev = it["claim"].get("prev") or {"attempts": 0, "status": "interrupted"}
            log["items"][k] = {**prev, "interrupted_at": iso(t)}
            resumed.append(k)
    return resumed


def release_run(log, run):
    """End of a run: give back anything it claimed but never recorded (no attempt counted)."""
    out = []
    for k, it in list(log["items"].items()):
        if it.get("status") == "in_progress" and it["claim"]["run"] == run:
            prev = it["claim"].get("prev")
            if prev and prev.get("status") != "interrupted":
                log["items"][k] = prev
            else:
                log["items"].pop(k)   # was new: back to the new pile, nothing recorded
            out.append(k)
    return out


def ends_of(c):
    return c.get("ends_guess") or "9999-12-31"


def priority(c, today):
    soon = 0 if ends_of(c) <= (today + dt.timedelta(days=7)).isoformat() else 1
    cat = {"cash": 0, "gift_card": 1, "electronics": 2, "trip": 3}.get(c.get("category_guess"), 4)
    daily = 0 if str(c.get("frequency_guess", "")).startswith("daily") else 1
    return (soon, cat, daily, -(c.get("value_guess") or 0), ends_of(c))


def plan(log, cands, data, n, t=None):
    """Pick up to n items: interrupted first, then mostly new, plus due retries."""
    t = t or now()
    today = t.date()
    keys, prefixes = listing_keys(data)
    listed_by_id = {g["id"]: g for g in data.get("giveaways", [])}
    items = log["items"]

    def live(c):
        return ends_of(c) > today.isoformat()

    resume = [k for k, it in items.items() if it.get("interrupted_at") and it.get("status") not in ("rejected", "ended", "listed")
              and k in cands and live(cands[k])]
    new = [k for k, c in cands.items() if k not in items and live(c) and not already_listed(k, keys, prefixes)]
    new.sort(key=lambda k: priority(cands[k], today))
    retry = []
    for k, it in items.items():
        due = it.get("next_retry_at") and parse(it["next_retry_at"]) <= t
        if not due or k in resume:
            continue
        if it.get("status") in ("blocked", "needs_review") and k in cands and live(cands[k]):
            retry.append(k)
        elif it.get("status") == "listed":
            g = listed_by_id.get(it.get("listing_id"))
            if g and (g.get("verification") or {}).get("status") != "verified" and parse(g["ends"]) > t:
                retry.append(k)
    retry.sort(key=lambda k: (items[k]["next_retry_at"], ends_of(cands.get(k, {}))))

    picked = resume[:n]
    room = n - len(picked)
    retry_cap = max(1, int(round(room * RETRY_SHARE))) if new else room
    take_retry = retry[:min(retry_cap, room)]
    take_new = new[:room - len(take_retry)]
    if len(take_new) < room - len(take_retry):  # not enough new: fill with more retries
        take_retry = retry[:room - len(take_new)]
    picked += take_new + take_retry
    return picked, {"resume": len(resume), "new_waiting": len(new), "retry_due": len(retry)}


def claim(log, picked, run, t=None):
    t = t or now()
    exp = iso(t + dt.timedelta(hours=CLAIM_HOURS))
    for k in picked:
        prev = log["items"].get(k)
        prev = {x: y for x, y in prev.items() if x not in ("claim", "interrupted_at")} if prev else None
        log["items"][k] = {**(prev or {"attempts": 0}), "status": "in_progress",
                           "claim": {"run": run, "expires_at": exp, "prev": prev}}


def sweep(log, data, cands, t=None):
    """Retire what has ended: candidates nobody decided on, and listings past their end."""
    t = t or now()
    today = t.date().isoformat()
    out = {"listings_ended": [], "candidates_ended": 0}
    keep = []
    for g in data.get("giveaways", []):
        if parse(g["ends"]) <= t:
            out["listings_ended"].append(g["name"])
            for k, it in log["items"].items():
                if it.get("listing_id") == g["id"]:
                    it.update({"status": "ended", "next_retry_at": None, "decided_at": iso(t)})
        else:
            keep.append(g)
    data["giveaways"] = keep
    for k, c in cands.items():
        it = log["items"].get(k)
        if ends_of(c) <= today and (not it or it.get("status") in ("blocked", "needs_review", "parked")):
            log["items"][k] = {**(it or {"attempts": 0}), "name": c.get("title", ""), "status": "ended",
                               "reason_code": "ended", "reason": "ended before it could be verified",
                               "next_retry_at": None, "decided_at": iso(t)}
            out["candidates_ended"] += 1
    return out


def counts(log, data, cands, t=None):
    t = t or now()
    from collections import Counter
    c = Counter(it.get("status") for it in log["items"].values())
    v = Counter((g.get("verification") or {}).get("status", "missing") for g in data.get("giveaways", []))
    keys, prefixes = listing_keys(data)
    waiting = sum(1 for k, x in cands.items() if k not in log["items"] and ends_of(x) > t.date().isoformat()
                  and not already_listed(k, keys, prefixes))
    return {"review_log": dict(sorted(c.items())), "listings": dict(sorted(v.items())), "new_waiting": waiting}
