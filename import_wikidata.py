import requests
import json

url = "https://query.wikidata.org/sparql"

# query = """
# SELECT ?author ?penname ?olid WHERE {
#   ?author wdt:P648 ?olid .
#   ?author wdt:P742 ?penname .
# }
# LIMIT 10000
# """

# response = requests.get(url, params={
#     "query": query,
#     "format": "json"
# }, headers={
#     "User-Agent": "LitReconcile/1.0"
# })

# data = response.json()



# results = data["results"]["bindings"]

# print(f"Got {len(results)} results")
# print()

# for row in results[:5]:
#     print(f"OL key:   {row['olid']['value']}")
#     print(f"Pen name: {row['penname']['value']}")
#     print()



all_results = []
offset = 0
limit = 10000

while True:
    query = f"""
    SELECT ?author ?penname ?olid WHERE {{
      ?author wdt:P648 ?olid .
      ?author wdt:P742 ?penname .
    }}
    LIMIT {limit}
    OFFSET {offset}
    """
    
    print(f"Fetching results {offset} to {offset + limit}...")
    
    response = requests.get(url, params={
        "query": query,
        "format": "json"
    }, headers={
        "User-Agent": "LitReconcile/1.0"
    })
    
    results = response.json()["results"]["bindings"]
    all_results.extend(results)
    
    print(f"Got {len(results)} results, total so far: {len(all_results)}")
    
    if len(results) < limit:
        break
    
    offset += limit


pennames = {}

for row in all_results:
    ol_key = "/authors/" + row["olid"]["value"]
    penname = row["penname"]["value"]
    
    if ol_key not in pennames:
        pennames[ol_key] = []
    
    if penname not in pennames[ol_key]:
        pennames[ol_key].append(penname)

print(f"Unique author keys with pen names: {len(pennames)}")

# print a few to check
for key, names in list(pennames.items())[:5]:
    print(f"{key}: {names}")


# print(f"Total results: {len(all_results)}")


input_file = "authors_filtered.jsonl"
output_file = "authors_enriched.jsonl"

enriched = 0
total = 0

with open(input_file, "r", encoding="utf-8") as infile, \
     open(output_file, "w", encoding="utf-8") as outfile:
    
    for line in infile:
        line = line.strip()
        if not line:
            continue
        
        record = json.loads(line)
        total += 1
        
        key = record.get("key", "")
        if key in pennames:
            existing = record.get("alternate_names", [])
            for name in pennames[key]:
                if name not in existing:
                    existing.append(name)
            record["alternate_names"] = existing
            enriched += 1
        
        outfile.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"Done. {enriched} of {total} records enriched.")