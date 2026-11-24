import json
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from backend.app.db import mongo as catalog_db
from backend.app.db import redis as redis_db
from backend.app.main import app
from data_pipeline.mongo import build_works as bw
from data_pipeline.mongo import load_mongo, make_sample

client = TestClient(app)
# Only the 20 hand-made works: the file can also hold generated works (300-work sample).
_ALL = json.loads(Path("data/sample/works_sample.json").read_text(encoding="utf-8"))
SAMPLE = [w for w in _ALL if w.get("source") == "sample"]


@pytest.fixture
def collection():
    coll = mongomock.MongoClient()["pinakes"]["works"]
    load_mongo.load(SAMPLE, coll)
    load_mongo.create_indexes(coll)
    return coll


def test_load_is_idempotent(collection):
    assert load_mongo.load(SAMPLE, collection) == len(SAMPLE)


def test_indexes_exist(collection):
    assert {"genre", "authors_name", "authors_id"} <= set(collection.index_information())


def test_list_genres(collection):
    genres = {g["genre"]: g["count"] for g in catalog_db.list_genres(collection)}
    assert genres["epic"] == 4 and genres["philosophy"] == 3


def test_authors_of_genre(collection):
    authors = {a["author_id"]: a for a in catalog_db.authors_of_genre("epic", collection)}
    assert [w["title"] for w in authors["a_homer"]["works"]] == ["Iliad", "Odyssey"]
    assert authors["a_dante"]["works"][0]["title"] == "Divine Comedy"
    assert catalog_db.authors_of_genre("nope", collection) == []


def test_get_work(collection):
    assert catalog_db.get_work("w_0003", collection)["title"] == "The Republic"
    assert catalog_db.get_work("w_9999", collection) is None


@pytest.fixture
def fake_db(monkeypatch):
    views = []
    monkeypatch.setattr(redis_db, "record_view", views.append)
    monkeypatch.setattr(catalog_db, "list_genres", lambda: [{"genre": "epic", "count": 4}])
    monkeypatch.setattr(
        catalog_db,
        "authors_of_genre",
        lambda g: [] if g == "nope" else [{"author_id": "a_homer", "name": "Homer", "works": []}],
    )
    monkeypatch.setattr(
        catalog_db, "get_work", lambda i: None if i == "w_9999" else {"_id": i, "title": "x"}
    )
    return views


def test_opening_a_work_counts_one_view(fake_db):
    client.get("/catalog/works/w_0001")
    client.get("/catalog/works/w_9999")  # unknown work: no view
    assert fake_db == ["w_0001"]


def test_catalog_endpoints(fake_db):
    assert client.get("/catalog/genres").json() == [{"genre": "epic", "count": 4}]
    assert client.get("/catalog/genres/epic/authors").json()[0]["author_id"] == "a_homer"
    assert client.get("/catalog/genres/nope/authors").status_code == 404
    assert client.get("/catalog/works/w_0001").json()["_id"] == "w_0001"
    assert client.get("/catalog/works/w_9999").status_code == 404


def test_mongo_down_is_503(monkeypatch):
    def boom():
        raise ServerSelectionTimeoutError("down")

    monkeypatch.setattr(catalog_db, "list_genres", boom)
    assert client.get("/catalog/genres").status_code == 503


# ---- build_works ----


def test_parse_author():
    plato = bw.parse_author("Plato, 427? BCE-347? BCE")
    assert plato == {"id": "a_plato", "name": "Plato", "birth_year": -427, "bio": None}
    cicero = bw.parse_author("Cicero, Marcus Tullius, 106 BCE-43 BCE")
    assert cicero["name"] == "Marcus Tullius Cicero" and cicero["birth_year"] == -106
    assert bw.parse_author("Shakespeare, William, 1564-1616")["birth_year"] == 1564
    assert bw.parse_author("Homer")["birth_year"] is None
    assert bw.parse_author("Jowett, Benjamin, 1817-1893 [Translator]") is None
    assert bw.parse_author("Anonymous") is None
    assert bw.parse_author("Zola, Émile, 1840-1902")["id"] == "a_emile_zola"


def test_guess_genre():
    assert bw.guess_genre("Greek drama (Tragedy)") == "tragedy"
    assert bw.guess_genre("Epic poetry, Greek -- Translations") == "epic"
    assert bw.guess_genre("Ethics; Philosophy, Ancient") == "philosophy"
    assert bw.guess_genre("Cookery") == "miscellany"


def row(title, authors, subjects="", lang="en", kind="Text"):
    return {
        "Type": kind,
        "Title": title,
        "Language": lang,
        "Authors": authors,
        "Subjects": subjects,
        "Bookshelves": "",
    }


def test_build_works_filters_and_ids():
    rows = [
        row("The Republic", "Plato, 427? BCE-347? BCE", "Political science; Justice"),
        row("The Republic", "Plato, 427? BCE-347? BCE"),  # duplicate
        row("Hamlet", "Shakespeare, William, 1564-1616", "Tragedies"),
        row("Modern novel", "Writer, Some, 1950-"),  # too recent
        row("Le Cid", "Corneille, Pierre, 1606-1684", lang="fr"),  # wrong language
        row("A sound recording", "Plato, 427? BCE-347? BCE", kind="Sound"),
        row("No author", ""),
    ]
    seed = [SAMPLE[0], SAMPLE[1]]
    works = bw.build_works(rows, seed=seed)
    assert [w["_id"] for w in works] == ["w_0001", "w_0002", "w_0003", "w_0004"]
    assert [w["title"] for w in works[2:]] == ["The Republic", "Hamlet"]  # oldest author first
    assert works[2]["year"] == -397 and works[2]["source"] == "gutenberg"
    assert works[3]["genre"] == "tragedy"


def test_built_works_follow_the_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(Path("contracts/schema_work.json").read_text(encoding="utf-8"))
    for w in bw.build_works([row("Hamlet", "Shakespeare, William, 1564-1616", "Tragedies")]):
        jsonschema.validate(w, schema)


def test_make_sample_keeps_hand_made_and_all_genres():
    generated = [
        {"_id": f"w_{100 + i:04d}", "genre": g, "title": f"t{i}", "source": "gutenberg"}
        for i, g in enumerate(["epic"] * 30 + ["law"] * 3 + ["comedy"] * 3)
    ]
    sample = make_sample.pick(SAMPLE + generated, size=30)
    assert len(sample) == 30
    assert {w["_id"] for w in SAMPLE} <= {w["_id"] for w in sample}
    assert {"law", "comedy"} <= {w["genre"] for w in sample}
