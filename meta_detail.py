"""
Meta campaign detail for the dashboards (read-only).

Per campaign: ad sets (spend, impressions, reach, frequency, clicks, CTR, cost per
click, page views, result, cost per result), funnel by ad set, spend by day by ad
set, and where the results came from (platform, placement, country, age and
gender, device). Also the Meta ad account status and amount owed.

Same logic as ~/meta-ads-tool/build_cc_adset_report.py, for every campaign.
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
def pull(graph, graph_all, acct, since, until):
    rng = json.dumps({"since": since, "until": until})
    account = graph(acct, fields="account_status,balance,currency")
    ad_life = graph_all("%s/insights" % acct, level="adset", limit=500, time_range=rng,
                        fields="campaign_id,adset_id,adset_name,spend,impressions,reach,frequency,actions")
    ad_daily = graph_all("%s/insights" % acct, level="adset", time_increment=1, limit=500,
                         time_range=rng, fields="campaign_id,adset_id,spend")
    bds = {}
    for title, bd, _ in BREAKDOWNS:
        bds[title] = graph_all("%s/insights" % acct, level="campaign", breakdowns=bd, limit=500,
                               time_range=rng, fields="campaign_id,spend,impressions,actions")
    return {"account": account, "ad_life": ad_life, "ad_daily": ad_daily, "bds": bds}


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


def _bd_table(title, rows, cols, rtype, cur):
    rows = [r for r in rows if r["spend"] > 0]
    if not rows:
        return ""
    rows.sort(key=lambda r: (-r[rtype] if rtype else 0, -r["spend"]))
    tsp = sum(r["spend"] for r in rows) or 1
    head = "".join("<th>%s</th>" % LABEL[c] for c in cols)
    body = "".join(
        "<tr><td>%s</td><td>%s</td><td>%.0f%%</td>%s</tr>" % (
            e(r["lab"]), rm(r["spend"], cur), r["spend"] / tsp * 100,
            "".join("<td%s>%s</td>" % (" class='res'" if c == rtype else "", "{:,}".format(r[c]))
                    for c in cols)) for r in rows)
    tot = "<tr class='sum'><td>Total</td><td>%s</td><td>100%%</td>%s</tr>" % (
        rm(sum(r["spend"] for r in rows), cur),
        "".join("<td%s>%s</td>" % (" class='res'" if c == rtype else "",
                                   "{:,}".format(sum(r[c] for r in rows))) for c in cols))
    return ("<h4>%s</h4><div class='scroll'><table class='dt'><thead><tr><th>%s</th><th>Spend</th>"
            "<th>Share of spend</th>%s</tr></thead><tbody>%s%s</tbody></table></div>" % (
                title, title, head, body, tot))


# ------------------------------------------------------------------ one campaign
def campaign_section(camp, sets, det, rtype, acct_ok, running, cur, today):
    cid = camp["id"]
    camp_on = camp.get("effective_status") == "ACTIVE"
    now = dt.datetime.now(dt.timezone.utc)

    def ended(s):
        try:
            return bool(s.get("end_time")) and dt.datetime.strptime(s["end_time"], "%Y-%m-%dT%H:%M:%S%z") < now
        except ValueError:
            return False

    def pill(on):
        """on = would deliver if the account were paid up."""
        if on and not acct_ok:
            return '<span class="tag warn">Set to Active, no delivery</span>'
        return '<span class="tag on">LIVE</span>' if on else '<span class="tag pz">OFF</span>'

    smap = {s["id"]: s for s in sets if s.get("campaign_id") == cid}
    life = [r for r in det["ad_life"] if r.get("campaign_id") == cid and float(r.get("spend") or 0) > 0]
    if not life:
        return ""
    days = {}
    for r in det["ad_daily"]:
        if r.get("campaign_id") == cid and float(r.get("spend") or 0) > 0:
            days.setdefault(r["date_start"], {})[r["adset_id"]] = float(r["spend"])
    rows = []
    for r in life:
        s = smap.get(r["adset_id"], {})
        sp = float(r["spend"])
        mine = sorted(day for day, v in days.items() if r["adset_id"] in v)
        x = {"id": r["adset_id"], "name": r.get("adset_name", ""),
             "on": camp_on and s.get("effective_status") == "ACTIVE" and not ended(s),
             "spend": sp, "impr": int(r.get("impressions") or 0), "reach": int(r.get("reach") or 0),
             "freq": float(r.get("frequency") or 0),
             "first": mine[0] if mine else "", "last": mine[-1] if mine else "", "ndays": len(mine)}
        for t, _ in FUNNEL:
            x[t] = act(r, t)
        if s.get("daily_budget") not in (None, "", "0"):
            x["budget"] = "budget %s/day" % rm(int(s["daily_budget"]) / 100, cur, 0)
        elif s.get("lifetime_budget") not in (None, "", "0"):
            x["budget"] = "budget %s total" % rm(int(s["lifetime_budget"]) / 100, cur, 0)
        else:
            x["budget"] = "campaign budget"
        rows.append(x)
    rows.sort(key=lambda x: -x["spend"])
    for x, n in zip(rows, short_names([x["name"] for x in rows])):
        x["short"] = n
    rlab = LABEL.get(rtype, "Results")
    tot = {k: sum(x[k] for x in rows) for k in ["spend", "impr"] + [t for t, _ in FUNNEL]}
    res = tot.get(rtype, 0) if rtype else 0
    cols = [t for t, _ in FUNNEL if tot[t] > 0 or t in ("link_click", rtype)]
    maxsp = max(x["spend"] for x in rows) or 1
    first = min((x["first"] for x in rows if x["first"]), default="")
    last = max((x["last"] for x in rows if x["last"]), default="")


    # mini KPIs
    k = ['<div class="mk"><div class="l">Spend</div><div class="v">%s</div><div class="s">%s to %s</div></div>'
         % (rm(tot["spend"], cur), d(first), d(last)),
         '<div class="mk"><div class="l">Link clicks</div><div class="v">%s</div><div class="s">%s impressions</div></div>'
         % ("{:,}".format(tot["link_click"]), "{:,}".format(tot["impr"]))]
    for t in cols:
        if t == "link_click":
            continue
        sub = ("%s each, Meta-counted" % rm(tot["spend"] / tot[t], cur) if t == rtype and tot[t]
               else "%s of link clicks" % pct(tot[t], tot["link_click"]))
        k.append('<div class="mk%s"><div class="l">%s</div><div class="v">%s</div><div class="s">%s</div></div>'
                 % (" hi" if t == rtype else "", LABEL[t], "{:,}".format(tot[t]), sub))

    # ad set table
    ab = "".join(
        "<tr><td><b>%s</b><div class='sm'>%s %s · %s to %s (%d days with spend)</div></td>"
        "<td>%s<div class='bar'><i style='width:%.0f%%'></i></div></td><td>%s</td><td>%s</td><td>%.2f</td>"
        "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='res'>%s</td><td class='res'>%s</td></tr>" % (
            e(x["name"]), pill(x["on"]), e(x["budget"]), d(x["first"]), d(x["last"]), x["ndays"],
            rm(x["spend"], cur), x["spend"] / maxsp * 100, "{:,}".format(x["impr"]), "{:,}".format(x["reach"]),
            x["freq"], "{:,}".format(x["link_click"]), ("%.2f%%" % (x["link_click"] / x["impr"] * 100) if x["impr"] else "-"),
            rm(x["spend"] / x["link_click"], cur) if x["link_click"] else "-", "{:,}".format(x["landing_page_view"]),
            "{:,}".format(x.get(rtype, 0)) if rtype else "-",
            rm(x["spend"] / x[rtype], cur) if rtype and x.get(rtype) else "-") for x in rows)
    adtable = ("<div class='scroll'><table class='dt'><thead><tr><th>Ad set</th><th>Spend</th><th>Impressions</th>"
               "<th>Reach</th><th>Frequency</th><th>Link clicks</th><th>CTR</th><th>Cost per click</th>"
               "<th>Page views</th><th>%s</th><th>Cost per result</th></tr></thead><tbody>%s</tbody></table></div>"
               % ("Result (page views)" if rtype == "landing_page_view" else rlab, ab))

    # funnel by ad set
    extra = []
    if tot["initiate_checkout"] > 0:
        extra.append(("Click to checkout", "initiate_checkout"))
    if rtype and rtype not in ("link_click", "initiate_checkout"):
        extra.append(("Click to %s" % rlab.lower().rstrip("s"), rtype))
    fh = "".join("<th>%s</th>" % LABEL[c] for c in cols) + "".join("<th>%s</th>" % a for a, _ in extra)
    fb = "".join("<tr><td>%s</td>%s%s</tr>" % (
        e(x["name"]),
        "".join("<td%s>%s</td>" % (" class='res'" if c == rtype else "", "{:,}".format(x[c])) for c in cols),
        "".join("<td>%s</td>" % pct(x[t], x["link_click"]) for _, t in extra)) for x in rows)
    funnel = ("<h4>Funnel by ad set</h4><div class='scroll'><table class='dt'><thead><tr><th>Ad set</th>%s"
              "</tr></thead><tbody>%s</tbody></table></div>" % (fh, fb))

    # spend by day by ad set (newest first)
    dh = "".join("<th>%s</th>" % e(x["short"]) for x in rows)
    db = "".join("<tr><td>%s</td>%s<td><b>%s</b></td></tr>" % (
        dt.date.fromisoformat(day).strftime("%a %-d %b %Y"),
        "".join("<td>%s</td>" % (rm(days[day][x["id"]], cur) if x["id"] in days[day] else "-") for x in rows),
        rm(sum(days[day].values()), cur)) for day in sorted(days, reverse=True))
    daily = ("<h4>Spend by day</h4><div class='scroll daybox'><table class='dt'><thead><tr><th>Day</th>%s"
             "<th>Total</th></tr></thead><tbody>%s</tbody></table></div>" % (dh, db))

    # where the results came from
    bd_cols = [c for c in cols if c != "landing_page_view" or rtype == "landing_page_view"]
    bdh = ""
    for title, _, lab in BREAKDOWNS:
        agg = {}
        for r in det["bds"][title]:
            if r.get("campaign_id") != cid:
                continue
            key = lab(r)
            a = agg.setdefault(key, dict({"lab": key, "spend": 0.0}, **{t: 0 for t, _ in FUNNEL}))
            a["spend"] += float(r.get("spend") or 0)
            for t, _ in FUNNEL:
                a[t] += act(r, t)
        bdh += _bd_table(title, list(agg.values()), bd_cols, rtype, cur)
    where = ""
    if bdh:
        where = ("<h4 class='big'>Where the results came from</h4><p class='sm'>All ad sets in this campaign "
                 "together. Rows with the most %s come first. %s%s Small counts are early signs only. Meta can "
                 "give a breakdown total a few ringgit different from the campaign total.</p>%s"
                 % (rlab.lower(),
                    "Country spend includes the retargeting ad set's spend, so it can differ from the ad set table. "
                    if any("retarget" in x["name"].lower() for x in rows) else "",
                    "Meta gives each event to the row it was delivered on, so a row can show more purchases than "
                    "checkouts." if tot["purchase"] or tot["initiate_checkout"] else
                    "Meta gives each event to the row it was delivered on, so a row can differ slightly from the "
                    "ad set table.", bdh))

    any_active = running or (not acct_ok and any(x["on"] for x in rows))
    head_pill = pill(any_active)
    meta = "Spend %s · %s %s · %s per %s" % (
        rm(tot["spend"], cur), "{:,}".format(res), rlab.lower(),
        rm(tot["spend"] / res, cur) if res else "-", rlab.lower().rstrip("s")) if rtype else \
        "Spend %s" % rm(tot["spend"], cur)
    recent = last and dt.date.fromisoformat(last) >= today - dt.timedelta(days=7)
    return ("<details class='card camp'%s><summary><span class='ct'>%s%s</span><span class='cm'>%s</span></summary>"
            "<div class='mks'>%s</div>%s%s%s%s</details>" % (
                " open" if (running or any_active or recent) else "", head_pill, e(camp["name"]), meta,
                "".join(k), adtable, funnel, daily, where))


NOTES = """<div class="card notes"><h2>How to read the campaign detail</h2><ul>
<li><b>Result</b> is what each campaign was bought for (its ad set goal): purchases, sign-ups, leads, chats or page views.</li>
<li><b>Purchases, sign-ups, page views and checkouts</b> are counted by Meta from the site pixel, which only fires for visitors who accept the cookie banner. Stripe and the CRM are the true record, so treat these as lower bounds, and treat region-to-region funnel rates as indicative only.</li>
<li><b>Budgets</b> are the current settings. Daily budgets may have been changed during the run, so daily spend can sit above or below them.</li>
<li><b>Reach</b> is counted per ad set. A person who saw two ad sets is counted twice, so reach is not added up.</li>
<li><b>CTR</b> is link clicks over impressions. <b>Cost per click</b> is spend over link clicks.</li>
<li>Campaigns that are live, or spent in the last 7 days, open by default. Click a campaign name to open or close it.</li>
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
