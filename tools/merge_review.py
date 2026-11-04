#!/usr/bin/env python3
"""Batch version of tools/queue.py (all-or-nothing). Prefer queue.py during a run: it saves
each decision as you make it, so an interrupted run can resume.

batch.json:
{
  "accepted":     [ <listing with a verification block> (+ optional "_candidate_key") ],
  "rejected":     [ {"key": "...", "code": "<REJECT_CODES>", "reason": "...", "evidence": [...]} ],
  "blocked":      [ {"key": "...", "code": "<RETRY_CODES>", "reason": "..."} ],
  "needs_review": [ {"key": "...", "code": "<RETRY_CODES>", "reason": "..."} ]
}
"""
import argparse
import copy
import json
import sys

import reviewlib as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    batch = json.load(open(a.batch))
    t = R.now()
    log = R.load_log()
    data = R.load("giveaways.json", {"version": 1, "giveaways": []})
    work_log, work_data = copy.deepcopy(log), copy.deepcopy(data)
    out = {"added": [], "updated": [], "rejected": 0, "blocked": 0, "needs_review": 0, "invalid": []}

    for g in batch.get("accepted", []):
        g = dict(g)
        cand = g.pop("_candidate_key", None)
        try:
            listing, how = R.upsert_listing(work_data, g, t)
        except (ValueError, KeyError) as e:
            out["invalid"].append(str(e))
            continue
        out[how].append(listing["name"])
        ok = listing["verification"]["status"] == "verified"
        for k in {R.norm_url(listing["entry_url"]), R.key_of(cand) if cand else None} - {None}:
            R.record(work_log, k, "listed", "verified" if ok else "needs_rules_check",
                     listing["verification"].get("reason", ""), listing["verification"].get("evidence"), t, listing["id"], ok)

    for status, field in (("rejected", "rejected"), ("blocked", "blocked"), ("needs_review", "needs_review")):
        for r in batch.get(field, []):
            k = r.get("key") or r.get("url")
            try:
                if not k:
                    raise ValueError("item needs key")
                it = R.record(work_log, R.key_of(k), status, r.get("code", ""), r.get("reason", ""), r.get("evidence"), t)
                it.setdefault("name", r.get("name", ""))
                out[status] += 1
            except ValueError as e:
                out["invalid"].append(f"{r.get('name') or k}: {e}")

    ended = R.sweep(work_log, work_data, R.load("candidates.json", {"candidates": {}})["candidates"], t)
    out["ended_removed"] = ended["listings_ended"]
    out["counts"] = R.counts(work_log, work_data, R.load("candidates.json", {"candidates": {}})["candidates"], t)
    print(json.dumps(out, indent=2))
    if out["invalid"]:
        print("\nFix the invalid entries above and run again. Nothing was written.", file=sys.stderr)
        sys.exit(1)
    if a.dry_run:
        return
    work_data["updated"] = t.date().isoformat()
    R.save("giveaways.json", work_data)
    R.save_log(work_log)
    with open(f"{R.DATA}/run_log.md", "a") as f:
        f.write(f"- {t.strftime('%Y-%m-%d %H:%M')} ET (batch): +{len(out['added'])} added, {len(out['updated'])} updated, "
                f"{out['rejected']} rejected, {out['blocked']} blocked, {out['needs_review']} needs review\n")


if __name__ == "__main__":
    main()
