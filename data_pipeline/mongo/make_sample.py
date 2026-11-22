"""Write data/sample/works_sample.json (300 works) for member B and the tests (task A3, owner: A).

Keeps the 20 hand-made works, then adds works from data/raw/works.json, one genre after the
other, so every genre is represented. Ids are the same as in works.json.
    python -m data_pipeline.mongo.make_sample
"""

import argparse
import json
from itertools import zip_longest
from pathlib import Path


def pick(works: list[dict], size: int = 300) -> list[dict]:
    hand_made = [w for w in works if w.get("source") == "sample"]
    by_genre: dict[str, list[dict]] = {}
    for w in works:
        if w.get("source") != "sample":
            by_genre.setdefault(w["genre"], []).append(w)
    chosen = list(hand_made)
    # round robin over the genres, biggest genre first
    queues = [by_genre[g] for g in sorted(by_genre, key=lambda g: -len(by_genre[g]))]
    for group in zip_longest(*queues):
        for w in group:
            if w is not None and len(chosen) < size:
                chosen.append(w)
    return sorted(chosen, key=lambda w: w["_id"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--works", default="data/raw/works.json")
    ap.add_argument("--out", default="data/sample/works_sample.json")
    ap.add_argument("--size", type=int, default=300)
    args = ap.parse_args()
    works = json.loads(Path(args.works).read_text(encoding="utf-8"))
    sample = pick(works, args.size)
    Path(args.out).write_text(json.dumps(sample, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{len(sample)} works written to {args.out}")


if __name__ == "__main__":
    main()
