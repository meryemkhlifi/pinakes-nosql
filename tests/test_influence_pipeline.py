import json

from data_pipeline.neo4j import fetch_influences as fi
from data_pipeline.neo4j import generate_influences as gi
from data_pipeline.neo4j import load_neo4j as ln
from data_pipeline.neo4j.influence_io import author_id, merge_edges, slugify


def work(wid, title, genre, year, subjects, author):
    return {
        "_id": wid,
        "title": title,
        "genre": genre,
        "language": "en",
        "year": year,
        "subjects": subjects,
        "authors": [author],
    }


WORKS = [
    work("w_1", "Iliad", "epic", -750, ["Trojan War"], {"id": "a_homer", "name": "Homer"}),
    work(
        "w_2",
        "Aeneid",
        "epic",
        -19,
        ["Trojan War", "Rome"],
        {"id": "a_virgil", "name": "Virgil", "birth_year": -70},
    ),
    work(
        "w_3",
        "Divine Comedy",
        "epic",
        1320,
        ["Afterlife"],
        {"id": "a_dante", "name": "Dante", "birth_year": 1265},
    ),
    work(
        "w_4", "Elements", "mathematics", -300, ["Geometry"], {"id": "a_euclid", "name": "Euclid"}
    ),
]


def test_slugify():
    assert slugify("Marcus Aurelius") == "marcus_aurelius"
    assert author_id("Émile Zola") == "a_emile_zola"


def test_generate_links_point_to_older_authors():
    edges = gi.generate(WORKS, max_links=2)
    pairs = {(e["source"], e["target"]) for e in edges}
    assert ("a_virgil", "a_homer") in pairs  # shared subject 'trojan war'
    assert ("a_dante", "a_virgil") in pairs  # same genre, closest in time
    assert all(e["source"] != "a_homer" for e in edges)  # the oldest has no influencer
    assert not any("a_euclid" in (e["source"], e["target"]) for e in edges)  # alone in its genre
    assert all(e["type"] == "INFLUENCED_BY" for e in edges)


def test_generate_respects_max_links():
    edges = gi.generate(WORKS, max_links=1)
    assert sum(e["source"] == "a_dante" for e in edges) == 1


def test_merge_edges_keeps_existing_and_skips_duplicates():
    old = [{"source": "a", "target": "b", "type": "STUDENT_OF", "origin": "curated"}]
    new = [
        {"source": "a", "target": "b", "type": "STUDENT_OF", "origin": "generated"},
        {"source": "a", "target": "c", "type": "INFLUENCED_BY", "origin": "generated"},
    ]
    merged = merge_edges(old, new)
    assert len(merged) == 2 and merged[0]["origin"] == "curated"


def test_year_from_wikidata():
    assert fi.year_from_wikidata("-0427-01-01T00:00:00Z") == -427
    assert fi.year_from_wikidata("1265-05-30T00:00:00Z") == 1265
    assert fi.year_from_wikidata(None) is None


def test_build_query_escapes_quotes():
    q = fi.build_query(['Say "hi"', "Plato"], 10)
    assert '"Say \\"hi\\""@en' in q and '"Plato"@en' in q and "LIMIT 10" in q


def row(name, other, prop, birth=None):
    r = {"name": {"value": name}, "otherLabel": {"value": other}, "prop": {"value": prop}}
    if birth:
        r["birth"] = {"value": birth}
    return r


def test_parse_bindings():
    by_name = {
        "plato": {"id": "a_plato", "name": "Plato", "birth_year": -428},
        "aristotle": {"id": "a_aristotle", "name": "Aristotle", "birth_year": -384},
    }
    rows = [
        row("Aristotle", "Plato", "STUDENT_OF", "-0383-01-01T00:00:00Z"),
        row("Plato", "Socrates", "STUDENT_OF", "-0427-01-01T00:00:00Z"),
        row("Plato", "Someone", "INFLUENCED_BY", "1900-01-01T00:00:00Z"),  # namesake: dropped
    ]
    external, edges = fi.parse_bindings(rows, by_name)
    assert {(e["source"], e["target"]) for e in edges} == {
        ("a_aristotle", "a_plato"),
        ("a_plato", "a_socrates"),
    }
    assert external == {"a_socrates": {"id": "a_socrates", "name": "Socrates"}}


def test_loader_rows_and_influence_file(tmp_path):
    authors, works = ln.build_rows(WORKS)
    assert len(authors) == 4 and len(works) == 4
    assert works[1]["author_ids"] == ["a_virgil"]
    f = tmp_path / "inf.json"
    f.write_text(
        json.dumps(
            {
                "external_authors": [{"id": "a_socrates", "name": "Socrates"}],
                "edges": [
                    {"source": "a_virgil", "target": "a_homer", "type": "INFLUENCED_BY"},
                    {"source": "a_homer", "target": "a_socrates", "type": "STUDENT_OF"},
                    {"source": "a_homer", "target": "a_ghost", "type": "STUDENT_OF"},
                    {"source": "a_homer", "target": "a_virgil", "type": "WROTE"},
                ],
            }
        )
    )
    external, by_type, skipped = ln.read_influences(f, [a["id"] for a in authors])
    assert [a["id"] for a in external] == ["a_socrates"] and external[0]["external"] is True
    assert len(by_type["INFLUENCED_BY"]) == 1 and len(by_type["STUDENT_OF"]) == 1
    assert skipped == 2  # unknown author, unknown type
