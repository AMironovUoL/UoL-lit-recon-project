import json
import requests
import random
from unidecode import unidecode
import re

def normalize(text):
    text = unidecode(text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Load two-word authors and reverse their name order
authors = []
with open("authors_enriched.jsonl") as f:
    for line in f:
        r = json.loads(line)
        name = r.get("name", "")
        parts = name.split()
        if len(parts) == 2 and len(parts[0]) > 1 and len(parts[1]) > 1:
            authors.append(r)

sample = random.sample(authors, min(50, len(authors)))

results = []
for author in sample:
    parts = author["name"].split()
    # reverse word order
    reversed_name = f"{parts[1]} {parts[0]}"
    canonical_key = author["key"]

    # skip if reversed is same as original after normalization
    if normalize(reversed_name) == normalize(author["name"]):
        continue

    response = requests.post(
        "http://127.0.0.1:5001/reconcile",
        data={"queries": json.dumps({"q0": {"query": reversed_name, "type": "Person"}})}
    )
    data = response.json()
    candidates = data.get("q0", {}).get("result", [])

    top = candidates[0] if candidates else None
    correct_at_rank_1 = top and top["id"] == canonical_key
    auto_matched = top and top.get("match", False)
    correct_auto = correct_at_rank_1 and auto_matched
    false_auto = auto_matched and not correct_at_rank_1

    results.append({
        "query": reversed_name,
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
    print(f"{'+' if correct_at_rank_1 else '-'} {reversed_name:30s} --> {author['name']:30s} | {top['name'][:25] if top else 'none':25s} ({top['score'] if top else '-'})")

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

with open("test_results_word_order.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Full results saved to test_results_word_order.json")