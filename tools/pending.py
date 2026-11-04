#!/usr/bin/env python3
"""Preview what the next review batch would contain, without claiming anything."""
import argparse
import json

import reviewlib as R

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=25)
a = ap.parse_args()
log = R.load_log()
data = R.load("giveaways.json", {"giveaways": []})
cands = R.load("candidates.json", {"candidates": {}})["candidates"]
t = R.now()
R.release_expired(log, t)
picked, info = R.plan(log, cands, data, a.n, t)
print(json.dumps({**R.counts(log, data, cands, t), **info}, indent=2))
for k in picked:
    c = cands.get(k, {})
    prev = log["items"].get(k, {})
    print(f"- {c.get('title')}  [{prev.get('status', 'new')}]\n  entry: {c.get('entry_url')}\n  key: {k}")
