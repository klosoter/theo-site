import os, json, pathlib, re
from collections import Counter
from typing import Dict, List, Tuple
from flask import Flask, jsonify, send_from_directory, request, abort
from markdown import markdown
from dotenv import load_dotenv

load_dotenv()
ROOT = pathlib.Path(__file__).parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()

# Optional text fallbacks placed by your process (used if JSON missing)
BY_WORKS_FILE = pathlib.Path(os.getenv("BY_WORKS_FILE", DATA_DIR / "indices" / "by_work.json"))
WORK_CANON_FILE = pathlib.Path(os.getenv("WORK_CANON_FILE", DATA_DIR / "work_canon_map.json"))

def _load_json_maybe_txt(pathish: pathlib.Path, default=None):
    """Load JSON from .json or the same path with .txt (used in repo)."""
    pathish = pathlib.Path(pathish)
    for p in (pathish, pathish.with_suffix(".txt")):
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return default

app = Flask(__name__, static_folder=str(ROOT / "static"))  # assets served at /static

# ---------- helpers ----------
def _load_json(path: pathlib.Path, default=None):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def _resolve_outlines_dir():
    env_path = os.getenv("OUTLINES_DIR")
    if env_path:
        return pathlib.Path(env_path).resolve()
    data_out = DATA_DIR / "outlines"
    if data_out.exists():
        return data_out.resolve()
    return (ROOT / "outlines").resolve()

OUTLINES_DIR = _resolve_outlines_dir()

CACHE = {
    "topics": _load_json(DATA_DIR / "topics.json", []),
    "theologians": _load_json(DATA_DIR / "theologians.json", []),
    "works": _load_json(DATA_DIR / "works.json", []),
    "by_topic": _load_json(DATA_DIR / "indices" / "by_topic.json", {}),
    "by_theologian": _load_json(DATA_DIR / "indices" / "by_theologian.json", {}),
    "by_work": _load_json(DATA_DIR / "indices" / "by_work.json", {}),
    "by_topic_keyworks": _load_json(DATA_DIR / "indices" / "by_topic_keyworks.json", {}),
    "topic_work_edges": _load_json(DATA_DIR / "indices" / "topic_work_edges.json", []),
    "search": _load_json(DATA_DIR / "indices" / "search_index.json", []),
    # registries
    "institutions_registry": _load_json(DATA_DIR / "indices" / "institutions_registry.json", {"kind":"institutions","items":{}}),
    "geo_registry": _load_json(DATA_DIR / "indices" / "geo_registry.json", {"kind":"geo","items":{}}),
    "eras": _load_json(DATA_DIR / "eras.json", []),
    "traditions": _load_json(DATA_DIR / "traditions.json", []),
}

THEO_MAP = {t["id"]: t for t in (CACHE["theologians"] or []) if isinstance(t, dict) and "id" in t}
TOPIC_MAP = {t["id"]: t for t in (CACHE["topics"] or []) if isinstance(t, dict) and "id" in t}
WORK_MAP = {w["id"]: w for w in (CACHE["works"] or []) if isinstance(w, dict) and "id" in w}


# --- add near other helpers ---
def _parse_frontmatter(text: str):
    """
    Parse a very small '--- ... ---' front-matter block.
    Returns (meta_dict, body_without_frontmatter).
    Only extracts simple scalars and key_work_ids (array of quoted strings).
    """
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 3)
    if end == -1:
        return {}, text
    block = text[3:end].strip()
    body = text[end+4:].lstrip('\n')

    meta = {}
    for line in block.splitlines():
        m = re.match(r'^\s*([A-Za-z0-9_]+)\s*:\s*(.*)\s*$', line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        # strip quotes if present
        if raw.startswith('"') and raw.endswith('"'):
            val = raw[1:-1]
        elif raw.startswith("'") and raw.endswith("'"):
            val = raw[1:-1]
        else:
            val = raw

        if key == 'key_work_ids':
            # Expect YAML-ish: ["work_x","work_y",...]
            ids = re.findall(r'"([^"]+)"|\'([^\']+)\'', raw)
            meta[key] = [a or b for a, b in ids]
        else:
            meta[key] = val
    return meta, body


# ---------- Canonical works mapping ----------
def _build_canon_map(raw) -> Dict[str, str]:
    """Accepts either list[{work_id, canonical_id}] or direct mapping."""
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    out = {}
    for i in raw or []:
        wid = i.get("work_id")
        cid = i.get("canonical_id")
        if wid and cid:
            out[wid] = cid
    return out

def _load_canon_map() -> Dict[str, str]:
    raw = _load_json_maybe_txt(WORK_CANON_FILE, default={})
    cmap = _build_canon_map(raw or {})
    # Ensure canonical IDs map to themselves
    for k, v in list(cmap.items()):
        if v not in cmap:
            cmap[v] = v
    return cmap

CANON_MAP: Dict[str, str] = _load_canon_map()

def _canonicalize(wid: str) -> str:
    return CANON_MAP.get(wid, wid)

# ---------- Aggregations: counts per theologian and per topic (WTS/Recent) ----------
def _top_canonical_for_theologians() -> Dict[str, List[Tuple[str,int]]]:
    by_work = CACHE["by_work"] or {}
    counter_by_theo: Dict[str, Counter] = {}
    for wid, wdata in by_work.items():
        tid = wdata.get("primary_author_theologian_id")
        if not tid:
            continue
        cid = _canonicalize(wid)
        counter_by_theo.setdefault(tid, Counter())[cid] += 1
    # Sort by count desc, then title asc
    result: Dict[str, List[Tuple[str,int]]] = {}
    for tid, ctr in counter_by_theo.items():
        pairs = list(ctr.items())
        pairs.sort(key=lambda kv: (-kv[1], (WORK_MAP.get(kv[0], {}) or {}).get("title", kv[0])))
        result[tid] = pairs
    return result

def _canon_counts_by_topic() -> Dict[str, Dict[str, List[Tuple[str,int]]]]:
    """For each topic, compute two buckets: WTS and Recent; collapse aliases -> canonical, sort by count desc then title."""
    topics = CACHE["topics"] or []
    out: Dict[str, Dict[str, List[Tuple[str,int]]]] = {}
    for t in topics:
        kw = t.get("key_works", {}) or {}
        wts_ids = [_canonicalize(w) for w in (kw.get("wts_old_princeton") or [])]
        recent_ids = [_canonicalize(w) for w in (kw.get("recent") or [])]
        wts_ctr = Counter(wts_ids)
        recent_ctr = Counter(recent_ids)
        def sorted_list(ctr: Counter):
            items = list(ctr.items())
            items.sort(key=lambda kv: (-kv[1], (WORK_MAP.get(kv[0], {}) or {}).get("title", kv[0])))
            return items
        out[t["id"]] = {"WTS": sorted_list(wts_ctr), "Recent": sorted_list(recent_ctr)}
    return out

CANON_COUNTS_THEO_PAIRS = _top_canonical_for_theologians()
CANON_COUNTS_TOPIC_PAIRS = _canon_counts_by_topic()

# ---------- request logging ----------
@app.before_request
def _log_api_hits():
    if request.path.startswith("/api/"):
        print("[api] ←", request.method, request.path, request.query_string.decode("utf-8") or "-")

@app.get("/api/health")
def health():
    return jsonify({"ok": True})

# ---------- API: core datasets ----------
@app.get("/api/topics")
def topics():
    return jsonify(CACHE["topics"])

@app.get("/api/theologians")
def theologians():
    return jsonify(CACHE["theologians"])

@app.get("/api/works")
def works():
    return jsonify(CACHE.get("works") or [])

@app.get("/api/indices/by_topic")
def by_topic():
    return jsonify(CACHE["by_topic"])

@app.get("/api/indices/by_theologian")
def by_theologian():
    return jsonify(CACHE["by_theologian"])

@app.get("/api/indices/by_work")
def by_work():
    # Allow file override via env if needed
    data = CACHE["by_work"] or _load_json_maybe_txt(BY_WORKS_FILE, {})
    return jsonify(data)

@app.get("/api/indices/by_topic_keyworks")
def by_topic_keyworks():
    return jsonify(CACHE["by_topic_keyworks"])

@app.get("/api/indices/topic_work_edges")
def topic_work_edges():
    return jsonify(CACHE["topic_work_edges"])

# ---------- Canonical endpoints ----------
@app.get("/api/works/canon_map")
def api_canon_map():
    return jsonify(CANON_MAP)

@app.get("/api/works/reverse_canon_map")
def api_reverse_canon_map():
    reverse_canon_map = {
        canonical_id: list(set([wid for wid, cid in CANON_MAP.items() if cid == canonical_id] + [canonical_id]))
        for canonical_id in set(CANON_MAP.values())
    }
    return jsonify(reverse_canon_map)

@app.get("/api/indices/canon_counts_by_theologian")
def api_canon_counts_by_theologian():
    out = {tid: [{"id": cid, "count": n} for (cid, n) in pairs] for tid, pairs in CANON_COUNTS_THEO_PAIRS.items()}
    return jsonify(out)

@app.get("/api/indices/canon_counts_by_topic")
def api_canon_counts_by_topic():
    out = {}
    for top_id, buckets in CANON_COUNTS_TOPIC_PAIRS.items():
        out[top_id] = {
            "WTS": [{"id": cid, "count": n} for (cid, n) in (buckets.get("WTS") or [])],
            "Recent": [{"id": cid, "count": n} for (cid, n) in (buckets.get("Recent") or [])],
        }
    return jsonify(out)

# ---------- Registries ----------
@app.get("/api/registries/institutions")
def institutions_registry():
    reg = CACHE.get("institutions_registry") or {}
    items = reg.get("items", {})
    flat = {k: (v.get("name") if isinstance(v, dict) else str(v)) for k, v in items.items()}
    return jsonify(flat)

@app.get("/api/registries/geo")
def geo_registry():
    reg = CACHE.get("geo_registry") or {}
    return jsonify(reg.get("items", {}))

@app.get("/api/eras")
def api_eras():
    return jsonify(CACHE.get("eras") or [])

@app.get("/api/traditions")
def api_traditions():
    return jsonify(CACHE.get("traditions") or [])

# ---------- API: search ----------
@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    terms = [t for t in re.split(r"\s+", q.lower()) if t]
    results = []
    for item in CACHE["search"]:
        hay = " ".join([
            (item.get("name") or item.get("title") or ""),
            item.get("slug", ""),
            " ".join(item.get("eras", []) or []),
            " ".join(item.get("traditions", []) or []),
            item.get("type", ""),
        ]).lower()
        if all(t in hay for t in terms):
            if item.get("type") == "work":
                wid = item.get("id")
                if wid:
                    item = dict(item)
                    item["id"] = _canonicalize(wid)
            results.append(item)
    type_order = {"theologian": 0, "work": 1, "topic": 2, "outline": 3}
    results.sort(key=lambda x: (type_order.get(x.get("type"), 9), len(x.get("name", x.get("title", "")))))
    # Deduplicate work results that collapse to the same canonical id
    seen = set()
    deduped = []
    for r in results:
        key = (r.get("type"), r.get("id") if r.get("type") == "work" else r.get("slug") or r.get("title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return jsonify(deduped[:50])

# ---------- Markdown normalization ----------
def normalize_md(text: str) -> str:
    lines = text.splitlines()
    first_h1 = None
    for i, ln in enumerate(lines):
        if re.match(r'^\s*#\s+', ln):
            first_h1 = i
            break
    if first_h1 is not None:
        lines = lines[first_h1:]

    out = []
    pat_num_hdr = re.compile(r'^\s*\d+\.\s+\*\*.+\*\*\s*$')
    need_blank_after = False

    for line in lines:
        if pat_num_hdr.match(line):
            out.append(line.rstrip())
            need_blank_after = True
            continue

        if need_blank_after:
            if line.strip() != '':
                out.append('')
            need_blank_after = False

        if re.match(r'^\s{1,3}-\s', line):
            out.append('    ' + line.lstrip())
        else:
            out.append(line)

    return '\n'.join(out).lstrip().rstrip()

# ---------- API: outline Markdown → HTML ----------
@app.get("/api/outline")
def outline_html():
    rel = (request.args.get("path") or "").strip()
    if not rel:
        return jsonify({"error": "Missing 'path' query param"}), 400

    rel = rel.lstrip("/\\")
    candidates = [rel]
    if rel.startswith("outlines/"):
        candidates.append(rel[len("outlines/"):])
    else:
        candidates.append("outlines/" + rel)

    tried = []
    for cand in candidates:
        if ".." in cand.replace("\\", "/"):
            continue
        md_path = (OUTLINES_DIR / cand).resolve()
        tried.append(str(md_path))
        if OUTLINES_DIR in md_path.parents and md_path.exists():
            text = md_path.read_text(encoding="utf-8")
            # NEW: parse front-matter and strip it before markdown render
            meta, body = _parse_frontmatter(text)
            body = normalize_md(body)
            html = markdown(body, extensions=["fenced_code", "tables", "toc"])
            return jsonify({"html": html, "meta": meta})

    return jsonify({"error": "Not found", "outlines_dir": str(OUTLINES_DIR), "tried": tried}), 404

# ---------- Static SPA ----------
@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def spa(path):
    if path.startswith(("api/", "static/")):
        abort(404)
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
