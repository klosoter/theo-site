import os, json, pathlib, re
from collections import Counter
from typing import Dict, List, Tuple
from flask import Flask, jsonify, send_from_directory, request, abort
from markdown import markdown
from markdown_it import MarkdownIt
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()

import re
_BULLET_2SPACE_RE = re.compile(r"^( {1,2})([-*+])\s+")
import re

def _collapse_interbullet_blank_lines(text: str) -> str:
    """
    Remove blank lines *between* list items at the same indentation level.
    Keep blanks before headings/paragraphs. Ignore fenced code blocks.
    """
    if not text:
        return text

    lines = text.splitlines()
    out = []

    fence_re = re.compile(r"^```")
    bullet_re = re.compile(r"^(\s*)([-*+])\s+")

    in_fence = False
    prev_was_bullet = False
    prev_indent = None
    pending_blank = False  # blank after a bullet we haven't decided to keep/drop yet

    for ln in lines:
        # handle fences
        if fence_re.match(ln):
            # flush any pending blank before the fence
            if pending_blank:
                out.append("")
                pending_blank = False
            in_fence = not in_fence
            out.append(ln)
            prev_was_bullet = False
            prev_indent = None
            continue

        if in_fence:
            # inside code: pass through literally
            if pending_blank:
                out.append("")
                pending_blank = False
            out.append(ln)
            continue

        # outside fences
        if ln.strip() == "":
            # blank line
            if prev_was_bullet:
                # maybe drop it later if next line is same-indent bullet
                pending_blank = True
            else:
                out.append("")
            continue

        # non-blank line
        m = bullet_re.match(ln)
        if m:
            indent = len(m.group(1) or "")

            if pending_blank:
                # if previous was bullet at SAME indent, drop the blank
                if not (prev_was_bullet and indent == prev_indent):
                    out.append("")
                pending_blank = False

            out.append(ln)
            prev_was_bullet = True
            prev_indent = indent
        else:
            # heading/paragraph/etc.
            if pending_blank:
                # we DO want a blank before non-bullet content
                out.append("")
                pending_blank = False
            out.append(ln)
            prev_was_bullet = False
            prev_indent = None

    return "\n".join(out)


def _fix_two_space_bullets(text: str) -> str:
    """
    Normalize leading 1- or 2-space bullets to 4-space bullets.
    Only outside fenced code blocks.
    """
    if not text:
        return text

    lines = text.splitlines()
    out = []
    in_fence = False
    fence_re = re.compile(r"^```")

    for ln in lines:
        if fence_re.match(ln):
            in_fence = not in_fence
            out.append(ln)
            continue

        if not in_fence:
            m = _BULLET_2SPACE_RE.match(ln)
            if m:
                indent = m.group(1)     # either " " or "  "
                rest = ln[len(indent):]  # remove the original indent
                out.append("    " + rest)  # force 4 spaces
                continue

        out.append(ln)

    return "\n".join(out)



MD = MarkdownIt("commonmark", {
    "html": False,     # no raw HTML from user content
    "linkify": True,   # auto-link URLs
    "typographer": False,
}).enable("table")      # tables on; code fences are already on in commonmark

def render_md(text: str) -> str:
    if not text:
        return ""
    text = _fix_two_space_bullets(text)
    text = _collapse_interbullet_blank_lines(text)
#     text = text.replace("\n  -", "\n    -")  # also fix any 2-space indented bullets after line breaks
    return MD.render(text)



ROOT = pathlib.Path(__file__).parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()

# Optional text fallbacks placed by your process (used if JSON missing)
BY_WORKS_FILE = pathlib.Path(os.getenv("BY_WORKS_FILE", DATA_DIR / "indices" / "by_work.json"))
WORK_CANON_FILE = pathlib.Path(os.getenv("WORK_CANON_FILE", DATA_DIR / "work_canon_map.json"))
THEOLOGIAN_ESSAYS_DIR = (DATA_DIR / "theologian-essays").resolve()


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

def last_name_key(full_name: str) -> str:
    if not full_name:
        return ""
    full_name = (full_name or "").strip()
    full_name = re.sub(r"\s+", " ", full_name)
    parts = full_name.split()

    if not parts:
        return ""
    last = re.sub(r"[^a-zA-Z]", "", parts[-1])
    # if the last token is 3 or fewer letters, include the previous word too
    if len(last) <= 3 and len(parts) >= 2:
        prev = re.sub(r"[^a-zA-Z]", "", parts[-2])
        return f"{prev} {last}"
    return last

# ======== Essays (CH/AP) — REPLACE the earlier essay helpers with THIS ========
from datetime import datetime  # you already added this, but just to be sure.

ESSAY_ROOT = ROOT

def _resolve_any_dir(*names):
    for n in names:
        p = (ESSAY_ROOT / n).resolve()
        if p.exists():
            return p
    return (ESSAY_ROOT / names[0]).resolve()

AP_ROOT = _resolve_any_dir("ap-data", "Ap-data")
CH_ROOT = _resolve_any_dir("ch-data", "Ch-data")

CH_CATEGORIES = [
    {"key": "1", "label": "Ancient",     "dir": "Ancient"},
    {"key": "2", "label": "Medieval",    "dir": "Medieval"},
    {"key": "3", "label": "Reformation", "dir": "Reformation"},
    {"key": "4", "label": "Modern",      "dir": "Modern"},
]

AP_CATEGORIES = [
    {"key": "1", "label": "Figures",                              "dir": os.path.join("ap-figures")},
    {"key": "2", "label": "Issues",                               "dir": os.path.join("ap-issues")},
    {"key": "3", "label": "Van Til — Method Foundations",         "dir": os.path.join("ap-cvt-src", "Method Foundations")},
    {"key": "4", "label": "Van Til — Interlocutors & Influences", "dir": os.path.join("ap-cvt-src", "Interlocutors & Influences")},
    {"key": "5", "label": "Van Til — Debates & Controversies",    "dir": os.path.join("ap-cvt-src", "Debates & Controversies")},
]

_slug_rx = re.compile(r"[^a-z0-9]+")
def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = _slug_rx.sub("-", s)
    return s.strip("-").strip(".")

# Accept either "TITLE:"/etc OR markdown headings like "### Title"
# We’ll normalize the header label to one of: title, preview, essay, recap
_HDR_RE = re.compile(
    r"""^\s{0,3}  # up to 3 spaces
        (?:
          \#{1,6}\s*([A-Za-z ]+)\s*:?\s*$   # markdown heading form (### Title)
          |
          ([A-Za-z ]+)\s*:\s*$              # plain KEY: form
        )
    """,
    re.I | re.X,
)

# map many spellings to canonical keys
def _canon_header(label: str) -> str | None:
    if not label:
        return None
    k = re.sub(r"\s+", " ", label.strip().lower())
    if k in ("title",): return "title"
    if k in ("preview", "preview notes"): return "preview"
    if k in ("essay",): return "essay"
    if k in ("recap", "recap notes"): return "recap"
    return None

def _parse_essay_blocks(txt: str) -> Dict[str, str]:
    """Return dict with keys: title, preview, essay, recap (strings, may be empty)."""
    lines = txt.replace("\r\n", "\n").split("\n")
    buckets = {"title": [], "preview": [], "essay": [], "recap": []}
    cur = None

    for ln in lines:
        m = _HDR_RE.match(ln)
        if m:
            label = m.group(1) or m.group(2) or ""
            canon = _canon_header(label)
            if canon:
                cur = canon
                continue  # header line itself doesn’t go into content
        if cur:
            buckets[cur].append(ln)

    # Clean up blocks
    out = {}
    for k, arr in buckets.items():
        while arr and not arr[0].strip(): arr.pop(0)
        while arr and not arr[-1].strip(): arr.pop()
        out[k] = "\n".join(arr).strip()

    # Title fallback: first non-empty non-header line; otherwise filename gets used by caller
    if not out["title"]:
        for ln in lines:
            if _HDR_RE.match(ln):  # skip headings
                continue
            if ln.strip():
                out["title"] = ln.strip()
                break

    # Remove only markdown hashes, but preserve leading numbers like "1." or "3.2."
    t = out.get("title") or ""
    t = re.sub(r"^\s*\#{1,6}\s*", "", t).strip()
    # Don’t strip numeric prefixes—keep things like "1." or "3.2."
    out["title"] = t

    return out

def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _md_min_to_html(md: str) -> str:
    """Tiny markdown-ish renderer: paragraphs + unordered lists only (safe)."""
    if not md: return ""
    lines = md.split("\n")
    out, in_list = [], False
    for ln in lines:
        if re.match(r"^\s*[-*]\s+", ln):
            if not in_list:
                out.append("<ul>"); in_list = True
            item = re.sub(r"^\s*[-*]\s+", "", ln)
            out.append(f"<li>{_html_escape(item)}</li>")
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            if ln.strip() == "":
                out.append("")
            else:
                out.append(f"<p>{_html_escape(ln)}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)

# EXAM ESSAYS

EXAM_ES_DIR = (ROOT / "exam_essays_structured").resolve()

EXAM_ESSAY_MAP = {}
EXAM_ESSAY_FILES = {}

def _load_exam_essays():
    global EXAM_ESSAY_MAP, EXAM_ESSAY_FILES
    out = []
    file_map = {}

    if EXAM_ES_DIR.is_dir():
        for path in sorted(EXAM_ES_DIR.glob("*.json")):
            data = _load_json(path, {})
            if not isinstance(data, dict):
                continue
            if "id" not in data:
                data["id"] = path.stem

            track = (data.get("exam_track") or "").upper()
            if track == "ST":
                data["exam_track_label"] = "Systematic Theology"
            elif track == "CH":
                data["exam_track_label"] = "Church History"
            elif track == "AP":
                data["exam_track_label"] = "Apologetics"
            else:
                data["exam_track_label"] = track or "Other"

            # NEW: pre-render model_oral_answers markdown → HTML
            moa = data.get("model_oral_answers") or {}
            for key in ("critical_historical_fixes",
                        "critical_doctrinal_themes",
                        "top_exam_questions"):
                arr = moa.get(key)
                if isinstance(arr, list):
                    for qa in arr:
                        if not isinstance(qa, dict):
                            continue
                        md = qa.get("answer_markdown")
                        md = re.sub(r"\n[ ]{2}-", "\n    -", md)
                        qa["answer_html"] = render_md(md)

            out.append(data)
            file_map[data["id"]] = path

    CACHE["exam_essays"] = out
    EXAM_ESSAY_MAP = {e["id"]: e for e in out}
    EXAM_ESSAY_FILES = file_map



_load_exam_essays()


@app.get("/api/exam_essays")
def api_exam_essays():
    items = []
    for e in CACHE.get("exam_essays", []):
        items.append({
            "id": e["id"],
            "exam_track": e.get("exam_track"),
            "exam_track_label": e.get("exam_track_label"),
            "session": e.get("session"),
            "question_label": e.get("question_label"),
            "question_text": e.get("question_text"),
        })
    def _track_order(t):
        if t == "ST": return 0
        if t == "CH": return 1
        if t == "AP": return 2
        return 9
    items.sort(key=lambda x: (_track_order(x.get("exam_track")), x.get("question_label") or ""))
    return jsonify(items)

@app.get("/api/exam_essays/<essay_id>")
def api_exam_essay_detail(essay_id):
    e = EXAM_ESSAY_MAP.get(essay_id)
    if not e:
        return jsonify({"error": "Not found"}), 404
    return jsonify(e)

@app.post("/api/exam_essays/<essay_id>/update_note")
def api_update_exam_essay_note(essay_id):
    payload = request.get_json(force=True) or {}
    path = payload.get("path")      # e.g. "user_notes.thesis_points"
    index = payload.get("index")
    value = payload.get("value", "")

    if not path or not isinstance(index, int):
        return jsonify({"error": "invalid payload"}), 400

    essay = EXAM_ESSAY_MAP.get(essay_id)
    file_path = EXAM_ESSAY_FILES.get(essay_id)
    if essay is None or file_path is None:
        return jsonify({"error": "not found"}), 404

    # --- version history BEFORE mutating ---
    history = essay.setdefault("_note_history", [])
    history.insert(0, {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_notes": essay.get("user_notes", {}),
        "oral_prep_notes": essay.get("oral_prep_notes", {}),
    })
    if len(history) > 10:
        del history[10:]

    # --- generic path navigation ---
    keys = path.split(".")  # ["user_notes", "weak_spots", "logic_weaknesses"]
    target = essay
    for key in keys[:-1]:
        if key not in target or not isinstance(target[key], dict):
            target[key] = {}
        target = target[key]

    arr_key = keys[-1]
    arr = target.get(arr_key)
    if not isinstance(arr, list):
        arr = []
    # extend array if needed
    while len(arr) <= index:
        arr.append("")
    arr[index] = value
    target[arr_key] = arr

    # --- write back to disk ---
    # don't persist internal helper fields if you add any later;
    # _note_history *is* meant to be saved.
    to_save = dict(essay)
    # if you ever add other transient fields, pop them here

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)

    return jsonify({"ok": True})




DIGESTS_ROOT = (ROOT / "Digests").resolve()
DIGEST_CATS  = ["AP", "ST", "CH"]

from utils import slugify2, parse_digest_filename_md

def _scan_digests_md():
    recs = []
    for cat in DIGEST_CATS:
        folder = DIGESTS_ROOT / cat
        if not folder.exists():
            continue
        for f in sorted(folder.glob("*.md")):
            # keep your “skip temp/hidden” rule
            if not re.match(r"^[A-Za-z0-9]", f.name):
                continue
            title, authors_display, authors_short = parse_digest_filename_md(f.name)
            if not title:
                continue
            slug = slugify2(f"{cat}-{authors_display}-{title}", max_len=220)
            recs.append({
                "type": "digest",
                "category": cat,
                "title": title,
                "authors_display": authors_display,  # full left side, untouched
                "authors_short": authors_short,      # surnames only
                "slug": slug,
                "filename": f.name,
                "path": f"Digests/{cat}/{f.name}",
            })
    return recs

def _read_md(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8")
    return render_md(text)
#     return markdown(text, extensions=["tables", "footnotes"])

@app.get("/api/digests")
def api_digests_index():
    # wrap in { digests: [...] } so front-end sees payload.digests
    if "digests" not in CACHE:
        CACHE["digests"] = _scan_digests_md()
    return {"digests": CACHE["digests"]}

@app.get("/api/digest/<slug>")
def api_digest_meta(slug):
    # needed by DigestPage()
    slug = (slug or "").lower().strip()
    digests = CACHE.get("digests") or _scan_digests_md()
    hit = next((d for d in digests if (d.get("slug") or "").lower() == slug), None)

    if not hit:
        return {"error": "Not found"}, 404
    # you can also add a convenience 'name' the search UI might use
    return {
        **hit,
        "name": f"{hit['authors_display']}: {hit['title']}",
    }

@app.get("/api/digest_html/<slug>")
def api_digest_html(slug):
    slug = (slug or "").lower().strip()
    digests = CACHE.get("digests") or _scan_digests_md()
    hit = next((d for d in digests if (d.get("slug") or "").lower() == slug), None)
    if not hit:
        return {"html": "<div class='small'>Not found.</div>"}, 404
    abs_path = (DIGESTS_ROOT / hit["category"] / hit["filename"]).resolve()
    if DIGESTS_ROOT not in abs_path.parents or not abs_path.exists():
        return {"html": "<div class='small'>File missing.</div>"}, 404
    html = _read_md(abs_path)
    return {"html": f"<article class='prose max-w-none'>{html}</article>"}


def _scan_domain(root_dir: pathlib.Path, domain_id: str, label: str, categories: List[Dict]) -> Dict:
    essays = []
    for cat in categories:
        abs_dir = (root_dir / cat["dir"]).resolve()
        if not abs_dir.exists():
            continue
        for fp in sorted(abs_dir.glob("*.txt")):
            try:
                raw = fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = fp.read_text(encoding="utf-8", errors="replace")




            blocks = _parse_essay_blocks(raw)

            stem = fp.stem
            mnum = re.match(r"^\s*(\d+(?:\.\d+)*)[^\w]?", stem)   # captures 3, 02, 2.3, 3.1.4 etc.
            num_prefix = mnum.group(1) if mnum else ""

            title = blocks.get("title") or stem
            display_title = f"{num_prefix} {title}".strip() if num_prefix else title

            slug = _slugify(title or stem)  # keep slug aligned with what users see

            title = blocks.get("title") or fp.stem
            slug = _slugify(title or fp.stem)
            essays.append({
                "id": slug,
                "slug": slug,
#                 "title": title,
                "title": display_title,
                "preview_md": blocks.get("preview", ""),
                "essay_md": blocks.get("essay", ""),
                "recap_md": blocks.get("recap", ""),
                "preview_html": render_md(blocks.get("preview", "")),
                "essay_html": render_md(blocks.get("essay", "")),
                "recap_html": render_md(blocks.get("recap", "")),
#                 "preview_html": markdown(
#                     blocks.get("preview", ""),
#                     extensions=["fenced_code", "tables", "toc"]
#                 ),
#                 "essay_html": markdown(
#                     blocks.get("essay", ""),
#                     extensions=["fenced_code", "tables", "toc"]
#                 ),
#                 "recap_html": markdown(
#                     blocks.get("recap", ""),
#                     extensions=["fenced_code", "tables", "toc"]
#                 ),

                "domain": domain_id,
                "domain_label": label,
                "category_key": cat["key"],
                "category_label": cat["label"],
                "file": fp.as_posix(),
                "updated_at": datetime.fromtimestamp(fp.stat().st_mtime).isoformat() if fp.exists() else None,
            })

    def _num_prefix_sort_key(title):
        m = re.match(r"^\s*(\d+(?:\.\d+)*)", title)
        if m:
            # convert "2.3.1" -> tuple of ints (2,3,1)
            return tuple(map(int, m.group(1).split(".")))
        return (9999,)

    def _num_tuple(s: str):
        m = re.match(r"^\s*(\d+(?:\.\d+)*)", s)
        if not m:
            return (9999,)  # push unnumbered to the end
        return tuple(int(p) for p in m.group(1).split("."))

    # Sort within category: numeric prefix → title (as tiebreaker)
    essays.sort(key=lambda e: (int(e["category_key"]), _num_tuple(e["title"]), e["title"]))

    cats_out = []
    for c in categories:
        count = sum(1 for e in essays if e["category_key"] == c["key"])
        cats_out.append({"key": c["key"], "label": c["label"], "count": count})
    return {"domain": domain_id, "label": label, "categories": cats_out, "essays": essays}

def _get_ch_payload(): return _scan_domain(CH_ROOT, "CH", "Church History", CH_CATEGORIES)
def _get_ap_payload(): return _scan_domain(AP_ROOT, "AP", "Apologetics", AP_CATEGORIES)

@app.get("/api/digests")
def api_digests():
    return jsonify({"digests": CACHE.get("digests", [])})

@app.get("/api/digest/<slug>")
def api_digest(slug):
    slug = (slug or "").lower().strip()
    hit = next((d for d in (CACHE.get("digests") or []) if (d.get("slug") or "").lower() == slug), None)
    if not hit:
        return jsonify({"error": "Not found"}), 404
    return jsonify(hit)

@app.get("/files/digests/<path:rel>")
def files_digests(rel):
    # serve only from Digests root; rel should be like 'AP/Foo - Bar.docx'
    safe = pathlib.Path(rel).as_posix()
    parts = safe.split("/")
    if len(parts) < 2 or parts[0] not in DIGEST_CATS:
        abort(404)
    cat = parts[0]
    filename = "/".join(parts[1:])
    return send_from_directory((DIGESTS_ROOT / cat), filename, as_attachment=False)

@app.get("/api/essays/ch")
def api_essays_ch(): return jsonify(_get_ch_payload())

@app.get("/api/essays/ap")
def api_essays_ap(): return jsonify(_get_ap_payload())

@app.get("/api/essay/<slug>")
def api_essay(slug):
    slug = slug.strip().lower()
    all_essays = _get_ch_payload()["essays"] + _get_ap_payload()["essays"]
    hit = next((e for e in all_essays if e["slug"] == slug), None)
    if not hit: return jsonify({"error": "Not found"}), 404
    return jsonify(hit)

CACHE["search"] = _load_json(DATA_DIR / "indices" / "search_index.json", [])

@app.get("/api/theologian_essay/<theo_id>")
def api_theologian_essay(theo_id):
    """
    Serve data/theologian-essays/{theo_id}.md as HTML.
    Reuses normalize_md + markdown renderer like /api/outline.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_:-]+", "", (theo_id or ""))
    md_path = (THEOLOGIAN_ESSAYS_DIR / f"{safe_id}.md").resolve()

    # Safety: must be inside THEOLOGIAN_ESSAYS_DIR and exist
    if THEOLOGIAN_ESSAYS_DIR not in md_path.parents or not md_path.exists():
        return jsonify({"html": ""})

    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return jsonify({"html": ""})

    body = normalize_md(text)
    html = render_md(body)

    return jsonify({"html": html})



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

@app.get("/api/work_summary/<work_id>")
def work_summary(work_id):
    """Serve pre-generated Markdown summaries as HTML."""
    summary_dir = DATA_DIR / "summaries" / "by_work"
    md_path = summary_dir / f"{work_id}.md"
    # also try slug form if files are named work_<id>.<slug>.md
    if not md_path.exists():
        matches = list(summary_dir.glob(f"{work_id}.*.md"))
        md_path = matches[0] if matches else None
    if not md_path or not md_path.exists():
        return jsonify({"html": "<div class='small'>Summary not found.</div>"}), 404

    text = md_path.read_text(encoding="utf-8")
    html = markdown(normalize_md(text), extensions=["fenced_code", "tables"])
    html = render_md(text)
    return jsonify({"html": html})


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
def api_search():
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify([])

    terms = [t for t in re.split(r"\s+", q) if t]
    pool = CACHE.get("search") or []

    hits = []
    for it in pool:
        if all(t in it.get("hay","") for t in terms):
            r = dict(it)
            r.pop("hay", None)
            if r.get("type") == "work" and r.get("id"):
                r["id"] = _canonicalize(r["id"])
            hits.append(r)

    # optional: keep global type ordering but not inner sorting
    type_order = {"theologian": 0, "work": 1, "topic": 2, "outline": 3, "essay": 4, "digest": 5}
    hits.sort(key=lambda x: type_order.get(x.get("type"), 9))

    # dedupe (same as before)
    seen, unique = set(), []
    for r in hits:
        key = (r.get("type"), r.get("id") if r.get("type") == "work" else r.get("slug") or r.get("title"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    # cap per type
    MAX_PER_TYPE = {
        "theologian": 10,
        "work": 15,
        "topic": 10,
        "outline": 10,
        "essay": 10,
        "digest": 10,
    }

    grouped = {}
    for r in unique:
        t = r.get("type")
        grouped.setdefault(t, []).append(r)

    limited = []
    for t in sorted(grouped.keys(), key=lambda x: type_order.get(x, 9)):
        limited.extend(grouped[t][:MAX_PER_TYPE.get(t, 10)])

    return jsonify(limited)


@app.post("/api/search/reload")
def api_search_reload():
    CACHE["search"] = _load_json(DATA_DIR / "indices" / "search_index.json", [])
    return jsonify({"ok": True, "count": len(CACHE["search"])})

# ---------- Markdown normalization ----------
def normalize_md(text: str) -> str:
    text = text.replace(" __", "__ ")
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
            topic_slug = cand.split("/")[-2]
            topic = [t for tid, t in TOPIC_MAP.items() if topic_slug == "-".join(t["slug"].split("-")[2:])][0]

            theo_slug = cand.split("/")[-1][:-3]
            theo_match = [th["full_name"] for thid, th in THEO_MAP.items() if th["slug"] == theo_slug] or ["Essay"]
            page_title_string = (f"{last_name_key(theo_match[0])} - {topic['title']}")


            text = md_path.read_text(encoding="utf-8")
            # NEW: parse front-matter and strip it before markdown render
            meta, body = _parse_frontmatter(text)
            body = normalize_md(body)
            html = render_md(body)
            return jsonify({"html": html, "meta": meta, "page_title_string": page_title_string})

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


#  lsof -ti tcp:5001 | xargs kill -9 && python app.py
