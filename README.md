# giveaways

A personal sweepstakes pipeline:

1. `scraper/finder.py` runs on the Mac mini twice a day (`mac_mini/run.sh` via cron). It reads public listing sites, obeys robots.txt, and pushes `data/candidates.json`.
2. A daily Claude task follows `REVIEW_TASK.md`. It reads each candidate's official rules, using `tools/queue.py`, which saves every decision so interrupted runs resume. Listings are `verified` (ready: the sponsor's rules confirm eligibility, free entry, deadline and entry limit) or `needs_rules_check`. Everything else stays queued as rejected, blocked, needs_review or parked, each with a reason.
3. The Giveaway Filler Chrome extension (`extension/`) reads `data/giveaways.json` from this repo. It fills forms only on listed entry pages and frames, only for verified giveaways unless you choose Fill anyway, and logs an entry only when you confirm it went through. Your details and birth date stay in the browser, never in this repo. Install, local setup, list refresh and daily use are in `extension/README.md`.

## Setup on the Mac mini

Run this once:

    curl -fsSL https://raw.githubusercontent.com/marcos94-hash/giveaways/main/mac_mini/install.sh | bash -s -- marcos94-hash

It makes a deploy key, asks you to add it to the repo with write access, clones the repo, adds the cron job, and does a first run.

The Mac mini runs whatever finder code is in this repo, so only give push access to people and tools you trust.

## Tests

    python3 tests/test_finder.py
    python3 tests/test_review.py
    node extension_tests/test_lib.mjs
    # browser test (Playwright + Chromium), from extension_tests/:
    #   python3 server.py site /tmp/gf_server.log &  node test_extension.mjs
