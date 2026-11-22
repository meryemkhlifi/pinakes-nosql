"""Generate influence links from shared subjects and genres (task B3, owner: B).

This is the fallback when Wikidata is slow or returns too little. Rule: an author X is
INFLUENCED_BY an author Y when Y is older than X and they share subjects (or, if they share
none, a genre). Each author gets at most --max-links such links, the best ones first.

    python -m data_pipeline.neo4j.generate_influences --merge
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from data_pipeline.neo4j.influence_io import (
    authors_from_works,
    merge_edges,
    read_file,
    write_file,
)


def author_year(author: dict):
    if author["birth_year"] is not None:
        return author["birth_year"]
    return min(author["years"]) if author["years"] else None


def generate(works: list[dict], max_links: int = 2) -> list[dict]:
    authors = authors_from_works(works)
    year = {i: author_year(a) for i, a in authors.items()}
    by_subject, by_genre = defaultdict(set), defaultdict(set)
    for i, a in authors.items():
        if year[i] is None:
            continue
        for s in a["subjects"]:
            by_subject[s].add(i)
        for g in a["genres"]:
            by_genre[g].add(i)

    edges = []
    for x, ax in authors.items():
        if year[x] is None:
            continue
        shared: dict[str, int] = defaultdict(int)
        for s in ax["subjects"]:
            for y in by_subject[s]:
                shared[y] += 1
        shared.pop(x, None)  # an author always shares everything with themselves
        if not shared:  # no common subject: fall back to the same genre
            for g in ax["genres"]:
                for y in by_genre[g]:
                    shared[y] += 1
        candidates = [(y, n) for y, n in shared.items() if y != x and year[y] < year[x]]
        # best first: most shared subjects, then the closest in time, then id (stable)
        candidates.sort(key=lambda c: (-c[1], year[x] - year[c[0]], c[0]))
        for y, _ in candidates[:max_links]:
            edges.append({"source": x, "target": y, "type": "INFLUENCED_BY", "origin": "generated"})
    return edges


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--works", default="data/sample/works_sample.json")
    ap.add_argument("--out", default="data/sample/influences.json")
    ap.add_argument("--max-links", type=int, default=2)
    ap.add_argument("--merge", action="store_true", help="keep the links already in --out")
    args = ap.parse_args()

    works = json.loads(Path(args.works).read_text(encoding="utf-8"))
    new = generate(works, args.max_links)
    external, existing = read_file(args.out) if args.merge else ({}, [])
    write_file(args.out, external, merge_edges(existing, new))
    print(f"{len(new)} generated links, written to {args.out}")


if __name__ == "__main__":
    main()
