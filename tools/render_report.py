#!/usr/bin/env python3
"""Render today's ranked list to reports/latest.html (plus a dated copy)."""
import html, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402  (also sets UTF-8 output)

STAGE_AR = {"text": "النص", "visual": "الصور", "crosscheck": "المطابقة", "inference": "استنتاج",
            "price": "السعر", "archive": "الأرشيف"}
SEV_AR = {"critical": "خطير", "warn": "تنبيه", "info": "معلومة"}
ORIGIN_AR = {"gcc": "خليجي", "us": "وارد أمريكا", "japan": "وارد اليابان", "other": "وارد آخر"}

d = lambda x: f'<bdi dir="ltr">{html.escape(str(x))}</bdi>'
e = lambda x: html.escape("" if x is None else str(x))


def fmt_price(p):
    return "غير مذكور" if p is None else f"{p:,.0f} ر.ع"


def change_badge(it):
    if it["prev_rank"] is None:
        return '<span class="chg new">جديد</span>'
    d = it["prev_rank"] - it["rank"]
    if d > 0:
        return f'<span class="chg up">▲ {d}</span>'
    if d < 0:
        return f'<span class="chg down">▼ {-d}</span>'
    return '<span class="chg same">=</span>'


def price_note(it):
    ph = [p["price_omr"] for p in it["price_history"] if p["price_omr"] is not None]
    if len(ph) >= 2 and ph[-1] != ph[0]:
        diff = ph[-1] - ph[0]
        word = "نزل" if diff < 0 else "ارتفع"
        return f'<span class="pnote {"good" if diff < 0 else "bad"}">{word} {abs(diff):,.0f} منذ أول ظهور</span>'
    return ""


def facts(at):
    bits = []
    for key, label in (("year", None), ("trim", None), ("engine", None)):
        if at.get(key):
            bits.append(e(at[key]))
    if at.get("mileage_km") is not None:
        bits.append(f'{int(at["mileage_km"]):,} كم')
    if at.get("origin"):
        bits.append(e(ORIGIN_AR.get(at["origin"], at["origin"])))
    return " · ".join(bits) or "البيانات ناقصة"


def row(it):
    at = it["attrs"]
    crit = sum(1 for f in it["findings"] if f["severity"] == "critical")
    warn = sum(1 for f in it["findings"] if f["severity"] == "warn")
    flags = []
    if crit:
        flags.append(f'<span class="flag crit">{crit} خطير</span>')
    if warn:
        flags.append(f'<span class="flag warn">{warn} تنبيه</span>')
    findings = "".join(
        f'<li class="{f["severity"]}"><b>{SEV_AR[f["severity"]]} · {STAGE_AR.get(f["stage"], f["stage"])}</b> '
        f'{e(f["evidence"])}{(" <i>(الإعلان يقول: " + e(f["claim"]) + ")</i>") if f.get("claim") else ""}'
        f'{(" <span class=conf>ثقة " + str(round(f["confidence"]*100)) + "%</span>") if f.get("confidence") is not None else ""}</li>'
        for f in sorted(it["findings"], key=lambda f: ["critical", "warn", "info"].index(f["severity"])))
    labels = {"budget": "الميزانية", "condition": "الحالة", "consistency": "التطابق", "value": "قيمة السعر",
              "age_mileage": "العمر والممشى", "location": "الموقع"}
    parts = " · ".join(f'{labels.get(k, k)} {v:.0f}' for k, v in it["parts"].items())
    verdict = e(at.get("ranker_note", ""))
    market = ""
    if at.get("market_median"):
        market = f'<p class="muted">متوسط السوق لسيارات مشابهة: {at["market_median"]:,.0f} ر.ع ({at.get("price_delta_pct", 0):+.0f}%)</p>'
    return f"""
<article class="item">
  <div class="rank"><span class="n">{it['rank']}</span>{change_badge(it)}</div>
  <div class="main">
    <h2><a href="{e(it['url'])}" target="_blank" rel="noopener">{e(it['title'] or 'هوندا أكورد')}</a></h2>
    <p class="facts">{facts(at)} · {e(it['location'] or 'الموقع غير مذكور')} · <span class="site">{e(it['site'])}</span></p>
    {f'<p class="verdict">{verdict}</p>' if verdict else ''}
    <details><summary>التفاصيل والملاحظات</summary>
      {market}
      <ul class="findings">{findings or '<li class="info">لا توجد ملاحظات</li>'}</ul>
      <p class="muted">تفصيل الدرجة: {e(parts)}</p>
      <p class="muted">أول ظهور {d(it['first_seen'])} · آخر ظهور {d(it['last_seen'])}</p>
    </details>
  </div>
  <div class="side">
    <div class="price">{fmt_price(it['price_omr'])}</div>{price_note(it)}
    <div class="score">{it['total']:.0f}<small>/100</small></div>
    <div class="flags">{''.join(flags)}</div>
  </div>
</article>"""


def render(data):
    s = data.get("summary") or {}
    summary = "".join(f"<li>{e(x)}</li>" for x in s.get("highlights", []))
    gone = "".join(f'<li><a href="{e(g["url"])}">{e(g["title"])}</a> · {fmt_price(g["price_omr"])} · آخر ظهور {d(g["last_seen"])}</li>'
                   for g in data["recently_gone"])
    items = "".join(row(it) for it in data["items"]) or '<p class="muted">لا توجد إعلانات بعد.</p>'
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>قائمة أكورد اليومية</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg:#F4F6F8; --ink:#16202B; --muted:#5B6773; --line:#D9DEE4; --accent:#1F5F8B;
        --good:#1C7C54; --bad:#B23A3A; --warn:#A86A00; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#11161C; --ink:#E6EBF0; --muted:#94A0AC; --line:#2A333D;
        --accent:#7DB8E0; --good:#5CC79A; --bad:#F08080; --warn:#E3B04B; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 "IBM Plex Sans Arabic", system-ui, sans-serif; }}
.wrap {{ max-width:960px; margin:0 auto; padding:32px 16px 64px; }}
header h1 {{ font-size:28px; margin:0 0 4px; }}
header p {{ margin:0; color:var(--muted); }}
.summary {{ border-inline-start:3px solid var(--accent); padding:4px 16px; margin:24px 0 32px; }}
.summary ul {{ margin:0; padding-inline-start:18px; }}
.item {{ display:grid; grid-template-columns:64px 1fr 150px; gap:16px; padding:20px 0; border-bottom:1px solid var(--line); }}
.rank .n {{ display:block; font-size:30px; font-weight:700; line-height:1; }}
.chg {{ font-size:13px; }} .up {{ color:var(--good) }} .down {{ color:var(--bad) }} .new {{ color:var(--accent) }} .same {{ color:var(--muted) }}
h2 {{ font-size:18px; margin:0 0 4px; }} h2 a {{ color:inherit; text-decoration:none; }} h2 a:hover {{ text-decoration:underline; }}
.facts, .muted {{ color:var(--muted); margin:0; font-size:14px; }}
.site {{ direction:ltr; unicode-bidi:isolate; }}
.verdict {{ margin:8px 0 0; }}
details {{ margin-top:8px; }} summary {{ cursor:pointer; color:var(--accent); font-size:14px; }}
.findings {{ padding-inline-start:18px; font-size:14px; }}
.findings .critical b {{ color:var(--bad) }} .findings .warn b {{ color:var(--warn) }} .findings .info b {{ color:var(--muted) }}
.conf {{ color:var(--muted); font-size:12px; }}
.side {{ text-align:left; }}
.price {{ font-weight:700; font-size:18px; }}
.pnote {{ display:block; font-size:12px; }} .pnote.good {{ color:var(--good) }} .pnote.bad {{ color:var(--bad) }}
.score {{ font-size:26px; font-weight:700; margin-top:6px; }} .score small {{ font-size:13px; color:var(--muted); font-weight:400; }}
.flag {{ font-size:12px; margin-inline-end:6px; }} .flag.crit {{ color:var(--bad) }} .flag.warn {{ color:var(--warn) }}
section.gone h3 {{ margin-top:40px; font-size:16px; }} section.gone a {{ color:var(--accent) }} section.gone li {{ color:var(--muted); font-size:14px; }}
@media (max-width:640px) {{ .item {{ grid-template-columns:44px 1fr; }} .side {{ grid-column:2; text-align:right; }} }}
</style></head>
<body><div class="wrap">
<header><h1>قائمة هوندا أكورد اليومية</h1>
<p>تحديث {d(data['day'])}{(' · مقارنة بيوم ' + d(data['prev_day'])) if data['prev_day'] else ''} · {len(data['items'])} سيارة نشطة</p></header>
{f'<div class="summary"><ul>{summary}</ul></div>' if summary else ''}
{items}
{f'<section class="gone"><h3>اختفت خلال آخر 7 أيام</h3><ul>{gone}</ul></section>' if gone else ''}
<p class="muted" style="margin-top:40px">الملاحظات البصرية تشير إلى ما يستحق السؤال والفحص، والحكم النهائي يكون بعد فحص فني للسيارة.</p>
</div></body></html>"""


def main():
    data = db.ranking_data(db.conn())
    out_dir = os.path.join(db.ROOT, "reports")
    os.makedirs(out_dir, exist_ok=True)
    latest = os.path.join(out_dir, "latest.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(render(data))
    shutil.copy(latest, os.path.join(out_dir, f"{data['day']}.html"))
    db.out({"report": os.path.relpath(latest, db.ROOT), "items": len(data["items"])})


if __name__ == "__main__":
    main()
