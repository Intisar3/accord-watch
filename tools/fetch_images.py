#!/usr/bin/env python3
"""Download listing photos that are not on disk yet, then record sha256 and an average hash.

Usage:  python3 tools/fetch_images.py [--listing ID]
Photos land in data/photos/<site>_<id>/<idx>.jpg, resized to 1600px on the long edge
so the Visual Inspector can read them quickly.
"""
import argparse, hashlib, io, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402  (also sets UTF-8 output)

from PIL import Image  # noqa: E402

UA = "Mozilla/5.0 (accord-watch personal research; one run per day)"


def ahash(img):
    g = img.convert("L").resize((8, 8))
    px = list(g.getdata())
    avg = sum(px) / 64
    return f"{sum(1 << i for i, v in enumerate(px) if v > avg):016x}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing")
    a = ap.parse_args()
    c = db.conn()
    q = "SELECT listing_id, idx, url FROM photos WHERE local_path IS NULL"
    args = ()
    if a.listing:
        q += " AND listing_id=?"
        args = (a.listing,)
    rows = c.execute(q, args).fetchall()
    ok = fail = 0
    for r in rows:
        folder = os.path.join(db.ROOT, "data", "photos", r["listing_id"].replace(":", "_"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{r["idx"]:02d}.jpg')
        try:
            req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=30).read()
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((1600, 1600))
            img.convert("RGB").save(path, "JPEG", quality=88)
            c.execute("UPDATE photos SET local_path=?, sha256=?, ahash=? WHERE listing_id=? AND idx=?",
                      (os.path.relpath(path, db.ROOT), hashlib.sha256(raw).hexdigest(), ahash(img),
                       r["listing_id"], r["idx"]))
            c.commit()
            ok += 1
            time.sleep(0.5)
        except Exception as e:  # keep going; the Archivist reports failures
            print(f"FAILED {r['listing_id']}#{r['idx']}: {e}", file=sys.stderr)
            fail += 1
    db.out({"downloaded": ok, "failed": fail})


if __name__ == "__main__":
    main()
