"""Elasticsearch access and search queries (owner: A). Used by routers/search.py."""

from functools import lru_cache

from elasticsearch import Elasticsearch

from backend.app.config import settings

INDEX = "works"
YEAR_BUCKET = 100  # width of the year facet (years)
SEARCH_FIELDS = ["title^3", "authors^2", "subjects", "incipit"]


@lru_cache(maxsize=1)
def get_client() -> Elasticsearch:
    return Elasticsearch(settings.es_catalog_url, request_timeout=5)


def build_search_body(
    q: str,
    genre: str | None = None,
    language: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    page: int = 1,
    size: int = 10,
) -> dict:
    filters = []
    if genre:
        filters.append({"term": {"genre": genre}})
    if language:
        filters.append({"term": {"language": language}})
    if year_from is not None or year_to is not None:
        bounds = {}
        if year_from is not None:
            bounds["gte"] = year_from
        if year_to is not None:
            bounds["lte"] = year_to
        filters.append({"range": {"year": bounds}})
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": SEARCH_FIELDS,
                            "fuzziness": "AUTO",  # tolerates typos: 'republc' finds 'Republic'
                        }
                    }
                ],
                "filter": filters,
            }
        },
        "highlight": {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "encoder": "html",  # escapes the text, so <em> is the only tag in the result
            "fields": {
                "incipit": {"fragment_size": 150, "number_of_fragments": 1},
                "title": {"number_of_fragments": 0},
            },
        },
        "aggs": {
            "genre": {"terms": {"field": "genre", "size": 20}},
            "language": {"terms": {"field": "language", "size": 20}},
            "year": {"histogram": {"field": "year", "interval": YEAR_BUCKET, "min_doc_count": 1}},
        },
        "_source": ["title", "genre", "authors", "year"],
        "from": (page - 1) * size,
        "size": size,
        "track_total_hits": True,
    }


def parse_search(resp: dict, page: int, size: int) -> dict:
    hits = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        hit = {
            "id": h["_id"],
            "title": src.get("title"),
            "genre": src.get("genre"),
            "authors": src.get("authors", []),
            "year": src.get("year"),
            "score": h.get("_score"),
        }
        if h.get("highlight"):
            hit["highlight"] = h["highlight"]
        hits.append(hit)
    aggs = resp.get("aggregations", {})

    def buckets(name, cast=lambda k: k):
        return [
            {"key": cast(b["key"]), "count": b["doc_count"]}
            for b in aggs.get(name, {}).get("buckets", [])
        ]

    return {
        "total": resp["hits"]["total"]["value"],
        "page": page,
        "size": size,
        "hits": hits,
        "facets": {
            "genre": buckets("genre"),
            "language": buckets("language"),
            "year": buckets("year", int),
        },
    }


def build_suggest_body(q: str, size: int = 10) -> dict:
    return {
        "query": {"match": {"title.autocomplete": {"query": q, "operator": "and"}}},
        "_source": ["title"],
        "size": size,
    }


def parse_suggest(resp: dict, limit: int = 5) -> list[str]:
    titles: list[str] = []
    for h in resp["hits"]["hits"]:
        title = h["_source"]["title"]
        if title not in titles:
            titles.append(title)
    return titles[:limit]


def search_works(q, genre=None, language=None, year_from=None, year_to=None, page=1, size=10):
    body = build_search_body(q, genre, language, year_from, year_to, page, size)
    return parse_search(get_client().search(index=INDEX, body=body), page, size)


def suggest(q: str) -> list[str]:
    return parse_suggest(get_client().search(index=INDEX, body=build_suggest_body(q)))
