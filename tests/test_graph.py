import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from backend.app.db import neo4j as graph_db
from backend.app.main import app

client = TestClient(app)

PLATO = {"id": "a_plato", "name": "Plato"}
ARISTOTLE = {"id": "a_aristotle", "name": "Aristotle"}


@pytest.fixture
def fake_neo4j(monkeypatch):
    monkeypatch.setattr(
        graph_db, "existing_author_ids", lambda ids: {i for i in ids if i != "a_nobody"}
    )
    monkeypatch.setattr(
        graph_db,
        "shortest_path",
        lambda a, b: {
            "found": True,
            "length": 1,
            "nodes": [ARISTOTLE, PLATO],
            "edges": [{"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF"}],
        },
    )
    monkeypatch.setattr(
        graph_db, "get_author", lambda i: None if i == "a_nobody" else {"id": i, "name": i}
    )
    monkeypatch.setattr(
        graph_db, "neighbors", lambda i, depth: {"nodes": [PLATO], "edges": [], "depth": depth}
    )
    monkeypatch.setattr(
        graph_db, "top_influence", lambda n: [{"author_id": "a_plato", "name": "Plato", "score": 1}]
    )


def test_path_ok(fake_neo4j):
    r = client.get("/graph/path", params={"from": "a_aristotle", "to": "a_plato"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["length"] == 1
    assert body["edges"][0]["type"] == "STUDENT_OF"


def test_path_unknown_author_is_404(fake_neo4j):
    r = client.get("/graph/path", params={"from": "a_nobody", "to": "a_plato"})
    assert r.status_code == 404
    assert "a_nobody" in r.json()["detail"]


def test_path_needs_both_parameters():
    assert client.get("/graph/path", params={"from": "a_plato"}).status_code == 422


def test_neighbors_ok_and_depth_checked(fake_neo4j):
    assert client.get("/graph/neighbors/a_plato?depth=3").json()["depth"] == 3
    assert client.get("/graph/neighbors/a_plato?depth=9").status_code == 422
    assert client.get("/graph/neighbors/a_nobody").status_code == 404


def test_top_ok_and_n_checked(fake_neo4j):
    assert client.get("/graph/influence/top?n=5").json()[0]["author_id"] == "a_plato"
    assert client.get("/graph/influence/top?n=0").status_code == 422


def test_neo4j_down_is_503(monkeypatch):
    def boom(ids):
        raise ServiceUnavailable("down")

    monkeypatch.setattr(graph_db, "existing_author_ids", boom)
    r = client.get("/graph/path", params={"from": "a_plato", "to": "a_aristotle"})
    assert r.status_code == 503


def test_pagerank_most_cited_wins_and_sums_to_one():
    # b and c were influenced by a; d was influenced by b
    scores = graph_db.pagerank("abcde", [("b", "a"), ("c", "a"), ("d", "b")])
    assert max(scores, key=scores.get) == "a"
    assert scores["a"] > scores["b"] > scores["d"]
    assert scores["e"] == pytest.approx(min(scores.values()))  # isolated author
    assert sum(scores.values()) == pytest.approx(1.0)


def test_pagerank_empty():
    assert graph_db.pagerank([], []) == {}
