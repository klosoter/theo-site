#!/usr/bin/env python3
import os, json, pathlib, datetime, shutil
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from collections.abc import Mapping, Sequence

load_dotenv()
ROOT = pathlib.Path(".").parent.resolve()
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()

THEO_FILE = DATA_DIR / "theologians.json"
WORK_FILE = DATA_DIR / "works.json"
AUTHORS_REGISTRY = DATA_DIR / "authors_registry.json"
OUTLINES_JSONL = DATA_DIR / "outlines.jsonl"
BY_WORK = DATA_DIR / "indices/by_work.json"
BY_TOPIC = DATA_DIR / "indices/by_topic.json"
BY_THEO = DATA_DIR / "indices/by_theologian.json"
SEARCH_INDEX = DATA_DIR / "indices/search_index.json"

app = Flask(__name__, static_folder=str(ROOT / "static"))


def _load_json(path: pathlib.Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _read_jsonl(p):
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _write_json(path: pathlib.Path, obj):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if path.exists():
        backups = path.parent / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backups / f"{path.name}.bak-{ts}")
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: pathlib.Path, obj):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if path.exists():
        backups = path.parent / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backups / f"{path.name}.bak-{ts}")
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in obj) + "\n", encoding="utf-8")


CACHE = {}


def _reload():
    CACHE["theologians"] = _load_json(THEO_FILE, [])
    CACHE["works"] = _load_json(WORK_FILE, [])
    CACHE["outlines"] = _read_jsonl(OUTLINES_JSONL)
    CACHE["authors_registry"] = _load_json(AUTHORS_REGISTRY, {})
    CACHE["by_work"] = _load_json(BY_WORK, {})
    CACHE["by_topic"] = _load_json(BY_TOPIC, {})
    CACHE["by_theologian"] = _load_json(BY_THEO, {})
    CACHE["search_index"] = _load_json(SEARCH_INDEX, [])


def _load_map(all_works):
    rows = _load_json(MAP_FILE, []) or []
    m = {}
    for r in rows:
        wid = r.get("work_id");
        cid = r.get("canonical_id")
        if wid and cid:
            m[wid] = cid
    # ensure all work ids have a mapping (identity)
    for w in (all_works or []):
        wid = w.get("id")
        if wid:
            m.setdefault(wid, wid)
    # compress
    for wid in list(m.keys()):
        m[wid] = _root(m, wid)
    return m


def _save_map(m):
    rows = [{"work_id": wid, "canonical_id": cid} for wid, cid in sorted(m.items())]
    _write_json(MAP_FILE, rows)


def IDT(tid):
    for t in theologians:
        if t["id"] == tid:
            return t.get("name", "")
    else:
        return ""


def TID(name):
    """Return the theologian id for a given name, or None if not found."""
    for t in theologians:
        if t.get("name") == name or t.get("full_name") == name:
            return t["id"]
    return None


import re, unicodedata


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)

from collections.abc import Mapping

def root_id(tid: str, id_map: dict[str, str]) -> str:
    """Follow alias→canonical chain until it stabilizes."""
    seen = set()
    cur = tid
    while True:
        nxt = id_map.get(cur, cur)
        if nxt == cur or nxt in seen:
            return nxt
        seen.add(cur)
        cur = nxt

def _key_for_dedup(x):
    """Stable key for any item, including dicts/lists."""
    # Prefer semantic ids when present
    if isinstance(x, Mapping):
        if "id" in x and isinstance(x["id"], (str, int)):  # common case
            return ("id", x["id"])
        if "outline_id" in x and isinstance(x["outline_id"], (str, int)):
            return ("outline_id", x["outline_id"])
        # Fallback: JSON signature of the mapping
        return ("json", json.dumps(x, sort_keys=True, ensure_ascii=False))
    # Tuples/lists: JSON signature (avoids unhashable)
    if isinstance(x, (list, tuple)):
        return ("json", json.dumps(x, sort_keys=True, ensure_ascii=False))
    # Hashables
    try:
        hash(x)
        return ("hash", x)
    except TypeError:
        return ("repr", repr(x))



def _dedup_seq(seq):
    seen, out = set(), []
    for x in (seq or []):
        k = _key_for_dedup(x)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _merge_vals(a, b):
    if a is None: return b
    if b is None: return a

    if isinstance(a, Mapping) and isinstance(b, Mapping):
        out = dict(a)
        for k, vb in b.items():
            out[k] = _merge_vals(out.get(k), vb) if k in out else vb
        return out

    if isinstance(a, set) and isinstance(b, set):
        return a | b

    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return _dedup_seq(list(a) + list(b))

    return a if a not in (None, "", [], {}) else b




check_names = {
    "Alan Spence": "Alan J. Spence",
    "Catherine McDowell": "Catherine L. McDowell",
    "David Fergusson": "David S. Fergusson",
    "Edward J. Young": "E.J. Young",
    "Gentry": "Peter J. Gentry",
    "Gordon Fee": "Gordon D. Fee",
    "Graham Cole": "Graham A. Cole",
    "Greg K. Beale": "Gregory K. Beale",
    "J.K. Beale": "Gregory K. Beale",
    "James Hamilton": "James M. Hamilton Jr.",
    "John Frame": "John M. Frame",
    "John MacArthur": "John F. MacArthur",
    "John Kilner": "John F. Kilner",
    "John Walton": "John H. Walton",
    "John Cooper": "John W. Cooper",
    "John Zizioulas": "John D. Zizioulas",
    "John Feinberg": "John S. Feinberg",
    "Joshua Farris": "Joshua R. Farris",
    "Michael Horton": "Michael S. Horton",
    "Peter Lillback": "Peter A. Lillback",
    "R. Michael Allen": "Michael Allen",
    "Richard Muller": "Richard A. Muller",
    "Richard Gaffin": "Richard B. Gaffin Jr.",
    "Scott Oliphint": "K. Scott Oliphint",
    "Adam C. Johnson": "Adam J. Johnson"
}

check_ids = {
    'theo_62f645237cbb': 'theo_c66c309571d9',
    'theo_253aff752917': 'theo_dde2bb8d741f',
    'theo_b9954d5c121e': 'theo_45caa804f8e0',
    'theo_4fee92d32985': 'theo_258a625b4ef0',
    'theo_46c70c2943c0': 'theo_3907f7b67a12',
    'theo_97952d3f743d': 'theo_6c80a418d7d3',
    'theo_440ea3109c7d': 'theo_364cc75ee079',
    'theo_c30de6e1e9d5': 'theo_38bdde67d604',
    'theo_af1da100ed05': 'theo_38bdde67d604',
    'theo_b4bc91dbb7bb': 'theo_02d402e5475a',
    'theo_a9d7b0a5f494': 'theo_ea6658b8fe68',
    'theo_eb306afbcaaa': 'theo_95d2d502c3ed',
    'theo_3744a9f4a218': 'theo_97c5607b2a3f',
    'theo_669053ae4ac4': 'theo_59a7835435c2',
    'theo_ce6917d33274': 'theo_19f8ef8dc16d',
    'theo_978af2b7052c': 'theo_c45d52affb4c',
    'theo_0a7a3b8cebf5': 'theo_e0b69ac23733',
    'theo_17f2cdad80ea': 'theo_3bbe3faed649',
    'theo_af308ef786d9': 'theo_2c429c991f77',
    'theo_fdc11111194f': 'theo_cf2f4adad47b',
    'theo_137dccd720d4': 'theo_d04d5e20087a',
    'theo_8632e4000bfa': 'theo_0a257bf889f6',
    'theo_452e8ff3c243': 'theo_01d6e8e3cff7',
    'theo_92ae76efc1c9': 'theo_36708a47db3b',
    'theo_421f6f1cf18d': 'theo_3698ee84fe2f'
}


def update_outlines(outlines, id_map):
    out = []
    for o in outlines:
        d = dict(o)
        tid = d.get("theologian_id")
        d["theologian_id"] = root_id(tid, id_map) if tid else tid
        out.append(d)
    return out



def update_theologians(theologians, id_map, _slugify=lambda s: s):
    by_id = {t["id"]: t for t in theologians if isinstance(t, dict) and t.get("id")}
    groups = {}  # canon_id -> [rows]
    for t in theologians:
        tid = t.get("id")
        if not tid:
            continue
        canon = root_id(tid, id_map)
        groups.setdefault(canon, []).append(t)

    # ensure we create a row even if canonical id isn't present but aliases are
    for alias, canon in id_map.items():
        groups.setdefault(root_id(canon, id_map), groups.get(root_id(canon, id_map), []))

    merged_rows = []
    for canon_id, members in groups.items():
        base = by_id.get(canon_id) or (members[0] if members else {"id": canon_id})
        kw_union = set()
        for m in members:
            for wid in (m.get("key_work_ids") or []):
                if wid:
                    kw_union.add(wid)

        merged = {
            "id": base.get("id", canon_id),
            "slug": _slugify(base.get("full_name") or base.get("name") or ""),
            "full_name": base.get("full_name", ""),
            "name": base.get("name", ""),
            "dates": base.get("dates", ""),
            "era_category": base.get("era_category", []) or [],
            "traditions": base.get("traditions", []) or [],
            "bio": base.get("bio", "") or "",
            "timeline": base.get("timeline", []) or [],
            "key_work_ids": sorted(kw_union),
            "wts_relevance": base.get("wts_relevance", False),
            "created_at": base.get("created_at", ""),
            "updated_at": base.get("updated_at", ""),
        }
        merged_rows.append(merged)

    merged_rows.sort(key=lambda t: ((t.get("full_name") or t.get("name") or "").lower(), t.get("id") or ""))
    return merged_rows



def update_by_work(by_work, id_map, theologian_name_by_id, _slugify=lambda s: s):
    out = {}
    for wid, work in by_work.items():
        w = dict(work)

        prim = w.get("primary_author_theologian_id")
        w["primary_author_theologian_id"] = root_id(prim, id_map) if prim else prim

        refs = []
        for ref in w.get("referenced_in", []) or []:
            r = dict(ref)
            tid = r.get("theologian_id")
            r["theologian_id"] = root_id(tid, id_map) if tid else tid
            refs.append(r)
        w["referenced_in"] = refs

        authors = []
        for a in w.get("authors", []) or []:
            aid = a.get("id")
            cid = root_id(aid, id_map) if aid else aid
            full = theologian_name_by_id.get(cid, a.get("full_name") or "")
            authors.append({"id": cid, "slug": _slugify(full), "full_name": full})
        w["authors"] = authors

        out[wid] = w
    return out


def update_by_topic(by_topic, id_map, theologian_name_by_id, _slugify=lambda s: s):
    out = {}
    for topic_id, topic_data in by_topic.items():
        td = dict(topic_data)
        new_theos = []
        for theo in td.get("theologians", []) or []:
            old_id = theo.get("theologian_id")
            new_id = root_id(old_id, id_map) if old_id else old_id
            full = theologian_name_by_id.get(new_id, theo.get("full_name") or "")
            new_theos.append({"full_name": full, "theologian_id": new_id, "slug": _slugify(full)})
        td["theologians"] = new_theos
        out[topic_id] = td
    return out




def update_by_theologian(by_theologian: dict[str, object], id_map: dict[str, str]) -> dict[str, object]:
    # group keys by canonical id
    groups: dict[str, list[str]] = {}
    for tid in by_theologian.keys():
        canon = root_id(tid, id_map)
        groups.setdefault(canon, []).append(tid)

    out: dict[str, object] = {}
    for canon_id, members in groups.items():
        # merge canonical's value first so its scalars "win"
        ordered = [canon_id] + [k for k in members if k != canon_id]
        merged_val = None
        for k in ordered:
            if k in by_theologian:
                merged_val = _merge_vals(merged_val, by_theologian[k])
        out[canon_id] = merged_val
    return out



# --- main ---
if __name__ == "__main__":
    _reload()
    outlines        = CACHE["outlines"]
    works           = CACHE["works"]
    theologians     = CACHE["theologians"]
    authors_registry= CACHE["authors_registry"]
    by_work         = CACHE["by_work"]
    by_topic        = CACHE["by_topic"]
    by_theologian   = CACHE["by_theologian"]
    search_index    = CACHE["search_index"]

    id_map = check_ids
    theologian_name_by_id = {t["id"]: (t.get("full_name") or t.get("name") or "") for t in theologians}

    _write_jsonl(OUTLINES_JSONL,  update_outlines(outlines, id_map))
    print("wrote outlines")

    _write_json(BY_WORK,  update_by_work(by_work, id_map, theologian_name_by_id))
    print("wrote by work")

    _write_json(BY_TOPIC, update_by_topic(by_topic, id_map, theologian_name_by_id))
    print("wrote by topic")

    _write_json(BY_THEO,  update_by_theologian(by_theologian, id_map))   # <-- add ()
    print("wrote by theologian")

    _write_json(THEO_FILE, update_theologians(theologians, id_map))
    print("wrote theologian")
