#!/usr/bin/env bash
# One-time setup on the Mac mini (Ubuntu). Usage:
#   curl -fsSL https://raw.githubusercontent.com/<you>/giveaways/main/mac_mini/install.sh | bash -s -- <github-username>
set -euo pipefail
GH_USER="${1:?usage: install.sh <github-username>}"
REPO_DIR="$HOME/giveaways"
KEY="$HOME/.ssh/giveaways_deploy"

for tool in git python3 ssh-keygen; do
  command -v "$tool" >/dev/null || { echo "Installing $tool..."; sudo apt-get update -qq && sudo apt-get install -y -qq git python3 openssh-client; break; }
done

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "giveaways-mac-mini" -q
fi

echo
echo "=== Step 1: give the Mac mini permission to update the repo ==="
echo "Open: https://github.com/$GH_USER/giveaways/settings/keys/new"
echo "Title: Mac mini    Key: paste the line below    Tick 'Allow write access'    Add key"
echo
cat "$KEY.pub"
echo
read -rp "Press Enter once the key is added... " _ </dev/tty

export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull -q --rebase origin main
else
  git clone -q "git@github.com:$GH_USER/giveaways.git" "$REPO_DIR"
fi
chmod +x "$REPO_DIR/mac_mini/run.sh"

echo "=== Step 2: schedule the finder (6:17 AM and 4:17 PM, Mac mini time) ==="
LINE="17 6,16 * * * $REPO_DIR/mac_mini/run.sh >> $HOME/giveaways-finder.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'giveaways/mac_mini/run.sh' || true; echo "$LINE" ) | crontab -
crontab -l | grep giveaways

echo "=== Step 3: first run (takes a few minutes) ==="
"$REPO_DIR/mac_mini/run.sh"
echo
echo "Done. The Mac mini will look for giveaways twice a day and push them to GitHub."
echo "Log: $HOME/giveaways-finder.log"
