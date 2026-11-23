#!/usr/bin/env python3
"""
Ads Live Dashboard: builds one spend page per brand from the Meta Marketing API.

Read-only. Never changes anything in the ad account.

Output (plain HTML, encrypted later by the GitHub workflow):
    dist/lsaa/index.html
    dist/creatorcity/index.html
    dist/index.html                (simple landing page with the two links)

Run locally:
    python3 build.py               (token from $META_TOKEN, else the local
                                    meta-ads-tool config if it exists)

Settings live in config.json (brands, page ids, name prefixes).
See HANDOVER.md for how to run, change and hand over this tool.
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
MYT = dt.timezone(dt.timedelta(hours=8))          # account timezone is Asia/Singapore
NOW = dt.datetime.now(MYT)
TODAY = NOW.date()


# ------------------------------------------------------------------ token
def token():
    t = os.environ.get("META_TOKEN", "").strip()
    if t:
        return t
    local = os.path.expanduser(CFG.get("local_token_file", ""))
    if local and os.path.exists(local):
        return json.load(open(local))["access_token"]
    sys.exit("No Meta token. Set META_TOKEN.")


TOKEN = token()


def graph(path, **params):
    params["access_token"] = TOKEN
    url = "https://graph.facebook.com/%s/%s?%s" % (
        CFG["api_version"], path, urllib.parse.urlencode(params))
    return graph_url(url)


def graph_url(url):
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        # Never print the URL: it carries the token.
        raise RuntimeError("Graph HTTP %s: %s" % (e.code, body[:300])) from None


def graph_all(path, **params):
    out, d = [], graph(path, **params)
    while True:
        out += d.get("data", [])
        nxt = d.get("paging", {}).get("next")
        if not nxt:
            return out
        d = graph_url(nxt)


# ------------------------------------------------------------------ pull
def pull():
    acct = CFG["ad_account"]
    camps = graph_all("%s/campaigns" % acct, limit=200,
                      fields="name,effective_status,stop_time,daily_budget,lifetime_budget")
    sets = graph_all("%s/adsets" % acct, limit=500,
                     fields="campaign_id,effective_status,daily_budget,lifetime_budget,promoted_object")
    ads = graph_all("%s/ads" % acct, limit=500,
                    fields="campaign_id,creative{actor_id,object_story_spec{page_id}}")
    rows = graph_all("%s/insights" % acct, level="campaign", time_increment=1, limit=500,
                     fields="campaign_id,spend,impressions,clicks,actions",
                     time_range=json.dumps({"since": CFG["history_since"],
                                            "until": TODAY.isoformat()}))
    return camps, sets, ads, rows


def page_of_campaign(sets, ads):
    """Campaign id -> Facebook Page id, read from the ads, then from the ad sets."""
    m = {}
    for a in ads:
        cr = a.get("creative") or {}
        p = cr.get("actor_id") or (cr.get("object_story_spec") or {}).get("page_id")
        if p:
            m.setdefault(a["campaign_id"], p)
    for s in sets:
        p = (s.get("promoted_object") or {}).get("page_id")
        if p:
            m.setdefault(s["campaign_id"], p)
    return m


def brand_of(camp, page_map):
    p = page_map.get(camp["id"])
    for key, b in CFG["brands"].items():
        if p and p == b["page_id"]:
            return key
    for key, b in CFG["brands"].items():          # fallback: name prefix
        if any(camp["name"].startswith(x) for x in b["name_prefixes"]):
            return key
    return None


RESULT_TYPES = [("lead", "leads"), ("complete_registration", "sign-ups"),
                ("onsite_conversion.messaging_conversation_started_7d", "chats"),
                ("landing_page_view", "page views")]


def build_brand(key, camps, sets, page_map, rows):
    mine = {c["id"]: c for c in camps if brand_of(c, page_map) == key}
    daily = {}                                    # date -> spend
    per = {cid: {"today": 0.0, "yday": 0.0, "d7": 0.0, "month": 0.0, "life": 0.0,
                 "acts": {}, "impr": 0, "clicks": 0} for cid in mine}
    yday = TODAY - dt.timedelta(days=1)
    d7_start = TODAY - dt.timedelta(days=6)
    for r in rows:
        cid = r.get("campaign_id")
        if cid not in mine:
            continue
        day = dt.date.fromisoformat(r["date_start"])
        sp = float(r.get("spend") or 0)
        daily[day] = daily.get(day, 0.0) + sp
        p = per[cid]
        p["life"] += sp
        p["impr"] += int(r.get("impressions") or 0)
        p["clicks"] += int(r.get("clicks") or 0)
        if day == TODAY:
            p["today"] += sp
        if day == yday:
            p["yday"] += sp
        if day >= d7_start:
            p["d7"] += sp
        if day.year == TODAY.year and day.month == TODAY.month:
            p["month"] += sp
        for a in r.get("actions") or []:
            p["acts"][a["action_type"]] = p["acts"].get(a["action_type"], 0) + float(a.get("value") or 0)

    now_utc = dt.datetime.now(dt.timezone.utc)
    table = []
    for cid, c in mine.items():
        p = per[cid]
        live_sets = [s for s in sets if s.get("campaign_id") == cid
                     and s.get("effective_status") == "ACTIVE"]
        ended = False
        if c.get("stop_time"):
            try:
                ended = dt.datetime.strptime(c["stop_time"], "%Y-%m-%dT%H:%M:%S%z") < now_utc
            except ValueError:
                pass
        running = c.get("effective_status") == "ACTIVE" and bool(live_sets) and not ended
        budget = (int(c.get("daily_budget") or 0) or
                  sum(int(s.get("daily_budget") or 0) for s in live_sets)) / 100.0
        res, lab = 0, ""
        for t, l in RESULT_TYPES:
            if t in p["acts"]:
                res, lab = int(p["acts"][t]), l
                break
        if p["life"] == 0 and not running:
            continue
        table.append({"name": c["name"], "running": running, "budget": budget,
                      "res": res, "lab": lab, **{k: p[k] for k in
                      ("today", "yday", "d7", "month", "life", "impr", "clicks")}})
    table.sort(key=lambda t: (not t["running"], -t["d7"], -t["life"]))

    tot = {k: sum(t[k] for t in table) for k in ("today", "yday", "d7", "month", "life")}
    months = {}
    for d, sp in daily.items():
        months[(d.year, d.month)] = months.get((d.year, d.month), 0.0) + sp
    return {"table": table, "tot": tot, "daily": daily, "months": months,
            "running": sum(1 for t in table if t["running"])}


# ------------------------------------------------------------------ render
CSS = """
*{box-sizing:border-box}body{margin:0;background:#0f1115;color:#e8eaed;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 28px 64px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;
border-bottom:1px solid #262a33;padding-bottom:22px;margin-bottom:28px}
h1{margin:0;font-size:34px;line-height:1.1;font-weight:700;letter-spacing:-.01em}
h1 small{display:block;font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
color:var(--acc);margin-bottom:8px}
.stamp{color:#9aa0aa;font-size:13px;text-align:right}.stamp b{color:#e8eaed}
.stale{display:none;background:#5a1d1d;color:#ffd7d7;border-radius:8px;padding:10px 14px;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:28px}
.kpi{background:#171a21;border:1px solid #262a33;border-radius:12px;padding:16px 18px}
.kpi .l{color:#9aa0aa;font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.kpi .v{font-size:22px;white-space:nowrap;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .s{color:#9aa0aa;font-size:12px}.kpi.hi{border-color:var(--acc)}.kpi.hi .v{color:var(--acc)}
.card{background:#171a21;border:1px solid #262a33;border-radius:12px;padding:20px 22px;margin-bottom:22px}
.card h2{margin:0 0 14px;font-size:16px;font-weight:600}
.grid2{display:grid;grid-template-columns:2fr 1fr;gap:22px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid #232730;white-space:nowrap}
th{color:#9aa0aa;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
th:first-child,td:first-child{text-align:left;white-space:normal;min-width:250px}
tr.off td{color:#8a909a}.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;
margin-right:8px;font-weight:600}.on{background:var(--acc);color:#0f1115}.pz{background:#2a2e38;color:#9aa0aa}
tfoot td{font-weight:700;border-top:1px solid #3a3f4a;border-bottom:0}
svg text{fill:#9aa0aa;font-size:11px}.foot{color:#7d838d;font-size:12px;margin-top:30px}
@media(max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}
.scroll{overflow-x:auto}h1{font-size:28px}}
"""


def money(v, cur):
    return "%s %s" % (cur, "{:,.2f}".format(v))


def bars(daily, cur, acc):
    days = [TODAY - dt.timedelta(days=i) for i in range(29, -1, -1)]
    vals = [daily.get(d, 0.0) for d in days]
    top = max(vals) or 1.0
    W, H, pad = 740, 220, 28
    bw = (W - pad - 20) / len(days)
    out = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="Daily spend, last 30 days">' % (W, H + 24)]
    for f in (0.5, 1.0):
        y = H - (H - 16) * f
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#262a33"/>' % (pad, W, y, y))
        out.append('<text x="0" y="%.1f">%s</text>' % (y + 4, "{:,.0f}".format(top * f)))
    for i, (d, v) in enumerate(zip(days, vals)):
        h = (H - 16) * v / top
        x = pad + i * bw + 2
        col = acc if d == TODAY else "#5d6573" if v else "#262a33"
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s">'
                   '<title>%s: %s%s</title></rect>' % (
                       x, H - max(h, 1), bw - 4, max(h, 1), col, d.strftime("%a %d %b"),
                       money(v, cur), " (today so far)" if d == TODAY else ""))
        if i % 5 == 4 or d == TODAY:
            out.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (
                x + (bw - 4) / 2, H + 18, d.strftime("%d %b")))
    out.append("</svg>")
    return "".join(out)


def render(key, data):
    b = CFG["brands"][key]
    cur = CFG["currency"]
    e = html.escape
    t = data["tot"]
    kp = [("Today so far", t["today"], "updates every hour", True),
          ("Yesterday", t["yday"], (TODAY - dt.timedelta(days=1)).strftime("%a %d %b"), False),
          ("Last 7 days", t["d7"], "including today", False),
          ("This month", t["month"], TODAY.strftime("%B %Y"), False),
          ("All time", t["life"], "since " + dt.date.fromisoformat(CFG["history_since"]).strftime("%d %b %Y"), False)]
    kpis = "".join('<div class="kpi%s"><div class="l">%s</div><div class="v">%s</div><div class="s">%s</div></div>'
                   % (" hi" if hi else "", l, money(v, cur), s) for l, v, s, hi in kp)
    rows = []
    for r in data["table"]:
        tag = '<span class="tag on">LIVE</span>' if r["running"] else '<span class="tag pz">OFF</span>'
        res = ("%s %s" % ("{:,}".format(r["res"]), r["lab"])) if r["lab"] else "-"
        rows.append("<tr class='%s'><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                    "<td>%s</td><td>%s</td><td>%s</td></tr>" % (
                        "" if r["running"] else "off", tag, e(r["name"]),
                        money(r["budget"], cur) if r["running"] and r["budget"] else "-",
                        money(r["today"], cur), money(r["yday"], cur), money(r["d7"], cur),
                        money(r["month"], cur), money(r["life"], cur), res))
    if not rows:
        rows.append("<tr><td colspan='8'>No campaigns with spend yet.</td></tr>")
    foot = ("<tfoot><tr><td>Total</td><td></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td></td></tr></tfoot>"
            % tuple(money(t[k], cur) for k in ("today", "yday", "d7", "month", "life")))
    mrows = "".join("<tr><td>%s</td><td>%s</td></tr>" % (
        dt.date(y, m, 1).strftime("%b %Y"), money(v, cur))
        for (y, m), v in sorted(data["months"].items(), reverse=True) if v > 0) \
        or "<tr><td colspan='2'>No spend yet.</td></tr>"
    stamp_iso = NOW.isoformat()
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>%(title)s ad spend</title><style>:root{--acc:%(acc)s}%(css)s</style></head><body><div class="wrap">
<header><h1><small>Meta Ads spend</small>%(title)s</h1>
<div class="stamp">Updated <b>%(stamp)s</b> (Malaysia time)<br>%(running)d campaign(s) live now</div></header>
<div class="stale" id="stale">This page has not updated for more than 3 hours. The numbers can be old. See HANDOVER.md, section "If the page stops updating".</div>
<div class="kpis">%(kpis)s</div>
<div class="grid2"><div class="card"><h2>Daily spend, last 30 days</h2>%(bars)s</div>
<div class="card"><h2>Spend by month</h2><table><tbody>%(mrows)s</tbody></table></div></div>
<div class="card scroll"><h2>Campaigns</h2><table><thead><tr><th>Campaign</th><th>Daily budget</th><th>Today</th>
<th>Yesterday</th><th>Last 7 days</th><th>This month</th><th>All time</th><th>Results (all time)</th></tr></thead>
<tbody>%(rows)s</tbody>%(foot)s</table></div>
<p class="foot">Source: Meta Marketing API, ad account %(acct_name)s, read-only. Amounts in %(cur)s, before tax.
Today is not final: Meta can add spend for a few hours after midnight. Results use Meta's own count
(leads, sign-ups or chats); the CRM or Stripe stays the true record.</p>
</div><script>if(Date.now()-new Date("%(iso)s").getTime()>3*3600e3)document.getElementById("stale").style.display="block"</script>
</body></html>""" % {"title": e(b["title"]), "acc": b["accent"], "css": CSS, "kpis": kpis,
                     "stamp": NOW.strftime("%a %d %b %Y, %H:%M"), "running": data["running"],
                     "bars": bars(data["daily"], cur, b["accent"]), "mrows": mrows,
                     "rows": "".join(rows), "foot": foot, "cur": cur,
                     "acct_name": e(CFG["ad_account_name"]), "iso": stamp_iso}


def landing():
    links = "".join('<li><a href="%s/">%s</a></li>' % (k, html.escape(b["title"]))
                    for k, b in CFG["brands"].items())
    return ("<!doctype html><html><head><meta charset='utf-8'><meta name='robots' content='noindex'>"
            "<title>Ad spend dashboards</title><style>body{font:16px -apple-system,sans-serif;background:#0f1115;"
            "color:#e8eaed;padding:60px}a{color:#8fd3ff}</style></head><body><h1>Ad spend dashboards</h1>"
            "<ul>%s</ul><p>Each page has its own password.</p></body></html>" % links)


def main():
    camps, sets, ads, rows = pull()
    pm = page_of_campaign(sets, ads)
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    for key in CFG["brands"]:
        data = build_brand(key, camps, sets, pm, rows)
        out = os.path.join(HERE, "dist", key)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "index.html"), "w") as f:
            f.write(render(key, data))
        # Safe to print: counts only, no spend figures in public logs.
        print("%s: %d campaigns on page, %d live" % (key, len(data["table"]), data["running"]))
    with open(os.path.join(HERE, "dist", "index.html"), "w") as f:
        f.write(landing())
    with open(os.path.join(HERE, "dist", ".nojekyll"), "w") as f:
        f.write("")


if __name__ == "__main__":
    main()
