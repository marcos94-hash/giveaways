# giveaways

Marco's sweepstakes pipeline:

1. `scraper/finder.py` runs on the Mac mini twice a day (`mac_mini/run.sh` via cron). It reads public listing sites, obeys robots.txt, and pushes `data/candidates.json`.
2. A daily Claude task follows `REVIEW_TASK.md`. It reads each new candidate's official rules and keeps only the free giveaways an adult NJ resident can enter. Then it updates `data/giveaways.json` and republishes the Giveaway Board artifact.
3. The Giveaway Filler Chrome extension reads `data/giveaways.json` from this repo. It fills in the entry forms and tracks the entry limits. Marco clicks submit.

## Setup on the Mac mini

Run this once:

    curl -fsSL https://raw.githubusercontent.com/marcos94-hash/giveaways/main/mac_mini/install.sh | bash -s -- marcos94-hash

It makes a deploy key, asks you to add it to the repo with write access, clones the repo, adds the cron job, and does a first run.

The Mac mini runs whatever finder code is in this repo, so only give push access to people and tools you trust.

## Tests

    python3 tests/test_finder.py
