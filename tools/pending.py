#!/usr/bin/env python3
"""List candidates the Mac mini found that haven't been reviewed yet, best first."""
import argparse, json
from common import load, norm_url, now_et

ap = argparse.ArgumentParser(); ap.add_argument("-n", type=int, default=25); ap.add_argument("--json", action="store_true")
a = ap.parse_args()
cands = load("candidates.json", {"candidates": {}})["candidates"]
log = load("review_log.json", {"reviewed": {}})["reviewed"]
listed = {norm_url(g["entry_url"]) for g in load("giveaways.json", {"giveaways": []})["giveaways"]}
today = now_et().date().isoformat()

def score(c):
    cat = {"cash": 0, "gift_card": 1, "electronics": 2, "trip": 3}.get(c.get("category_guess"), 4)
    freq = 0 if str(c.get("frequency_guess", "")).startswith("daily") else 1
    soon = c.get("ends_guess") or "9999"
    return (cat, freq, -(c.get("value_guess") or 0), soon)

todo = [c for k, c in cands.items() if k not in log and k not in listed
        and not (c.get("ends_guess") and c["ends_guess"] <= today)]
todo.sort(key=score)
print(f"{len(todo)} unreviewed candidates ({len(cands)} total found, {len(log)} already reviewed)\n")
for c in todo[: a.n]:
    if a.json:
        print(json.dumps({k: c.get(k) for k in ("key", "title", "entry_url", "rules_url", "source_url", "ends_guess", "frequency_guess", "min_age_guess", "value_guess", "category_guess")}))
    else:
        print(f"- {c.get('title')}\n  entry: {c.get('entry_url')}\n  rules: {c.get('rules_url')}\n  listing: {c.get('source_url')}\n"
              f"  guesses: ends {c.get('ends_guess')}, {c.get('frequency_guess')}, age {c.get('min_age_guess')}, ${c.get('value_guess')}, {c.get('category_guess')}\n  key: {c.get('key')}")
