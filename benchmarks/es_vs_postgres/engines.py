"""The two search engines of the benchmark: Elasticsearch and PostgreSQL (owner: A).

Both work on a COPY of the catalog (index bench_works / table bench_works), so the real index
of the project is never touched. A query is a pair (text, kind):
  kind "exact": all the words must be there. ES: multi_match with operator AND.
                PostgreSQL: full-text search (tsvector, GIN index, ts_rank_cd).
  kind "fuzzy": the text has a typo. ES: fuzziness AUTO. PostgreSQL: trigrams (pg_trgm, GIN).
"""

import psycopg

from data_pipeline.elastic.index_config import MAPPINGS, SETTINGS

BATCH = 2000
FIELDS = ["title^3", "authors^2", "subjects", "incipit"]

PG_SCHEMA = """
DROP TABLE IF EXISTS bench_works;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE bench_works (
  id text PRIMARY KEY, title text NOT NULL, incipit text, genre text, authors text,
  subjects text, year integer,
  search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(authors, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(subjects, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(incipit, '')), 'D')) STORED
);
"""
PG_INDEXES = """
CREATE INDEX bench_works_fts ON bench_works USING gin (search_vector);
CREATE INDEX bench_works_trgm ON bench_works USING gin (title gin_trgm_ops);
ANALYZE bench_works;
"""
SQL_EXACT = """
SELECT id, title FROM bench_works, websearch_to_tsquery('english', %(q)s) AS q
WHERE search_vector @@ q ORDER BY ts_rank_cd(search_vector, q) DESC LIMIT 10
"""
SQL_FUZZY = """
SELECT id, title FROM bench_works WHERE title %% %(q)s
ORDER BY similarity(title, %(q)s) DESC LIMIT 10
"""
SQL_COUNT_EXACT = (
    "SELECT count(*) FROM bench_works WHERE search_vector @@ websearch_to_tsquery('english', %(q)s)"
)
SQL_COUNT_FUZZY = "SELECT count(*) FROM bench_works WHERE title %% %(q)s"


class PgSearch:
    name = "PostgreSQL"

    def __init__(self, url: str, timeout_ms: int = 20000):
        self.conn = psycopg.connect(url, autocommit=True)
        self.conn.execute(f"SET statement_timeout = {int(timeout_ms)}")

    def load(self, docs: list[dict]) -> None:
        for statement in PG_SCHEMA.split(";"):
            if statement.strip():
                self.conn.execute(statement)
        columns = "id, title, incipit, genre, authors, subjects, year"
        with (
            self.conn.cursor() as cur,
            cur.copy(f"COPY bench_works ({columns}) FROM STDIN") as copy,
        ):
            for d in docs:
                copy.write_row(
                    (
                        d["id"],
                        d["title"],
                        d["incipit"],
                        d["genre"],
                        " ".join(d["authors"]),
                        " ".join(d["subjects"]),
                        d["year"],
                    )  # fmt: skip
                )
        for statement in PG_INDEXES.split(";"):
            if statement.strip():
                self.conn.execute(statement)

    def search(self, text: str, kind: str) -> list[tuple[str, str]]:
        sql = SQL_FUZZY if kind == "fuzzy" else SQL_EXACT
        return [(r[0], r[1]) for r in self.conn.execute(sql, {"q": text}).fetchall()]

    def count(self, text: str, kind: str) -> int:
        sql = SQL_COUNT_FUZZY if kind == "fuzzy" else SQL_COUNT_EXACT
        return self.conn.execute(sql, {"q": text}).fetchone()[0]

    def close(self) -> None:
        self.conn.close()


class EsSearch:
    name = "Elasticsearch"

    def __init__(self, client, index: str = "bench_works"):
        self.client, self.index = client, index
        self.took_ms: list[int] = []  # time measured by Elasticsearch itself

    @staticmethod
    def query(text: str, kind: str) -> dict:
        multi = {"query": text, "fields": FIELDS}
        if kind == "fuzzy":
            multi["fuzziness"] = "AUTO"
        else:
            multi["operator"] = "and"
        return {"multi_match": multi}

    def load(self, docs: list[dict]) -> None:
        from elasticsearch import helpers

        if self.client.indices.exists(index=self.index):
            self.client.indices.delete(index=self.index)
        self.client.indices.create(index=self.index, settings=SETTINGS, mappings=MAPPINGS)
        actions = (
            {
                "_index": self.index,
                "_id": d["id"],
                "_source": {
                    k: d[k]
                    for k in (
                        "title",
                        "incipit",
                        "genre",
                        "authors",
                        "subjects",
                        "language",
                        "year",
                    )
                },
            }
            for d in docs
        )
        helpers.bulk(self.client, actions, chunk_size=BATCH)
        self.client.indices.refresh(index=self.index)

    def search(self, text: str, kind: str) -> list[tuple[str, str]]:
        body = {"query": self.query(text, kind), "size": 10, "_source": ["title"]}
        resp = self.client.search(index=self.index, body=body)
        self.took_ms.append(resp["took"])
        return [(h["_id"], h["_source"]["title"]) for h in resp["hits"]["hits"]]

    def count(self, text: str, kind: str) -> int:
        return self.client.count(index=self.index, query=self.query(text, kind))["count"]

    def cleanup(self) -> None:
        self.client.indices.delete(index=self.index, ignore_unavailable=True)
