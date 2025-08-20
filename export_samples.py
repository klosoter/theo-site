#!/usr/bin/env python3
import os, json, pathlib, itertools

ROOT = pathlib.Path(".").parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()
SAMPLES_DIR = DATA_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

N = int(os.getenv("SAMPLE_N", "20"))

def load_json(path: pathlib.Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def read_jsonl(path: pathlib.Path):
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except FileNotFoundError:
        return []

def sample_obj(obj, n):
    if isinstance(obj, list):
        return obj[:n]
    if isinstance(obj, dict):
        return dict(itertools.islice(obj.items(), n))
    return obj

def write_txt(name: str, obj, *, as_jsonl=False):
    out = SAMPLES_DIR / f"{name}.txt"
    if as_jsonl and isinstance(obj, list):
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in obj[:N]) + "\n", encoding="utf-8")
    else:
        out.write_text(json.dumps(sample_obj(obj, N), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")

# ---- paths ----
WORK_FILE             = DATA_DIR / "works.json"
WORK_CANON_MAP        = DATA_DIR / "work_canon_map.json"
TOPIC_FILE            = DATA_DIR / "topics.json"
THEO_FILE             = DATA_DIR / "theologians.json"
AUTHORS_REGISTRY      = DATA_DIR / "authors_registry.json"
OUTLINES_JSONL        = DATA_DIR / "outlines.jsonl"
TOPIC_WORK_EDGES      = DATA_DIR / "indices/topic_work_edges.json"
SEARCH_INDEX          = DATA_DIR / "indices/search_index.json"
BY_WORK               = DATA_DIR / "indices/by_work.json"
BY_TOPIC              = DATA_DIR / "indices/by_topic.json"
BY_TOPIC_KEYWORKS     = DATA_DIR / "indices/by_topic_key_works.json"
BY_THEO               = DATA_DIR / "indices/by_theologian.json"
TOPIC_MAPPING         = ROOT / "topic_mapping_updated.json"

# ---- load ----
works               = load_json(WORK_FILE, [])
work_canon_map      = load_json(WORK_CANON_MAP, [])
topics              = load_json(TOPIC_FILE, [])
theologians         = load_json(THEO_FILE, [])
authors_registry    = load_json(AUTHORS_REGISTRY, {})
outlines            = read_jsonl(OUTLINES_JSONL)
topic_work_edges    = load_json(TOPIC_WORK_EDGES, [])
by_work             = load_json(BY_WORK, {})
by_topic            = load_json(BY_TOPIC, {})
by_topic_key_works  = load_json(BY_TOPIC_KEYWORKS, {})
by_theologian       = load_json(BY_THEO, {})
search_index        = load_json(SEARCH_INDEX, [])
topic_mapping       = load_json(TOPIC_MAPPING, {})

# ---- write samples ----
write_txt("works", works)
write_txt("work_canon_map", work_canon_map)
write_txt("topics", topics)
write_txt("theologians", theologians)
write_txt("authors_registry", authors_registry)
write_txt("outlines", outlines, as_jsonl=True)
write_txt("topic_work_edges", topic_work_edges)
write_txt("by_work", by_work)
write_txt("by_topic", by_topic)
write_txt("by_topic_key_works", by_topic_key_works)
write_txt("by_theologian", by_theologian)
write_txt("search_index", search_index)
write_txt("topic_mapping_updated", topic_mapping)
