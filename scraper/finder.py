#!/usr/bin/env python3
"""Giveaway finder: runs on the Mac mini, collects candidate sweepstakes from
public listing sites, and writes data/candidates.json for review.

Stdlib only. Polite: obeys robots.txt, one request every 1.5 s, small page caps.
It never enters anything; it only reads public listing pages.
"""
import argparse
import datetime as dt
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

UA = "GiveawayFinder/1.0 (personal use, one person's sweepstakes list)"
DELAY = 1.5
TIMEOUT = 20

# Listing sites. detail_re picks links to individual giveaway posts.
# If detail_re finds nothing, generic discovery is used and noted in the report.
SOURCES = [
    {
        "name": "freestufftimes",
        "listing": ["https://www.freestufftimes.com/contests/"] +
                   [f"https://www.freestufftimes.com/contests/page/{n}/" for n in range(2, 5)],
        "detail_re": r"^https://www\.freestufftimes\.com/contests/\d+/[a-z0-9-]+/?$",
    },
    {
        "name": "thefreebieguy",
        "listing": ["https://thefreebieguy.com/sweepstakes/", "https://thefreebieguy.com/sweepstakes/page/2/"],
        "detail_re": r"^https://thefreebieguy\.com/sweepstakes/[a-z0-9-]+/?$",
    },
    {
        "name": "winprizesonline",
        "listing": ["https://www.winprizesonline.com/", "https://www.winprizesonline.com/sweepstakes/"],
        "detail_re": r"^https://www\.winprizesonline\.com/[A-Za-z0-9-]+-(?:Sweepstakes|Giveaway|Contest)[A-Za-z0-9-]*/?$",
    },
]

SOCIAL = ("instagram.com", "facebook.com", "fb.com", "tiktok.com", "twitter.com", "x.com",
          "youtube.com", "threads.net", "pinterest.com", "linkedin.com", "reddit.com", "t.me", "discord.")
SHARE = ("sharer", "share?", "intent/tweet", "pin/create", "mailto:", "javascript:", "addtoany", "whatsapp")
PLATFORMS = ("gleam.io", "viralsweep.com", "sweepwidget.com", "woobox.com", "wishpond.com", "rafflecopter.com",
             "shortstack", "a.pgtb.me", "promo.", "promotions.", "sweeps", "giveaway", "contest", "win")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# ---------------------------------------------------------------- fetching
_robots = {}
_last = [0.0]


def allowed(url):
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            rp.parse(["User-agent: *", "Disallow: /"] if e.code in (401, 403) else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(UA, url)


def fetch(url):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), body.decode(charset, "replace")


# ---------------------------------------------------------------- parsing
BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
         "section", "article", "header", "footer", "table", "dt", "dd", "blockquote", "hr", "strong"}
SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}


class Page(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.text = []
        self.links = []   # (href, text)
        self.meta = {}
        self.h1 = ""
        self._skip = 0
        self._a = None
        self._h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self._skip += 1
        if tag in BLOCK:
            self.text.append("\n")
        if tag == "a" and a.get("href"):
            self._a = [urllib.parse.urljoin(self.base, a["href"].strip()), []]
        if tag == "meta" and (a.get("property") or a.get("name")):
            self.meta[(a.get("property") or a.get("name")).lower()] = a.get("content") or ""
        if tag == "h1":
            self._h1 = True

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag in BLOCK:
            self.text.append("\n")
        if tag == "a" and self._a:
            self.links.append((self._a[0], " ".join("".join(self._a[1]).split())))
            self._a = None
        if tag == "h1":
            self._h1 = False

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._a is not None:
            self._a[1].append(data)
        if self._h1:
            self.h1 += data

    def plain(self):
        t = "".join(self.text)
        t = re.sub(r"[ \t\r\f\v\xa0]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n", t).strip()


def parse(url, body):
    p = Page(url)
    try:
        p.feed(body)
    except Exception:
        pass
    return p


def host(u):
    return urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")


def norm_url(u):
    p = urllib.parse.urlsplit(u)
    q = urllib.parse.parse_qsl(p.query)
    q = [(k, v) for k, v in q if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref", "mc_"))]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path,
                                    urllib.parse.urlencode(q), ""))


# ---------------------------------------------------------------- field extraction
DATE_RX = (r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"
           r"(?:[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?"
           r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})")
END_LABEL = (r"(?:last day to enter|ends?|ending|end date|deadline(?: date)?|expires|expiration(?: date)?|"
             r"entry deadline|closes|giveaway ends|sweepstakes ends|ends on)")


def parse_date(s, today):
    s = s.strip().lower().replace(".", "")
    s = re.sub(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+", "", s)
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
        if m:
            mo, d, y = map(int, m.groups())
            y += 2000 if y < 100 else 0
        else:
            m = re.match(r"([a-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})?", s)
            if not m or m.group(1)[:3] not in MONTHS:
                return None
            mo, d = MONTHS[m.group(1)[:3]], int(m.group(2))
            y = int(m.group(3)) if m.group(3) else None
            if y is None:  # no year shown: next occurrence
                y = today.year
                try:
                    if dt.date(y, mo, d) < today - dt.timedelta(days=1):
                        y += 1
                except ValueError:
                    return None
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def find_end(text, today):
    for m in re.finditer(END_LABEL + r"\s*[:\-–—]?\s*(?:on\s+)?(" + DATE_RX + r")", text, re.I):
        d = parse_date(m.group(1), today)
        if d and today - dt.timedelta(days=2) <= d <= today + dt.timedelta(days=400):
            return d, m.group(0)[:80]
    return None, None


def find_frequency(text):
    lab = re.search(r"(?:entry frequency|frequency|entry|entries)\s*[:\-–—]\s*([^\n]{0,60})", text, re.I)
    chunk = lab.group(1) if lab else ""
    probe = chunk or text[:3000]
    if re.search(r"\b(daily|once (?:a|per) day|per day|every day|each day)\b", probe, re.I):
        return "daily"
    if re.search(r"\b(weekly|per week|once a week)\b", probe, re.I):
        return "weekly"
    if re.search(r"\b(single|one[- ]time|one entry|1 entry|once per person|limit one)\b", probe, re.I):
        return "once"
    if re.search(r"\binstant win\b", probe, re.I):
        return "daily?"
    return "unknown"


def find_age(text):
    ages = [int(a) for a in re.findall(r"\b(18|19|21)\s*\+", text)]
    ages += [int(a) for a in re.findall(r"\b(18|19|21)\s*(?:years|yrs)\.?\s*(?:of age\s*)?(?:or|and)\s*older", text, re.I)]
    ages += [int(a) for a in re.findall(r"\bage\s*(?:of\s*)?(18|19|21)\b", text, re.I)]
    return max(ages) if ages else None


def flags_for(text, entry_url):
    t = text
    us = bool(re.search(r"\b(U\.?S\.?A?\.?|United States|50 (?:U\.?S\.? )?states|USA)\b", t))
    foreign = bool(re.search(r"\b(Canada only|Canadian residents|United Kingdom|UK residents|Australia|Australian residents|Ireland|India)\b", t, re.I))
    nj_out = bool(re.search(r"(?:exclud\w*|void in|except(?:ing)?|not open to)[^.\n]{0,160}\b(New Jersey|N\.?J\.?)\b", t, re.I))
    no_purchase = bool(re.search(r"no purchase (?:is )?necessary", t, re.I))
    purchase = (not no_purchase) and bool(re.search(r"purchase (?:is )?required|proof of purchase|upload (?:your )?receipt|with (?:any|qualifying) purchase", t, re.I))
    local = bool(re.search(r"\b(?:must|only) (?:live|reside) (?:with)?in\b|listening area|viewing area|DMA\b", t, re.I))
    social = host(entry_url).endswith(SOCIAL) if entry_url else False
    return {"us_mentioned": us, "foreign_only": foreign and not us, "nj_excluded": nj_out,
            "purchase_required": purchase, "local_only": local, "social_entry": social}


def pick_links(page, source_host):
    enter = rules = None
    outbound = []
    for href, txt in page.links:
        if not href.startswith("http") or any(s in href.lower() for s in SHARE):
            continue
        h = host(href)
        if h == source_host or h.endswith("." + source_host):
            continue
        outbound.append((href, txt))
        tl = txt.lower()
        path = urllib.parse.urlsplit(href).path.lower()
        looks_rules = "rule" in tl or re.search(r"rules|terms|\.pdf$", path)
        if looks_rules:
            if rules is None:
                rules = href
            continue
        elif enter is None and re.search(r"\benter\b|click here|go to (?:the )?(?:giveaway|sweepstakes)|entry form", tl):
            enter = href
    if enter is None:  # fallback: first outbound link to something that looks like a promotion
        for href, txt in outbound:
            h, path = host(href), urllib.parse.urlsplit(href).path.lower()
            if (not h.endswith(SOCIAL) and any(k in h or k in path for k in PLATFORMS) and "rule" not in txt.lower()
                    and not re.search(r"rules|terms|\.pdf$", path)):
                enter = href
                break
    return enter, rules


def money(text):
    vals = []
    for m in re.finditer(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d\d)?\s*(k|K)?", text):
        v = int(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        if v < 5_000_000:
            vals.append(v)
    return max(vals) if vals else None


def category(text):
    t = text.lower()
    if re.search(r"\bcash\b(?! ?&)|in the form of a check|venmo|paypal|\$\d[\d,]* (?:cash|check)", t):
        return "cash"
    if re.search(r"gift card|giftcard|e-gift|visa prepaid|prepaid card|gift certificate", t):
        return "gift_card"
    if re.search(r"iphone|ipad|macbook|laptop|playstation|ps5|xbox|nintendo|switch 2|\btv\b|television|headphones|airpods|camera|smartwatch|tablet|gaming|console|speaker|monitor|drone", t):
        return "electronics"
    if re.search(r"\btrip\b|vacation|cruise|getaway|travel|flight", t):
        return "trip"
    return "other"


def body_after_title(text, title):
    """Text that follows the post title, so site navigation (e.g. 'Cash & gift cards' menus) doesn't skew guesses."""
    i = text.find(title[:40]) if title else -1
    return text[i + len(title):i + len(title) + 2500] if i >= 0 else text[-2500:]


def extract(url, body, source_host, today):
    p = parse(url, body)
    text = p.plain()
    title = html.unescape(p.meta.get("og:title") or p.h1 or p.meta.get("title") or "").strip()
    title = re.sub(r"\s*[|\-–]\s*[^|\-–]{2,40}$", "", title) or title
    enter, rules = pick_links(p, source_host)
    end, end_raw = find_end(text, today)
    return {
        "title": title[:160],
        "source_url": url,
        "entry_url": enter,
        "rules_url": rules,
        "ends_guess": end.isoformat() if end else None,
        "ends_text": end_raw,
        "frequency_guess": find_frequency(text),
        "min_age_guess": find_age(text),
        "value_guess": money(text[:6000]),
        "category_guess": category(title + " " + body_after_title(text, title)),
        "flags": flags_for(text[:8000], enter),
        "snippet": text[:700],
    }


# ---------------------------------------------------------------- main
def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def keep(c, today):
    f = c["flags"]
    if not c.get("entry_url"):
        return False, "no entry link found"
    if c.get("ends_guess") and c["ends_guess"] < today.isoformat():
        return False, "ended"
    if f["foreign_only"]:
        return False, "not open to US"
    if f["nj_excluded"]:
        return False, "excludes New Jersey"
    if f["social_entry"]:
        return False, "social-media-only entry"
    if f["purchase_required"]:
        return False, "purchase required"
    if f["local_only"]:
        return False, "local residents only"
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/candidates.json")
    ap.add_argument("--report", default="data/scrape_report.json")
    ap.add_argument("--state", default=os.path.expanduser("~/.cache/giveaway-finder/seen.json"))
    ap.add_argument("--max-details", type=int, default=150)
    ap.add_argument("--per-source", type=int, default=60)
    ap.add_argument("--only", help="run one source by name (testing)")
    args = ap.parse_args()

    today = dt.date.today()
    os.makedirs(os.path.dirname(args.state), exist_ok=True)
    seen = load(args.state, {})            # detail url -> date last parsed
    store = load(args.out, {"candidates": {}})
    cands = store.get("candidates", {})
    report = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "sources": {}}
    budget = args.max_details

    for src in SOURCES:
        if args.only and src["name"] != args.only:
            continue
        r = {"listing_pages": 0, "detail_links": 0, "parsed": 0, "kept": 0, "dropped": {}, "errors": [], "samples": []}
        report["sources"][src["name"]] = r
        details = []
        for lu in src["listing"]:
            if not allowed(lu):
                r["errors"].append(f"robots.txt disallows {lu}")
                continue
            try:
                final, body = fetch(lu)
            except Exception as e:
                r["errors"].append(f"{lu}: {e}")
                continue
            r["listing_pages"] += 1
            pg = parse(final, body)
            rx = re.compile(src["detail_re"])
            found = [h.split("#")[0] for h, _ in pg.links if rx.match(h.split("#")[0])]
            if not found:  # generic fallback: same-site links that look like giveaway posts
                sh = host(final)
                found = [h.split("#")[0] for h, t in pg.links
                         if host(h) == sh and re.search(r"sweep|giveaway|contest|win-", h.lower())
                         and not re.search(r"/(page|category|tag|author)/", h.lower())]
                if found:
                    r["errors"].append(f"detail_re matched nothing on {lu}; used generic links ({len(found)})")
            for h in found:
                if h not in details and h.rstrip("/") != final.rstrip("/"):
                    details.append(h)
        r["detail_links"] = len(details)
        src_budget = args.per_source

        for du in details:
            if budget <= 0 or src_budget <= 0:
                break
            if du in seen:
                continue
            if not allowed(du):
                r["errors"].append(f"robots.txt disallows {du}")
                continue
            try:
                final, body = fetch(du)
            except Exception as e:
                r["errors"].append(f"{du}: {e}")
                continue
            budget -= 1
            src_budget -= 1
            seen[du] = today.isoformat()
            c = extract(final, body, host(final), today)
            r["parsed"] += 1
            if len(r["samples"]) < 2:
                r["samples"].append({k: c[k] for k in ("title", "entry_url", "rules_url", "ends_guess", "ends_text", "frequency_guess", "min_age_guess", "snippet")})
            ok, why = keep(c, today)
            if not ok:
                r["dropped"][why] = r["dropped"].get(why, 0) + 1
                continue
            key = norm_url(c["entry_url"])
            prev = cands.get(key)
            c["key"] = key
            c["source"] = src["name"]
            c["first_seen"] = prev["first_seen"] if prev else today.isoformat()
            c["last_seen"] = today.isoformat()
            cands[key] = {**(prev or {}), **c}
            r["kept"] += 1

    # drop ended candidates; forget detail pages older than 45 days
    cutoff = (today - dt.timedelta(days=45)).isoformat()
    cands = {k: v for k, v in cands.items() if not (v.get("ends_guess") and v["ends_guess"] < today.isoformat())}
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    for v in cands.values():
        v.pop("snippet", None)

    store = {"updated": report["run_at"], "count": len(cands),
             "candidates": dict(sorted(cands.items(), key=lambda kv: kv[1].get("first_seen", ""), reverse=True))}
    save(args.out, store)
    save(args.state, seen)
    report["total_candidates"] = len(cands)
    report["details_budget_left"] = budget
    save(args.report, report)
    print(json.dumps({s: {k: v[k] for k in ("listing_pages", "detail_links", "parsed", "kept")} for s, v in report["sources"].items()}))
    print(f"total candidates: {len(cands)}")


if __name__ == "__main__":
    sys.exit(main())
