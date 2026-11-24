import mongomock
import pytest
from elastic_transport import ConnectionError as TransportConnectionError
from fastapi.testclient import TestClient

from backend.app.db import es as search_db
from backend.app.main import app
from data_pipeline.elastic import index_config as ic
from data_pipeline.elastic import load_es

client = TestClient(app)

RESPONSE = {
    "hits": {
        "total": {"value": 42},
        "hits": [
            {
                "_id": "w_0003",
                "_score": 7.3,
                "_source": {
                    "title": "The Republic",
                    "genre": "philosophy",
                    "authors": ["Plato"],
                    "year": -375,
                },
                "highlight": {"incipit": ["I went down yesterday to the <em>Piraeus</em>"]},
            },
            {
                "_id": "w_0004",
                "_score": 1.0,
                "_source": {"title": "Ethics", "genre": "philosophy", "authors": ["Aristotle"]},
            },
        ],
    },
    "aggregations": {
        "genre": {"buckets": [{"key": "philosophy", "doc_count": 5}]},
        "language": {"buckets": [{"key": "en", "doc_count": 20}]},
        "year": {"buckets": [{"key": -500.0, "doc_count": 3}]},
    },
}


def test_search_body_without_filters():
    body = search_db.build_search_body("republc")
    mm = body["query"]["bool"]["must"][0]["multi_match"]
    assert mm["query"] == "republc" and mm["fuzziness"] == "AUTO"
    assert body["query"]["bool"]["filter"] == []
    assert body["from"] == 0 and body["size"] == 10 and body["track_total_hits"] is True
    assert set(body["aggs"]) == {"genre", "language", "year"}


def test_search_body_filters_and_pagination():
    body = search_db.build_search_body("war", "history", "en", -500, 100, page=3, size=20)
    assert body["from"] == 40 and body["size"] == 20
    assert body["query"]["bool"]["filter"] == [
        {"term": {"genre": "history"}},
        {"term": {"language": "en"}},
        {"range": {"year": {"gte": -500, "lte": 100}}},
    ]
    only_from = search_db.build_search_body("war", year_from=1000)["query"]["bool"]["filter"]
    assert only_from == [{"range": {"year": {"gte": 1000}}}]


def test_parse_search_follows_the_contract():
    out = search_db.parse_search(RESPONSE, page=1, size=10)
    assert out["total"] == 42 and out["page"] == 1 and out["size"] == 10
    first = out["hits"][0]
    assert first == {
        "id": "w_0003",
        "title": "The Republic",
        "genre": "philosophy",
        "authors": ["Plato"],
        "year": -375,
        "score": 7.3,
        "highlight": {"incipit": ["I went down yesterday to the <em>Piraeus</em>"]},
    }
    assert "highlight" not in out["hits"][1]
    assert out["facets"]["genre"] == [{"key": "philosophy", "count": 5}]
    assert out["facets"]["year"] == [{"key": -500, "count": 3}]


def test_suggest_body_and_parse():
    body = search_db.build_suggest_body("the rep")
    assert body["query"]["match"]["title.autocomplete"]["operator"] == "and"
    resp = {
        "hits": {
            "hits": [{"_source": {"title": t}} for t in ["The Republic", "The Republic", "The Rep"]]
        }
    }
    assert search_db.parse_suggest(resp) == ["The Republic", "The Rep"]


@pytest.fixture
def fake_es(monkeypatch):
    seen = {}

    def fake_search(q, genre, language, year_from, year_to, page, size):
        seen.update(q=q, genre=genre, page=page, size=size)
        return {"total": 0, "page": page, "size": size, "hits": [], "facets": {}}

    monkeypatch.setattr(search_db, "search_works", fake_search)
    monkeypatch.setattr(search_db, "suggest", lambda q: ["The Republic"])
    return seen


def test_search_endpoint(fake_es):
    r = client.get("/search", params={"q": "republc", "genre": "philosophy", "page": 2})
    assert r.status_code == 200
    assert fake_es == {"q": "republc", "genre": "philosophy", "page": 2, "size": 10}
    assert client.get("/suggest", params={"q": "rep"}).json() == ["The Republic"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "x", "page": 0},
        {"q": "x", "size": 51},
        {"q": "x", "year_from": 100, "year_to": -100},
        {"q": "x", "page": 201, "size": 50},
    ],
)
def test_search_validation(fake_es, params):
    assert client.get("/search", params=params).status_code == 422


def test_elasticsearch_down_is_503(monkeypatch):
    def boom(*args):
        raise TransportConnectionError("down")

    monkeypatch.setattr(search_db, "search_works", boom)
    r = client.get("/search", params={"q": "x"})
    assert r.status_code == 503 and "load_es" in r.json()["detail"]


# ---- index and loader ----


def test_every_analyzer_used_in_the_mapping_is_defined():
    defined = set(ic.SETTINGS["analysis"]["analyzer"]) | {"standard"}
    used = set()

    def walk(node):
        for key, value in node.items():
            if key in ("analyzer", "search_analyzer"):
                used.add(value)
            elif isinstance(value, dict):
                walk(value)

    walk(ic.MAPPINGS)
    assert used <= defined, used - defined
    assert (
        ic.MAPPINGS["properties"]["title"]["fields"]["autocomplete"]["analyzer"] == "autocomplete"
    )


def test_work_to_doc():
    work = {
        "_id": "w_0003",
        "title": "The Republic",
        "genre": "philosophy",
        "language": "en",
        "year": -375,
        "incipit": None,
        "subjects": ["Justice"],
        "source": "sample",
        "authors": [{"id": "a_plato", "name": "Plato", "birth_year": -428}],
    }
    doc = ic.work_to_doc(work)
    assert doc["authors"] == ["Plato"] and doc["author_ids"] == ["a_plato"]
    assert doc["title"] == "The Republic" and doc["incipit"] is None


def test_actions_use_the_mongo_id():
    coll = mongomock.MongoClient()["pinakes"]["works"]
    coll.insert_many(
        [
            {"_id": "w_1", "title": "A", "genre": "epic", "authors": [{"id": "a_x", "name": "X"}]},
            {"_id": "w_2", "title": "B", "genre": "law", "authors": [{"id": "a_y", "name": "Y"}]},
        ]
    )
    acts = list(load_es.actions(coll))
    assert [a["_id"] for a in acts] == ["w_1", "w_2"]
    assert all(a["_index"] == "works" and a["_op_type"] == "index" for a in acts)
