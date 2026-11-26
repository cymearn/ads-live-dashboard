"""
Meta campaign detail for the dashboards (read-only).

Per campaign: ad sets (spend, impressions, reach, frequency, clicks, CTR, cost per
click, page views, result, cost per result), funnel by ad set, spend by day by ad
set, and where the results came from (platform, placement, country, age and
gender, device). Also the Meta ad account status and amount owed.

Same logic as ~/meta-ads-tool/build_cc_adset_report.py, for every campaign. page.py
packs this data per day; the browser does the sums for the date range picked.
"""
import datetime as dt
import html
import json

CHAT = "onsite_conversion.messaging_conversation_started_7d"
FUNNEL = [("link_click", "Link clicks"), ("landing_page_view", "Page views"),
          ("complete_registration", "Sign-ups"), ("initiate_checkout", "Checkouts started"),
          ("purchase", "Purchases"), ("lead", "Leads"), (CHAT, "Chats")]
LABEL = dict(FUNNEL)
EVENT = {"PURCHASE": "purchase", "COMPLETE_REGISTRATION": "complete_registration",
         "LEAD": "lead", "INITIATED_CHECKOUT": "initiate_checkout"}
GOAL = {"LEAD_GENERATION": "lead", "QUALITY_LEAD": "lead", "CONVERSATIONS": CHAT,
        "LANDING_PAGE_VIEWS": "landing_page_view", "LINK_CLICKS": "link_click"}
ACCT_STATUS = {1: "Active", 2: "Disabled", 3: "Unsettled (payment due)", 7: "Pending review",
               8: "Pending settlement", 9: "In grace period", 100: "Pending closure", 101: "Closed"}

POS = {"facebook_reels": "Reels", "instagram_reels": "Reels", "feed": "Feed", "instagram_stories": "Stories",
       "facebook_stories": "Stories", "marketplace": "Marketplace", "explore_home": "Explore",
       "profile_feed": "Profile feed", "facebook_profile_feed": "Profile feed",
       "instagram_profile_feed": "Profile feed", "instagram_explore": "Explore",
       "instagram_explore_grid_home": "Explore", "facebook_notification": "Notifications",
       "instream_video": "In-stream video", "search": "Search", "video_feeds": "Video feeds",
       "an_classic": "Audience Network", "rewarded_video": "Rewarded video",
       "facebook_reels_overlay": "Reels overlay", "messenger_inbox": "Inbox",
       "messenger_stories": "Stories", "threads_feed": "Feed", "instagram_search": "Search",
       "whatsapp_status": "status", "whatsapp_status_ads": "status", "unknown": ""}
CTRY = {"GB": "UK", "AU": "Australia", "CA": "Canada", "US": "United States", "MY": "Malaysia",
        "SG": "Singapore", "NZ": "New Zealand", "IE": "Ireland", "IN": "India", "ID": "Indonesia",
        "PH": "Philippines", "TH": "Thailand", "VN": "Vietnam", "AE": "UAE", "JP": "Japan"}
DEV = {"mobile_app": "Phone app", "desktop": "Desktop", "mobile_web": "Phone browser",
       "unknown": "Not known to Meta"}
PLAT = {"facebook": "Facebook", "instagram": "Instagram", "messenger": "Messenger",
        "audience_network": "Audience Network", "threads": "Threads", "whatsapp": "WhatsApp", "unknown": "Not known to Meta"}


def _plat(x):
    return PLAT.get(x.get("publisher_platform"), str(x.get("publisher_platform")).capitalize())


def _place(x):
    if x.get("publisher_platform") == "unknown":
        return "Not known to Meta"
    pos = x.get("platform_position", "")
    plat = _plat(x)
    lab = POS.get(pos, pos.replace("_", " "))
    if lab.lower().startswith(plat.lower()):
        lab = lab[len(plat):].strip()
    return ("%s %s" % (plat, lab)).strip() if lab else plat


def _age(x):
    g = {"male": "male", "female": "female"}.get(x.get("gender"), "gender not known")
    return "%s, %s" % (x.get("age"), g)


BREAKDOWNS = [("Platform", "publisher_platform", _plat),
              ("Placement", "publisher_platform,platform_position", _place),
              ("Country", "country", lambda x: CTRY.get(x["country"], x["country"])),
              ("Age and gender", "age,gender", _age),
              ("Device", "device_platform", lambda x: DEV.get(x["device_platform"], x["device_platform"]))]


def act(r, t):
    for x in r.get("actions") or []:
        if x["action_type"] == t:
            return int(float(x.get("value") or 0))
    return 0


# ------------------------------------------------------------------ pull
def presets(today, since):
    """Fixed ranges where Meta reach is exact. Same keys and dates as the page's buttons."""
    t = today
    first = t.replace(day=1)
    last_m_end = first - dt.timedelta(days=1)
    return {"today": (t, t), "yesterday": (t - dt.timedelta(days=1), t - dt.timedelta(days=1)),
            "last7": (t - dt.timedelta(days=6), t), "last30": (t - dt.timedelta(days=29), t),
            "month": (first, t), "lastmonth": (last_m_end.replace(day=1), last_m_end),
            "all": (dt.date.fromisoformat(since), t)}


def pull(graph, graph_all, acct, since, until):
    rng = json.dumps({"since": since, "until": until})
    account = graph(acct, fields="account_status,balance,currency")
    ad_life = graph_all("%s/insights" % acct, level="adset", limit=500, time_range=rng,
                        fields="campaign_id,adset_id,adset_name,spend,impressions,reach,frequency,actions")
    ad_daily = graph_all("%s/insights" % acct, level="adset", time_increment=1, limit=500,
                         time_range=rng, fields="campaign_id,adset_id,spend,impressions,actions")
    bds = {}
    for title, bd, _ in BREAKDOWNS:
        bds[title] = graph_all("%s/insights" % acct, level="campaign", breakdowns=bd, limit=500,
                               time_increment=1, time_range=rng,
                               fields="campaign_id,spend,impressions,actions")
    # One call for all quick ranges (time_ranges); rows come back tagged with their dates.
    pr = presets(dt.date.fromisoformat(until), since)
    by_dates = {}
    for key, (a, b) in pr.items():
        by_dates.setdefault((a.isoformat(), b.isoformat()), []).append(key)
    reach = {key: [] for key in pr}
    rows = graph_all("%s/insights" % acct, level="adset", limit=500,
                     time_ranges=json.dumps([{"since": a, "until": b} for a, b in by_dates]),
                     fields="adset_id,reach,impressions")
    for r in rows:
        for key in by_dates.get((r.get("date_start"), r.get("date_stop")), []):
            reach[key].append(r)
    return {"account": account, "ad_life": ad_life, "ad_daily": ad_daily, "bds": bds, "reach": reach}


def result_types(sets, ad_life):
    """Campaign id -> the action type its biggest-spend ad set was bought for."""
    spend = {r["adset_id"]: float(r.get("spend") or 0) for r in ad_life}
    out = {}
    for s in sorted(sets, key=lambda s: -spend.get(s["id"], 0)):
        cid = s.get("campaign_id")
        if cid in out:
            continue
        g = s.get("optimization_goal", "")
        ev = (s.get("promoted_object") or {}).get("custom_event_type", "")
        if g in ("OFFSITE_CONVERSIONS", "VALUE") and ev in EVENT:
            out[cid] = EVENT[ev]
        elif g in GOAL:
            out[cid] = GOAL[g]
    return out


# ------------------------------------------------------------------ render helpers
e = html.escape


def rm(v, cur, dp=2):
    return "-" if v is None else "%s %s" % (cur, ("{:,.%df}" % dp).format(v))


def d(s):
    return dt.date.fromisoformat(s).strftime("%-d %b") if s else "-"


def pct(a, b):
    return "%.1f%%" % (a / b * 100) if b else "-"


def short_names(names):
    """Drop the name parts that all ad sets in a campaign share ("CC | PaidFirst | US" -> "US")."""
    parts = [n.split(" | ") for n in names]
    if len(parts) < 2:
        return names
    i = 0
    while all(len(p) > i + 1 for p in parts) and len({p[i] for p in parts}) == 1:
        i += 1
    return [" | ".join(p[i:]) for p in parts]


def account_banner(account, cur):
    st = int(account.get("account_status") or 0)
    owed = int(account.get("balance") or 0) / 100
    word = ACCT_STATUS.get(st, str(st))
    line = "Meta account: <b>%s</b> · %s owed (whole ad account, both brands)" % (e(word), rm(owed, cur))
    warn = ""
    if st != 1:
        warn = ('<div class="warnbox"><b>Meta delivery stopped.</b> The ad account is %s. %s is owed for the '
                'whole ad account, LSAA and CreatorCity together. Ad sets set to Active do not spend '
                'until this is settled.</div>' % (e(word.lower()), rm(owed, cur)))
    return line, warn


NOTES = """<div class="card notes"><h2>How to read the campaign detail</h2><ul>
<li><b>Result</b> is what each campaign was bought for (its ad set goal): purchases, sign-ups, leads, chats or page views.</li>
<li><b>Purchases, sign-ups, page views and checkouts</b> are counted by Meta from the site pixel, which only fires for visitors who accept the cookie banner. Stripe and the CRM are the true record, so treat these as lower bounds, and treat region-to-region funnel rates as indicative only.</li>
<li><b>Budgets</b> are the current settings. Daily budgets may have been changed during the run, so daily spend can sit above or below them.</li>
<li><b>Reach</b> is counted per ad set. A person who saw two ad sets is counted twice, so reach is not added up.</li>
<li><b>CTR</b> is link clicks over impressions. <b>Cost per click</b> is spend over link clicks.</li>
<li>The date bar changes everything below the top cards. The top cards always show today, yesterday, the last 7 days, this month and all time. The page keeps the range and campaign in the link, so you can bookmark it.</li>
<li><b>Ad previews</b> (tab inside the campaign detail) shows each ad's picture, text and button, with its spend and results for the date range. Live ads first; ads now off show only if they spent in the range. Video ads show their cover picture: use "Open Meta preview" to play them.</li>
<li>Pick a campaign in the dropdown, or click a Meta row in the Campaigns table, to see its detail. The dropdown lists Meta campaigns with spend in the range, live ones first.</li>
</ul></div>"""

CSS = """
.warnbox{background:#3d2e0f;border:1px solid #6b5216;color:#ffe2a6;border-radius:8px;padding:12px 16px;margin-bottom:20px}
.camp{padding:0;overflow:hidden}.camp>summary{cursor:pointer;list-style:none;padding:18px 22px;display:flex;
justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}.camp>summary::-webkit-details-marker{display:none}
.camp>summary .ct{font-weight:600;font-size:16px}.camp>summary .cm{color:#9aa0aa;font-size:13px}
.camp>summary:before{content:"+";color:var(--acc);font-weight:700;margin-right:6px}.camp[open]>summary:before{content:"-"}
.camp[open]>summary{border-bottom:1px solid #262a33}.camp>*:not(summary){margin-left:22px;margin-right:22px}
.mks{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px;margin-bottom:6px}
.mk{background:#12151b;border:1px solid #262a33;border-radius:10px;padding:10px 12px}
.mk .l{color:#9aa0aa;font-size:11px;text-transform:uppercase;letter-spacing:.07em}.mk .v{font-size:18px;font-weight:700;
font-variant-numeric:tabular-nums}.mk .s{color:#9aa0aa;font-size:11px}.mk.hi{border-color:var(--acc)}.mk.hi .v{color:var(--acc)}
.camp h4{margin:20px 22px 6px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--acc)}
.camp h4.big{font-size:14px;margin:26px 22px 6px;color:#e8eaed;text-transform:none;letter-spacing:0}
.camp p.sm{color:#9aa0aa;font-size:12px;margin:0 22px 4px}.camp .dt{margin-bottom:6px}
.camp .dt td,.camp .dt th{font-size:13px;padding:7px 7px}.camp .dt th{font-size:10px}
.camp .dt th:first-child,.camp .dt td:first-child{min-width:170px}
.sm{color:#9aa0aa;font-size:11px;font-weight:400;margin-top:3px}td.res{color:var(--acc);font-weight:700}
.bar{height:4px;background:#262a33;border-radius:2px;margin-top:4px;min-width:60px}.bar i{display:block;height:100%;background:var(--acc);border-radius:2px}
.daybox{max-height:320px;overflow-y:auto}.camp>*:last-child{margin-bottom:20px}
.tag.warn{background:#6b5216;color:#ffe2a6}.notes ul{margin:0;padding-left:18px;color:#c3c8d0;font-size:13px}.notes li{margin:4px 0}
"""
