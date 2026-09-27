"""
app.py — Literary reconciliation service prototype.

Implements the W3C Reconciliation Service API v0.2.
Compatible with OpenRefine out of the box.

Setup:
    pip install flask flask-cors rapidfuzz unidecode
    python filter.py --authors <your_authors_dump> --works <your_works_dump>
    python app.py

Endpoints:
    GET  /reconcile  --> service manifest
    POST /reconcile  --> reconciliation queries
"""

import json
import re
import sys
import os

from flask import Flask, request, jsonify
from flask_cors import CORS
from rapidfuzz import fuzz
from unidecode import unidecode


#  Configuration 

AUTHORS_FILE   = "authors_enriched.jsonl"
WORKS_FILE     = "works_filtered.jsonl"
MATCH_THRESHOLD = 95    # score at or above this is treated as an automatic match
PORT            = 5001

MANIFEST = {
    "versions": ["0.2"],
    "name": "Literary Reconciliation Service",
    "identifierSpace": "https://openlibrary.org",
    "schemaSpace": "https://schema.org/",
    "defaultTypes": [
        {"id": "Person", "name": "Author"},
        {"id": "Book",   "name": "Work"},
    ],
}


# Normalisation 

def normalize(text):
    """
    Lowercase, strip diacritics, remove punctuation, collapse whitespace.
    This runs on both stored data and incoming query strings.

    Examples:
        "Álvaro de Campos"  --> "alvaro de campos"
        "Robert Schönmayr"  --> "robert schonmayr"
        "L'enfant"          --> "lenfant"
        "george  eliot"     --> "george eliot"
    """
    if not text:
        return ""
    text = unidecode(text)           # strip diacritics: é --> e, ö --> o
    text = text.lower()              # lowercase
    text = re.sub(r"[^\w\s]", "", text)  # remove punctuation
    text = re.sub(r"\s+", " ", text).strip()  # collapse whitespace
    return text


#  Data classes

class Author:
    def __init__(self, key, name, alternate_names=None, source_records=None):
        self.key                       = key
        self.name                      = name
        self.name_normalized           = normalize(name)
        self.alternate_names           = alternate_names or []
        self.alternate_names_normalized = [normalize(n) for n in self.alternate_names]
        self.source_records            = source_records or []

    def all_names(self):
        """All name variants to match against — real name plus alternates."""
        return [self.name_normalized] + self.alternate_names_normalized

    def to_candidate(self, score):
        return {
            "id":    self.key,
            "name":  self.name,
            "score": score,
            "match": score >= MATCH_THRESHOLD,
            "type":  [{"id": "Person", "name": "Author"}],
        }


class Book:
    def __init__(self, key, title, author_keys=None, subjects=None):
        self.key              = key
        self.title            = title
        self.title_normalized = normalize(title)
        self.author_keys      = author_keys or []
        self.subjects         = subjects or []

    def to_candidate(self, score):
        return {
            "id":    self.key,
            "name":  self.title,
            "score": score,
            "match": score >= MATCH_THRESHOLD,
            "type":  [{"id": "Book", "name": "Work"}],
        }


#  Data loading 

def load_authors(path):
    """
    Load authors from a filtered JSONL file (one JSON object per line).
    Returns a list of Author objects and a dict keyed by OL author key
    for fast lookup when joining from book records.
    """
    authors = []
    index   = {}  # key --> Author, for joining from book records

    if not os.path.exists(path):
        print(f"  Warning: {path} not found. Author matching will be unavailable.")
        print(f"  Run: python filter.py --authors <dump> --works <dump>")
        return authors, index

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            author = Author(
                key             = record.get("key", ""),
                name            = record.get("name", ""),
                alternate_names = record.get("alternate_names", []),
                source_records  = record.get("source_records", []),
            )
            if author.name_normalized:
                authors.append(author)
                index[author.key] = author

    return authors, index


def load_works(path):
    """
    Load works from a filtered JSONL file (one JSON object per line).
    Returns a list of Book objects.
    """
    works = []

    if not os.path.exists(path):
        print(f"  Warning: {path} not found. Work matching will be unavailable.")
        print(f"  Run: python filter.py --authors <dump> --works <dump>")
        return works

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            book = Book(
                key         = record.get("key", ""),
                title       = record.get("title", ""),
                author_keys = record.get("author_keys", []),
                subjects    = record.get("subjects", []),
            )
            if book.title_normalized:
                works.append(book)

    return works

#  Indexing 
def build_index(authors):
    index = {}
    for author in authors:
        for name in author.all_names():
            for token in name.split():
                if len(token) >= 4:
                    if token not in index:
                        index[token] = []
                    if author not in index[token]:
                        index[token].append(author)
    return index


def lookup_candidates(query, index):
    tokens = normalize(query).split()
    candidates = set()
    initials = []

    for token in tokens:
        if len(token) == 1:
            initials.append(token)
        elif len(token) < 4:
            pass  # skip short tokens
        else:
            for author in index.get(token, []):
                candidates.add(author)

    # fallback if nothing found
    if not candidates:
        return AUTHORS

    # filter by initials if any
    if initials:
        candidates = {
            a for a in candidates
            if any(
                any(n.startswith(initial) for n in a.name_normalized.split())
                for initial in initials
            )
        }

    return list(candidates)



#  Matching 

def score_author(query_normalized, author):
    """
    Score a query string against an author record.
    Checks the real name and all alternate names, returns the highest score.
    Uses token_sort_ratio so word order doesn't matter:
        "Eliot George" scores well against "George Eliot".
    """
    best = 0
    for name in author.all_names():
        s = fuzz.token_sort_ratio(query_normalized, name)
        if s > best:
            best = s
    return best


def score_work(query_normalized, book):
    full_score = fuzz.token_sort_ratio(query_normalized, book.title_normalized)
    
    # only use partial_ratio when query is longer than stored title
    # to avoid short titles matching as substrings of the query
    if len(query_normalized) > len(book.title_normalized):
        return full_score
    
    partial = fuzz.partial_ratio(query_normalized, book.title_normalized)
    return max(full_score, partial)

def match_authors(query_string, limit=5):
    """
    Find the top matching authors for a query string.
    Returns a list of candidate dicts sorted by score descending.
    """
    q = normalize(query_string)
    if not q:
        return []

    candidates = lookup_candidates(query_string, TOKEN_INDEX)

    scored = []
    for author in candidates:
        s = score_author(q, author)
        if s > 0:
            scored.append((s, author, None, None))

    # identity graph lookup
    graph_matches = graph_lookup(q)
    for match in graph_matches:
        author = match["author"]
        # use the higher of the identity score or the regular score
        existing = next((x for x in scored if x[1] == author), None)
        if existing:
            scored.remove(existing)
        scored.append((
            match["identity_score"],
            author,
            match["relationship"],
            match["to_name"]
        ))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, author, relationship, matched_via in scored[:limit]:
        candidate = author.to_candidate(score)
        if relationship:
            candidate["match_via"] = relationship
            candidate["matched_name"] = matched_via
            candidate["confidence"] = next(
                (m["confidence"] for m in graph_matches if m["author"] == author),
                1.0
            )
        results.append(candidate)
    return results    


def graph_lookup(query_normalized):
    """
    Check if the query matches any identity name in the reverse graph.
    Returns a list of candidate dicts if found, empty list otherwise.
    """
    if not IDENTITY_GRAPH:
        return []
    
    reverse = IDENTITY_GRAPH.get("reverse", {})
    matches = []
    
    for identity_name, relationships in reverse.items():
        score = fuzz.token_sort_ratio(query_normalized, identity_name)
        # print(f"  graph: '{query_normalized}' vs '{identity_name}' = {score}")  # debug
        if score >= 60:  # low threshold — let the main scorer decide
            for rel in relationships:
                author = AUTHOR_INDEX.get(rel["from_key"])
                if author:
                    matches.append({
                        "author": author,
                        "identity_score": score,
                        "relationship": rel["relationship"],
                        "to_name": rel["to_name"],
                        "confidence": rel["confidence"],
                        "note": rel["note"]
                    })
    
    return matches

def match_works(query_string, limit=5):
    """
    Find the top matching works for a query string.
    Returns a list of candidate dicts sorted by score descending.
    """
    q = normalize(query_string)
    if not q:
        return []


    # title variant lookup first
    variant_matches = title_variant_lookup(q)
    # deduplicate variant matches by canonical key, keeping highest score
    seen_keys = {}
    for match in variant_matches:
        key = match["book"].key
        if key not in seen_keys or match["score"] > seen_keys[key]["score"]:
            seen_keys[key] = match
    variant_matches = list(seen_keys.values())
    variant_books = {m["book"] for m in variant_matches}

    scored = []
    for book in WORKS:
        if book in variant_books:
            continue
        s = score_work(q, book)
        if s > 0:
            scored.append((s, book, None, None))


    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for match in variant_matches:
        candidate = match["book"].to_candidate(match["score"])
        candidate["match_via"] = "titleVariant"
        candidate["matched_variant"] = match["matched_variant"]
        candidate["variant_language"] = match["language"]
        results.append(candidate)

    for score, book, _, _ in scored[:limit - len(results)]:
        results.append(book.to_candidate(score))

    return results[:limit]


def dispatch_query(query):
    """
    Route a single reconciliation query to the right matcher
    based on the type hint OpenRefine sends, or match both if no type given.
    Returns a list of candidates.
    """
    query_string = query.get("query", "")
    type_hint    = query.get("type", "")
    limit        = query.get("limit", 5)

    # OpenRefine sends type as either a string ID or a list of type objects
    if isinstance(type_hint, list):
        type_ids = [t.get("id", "") if isinstance(t, dict) else t for t in type_hint]
    else:
        type_ids = [type_hint]

    if "Person" in type_ids or "Author" in type_ids:
        return match_authors(query_string, limit)
    elif "Book" in type_ids or "Work" in type_ids:
        return match_works(query_string, limit)
    else:
        # No type specified — try authors first, fall back to works
        results = match_authors(query_string, limit)
        if not results:
            results = match_works(query_string, limit)
        return results


#  Identity graph 

def load_identity_graph(path="identity_graph.json"):
    if not os.path.exists(path):
        print(f"  Warning: {path} not found. Identity graph unavailable.")
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    graph = {}
    for rel in data["relationships"]:
        key = rel["from_key"]
        if key not in graph:
            graph[key] = []
        graph[key].append({
            "relationship": rel["relationship"],
            "to_name": rel["to_name"],
            "confidence": rel["confidence"],
            "note": rel.get("note", ""),
            "to_name":      rel["to_name"]
        })
    
    # build reverse index — to_name --> list of (from_key, relationship, confidence)
    reverse = {}
    for rel in data["relationships"]:
        name_normalized = normalize(rel["to_name"])
        if name_normalized not in reverse:
            reverse[name_normalized] = []
        reverse[name_normalized].append({
            "from_key": rel["from_key"],
            "from_name": rel["from_name"],
            "relationship": rel["relationship"],
            "confidence": rel["confidence"],
            "note": rel.get("note", ""),
            "to_name":      rel["to_name"]
        })
    
    return {"forward": graph, "reverse": reverse}

#  Title variants handling 


def load_title_variants(path="title_variants.json"):
    if not os.path.exists(path):
        print(f"  Warning: {path} not found. Title variant matching unavailable.")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # reverse index: normalised variant title --> canonical work key
    reverse = {}
    for entry in data["variants"]:
        canonical_key = entry["canonical_key"]
        canonical_title = entry["canonical_title"]
        for variant in entry["variants"]:
            variant_normalized = normalize(variant["title"])
            if variant_normalized not in reverse:
                reverse[variant_normalized] = []
            reverse[variant_normalized].append({
                "canonical_key": canonical_key,
                "canonical_title": canonical_title,
                "variant_title": variant["title"],
                "language": variant["language"]
            })

    return reverse


def title_variant_lookup(query_normalized):
    matches = []
    for variant_title, entries in TITLE_VARIANTS.items():
        score = fuzz.token_sort_ratio(query_normalized, variant_title)
        if score >= 80:
            for entry in entries:
                book = next(
                    (b for b in WORKS if b.key == entry["canonical_key"]),
                    None
                )
                if book:
                    matches.append({
                        "book": book,
                        "score": score,
                        "matched_variant": entry["variant_title"],
                        "language": entry["language"]
                    })
    return matches
#  Flask app 

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)  # mandatory for OpenRefine compatibility

@app.route("/")
def index():
    """Serve the web UI."""
    return app.send_static_file("index.html")


@app.route("/search")
def search():
    """
    Simple search endpoint for the web UI.
    GET /search?q=george+eliot&type=Person
    Returns top candidates as JSON.
    """
    q    = request.args.get("q", "").strip()
    kind = request.args.get("type", "")

    if not q:
        return jsonify({"results": []})

    if kind == "Person":
        candidates = match_authors(q, limit=5)
    elif kind == "Book":
        candidates = match_works(q, limit=5)
    else:
        candidates = match_authors(q, limit=5) or match_works(q, limit=5)

    return jsonify({"results": candidates})

@app.route("/reconcile", methods=["GET"])
def manifest():
    """Return the service manifest."""
    return jsonify(MANIFEST)


@app.route("/reconcile", methods=["POST"])
def reconcile():
    """
    Handle reconciliation queries from OpenRefine.
    OpenRefine sends a 'queries' parameter containing a JSON object
    where each key maps to one query dict.

    Example input:
        queries = {
            "q0": {"query": "george eliot", "type": "Person"},
            "q1": {"query": "middlemarch",   "type": "Book"},
        }

    Example output:
        {
            "q0": {"result": [{"id": "/authors/OL24528A", "name": "George Eliot", "score": 98, "match": true, ...}]},
            "q1": {"result": [{"id": "/works/OL...",      "name": "Middlemarch",   "score": 100, "match": true, ...}]},
        }
    """
    # OpenRefine may send queries as form data or JSON body
    raw = request.form.get("queries") or request.get_json(silent=True, force=True)

    if raw is None:
        return jsonify({"error": "No queries provided"}), 400

    # If it arrived as a string (form data), parse it
    if isinstance(raw, str):
        try:
            queries = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({"error": "Malformed queries JSON"}), 400
    else:
        queries = raw.get("queries", raw)

    results = {}
    for key, query in queries.items():
        candidates = dispatch_query(query)
        results[key] = {"result": candidates}

    return jsonify(results)


#  Startup 

print("Loading authors...", end=" ", flush=True)
AUTHORS, AUTHOR_INDEX = load_authors(AUTHORS_FILE)
print(f"done ({len(AUTHORS):,} records)")

print("Building token index...", end=" ", flush=True)
TOKEN_INDEX = build_index(AUTHORS)
print(f"done ({len(TOKEN_INDEX):,} tokens)")

print("Loading identity graph...", end=" ", flush=True)
IDENTITY_GRAPH = load_identity_graph()
print(f"done ({len(IDENTITY_GRAPH.get('forward', {}))} nodes, "
      f"{len(IDENTITY_GRAPH.get('reverse', {}))} reverse entries)")

print("Loading works...", end=" ", flush=True)
WORKS = load_works(WORKS_FILE)
print(f"done ({len(WORKS):,} records)")

print("Loading title variants...", end=" ", flush=True)
TITLE_VARIANTS = load_title_variants()
print(f"done ({len(TITLE_VARIANTS)} variant entries)")

if not AUTHORS and not WORKS:
    print("\nNo data loaded. Run filter.py first, then restart.")
    sys.exit(1)

print(f"\nService ready at http://localhost:{PORT}/reconcile\n")

if __name__ == "__main__":
    app.run(debug=True, port=PORT)