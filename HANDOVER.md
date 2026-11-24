# Ads Live Dashboard: owner and operations guide

Two password-protected web pages that show ad spend from Meta Ads and Google Ads, with a total, updated every hour. Each page also has a "Meta campaign detail" part: per campaign, the ad sets, funnel, spend by day and where the results came from (platform, placement, country, age and gender, device), plus the Meta account status and amount owed. This is the same data as the old one-off ad set report (`~/meta-ads-tool/build_cc_adset_report.py`), now for every campaign of both brands:

| Page | Shows | Password secret |
|---|---|---|
| `/lsaa/` | Lemon Sky AI Academy campaigns | `PW_LSAA` |
| `/creatorcity/` | CreatorCity campaigns | `PW_CREATORCITY` |

The tool only reads data. It cannot change, pause or start any ad.

## How it works

1. Every hour (minute 7), a free Cloudflare timer (`cloudflare-trigger/`, worker `ads-dashboard-timer`) asks GitHub to start the update. GitHub Actions (a free robot in GitHub) then runs `build.py`. GitHub's own schedule skips many runs, so it is only a backup, every 3 hours.
2. `build.py` asks the Meta Marketing API for spend on ad account `act_1363790602156847` (EarlyAdvantageAI). It also asks the Google Ads API for spend on the Google account of each brand: LSAA `479-468-6827`, CreatorCity `216-627-2119` (`google_customer_id` in `config.json`).
3. It sorts each campaign to a brand by its Facebook Page. If a campaign has no Page, it uses the name start (`LSAA |`, `LSA_`, `CC |`). Settings are in `config.json`.
4. `page.py` puts each brand's DAILY data (encrypted with the page) into the page. The browser does the sums for the date range picked (quick buttons or From/To dates) and shows one Meta campaign at a time (dropdown, or click a Meta row in the Campaigns table). The range and campaign are kept in the link (`#r=last7&c=<campaign id>`), so a view can be bookmarked. Reach cannot be added up day by day, so it is pulled for the quick ranges only and shows "-" for a custom range.
   `meta_detail.py` pulls the campaign detail data. A campaign's "result" comes from its biggest ad set's goal (purchases, sign-ups, leads, chats or page views).
5. StatiCrypt locks each page with its own password. Only locked pages go online. No spend figure is ever saved in the code or the logs.
6. GitHub Pages hosts the pages.

No computer needs to stay on. Nothing runs on a laptop.

## What the owner needs

| Item | Where it lives | Who must own it |
|---|---|---|
| GitHub repository | `github.com/<owner>/ads-live-dashboard` | A company GitHub organisation, not a person |
| `META_TOKEN` | Repository > Settings > Secrets and variables > Actions | System user token from the Meta business portfolio |
| `PW_LSAA`, `PW_CREATORCITY` | Same place | The page passwords |
| `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Same place | Google Ads API keys. The refresh token belongs to the Google login that made it. Replace it with one from a company login before that person leaves (see below) |
| Cloudflare account + worker `ads-dashboard-timer` | dash.cloudflare.com > Workers | A company Cloudflare account |
| `GH_TOKEN` (Cloudflare worker secret) | Cloudflare > worker > Settings > Variables | GitHub fine-grained token, Actions read and write on this repository only. It expires: make a new one before the date shown in GitHub |
| Meta system user | Meta Business Settings, portfolio Lemon Sky AI Academy (`737168432518874`) > System users | The company portfolio (it already does) |

The Meta token belongs to a system user in the company portfolio, not to a person. It does not expire. It keeps working when people leave.

The Google refresh token is different: it belongs to the person who made it. If that person loses access to the Google Ads accounts, the Google part stops. Google has no read-only API key, so give the company login only "Read only" access to the two Google Ads accounts.

## Hand over to a new owner (about 15 minutes)

1. Create a free GitHub organisation for the company (github.com > your picture > Your organizations > New organization > Free). Add at least two company admins.
2. Move the repository: repository > Settings > General > Danger Zone > Transfer ownership > choose the organisation.
3. After the move, open Settings > Secrets and variables > Actions. Check that `META_TOKEN`, `PW_LSAA`, `PW_CREATORCITY` and the five `GOOGLE_ADS_*` secrets are there. If not, add them again.
4. Open Settings > Pages. Check that Source is "GitHub Actions".
5. Open Actions > "Update dashboards" > Run workflow. Wait for a green tick.
6. The web address changes to `https://<organisation>.github.io/ads-live-dashboard/`. Send the new links to the people who use them.
7. Change the passwords (see below) and send the new ones.
8. Cloudflare timer: change `GH_REPO` in `cloudflare-trigger/wrangler.toml` to the new owner, make a new GitHub token for the new repository, then run `cloudflare-trigger/setup_timer.sh` from a company Cloudflare login.
9. Make a new Google refresh token from a company login (see "Change the Google keys") and paste it into `GOOGLE_ADS_REFRESH_TOKEN`.
10. Remove the old owner from the organisation and from the Meta system user, if needed.

## Daily tasks

None. The pages update by themselves.

## Common changes

**Change a password.** Settings > Secrets and variables > Actions > edit `PW_LSAA` or `PW_CREATORCITY`. Then Actions > Update dashboards > Run workflow. Old saved logins stop working.

**Refresh now.** Actions > Update dashboards > Run workflow.

**Add a brand.** Add a block under `brands` in `config.json` with its Facebook Page id, name prefixes, title and colour. Add a password secret and one StatiCrypt line in `.github/workflows/update.yml`.

**New campaigns.** No change needed. A new campaign shows when it runs on the brand's Facebook Page.

**Change the Meta token.** In Meta Business Settings > System users > `Meta_Ads` > Generate new token. Select the ad account, and give the `ads_read` permission (read-only is enough). Paste it into the `META_TOKEN` secret.

**Change the Google keys.** Use a company Google login that has access to the Lemon Sky manager account (MCC 390-139-0486). Make a new refresh token with the OAuth client in Google Cloud (the same steps as the original `google-ads.yaml` setup). Paste it into `GOOGLE_ADS_REFRESH_TOKEN`. The other four Google secrets stay the same unless the OAuth client or developer token changes.

**Add a Google account to a brand.** Put its 10-digit id (no dashes) in `google_customer_id` for that brand in `config.json`. The account must sit under the manager account and use MYR.

## If the page stops updating

The page shows a red warning when it is more than 3 hours old.

1. Open the repository > Actions. Look at the last "Update dashboards" run.
2. Red cross with "Graph HTTP 190": the Meta token is wrong or was removed. Make a new token (see above).
3. Red cross with "Graph HTTP 17" or "613": Meta rate limit. It usually fixes itself on the next run.
4. No runs for hours: check the Cloudflare timer (dash.cloudflare.com > Workers > ads-dashboard-timer > Logs). "GitHub said 401" = the GitHub token expired; make a new one and run `npx wrangler@4 secret put GH_TOKEN` in `cloudflare-trigger/`. No runs for days: Actions > "Update dashboards" > Enable workflow. The monthly "Keep schedule alive" job normally stops this.
5. Red cross at "Lock each page": a password secret is empty. Add it again.
6. Red banner "Google figures could not be read this hour" on the page: the Google part failed, Meta still shows. Look in the run log for "Google pull failed". `invalid_grant` = the refresh token is dead, make a new one (see above). Other errors usually fix themselves on the next run.

## Limits

- Meta Ads and Google Ads only. Other channels are not on these pages.
- "Today" is not final. Meta can add spend for some hours after midnight. Google figures can be about 3 hours behind.
- Results use each platform's own count (Meta: leads, sign-ups, chats; Google: conversions). The CRM, WhatsApp or Stripe stays the true record.
- The code is public (free GitHub Pages needs this). The data is not public: every page is encrypted. Do not put the token or passwords in any file.
- A person with the password can see the page. Change the password when people leave the team.

## Run on a computer (optional)

```bash
META_TOKEN=xxxx python3 build.py
# Google keys: GOOGLE_ADS_* variables, or ~/google-ads-tool/google-ads.yaml if it exists
```

Pages appear in `dist/` without a password. Do not upload `dist/` by hand.
