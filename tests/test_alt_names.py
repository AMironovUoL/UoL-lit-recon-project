import json
import random
import requests
from unidecode import unidecode
import re

def normalize(text):
    text = unidecode(text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Load authors with alternate names
authors_with_alts = []
with open("authors_enriched.jsonl") as f:
    for line in f:
        r = json.loads(line)
        alts = r.get("alternate_names", [])
        if alts and r.get("name") and r.get("key"):
            authors_with_alts.append(r)

print(f"Found {len(authors_with_alts)} authors with alternate names")

# Sample up to 50
sample = random.sample(authors_with_alts, min(50, len(authors_with_alts)))

results = []
for author in sample:
    # pick the first alternate name as query
    alt_name = author["alternate_names"][0]
    canonical_key = author["key"]
    canonical_name = author["name"]

    # skip if alternate name is too similar to canonical (not interesting)
    if normalize(alt_name) == normalize(canonical_name):
        continue

    response = requests.post(
        "http://127.0.0.1:5001/reconcile",
        data={"queries": json.dumps({"q0": {"query": alt_name, "type": "Person"}})}
    )
    data = response.json()
    candidates = data.get("q0", {}).get("result", [])

    top = candidates[0] if candidates else None
    correct_at_rank_1 = top and top["id"] == canonical_key
    auto_matched = top and top.get("match", False)
    correct_auto = correct_at_rank_1 and auto_matched
    false_auto = auto_matched and not correct_at_rank_1

    results.append({
        "query": alt_name,
        "canonical_name": canonical_name,
        "canonical_key": canonical_key,
        "top_result_key": top["id"] if top else None,
        "top_result_name": top["name"] if top else None,
        "top_score": top["score"] if top else None,
        "correct_at_rank_1": correct_at_rank_1,
        "auto_matched": auto_matched,
        "correct_auto": correct_auto,
        "false_auto": false_auto,
    })
    print(f"{'+' if correct_at_rank_1 else '-'} {alt_name[:45]:45s} --> {top['name'][:35] if top else 'no result':35s} ({top['score'] if top else '-'})")

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

with open("test_results_alternate_names.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Full results saved to test_results_alternate_names.json")