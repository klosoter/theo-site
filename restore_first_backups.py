#!/usr/bin/env python3
import argparse, pathlib, shutil

TARGETS = [
    "data/theologians.json",
    "data/works.json",
    "data/authors_registry.json",
    "data/outlines.jsonl",
    "data/indices/by_work.json",
    "data/indices/by_topic.json",
    "data/indices/by_theologian.json",
    "data/indices/search_index.json",
]

def earliest_backup(file_path: pathlib.Path) -> pathlib.Path | None:
    bdir = file_path.parent / "backups"
    pattern = f"{file_path.name}.bak-"
    if not bdir.exists():
        return None
    cands = sorted(p for p in bdir.iterdir() if p.name.startswith(pattern))
    return cands[0] if cands else None

def main(dry_run: bool):
    for t in TARGETS:
        fp = pathlib.Path(t)
        bk = earliest_backup(fp)
        if bk:
            print(f"{'DRY' if dry_run else 'RESTORE'}: {fp}  <--  {bk}")
            if not dry_run:
                shutil.copy2(bk, fp)
        else:
            print(f"SKIP (no backups): {fp}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    main(args.dry_run)
