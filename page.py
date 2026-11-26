"""
Page builder with a date-range picker.

build.py pulls the data; brand_data() packs one brand's DAILY data into a small
JSON object; html() writes a page that does all sums in the browser for the
range picked (quick buttons or From/To dates). The page is encrypted by the
workflow, so the embedded data is never public.

Reach is not additive across days, so it is pulled for the quick ranges only
(meta_detail.presets) and shows "-" for a custom range.
"""
import datetime as dt
import html
import json

import meta_detail as md

SHORT = {"link_click": "lc", "landing_page_view": "lpv", "complete_registration": "reg",
         "initiate_checkout": "ic", "purchase": "pur", "lead": "lead", md.CHAT: "chat"}


def acts(r):
    out = {}
    for t, k in SHORT.items():
        v = md.act(r, t)
        if v:
            out[k] = v
    return out


def brand_data(key, cfg, brand_table, camps, sets, rows, det, gdata, rtypes, acct_line, acct_warn,
               gerr, now, today):
    """brand_table = build_brand(...)["table"] (status + budget per campaign)."""
    b = cfg["brands"][key]
    by_id = {t["id"]: t for t in brand_table if t.get("id")}
    now_utc = dt.datetime.now(dt.timezone.utc)

    def ended(x, field):
        try:
            return bool(x.get(field)) and dt.datetime.strptime(x[field], "%Y-%m-%dT%H:%M:%S%z") < now_utc
        except ValueError:
            return False

    cl, cd = [], {}
    meta_ids = set(by_id) & {c["id"] for c in camps}
    for c in camps:
        if c["id"] not in by_id:
            continue
        t = by_id[c["id"]]
        rt = rtypes.get(c["id"])
        if not rt:                                   # fallback: first result type with any count
            life = {}
            for r in rows:
                if r.get("campaign_id") == c["id"]:
                    for k, v in acts(r).items():
                        life[k] = life.get(k, 0) + v
            rt = next((x for x in ("lead", "complete_registration", md.CHAT, "landing_page_view")
                       if life.get(SHORT[x])), None)
        cl.append({"id": c["id"], "n": c["name"], "ch": "Meta", "run": t["running"], "bud": t["budget"],
                   "rt": SHORT.get(rt), "rl": md.LABEL.get(rt, "results").lower() if rt else "",
                   "on": c.get("effective_status") == "ACTIVE"})
    for r in rows:
        cid = r.get("campaign_id")
        if cid in meta_ids:
            a = acts(r)
            cd.setdefault(cid, []).append([r["date_start"], round(float(r.get("spend") or 0), 2),
                                           int(r.get("impressions") or 0), a.pop("lc", 0), a])

    # Google
    if gdata is not None:
        gcamps, grows = gdata
        gt = {t["name"]: t for t in brand_table if t.get("channel") == "Google"}
        for c in gcamps:
            cp = c["campaign"]
            gid = "g" + cp["id"]
            t = gt.get(cp["name"])
            has = any(r["campaign"]["id"] == cp["id"] for r in grows)
            if not t and not has:
                continue
            cl.append({"id": gid, "n": cp["name"], "ch": "Google", "run": bool(t and t["running"]),
                       "bud": (t or {}).get("budget", 0), "rt": "conv", "rl": "conversions", "on": False})
        for r in grows:
            m = r.get("metrics", {})
            conv = float(m.get("conversions") or 0)
            cd.setdefault("g" + r["campaign"]["id"], []).append(
                [r["segments"]["date"], round(int(m.get("costMicros") or 0) / 1e6, 2),
                 int(m.get("impressions") or 0), int(m.get("clicks") or 0),
                 {"conv": round(conv, 2)} if conv else {}])

    # Meta ad sets
    smap = {s["id"]: s for s in sets}
    camp_on = {c["id"]: c.get("effective_status") == "ACTIVE" for c in camps}
    life_spend = {r["adset_id"]: float(r.get("spend") or 0) for r in det["ad_life"]}
    al, ad = [], []
    for cid in meta_ids:
        mine = [r for r in det["ad_life"] if r.get("campaign_id") == cid and life_spend.get(r["adset_id"], 0) > 0]
        mine.sort(key=lambda r: -life_spend[r["adset_id"]])
        for r, short in zip(mine, md.short_names([r.get("adset_name", "") for r in mine])):
            s = smap.get(r["adset_id"], {})
            if s.get("daily_budget") not in (None, "", "0"):
                bud = "budget %s/day" % md.rm(int(s["daily_budget"]) / 100, cfg["currency"], 0)
            elif s.get("lifetime_budget") not in (None, "", "0"):
                bud = "budget %s total" % md.rm(int(s["lifetime_budget"]) / 100, cfg["currency"], 0)
            else:
                bud = "campaign budget"
            al.append({"id": r["adset_id"], "c": cid, "n": r.get("adset_name", ""), "s": short, "bud": bud,
                       "on": camp_on.get(cid, False) and s.get("effective_status") == "ACTIVE"
                       and not ended(s, "end_time")})
    keep = {a["id"] for a in al}
    for r in det["ad_daily"]:
        if r["adset_id"] in keep and float(r.get("spend") or 0) > 0:
            a = acts(r)
            ad.append([r["adset_id"], r["date_start"], round(float(r["spend"]), 2),
                       int(r.get("impressions") or 0), a])
    rc = {k: {r["adset_id"]: [int(r.get("reach") or 0), int(r.get("impressions") or 0)]
              for r in v if r["adset_id"] in keep} for k, v in det["reach"].items()}
    bd = {}
    for title, _, lab in md.BREAKDOWNS:
        bd[title] = [[r["campaign_id"], r["date_start"], lab(r), round(float(r.get("spend") or 0), 2), acts(r)]
                     for r in det["bds"][title] if r.get("campaign_id") in meta_ids and float(r.get("spend") or 0) > 0]

    gcid = b.get("google_customer_id")
    return {"title": b["title"], "acc": b["accent"], "cur": cfg["currency"], "today": today.isoformat(),
            "since": cfg["history_since"], "stamp": now.strftime("%a %d %b %Y, %H:%M"), "iso": now.isoformat(),
            "acctLine": acct_line, "acctWarn": acct_warn, "acctOk": "Active</b>" in acct_line,
            "gerr": bool(gerr and gcid), "acctName": cfg["ad_account_name"],
            "gcid": "%s-%s-%s" % (gcid[:3], gcid[3:6], gcid[6:]) if gcid else "none",
            "detErr": bool(det.get("error")), "camps": cl, "cd": cd, "as": al, "ad": ad, "rc": rc, "bd": bd,
            "labels": {SHORT[t]: l for t, l in md.FUNNEL}}


def ad_previews(ads, det, camp_ids):
    """Ad previews tab: each ad in this brand's Meta campaigns (picture, text, CTA, status,
    Meta preview link) plus its spend and actions by day, so the page sums the picked range."""
    av = []
    for a in ads:
        if a.get("campaign_id") not in camp_ids:
            continue
        cr = a.get("creative") or {}
        oss = cr.get("object_story_spec") or {}
        ld, vd = oss.get("link_data") or {}, oss.get("video_data") or {}
        afs = cr.get("asset_feed_spec") or {}
        first = lambda k: ((afs.get(k) or [{}])[0] or {}).get("text", "")
        cta = (cr.get("call_to_action_type") or (ld.get("call_to_action") or {}).get("type")
               or (vd.get("call_to_action") or {}).get("type") or "")
        video = bool(cr.get("video_id") or vd or afs.get("videos"))
        av.append({"id": a["id"], "c": a["campaign_id"], "s": a.get("adset_id", ""), "n": a.get("name", ""),
                   "on": a.get("effective_status") == "ACTIVE",
                   "st": (a.get("effective_status") or "").replace("_", " ").lower(),
                   "t": cr.get("title") or ld.get("name") or vd.get("title") or first("titles"),
                   "b": cr.get("body") or ld.get("message") or vd.get("message") or first("bodies"),
                   "cta": cta.replace("_", " ").capitalize(), "v": video,
                   "img": cr.get("thumbnail_url") or cr.get("image_url") or vd.get("image_url") or "",
                   "lk": a.get("preview_shareable_link", "")})
    keep = {a["id"] for a in av}
    ai = [[r["ad_id"], r["date_start"], round(float(r.get("spend") or 0), 2), int(r.get("impressions") or 0), acts(r)]
          for r in det.get("ad_ins", []) if r.get("ad_id") in keep and float(r.get("spend") or 0) > 0]
    return {"av": av, "ai": ai, "adErr": bool(det.get("adErr"))}


CSS_EXTRA = """
.rangebar{position:sticky;top:0;z-index:5;background:#0f1115ee;backdrop-filter:blur(6px);border:1px solid #262a33;
border-radius:12px;padding:12px 14px;margin:0 0 22px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.rangebar .lab{color:#9aa0aa;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-right:4px}
.rangebar button{background:#171a21;color:#e8eaed;border:1px solid #2f3440;border-radius:99px;padding:6px 12px;
font:inherit;font-size:13px;cursor:pointer}.rangebar button.sel{background:var(--acc);color:#0f1115;border-color:var(--acc);font-weight:600}
.rangebar input{background:#171a21;color:#e8eaed;border:1px solid #2f3440;border-radius:8px;padding:5px 8px;font:inherit;font-size:13px;color-scheme:dark}
.rangebar .custom{display:flex;gap:6px;align-items:center;margin-left:auto;color:#9aa0aa;font-size:13px}
.vtabs{display:flex;gap:6px;margin-top:16px}.vtab{background:#12151b;color:#c3c8d0;border:1px solid #2f3440;border-radius:99px;
padding:7px 14px;font:inherit;font-size:13px;cursor:pointer}.vtab.sel{background:var(--acc);border-color:var(--acc);color:#0f1115;font-weight:600}
.adgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin-top:14px}
.adc{background:#12151b;border:1px solid #262a33;border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.adc.live{border-color:var(--acc)}.adimg{position:relative;aspect-ratio:4/5;background:#000}
.adimg img{width:100%;height:100%;object-fit:contain;display:block}.adimg .ni{display:flex;height:100%;align-items:center;justify-content:center;color:#7d838d;font-size:12px}
.adimg .vb{position:absolute;top:8px;left:8px;background:#000c;color:#fff;font-size:10px;font-weight:700;letter-spacing:.06em;padding:3px 7px;border-radius:4px}
.adtx{padding:10px 12px 12px;display:flex;flex-direction:column;gap:5px;font-size:12.5px;flex:1}
.adtx .an{color:#9aa0aa;font-size:11px;word-break:break-word}.adtx .ah{font-weight:600;font-size:13.5px}
.adtx .ab{color:#c3c8d0;line-height:1.45}.adtx details summary{cursor:pointer;color:var(--acc);font-size:11.5px}
.adtx details p{color:#9aa0aa;margin:6px 0 0;line-height:1.5;white-space:pre-line}.adtx .cta{color:#9aa0aa;font-size:11.5px}
.adnum{display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;margin-top:auto;padding-top:8px;border-top:1px solid #262a33;font-size:12px}
.adnum span{color:#9aa0aa}.adnum b{font-variant-numeric:tabular-nums}.adnum b.r{color:var(--acc)}
.adtx a{color:var(--acc);font-weight:600;text-decoration:none;font-size:12.5px;margin-top:4px}
.offads{margin-top:16px;color:#9aa0aa;font-size:13px}.offads>summary{cursor:pointer}
.rangenow{color:#9aa0aa;font-size:13px;margin:-12px 0 18px}.rangenow b{color:#e8eaed}
.glance{color:#9aa0aa;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px}
.empty{color:#9aa0aa;font-size:14px;padding:8px 0}
.selbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:34px 0 14px}.selbar h2.sect{margin:0}
.selbar select{background:#171a21;color:#e8eaed;border:1px solid var(--acc);border-radius:8px;padding:8px 12px;font:inherit;
font-size:14px;max-width:100%;min-width:280px;color-scheme:dark}.selcount{color:#9aa0aa;font-size:13px}
.camp.one>.chead{padding:18px 22px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center;
border-bottom:1px solid #262a33}.camp.one>.chead .ct{font-weight:600;font-size:16px}.camp.one>.chead .cm{color:#9aa0aa;font-size:13px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;margin-bottom:4px}.tabs .tab{background:#12151b;color:#c3c8d0;
border:1px solid #2f3440;border-radius:8px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
.tabs .tab.sel{border-color:var(--acc);color:var(--acc);font-weight:600}.bdpane .dt{margin-top:6px}
.camp.one>*:not(.chead){margin-left:22px;margin-right:22px}
@media(max-width:860px){.kpi .v{font-size:18px}.kpi{padding:12px 12px}.selbar select{min-width:0;width:100%}
.rangebar .custom{margin-left:0}.rangebar input{width:118px}.grid2>.card{min-width:0}.wrap{padding-left:16px;padding-right:16px}.camp.one>*:not(.chead){margin-left:14px;margin-right:14px}
.camp.one>.chead{padding:14px}.camp p.sm{margin:0 14px 4px}.camp h4,.camp h4.big{margin-left:14px;margin-right:14px}}tr.pick{cursor:pointer}tr.pick:hover td{background:#1d2129}

.bud td.nt{color:#9aa0aa;font-size:12px;white-space:normal;text-align:left;padding-top:0;border-bottom:1px solid #262a33}
.bud tr.top td{border-bottom:0}.bud .bar{display:inline-block;width:70px;height:7px;background:#2a2e38;border-radius:9px;
vertical-align:middle;margin-right:6px;overflow:hidden}.bud .bar i{display:block;height:100%;background:var(--acc)}
.bud .over{color:#ff9b9b;font-weight:600}.bud .cm{color:#9aa0aa;font-size:12px}.bud .bn{font-weight:600}.budnote{color:#9aa0aa;font-size:12px;margin:10px 0 0}
.bud details{margin-top:12px;color:#9aa0aa;font-size:13px}.bud summary{cursor:pointer}
@media(max-width:860px){.bud table,.bud tbody,.bud tr,.bud td{display:block;width:100%}.bud thead{display:none}
.bud tr.top{border-top:1px solid #262a33;padding-top:10px}.bud tr.top td{text-align:right;padding:4px 0;border:0}
.bud tr.top td:first-child{text-align:left;padding-bottom:8px}.bud tr.top td[data-l]::before{content:attr(data-l);float:left;
color:#9aa0aa;font-size:12px;text-transform:uppercase;letter-spacing:.06em}.bud td.nt{padding:6px 0 12px;border:0}.bud tr.top td{white-space:normal}}
"""

JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const L = D.labels; L.conv = 'Conversions';
const ORDER = ['lc','lpv','reg','ic','pur','lead','chat'];
const BDS = ['Platform','Placement','Country','Age and gender','Device'];
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v == null ? '-' : D.cur + ' ' + v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const money0 = v => D.cur + ' ' + v.toLocaleString('en-US',{maximumFractionDigits:0});
const num = v => Math.round(v).toLocaleString('en-US');
const pct = (a,b) => b ? (a/b*100).toFixed(1)+'%' : '-';
const P = s => new Date(s+'T00:00:00Z');
const F = d => d.toISOString().slice(0,10);
const add = (s,n) => { const d = P(s); d.setUTCDate(d.getUTCDate()+n); return F(d); };
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DOW = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const dshort = s => { const d=P(s); return d.getUTCDate()+' '+MON[d.getUTCMonth()]; };
const dlong = s => { const d=P(s); return DOW[d.getUTCDay()]+' '+d.getUTCDate()+' '+MON[d.getUTCMonth()]+' '+d.getUTCFullYear(); };
const T = D.today;

function presets(){
  const first = T.slice(0,8)+'01', lme = add(first,-1);
  return {today:[T,T,'Today'], yesterday:[add(T,-1),add(T,-1),'Yesterday'], last7:[add(T,-6),T,'Last 7 days'],
          last30:[add(T,-29),T,'Last 30 days'], month:[first,T,'This month'], lastmonth:[lme.slice(0,8)+'01',lme,'Last month'],
          all:[D.since,T,'All time']};
}
const PR = presets();
let R = {key:'all', from:D.since, to:T};
let SEL = null, BD = 'Platform', VIEW = 'num';
const inR = s => s >= R.from && s <= R.to;

function readHash(){
  const parts = decodeURIComponent(location.hash.slice(1)).split('&');
  const cp = parts.find(p => p.startsWith('c=')); if (cp) SEL = cp.slice(2);
  if (parts.includes('v=ads')) VIEW = 'ads';
  const h = parts.find(p => p.startsWith('r=')) || '';
  const m = h.match(/^r=(\w+)$/), c = h.match(/^r=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)$/);
  if (c && c[1] <= c[2]) { R = {key:'custom', from:c[1] < D.since ? D.since : c[1], to:c[2] > T ? T : c[2]}; return; }
  if (m && PR[m[1]]) R = {key:m[1], from:PR[m[1]][0], to:PR[m[1]][1]};
}
function setRange(key, from, to){
  if (key !== 'custom') { from = PR[key][0]; to = PR[key][1]; }
  for (const k in PR) if (PR[k][0] === from && PR[k][1] === to) key = k;   // a custom pick equal to a quick range gets its reach
  R = {key, from, to};
  draw();
}

// ---------- sums
function campTot(c){
  const t = {sp:0, im:0, cl:0, a:{}, days:new Set()};
  for (const r of (D.cd[c.id]||[])) { if (!inR(r[0])) continue;
    t.sp += r[1]; t.im += r[2]; t.cl += r[3]; if (r[1] > 0) t.days.add(r[0]);
    for (const k in r[4]) t.a[k] = (t.a[k]||0) + r[4][k]; }
  t.res = c.rt === 'lc' ? t.cl : (t.a[c.rt]||0);
  return t;
}
function sumWin(from, to){
  let s = 0;
  for (const c of D.camps) for (const r of (D.cd[c.id]||[])) if (r[0] >= from && r[0] <= to) s += r[1];
  return s;
}

// ---------- approved budgets (register kept outside the public repo; not affected by the date range)
function budSpent(b){
  let s = 0;
  for (const id of (b.campaigns||[])) for (const r of (D.cd[id]||[])) s += r[1];
  return s;
}
function budStatus(b){
  const run = D.camps.some(c => (b.campaigns||[]).includes(c.id) && c.run);
  if (run) return ['Live', true];
  if (b.end && T > b.end) return ['Ended', false];
  if (b.start && T < b.start) return ['Not started', false];
  return ['Paused', false];
}
function budgets(){
  if (D.budgets == null) return `<p class="empty">The approved budget register could not be read this hour. It comes back on the next update.</p>`;
  if (!D.budgets.length) return `<p class="empty">No approved budget on record yet.</p>`;
  const rows = D.budgets.map(b => {
    const sp = budSpent(b), ap = +b.approved || 0, rel = b.released == null ? null : +b.released;
    const lim = rel != null ? rel : ap, used = ap ? sp/ap*100 : 0;
    const [st, on] = budStatus(b);
    const over = rel != null && sp > rel + 0.005;
    const note = [b.released_note, b.note].filter(Boolean).map(esc).join(' ');
    return `<tr class="top"><td><span class="tag ${on?'on':'pz'}">${st}</span><span class="bn">${esc(b.name)}</span></td><td data-l="Channel">${esc(b.channel||'')}</td>`
      + `<td data-l="Approved">${money0(ap)}</td><td data-l="Approved on">${b.approved_on?dlong(b.approved_on):'-'}${b.approved_by?'<br><span class="cm">by '+esc(b.approved_by)+'</span>':''}</td>`
      + `<td data-l="Period">${b.start?dshort(b.start):'-'} to ${b.end?dshort(b.end)+' '+b.end.slice(0,4):'-'}</td>`
      + `<td data-l="Released so far">${rel != null ? money0(rel) : '-'}</td><td data-l="Spent"${over?' class="over"':''}>${money(sp)}<br><span class="cm"><span class="bar"><i style="width:${Math.min(100,used).toFixed(1)}%"></i></span>${Math.round(used)}%${rel != null && rel < ap ? ' of approved spent, '+money0(ap - rel)+' not yet released' : ' used'}</span></td>`
      + `<td data-l="Left to spend now">${st === 'Ended' ? 'None (ended)' : money(Math.max(0, lim - sp)) + (st === 'Paused' ? ' (paused)' : '')}</td></tr>`
      + `<tr><td class="nt" colspan="8">${over?'<span class="over">Spend is above the released limit. </span>':''}${note}</td></tr>`;
  }).join('');
  const covered = new Set(D.budgets.flatMap(b => b.campaigns||[]));
  const loose = D.camps.filter(c => !covered.has(c.id) && (D.cd[c.id]||[]).some(r => r[1] > 0));
  const looseHtml = loose.length ? `<details><summary>${loose.length} campaign${loose.length>1?'s':''} with spend have no approved budget on record (older flights). Tell the marketing team the approved amount to add it.</summary><p>${loose.map(c => esc(c.n)+' ('+money(budSpent({campaigns:[c.id]}))+')').join('<br>')}</p></details>` : '';
  return `<table><thead><tr><th>Approved budget</th><th>Channel</th><th>Approved</th><th>Approved on</th><th>Period</th><th>Released so far</th><th>Spent</th><th>Left to spend now</th></tr></thead><tbody>${rows}</tbody></table>`
    + `<p class="budnote">Spent = all spend on the campaigns linked to that budget, from the same data as the rest of this page. Released so far = the part of the approved amount that is open to spend now (tranches). The approved amounts come from management approvals. The ad platforms do not hold them. Unspent money on ended or paused budgets is not available unless management re-approves it.</p>${looseHtml}`;
}

// ---------- blocks
function glance(){
  const first = T.slice(0,8)+'01';
  const k = [['Today so far', sumWin(T,T), 'updates every hour', true],
             ['Yesterday', sumWin(add(T,-1),add(T,-1)), dlong(add(T,-1)).slice(0,-5), false],
             ['Last 7 days', sumWin(add(T,-6),T), 'including today', false],
             ['This month', sumWin(first,T), MON[P(T).getUTCMonth()]+' '+T.slice(0,4), false],
             ['All time', sumWin(D.since,T), 'since '+dshort(D.since)+' '+D.since.slice(0,4), false]];
  return k.map(([l,v,s,hi]) => `<div class="kpi${hi?' hi':''}"><div class="l">${l}</div><div class="v">${money(v)}</div><div class="s">${s}</div></div>`).join('');
}

function byChannel(tots){
  const rows = ['Meta','Google'].map(ch => {
    const cs = D.camps.filter(c => c.ch === ch);
    const t = {sp:0, im:0, cl:0}; cs.forEach(c => { const x = tots[c.id]; t.sp += x.sp; t.im += x.im; t.cl += x.cl; });
    return [ch, cs.filter(c => c.run).length, t]; });
  const all = rows.reduce((a,[,n,t]) => ({n:a.n+n, sp:a.sp+t.sp, im:a.im+t.im, cl:a.cl+t.cl}), {n:0,sp:0,im:0,cl:0});
  const tr = (n,live,t,cls) => `<tr${cls?' class="sum"':''}><td>${n}</td><td>${live}</td><td>${money(t.sp)}</td><td>${all.sp?Math.round(t.sp/all.sp*100):0}%</td><td>${num(t.im)}</td><td>${num(t.cl)}</td><td>${t.cl?money(t.sp/t.cl):'-'}</td></tr>`;
  return `<table><thead><tr><th>Channel</th><th>Live campaigns</th><th>Spend</th><th>Share</th><th>Impressions</th><th>Clicks</th><th>Cost per click</th></tr></thead><tbody>${rows.map(([n,l,t]) => tr(n,l,t)).join('')}${tr('Total',all.n,all,1)}</tbody></table>`;
}

function chart(){
  const daily = {};
  for (const c of D.camps) for (const r of (D.cd[c.id]||[])) if (inR(r[0])) daily[r[0]] = (daily[r[0]]||0) + r[1];
  const days = []; for (let s = R.from; s <= R.to; s = add(s,1)) days.push(s);
  const vals = days.map(d => daily[d]||0), top = Math.max(...vals, 0) || 1;
  const W = 740, H = 220, pad = 28, bw = (W-pad-20)/days.length, step = Math.max(1, Math.ceil(days.length/7));
  let o = `<svg viewBox="0 0 ${W} ${H+24}" width="100%" role="img" aria-label="Daily spend">`;
  for (const f of [.5,1]) { const y = H-(H-16)*f; o += `<line x1="${pad}" x2="${W}" y1="${y}" y2="${y}" stroke="#262a33"/><text x="0" y="${y+4}">${Math.round(top*f).toLocaleString('en-US')}</text>`; }
  days.forEach((d,i) => { const v = vals[i], h = (H-16)*v/top, x = pad+i*bw+(bw>4?1:0), w = Math.max(bw-(bw>4?2:0.3),0.5);
    const col = d === T ? 'var(--acc)' : v ? '#5d6573' : '#262a33';
    o += `<rect x="${x.toFixed(1)}" y="${(H-Math.max(h,1)).toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(h,1).toFixed(1)}" rx="1" fill="${col}"><title>${dlong(d)}: ${money(v)}${d===T?' (today so far)':''}</title></rect>`;
    if ((days.length-1-i) % step === 0) o += `<text x="${(x+w/2).toFixed(1)}" y="${H+18}" text-anchor="middle">${dshort(d)}</text>`; });
  return o + '</svg>';
}

function months(){
  const m = {};
  for (const c of D.camps) for (const r of (D.cd[c.id]||[])) if (inR(r[0])) m[r[0].slice(0,7)] = (m[r[0].slice(0,7)]||0) + r[1];
  const ks = Object.keys(m).filter(k => m[k] > 0).sort().reverse();
  return ks.length ? ks.map(k => `<tr><td>${MON[+k.slice(5,7)-1]} ${k.slice(0,4)}</td><td>${money(m[k])}</td></tr>`).join('') : `<tr><td colspan="2">No spend in this range.</td></tr>`;
}

function campTable(tots){
  const list = D.camps.filter(c => c.run || tots[c.id].sp > 0)
    .sort((a,b) => (b.run-a.run) || (tots[b.id].sp - tots[a.id].sp));
  if (!list.length) return `<tbody><tr><td colspan="10">No campaigns with spend in this range.</td></tr></tbody>`;
  const tag = c => c.run ? '<span class="tag on">LIVE</span>' : '<span class="tag pz">OFF</span>';
  const body = list.map(c => { const t = tots[c.id];
    return `<tr class="${c.run?'':'off'}${c.ch==='Meta'?' pick':''}"${c.ch==='Meta'?` data-id="${c.id}" title="Show this campaign's detail"`:''}><td>${tag(c)}${esc(c.n)}</td><td>${c.ch}</td><td>${c.run && c.bud ? money(c.bud) : '-'}</td><td>${money(t.sp)}</td><td>${num(t.im)}</td><td>${num(t.cl)}</td><td>${t.im?(t.cl/t.im*100).toFixed(2)+'%':'-'}</td><td>${t.cl?money(t.sp/t.cl):'-'}</td><td>${c.rl ? num(t.res)+' '+c.rl : '-'}</td><td>${t.res?money(t.sp/t.res):'-'}</td></tr>`; }).join('');
  const s = list.reduce((a,c) => ({sp:a.sp+tots[c.id].sp, im:a.im+tots[c.id].im, cl:a.cl+tots[c.id].cl}), {sp:0,im:0,cl:0});
  return `<tbody>${body}</tbody><tfoot><tr><td>Total</td><td></td><td></td><td>${money(s.sp)}</td><td>${num(s.im)}</td><td>${num(s.cl)}</td><td>${s.im?(s.cl/s.im*100).toFixed(2)+'%':'-'}</td><td>${s.cl?money(s.sp/s.cl):'-'}</td><td></td><td></td></tr></tfoot>`;
}

function bdTable(title, cid, cols, rt){
  const agg = {};
  for (const r of D.bd[title]) { if (r[0] !== cid || !inR(r[1])) continue;
    const a = agg[r[2]] || (agg[r[2]] = {lab:r[2], sp:0, a:{}}); a.sp += r[3];
    for (const k in r[4]) a.a[k] = (a.a[k]||0) + r[4][k]; }
  const rows = Object.values(agg).filter(x => x.sp > 0);
  if (!rows.length) return '';
  rows.sort((x,y) => ((y.a[rt]||0) - (x.a[rt]||0)) || (y.sp - x.sp));
  const tsp = rows.reduce((s,x) => s + x.sp, 0) || 1;
  const cell = (k,v) => `<td${k===rt?" class='res'":''}>${num(v||0)}</td>`;
  const body = rows.map(x => `<tr><td>${esc(x.lab)}</td><td>${money(x.sp)}</td><td>${Math.round(x.sp/tsp*100)}%</td>${cols.map(k => cell(k,x.a[k])).join('')}</tr>`).join('');
  const tot = `<tr class='sum'><td>Total</td><td>${money(rows.reduce((s,x)=>s+x.sp,0))}</td><td>100%</td>${cols.map(k => cell(k, rows.reduce((s,x)=>s+(x.a[k]||0),0))).join('')}</tr>`;
  return `<div class='scroll bdpane' data-t='${title}'><table class='dt'><thead><tr><th>${title}</th><th>Spend</th><th>Share of spend</th>${cols.map(k=>`<th>${L[k]}</th>`).join('')}</tr></thead><tbody>${body}${tot}</tbody></table></div>`;
}

function adCard(x, rt, rl){
  const r = rt ? (x.a[rt]||0) : 0, lc = x.a.lc||0;
  const ok = D.acctOk;
  const pill = x.on && !ok ? '<span class="tag warn">Set to Active, no delivery</span>' : x.on ? '<span class="tag on">LIVE</span>' : `<span class="tag pz">${esc(x.st||'off').toUpperCase()}</span>`;
  const body = x.b || '', line1 = body.split('\n')[0], short = line1.length > 150 ? line1.slice(0,150).replace(/\s+\S*$/,'') + '…' : line1;
  const more = body.length > line1.length || line1.length > 150 ? `<details><summary>Full text</summary><p>${esc(body)}</p></details>` : '';
  const img = x.img ? `<img src="${esc(x.img)}" loading="lazy" alt="" referrerpolicy="no-referrer">` : '<div class="ni">No picture</div>';
  return `<div class="adc${x.on?' live':''}"><div class="adimg">${img}${x.v?'<span class="vb">VIDEO</span>':''}</div><div class="adtx">`
    + `<div>${pill}</div><div class="an">${esc(x.n)}</div>${x.t?`<div class="ah">${esc(x.t)}</div>`:''}<div class="ab">${esc(short)}</div>${more}`
    + `${x.cta?`<div class="cta">Button: ${esc(x.cta)}</div>`:''}`
    + `<div class="adnum"><span>Spend</span><b>${money(x.sp)}</b><span>Link clicks</span><b>${num(lc)}${x.im?' · '+(lc/x.im*100).toFixed(2)+'%':''}</b>`
    + `<span class="r">${esc(rl)}</span><b class="r">${rt?num(r):'-'}</b><span>Cost per ${esc(rt?rl.toLowerCase().replace(/s$/,''):'result')}</span><b>${r?money(x.sp/r):'-'}</b></div>`
    + `${x.lk?`<a href="${esc(x.lk)}" target="_blank" rel="noopener">Open Meta preview &rarr;</a>`:''}</div></div>`;
}
function previews(c){
  const rows = D.av.filter(a => a.c === c.id).map(a => ({...a, on: a.on && c.run, st: a.on && !c.run ? 'campaign ended' : a.st, sp:0, im:0, a:{}}));
  const idx = Object.fromEntries(rows.map(x => [x.id, x]));
  for (const r of D.ai) { const x = idx[r[0]]; if (!x || !inR(r[1])) continue;
    x.sp += r[2]; x.im += r[3]; for (const k in r[4]) x.a[k] = (x.a[k]||0) + r[4][k]; }
  const rt = c.rt, rl = rt ? L[rt] : 'Results';
  const show = rows.filter(x => x.on || x.sp > 0).sort((p,q) => (q.on-p.on) || (q.sp-p.sp));
  const live = show.filter(x => x.on), off = show.filter(x => !x.on);
  const err = D.adErr ? `<p class='sm'>Per-ad numbers could not be read this hour. They come back on the next update.</p>` : '';
  if (!show.length) return err + `<p class="empty">No ads with spend in this date range.</p>`;
  const head = `<p class='sm' style='margin-top:12px'>${live.length} live ad${live.length===1?'':'s'}${off.length?', '+off.length+' off with spend in this range':''}. Numbers follow the date range. Results are ${esc(rl.toLowerCase())}, Meta-counted. "Open Meta preview" shows the ad as people see it on Facebook and Instagram.</p>`;
  const grid = list => `<div class="adgrid">${list.map(x => adCard(x, rt, rl)).join('')}</div>`;
  return err + head + (live.length ? grid(live) : '')
    + (off.length ? `<details class="offads"${live.length?'':' open'}><summary>${off.length} ad${off.length===1?'':'s'} now off (had spend in this range)</summary>${grid(off)}</details>` : '');
}

function section(c){
  const sets = D.as.filter(a => a.c === c.id);
  const rows = sets.map(a => ({...a, sp:0, im:0, a:{}, days:[]}));
  const idx = Object.fromEntries(rows.map(x => [x.id, x]));
  const days = {};
  for (const r of D.ad) { const x = idx[r[0]]; if (!x || !inR(r[1])) continue;
    x.sp += r[2]; x.im += r[3]; x.days.push(r[1]); for (const k in r[4]) x.a[k] = (x.a[k]||0) + r[4][k];
    (days[r[1]] || (days[r[1]] = {}))[r[0]] = r[2]; }
  const live = rows.filter(x => x.sp > 0).sort((p,q) => q.sp - p.sp);
  if (!live.length) return '';
  const rt = c.rt, rl = rt ? L[rt] : 'Results';
  const tot = {sp:0, im:0}; ORDER.forEach(k => tot[k] = 0);
  live.forEach(x => { tot.sp += x.sp; tot.im += x.im; ORDER.forEach(k => tot[k] += x.a[k]||0); });
  const cols = ORDER.filter(k => tot[k] > 0 || k === 'lc' || k === rt);
  const res = rt ? tot[rt] : 0, maxsp = Math.max(...live.map(x => x.sp)) || 1;
  const allDays = Object.keys(days).sort(), first = allDays[0], last = allDays[allDays.length-1];
  const ok = D.acctOk;
  const pill = on => on && !ok ? '<span class="tag warn">Set to Active, no delivery</span>' : on ? '<span class="tag on">LIVE</span>' : '<span class="tag pz">OFF</span>';
  const reachSet = R.key !== 'custom' ? (D.rc[R.key] || {}) : null;

  let k = `<div class="mk"><div class="l">Spend</div><div class="v">${money(tot.sp)}</div><div class="s">spend on ${dshort(first)} to ${dshort(last)}</div></div>`
        + `<div class="mk"><div class="l">Link clicks</div><div class="v">${num(tot.lc)}</div><div class="s">${num(tot.im)} impressions</div></div>`;
  for (const t of cols) { if (t === 'lc') continue;
    const sub = t === rt && tot[t] ? money(tot.sp/tot[t]) + ' each, Meta-counted' : pct(tot[t], tot.lc) + ' of link clicks';
    k += `<div class="mk${t===rt?' hi':''}"><div class="l">${L[t]}</div><div class="v">${num(tot[t])}</div><div class="s">${sub}</div></div>`; }

  const ab = live.map(x => { const rc = reachSet && reachSet[x.id];
    const reach = rc ? num(rc[0]) : '-', freq = rc && rc[0] ? (rc[1]/rc[0]).toFixed(2) : '-';
    const lc = x.a.lc||0, r = rt ? (x.a[rt]||0) : 0;
    return `<tr><td><b>${esc(x.n)}</b><div class='sm'>${pill(x.on)} ${esc(x.bud)} · ${dshort(x.days.sort()[0])} to ${dshort(x.days[x.days.length-1])} (${x.days.length} days with spend)</div></td>`
      + `<td>${money(x.sp)}<div class='bar'><i style='width:${Math.round(x.sp/maxsp*100)}%'></i></div></td><td>${num(x.im)}</td><td>${reach}</td><td>${freq}</td>`
      + `<td>${num(lc)}</td><td>${x.im?(lc/x.im*100).toFixed(2)+'%':'-'}</td><td>${lc?money(x.sp/lc):'-'}</td>${tot.lpv>0?`<td>${num(x.a.lpv||0)}</td>`:''}`
      + `<td class='res'>${rt?num(r):'-'}</td><td class='res'>${r?money(x.sp/r):'-'}</td></tr>`; }).join('');
  const reachNote = reachSet ? '' : `<p class='sm'>Reach and frequency show for the quick ranges only (Today, Yesterday, Last 7 days, Last 30 days, This month, Last month, All time). Meta cannot add reach up day by day, because one person can see an ad on many days.</p>`;
  const adtable = `<div class='scroll'><table class='dt'><thead><tr><th>Ad set</th><th>Spend</th><th>Impressions</th><th>Reach</th><th>Frequency</th><th>Link clicks</th><th>CTR</th><th>Cost per click</th>${tot.lpv>0?'<th>Page views</th>':''}<th>${rt==='lpv'?'Result (page views)':rl}</th><th>Cost per result</th></tr></thead><tbody>${ab}</tbody></table></div>${reachNote}`;

  const extra = [];
  if (tot.ic > 0) extra.push(['Click to checkout','ic']);
  if (rt && rt !== 'lc' && rt !== 'ic') extra.push(['Click to '+rl.toLowerCase().replace(/s$/,''), rt]);
  const funnel = `<h4>Funnel by ad set</h4><div class='scroll'><table class='dt'><thead><tr><th>Ad set</th>${cols.map(k=>`<th>${L[k]}</th>`).join('')}${extra.map(([a])=>`<th>${a}</th>`).join('')}</tr></thead><tbody>`
    + live.map(x => `<tr><td>${esc(x.n)}</td>${cols.map(k => `<td${k===rt?" class='res'":''}>${num(x.a[k]||0)}</td>`).join('')}${extra.map(([,t]) => `<td>${pct(x.a[t]||0, x.a.lc||0)}</td>`).join('')}</tr>`).join('') + `</tbody></table></div>`;

  const daily = `<h4>Spend by day</h4><div class='scroll daybox'><table class='dt'><thead><tr><th>Day</th>${live.map(x=>`<th>${esc(x.s)}</th>`).join('')}<th>Total</th></tr></thead><tbody>`
    + allDays.slice().reverse().map(d => `<tr><td>${dlong(d)}</td>${live.map(x => `<td>${days[d][x.id] != null ? money(days[d][x.id]) : '-'}</td>`).join('')}<td><b>${money(Object.values(days[d]).reduce((s,v)=>s+v,0))}</b></td></tr>`).join('') + `</tbody></table></div>`;

  const bdCols = cols.filter(k => k !== 'lpv' || rt === 'lpv');
  const panes = BDS.map(t => [t, bdTable(t, c.id, bdCols, rt)]).filter(([,h]) => h);
  if (!panes.some(([t]) => t === BD)) BD = panes.length ? panes[0][0] : BD;
  const bdh = panes.length ? `<div class='tabs'>${panes.map(([t]) => `<button class='tab${t===BD?' sel':''}' data-t='${t}'>${t}</button>`).join('')}</div>`
    + panes.map(([t,h]) => h.replace(`data-t='${t}'`, `data-t='${t}'${t===BD?'':' hidden'}`)).join('') : '';
  const retarget = live.some(x => /retarget/i.test(x.n));
  const where = bdh ? `<h4 class='big'>Where the results came from</h4><p class='sm'>All ad sets in this campaign together. Rows with the most ${rl.toLowerCase()} come first. `
    + (retarget ? "Country spend includes the retargeting ad set's spend, so it can differ from the ad set table. " : '')
    + (tot.pur || tot.ic ? 'Meta gives each event to the row it was delivered on, so a row can show more purchases than checkouts.' : 'Meta gives each event to the row it was delivered on, so a row can differ slightly from the ad set table.')
    + ` Small counts are early signs only. Meta can give a breakdown total a few ringgit different from the campaign total.</p>${bdh}` : '';

  const meta = rt ? `Spend ${money(tot.sp)} · ${num(res)} ${rl.toLowerCase()} · ${res?money(tot.sp/res):'-'} per ${rl.toLowerCase().replace(/s$/,'')}` : `Spend ${money(tot.sp)}`;
  const headOn = c.run || (!ok && live.some(x => x.on));
  const bb = (D.budgets||[]).find(b => (b.campaigns||[]).includes(c.id));
  const bline = bb ? `<p class='sm'>Approved budget: <b>${money0(+bb.approved||0)}</b> for ${esc(bb.name)}${bb.released!=null?', released so far '+money0(+bb.released):''}. See Approved budgets at the top.</p>` : `<p class='sm'>No approved budget on record for this campaign.</p>`;
  const nAds = c.run ? D.av.filter(a => a.c === c.id && a.on).length : 0;
  const vt = `<div class='vtabs'><button class='vtab${VIEW==='num'?' sel':''}' data-v='num'>Numbers</button><button class='vtab${VIEW==='ads'?' sel':''}' data-v='ads'>Ad previews${nAds?' ('+nAds+' live)':''}</button></div>`;
  return `<div class='card camp one'><div class='chead'><span class='ct'>${pill(headOn)}${esc(c.n)}</span><span class='cm'>${meta}</span></div>${bline}${vt}`
    + `<div class='vpane' data-v='num'${VIEW==='num'?'':' hidden'}><div class='mks'>${k}</div>${adtable}${funnel}${daily}${where}</div>`
    + `<div class='vpane' data-v='ads'${VIEW==='ads'?'':' hidden'}>${VIEW==='ads'?previews(c):''}</div></div>`;
}

function draw(){
  document.querySelectorAll('.rangebar button').forEach(b => b.classList.toggle('sel', b.dataset.k === R.key));
  document.getElementById('from').value = R.from; document.getElementById('to').value = R.to;
  const n = Math.round((P(R.to)-P(R.from))/864e5)+1;
  document.getElementById('rangenow').innerHTML = `Showing <b>${dlong(R.from)}</b> to <b>${dlong(R.to)}</b> (${n} day${n>1?'s':''})${R.to===T?', today is not final':''}`;
  const tots = Object.fromEntries(D.camps.map(c => [c.id, campTot(c)]));
  document.getElementById('bych').innerHTML = byChannel(tots);
  document.getElementById('chart').innerHTML = chart();
  document.getElementById('months').innerHTML = months();
  document.getElementById('camps').innerHTML = campTable(tots);
  const adsp = {};
  for (const r of D.ad) if (inR(r[1])) adsp[r[0]] = (adsp[r[0]]||0) + r[2];
  const metaCamps = D.camps.filter(c => c.ch === 'Meta' && D.as.some(a => a.c === c.id && adsp[a.id] > 0))
    .sort((a,b) => (b.run-a.run) || (tots[b.id].sp - tots[a.id].sp));
  const sel = document.getElementById('campsel');
  if (!metaCamps.some(c => c.id === SEL)) SEL = metaCamps.length ? metaCamps[0].id : null;
  sel.innerHTML = metaCamps.map(c => `<option value="${c.id}"${c.id===SEL?' selected':''}>${c.run?'LIVE · ':''}${esc(c.n)} · ${money(tots[c.id].sp)}</option>`).join('');
  sel.disabled = !metaCamps.length;
  document.getElementById('selcount').textContent = metaCamps.length ? metaCamps.length + ' Meta campaign' + (metaCamps.length>1?'s':'') + ' with spend in this range' : '';
  const c = metaCamps.find(c => c.id === SEL);
  document.getElementById('detail').innerHTML = c ? section(c) : `<p class="empty">No Meta spend in this range.</p>`;
  document.querySelectorAll('.tabs .tab').forEach(b => b.addEventListener('click', () => {
    BD = b.dataset.t;
    document.querySelectorAll('.tabs .tab').forEach(x => x.classList.toggle('sel', x === b));
    document.querySelectorAll('.bdpane').forEach(p => p.hidden = p.dataset.t !== BD); }));
  document.querySelectorAll('.vtab').forEach(b => b.addEventListener('click', () => {
    VIEW = b.dataset.v; draw(); }));
  document.querySelectorAll('#camps-t tr[data-id]').forEach(tr => tr.addEventListener('click', () => {
    if (!metaCamps.some(c => c.id === tr.dataset.id)) return;
    SEL = tr.dataset.id; draw(); document.getElementById('detailtop').scrollIntoView({behavior:'smooth'}); }));
  history.replaceState(null,'','#r='+(R.key==='custom' ? R.from+'..'+R.to : R.key)+(SEL?'&c='+SEL:'')+(VIEW==='ads'?'&v=ads':''));
}

document.getElementById('glance').innerHTML = glance();
document.getElementById('budgets').innerHTML = budgets();
document.querySelectorAll('.rangebar button').forEach(b => b.addEventListener('click', () => setRange(b.dataset.k)));
document.getElementById('campsel').addEventListener('change', e => { SEL = e.target.value; draw(); });
const fromI = document.getElementById('from'), toI = document.getElementById('to');
[fromI, toI].forEach(i => { i.min = D.since; i.max = T; i.addEventListener('change', () => {
  if (fromI.value && toI.value && fromI.value <= toI.value && fromI.value >= D.since && toI.value <= T) setRange('custom', fromI.value, toI.value); }); });
readHash(); draw();
if (Date.now() - new Date(D.iso).getTime() > 3*3600e3) document.getElementById('stale').style.display = 'block';
"""

NOTES = md.NOTES


def html_page(D, base_css):
    e = html.escape
    data = json.dumps(D, separators=(",", ":")).replace("</", "<\\/")
    gwarn = ('<div class="stale" style="display:block">Google figures could not be read this hour. '
             'The numbers on this page show Meta only until the next update.</div>') if D["gerr"] else ""
    buttons = "".join('<button data-k="%s">%s</button>' % (k, l) for k, l in [
        ("today", "Today"), ("yesterday", "Yesterday"), ("last7", "Last 7 days"), ("last30", "Last 30 days"),
        ("month", "This month"), ("lastmonth", "Last month"), ("all", "All time")])
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>%(title)s ad spend</title><style>:root{--acc:%(acc)s}%(css)s</style></head><body><div class="wrap">
<header><h1><small>Ad spend: Meta + Google</small>%(title)s</h1>
<div class="stamp">Updated <b>%(stamp)s</b> (Malaysia time)<br>%(running)d campaign(s) live now<br>%(mline)s</div></header>
<div class="stale" id="stale">This page has not updated for more than 3 hours. The numbers can be old. See HANDOVER.md, section "If the page stops updating".</div>
%(mwarn)s%(gwarn)s
<p class="glance">At a glance (not affected by the date range)</p><div class="kpis" id="glance"></div>
<div class="card scroll bud"><h2>Approved budgets (not affected by the date range)</h2><div id="budgets"></div></div>
<div class="rangebar"><span class="lab">Date range</span>%(buttons)s
<span class="custom">From <input type="date" id="from"> to <input type="date" id="to"></span></div>
<p class="rangenow" id="rangenow"></p>
<div class="card scroll"><h2>By channel</h2><div id="bych"></div></div>
<div class="grid2"><div class="card"><h2>Daily spend</h2><div id="chart"></div></div>
<div class="card"><h2>Spend by month</h2><table><tbody id="months"></tbody></table></div></div>
<div class="card scroll"><h2>Campaigns</h2><table id="camps-t"><thead><tr><th>Campaign</th><th>Channel</th><th>Daily budget</th>
<th>Spend</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>Cost per click</th><th>Results</th><th>Cost per result</th></tr></thead>
<tbody id="camps-b"></tbody></table></div>
<div class="selbar" id="detailtop"><h2 class="sect">Meta campaign detail</h2><select id="campsel" aria-label="Campaign"></select><span class="selcount" id="selcount"></span></div>
%(derr)s<div id="detail"></div>
%(notes)s
<p class="foot">Sources (read-only): Meta Marketing API, ad account %(acct)s; Google Ads API, account %(gcid)s.
Amounts in %(cur)s, before tax. Today is not final: Meta can add spend for a few hours after midnight, and
Google figures can run about 3 hours behind. Clicks are link clicks for Meta and clicks for Google. Results use
each platform's own count (Meta: purchases, sign-ups, leads, chats or page views; Google: conversions); the CRM
or Stripe stays the true record.</p>
</div><script type="application/json" id="data">%(data)s</script>
<script>%(js)s</script></body></html>""" % {
        "title": e(D["title"]), "acc": D["acc"], "css": base_css + md.CSS + CSS_EXTRA, "stamp": D["stamp"],
        "running": sum(1 for c in D["camps"] if c["run"]), "mline": D["acctLine"], "mwarn": D["acctWarn"],
        "gwarn": gwarn, "buttons": buttons,
        "derr": ('<div class="stale" style="display:block">Meta campaign detail could not be read this hour. '
                 'Spend above is up to date. The detail comes back on the next update.</div>') if D["detErr"] else "", "notes": NOTES, "acct": e(D["acctName"]), "gcid": D["gcid"],
        "cur": D["cur"], "data": data,
        "js": JS.replace("document.getElementById('camps').innerHTML = campTable(tots);",
                         "{const h = campTable(tots); const t = document.getElementById('camps-t'); "
                         "t.querySelectorAll('tbody,tfoot').forEach(x => x.remove()); t.insertAdjacentHTML('beforeend', h);}")}
