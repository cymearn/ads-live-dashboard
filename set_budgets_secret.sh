#!/bin/sh
# Copies the local approved budget register (budgets.json, not in git because the
# repo is public) into the GitHub secret BUDGETS_JSON, then starts an update so
# both pages show it. Run after every change to budgets.json.
set -e
cd "$(dirname "$0")"
python3 -c "import json; json.load(open('budgets.json'))"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh secret set BUDGETS_JSON -R "$REPO" < budgets.json
gh workflow run update.yml -R "$REPO"
echo "BUDGETS_JSON updated on $REPO. Pages update in about 2 minutes."
