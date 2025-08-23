#!/usr/bin/env python3
import sys, json, re, shutil
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

# ---------------- regexes ----------------
# Category name like "10. Ecclesiology ..." → captures 10
CAT_NUM_RE = re.compile(r'^\s*(\d{1,2})\s*\.')

# topic_slug like "10-a-..." or "10.A..." or "11.c.something"
# captures: 10, 'A' (letter can be a..k or A..K)
SLUG_CODE_RE = re.compile(r'^\s*(\d{1,2})[.\-]([A-Za-z])\b')

# deterministic order for letters A..K (anything else goes after K)
LETTER_ORDER = {chr(ord('A') + i): i for i in range(11)}  # A→0 ... K→10

def cat_sort_key(cat_name: str, original_index: int):
    """
    Sort by leading category number (1..11). If missing, put at bottom but
    preserve its relative order via original_index.
    """
    m = CAT_NUM_RE.match(cat_name or "")
    if m:
        n = int(m.group(1))
        return (n, 0, original_index)  # numeric first; keep stable by index
    return (10**9, 1, original_index)  # sink non-numbered to bottom

def topic_sort_key(topic_obj: dict):
    """
    Sort by (category number from slug, letter A..K), then whole slug as tiebreaker.
    If missing/odd, push to bottom but keep deterministic by slug.
    """
    slug = (topic_obj or {}).get("topic_slug", "") or ""
    m = SLUG_CODE_RE.match(slug)
    if m:
        num = int(m.group(1))
        letter = m.group(2).upper()
        letter_rank = LETTER_ORDER.get(letter, 10**6)  # unknown letters after K
        # Final tie‑breaker by full slug for stability
        return (num, letter_rank, slug)
    # Fallback: uncoded slugs sink below coded ones, ordered lexicographically
    return (10**9, 10**7, slug)

def load_json_preserve_order(p: Path):
    # Python 3.7+ preserves dict order, but be explicit for clarity.
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)

def main():
    if len(sys.argv) < 2:
        print("Usage: sort_by_theologian.py <path/to/input.json> [--inplace]")
        sys.exit(1)

    src = Path(sys.argv[1]).resolve()
    inplace = ("--inplace" in sys.argv)

    data = load_json_preserve_order(src)  # keep theologian order as-is
    out = OrderedDict()

    for theo_id, payload in data.items():
        new_payload = dict(payload)
        obtc = (payload or {}).get("outlines_by_topic_category")

        if isinstance(obtc, dict):
            # Attach original index so non-numbered categories keep relative order
            cat_rows = [(name, items, idx) for idx, (name, items) in enumerate(obtc.items())]
            # 1) sort categories 1..11 numerically
            cat_rows.sort(key=lambda row: cat_sort_key(row[0], row[2]))

            # 2) within each category, sort topics by topic_slug code (e.g., 10-A .. 10-K)
            new_obtc = OrderedDict()
            for cat_name, items, _ in cat_rows:
                if isinstance(items, list):
                    items_sorted = sorted(items, key=topic_sort_key)
                else:
                    items_sorted = items
                new_obtc[cat_name] = items_sorted

            new_payload["outlines_by_topic_category"] = new_obtc

        out[theo_id] = new_payload  # preserve original theologian order

    result = json.dumps(out, ensure_ascii=False, indent=2)
    if inplace:
        backup = src.with_suffix(src.suffix + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(src, backup)
        src.write_text(result + "\n", encoding="utf-8")
        print(f"Updated in place. Backup at: {backup}")
    else:
        sys.stdout.write(result + "\n")

if __name__ == "__main__":
    print("did not do anything")
#     main()
