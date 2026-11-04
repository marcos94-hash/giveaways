#!/usr/bin/env bash
# Runs on the Mac mini from cron: get the latest finder code, scrape, push candidates.
set -euo pipefail
REPO_DIR="$HOME/giveaways"
KEY="$HOME/.ssh/giveaways_deploy"
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
cd "$REPO_DIR"
echo "--- $(date -Is) finder run"
git pull -q --rebase origin main
python3 scraper/finder.py --out data/candidates.json --report data/scrape_report.json
git add data/candidates.json data/scrape_report.json
if ! git diff --cached --quiet; then
  git -c user.name="Mac mini finder" -c user.email="finder@firsttradingbot.local" \
      commit -q -m "finder: new candidates $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q origin main || { git pull -q --rebase origin main && git push -q origin main; }
  echo "pushed"
else
  echo "no changes"
fi
