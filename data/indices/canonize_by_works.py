from utils import get_files, write_json, write_jsonl
import pathlib

CACHE = get_files()
authors_registry, authors_registry_path = CACHE["authors_registry"]
outlines_jsonl, outlines_jsonl_path = CACHE["outlines_jsonl"]
theologians, theologians_path = CACHE["theologians"]
topic_mapping, topic_mapping_path = CACHE["topic_mapping"]
topics, topics_path = CACHE["topics"]
traditions, traditions_path = CACHE["traditions"]
work_canon_map, work_canon_map_path = CACHE["work_canon_map"]
works, works_path = CACHE["works"]
by_theologian, by_theologian_path = CACHE["by_theologian"]
by_topic, by_topic_path = CACHE["by_topic"]
by_topic_keyworks, by_topic_keyworks_path = CACHE["by_topic_keyworks"]
by_work, by_work_path = CACHE["by_work"]
eras_registry, eras_registry_path = CACHE["eras_registry"]
institutions_registry, institutions_registry_path = CACHE["institutions_registry"]
theologian_profiles, theologian_profiles_path = CACHE["theologian_profiles"]
topic_work_edges, topic_work_edges_path = CACHE["topic_work_edges"]
search_index, search_index_path = CACHE["search_index"]

def update_refs_and_keywork(by_work: dict, canon_map: dict):
    """
    Mutates and returns `by_work`.

    Rules:
    - referenced_in: merged & deduped ONLY on the canonical entry.
    - is_topic_keywork: if any alias True -> set True on ALL entries in that canon group.
    - All other fields remain as-is.
    """

    def dedupe_refs(refs):
        seen, out = set(), []
        for r in refs:
            key = (
                r.get("outline_id"),
            )
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    # group work ids by canonical
    canon_map_dict = {i["work_id"]: i["canonical_id"] for i in canon_map}
    reverse_canon_map = {canonical_id: list(set([wid for wid, cid in canon_map_dict.items() if cid == canonical_id] + [canonical_id])) for canonical_id in set(canon_map_dict.values())}

    # process each group
    for canon_id, wids in reverse_canon_map.items():
        # any alias might be missing from by_work (defensive)
        entries = [by_work[wid] for wid in wids if wid in by_work]

        # compute union for referenced_in and OR for is_topic_keywork
        any_keywork = any(bool(e.get("is_topic_keywork")) for e in entries)
        merged_refs = dedupe_refs(
            [r for e in entries for r in e.get("referenced_in", [])]
        )

        # 1) propagate is_topic_keywork to all items in the group
        if any_keywork:
            for wid in wids:
                if wid in by_work:
                    by_work[wid]["is_topic_keywork"] = True

        # 2) write merged referenced_in ONLY to the canonical entry
        if canon_id in by_work:
            by_work[canon_id]["referenced_in"] = merged_refs

    return by_work

by_work = update_refs_and_keywork(by_work, work_canon_map)
write_json("data/indices/by_work.json", by_work)
