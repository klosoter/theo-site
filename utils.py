# import os, json, pathlib, datetime, shutil
# from dotenv import load_dotenv
#
# def load_json(path: pathlib.Path, default=None):
#     try:
#         return json.loads(path.read_text(encoding="utf-8"))
#     except FileNotFoundError:
#         print(f"{path} not found")
#         return default
#
#
# def load_jsonl(path: pathlib.Path, default=None):
#     try:
#         return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
#     except FileNotFoundError:
#         print(f"{path} not found")
#
#         return default
#
#
# def write_json(path: pathlib.Path, obj):
#     ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
#     try:
#         path.exists()
#     except:
#         path = pathlib.Path(path)
#
#     if path.exists():
#         backups = path.parent / "backups"
#         backups.mkdir(parents=True, exist_ok=True)
#         shutil.copy2(path, backups / f"{path.name}.bak-{ts}")
#     pathlib.Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
#
#
#
# def write_jsonl(path: pathlib.Path, obj):
#     ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
#     if path.exists():
#         backups = path.parent / "backups"
#         backups.mkdir(parents=True, exist_ok=True)
#         shutil.copy2(path, backups / f"{path.name}.bak-{ts}")
#     path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in obj) + "\n", encoding="utf-8")
#
# ROOT = pathlib.Path(".").parent.resolve().parent.resolve()
# ROOT = ROOT / "theo-ai"
# DATA_DIR = ROOT / "data"
# INDICES_DIR = DATA_DIR / "indices"
# THEO_PROFILES_DIR = INDICES_DIR / "theologian_profiles"
# OUTLINES_DIR = ROOT / "outlines"
#
# AUTHORS_REGISTRY_FILE = DATA_DIR / "authors_registry.json"
# OUTLINES_JSONL_FILE = DATA_DIR / "outlines.jsonl"
# THEOLOGIANS_FILE = DATA_DIR / "theologians.json"
# TOPIC_MAPPING_FILE = DATA_DIR / "topic_mapping.json"
# TOPICS_FILE = DATA_DIR / "topics.json"
# TRADITIONS_FILE = DATA_DIR / "traditions.json"
# ERAS_FILE = DATA_DIR / "eras.json"
# WORK_CANON_MAP_FILE = DATA_DIR / "work_canon_map.json"
# WORKS_FILE = DATA_DIR / "works.json"
#
# BY_THEOLOGIAN_FILE = INDICES_DIR / "by_theologian.json"
# BY_TOPIC_FILE = INDICES_DIR / "by_topic.json"
# BY_TOPIC_KEYWORKS_FILE = INDICES_DIR / "by_topic_keyworks.json"
# BY_WORK_FILE = INDICES_DIR / "by_work.json"
# ERAS_REGISTRY_FILE = INDICES_DIR / "eras_registry.json"
# INSTITUTIONS_REGISTRY_FILE = INDICES_DIR / "institutions_registry.json"
# THEOLOGIAN_PROFILES_FILE = INDICES_DIR / "theologian_profiles.json"
# TOPIC_WORK_EDGES_FILE = INDICES_DIR / "topic_work_edges.json"
# SEARCH_INDEX_FILE = INDICES_DIR / "search_index.json"
#
#
# file_paths = [
#     "AUTHORS_REGISTRY_FILE",
#     "OUTLINES_JSONL_FILE",
#     "THEOLOGIANS_FILE",
#     "TOPIC_MAPPING_FILE",
#     "TOPICS_FILE",
#     "TRADITIONS_FILE",
#     "ERAS_FILE",
#     "WORK_CANON_MAP_FILE",
#     "WORKS_FILE",
#     "BY_THEOLOGIAN_FILE",
#     "BY_TOPIC_FILE",
#     "BY_TOPIC_KEYWORKS_FILE",
#     "BY_WORK_FILE",
#     "ERAS_REGISTRY_FILE",
#     "INSTITUTIONS_REGISTRY_FILE",
#     "THEOLOGIAN_PROFILES_FILE",
#     "TOPIC_WORK_EDGES_FILE",
#     "SEARCH_INDEX_FILE",
# ]
#
# def get_files():
#     CACHE = {
#         "authors_registry": (load_json(AUTHORS_REGISTRY_FILE, {}), AUTHORS_REGISTRY_FILE),
#         "outlines_jsonl": (load_jsonl(OUTLINES_JSONL_FILE, []), OUTLINES_JSONL_FILE),
#         "theologians": (load_json(THEOLOGIANS_FILE, []), THEOLOGIANS_FILE),
#         "topic_mapping": (load_json(TOPIC_MAPPING_FILE, {}), TOPIC_MAPPING_FILE),
#         "topics": (load_json(TOPICS_FILE, []), TOPICS_FILE),
#         "traditions": (load_json(TRADITIONS_FILE, {}), TRADITIONS_FILE),
#         "eras": (load_json(ERAS_FILE, {}), ERAS_FILE),
#         "work_canon_map": (load_json(WORK_CANON_MAP_FILE, []), WORK_CANON_MAP_FILE),
#         "works": (load_json(WORKS_FILE, []), WORKS_FILE),
#         "by_theologian": (load_json(BY_THEOLOGIAN_FILE, {}), BY_THEOLOGIAN_FILE),
#         "by_topic": (load_json(BY_TOPIC_FILE, {}), BY_TOPIC_FILE),
#         "by_topic_keyworks": (load_json(BY_TOPIC_KEYWORKS_FILE, {}), BY_TOPIC_KEYWORKS_FILE),
#         "by_work": (load_json(BY_WORK_FILE, {}), BY_WORK_FILE),
#         "eras_registry": (load_json(ERAS_REGISTRY_FILE, {}), ERAS_REGISTRY_FILE),
#         "institutions_registry": (load_json(INSTITUTIONS_REGISTRY_FILE, {}), INSTITUTIONS_REGISTRY_FILE),
#         "theologian_profiles": (load_json(THEOLOGIAN_PROFILES_FILE, {}), THEOLOGIAN_PROFILES_FILE),
#         "topic_work_edges": (load_json(TOPIC_WORK_EDGES_FILE, []), TOPIC_WORK_EDGES_FILE),
#         "search_index": (load_json(SEARCH_INDEX_FILE, []), SEARCH_INDEX_FILE),
#     }
#     return CACHE
#
#
# file_paths = [
#     "AUTHORS_REGISTRY_FILE",
#     "OUTLINES_JSONL_FILE",
#     "THEOLOGIANS_FILE",
#     "TOPIC_MAPPING_FILE",
#     "TOPICS_FILE",
#     "TRADITIONS_FILE",
#     "ERAS_FILE",
#     "WORK_CANON_MAP_FILE",
#     "WORKS_FILE",
#     "BY_THEOLOGIAN_FILE",
#     "BY_TOPIC_FILE",
#     "BY_TOPIC_KEYWORKS_FILE",
#     "BY_WORK_FILE",
#     "ERAS_REGISTRY_FILE",
#     "INSTITUTIONS_REGISTRY_FILE",
#     "THEOLOGIAN_PROFILES_FILE",
#     "TOPIC_WORK_EDGES_FILE",
#     "SEARCH_INDEX_FILE",
# ]
#
#
# def get_literal_string(file_paths):
#     literal_dict_string = "CACHE = {\n"
#     for file_path in file_paths:
#         text = ("_").join(file_path.lower().split("_")[:-1])
#         if text.endswith("jsonl"):
#             literal_dict_string += f'\t"{text.lower()}": (load_jsonl({file_path}), {file_path}),\n'
#         else:
#             literal_dict_string += f'\t"{text.lower()}": (load_json({file_path}), {file_path}),\n'
#
#     literal_dict_string += "}"
#
# #     CACHE = {
# #         "authors_registry": (load_json(AUTHORS_REGISTRY_FILE, {}), AUTHORS_REGISTRY_FILE),
# #         "outlines_jsonl": (load_jsonl(OUTLINES_JSONL_FILE, []), OUTLINES_JSONL_FILE),
# #         "theologians": (load_json(THEOLOGIANS_FILE, []), THEOLOGIANS_FILE),
# #         "topic_mapping": (load_json(TOPIC_MAPPING_FILE, {}), TOPIC_MAPPING_FILE),
# #         "topics": (load_json(TOPICS_FILE, []), TOPICS_FILE),
# #         "traditions": (load_json(TRADITIONS_FILE, {}), TRADITIONS_FILE),
# #         "eras": (load_json(ERAS_FILE, {}), ERAS_FILE),
# #         "work_canon_map": (load_json(WORK_CANON_MAP_FILE, []), WORK_CANON_MAP_FILE),
# #         "works": (load_json(WORKS_FILE, []), WORKS_FILE),
# #         "by_theologian": (load_json(BY_THEOLOGIAN_FILE, {}), BY_THEOLOGIAN_FILE),
# #         "by_topic": (load_json(BY_TOPIC_FILE, {}), BY_TOPIC_FILE),
# #         "by_topic_keyworks": (load_json(BY_TOPIC_KEYWORKS_FILE, {}), BY_TOPIC_KEYWORKS_FILE),
# #         "by_work": (load_json(BY_WORK_FILE, {}), BY_WORK_FILE),
# #         "eras_registry": (load_json(ERAS_REGISTRY_FILE, {}), ERAS_REGISTRY_FILE),
# #         "institutions_registry": (load_json(INSTITUTIONS_REGISTRY_FILE, {}), INSTITUTIONS_REGISTRY_FILE),
# #         "theologian_profiles": (load_json(THEOLOGIAN_PROFILES_FILE, {}), THEOLOGIAN_PROFILES_FILE),
# #         "topic_work_edges": (load_json(TOPIC_WORK_EDGES_FILE, []), TOPIC_WORK_EDGES_FILE),
# #         "search_index": (load_json(SEARCH_INDEX_FILE, []), SEARCH_INDEX_FILE),
# #     }
#
#     return literal_dict_string
#
# # for file_path in file_paths:
# #     file = ("_").join(file_path.lower().split("_")[:-1])
# #     print(f'{file}, {file}_path = CACHE["{file}"]')
#
# # CACHE = get_files()
# # authors_registry, authors_registry_path = CACHE["authors_registry"]
# # outlines_jsonl, outlines_jsonl_path = CACHE["outlines_jsonl"]
# # theologians, theologians_path = CACHE["theologians"]
# # topic_mapping, topic_mapping_path = CACHE["topic_mapping"]
# # topics, topics_path = CACHE["topics"]
# # traditions, traditions_path = CACHE["traditions"]
# # eras, eras_path = CACHE["eras"]
# # work_canon_map, work_canon_map_path = CACHE["work_canon_map"]
# # works, works_path = CACHE["works"]
# # by_theologian, by_theologian_path = CACHE["by_theologian"]
# # by_topic, by_topic_path = CACHE["by_topic"]
# # by_topic_keyworks, by_topic_keyworks_path = CACHE["by_topic_keyworks"]
# # by_work, by_work_path = CACHE["by_work"]
# # eras_registry, eras_registry_path = CACHE["eras_registry"]
# # institutions_registry, institutions_registry_path = CACHE["institutions_registry"]
# # theologian_profiles, theologian_profiles_path = CACHE["theologian_profiles"]
# # topic_work_edges, topic_work_edges_path = CACHE["topic_work_edges"]
# # search_index, search_index_path = CACHE["search_index"]


# utils.py — digest filename + author helpers
import re, pathlib

_slug_rx = re.compile(r"[^a-z0-9]+")

def slugify2(s: str, max_len: int = 220) -> str:
    s = (s or "").strip().lower()
    s = _slug_rx.sub("-", s)
    return s.strip("-").strip(".")[:max_len]

def extract_author_and_title_from_name(file_name: str):
    """
    Expect '<authors> - <title>.<ext>'.
    Works for .md/.docx/etc. Uses Path.stem (no brittle slicing).
    Normalizes title: ';' → ':'.
    """
    stem = pathlib.Path(file_name).stem
    parts = stem.split(" - ", 1)
    if len(parts) != 2:
        return None, None
    authors_display, title = parts[0].strip(), parts[1].strip()
    title = title.replace(";", ":")
    return authors_display, title

def split_authors(authors_display: str):
    """
    Robust split into individual authors without breaking 'Last, First' chunks.
    Handles: ', and ' (Oxford), ' and ', '&', and trims trailing 'et al'.
    Returns e.g.: ['Anderson, James N.', 'Greg Welty']
    """
    if not authors_display:
        return []
    s = re.sub(r"\s+et\s+al\.?$", "", authors_display, flags=re.I).strip()
    s = re.sub(r",\s+and\s+", " and ", s, flags=re.I)  # normalize Oxford comma
    parts = re.split(r"\s+(?:and|&)\s+", s)
    return [p.strip() for p in parts if p.strip()]

def surname_of(author: str):
    """
    'Anderson, James N.' → 'Anderson'
    'Greg Welty' → 'Welty'
    'Thomas of Aquino' → 'Aquino'
    """
    a = (author or "").strip()
    if "," in a:
        return a.split(",", 1)[0].strip()
    toks = a.split()
    if len(toks) >= 3 and toks[-2].lower() == "of":
        return toks[-1]
    return toks[-1] if toks else ""

def parse_digest_filename_md(file_name: str):
    """
    Returns: (title, authors_display, authors_short[list])
    """
    authors_display, title = extract_author_and_title_from_name(file_name)
    if not authors_display or not title:
        return None, None, []
    parts = split_authors(authors_display)
    authors_short = [surname_of(p) for p in parts]
    return title, authors_display, authors_short
