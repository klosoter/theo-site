#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hydrate ONLY indices/by_work.json from topic_mapping_updated.json + topics.json.

- Reads (does not modify): data/topics.json, data/works.json, data/theologians.json
- Reads & updates:         data/indices/by_work.json
- Reads:                   topic_mapping_updated.json

What it adds to by_work[work_id]:
  • reference / suffix (mapping "suffix")
  • primary_author_theologian_id (from mapping "theologian", if resolvable)
  • authors[] (primary + names parsed from suffix; link to theologians when possible)
  • is_topic_keywork = True when work_id is listed in a topic's key_works

Idempotent: safe to re-run.
"""

import os, json, pathlib, re
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()
IDX_DIR  = DATA_DIR / "indices"

TOPICS_JSON  = DATA_DIR / "topics.json"
WORKS_JSON   = DATA_DIR / "works.json"
THEOS_JSON   = DATA_DIR / "theologians.json"
BY_WORK_JSON = IDX_DIR  / "by_work.json"
MAPPING_JSON = ROOT / "topic_mapping_updated.json"  # adjust if stored elsewhere

# ---------- io helpers ----------
def load(path, default):
    try:
        with path.open("r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        return default

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ---------- tiny normalization ----------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()) \
            .replace("“", '"').replace("”", '"').replace("’", "'")

def parse_names_from_suffix(s):
    """
    Extract human names from suffix like:
      "and Scott R. Swain", "& Fred Sanders (eds.)",
      "Michael Allen and Scott R. Swain (eds.)"
    """
    s = s or ""
    s = re.sub(r"\(eds?\.\)|editors?|ed\.", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*(and|&|with)\s+", "", s, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:and|&)\s+|,\s*", s)
    out = []
    for p in parts:
        p = norm(p)
        if p and re.search(r"[A-Za-z]", p):
            out.append(p)
    return out

def build_theo_indexes(theologians):
    by_id, by_name = {}, {}
    for t in theologians:
        if not isinstance(t, dict): continue
        if "id" in t: by_id[t["id"]] = t
        nm = t.get("full_name") or t.get("name")
        if nm: by_name[norm(nm)] = t
    return by_id, by_name

# ---------- load data ----------
topics      = load(TOPICS_JSON, [])
works       = load(WORKS_JSON, [])
theologians = load(THEOS_JSON, [])
by_work     = load(BY_WORK_JSON, {})
mapping     = load(MAPPING_JSON, {})

theos_by_id, theos_by_name = build_theo_indexes(theologians)
works_by_id = {w["id"]: w for w in works if isinstance(w, dict) and "id" in w}
topics_by_id = {t["id"]: t for t in topics if isinstance(t, dict) and "id" in t}
topics_by_title = {norm(t.get("title") or ""): t for t in topics}

# ---------- index mapping rows by (topic_title, work_title) & by title ----------
map_by_topic_and_title = defaultdict(list)  # (topic, title) -> [rows]
map_by_title_only      = defaultdict(list)  # title -> [rows]

for topic_title, payload in (mapping or {}).items():
    gen = (payload or {}).get("generated") or {}
    for bucket in ("wts_or_old_princeton_works", "recent_works_discussions"):
        for item in gen.get(bucket, []) or []:
            title  = norm(item.get("title"))
            theo   = norm(item.get("theologian"))
            suffix = norm(item.get("suffix"))
            if not title: continue
            row = {"title": title, "theologian": theo, "suffix": suffix}
            map_by_topic_and_title[(norm(topic_title), title)].append(row)
            map_by_title_only[title].append(row)

def pick_mapping_row(topic_title: str, work_title: str, prefer_author_name: str | None):
    """try (topic, title) exact; prefer row with author match; else title-only with suffix if possible"""
    topic_title_n = norm(topic_title)
    work_title_n  = norm(work_title)
    cand = map_by_topic_and_title.get((topic_title_n, work_title_n)) or []
    if prefer_author_name:
        nm = norm(prefer_author_name)
        for r in cand:
            if norm(r["theologian"]) == nm:
                return r
    if cand:
        cand = sorted(cand, key=lambda r: 0 if r["suffix"] else 1)
        return cand[0]
    cand = map_by_title_only.get(work_title_n) or []
    if prefer_author_name:
        nm = norm(prefer_author_name)
        for r in cand:
            if norm(r["theologian"]) == nm:
                return r
    if cand:
        cand = sorted(cand, key=lambda r: 0 if r["suffix"] else 1)
        return cand[0]
    return None

# ---------- collect all key work ids from topics ----------
keywork_ids = set()
for t in topics:
    kw = (t or {}).get("key_works") or {}
    for wid in (kw.get("wts_old_princeton") or []): keywork_ids.add(wid)
    for wid in (kw.get("recent") or []):            keywork_ids.add(wid)

# ---------- hydrate by_work ----------
touched = 0
with_suffix = 0

for wid in sorted(keywork_ids):
    node = by_work.setdefault(wid, {"id": wid})
    live = works_by_id.get(wid, {})
    # prefer title already present in by_work; fallback to works.json
    work_title = node.get("title") or live.get("title") or ""
    work_title = norm(work_title)

    # figure the topic title(s) where this wid appears (try all until we find a mapping row)
    topic_titles = []
    for t in topics:
        kw = (t or {}).get("key_works") or {}
        if wid in (kw.get("wts_old_princeton") or []) or wid in (kw.get("recent") or []):
            topic_titles.append(t.get("title") or t.get("name") or "")

    # author preference based on current data (if any)
    prefer_author_name = None
    if node.get("primary_author_theologian_id") and node["primary_author_theologian_id"] in theos_by_id:
        prefer_author_name = theos_by_id[node["primary_author_theologian_id"]]["full_name"]

    mp = None
    for tt in topic_titles:
        mp = pick_mapping_row(tt, work_title, prefer_author_name)
        if mp: break
    if not mp:
        # last resort: title-only
        mp = pick_mapping_row("", work_title, prefer_author_name)
    if not mp:
        continue  # nothing to add for this wid

    touched += 1

    # write suffix/reference
    if mp["suffix"]:
        node["reference"] = mp["suffix"]
        node["suffix"] = mp["suffix"]
        with_suffix += 1

    # primary author id, if resolvable
    if not node.get("primary_author_theologian_id") and mp["theologian"]:
        t = theos_by_name.get(norm(mp["theologian"]))
        if t:
            node["primary_author_theologian_id"] = t["id"]

    # authors[] (primary + parsed from suffix)
    authors = list(node.get("authors") or [])
    seen = set((a.get("id") or norm(a.get("full_name") or a.get("name") or a.get("slug") or "")) for a in authors)

    # primary mapping author
    if mp["theologian"]:
        t = theos_by_name.get(norm(mp["theologian"]))
        key = (t["id"] if t else norm(mp["theologian"]))
        if key not in seen:
            if t:
                authors.append({"id": t["id"], "slug": t.get("slug"), "full_name": t["full_name"]})
            else:
                authors.append({"full_name": mp["theologian"]})
            seen.add(key)

    # co-authors / editors from suffix
    for nm in parse_names_from_suffix(mp["suffix"]):
        t = theos_by_name.get(norm(nm))
        key = (t["id"] if t else norm(nm))
        if key in seen: continue
        if t:
            authors.append({"id": t["id"], "slug": t.get("slug"), "full_name": t["full_name"]})
        else:
            authors.append({"full_name": nm})
        seen.add(key)

    if authors:
        node["authors"] = authors

    # mark as topic keywork
    node["is_topic_keywork"] = True

# ---------- write back ----------
dump(BY_WORK_JSON, by_work)
print(f"by_work.json updated. touched={touched}, with_suffix={with_suffix}")
