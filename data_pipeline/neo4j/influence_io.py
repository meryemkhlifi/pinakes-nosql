"""Helpers shared by the influence scripts (owner: B).

File format of data/sample/influences.json:
{
  "external_authors": [{"id": "a_socrates", "name": "Socrates"}],
  "edges": [
    {"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF", "origin": "curated"}
  ]
}
An edge always points from the person who was influenced (or the student)
to the person who influenced them (or the teacher).
"""

import json
import re
import unicodedata
from pathlib import Path

EDGE_TYPES = ("INFLUENCED_BY", "STUDENT_OF")


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def author_id(name: str) -> str:
    return "a_" + slugify(name)


def authors_from_works(works: list[dict]) -> dict[str, dict]:
    """One entry per author id, with the subjects, genres and years of all their works."""
    authors: dict[str, dict] = {}
    for w in works:
        for a in w["authors"]:
            cur = authors.setdefault(
                a["id"],
                {
                    "id": a["id"],
                    "name": a["name"],
                    "birth_year": a.get("birth_year"),
                    "subjects": set(),
                    "genres": set(),
                    "years": [],
                },
            )
            if cur["birth_year"] is None and a.get("birth_year") is not None:
                cur["birth_year"] = a["birth_year"]
            cur["subjects"].update(s.lower() for s in w.get("subjects", []))
            cur["genres"].add(w["genre"])
            if w.get("year") is not None:
                cur["years"].append(w["year"])
    return authors


def edge_key(edge: dict) -> tuple:
    return (edge["source"], edge["target"], edge["type"])


def merge_edges(existing: list[dict], new: list[dict]) -> list[dict]:
    seen = {edge_key(e) for e in existing}
    merged = list(existing)
    for e in new:
        if edge_key(e) not in seen:
            seen.add(edge_key(e))
            merged.append(e)
    return merged


def read_file(path) -> tuple[dict[str, dict], list[dict]]:
    p = Path(path)
    if not p.exists():
        return {}, []
    data = json.loads(p.read_text(encoding="utf-8"))
    external = {a["id"]: a for a in data.get("external_authors", [])}
    return external, data.get("edges", [])


def write_file(path, external: dict[str, dict], edges: list[dict]) -> None:
    out = {
        "external_authors": sorted(external.values(), key=lambda a: a["id"]),
        "edges": sorted(edges, key=edge_key),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
