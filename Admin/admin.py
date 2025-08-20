#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical Mapping Tool (simplified)

- Reads: theologians.json, indices/by_work.json
- Maintains: data/work_canon_map.json
- Purpose: Pick canonical work ids per author.
"""

import os, json, pathlib, shutil, datetime
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv()
ROOT = pathlib.Path(__file__).parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "../data")).resolve()

THEO_FILE = DATA_DIR / "theologians.json"
BY_WORK   = DATA_DIR / "indices/by_work.json"
MAP_FILE  = DATA_DIR / "work_canon_map.json"

app = Flask(__name__, static_folder=str(ROOT / "static"))

def read_json(p, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def write_json(p, obj):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if p.exists():
        backups = p.parent / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backups / f"{p.name}.bak-{ts}")
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _root(m, wid):
    seen, cur = set(), wid
    while True:
        nxt = m.get(cur, cur)
        if nxt == cur or nxt in seen: break
        seen.add(cur); cur = nxt
    for s in seen: m[s] = cur
    return cur

def _load_map(all_ids):
    rows = read_json(MAP_FILE, []) or []
    m = {r["work_id"]: r["canonical_id"] for r in rows if r.get("work_id")}
    for wid in all_ids:
        m.setdefault(wid, wid)
    for wid in list(m): m[wid] = _root(m, wid)
    return m

def _save_map(m):
    rows = [{"work_id": wid, "canonical_id": cid} for wid, cid in sorted(m.items())]
    write_json(MAP_FILE, rows)

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/authors")
def api_authors():
    theos = read_json(THEO_FILE, []) or []
    theos = [{"id": t.get("id"), "full_name": t.get("name") or t.get("name"),
              "dates": t.get("dates")} for t in theos if t.get("id")]
    theos.sort(key=lambda t: t["full_name"])
    return jsonify(theos)

@app.get("/api/works")
def api_works():
    author_id = request.args.get("author_id")
    if not author_id:
        return jsonify({"error": "author_id required"}), 400
    by_work = read_json(BY_WORK, {}) or {}
    works = []
    for wid, node in by_work.items():
        if node.get("primary_author_theologian_id") == author_id:
            works.append({"id": wid, "title": node.get("title")})
    works.sort(key=lambda w: (w.get("title") or "", w["id"]))
    return jsonify(works)

@app.get("/api/map")
def api_map():
    by_work = read_json(BY_WORK, {}) or {}
    all_ids = list(by_work.keys())
    m = _load_map(all_ids)
    return jsonify([{"work_id": wid, "canonical_id": cid} for wid, cid in sorted(m.items())])

@app.post("/api/map/merge")
def api_merge():
    data = request.get_json(force=True, silent=True) or {}
    canonical_id = data.get("canonical_id")
    merge_ids = [x for x in (data.get("merge_ids") or []) if x and x != canonical_id]
    if not canonical_id or not merge_ids:
        return jsonify({"error": "canonical_id and merge_ids required"}), 400

    by_work = read_json(BY_WORK, {}) or {}
    all_ids = list(by_work.keys())
    m = _load_map(all_ids)

    for mid in merge_ids:
        m[mid] = canonical_id
    for wid in list(m): m[wid] = _root(m, wid)
    _save_map(m)
    return jsonify({"ok": True, "canonical_id": canonical_id, "merged": merge_ids})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
