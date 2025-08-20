# Paths (adjust if needed)
from pathlib import Path
import json, re

ROOT = Path(".").resolve()              # repo root (where theo-site lives)
DATA = ROOT / "data"
OUTLINES_DIR = ROOT / "outlines"

THEO_FILE = DATA / "theologians_migrated.json"  # source of truth
WORKS_FILE = DATA / "works.json"
OUTLINES_L = DATA / "outlines.jsonl"

def load_json(p, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def write_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def read_jsonl(p):
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

def write_jsonl(p, rows):
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

theologians = load_json(THEO_FILE, [])
works = load_json(WORKS_FILE, [])
outlines = read_jsonl(OUTLINES_L)

MERGES = [
    ("anthony-hoekema", "anthony-a.-hoekema"),
    ("b.b.-warfield", "benjamin-b.-warfield"),
    ("benjamin-b.-warfield-(distinct-focus-on-inerrancy)", "benjamin-b.-warfield"),
    ("edmund-clowney", "edmund-p.-clowney"),
    ("gordon-fee", "gordon-d.-fee"),
    ("greg-bahnsen", "greg-l.-bahnsen"),
    ("greg-k.-beale", "gregory-k.-beale"),
    ("gregory-beale", "gregory-k.-beale"),
    ("james-d.-g.-dunn", "james-d.g.-dunn"),
    ("james-dunn", "james-d.g.-dunn"),
    ("james-dolezal", "james-e.-dolezal"),
    ("james-k.-a.-smith", "james-k.a.-smith"),
    ("john-macarthur", "john-f.-macarthur"),
    ("john-walton", "john-h.-walton"),
    ("scott-oliphint", "k.-scott-oliphint"),
    ("kevin-vanhoozer", "kevin-j.-vanhoozer"),
    ("lane-tipton", "lane-g.-tipton"),
    ("michael-bird", "michael-f.-bird"),
    ("michael-horton", "michael-s.-horton"),
    ("n.-t.-wright", "n.t.-wright"),
    ("peter-lillback", "peter-a.-lillback"),
    ("peter-leithart", "peter-j.-leithart"),
    ("richard-muller", "richard-a.-muller"),
    ("richard-bauckham", "richard-j.-bauckham"),
    ("scott-swain", "scott-r.-swain"),
    ("sinclair-ferguson", "sinclair-b.-ferguson"),
    ("stephen-wellum", "stephen-j.-wellum"),
    ("thomas-f.-torrance", "t.f.-torrance"),
    ("ursinus-(zacharias-ursinus)", "zacharias-ursinus"),
    ("ursinus-zacharias", "zacharias-ursinus"),
    ("zwingli-huldrych", "huldrych-zwingli")
    ]

from copy import deepcopy

def find_theo(theos, key):
    for t in theos:
        if t.get("id") == key or t.get("slug") == key:
            return t
    return None

def apply_merges(theologians, works, outlines, merges, dry_run=True):
    theos = deepcopy(theologians)
    wrks = deepcopy(works) if works else []
    outs = deepcopy(outlines)

    file_moves = []
    logs = []

    for frm, to in merges:
        dup = find_theo(theos, frm)
        canon = find_theo(theos, to)
        if not dup or not canon:
            logs.append(("ERROR", f"Could not resolve from={frm} or to={to}"))
            continue
        dup_id, canon_id = dup["id"], canon["id"]
        dup_slug, canon_slug = dup.get("slug",""), canon.get("slug","")

        # Merge aliases + provenance
        aliases = set(canon.get("aliases", []))
        aliases.update([dup.get("full_name",""), dup.get("slug",""), *(dup.get("aliases") or [])])
        canon["aliases"] = sorted({a for a in aliases if a})
        merged = set(canon.get("merged_from_ids", []))
        merged.add(dup_id)
        canon["merged_from_ids"] = sorted(merged)

        # Remove duplicate theologian
        theos = [t for t in theos if t["id"] != dup_id]
        logs.append(("INFO", f"Merged {dup_id} → {canon_id}"))

        # Rewrite works authors
        for w in wrks or []:
            authors = w.get("authors") or []
            for a in authors:
                if isinstance(a, dict) and a.get("id") == dup_id:
                    a["id"] = canon_id
            # dedupe authors by id
            seen, new_auth = set(), []
            for a in authors:
                aid = a.get("id") if isinstance(a, dict) else a
                if aid in seen: continue
                seen.add(aid); new_auth.append(a)
            w["authors"] = new_auth

        # Rewrite outlines
        for o in outs:
            if o.get("theologian_id") == dup_id:
                o["theologian_id"] = canon_id
            mp = o.get("markdown_path","")
            if dup_slug and canon_slug and dup_slug in mp:
                new_mp = mp.replace(dup_slug, canon_slug)
                if new_mp != mp:
                    file_moves.append((mp, new_mp))
                    o["markdown_path"] = new_mp

    return theos, wrks, outs, file_moves, logs

theos2, works2, outs2, file_moves, logs = apply_merges(theologians, works, outlines, MERGES, dry_run=False)

# If the dry-run above looks good, run this cell to WRITE the files.
# (Make a backup if you want: THEO_FILE.rename(THEO_FILE.with_suffix(".json.bak")))

write_json(THEO_FILE, theos2)
write_json(WORKS_FILE, works2)
write_jsonl(OUTLINES_L, outs2)

print("# Apply these renames in your repo (copy/paste):")
for old, new in file_moves:
    print(f"git mv '{(OUTLINES_DIR/old).as_posix()}' '{(OUTLINES_DIR/new).as_posix()}'")
