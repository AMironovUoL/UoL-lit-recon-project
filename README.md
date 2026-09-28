Literary Reconciliation Service

A reconciliation service for literary identity, compatible with OpenRefine.
Matches author names and book titles against Open Library data, with support for pen names, heteronyms, disputed identities, and cross-language title variants.

Setup

1. Install dependencies

bash
pip install flask flask-cors rapidfuzz unidecode

2. Data files

The filtered data files are included in this repository and the service will load them directly. If you want to re-run the pipeline from source, short sample dumps are also included (short_dump_authors.txt, short_dump_works.txt). For the full dataset, download the Open Library bulk dumps from https://openlibrary.org/developers/dumps and place them in the project root as ol_dump_authors.txt and ol_dump_works.txt.

3. (Optional) Re-filter the data

bash
python filter.py --authors ol_dump_authors.txt --works ol_dump_works.txt

4. (Optional) Re-import Wikidata pen name mappings

bash
python import_wikidata.py

This queries Wikidata's SPARQL endpoint and updates authors_enriched.jsonl. The enriched file is included in the repo as a snapshot of the data used for evaluation.

5. Start the service

bash
python app.py

You should see:

Loading authors... done (n records)
Loading works... done (n records)
Service ready at http://localhost:5001/reconcile
Using with OpenRefine
Open OpenRefine with a spreadsheet containing a column of author names or book titles
Click the column menu → Reconcile → Start reconciling
Click Add Standard Service and enter: http://localhost:5001/reconcile
Select Author or Work as the type and click Start Reconciling
File structure
project/
├── app.py                      <- the service
├── filter.py                   <- pre-processing script
├── import_wikidata.py          <- Wikidata pen name import
├── import_variant_queries.py   <- title variant import
├── identity_graph.json         <- pen names, heteronyms, disputed identities
├── title_variants.json         <- cross-language title variant index
├── authors_filtered.jsonl      <- filtered author records
├── authors_enriched.jsonl      <- author records enriched with Wikidata data
├── works_filtered.jsonl        <- filtered work records
├── short_dump_authors.txt      <- sample author dump for development
├── short_dump_works.txt        <- sample works dump for development
├── static/index.html           <- service info page
├── tests/                      <- test suite
└── demos/                      <- example CSV files for OpenRefine
Testing

Run the full test suite:

bash
python -m pytest tests/

Or test the live service directly:

bash
# Check the manifest
curl http://localhost:5001/reconcile

# Test an author query
curl -X POST http://localhost:5001/reconcile \
  -d 'queries={"q0":{"query":"george eliot","type":"Person"}}'

# Test with a pen name
curl -X POST http://localhost:5001/reconcile \
  -d 'queries={"q0":{"query":"mary ann evans","type":"Person"}}'

# Test a book query
curl -X POST http://localhost:5001/reconcile \
  -d 'queries={"q0":{"query":"middlemarch","type":"Book"}}'
Known limitations
No preview API or data extension API
Matching is limited to the ~100,000 author records retained after filtering; minor authors with thin Open Library records may not be found
The Wikidata enrichment snapshot was taken at the time of development; re-running import_wikidata.py will update it.
