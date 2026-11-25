import json
import os

import mongomock
import pytest

from benchmarks.es_vs_postgres import corpus
from benchmarks.es_vs_postgres.engines import EsSearch, PgSearch
from benchmarks.es_vs_postgres.measure import percentile, summarize
from benchmarks.es_vs_postgres.outputs import make_chart, table_markdown, write_results
from benchmarks.es_vs_postgres.run import DEFAULT_QUERIES, parse_query, run_queries

PG_TEST_URL = os.getenv("PG_TEST_URL")
needs_pg = pytest.mark.skipif(not PG_TEST_URL, reason="set PG_TEST_URL to test against PostgreSQL")


def doc(i, title, genre="philosophy", authors=("Plato",), subjects=("Justice",)):
    return {
        "id": f"w_{i:04d}", "title": title, "incipit": None, "genre": genre,
        "authors": list(authors), "subjects": list(subjects), "language": "en", "year": -375,
    }  # fmt: skip


DOCS = [
    doc(1, "The Republic"),
    doc(2, "The Roman Republic and its history", "history", ("Livy",), ("Rome",)),
    doc(3, "History of Rome", "history", ("Livy",), ("Rome", "History")),
    doc(4, "Poetics", "lyric", ("Aristotle",), ("Poetry",)),
    doc(5, "Nicomachean Ethics", "philosophy", ("Aristotle",), ("Ethics",)),
]


def test_percentile_and_summary():
    assert percentile(list(range(1, 101)), 50) == 50.5
    s = summarize([2.0, 4.0, 6.0])
    assert s["p50_ms"] == 4.0 and s["runs"] == 3


def test_real_corpus_reads_mongo_documents():
    coll = mongomock.MongoClient()["pinakes"]["works"]
    coll.insert_one(
        {
            "_id": "w_0003",
            "title": "The Republic",
            "genre": "philosophy",
            "language": "en",
            "year": -375,
            "subjects": ["Justice"],
            "authors": [{"id": "a_plato", "name": "Plato"}],
        }  # fmt: skip
    )
    docs = corpus.real_corpus(coll)
    assert docs == [
        {
            "id": "w_0003",
            "title": "The Republic",
            "incipit": None,
            "genre": "philosophy",
            "authors": ["Plato"],
            "subjects": ["Justice"],
            "language": "en",
            "year": -375,
        }  # fmt: skip
    ]


def test_scale_corpus():
    big = corpus.scale_corpus(DOCS, 200)
    assert len(big) == 200 and big[:5] == DOCS
    assert len({d["id"] for d in big}) == 200
    generated = big[5:]
    pool = {w for d in DOCS for w in d["title"].split()}
    assert all(set(d["title"].split()) <= pool for d in generated)
    assert all(d["authors"] and d["genre"] for d in generated)
    assert big == corpus.scale_corpus(DOCS, 200)  # same seed, same corpus
    assert corpus.scale_corpus(DOCS, 3) == DOCS  # never smaller than the real catalog


def test_es_queries_exact_and_fuzzy():
    exact = EsSearch.query("history of rome", "exact")["multi_match"]
    assert exact["operator"] == "and" and "fuzziness" not in exact
    fuzzy = EsSearch.query("republc", "fuzzy")["multi_match"]
    assert fuzzy["fuzziness"] == "AUTO" and "operator" not in fuzzy
    assert "title^3" in exact["fields"]


class FakeEs:
    def __init__(self):
        self.calls = []

    def search(self, index, body):
        self.calls.append(("search", index, body))
        return {"took": 4, "hits": {"hits": [{"_id": "w_1", "_source": {"title": "The Republic"}}]}}

    def count(self, index, query):
        self.calls.append(("count", index, query))
        return {"count": 12}


def test_es_engine_search_count_and_took():
    client = FakeEs()
    es = EsSearch(client, "bench_works")
    assert es.search("republc", "fuzzy") == [("w_1", "The Republic")]
    assert es.took_ms == [4] and es.count("republc", "fuzzy") == 12
    kind, index, body = client.calls[0]
    assert (
        index == "bench_works" and body["size"] == 10 and body["query"]["multi_match"]["fuzziness"]
    )


class FakeEngine:
    def __init__(self, titles):
        self.titles, self.calls = titles, 0

    def search(self, text, kind):
        self.calls += 1
        return [(f"w_{i}", t) for i, t in enumerate(self.titles)]

    def count(self, text, kind):
        return len(self.titles)


def test_parse_query_and_defaults():
    assert parse_query("republc:fuzzy") == ("republc", "fuzzy")
    assert parse_query("history of rome") == ("history of rome", "exact")
    assert parse_query("a:b") == ("a:b", "exact")
    assert [k for _, k in DEFAULT_QUERIES] == ["exact", "exact", "fuzzy"]


def sample_rows():
    return run_queries(
        {"Elasticsearch": FakeEngine(["The Republic", "B"]), "PostgreSQL": FakeEngine([])},
        [("republic", "exact"), ("republc", "fuzzy")],
        runs=10,
        warmup=2,
    )


def test_run_queries_rows():
    rows = sample_rows()
    assert len(rows) == 4
    es = next(r for r in rows if r["engine"] == "Elasticsearch" and r["query"] == "republc")
    assert es["kind"] == "fuzzy" and es["matches"] == 2 and es["runs"] == 10
    assert es["top_titles"] == ["The Republic", "B"]
    pg = next(r for r in rows if r["engine"] == "PostgreSQL")
    assert pg["top_titles"] == [] and pg["matches"] == 0


def test_outputs(tmp_path):
    rows = sample_rows()
    table = table_markdown(rows)
    assert "| republic | exact | 2 | 0 |" in table and "(none)" in table
    meta = {"docs": 50000, "real_docs": 5000, "runs": 10, "warmup": 2}
    out = write_results(rows, tmp_path, meta)
    assert json.loads((out / "results.json").read_text())["meta"]["docs"] == 50000
    assert "The Republic | B" in (out / "results.csv").read_text()
    assert "50000 documents" in (out / "results.md").read_text()
    pytest.importorskip("matplotlib")
    assert make_chart(rows, tmp_path / "chart.png", "test").stat().st_size > 5000


@pytest.fixture
def pg():
    engine = PgSearch(PG_TEST_URL)
    engine.load(DOCS)
    yield engine
    engine.close()


@needs_pg
def test_postgres_full_text_search(pg):
    titles = [t for _, t in pg.search("republic", "exact")]
    assert "The Republic" in titles and "The Roman Republic and its history" in titles
    found = [t for _, t in pg.search("history of rome", "exact")]
    assert found[0] == "History of Rome"  # best rank: both words are in the title
    assert pg.count("republic", "exact") == 2


@needs_pg
def test_postgres_trigrams_forgive_a_typo(pg):
    assert pg.search("republc", "fuzzy")[0][1] == "The Republic"
    assert pg.search("republc", "exact") == []  # full-text search alone has no fuzziness
    assert pg.count("republc", "fuzzy") >= 1
