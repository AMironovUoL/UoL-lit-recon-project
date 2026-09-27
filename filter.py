"""
filter.py — run this once before starting the service.

Reads your raw Open Library dump files and writes two smaller files
containing only records with enough data to be useful for matching.

Usage:
    python filter.py --authors ol_dump_authors.txt --works ol_dump_works.txt

Output:
    authors_filtered.jsonl
    works_filtered.jsonl

Each output file is one JSON object per line (JSON Lines format).
"""

import json
import argparse
import sys


def parse_ol_line(line):
    """
    Parse one line from an Open Library dump file.
    Format: type TAB key TAB revision TAB timestamp TAB json
    Returns the parsed JSON dict, or None if the line is malformed.
    """
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 5:
        return None
    try:
        return json.loads(parts[4])
    except json.JSONDecodeError:
        return None


def filter_authors(input_path, output_path):
    """
    Keep author records that have at least a name field.
    Prefer records that also have alternate_names or remote_ids,
    but include all named records so the dataset is not too sparse.
    """
    kept = 0
    skipped = 0

    print(f"Filtering authors from {input_path}...")

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            record = parse_ol_line(line)
            if record is None:
                skipped += 1
                continue

            name = record.get("name", "").strip()
            if not name:
                skipped += 1
                continue

            # Build a clean minimal record with only the fields we need
            clean = {
                "key":             record.get("key", ""),
                "name":            name,
                "alternate_names": record.get("alternate_names", []),
                "remote_ids":      record.get("remote_ids", {}),
                "birth_date":      record.get("birth_date", ""),
                "death_date":      record.get("death_date", ""),
                "source_records":  record.get("source_records", []),
            }

            outfile.write(json.dumps(clean, ensure_ascii=False) + "\n")
            kept += 1

            if kept % 100_000 == 0:
                print(f"  {kept:,} authors kept so far...")

    print(f"Authors done: {kept:,} kept, {skipped:,} skipped → {output_path}")
    return kept


def filter_works(input_path, output_path):
    """
    Keep work records that have a title and at least one author key.
    """
    kept = 0
    skipped = 0

    print(f"Filtering works from {input_path}...")

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            record = parse_ol_line(line)
            if record is None:
                skipped += 1
                continue

            title = record.get("title", "").strip()
            if not title:
                skipped += 1
                continue

            # Extract author keys from the nested structure
            raw_authors = record.get("authors", [])
            author_keys = []
            for entry in raw_authors:
                author = entry.get("author", {})
                key = author.get("key", "")
                if key:
                    author_keys.append(key)

            if not author_keys:
                skipped += 1
                continue

            clean = {
                "key":         record.get("key", ""),
                "title":       title,
                "author_keys": author_keys,
                "subjects":    record.get("subjects", []),
            }

            outfile.write(json.dumps(clean, ensure_ascii=False) + "\n")
            kept += 1

            if kept % 100_000 == 0:
                print(f"  {kept:,} works kept so far...")

    print(f"Works done: {kept:,} kept, {skipped:,} skipped → {output_path}")
    return kept


def main():
    parser = argparse.ArgumentParser(description="Filter Open Library dump files.")
    parser.add_argument("--authors", required=True, help="Path to the raw authors dump file")
    parser.add_argument("--works",   required=True, help="Path to the raw works dump file")
    parser.add_argument("--authors-out", default="authors_filtered.jsonl")
    parser.add_argument("--works-out",   default="works_filtered.jsonl")
    args = parser.parse_args()

    total_authors = filter_authors(args.authors, args.authors_out)
    total_works   = filter_works(args.works, args.works_out)

    print(f"\nDone. {total_authors:,} authors and {total_works:,} works ready.")
    print(f"Now run: python app.py")


if __name__ == "__main__":
    main()