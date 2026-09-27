import json
import requests
import re
from unidecode import unidecode

def normalize(text):
    text = unidecode(text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Load authors and generate abbreviated queries
import random

authors = []
with open("authors_enriched.jsonl") as f:
    for line in f:
        r = json.loads(line)
        name = r.get("name", "")
        parts = name.split()
        # only take authors with at least two parts and no initials already
        if len(parts) == 2 and len(parts[0]) > 1 and len(parts[1]) > 1:
            authors.append(r)

print(f"Found {len(authors)} two-word author names suitable for abbreviation")

# Sample 50
sample = random.sample(authors, min(50, len(authors)))

results = []
for author in sample:
    parts = author["name"].split()
    # generate first initial + surname
    abbreviated = f"{parts[0][0]}. {parts[1]}"
    canonical_key = author["key"]

    response = requests.post(
        "http://127.0.0.1:5001/reconcile",
        data={"queries": json.dumps({"q0": {"query": abbreviated, "type": "Person"}})}
    )
    data = response.json()
    candidates = data.get("q0", {}).get("result", [])

    top = candidates[0] if candidates else None
    correct_at_rank_1 = top and top["id"] == canonical_key
    auto_matched = top and top.get("match", False)
    correct_auto = correct_at_rank_1 and auto_matched
    false_auto = auto_matched and not correct_at_rank_1

    results.append({
        "query": abbreviated,
        "canonical_name": author["name"],
        "canonical_key": canonical_key,
        "top_result_key": top["id"] if top else None,
        "top_result_name": top["name"] if top else None,
        "top_score": top["score"] if top else None,
        "correct_at_rank_1": correct_at_rank_1,
        "auto_matched": auto_matched,
        "correct_auto": correct_auto,
        "false_auto": false_auto,
    })
    print(f"{'+' if correct_at_rank_1 else '-'} {abbreviated:20s} --> {author['name']:30s} | top: {top['name'][:30] if top else 'none':30s} ({top['score'] if top else '-'})")

total = len(results)
correct = sum(1 for r in results if r["correct_at_rank_1"])
auto = sum(1 for r in results if r["auto_matched"])
correct_auto = sum(1 for r in results if r["correct_auto"])
false_auto = sum(1 for r in results if r["false_auto"])

print(f"\n--- Summary ---")
print(f"Total queries: {total}")
print(f"Recall at rank 1: {correct}/{total} ({100*correct/total:.1f}%)")
print(f"Auto-matched: {auto}/{total}")
if auto:
    print(f"Correct auto-matches: {correct_auto}/{auto} ({100*correct_auto/auto:.1f}% precision)")
print(f"False auto-matches: {false_auto}")

with open("test_results_abbreviated.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Full results saved to test_results_abbreviated.json")