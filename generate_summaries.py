#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summaries_generate.py — Adaptive summary generator for works (debug print version, no fallback).

Order of generation:
  - summary_input_ordered.json (top-5 per author → missing keyworks → remainder)

Inputs:
  data/indices/by_work.json
  data/work_canon_map.json
  summary_input_ordered.json

Outputs:
  data/summaries/by_work/work_<id>.<slug>.md

Features:
  - Skips files that already exist (resumable)
  - Prints per-item timing on write or skip
  - Prints raw OpenAI response object and message content (first 800 chars)
  - Adaptive context:
      * refs <= 5   → list concrete topics
      * 6..20       → top topics + categories
      * > 20        → compact usage profile by category
"""

from __future__ import annotations
import os, re, json, time, unicodedata
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import Counter
from openai import OpenAI

# ---------- Paths ----------
BY_WORK_PATH = Path("data/indices/by_work.json")
CANON_MAP_PATH = Path("data/work_canon_map.json")
# FEED_PATH = Path("summary_input_ordered.json")
FEED_PATH = Path("unique_all_works.json")
OUT_DIR = Path("data/summaries/by_work"); OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Model ----------
MODEL_TEXT = os.getenv("MODEL_TEXT", "gpt-5-mini")

from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- Prompt spec ----------
SYSTEM_SPEC = (
    "You are a precise, well-read theologian writing structured yet readable research notes for advanced students. "
    "Use Markdown with bold for clarity. Bullets and one level of sub-bullets are encouraged but not required. "
    "Produce exactly four sections in this order and nothing else:\n\n"
    "### TITLE\n"
    "### OUTLINE NOTES\n"
    "### DISTINCTIVES\n"
    "### KEY TERMS & USES\n\n"
    "Plain ASCII punctuation only. Keep it concise but complete, roughly 400-900 words total."
    "Stop thinking aloud. Output the four Markdown sections now."
)

USER_PROMPT_TEMPLATE = """This is a topic keywork or a high-priority theological work in our library.

Work: {title}
Author(s): {authors}
Associated theologian(s) or tradition (optional): {theologians}

You are generating structured, skimmable research notes. Aim for density and clarity over prose flourish. Use **bold** for emphasis where it helps the eye. Bullets and sub-bullets are welcome; short paragraphs are fine too.

{adaptive_context_block}

Guidance:

### OUTLINE NOTES
- **Setting or publication context:** time period, movement, theological milieu.
- **Central thesis or doctrinal problem.**
- **Core argument or structure:** feel free to use a few sub-bullets for major moves.
- **Figures, sources, interlocutors** engaged.
- **Doctrines treated** (e.g., revelation, covenant, Trinity, Christology).
- **Closing line** capturing the work's theological center of gravity.

### DISTINCTIVES
- **Unique emphases or formulations.**
- **Corrections or contrasts** to predecessors or rivals.
- **Conceptual or terminological innovations.**
- **Reception and influence** in Reformed and wider theology.
- **Enduring value** for study and teaching.

### KEY TERMS & USES
- 8–15 **key terms or phrases** with short explanations; sub-bullets allowed to clarify contrasts or relations.
- Conclude with 2–4 bullets on **how this work is used** across loci — definition source, polemic, exegetical model, or conceptual pivot.
"""

# ---------- Utils ----------
REQUIRED_MARKERS = ["### TITLE","### OUTLINE NOTES","### DISTINCTIVES","### KEY TERMS & USES"]

def slugify(s: str, maxlen: int = 90) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:maxlen] or "untitled"

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def load_alias_map(path: Path) -> Dict[str, str]:
    if not path.exists(): return {}
    rows = load_json(path)
    return {r["work_id"]: r["canonical_id"] for r in rows if "work_id" in r and "canonical_id" in r}

def resolve_canonical(wid: str, alias_to_canon: Dict[str,str]) -> str:
    seen = set(); cur = wid
    while cur in alias_to_canon:
        if cur in seen: break
        seen.add(cur); cur = alias_to_canon[cur]
    return cur

def parse_ref(markdown_path: str) -> Tuple[str,str,str]:
    p = Path(markdown_path); parts = p.parts
    try:
        i = parts.index("outlines")
        category = parts[i+1] if len(parts) > i+1 else "Unknown"
        topic_slug = parts[i+2] if len(parts) > i+2 else "unknown-topic"
        theologian_slug = (parts[i+3] if len(parts) > i+3 else "unknown.md").replace(".md","")
        return category, topic_slug, theologian_slug
    except ValueError:
        return "Unknown", "unknown-topic", "unknown"

def prettify_slug(s: str) -> str:
    t = s.replace("-", " ")
    t = re.sub(r"\b(of|and|the|vs|in|to|for|by)\b", lambda m: m.group(1).lower(), t, flags=re.I)
    return t.title().replace(" Vs ", " vs ").replace(" & ", " & ")

def ensure_ascii_rules(txt: str) -> str:
    if txt is None:
        return ""
    subs = {"\u2018":"'", "\u2019":"'", "\u201C":'"', "\u201D":'"', "\u2013":"-", "\u2014":"-"}
    for k,v in subs.items():
        txt = txt.replace(k, v)
    # keep parentheses intact; just compress whitespace
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return txt.strip()

def has_all_markers(t: str) -> bool:
    if not t or not t.strip():
        return False
    return all(m in t for m in REQUIRED_MARKERS)

def call_model(user_prompt: str):
    """
    Single attempt; no fallback. Returns (raw_response, content_str).
    """
    r = client.chat.completions.create(
        model=MODEL_TEXT,
        max_completion_tokens=6000,
        messages=[{"role":"system","content":SYSTEM_SPEC},
                  {"role":"user","content":user_prompt}],
    )
    content = (r.choices[0].message.content or "").strip()
    return r, content

# ---------- Merge works with canonical ids ----------
def merge_aliases(works: Dict[str, Any], alias_to_canon: Dict[str, str]) -> Dict[str, Any]:
    final = {wid: resolve_canonical(wid, alias_to_canon) for wid in works}
    merged: Dict[str, Any] = {}
    for wid, w in works.items():
        cid = final[wid]
        merged.setdefault(cid, {**w, "referenced_in": [], "authors": list(w.get("authors", []) or [])})
        merged[cid]["referenced_in"].extend(w.get("referenced_in", []) or [])
        if w.get("is_topic_keywork"): merged[cid]["is_topic_keywork"] = True
        if not merged[cid].get("title") and w.get("title"): merged[cid]["title"] = w["title"]
        have = {(a.get("id"), a.get("full_name") or a.get("slug")) for a in merged[cid]["authors"]}
        for a in (w.get("authors") or []):
            key = (a.get("id"), a.get("full_name") or a.get("slug"))
            if key not in have:
                merged[cid]["authors"].append(a); have.add(key)
    # de-dup references
    for cid in list(merged):
        seen = set(); dedup = []
        for r in merged[cid]["referenced_in"]:
            key = (r.get("outline_id"), r.get("markdown_path"))
            if key not in seen:
                seen.add(key); dedup.append(r)
        merged[cid]["referenced_in"] = dedup
    return merged

# ---------- Context builder (adaptive) ----------
def build_adaptive_context(work_id: str, work_obj: Dict[str,Any]) -> Dict[str, Any]:
    title = (work_obj.get("title") or "").strip() or f"Work {work_id}"
    authors = [a.get("full_name") or a.get("slug") for a in work_obj.get("authors", []) if a]
    refs = work_obj.get("referenced_in", []) or []

    topics, cats, theos = [], [], []
    for r in refs:
        cat, topic_slug, theo = parse_ref(r.get("markdown_path",""))
        topics.append(topic_slug); cats.append(cat); theos.append(theo)

    topic_counts = Counter(topics); cat_counts = Counter(cats)
    distinct_topics = len(set(t for t in topics if t)); refs_count = len(refs)

    def top_items(counter: Counter, k: int) -> List[str]:
        return [f"{prettify_slug(name)} ({cnt})" for name, cnt in counter.most_common(k)
                if name and name not in {"unknown-topic","Unknown"}]

    if refs_count <= 5:
        shown_topics = [prettify_slug(t) for t in dict.fromkeys(topics) if t and t != "unknown-topic"]
        adaptive = "**Topics cited here:** " + ", ".join(shown_topics) + "." if shown_topics else "**Usage:** cited a small number of times across site outlines."
    elif refs_count <= 20:
        bits = []
        tt = top_items(topic_counts, 8); tc = top_items(cat_counts, 5)
        if tt: bits.append("**Most common topics:** " + ", ".join(tt) + ".")
        if tc: bits.append("**Categories:** " + ", ".join(tc) + ".")
        adaptive = "\n".join(bits) if bits else "**Usage profile:** moderate dispersion across topics."
    else:
        tc = top_items(cat_counts, 6)
        adaptive = "**Usage profile:** widely cited across the site; treat this summary as doctrinal and synthetic rather than topic-specific. " \
                   + ("Top categories: " + ", ".join(tc) + "." if tc else "")

    return {
        "title": title,
        "authors_joined": ", ".join(a for a in authors if a) or "Unknown",
        "theologians_hint": "—",
        "refs_count": refs_count,
        "distinct_topics": distinct_topics,
        "adaptive_block": adaptive
    }

def make_user_prompt(ctx: Dict[str,Any]) -> str:
    adaptive = f"**Site usage:** {ctx['refs_count']} references spanning {ctx['distinct_topics']} distinct topics.\n{ctx['adaptive_block']}\n"
    return USER_PROMPT_TEMPLATE.format(
        title=ctx["title"],
        authors=ctx["authors_joined"],
        theologians=ctx["theologians_hint"],
        adaptive_context_block=adaptive
    )

# ---------- IO ----------
def write_markdown(work_id: str, title: str, content: str) -> Path:
    out = OUT_DIR / f"{work_id}.{slugify(title)}.md"
    if not content.strip():
        diag = (
            "### TITLE\n"
            "Generation failed\n\n"
            "### OUTLINE NOTES\n"
            "No valid content returned from the model.\n"
            "### DISTINCTIVES\n"
            "- Stub written to avoid 0-byte file.\n"
            "### KEY TERMS & USES\n"
            "- Regenerate later; check model access and API logs."
        )
        out.write_text(diag, encoding="utf-8")
    else:
        out.write_text(content, encoding="utf-8")
    return out

# ---------- Main ----------
def main():
    if not BY_WORK_PATH.exists() or not CANON_MAP_PATH.exists() or not FEED_PATH.exists():
        raise SystemExit("Missing one or more inputs: data/indices/by_work.json, data/work_canon_map.json, summary_input_ordered.json")

    t_start = time.perf_counter()
    works_raw = load_json(BY_WORK_PATH)
    alias_to_canon = load_alias_map(CANON_MAP_PATH)
    works = merge_aliases(works_raw, alias_to_canon)
    feed = load_json(FEED_PATH)   # [{work_id,...}, ...]



    generated = skipped = 0
    for item in feed:
        wid = item["work_id"]
        w = works.get(wid)
        if not w:
            print(f"[SKIP] {wid} missing after canonical merge")
            skipped += 1
            continue

        out_path = OUT_DIR / f"{wid}.{slugify((w.get('title') or 'work'))}.md"
        if out_path.exists():
            print(f"[SKIP] {out_path.name} ({out_path.stat().st_size} bytes) in 0.00s")
            skipped += 1
            continue

        t0 = time.perf_counter()
        ctx = build_adaptive_context(wid, w)
        print(ctx["authors_joined"])
        user_prompt = make_user_prompt(ctx)

        try:
            raw_response, raw_content = call_model(user_prompt)
        except Exception as e:
            raw_response, raw_content = None, ""
            print(f"[ERR ] {wid} API error: {e}")

        # --- Debug prints ---
        if raw_response is not None:
            # Raw response object (repr) — can be large, but helpful for diagnosing
            print("[DBG] Raw OpenAI response object:")

        else:
            print("[DBG] Raw OpenAI response object: None (API exception)")

        # Message content (first 800 chars)
        safe_preview = ensure_ascii_rules(raw_content)[:80].replace("\n", "\\n")
        print(f"[DBG] Message content preview (<=800 chars): {safe_preview}")

        # Sanitize and validate
        md = ensure_ascii_rules(raw_content)
        ok_markers = has_all_markers(md)

        out_file = write_markdown(wid, ctx["title"], md if ok_markers else "")
        dt = time.perf_counter() - t0
        size = out_file.stat().st_size
        status = "OK" if ok_markers else "STUB"
        print(f"[{status}] {out_file.name} ({size} bytes) via {MODEL_TEXT} in {dt:.2f}s")

        generated += 1 if ok_markers else 0

    total_dt = time.perf_counter() - t_start
    print(f"[DONE] generated={generated} skipped={skipped} total={generated+skipped} time={total_dt:.2f}s")

if __name__ == "__main__":
    main()
