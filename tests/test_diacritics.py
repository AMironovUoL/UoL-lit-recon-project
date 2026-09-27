import json
import random
import requests
from unidecode import unidecode

# Load all works with diacritics
works_with_diacritics = []
with open("works_filtered.jsonl") as f:
    for line in f:
        r = json.loads(line)
        title = r.get("title", "")
        stripped = unidecode(title)
        if stripped != title and len(title.split()) >= 2:  # at least 2 words
            works_with_diacritics.append({
                "key": r["key"],
                "original_title": title,
                "stripped_title": stripped,
            })

# Sample 50
sample = random.sample(works_with_diacritics, 50)

# Query the service for each
results = []
for work in sample:
    query = work["stripped_title"]
    response = requests.post(
        "http://127.0.0.1:5001/reconcile",
        data={"queries": json.dumps({"q0": {"query": query, "type": "Book"}})}
    )
    data = response.json()
    candidates = data.get("q0", {}).get("result", [])

    top = candidates[0] if candidates else None
    correct_at_rank_1 = top and top["id"] == work["key"]
    auto_matched = top and top.get("match", False)
    correct_auto = correct_at_rank_1 and auto_matched
    false_auto = auto_matched and not correct_at_rank_1

    results.append({
        "query": query,
        "original_title": work["original_title"],
        "expected_key": work["key"],
        "top_result_key": top["id"] if top else None,
        "top_result_name": top["name"] if top else None,
        "top_score": top["score"] if top else None,
        "correct_at_rank_1": correct_at_rank_1,
        "auto_matched": auto_matched,
        "correct_auto": correct_auto,
        "false_auto": false_auto,
    })
    print(f"{'+' if correct_at_rank_1 else '-'} {query[:50]:50s} --> {top['name'][:40] if top else 'no result':40s} ({top['score'] if top else '-'})")

# Summary
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

# Save results
with open("test_results_diacritics.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nFull results saved to test_results_diacritics.json")