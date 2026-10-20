#!/usr/bin/env python3
"""accord-watch database helper.

Every agent talks to the database through this CLI, so the data stays consistent.
JSON input is read from --file PATH (use this on Windows) or stdin; JSON output goes to stdout.

Commands
  init                                   create data/accord.db
  upsert-listing                         stdin: one listing JSON (see CLAUDE.md)
  mark-gone --sites a,b                  listings on scanned sites not seen today -> gone
  pending --stage S                      active listings whose current content has not passed stage S
  show ID                                full record: listing, attrs, photos, findings, price history
  set-attrs ID                           stdin: JSON object merged into attrs
  add-findings ID --stage S              stdin: JSON list of findings; replaces S findings for current content, marks S done
  done ID --stage S                      mark stage done with no findings
  set-duplicate ID --of MAIN_ID          mark ID as a repost of MAIN_ID
  photo-dupes                            near-identical photos shared across different listings
  market [--generation G] [--year Y]     price stats of comparable listings (active + gone in last 90 days)
  score                                  compute today's scores and ranks
  ranking                                today's ranking with change vs previous run
  save-run                               stdin: JSON summary for today
"""
import argparse, datetime as dt, hashlib, json, os, re, sqlite3, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "accord.db")
STAGES = ["archive", "text", "visual", "crosscheck", "inference", "price", "rank"]


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def read_input(a):
    """JSON input from --file (preferred on Windows) or stdin, always UTF-8."""
    if getattr(a, "file", None):
        with open(a.file, encoding="utf-8-sig") as f:
            return json.load(f)
    return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))


def today():
    return os.environ.get("ACCORD_DAY") or dt.date.today().isoformat()


def config():
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


PRICE_STAGES = ("price", "rank")   # these re-run when only the price moves; the rest only when text or photos change


def content_hash(desc, photo_urls):
    h = hashlib.sha256()
    h.update(json.dumps([(desc or "").strip(), sorted(photo_urls or [])], ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def stage_key(content_hash, price, stage):
    return f"{content_hash}|{price}" if stage in PRICE_STAGES else content_hash


# ---------------------------------------------------------------- commands
def cmd_init(a):
    c = conn()
    with open(os.path.join(ROOT, "db", "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    c.commit()
    out({"ok": True, "db": DB})


def cmd_upsert(a):
    d = read_input(a)
    for k in ("site", "site_listing_id", "url"):
        if not d.get(k):
            sys.exit(f"missing field: {k}")
    lid = f"{d['site']}:{d['site_listing_id']}"
    day = today()
    photos = d.get("photo_urls") or []
    ch = content_hash(d.get("description"), photos)
    phone = re.sub(r"\D", "", d.get("phone") or "")
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16] if phone else None
    c = conn()
    row = c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
    result = {"id": lid, "is_new": row is None, "price_changed": False, "content_changed": False}
    if row is None:
        c.execute("""INSERT INTO listings (id, site, site_listing_id, url, title, price_omr, location, posted_at,
                     description, seller_name, phone_hash, first_seen, last_seen, status, content_hash)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?)""",
                  (lid, d["site"], d["site_listing_id"], d["url"], d.get("title"), d.get("price_omr"),
                   d.get("location"), d.get("posted_at"), d.get("description"), d.get("seller_name"),
                   phone_hash, day, day, ch))
    else:
        result["price_changed"] = row["price_omr"] != d.get("price_omr")
        result["content_changed"] = row["content_hash"] != ch
        if result["price_changed"]:
            result["old_price"] = row["price_omr"]
        c.execute("""UPDATE listings SET url=?, title=?, price_omr=?, location=?, description=?, seller_name=?,
                     phone_hash=COALESCE(?, phone_hash), last_seen=?, status='active', content_hash=? WHERE id=?""",
                  (d["url"], d.get("title"), d.get("price_omr"), d.get("location"), d.get("description"),
                   d.get("seller_name"), phone_hash, day, ch, lid))
    c.execute("INSERT OR REPLACE INTO price_history VALUES (?,?,?)", (lid, day, d.get("price_omr")))
    if result["is_new"] or result["content_changed"]:
        existing = {r["idx"]: r for r in c.execute("SELECT * FROM photos WHERE listing_id=?", (lid,))}
        c.execute("DELETE FROM photos WHERE listing_id=?", (lid,))
        for i, u in enumerate(photos[: config()["crawl"]["max_photos_per_listing"]]):
            old = existing.get(i)
            keep = old is not None and old["url"] == u
            c.execute("INSERT INTO photos VALUES (?,?,?,?,?,?)",
                      (lid, i, u, old["local_path"] if keep else None,
                       old["sha256"] if keep else None, old["ahash"] if keep else None))
    if phone_hash:
        others = [r["id"] for r in c.execute(
            "SELECT id FROM listings WHERE phone_hash=? AND id<>?", (phone_hash, lid))]
        if others:
            result["same_seller_listings"] = others
    c.commit()
    out(result)


def cmd_mark_gone(a):
    sites = [s.strip() for s in a.sites.split(",") if s.strip()]
    c = conn()
    q = f"SELECT id FROM listings WHERE status='active' AND last_seen<? AND site IN ({','.join('?'*len(sites))})"
    gone = [r["id"] for r in c.execute(q, (today(), *sites))]
    c.executemany("UPDATE listings SET status='gone' WHERE id=?", [(g,) for g in gone])
    c.commit()
    out({"gone": gone})


def cmd_pending(a):
    c = conn()
    rows = c.execute("""SELECT l.id, l.url, l.title, l.price_omr, l.content_hash, s.content_hash AS done_key
        FROM listings l LEFT JOIN stage_runs s ON s.listing_id=l.id AND s.stage=?
        WHERE l.status='active' AND l.duplicate_of IS NULL ORDER BY l.first_seen""", (a.stage,)).fetchall()
    out([{k: r[k] for k in ("id", "url", "title", "price_omr")} for r in rows
         if r["done_key"] != stage_key(r["content_hash"], r["price_omr"], a.stage)])


def record(c, lid):
    row = c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
    if not row:
        sys.exit(f"unknown listing {lid}")
    d = dict(row)
    d["attrs"] = json.loads(d["attrs"] or "{}")
    d["photos"] = [dict(r) for r in c.execute("SELECT idx,url,local_path FROM photos WHERE listing_id=? ORDER BY idx", (lid,))]
    d["findings"] = [dict(r) for r in c.execute(
        "SELECT stage,severity,kind,field,claim,evidence,confidence FROM findings WHERE listing_id=? AND content_hash=? ORDER BY id",
        (lid, d["content_hash"]))]
    d["price_history"] = [dict(r) for r in c.execute("SELECT day,price_omr FROM price_history WHERE listing_id=? ORDER BY day", (lid,))]
    return d


def cmd_show(a):
    out(record(conn(), a.id))


def cmd_set_attrs(a):
    patch = read_input(a)
    c = conn()
    row = c.execute("SELECT attrs FROM listings WHERE id=?", (a.id,)).fetchone()
    if not row:
        sys.exit(f"unknown listing {a.id}")
    attrs = json.loads(row["attrs"] or "{}")
    attrs.update(patch)
    c.execute("UPDATE listings SET attrs=? WHERE id=?", (json.dumps(attrs, ensure_ascii=False), a.id))
    c.commit()
    out({"id": a.id, "attrs": attrs})


def mark_done(c, lid, stage):
    r = c.execute("SELECT content_hash, price_omr FROM listings WHERE id=?", (lid,)).fetchone()
    c.execute("INSERT OR REPLACE INTO stage_runs VALUES (?,?,?,?)",
              (lid, stage, stage_key(r["content_hash"], r["price_omr"], stage), today()))
    return r["content_hash"]


def cmd_add_findings(a):
    if a.stage not in STAGES:
        sys.exit(f"stage must be one of {STAGES}")
    items = read_input(a)
    c = conn()
    ch = mark_done(c, a.id, a.stage)
    c.execute("DELETE FROM findings WHERE listing_id=? AND stage=? AND content_hash=?", (a.id, a.stage, ch))
    for f in items:
        if f.get("severity") not in ("info", "warn", "critical"):
            sys.exit("severity must be info | warn | critical")
        c.execute("""INSERT INTO findings (listing_id,stage,severity,kind,field,claim,evidence,confidence,content_hash,created)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (a.id, a.stage, f["severity"], f.get("kind"), f.get("field"), f.get("claim"),
                   f.get("evidence"), f.get("confidence"), ch, today()))
    c.commit()
    out({"id": a.id, "stage": a.stage, "saved": len(items)})


def cmd_done(a):
    c = conn()
    mark_done(c, a.id, a.stage)
    c.commit()
    out({"id": a.id, "stage": a.stage, "done": True})


def cmd_set_duplicate(a):
    c = conn()
    c.execute("UPDATE listings SET duplicate_of=? WHERE id=?", (a.of, a.id))
    c.commit()
    out({"id": a.id, "duplicate_of": a.of})


def cmd_photo_dupes(a):
    c = conn()
    rows = c.execute("SELECT listing_id, idx, ahash FROM photos WHERE ahash IS NOT NULL").fetchall()
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            x, y = rows[i], rows[j]
            if x["listing_id"] == y["listing_id"]:
                continue
            dist = bin(int(x["ahash"], 16) ^ int(y["ahash"], 16)).count("1")
            if dist <= 5:
                pairs.append({"a": f'{x["listing_id"]}#{x["idx"]}', "b": f'{y["listing_id"]}#{y["idx"]}', "distance": dist})
    out(pairs)


def cmd_market(a):
    c = conn()
    since = (dt.date.fromisoformat(today()) - dt.timedelta(days=90)).isoformat()
    prices = []
    for r in c.execute("SELECT price_omr, attrs FROM listings WHERE price_omr IS NOT NULL AND duplicate_of IS NULL AND last_seen>=?", (since,)):
        at = json.loads(r["attrs"] or "{}")
        if a.generation and at.get("generation") != a.generation:
            continue
        if a.year and at.get("year") and abs(int(at["year"]) - a.year) > 1:
            continue
        prices.append(r["price_omr"])
    if not prices:
        out({"count": 0})
        return
    out({"count": len(prices), "median": statistics.median(prices), "min": min(prices), "max": max(prices)})


def clamp(x):
    return max(0.0, min(100.0, x))


def cmd_score(a):
    cfg = config()
    w, b = cfg["weights"], cfg["budget"]
    pref = [p.lower() for p in cfg["location"]["preferred"]]
    c = conn()
    day = today()
    year_now = dt.date.fromisoformat(day).year
    min_year, max_year = cfg["target"]["min_year"], cfg["target"]["max_year"]
    rows = c.execute("SELECT * FROM listings WHERE status='active' AND duplicate_of IS NULL").fetchall()
    scored, excluded = [], []
    for r in rows:
        at = json.loads(r["attrs"] or "{}")
        if at.get("year") and not (min_year <= int(at["year"]) <= max_year):
            excluded.append(r["id"])         # outside the year range in config.yaml: tracked, not ranked
            continue
        p = r["price_omr"]
        # budget
        if p is None:
            s_budget = 40
        elif p <= b["target_omr"]:
            s_budget = 100
        elif p >= b["hard_max_omr"]:
            s_budget = 0
        else:
            s_budget = 100 * (b["hard_max_omr"] - p) / (b["hard_max_omr"] - b["target_omr"])
        # condition (from Ranker, 0..10)
        cs = at.get("condition_score")
        s_condition = 50 if cs is None else clamp(float(cs) * 10)
        # consistency: findings that point to problems
        f = c.execute("""SELECT severity, COUNT(*) n FROM findings WHERE listing_id=? AND content_hash=?
                         AND stage IN ('text','visual','crosscheck','archive') GROUP BY severity""",
                      (r["id"], r["content_hash"])).fetchall()
        sev = {x["severity"]: x["n"] for x in f}
        s_consistency = clamp(100 - 30 * sev.get("critical", 0) - 10 * sev.get("warn", 0))
        # value vs market
        delta = at.get("price_delta_pct")
        s_value = 50 if delta is None else clamp(50 - 2.5 * float(delta))
        # age and mileage
        # mileage: Inferencer's corrected figure (e.g. miles shown as km) > ad text > odometer photo
        real = (at.get("inferred") or {}).get("real_mileage_km")
        real = real.get("value") if isinstance(real, dict) else real
        year = at.get("year")
        km = next((v for v in (real, at.get("mileage_km"), at.get("visible_odometer_km")) if v is not None), None)
        if year and km is not None:
            age = max(1, year_now - int(year) + 1)
            ratio = float(km) / (age * cfg["expected_km_per_year"])
            s_age = clamp(100 - max(0, ratio - 0.6) * 80 - (year_now - int(year)) * 3)
        else:
            s_age = 10                       # unknown mileage is a risk, not a neutral
        if km is None:
            s_condition = min(s_condition, 50)
        # location
        loc = (r["location"] or "").lower()
        s_loc = 60 if not loc else (100 if any(x in loc for x in pref) else 40)
        parts = {"budget": s_budget, "condition": s_condition, "consistency": s_consistency,
                 "value": s_value, "age_mileage": s_age, "location": s_loc}
        total = sum(parts[k] * w[k] for k in parts) / sum(w.values())
        if sev.get("critical", 0) >= 2:      # two serious contradictions push a car to the bottom
            total *= 0.6
        scored.append((r["id"], round(total, 1), {k: round(v, 1) for k, v in parts.items()}))
    scored.sort(key=lambda x: -x[1])
    c.execute("DELETE FROM scores WHERE day=?", (day,))
    for rank, (lid, total, parts) in enumerate(scored, 1):
        c.execute("INSERT INTO scores VALUES (?,?,?,?,?)", (lid, day, total, json.dumps(parts), rank))
        mark_done(c, lid, "rank")
    for lid in excluded:
        mark_done(c, lid, "rank")
    c.commit()
    out({"day": day, "scored": len(scored), "excluded_out_of_year_range": excluded})


def ranking_data(c, day=None):
    day = day or today()
    prev = c.execute("SELECT MAX(day) d FROM scores WHERE day<?", (day,)).fetchone()["d"]
    prev_rank = {r["listing_id"]: r["rank"] for r in c.execute("SELECT listing_id, rank FROM scores WHERE day=?", (prev,))} if prev else {}
    items = []
    for s in c.execute("SELECT * FROM scores WHERE day=? ORDER BY rank", (day,)):
        d = record(c, s["listing_id"])
        d.update({"rank": s["rank"], "total": s["total"], "parts": json.loads(s["parts"]),
                  "prev_rank": prev_rank.get(s["listing_id"])})
        items.append(d)
    gone = [dict(r) for r in c.execute(
        "SELECT id,title,url,price_omr,last_seen FROM listings WHERE status='gone' AND last_seen>=? ORDER BY last_seen DESC",
        ((dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat(),))]
    run = c.execute("SELECT summary FROM runs WHERE day=?", (day,)).fetchone()
    return {"day": day, "prev_day": prev, "items": items, "recently_gone": gone,
            "summary": json.loads(run["summary"]) if run else None}


def cmd_ranking(a):
    data = ranking_data(conn())
    for it in data["items"]:
        it.pop("description", None)
        it.pop("photos", None)
    out(data)


def cmd_save_run(a):
    s = read_input(a)
    c = conn()
    c.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (today(), json.dumps(s, ensure_ascii=False)))
    c.commit()
    out({"ok": True})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init").set_defaults(fn=cmd_init)
    x = sp.add_parser("upsert-listing"); x.add_argument("--file"); x.set_defaults(fn=cmd_upsert)
    x = sp.add_parser("mark-gone"); x.add_argument("--sites", required=True); x.set_defaults(fn=cmd_mark_gone)
    x = sp.add_parser("pending"); x.add_argument("--stage", required=True, choices=STAGES); x.set_defaults(fn=cmd_pending)
    x = sp.add_parser("show"); x.add_argument("id"); x.set_defaults(fn=cmd_show)
    x = sp.add_parser("set-attrs"); x.add_argument("id"); x.add_argument("--file"); x.set_defaults(fn=cmd_set_attrs)
    x = sp.add_parser("add-findings"); x.add_argument("id"); x.add_argument("--file"); x.add_argument("--stage", required=True); x.set_defaults(fn=cmd_add_findings)
    x = sp.add_parser("done"); x.add_argument("id"); x.add_argument("--stage", required=True, choices=STAGES); x.set_defaults(fn=cmd_done)
    x = sp.add_parser("set-duplicate"); x.add_argument("id"); x.add_argument("--of", required=True); x.set_defaults(fn=cmd_set_duplicate)
    sp.add_parser("photo-dupes").set_defaults(fn=cmd_photo_dupes)
    x = sp.add_parser("market"); x.add_argument("--generation"); x.add_argument("--year", type=int); x.set_defaults(fn=cmd_market)
    sp.add_parser("score").set_defaults(fn=cmd_score)
    sp.add_parser("ranking").set_defaults(fn=cmd_ranking)
    x = sp.add_parser("save-run"); x.add_argument("--file"); x.set_defaults(fn=cmd_save_run)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
