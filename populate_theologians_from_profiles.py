from utils import get_files, write_json
from datetime import date

CACHE = get_files()
authors_registry, authors_registry_path = CACHE["authors_registry"]
outlines_jsonl, outlines_jsonl_path = CACHE["outlines_jsonl"]
theologians, theologians_path = CACHE["theologians"]
topic_mapping, topic_mapping_path = CACHE["topic_mapping"]
topics, topics_path = CACHE["topics"]
traditions, traditions_path = CACHE["traditions"]
eras, eras_path = CACHE["eras"]
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

# populate theologian profiles
for tp, tpdata in theologian_profiles.items():
    by = tpdata["birth_year"]
    dy = tpdata["death_year"]
    dates = f"{by}-{dy or ''}" if by else None

    tp_era = [era for era in eras if era["slug"] == tpdata["era_slug"]][0]
    tp_tradition = [trad for trad in traditions if trad["slug"] == tpdata["tradition_slug"]][0]

    if by and dy and dy - by > 110:
        theologian_profiles[tp]["birth_year"] = None
        theologian_profiles[tp]["death_year"] = None

    theologian_profiles[tp]["era"] = tp_era
    theologian_profiles[tp]["tradition"] = tp_tradition
    theologian_profiles[tp]["dates"] = dates

theologian_profiles = dict(sorted(theologian_profiles.items(),
                                  key=lambda x: x[1]["birth_year"] if x[1]["birth_year"] else (x[1]["era"]["start"] +
                                                                                               x[1]["era"]["end"]) / 2))
write_json(theologian_profiles_path, theologian_profiles)
write_json("data/indices/theologian_profiles.json", theologian_profiles)


# today's date
today = date.today()
date_str = today.strftime("%Y-%m-%d")


# populate theologians.json with profiles
theologians_dict = {theo["id"]: theo for theo in theologians}
new_theologians = []


for tp, tpdata in theologian_profiles.items():
    theologian = theologians_dict[tp]

    new_theo = {"id": tp, "slug": theologian["slug"], "full_name": theologian["full_name"], "name": theologian["name"],
                "institution_ids": tpdata["institution_ids"], "era_slug": tpdata["era_slug"],
                "tradition_slug": tpdata["tradition_slug"], "dates": tpdata["dates"],
                "birth_year": tpdata["birth_year"], "death_year": tpdata["death_year"], "era": tpdata["era"],
                "tradition": tpdata["tradition"], "bio": tpdata["bio"], "timeline": tpdata["timeline"],
                "key_work_ids": theologian["key_work_ids"], "wts_relevance": theologian["wts_relevance"],
                "created_at": theologian["created_at"], "updated_at": date_str, "themes": tpdata["themes"],
                "country_primary_iso": tpdata["country_primary_iso"]}

    new_theologians.append(new_theo)

write_json(theologians_path, new_theologians)
write_json("data/theologians.json", new_theologians)
