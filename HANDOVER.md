# Ads Live Dashboard: owner and operations guide

Two password-protected web pages that show Meta Ads spend, updated every hour:

| Page | Shows | Password secret |
|---|---|---|
| `/lsaa/` | Lemon Sky AI Academy campaigns | `PW_LSAA` |
| `/creatorcity/` | CreatorCity campaigns | `PW_CREATORCITY` |

The tool only reads data. It cannot change, pause or start any ad.

## How it works

1. Every hour, GitHub Actions (a free robot in GitHub) runs `build.py`.
2. `build.py` asks the Meta Marketing API for spend on ad account `act_1363790602156847` (EarlyAdvantageAI).
3. It sorts each campaign to a brand by its Facebook Page. If a campaign has no Page, it uses the name start (`LSAA |`, `LSA_`, `CC |`). Settings are in `config.json`.
4. StatiCrypt locks each page with its own password. Only locked pages go online. No spend figure is ever saved in the code or the logs.
5. GitHub Pages hosts the pages.

No computer needs to stay on. Nothing runs on a laptop.

## What the owner needs

| Item | Where it lives | Who must own it |
|---|---|---|
| GitHub repository | `github.com/<owner>/ads-live-dashboard` | A company GitHub organisation, not a person |
| `META_TOKEN` | Repository > Settings > Secrets and variables > Actions | System user token from the Meta business portfolio |
| `PW_LSAA`, `PW_CREATORCITY` | Same place | The page passwords |
| Meta system user | Meta Business Settings, portfolio Lemon Sky AI Academy (`737168432518874`) > System users | The company portfolio (it already does) |

The Meta token belongs to a system user in the company portfolio, not to a person. It does not expire. It keeps working when people leave.

## Hand over to a new owner (about 15 minutes)

1. Create a free GitHub organisation for the company (github.com > your picture > Your organizations > New organization > Free). Add at least two company admins.
2. Move the repository: repository > Settings > General > Danger Zone > Transfer ownership > choose the organisation.
3. After the move, open Settings > Secrets and variables > Actions. Check that `META_TOKEN`, `PW_LSAA` and `PW_CREATORCITY` are there. If not, add them again.
4. Open Settings > Pages. Check that Source is "GitHub Actions".
5. Open Actions > "Update dashboards" > Run workflow. Wait for a green tick.
6. The web address changes to `https://<organisation>.github.io/ads-live-dashboard/`. Send the new links to the people who use them.
7. Change the passwords (see below) and send the new ones.
8. Remove the old owner from the organisation and from the Meta system user, if needed.

## Daily tasks

None. The pages update by themselves.

## Common changes

**Change a password.** Settings > Secrets and variables > Actions > edit `PW_LSAA` or `PW_CREATORCITY`. Then Actions > Update dashboards > Run workflow. Old saved logins stop working.

**Refresh now.** Actions > Update dashboards > Run workflow.

**Add a brand.** Add a block under `brands` in `config.json` with its Facebook Page id, name prefixes, title and colour. Add a password secret and one StatiCrypt line in `.github/workflows/update.yml`.

**New campaigns.** No change needed. A new campaign shows when it runs on the brand's Facebook Page.

**Change the Meta token.** In Meta Business Settings > System users > `Meta_Ads` > Generate new token. Select the ad account, and give the `ads_read` permission (read-only is enough). Paste it into the `META_TOKEN` secret.

## If the page stops updating

The page shows a red warning when it is more than 3 hours old.

1. Open the repository > Actions. Look at the last "Update dashboards" run.
2. Red cross with "Graph HTTP 190": the Meta token is wrong or was removed. Make a new token (see above).
3. Red cross with "Graph HTTP 17" or "613": Meta rate limit. It usually fixes itself on the next run.
4. No runs for days: Actions > "Update dashboards" > Enable workflow. The monthly "Keep schedule alive" job normally stops this.
5. Red cross at "Lock each page": a password secret is empty. Add it again.

## Limits

- Meta only. Google Ads is not on these pages.
- "Today" is not final. Meta can add spend for some hours after midnight.
- Results use Meta's own count. The CRM, WhatsApp or Stripe stays the true record.
- The code is public (free GitHub Pages needs this). The data is not public: every page is encrypted. Do not put the token or passwords in any file.
- A person with the password can see the page. Change the password when people leave the team.

## Run on a computer (optional)

```bash
META_TOKEN=xxxx python3 build.py
```

Pages appear in `dist/` without a password. Do not upload `dist/` by hand.
