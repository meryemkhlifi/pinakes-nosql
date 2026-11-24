"""Build the catalog (about 5,000 works) from the Project Gutenberg catalog (task A3, owner: A).

1. Download the catalog once (PowerShell):
     mkdir data\\raw
     curl.exe -L -o data/raw/pg_catalog.csv https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv
2. Run from the repo root:
     python -m data_pipeline.mongo.build_works
Output: data/raw/works.json (not committed). The 20 hand-made works of data/sample
(source = "sample") are kept first, with their ids w_0001 to w_0020.

Rules: Text only, English, authors born before --max-birth-year (default 1800), earliest
authors first. The Gutenberg catalog has no first lines, so incipit is null, and no
composition year, so year is approximated as birth year + 30.
"""

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

DATES = re.compile(r",?\s*(\d{1,4})\??\s*(BCE)?\s*-\s*(\d{1,4})?\??\s*(BCE)?\s*$")
ROLE = re.compile(r"\[([^\]]*)\]\s*$")
SKIP_NAMES = {"anonymous", "various", "unknown", "unknown author"}

# First match wins, so specific genres come before general ones.
GENRE_KEYWORDS = [
    ("tragedy", ["tragedy", "tragedies"]),
    ("comedy", ["comedy", "comedies"]),
    ("epic", ["epic"]),
    ("rhetoric", ["rhetoric", "oratory", "orations", "speeches"]),
    ("law", ["law", "jurisprudence", "legal"]),
    ("medicine", ["medicine", "medical", "physiology", "anatomy"]),
    ("mathematics", ["mathematics", "geometry", "arithmetic", "algebra"]),
    ("science", ["science", "physics", "astronomy", "chemistry", "natural history", "biology"]),
    ("philosophy", ["philosophy", "ethics", "metaphysics", "logic", "stoic"]),
    ("history", ["history", "histories", "chronicle", "biography"]),
    ("lyric", ["poetry", "poems", "odes", "sonnets", "lyric", "verse"]),
]


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def parse_author(part: str):
    """'Plato, 427? BCE-347? BCE' -> {'id': 'a_plato', 'name': 'Plato', 'birth_year': -427}."""
    part = part.strip()
    role = ROLE.search(part)
    if role:
        if role.group(1).strip().lower() != "author":
            return None  # translator, illustrator, editor ...
        part = ROLE.sub("", part).strip()
    birth = None
    m = DATES.search(part)
    if m:
        birth = int(m.group(1)) * (-1 if m.group(2) else 1)
        part = part[: m.start()].strip().rstrip(",")
    pieces = [p.strip() for p in part.split(",") if p.strip()]
    name = f"{pieces[1]} {pieces[0]}" if len(pieces) == 2 else ", ".join(pieces)
    if not name or name.lower() in SKIP_NAMES:
        return None
    return {"id": "a_" + slugify(name), "name": name, "birth_year": birth, "bio": None}


def guess_genre(subjects: str, bookshelves: str = "") -> str:
    text = f"{subjects} {bookshelves}".lower()
    for genre, words in GENRE_KEYWORDS:
        if any(w in text for w in words):
            return genre
    return "miscellany"


def clean_subjects(subjects: str, limit: int = 5) -> list[str]:
    out = []
    for s in subjects.split(";"):
        s = s.split(" -- ")[0].strip()
        if s and s not in out:
            out.append(s)
    return out[:limit]


def build_works(rows, max_birth_year=1800, limit=5000, languages=("en",), seed=()):
    """Gutenberg rows (dicts) -> list of work documents following contracts/schema_work.json."""
    seed = list(seed)
    next_num = max((int(w["_id"][2:]) for w in seed), default=0) + 1
    seen = {(w["title"].lower(), w["authors"][0]["id"]) for w in seed}

    candidates = []
    for r in rows:
        if r.get("Type") != "Text":
            continue
        language = (r.get("Language") or "").split(";")[0].strip()
        if language not in languages:
            continue
        authors = [a for a in map(parse_author, (r.get("Authors") or "").split(";")) if a]
        title = " ".join((r.get("Title") or "").split())
        if not authors or not title:
            continue
        birth = authors[0]["birth_year"]
        if birth is None or birth > max_birth_year:
            continue
        key = (title.lower(), authors[0]["id"])
        if key in seen:
            continue
        seen.add(key)
        candidates.append((birth, title, authors, language, r))

    candidates.sort(key=lambda c: (c[0], c[1].lower()))
    works = []
    for birth, title, authors, language, r in candidates[: max(0, limit - len(seed))]:
        works.append(
            {
                "_id": f"w_{next_num:04d}",
                "title": title,
                "incipit": None,
                "genre": guess_genre(r.get("Subjects") or "", r.get("Bookshelves") or ""),
                "authors": authors,
                "language": language,
                "year": birth + 30,
                "subjects": clean_subjects(r.get("Subjects") or ""),
                "source": "gutenberg",
            }
        )
        next_num += 1
    return seed + works


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--csv", default="data/raw/pg_catalog.csv")
    ap.add_argument("--seed", default="data/sample/works_sample.json")
    ap.add_argument("--out", default="data/raw/works.json")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--max-birth-year", type=int, default=1800)
    args = ap.parse_args()

    if not Path(args.csv).exists():
        raise SystemExit(f"{args.csv} not found. See the download command at the top of this file.")
    seed = []
    if Path(args.seed).exists():
        all_sample = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        seed = [w for w in all_sample if w.get("source") == "sample"]
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        works = build_works(csv.DictReader(f), args.max_birth_year, args.limit, seed=seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(works, ensure_ascii=False), encoding="utf-8")

    genres: dict[str, int] = {}
    for w in works:
        genres[w["genre"]] = genres.get(w["genre"], 0) + 1
    print(f"{len(works)} works written to {args.out}")
    for g, n in sorted(genres.items(), key=lambda kv: -kv[1]):
        print(f"  {g:12} {n}")


if __name__ == "__main__":
    main()
