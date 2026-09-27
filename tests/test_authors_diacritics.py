import json
import random
import requests
from unidecode import unidecode

# Load all authors where name changes after diacritic stripping
authors_with_diacritics = []
with open("authors_enriched.jsonl") as f:
    for line in f:
        r = json.loads(line)
        name = r.get("name", "")
        stripped = unidecode(name)
        if stripped != name and len(name.split()) >= 2:
            authors_with_diacritics.append({
                "key": r["key"],
                "original_name": name,
                "stripped_name": stripped,
            })

print(f"Found {len(authors_with_diacritics)} authors with diacritics")

# Sample 50
sample = random.sample(authors_with_diacritics, min(50, len(authors_with_diacritics)))

results = []
for author in sample:
    query = author["stripped_name"]
    response = requests.post(
        "http://127.0.0.1:5001/reconcile",
        data={"queries": json.dumps({"q0": {"query": query, "type": "Person"}})}
    )
    data = response.json()
    candidates = data.get("q0", {}).get("result", [])

    top = candidates[0] if candidates else None
    correct_at_rank_1 = top and top["id"] == author["key"]
    auto_matched = top and top.get("match", False)
    correct_auto = correct_at_rank_1 and auto_matched
    false_auto = auto_matched and not correct_at_rank_1

    results.append({
        "query": query,
        "original_name": author["original_name"],
        "expected_key": author["key"],
        "top_result_key": top["id"] if top else None,
        "top_result_name": top["name"] if top else None,
        "top_score": top["score"] if top else None,
        "correct_at_rank_1": correct_at_rank_1,
        "auto_matched": auto_matched,
        "correct_auto": correct_auto,
        "false_auto": false_auto,
    })
    print(f"{'+' if correct_at_rank_1 else '-'} {query[:50]:50s} --> {top['name'][:40] if top else 'no result':40s} ({top['score'] if top else '-'})")

total = len(results)
correct = sum(1 for r in results if r["correct_at_rank_1"])
auto = sum(1 for r in results if r["auto_matched"])
correct_auto = sum(1 for r in results if r["correct_auto"])
false_auto = sum(1 for r in results if r["false_auto"])

print(f"\n--- Summary ---")
print(f"Total queries: {total}")
print(f"Recall at rank 1: {correct}/{total} ({100*correct/total:.1f}%)")
print(f"Auto-matched: {auto}/{total}")
print(f"Correct auto-matches: {correct_auto}/{auto if auto else 1} ({100*correct_auto/auto:.1f}% precision)" if auto else "No auto-matches")
print(f"False auto-matches: {false_auto}")

with open("test_results_authors_diacritics.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nFull results saved to test_results_authors_diacritics.json")