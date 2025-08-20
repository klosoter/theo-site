#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reindex + ingest mapping-based key works (file shapes fixed to your project).

File shapes (as provided):
- data/works.json            -> list[Work]
- data/topics.json           -> list[Topic]
- data/theologians.json      -> list[Theologian]
- data/indices/by_work.json  -> dict[str work_id] = { ... }   (optional pre-existing)
- data/indices/by_topic.json -> dict (left untouched)
- data/indices/search_index.json -> list
- topic_mapping_updated.json -> dict[topic_title] = { generated: { wts_or_old_princeton_works, recent_works_discussions } }

This script:
- preserves topics[*].work_ids (outline-cited)
- adds topics[*].key_works = { wts_old_princeton: [...], recent: [...] }
- upserts theologians and works (stable SHA1 ids)
- sets works[wid].authors = [primary_author_theologian_id]
- links wid into theologian.key_work_ids
- writes indices: by_work.json, by_topic_keyworks.json, topic_work_edges.json, search_index.json
"""

import json, pathlib, re, hashlib, unicodedata
from collections import OrderedDict, defaultdict
from datetime import datetime

# ---------------- Paths ----------------
ROOT = pathlib.Path(".").resolve()
DATA_DIR = ROOT / "data"
INDICES_DIR = DATA_DIR / "indices"
TOPICS_JSON = DATA_DIR / "topics.json"
THEOLOGIANS_JSON = DATA_DIR / "theologians.json"
WORKS_JSON = DATA_DIR / "works.json"
BY_WORK_JSON = INDICES_DIR / "by_work.json"              # dict
BY_TOPIC_JSON = INDICES_DIR / "by_topic.json"            # dict (left as-is)
SEARCH_INDEX_JSON = INDICES_DIR / "search_index.json"    # list
TOPIC_MAPPING_JSON = ROOT / "topic_mapping_updated.json" # dict

# ---------------- Helpers ----------------
def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def _now_date():
    return datetime.now().strftime("%Y-%m-%d")

def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _collapse_spaced_initials(s: str) -> str:
    if not s: return s
    pat = re.compile(r"\b([A-Za-z])\.\s+([A-Za-z])\.")
    prev = None
    while s != prev:
        prev = s
        s = pat.sub(r"\1.\2.", s)
    return s

def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return _collapse_spaced_initials(_norm_space(s))

def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)

def _norm_title(title: str) -> str:
    s = unicodedata.normalize("NFKC", title or "")
    s = _norm_space(s)
    # trim common trailing paren-noise from mapping
    s = re.sub(r"\s*\((?:eds?\.|newer editions|english trans\.[^)]+|especially [^)]+)\)\s*$", "", s, flags=re.I)
    return s

def _sid(prefix: str, key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"

# Canonicalization (extend as you wish)
ALIASES = {
    "B. B. Warfield": "B.B. Warfield",
    "Kevin Vanhoozer": "Kevin J. Vanhoozer",
    "Richard B. Gaffin, Jr.": "Richard B. Gaffin Jr.",
    "Bruce L. McCormack": "Bruce McCormack",
}
def _canonical_name(n: str) -> str:
    n = _norm_name(n)
    return ALIASES.get(n, n)

# ---------------- Load current datasets (fixed shapes) ----------------
topics_list = _read(TOPICS_JSON, [])            # list
theologians_list = _read(THEOLOGIANS_JSON, [])  # list
works_list = _read(WORKS_JSON, [])              # list

by_work_existing = _read(BY_WORK_JSON, {})      # dict or empty
mapping = _read(TOPIC_MAPPING_JSON, {})         # dict

# Build id -> record maps for fast updates (we'll write back lists)
theologians = {t["id"]: t for t in theologians_list if isinstance(t, dict) and "id" in t}
works = {w["id"]: w for w in works_list if isinstance(w, dict) and "id" in w}
topics_by_id = {t["id"]: t for t in topics_list if "id" in t}
topics_by_title = {t["title"]: t for t in topics_list if "title" in t}

# Name -> theologian record
theologians_by_name = {t["full_name"]: t for t in theologians.values() if t.get("full_name")}

def get_or_create_theologian(full_name: str):
#     full_name = _canonical_name(full_name)
    if full_name in theologians_by_name:
        return theologians_by_name[full_name]
    tid = _sid("theo", _norm_name(full_name))
    rec = {
        "id": tid,
        "slug": _slugify(full_name),
        "name": full_name,
        "dates": None,
        "era_category": [],
        "traditions": [],
        "bio": "",
        "timeline": [],
        "key_work_ids": [],
        "wts_relevance": False,
        "created_at": _now_date(),
        "updated_at": _now_date(),
    }
    theologians[tid] = rec
    theologians_by_name[full_name] = rec
    return rec

def _work_key(author_id: str, title: str) -> str:
    return f"{author_id}||{_norm_title(title).lower()}"

# existing works keyed by (author, title)
works_by_key = {}
for w in works.values():
    a0 = (w.get("authors") or [None])[0]
    title = w.get("title") or ""
    if a0 and title:
        works_by_key[_work_key(a0, title)] = w

def upsert_work(primary_author_name: str, title: str, suffix: str, raw: str):
    theo = get_or_create_theologian(primary_author_name)
    norm_title = _norm_title(title)
    k = _work_key(theo["id"], norm_title)
    if k in works_by_key:
        w = works_by_key[k]
        # enrich notes slightly
        new_note = _norm_space(suffix or "")
        if new_note:
            existing = _norm_space(w.get("notes") or "")
            if new_note.lower() not in existing.lower():
                w["notes"] = (existing + ("; " if existing else "") + new_note)
        if raw and not w.get("raw_citation"):
            w["raw_citation"] = raw
        return w["id"]
    wid = _sid("work", f"{theo['id']}::{norm_title.lower()}")
    rec = {
        "id": wid,
        "slug": _slugify(norm_title),
        "title": norm_title,
        "authors": [theo["id"]],
        "year": None,
        "publisher": None,
        "type": "book",
        "tradition": [],
        "topics": [],
        "summary": None,
        "summary_status": "pending",
        "notes": _norm_space(suffix or ""),
        "identifiers": {"isbn": None, "doi": None},
        "raw_citation": raw or "",
        "created_at": _now_date(),
        "updated_at": _now_date(),
    }
    works[wid] = rec
    works_by_key[k] = rec
    # link on theologian
    kw = theologians[theo["id"]].setdefault("key_work_ids", [])
    if wid not in kw: kw.append(wid)
    return wid

def ensure_keyworks_block(topic_obj: dict):
    if "key_works" not in topic_obj:
        topic_obj["key_works"] = {"wts_old_princeton": [], "recent": []}
    else:
        topic_obj["key_works"].setdefault("wts_old_princeton", [])
        topic_obj["key_works"].setdefault("recent", [])

# ---------------- Ingest mapping into topics ----------------
for topic_title, payload in (mapping or {}).items():
    t = topics_by_title.get(topic_title)
    if not t:
        # Create minimal topic if mapping mentions a new one
        tid = _sid("top", topic_title.lower())
        t = {
            "id": tid,
            "slug": _slugify(topic_title),
            "title": topic_title,
            "category": None,
            "created_at": _now_date(),
            "updated_at": _now_date(),
            "work_ids": [],
        }
        topics_list.append(t)
        topics_by_id[tid] = t
        topics_by_title[topic_title] = t

    ensure_keyworks_block(t)

    gen = (payload or {}).get("generated") or {}
    for bucket_name, dest in [
        ("wts_or_old_princeton_works", "wts_old_princeton"),
        ("recent_works_discussions", "recent"),
    ]:
        ids = []
        for item in gen.get(bucket_name, []) or []:
            wid = upsert_work(
                primary_author_name=item.get("theologian") or "",
                title=item.get("title") or "",
                suffix=item.get("suffix") or "",
                raw=item.get("raw") or "",
            )
            ids.append(wid)
        # append de-duped preserving order
        current = t["key_works"][dest]
        t["key_works"][dest] = list(OrderedDict.fromkeys(current + ids))

# ---------------- Rebuild indices ----------------
# a) by_work.json (dict keyed by wid). Keep existing referenced_in if present.
by_work = {}
for wid, w in works.items():
    node = by_work_existing.get(wid, {}).copy()
    node["title"] = w.get("title")
    node["primary_author_theologian_id"] = (w.get("authors") or [None])[0]
    node["is_topic_keywork"] = any(
        wid in t.get("key_works", {}).get("wts_old_princeton", [])
        or wid in t.get("key_works", {}).get("recent", [])
        for t in topics_list
    )
    by_work[wid] = node

# b) by_topic_keyworks.json (badge counts per topic)
by_topic_keyworks = {}
for t in topics_list:
    kw = t.get("key_works", {})
    by_topic_keyworks[t["id"]] = {
        "wts_old_princeton_count": len(kw.get("wts_old_princeton", [])),
        "recent_count": len(kw.get("recent", [])),
        "outline_cited_count": len(t.get("work_ids") or []),
    }

# c) topic_work_edges.json (normalized triples, so UI can dedupe)
edges = []
# outline edges from topics[*].work_ids
for t in topics_list:
    for wid in t.get("work_ids") or []:
        edges.append({"topic_id": t["id"], "work_id": wid, "source": "outline"})
# outline edges from existing by_work.referenced_in, if any
for wid, meta in by_work_existing.items():
    for ref in meta.get("referenced_in", []) or []:
        edges.append({"topic_id": ref["topic_id"], "work_id": wid, "source": "outline"})
# mapping edges
for t in topics_list:
    for wid in t.get("key_works", {}).get("wts_old_princeton", []):
        edges.append({"topic_id": t["id"], "work_id": wid, "source": "wts"})
    for wid in t.get("key_works", {}).get("recent", []):
        edges.append({"topic_id": t["id"], "work_id": wid, "source": "recent"})

# d) search_index.json (list)
search_index = []
for theo in theologians.values():
    search_index.append({
        "type": "theologian",
        "name": theo.get("full_name"),
        "slug": theo.get("slug"),
        "eras": theo.get("era_category") or [],
        "traditions": theo.get("traditions") or [],
    })
for w in works.values():
    search_index.append({"type": "work", "title": w.get("title"), "id": w.get("id")})
for t in topics_list:
    search_index.append({"type": "topic", "title": t.get("title"), "slug": t.get("slug")})

# ---------------- Write back (preserve list shapes) ----------------
# lists
theologians_list = list(theologians.values())
works_list = list(works.values())

_write(THEOLOGIANS_JSON, theologians_list)
_write(WORKS_JSON, works_list)
_write(TOPICS_JSON, topics_list)

# indices
_write(BY_WORK_JSON, by_work)
_write(INDICES_DIR / "by_topic_keyworks.json", by_topic_keyworks)
_write(INDICES_DIR / "topic_work_edges.json", edges)
_write(SEARCH_INDEX_JSON, search_index)

print("✔ Reindex + ingest complete")
print("  • theologians.json, works.json, topics.json updated (lists)")
print("  • indices: by_work.json, by_topic_keyworks.json, topic_work_edges.json, search_index.json")
