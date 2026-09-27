import json
from unidecode import unidecode
import re

works = []
with open("works_filtered.jsonl") as f:
    for line in f:
        r = json.loads(line)
        title = r.get("title", "")
        stripped = unidecode(title)
        if stripped != title:  # only titles that change after stripping
            works.append({
                "key": r["key"],
                "original": title,
                "stripped": stripped
            })

print(f"Found {len(works)} works with diacritics in title")
for w in works[:20]:
    print(f"  {w['original']} → {w['stripped']}")
    