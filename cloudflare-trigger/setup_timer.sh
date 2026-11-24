#!/bin/zsh
# Puts the hourly timer online in Cloudflare. Run once. Safe to run again.
set -e
cd "$(dirname "$0")"
if npx --yes wrangler@4 whoami 2>/dev/null | grep -q "You are logged in"; then
  echo "Step 1 of 3: already logged in to Cloudflare."
else
  echo "Step 1 of 3: a browser opens. Log in to Cloudflare and click Allow."
  npx --yes wrangler@4 login
fi
echo "Step 2 of 3: putting the timer online..."
npx --yes wrangler@4 deploy
echo "Step 3 of 3: paste the GitHub token, then press Enter (nothing shows while you paste)."
npx --yes wrangler@4 secret put GH_TOKEN
echo "Done. The timer starts the dashboard update at minute 7 of every hour."
