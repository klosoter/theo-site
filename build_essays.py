#!/usr/bin/env python3
"""
Build static JSON for Church History (CH) and Apologetics (AP).

Scans:
  ch-data/
    ├─ Ancient/*.txt
    ├─ Medieval/*.txt
    ├─ Reformation/*.txt
    └─ Modern/*.txt
  ap-data/ (or Ap-data/)
    ├─ ap-figures/*.txt
    ├─ ap-issues/*.txt
    └─ ap-cvt-src/
        ├─ Method Foundations/*.txt
        ├─ Interlocutors & Influences/*.txt
        └─ Debates & Controversies/*.txt

Each .txt file should contain labeled blocks (labels case-insensitive):
  TITLE:
  PREVIEW NOTES:  (or PREVIEW:)
  ESSAY:
  RECAP NOTES:    (or RECAP:)

Outputs (created if missing):
  public/data/ch.json
  public/data/ap.json
  public/data/essays_index.json

Usage:
  python scripts/build_essays.py
  python scripts/build_essays.py --root . --out public/data
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ---------- config ----------

CH_CATEGORIES = [
    {"key": "1", "label": "Ancient",      "dir": "Ancient"},
    {"key": "2", "label": "Medieval",     "dir": "Medieval"},
    {"key": "3", "label": "Reformation",  "dir": "Reformation"},
    {"key": "4", "label": "Modern",       "dir": "Modern"},
]

AP_CATEGORIES = [
    {"key": "1", "label": "Figures",                               "dir": os.path.join("ap-figures")},
    {"key": "2", "label": "Issues",                                "dir": os.path.join("ap-issues")},
    {"key": "3", "label": "Van Til — Method Foundations",          "dir": os.path.join("ap-cvt-src", "Method Foundations")},
    {"key": "4", "label": "Van Til — Interlocutors & Influences",  "dir": os.path.join("ap-cvt-src", "Interlocutors & Influences")},
    {"key": "5", "label": "Van Til — Debates & Controversies",     "dir": os.path.join("ap-cvt-src", "Debates & Controversies")},
]

# ---------- helpers ----------

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s

def read_text(fp: Path) -> str:
    try:
        return fp.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return fp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def file_mtime_iso(fp: Path) -> Optional[str]:
    try:
        ts = fp.stat().st_mtime
        return datetime.fromtimestamp(ts).isoformat()
    except Exception:
        return None

SECTION_MARKERS = [
    ("title",   re.compile(r"^\s*TITLE\s*:\s*$", re.I)),
    ("preview", re.compile(r"^\s*(PREVIEW\s*NOTES|PREVIEW)\s*:\s*$", re.I)),
    ("essay",   re.compile(r"^\s*ESSAY\s*:\s*$", re.I)),
    ("recap",   re.compile(r"^\s*(RECAP\s*NOTES|RECAP)\s*:\s*$", re.I)),
]

def parse_essay_blocks(txt: str) -> Dict[str, str]:
    """
    Parse labeled blocks from a .txt file. Returns keys:
      title, preview, essay, recap
    Missing sections become empty strings; if TITLE is missing,
    first non-empty line becomes title fallback.
    """
    lines = txt.replace("\r\n", "\n").split("\n")
    buckets: Dict[str, List[str]] = {"title": [], "preview": [], "essay": [], "recap": []}
    current: Optional[str] = None

    for line in lines:
        hit = next((k for (k, rx) in SECTION_MARKERS if rx.match(line)), None)
        if hit:
            current = hit
            continue
        if current:
            buckets[current].append(line)

    out = {}
    for k, arr in buckets.items():
        # trim leading/trailing blank lines
        while arr and not arr[0].strip():
            arr.pop(0)
        while arr and not arr[-1].strip():
            arr.pop()
        out[k] = "\n".join(arr).strip()

    if not out["title"]:
        first = next((ln.strip() for ln in lines if ln.strip()), "")
        out["title"] = first
    return out

def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )

def md_to_html(md: str) -> str:
    """
    Minimal Markdown-ish to HTML:
      - blank-line separated paragraphs
      - unordered lists for lines starting with '-' or '*'
      - HTML-escapes text
    This stays dependency-free and safe for static drop-in.
    """
    if not md:
        return ""
    lines = md.split("\n")

    out: List[str] = []
    in_list = False

    for line in lines:
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{html_escape(item)}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            if line.strip() == "":
                out.append("")  # preserve paragraph breaks
            else:
                out.append(f"<p>{html_escape(line)}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)

def ensure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)

# ---------- scanner ----------

def scan_domain(root: Path, domain_id: str, label: str, categories: List[Dict]) -> Dict:
    essays = []

    for cat in categories:
        cat_dir = Path(cat["dir"])
        abs_dir = root / cat_dir
        if not abs_dir.exists():
            # tolerate missing directories
            continue

        for fp in sorted(abs_dir.glob("*.txt")):
            raw = read_text(fp)
            sections = parse_essay_blocks(raw)
            title = sections.get("title") or fp.stem
            slug = slugify(title or fp.stem)

            essays.append({
                "id": slug,
                "slug": slug,
                "title": title or fp.stem,
                "preview_md": sections.get("preview", ""),
                "essay_md": sections.get("essay", ""),
                "recap_md": sections.get("recap", ""),
                "domain": domain_id,
                "domain_label": label,
                "category_key": cat["key"],
                "category_label": cat["label"],
                "folder": str(cat_dir),
                "file": str(fp.as_posix()),
                "updated_at": file_mtime_iso(fp),
            })

    # sort: category key asc, then title alpha
    essays.sort(key=lambda e: (int(e["category_key"]), e["title"]))

    # materialize simple HTML
    for e in essays:
        e["preview_html"] = md_to_html(e["preview_md"])
        e["essay_html"]   = md_to_html(e["essay_md"])
        e["recap_html"]   = md_to_html(e["recap_md"])

    cats_out = []
    for c in categories:
        count = sum(1 for e in essays if e["category_key"] == c["key"])
        cats_out.append({"key": c["key"], "label": c["label"], "count": count})

    return {"domain": domain_id, "label": label, "categories": cats_out, "essays": essays}

# ---------- main ----------

def resolve_root_dir(base: Path, *candidates: str) -> Path:
    """Return the first existing candidate under base; if none, return the first (for error visibility)."""
    for name in candidates:
        p = base / name
        if p.exists():
            return p
    # fallback to first; will error later if truly missing
    return base / candidates[0]

def build(root_dir: Path, out_dir: Path) -> None:
    # Accept both ap-data and Ap-data (user note)
    ap_root = resolve_root_dir(root_dir, "ap-data", "Ap-data")
    ch_root = resolve_root_dir(root_dir, "ch-data", "Ch-data")

    # Domain scans
    ch_payload = scan_domain(ch_root, "CH", "Church History", CH_CATEGORIES)
    ap_payload = scan_domain(ap_root, "AP", "Apologetics", AP_CATEGORIES)

    # Ensure output dir
    ensure_dir(out_dir)

    # Write files
    (out_dir / "ch.json").write_text(json.dumps(ch_payload, indent=2), encoding="utf-8")
    (out_dir / "ap.json").write_text(json.dumps(ap_payload, indent=2), encoding="utf-8")

    index_payload = {
        "ch": {"categories": ch_payload["categories"]},
        "ap": {"categories": ap_payload["categories"]},
    }
    (out_dir / "essays_index.json").write_text(json.dumps(index_payload, indent=2), encoding="utf-8")

    # Console summary
    print("✓ Wrote:")
    print(f"  - {out_dir / 'ch.json'}")
    print(f"  - {out_dir / 'ap.json'}")
    print(f"  - {out_dir / 'essays_index.json'}")

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Build CH/AP essay JSON from text sources.")
    parser.add_argument("--root", default=".", help="Project root containing ch-data/ and ap-data/")
    parser.add_argument("--out", default=os.path.join("public", "data"), help="Output directory for JSON")
    args = parser.parse_args(argv)

    root_dir = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()

    build(root_dir, out_dir)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
