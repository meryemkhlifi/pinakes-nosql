"""Fetch influence links from Wikidata (task B3, owner: B).

For each author of the catalog we ask Wikidata for P737 ('influenced by') and P1066
('student of'). Links to people who are not in the catalog are kept as 'external' authors
(for example Socrates), so paths can go through them.

    python -m data_pipeline.neo4j.fetch_influences --merge
If Wikidata is slow or empty, use generate_influences.py instead (or both with --merge).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

from data_pipeline.neo4j.influence_io import (
    author_id,
    authors_from_works,
    merge_edges,
    read_file,
    write_file,
)

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "PinakesNoSQL/1.0 (university course project)",
    "Accept": "application/sparql-results+json",
}
QUERY = """
SELECT ?name ?birth ?otherLabel ?prop WHERE {
  VALUES ?name { %(names)s }
  ?person rdfs:label ?name .
  ?person wdt:P31 wd:Q5 .
  { ?person wdt:P737 ?other . BIND("INFLUENCED_BY" AS ?prop) }
  UNION
  { ?person wdt:P1066 ?other . BIND("STUDENT_OF" AS ?prop) }
  OPTIONAL { ?person wdt:P569 ?birth }
  ?other rdfs:label ?otherLabel .
  FILTER(LANG(?otherLabel) = "en")
}
LIMIT %(limit)d
"""
MAX_BIRTH_GAP = 40  # years; drops namesakes (another 'Homer' born 2000 years later)


def build_query(names: list[str], limit: int) -> str:
    quoted = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in names)
    return QUERY % {"names": quoted, "limit": limit}


def year_from_wikidata(value: str | None):
    """'-0427-01-01T00:00:00Z' -> -427 ; '1265-05-30T00:00:00Z' -> 1265."""
    if not value:
        return None
    m = re.match(r"^(-?)(\d{1,4})-", value)
    if not m:
        return None
    year = int(m.group(2))
    return -year if m.group(1) else year


def parse_bindings(bindings: list[dict], authors_by_name: dict[str, dict]):
    """Turn SPARQL rows into (external_authors, edges)."""
    known_by_name = authors_by_name
    known_ids = {a["id"] for a in authors_by_name.values()}
    external: dict[str, dict] = {}
    edges: list[dict] = []
    for b in bindings:
        author = known_by_name.get(b["name"]["value"].lower())
        if author is None:
            continue
        wd_birth = year_from_wikidata(b.get("birth", {}).get("value"))
        ours = author["birth_year"]
        if ours is not None and wd_birth is not None and abs(ours - wd_birth) > MAX_BIRTH_GAP:
            continue  # a namesake, not our author
        other_name = b["otherLabel"]["value"]
        other = known_by_name.get(other_name.lower())
        other_id = other["id"] if other else author_id(other_name)
        if other_id == author["id"]:
            continue
        if other_id not in known_ids:
            external[other_id] = {"id": other_id, "name": other_name}
        edges.append(
            {
                "source": author["id"],
                "target": other_id,
                "type": b["prop"]["value"],
                "origin": "wikidata",
            }
        )
    return external, edges


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--works", default="data/sample/works_sample.json")
    ap.add_argument("--out", default="data/sample/influences.json")
    ap.add_argument("--chunk", type=int, default=30, help="authors per Wikidata request")
    ap.add_argument("--limit", type=int, default=500, help="LIMIT of each request")
    ap.add_argument("--merge", action="store_true", help="keep the links already in --out")
    args = ap.parse_args()

    works = json.loads(Path(args.works).read_text(encoding="utf-8"))
    authors = authors_from_works(works)
    by_name = {a["name"].lower(): a for a in authors.values()}
    names = sorted(a["name"] for a in authors.values())

    all_external: dict[str, dict] = {}
    all_edges: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        for i in range(0, len(names), args.chunk):
            chunk = names[i : i + args.chunk]
            try:
                r = client.get(
                    ENDPOINT,
                    params={"query": build_query(chunk, args.limit), "format": "json"},
                )
                r.raise_for_status()
                bindings = r.json()["results"]["bindings"]
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                print(f"  chunk {i // args.chunk + 1}: failed ({exc.__class__.__name__}), skipped")
                continue
            ext, edges = parse_bindings(bindings, by_name)
            all_external.update(ext)
            all_edges.extend(edges)
            print(f"  chunk {i // args.chunk + 1}: {len(edges)} links")
            time.sleep(1)  # be polite with the public endpoint

    if not all_edges:
        sys.exit("No link found. Use: python -m data_pipeline.neo4j.generate_influences --merge")
    external, existing = read_file(args.out) if args.merge else ({}, [])
    external.update(all_external)
    write_file(args.out, external, merge_edges(existing, all_edges))
    print(f"{len(all_edges)} Wikidata links, written to {args.out}")


if __name__ == "__main__":
    main()
