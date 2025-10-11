# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# authors_topN_works_sorted.py — Top N works per author, with authors sorted by:
#   1) author_distinct_topics (desc) — union of topic_ids across that author's works
#   2) author_keyworks_count  (desc) — count of unique keywork titles for that author
#   3) author_name (asc)
#
# Inputs:
#   /data/indices/by_work.json
#   /data/work_canon_map.json
#
# Outputs:
#   authors_topN_list.json   # ordered array of authors with their top-N works
#   authors_topN.csv         # csv in the same author order
#   unique_topN_works.json   # flattened, deduped list of selected works in author order
#
# Change TOP_N below to adjust per-author cap.
# """
#
# from __future__ import annotations
# import json, csv
# from pathlib import Path
# from typing import Dict, Any, List, Tuple, Set
# from collections import defaultdict
#
# BY_WORK_PATH = Path("data/indices/by_work.json")
# CANON_MAP_PATH = Path("data/work_canon_map.json")
# TOP_N = 5
#
# # ---------- helpers ----------
# def parse_ref_path(markdown_path: str) -> Tuple[str, str, str]:
#     p = Path(markdown_path)
#     parts = p.parts
#     try:
#         i = parts.index("outlines")
#         category = parts[i+1] if len(parts) > i+1 else "Unknown"
#         topic_slug = parts[i+2] if len(parts) > i+2 else "unknown-topic"
#         theologian = (parts[i+3] if len(parts) > i+3 else "unknown.md").replace(".md", "")
#         return category, topic_slug, theologian
#     except ValueError:
#         return "Unknown", "unknown-topic", "unknown"
#
# def to_bool(x: Any) -> bool:
#     return bool(x) and str(x).lower() not in {"false", "0", ""}
#
# def load_alias_map(path: Path) -> Dict[str, str]:
#     if not path.exists():
#         return {}
#     data = json.loads(path.read_text(encoding="utf-8"))
#     return {row["work_id"]: row["canonical_id"] for row in data if "work_id" in row and "canonical_id" in row}
#
# def resolve_canonical(wid: str, alias_to_canon: Dict[str, str]) -> str:
#     seen = set()
#     cur = wid
#     while cur in alias_to_canon:
#         if cur in seen:  # cycle guard
#             break
#         seen.add(cur)
#         cur = alias_to_canon[cur]
#     return cur
#
# def merge_aliases(works: Dict[str, Any], alias_to_canon: Dict[str, str]) -> Dict[str, Any]:
#     final_of = {wid: resolve_canonical(wid, alias_to_canon) for wid in works.keys()}
#     merged: Dict[str, Any] = {}
#     # seed canonical records
#     for wid, w in works.items():
#         cid = final_of[wid]
#         if cid not in merged:
#             merged[cid] = {k: v for k, v in works.get(cid, w).items()}
#             merged[cid]["referenced_in"] = list(merged[cid].get("referenced_in", []) or [])
#             merged[cid]["authors"] = list(merged[cid].get("authors", []) or [])
#     # absorb
#     for wid, w in works.items():
#         cid = final_of[wid]
#         merged[cid]["referenced_in"].extend(w.get("referenced_in", []) or [])
#         # authors union by (id,name)
#         existing = {(a.get("id"), a.get("full_name") or a.get("slug")) for a in merged[cid].get("authors", [])}
#         for a in (w.get("authors", []) or []):
#             key = (a.get("id"), a.get("full_name") or a.get("slug"))
#             if key not in existing:
#                 merged[cid]["authors"].append(a)
#                 existing.add(key)
#         # keywork OR
#         if to_bool(w.get("is_topic_keywork")):
#             merged[cid]["is_topic_keywork"] = True
#         # keep a title if missing
#         if not merged[cid].get("title") and w.get("title"):
#             merged[cid]["title"] = w["title"]
#     # de-dup references
#     for cid, w in merged.items():
#         seen_refs = set(); dedup = []
#         for r in w.get("referenced_in", []) or []:
#             key = (r.get("outline_id"), r.get("markdown_path"))
#             if key not in seen_refs:
#                 seen_refs.add(key); dedup.append(r)
#         w["referenced_in"] = dedup
#     return merged
#
# def compute_work_stats(work_id: str, w: Dict[str, Any]) -> Dict[str, Any]:
#     refs = w.get("referenced_in", []) or []
#     topic_ids: Set[str] = set()
#     categories: Set[str] = set()
#     for r in refs:
#         tid = r.get("topic_id")
#         if tid: topic_ids.add(tid)
#         cat, _, _ = parse_ref_path(r.get("markdown_path", ""))
#         if cat: categories.add(cat)
#     # author keys (prefer theologian id; fallback to name)
#     author_ids: List[str] = []
#     author_names: List[str] = []
#     for a in (w.get("authors") or []):
#         aid = a.get("id") or ""
#         name = a.get("full_name") or a.get("slug") or "Unknown"
#         author_ids.append(aid or name)
#         author_names.append(name)
#     if not author_ids:
#         author_ids = ["unknown"]; author_names = ["Unknown"]
#     return {
#         "work_id": work_id,
#         "title": (w.get("title") or "").strip() or f"Work {work_id}",
#         "authors_list": list(dict.fromkeys(author_names)),  # preserve order, dedupe
#         "author_keys": list(dict.fromkeys(author_ids)),
#         "is_topic_keywork": to_bool(w.get("is_topic_keywork")),
#         "refs_count": len(refs),
#         "distinct_topics": len(topic_ids),
#         "topic_ids": list(topic_ids),
#         "categories": sorted(categories),
#     }
#
# # ---------- main ----------
# def main():
#     if not BY_WORK_PATH.exists():
#         raise SystemExit(f"Missing: {BY_WORK_PATH}")
#
#     works_raw = json.loads(BY_WORK_PATH.read_text(encoding="utf-8"))
#     alias_to_canon = load_alias_map(CANON_MAP_PATH)
#     merged = merge_aliases(works_raw, alias_to_canon)
#     stats = {wid: compute_work_stats(wid, w) for wid, w in merged.items()}
#
#     # Group works by author, gather author-level metrics
#     by_author: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
#         "author_id": "",
#         "author_name": "",
#         "works": [],
#         "author_topic_ids": set(),
#         "author_keywork_ids": set(),
#     })
#
#     for wid, s in stats.items():
#         for ak in s["author_keys"]:
#             entry = by_author[ak]
#             if not entry["author_id"]:
#                 entry["author_id"] = ak if ak != "unknown" else ""
#             if not entry["author_name"]:
#                 entry["author_name"] = s["authors_list"][0] if s["authors_list"] else "Unknown"
#             entry["works"].append(s)
#             entry["author_topic_ids"].update(s["topic_ids"])
#             if s["is_topic_keywork"]:
#                 entry["author_keywork_ids"].add(wid)
#
#     # Rank each author's works
#     for entry in by_author.values():
#         entry["works"].sort(key=lambda x: (-x["distinct_topics"], -x["refs_count"], x["title"].lower()))
#         entry["count_available"] = len(entry["works"])
#         entry["count_selected"] = min(TOP_N, entry["count_available"])
#         entry["author_distinct_topics"] = len(entry["author_topic_ids"])
#         entry["author_keyworks_count"] = len(entry["author_keywork_ids"])
#
#     # Sort authors by: distinct topics desc, keyworks count desc, name asc
#     authors_sorted = sorted(
#         by_author.values(),
#         key=lambda e: (-e["author_distinct_topics"], -e["author_keyworks_count"], e["author_name"].lower())
#     )
#
#     # Build topN selections in that author order
#     authors_topN_list: List[Dict[str, Any]] = []
#     unique_selected: Dict[str, Dict[str, Any]] = {}
#     for entry in authors_sorted:
#         chosen = entry["works"][:TOP_N]
#         authors_topN_list.append({
#             "author_id": entry["author_id"],
#             "author_name": entry["author_name"],
#             "author_distinct_topics": entry["author_distinct_topics"],
#             "author_keyworks_count": entry["author_keyworks_count"],
#             "count_available": entry["count_available"],
#             "count_selected": len(chosen),
#             "works": chosen,
#         })
#         for w in chosen:
#             unique_selected[w["work_id"]] = w  # dedupe across co-authorships
#
#     # Write outputs
#     Path("authors_topN_list.json").write_text(
#         json.dumps(authors_topN_list, ensure_ascii=False, indent=2), encoding="utf-8"
#     )
#     print("[OK] wrote authors_topN_list.json")
#
#     with Path("authors_topN.csv").open("w", newline="", encoding="utf-8") as f:
#         wcsv = csv.writer(f)
#         wcsv.writerow([
#             "author_name","author_id","author_distinct_topics","author_keyworks_count",
#             "rank","work_id","title","distinct_topics","refs_count","is_topic_keywork","categories"
#         ])
#         for a in authors_topN_list:
#             for idx, s in enumerate(a["works"], start=1):
#                 wcsv.writerow([
#                     a["author_name"], a["author_id"], a["author_distinct_topics"], a["author_keyworks_count"],
#                     idx, s["work_id"], s["title"], s["distinct_topics"], s["refs_count"],
#                     int(s["is_topic_keywork"]), ";".join(s["categories"]),
#                 ])
#     print("[OK] wrote authors_topN.csv")
#
#     Path("unique_topN_works.json").write_text(
#         json.dumps(list(unique_selected.values()), ensure_ascii=False, indent=2), encoding="utf-8"
#     )
#     print("[OK] wrote unique_topN_works.json")
#
# if __name__ == "__main__":
#     main()
#
#
#


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
authors_topN_works_sorted.py — Top N works per author, with authors sorted by:
  1) author_distinct_topics (desc) — union of topic_ids across that author's works
  2) author_keyworks_count  (desc) — count of unique keywork titles for that author
  3) author_name (asc)

PLUS: "all-works" ordering per author:
  - First the Top N (as above),
  - Then the remainder sorted by: refs_count (desc), is_topic_keywork (True first), title (asc).

Inputs:
  /data/indices/by_work.json
  /data/work_canon_map.json

Outputs:
  authors_topN_list.json      # original (per-author, only top N)
  authors_topN.csv            # original CSV in same author order
  unique_topN_works.json      # original flattened, deduped list of selected top-N works in author order

  authors_all_works_list.json # NEW: per-author, ALL works (Top N first, then remainder ordering)
  unique_all_works.json       # NEW: flattened, deduped list of ALL works in the same ordering

Change TOP_N below to adjust the Top-N cap.
"""

from __future__ import annotations
import json, csv
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from collections import defaultdict

BY_WORK_PATH = Path("data/indices/by_work.json")
CANON_MAP_PATH = Path("data/work_canon_map.json")
TOP_N = 5

# ---------- helpers ----------
def parse_ref_path(markdown_path: str) -> Tuple[str, str, str]:
    p = Path(markdown_path)
    parts = p.parts
    try:
        i = parts.index("outlines")
        category = parts[i+1] if len(parts) > i+1 else "Unknown"
        topic_slug = parts[i+2] if len(parts) > i+2 else "unknown-topic"
        theologian = (parts[i+3] if len(parts) > i+3 else "unknown.md").replace(".md", "")
        return category, topic_slug, theologian
    except ValueError:
        return "Unknown", "unknown-topic", "unknown"

def to_bool(x: Any) -> bool:
    return bool(x) and str(x).lower() not in {"false", "0", ""}

def load_alias_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["work_id"]: row["canonical_id"] for row in data if "work_id" in row and "canonical_id" in row}

def resolve_canonical(wid: str, alias_to_canon: Dict[str, str]) -> str:
    seen = set()
    cur = wid
    while cur in alias_to_canon:
        if cur in seen:  # cycle guard
            break
        seen.add(cur)
        cur = alias_to_canon[cur]
    return cur

def merge_aliases(works: Dict[str, Any], alias_to_canon: Dict[str, str]) -> Dict[str, Any]:
    final_of = {wid: resolve_canonical(wid, alias_to_canon) for wid in works.keys()}
    merged: Dict[str, Any] = {}
    # seed canonical records
    for wid, w in works.items():
        cid = final_of[wid]
        if cid not in merged:
            merged[cid] = {k: v for k, v in works.get(cid, w).items()}
            merged[cid]["referenced_in"] = list(merged[cid].get("referenced_in", []) or [])
            merged[cid]["authors"] = list(merged[cid].get("authors", []) or [])
    # absorb
    for wid, w in works.items():
        cid = final_of[wid]
        merged[cid]["referenced_in"].extend(w.get("referenced_in", []) or [])
        # authors union by (id,name)
        existing = {(a.get("id"), a.get("full_name") or a.get("slug")) for a in merged[cid].get("authors", [])}
        for a in (w.get("authors", []) or []):
            key = (a.get("id"), a.get("full_name") or a.get("slug"))
            if key not in existing:
                merged[cid]["authors"].append(a)
                existing.add(key)
        # keywork OR
        if to_bool(w.get("is_topic_keywork")):
            merged[cid]["is_topic_keywork"] = True
        # keep a title if missing
        if not merged[cid].get("title") and w.get("title"):
            merged[cid]["title"] = w["title"]
    # de-dup references
    for cid, w in merged.items():
        seen_refs = set(); dedup = []
        for r in w.get("referenced_in", []) or []:
            key = (r.get("outline_id"), r.get("markdown_path"))
            if key not in seen_refs:
                seen_refs.add(key); dedup.append(r)
        w["referenced_in"] = dedup
    return merged

def compute_work_stats(work_id: str, w: Dict[str, Any]) -> Dict[str, Any]:
    refs = w.get("referenced_in", []) or []
    topic_ids: Set[str] = set()
    categories: Set[str] = set()
    for r in refs:
        tid = r.get("topic_id")
        if tid: topic_ids.add(tid)
        cat, _, _ = parse_ref_path(r.get("markdown_path", ""))
        if cat: categories.add(cat)
    # author keys (prefer theologian id; fallback to name)
    author_ids: List[str] = []
    author_names: List[str] = []
    for a in (w.get("authors") or []):
        aid = a.get("id") or ""
        name = a.get("full_name") or a.get("slug") or "Unknown"
        author_ids.append(aid or name)
        author_names.append(name)
    if not author_ids:
        author_ids = ["unknown"]; author_names = ["Unknown"]
    return {
        "work_id": work_id,
        "title": (w.get("title") or "").strip() or f"Work {work_id}",
        "authors_list": list(dict.fromkeys(author_names)),  # preserve order, dedupe
        "author_keys": list(dict.fromkeys(author_ids)),
        "is_topic_keywork": to_bool(w.get("is_topic_keywork")),
        "refs_count": len(refs),
        "distinct_topics": len(topic_ids),
        "topic_ids": list(topic_ids),
        "categories": sorted(categories),
    }

# ---------- main ----------
def main():
    if not BY_WORK_PATH.exists():
        raise SystemExit(f"Missing: {BY_WORK_PATH}")

    works_raw = json.loads(BY_WORK_PATH.read_text(encoding="utf-8"))
    alias_to_canon = load_alias_map(CANON_MAP_PATH)
    merged = merge_aliases(works_raw, alias_to_canon)
    stats = {wid: compute_work_stats(wid, w) for wid, w in merged.items()}

    # Group works by author, gather author-level metrics
    by_author: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "author_id": "",
        "author_name": "",
        "works": [],
        "author_topic_ids": set(),
        "author_keywork_ids": set(),
    })

    for wid, s in stats.items():
        for ak in s["author_keys"]:
            entry = by_author[ak]
            if not entry["author_id"]:
                entry["author_id"] = ak if ak != "unknown" else ""
            if not entry["author_name"]:
                entry["author_name"] = s["authors_list"][0] if s["authors_list"] else "Unknown"
            entry["works"].append(s)
            entry["author_topic_ids"].update(s["topic_ids"])
            if s["is_topic_keywork"]:
                entry["author_keywork_ids"].add(wid)

    # Rank each author's works (primary/top-N ranking)
    for entry in by_author.values():
        entry["works"].sort(key=lambda x: (-x["distinct_topics"], -x["refs_count"], x["title"].lower()))
        entry["count_available"] = len(entry["works"])
        entry["count_selected"] = min(TOP_N, entry["count_available"])
        entry["author_distinct_topics"] = len(entry["author_topic_ids"])
        entry["author_keyworks_count"] = len(entry["author_keywork_ids"])

    # Sort authors by: distinct topics desc, keyworks count desc, name asc
    authors_sorted = sorted(
        by_author.values(),
        key=lambda e: (-e["author_distinct_topics"], -e["author_keyworks_count"], e["author_name"].lower())
    )

    # Build topN selections in that author order (existing output)
    authors_topN_list: List[Dict[str, Any]] = []
    unique_selected_topN: Dict[str, Dict[str, Any]] = {}
    for entry in authors_sorted:
        chosen = entry["works"][:TOP_N]
        authors_topN_list.append({
            "author_id": entry["author_id"],
            "author_name": entry["author_name"],
            "author_distinct_topics": entry["author_distinct_topics"],
            "author_keyworks_count": entry["author_keyworks_count"],
            "count_available": entry["count_available"],
            "count_selected": len(chosen),
            "works": chosen,
        })
        for w in chosen:
            unique_selected_topN[w["work_id"]] = w  # dedupe across co-authorships

    # NEW: Build ALL-works lists with "topN first, then remainder by refs+keywork+title"
    authors_all_works_list: List[Dict[str, Any]] = []
    unique_selected_all: Dict[str, Dict[str, Any]] = {}
    for entry in authors_sorted:
        topN = entry["works"][:TOP_N]
        remainder = entry["works"][TOP_N:]
        remainder.sort(key=lambda x: (-x["refs_count"], -int(x["is_topic_keywork"]), x["title"].lower()))
        ordered_all = topN + remainder

        authors_all_works_list.append({
            "author_id": entry["author_id"],
            "author_name": entry["author_name"],
            "author_distinct_topics": entry["author_distinct_topics"],
            "author_keyworks_count": entry["author_keyworks_count"],
            "count_available": entry["count_available"],
            "count_selected": len(ordered_all),  # equals count_available
            "works": ordered_all,
        })

        for w in ordered_all:
            # retain first appearance across authors (stable by author order then top/remainder block)
            if w["work_id"] not in unique_selected_all:
                unique_selected_all[w["work_id"]] = w

    # Write outputs (originals)
    Path("authors_topN_list.json").write_text(
        json.dumps(authors_topN_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[OK] wrote authors_topN_list.json")

    with Path("authors_topN.csv").open("w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow([
            "author_name","author_id","author_distinct_topics","author_keyworks_count",
            "rank","work_id","title","distinct_topics","refs_count","is_topic_keywork","categories"
        ])
        for a in authors_topN_list:
            for idx, s in enumerate(a["works"], start=1):
                wcsv.writerow([
                    a["author_name"], a["author_id"], a["author_distinct_topics"], a["author_keyworks_count"],
                    idx, s["work_id"], s["title"], s["distinct_topics"], s["refs_count"],
                    int(s["is_topic_keywork"]), ";".join(s["categories"]),
                ])
    print("[OK] wrote authors_topN.csv")

    Path("unique_topN_works.json").write_text(
        json.dumps(list(unique_selected_topN.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[OK] wrote unique_topN_works.json")

    # Write NEW outputs
    Path("authors_all_works_list.json").write_text(
        json.dumps(authors_all_works_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[OK] wrote authors_all_works_list.json")

    Path("unique_all_works.json").write_text(
        json.dumps(list(unique_selected_all.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[OK] wrote unique_all_works.json")

if __name__ == "__main__":
    main()
