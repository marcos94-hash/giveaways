#!/usr/bin/env python3
"""Merge a review batch into data/giveaways.json and data/review_log.json.

batch.json:
{
  "accepted": [ <giveaway objects in the extension schema> ],
  "rejected": [ {"key": "<candidate key or url>", "name": "...", "reason": "..."} ]
}
Validates everything, drops ended giveaways, and appends a line to data/run_log.md.
"""
import argparse, json, re, sys
from common import load, save, norm_url, now_et, parse_iso, slug

LIMITS = {"once", "daily", "rolling24", "rolling"}
CATS = {"cash", "gift_card", "electronics", "trip", "mixed", "other"}

def validate(g):
    errs = []
    for f in ("id", "name", "prize", "entry_url", "ends", "limit"):
        if not g.get(f):
            errs.append(f"missing {f}")
    if g.get("entry_url") and not re.match(r"^https?://", g["entry_url"]):
        errs.append("entry_url must be http(s)")
    try:
        e = parse_iso(g["ends"])
        if e.tzinfo is None:
            errs.append("ends needs a UTC offset, e.g. -05:00")
        elif e <= now_et():
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
    if g.get("rules_checked") not in ("full", "partial"):
        errs.append("rules_checked must be full or partial")
    if g.get("category", "other") not in CATS:
        errs.append(f"category must be one of {sorted(CATS)}")
    return errs

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("batch"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    batch = json.load(open(a.batch))
    data = load("giveaways.json", {"version": 1, "giveaways": []})
    log = load("review_log.json", {"reviewed": {}})
    today = now_et().date().isoformat()
    gs = data["giveaways"]
    by_url = {norm_url(g["entry_url"]): g for g in gs}
    ids = {g["id"] for g in gs}
    added, updated, bad = [], [], []

    for g in batch.get("accepted", []):
        g = dict(g)
        cand_key = g.pop("_candidate_key", None)
        if not g.get("entry_url"):
            bad.append((g.get("name"), ["missing entry_url"])); continue
        key = norm_url(g["entry_url"])
        old = by_url.get(key)
        if old:  # same giveaway already listed: refresh the fields given, keep the rest
            g = {**old, **{k: v for k, v in g.items() if v not in (None, "", {}, [])}}
            g["id"], g["added"] = old["id"], old.get("added", today)
        g.setdefault("flags", {}); g.setdefault("notes", ""); g.setdefault("min_age", 18)
        g.setdefault("category", "other"); g.setdefault("added", today); g.setdefault("source", f"Claude review {today}")
        if not g.get("id"):
            g["id"] = slug(g.get("name", "giveaway"))
        if not g.get("match"):
            g["match"] = [key.split("://", 1)[-1].split("?")[0]]
        if int(g.get("min_age", 18)) >= 21:
            g["flags"]["age21"] = True
        errs = validate(g)
        if errs:
            bad.append((g.get("name"), errs)); continue
        if old:
            gs[gs.index(old)] = g; updated.append(g["name"])
        else:
            base, n = g["id"], 2
            while g["id"] in ids:
                g["id"] = f"{base}-{n}"; n += 1
            ids.add(g["id"]); gs.append(g); added.append(g["name"])
        by_url[key] = g
        for k in {key, cand_key} - {None}:
            log["reviewed"][k] = {"verdict": "accepted", "name": g["name"], "date": today}

    for r in batch.get("rejected", []):
        k = r.get("key") or r.get("url")
        if not k:
            bad.append((r.get("name"), ["rejected item needs key or url"])); continue
        k = k if "://" in k and k == norm_url(k) else norm_url(k)
        log["reviewed"][k] = {"verdict": "rejected", "name": r.get("name", ""), "reason": r.get("reason", ""), "date": today}

    # drop ended
    now = now_et(); ended = [g for g in gs if parse_iso(g["ends"]) <= now]
    data["giveaways"] = [g for g in gs if g not in ended]
    data["giveaways"].sort(key=lambda g: g["ends"])
    data["updated"] = today
    data["source"] = "Found by the Mac mini finder and Perplexity/web search, checked against official rules by Claude."

    summary = {"added": added, "updated": updated, "rejected": len(batch.get("rejected", [])),
               "ended_removed": [g["name"] for g in ended], "invalid": bad, "active": len(data["giveaways"])}
    print(json.dumps(summary, indent=2))
    if bad:
        print("\nFix the invalid entries above and run again. Nothing was written.", file=sys.stderr)
        sys.exit(1)
    if a.dry_run:
        return
    save("giveaways.json", data); save("review_log.json", log)
    with open(__import__("os").path.join(__import__("common").DATA, "run_log.md"), "a") as f:
        f.write(f"- {now.strftime('%Y-%m-%d %H:%M')} ET: +{len(added)} added, {len(updated)} updated, "
                f"{summary['rejected']} rejected, {len(ended)} ended; {summary['active']} active\n")

if __name__ == "__main__":
    main()
