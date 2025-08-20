#!/usr/bin/env python3
import pathlib, re, shutil, sys, os

# ---- CONFIG ---------------------------------------------------------------
# Scan these roots (relative to repo root "."); add/remove as needed.
ROOTS = ["."]
# Patterns to fix in PATHS (file & directory names)
PATH_RENAMES = [
    ("richard-b.-gaffin-jr.", "richard-b-gaffin-jr."),  # dotted slug -> clean
    ("richard-b.-gaffin-jr",  "richard-b-gaffin-jr"),
    ("gafifn",                "gaffin"),                # <-- your extra path case
]
# Patterns to fix in FILE CONTENTS (strings)
CONTENT_RENAMES = [
    ("richard-b.-gaffin-jr.", "richard-b-gaffin-jr."),
    ("richard-b.-gaffin-jr",  "richard-b-gaffin-jr"),
    ("richard-b-gaffin-jr..", "richard-b-gaffin-jr."),  # collapse double dot
    # Uncomment if text contains the typo too:
    # ("gafifn", "gaffin"),
]
TEXT_EXT = {
    ".md",".mdx",".markdown",".txt",".json",".jsonl",".yml",".yaml",
    ".js",".ts",".tsx",".py",".html",".css",".csv",".tsv"
}
BACKUP_DIR = ".backups_bulk_fix"
DRY_RUN = True  # set False to apply changes
# ---------------------------------------------------------------------------

ROOTS = [pathlib.Path(r).resolve() for r in ROOTS]
REPO = pathlib.Path(".").resolve()

def collapse_double_dots(s: str) -> str:
    # turn any 'name..ext' into 'name.ext' but leave '...' (ellipsis) alone in content
    while ".." in s:
        s = s.replace("..", ".")
    return s

def apply_map(s: str, mapping):
    for old, new in mapping:
        s = s.replace(old, new)
    return s

def rename_path(p: pathlib.Path) -> pathlib.Path:
    new_name = apply_map(p.name, PATH_RENAMES)
    new_name = collapse_double_dots(new_name)
    if new_name == p.name:
        return p
    target = p.with_name(new_name)
    # avoid collisions
    i = 1
    base, ext = os.path.splitext(new_name)
    while target.exists() and target != p:
        target = p.with_name(f"{base}-{i}{ext}")
        i += 1
    if DRY_RUN:
        print(f"[DRY] mv {p.relative_to(REPO)} -> {target.relative_to(REPO)}")
    else:
        p.rename(target)
    return target

def backup_file(p: pathlib.Path):
    dst = REPO / BACKUP_DIR / p.relative_to(REPO)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dst)

def process_contents(p: pathlib.Path):
    if p.suffix.lower() not in TEXT_EXT:
        return
    try:
        old = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        old = p.read_bytes().decode("latin-1")
    new = apply_map(old, CONTENT_RENAMES)
    # special: collapse only the slug’s accidental '..' (already mapped above)
    if new != old:
        if DRY_RUN:
            print(f"[DRY] edit {p.relative_to(REPO)}")
        else:
            backup_file(p)
            p.write_text(new, encoding="utf-8")

def walk_all(root: pathlib.Path):
    # Rename directories deepest-first, then files, then fix contents.
    # 1) collect all dirs/files
    dirs, files = [], []
    for path in root.rglob("*"):
        if path.is_dir():
            dirs.append(path)
        elif path.is_file():
            files.append(path)
    # 2) rename directories (deepest first)
    for d in sorted(dirs, key=lambda x: len(x.as_posix().split("/")), reverse=True):
        if d.exists():
            _ = rename_path(d)
    # 3) rename files
    for f in files:
        if f.exists():
            f2 = rename_path(f)
            # 4) fix contents (only if still a file)
            if f2.exists() and f2.is_file():
                process_contents(f2)

def main():
    print(f"Repo: {REPO}")
    print(f"Roots: {', '.join(str(r.relative_to(REPO)) for r in ROOTS)}")
    print(f"DRY_RUN = {DRY_RUN}")
    for root in ROOTS:
        if not root.exists():
            print(f"skip missing: {root}")
            continue
        walk_all(root)
    if DRY_RUN:
        print("\nDry run only. Set DRY_RUN=False in the script to apply changes.")

if __name__ == "__main__":
    main()
