import os, json, pathlib, re
from collections import Counter, defaultdict
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

# Allow .txt (JSON-per-file in repo) or .json
def _load_json_maybe_txt(pathish: pathlib.Path, default=None):
    pathish = pathlib.Path(pathish)
    if pathish.exists():
        try:
            with pathish.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # try .txt neighbor if present
    txt_path = pathish.with_suffix(".txt")
    if txt_path.exists():
        try:
            with txt_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
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
}

THEO_MAP = {t["id"]: t for t in (CACHE["theologians"] or []) if isinstance(t, dict) and "id" in t}
TOPIC_MAP = {t["id"]: t for t in (CACHE["topics"] or []) if isinstance(t, dict) and "id" in t}
WORK_MAP = {w["id"]: w for w in (CACHE["works"] or []) if isinstance(w, dict) and "id" in w}

# ---------- Canonical works mapping ----------
def _build_canon_map(raw) -> Dict[str, str]:
    return {i["work_id"]: i["canonical_id"] for i in raw}

def _load_canon_map() -> Dict[str, str]:
    # Load from JSON; if missing, try .txt neighbor as JSON
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
        def sort_key(kv):
            cid, n = kv
            title = (WORK_MAP.get(cid, {}) or {}).get("title", cid)
            return (-n, title)
        pairs.sort(key=sort_key)
        result[tid] = pairs
    return result

def _canon_counts_by_topic() -> Dict[str, Dict[str, List[Tuple[str,int]]]]:
    """
    For each topic, compute two buckets: WTS and Recent.
    Count alias hits to their canonical, then return sorted (desc count, then title).
    """
    topics = CACHE["topics"] or []
    out: Dict[str, Dict[str, List[Tuple[str,int]]]] = {}
    for t in topics:
        kw = t.get("key_works", {}) or {}
        wts_ids = [ _canonicalize(w) for w in (kw.get("wts_old_princeton") or []) ]
        recent_ids = [ _canonicalize(w) for w in (kw.get("recent") or []) ]
        wts_ctr = Counter(wts_ids)
        recent_ctr = Counter(recent_ids)
        def sorted_list(ctr: Counter):
            items = list(ctr.items())
            def srt(kv):
                cid, n = kv
                title = (WORK_MAP.get(cid, {}) or {}).get("title", cid)
                return (-n, title)
            items.sort(key=srt)
            return items
        out[t["id"]] = {
            "WTS": sorted_list(wts_ctr),
            "Recent": sorted_list(recent_ctr),
        }
    return out

CANON_COUNTS_THEO_PAIRS = _top_canonical_for_theologians()   # {theoId: [(cid,count), ...]}
CANON_COUNTS_TOPIC_PAIRS = _canon_counts_by_topic()          # {topicId: {"WTS":[(cid,count)], "Recent":[(cid,count)]}}

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
    # Only return canonical works? Keep full for compatibility; UI only links to canon.
    return jsonify(CACHE.get("works") or [])

@app.get("/api/indices/by_topic")
def by_topic():
    return jsonify(CACHE["by_topic"])

@app.get("/api/indices/by_theologian")
def by_theologian():
    return jsonify(CACHE["by_theologian"])

@app.get("/api/indices/by_work")
def by_work():
    return jsonify(CACHE["by_work"])

@app.get("/api/indices/by_topic_keyworks")
def by_topic_keyworks():
    return jsonify(CACHE["by_topic_keyworks"])

@app.get("/api/indices/topic_work_edges")
def topic_work_edges():
    return jsonify(CACHE["topic_work_edges"])

# ---------- NEW: Canonical endpoints ----------
@app.get("/api/works/canon_map")
def api_canon_map():
    return jsonify(CANON_MAP)

@app.get("/api/indices/canon_counts_by_theologian")
def api_canon_counts_by_theologian():
    # Convert to [{id,count}] for each theologian id
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
            # If a search item is a work alias, replace id with canonical ID
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
        key = (r.get("type"), r.get("id") if r.get("type")=="work" else r.get("slug") or r.get("title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return jsonify(deduped[:50])

# ---------- Markdown normalization ----------
def normalize_md(text: str) -> str:
    import re
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
    print(rel)
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
        print(md_path.parents)
        if OUTLINES_DIR in md_path.parents and md_path.exists():
            print("FOUND", md_path)
            text = md_path.read_text(encoding="utf-8")
            text = normalize_md(text)
            html = markdown(text, extensions=["fenced_code", "tables", "toc"])
            return jsonify({"html": html})

    return jsonify({
        "error": "Not found",
        "outlines_dir": str(OUTLINES_DIR),
        "tried": tried
    }), 404

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
