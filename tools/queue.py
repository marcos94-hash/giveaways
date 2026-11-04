#!/usr/bin/env python3
"""Review queue CLI. Every command saves immediately, so an interrupted run loses nothing.

  python3 tools/queue.py status
  python3 tools/queue.py next -n 25 --run RUN_ID        claim a batch (resumes interrupted work first)
  python3 tools/queue.py show KEY                       candidate + review history
  python3 tools/queue.py accept --run RUN_ID listing.json [--key KEY]
  python3 tools/queue.py reject KEY CODE "reason" [--evidence URL ...]
  python3 tools/queue.py blocked KEY CODE "reason" [--evidence URL ...]
  python3 tools/queue.py needs-review KEY CODE "reason" [--evidence URL ...]
  python3 tools/queue.py release --run RUN_ID           end of run: hand back unrecorded claims
  python3 tools/queue.py sweep                          retire ended candidates and listings
"""
import argparse
import json
import sys

import reviewlib as R


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("next"); p.add_argument("-n", type=int, default=25); p.add_argument("--run", required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("show"); p.add_argument("key")
    p = sub.add_parser("accept"); p.add_argument("listing"); p.add_argument("--key"); p.add_argument("--run")
    for name in ("reject", "blocked", "needs-review"):
        p = sub.add_parser(name); p.add_argument("key"); p.add_argument("code"); p.add_argument("reason")
        p.add_argument("--evidence", nargs="*", default=[])
    p = sub.add_parser("release"); p.add_argument("--run", required=True)
    sub.add_parser("sweep")
    a = ap.parse_args()

    log = R.load_log()
    data = R.load("giveaways.json", {"version": 1, "giveaways": []})
    cands = R.load("candidates.json", {"candidates": {}})["candidates"]
    t = R.now()

    if a.cmd == "status":
        print(json.dumps(R.counts(log, data, cands, t), indent=2))
        return

    if a.cmd == "next":
        resumed = R.release_expired(log, t)
        picked, info = R.plan(log, cands, data, a.n, t)
        if not a.dry_run:
            R.claim(log, picked, a.run, t)
            R.save_log(log)
        print(json.dumps({"run": a.run, "released_from_dead_runs": len(resumed), **info, "claimed": len(picked)}))
        for k in picked:
            c = cands.get(k, {})
            it = log["items"].get(k, {})
            prev = (it.get("claim") or {}).get("prev") or it
            print(json.dumps({"key": k, "title": c.get("title"), "entry_url": c.get("entry_url"), "rules_url": c.get("rules_url"),
                              "source_url": c.get("source_url"), "ends_guess": c.get("ends_guess"),
                              "frequency_guess": c.get("frequency_guess"), "min_age_guess": c.get("min_age_guess"),
                              "category_guess": c.get("category_guess"), "ends_how": c.get("ends_how"),
                              "review_flags": c.get("review_flags") or [k for k, v in (c.get("flags") or {}).items() if v],
                              "previous": {x: prev.get(x) for x in
                              ("status", "reason_code", "reason", "attempts", "listing_id", "evidence") if prev.get(x)}}))
        return

    if a.cmd == "show":
        k = R.key_of(a.key)
        print(json.dumps({"candidate": cands.get(k), "review": log["items"].get(k)}, indent=2))
        return

    if a.cmd == "accept":
        g = json.load(open(a.listing))
        key = R.key_of(a.key or g.pop("_candidate_key", None) or g["entry_url"])
        try:
            listing, how = R.upsert_listing(data, g, t)
        except ValueError as e:
            print(f"NOT SAVED: {e}", file=sys.stderr)
            sys.exit(1)
        verified = listing["verification"]["status"] == "verified"
        for k in {key, R.norm_url(listing["entry_url"])}:
            R.record(log, k, "listed", reason_code="verified" if verified else "needs_rules_check",
                     reason=listing["verification"].get("reason", ""), evidence=listing["verification"].get("evidence"),
                     t=t, listing_id=listing["id"], verified=verified)
        R.save("giveaways.json", data)
        R.save_log(log)
        print(json.dumps({"saved": how, "id": listing["id"], "verification": listing["verification"]["status"]}))
        return

    if a.cmd in ("reject", "blocked", "needs-review"):
        status = {"reject": "rejected", "blocked": "blocked", "needs-review": "needs_review"}[a.cmd]
        k = R.key_of(a.key)
        try:
            it = R.record(log, k, status, a.code, a.reason, a.evidence, t)
        except ValueError as e:
            print(f"NOT SAVED: {e}", file=sys.stderr)
            sys.exit(1)
        if not it.get("name"):
            it["name"] = cands.get(k, {}).get("title", "")
        R.save_log(log)
        print(json.dumps({"key": k, "status": it["status"], "attempts": it.get("attempts", 0), "next_retry_at": it.get("next_retry_at")}))
        return

    if a.cmd == "release":
        out = R.release_run(log, a.run)
        R.save_log(log)
        print(json.dumps({"released_unreviewed": len(out)}))
        return

    if a.cmd == "sweep":
        R.release_expired(log, t)
        out = R.sweep(log, data, cands, t)
        R.save("giveaways.json", data)
        R.save_log(log)
        print(json.dumps(out))
        return


if __name__ == "__main__":
    main()
