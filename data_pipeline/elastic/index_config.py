"""Elasticsearch index `works`: settings, mapping and document format (task A5, owner: A)."""

INDEX = "works"

SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "filter": {
            # 'republic' -> re, rep, repu, ... : lets 'rep' find 'The Republic'
            "autocomplete_filter": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20}
        },
        "analyzer": {
            "text_folded": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            },
            "autocomplete": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding", "autocomplete_filter"],
            },
            "autocomplete_search": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            },
        },
    },
}

MAPPINGS = {
    "properties": {
        "title": {
            "type": "text",
            "analyzer": "text_folded",
            "fields": {
                "keyword": {"type": "keyword", "ignore_above": 256},
                "autocomplete": {
                    "type": "text",
                    "analyzer": "autocomplete",
                    "search_analyzer": "autocomplete_search",
                },
            },
        },
        "incipit": {"type": "text", "analyzer": "text_folded"},
        "genre": {"type": "keyword"},
        "language": {"type": "keyword"},
        "year": {"type": "integer"},
        "authors": {
            "type": "text",
            "analyzer": "text_folded",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "author_ids": {"type": "keyword"},
        "subjects": {
            "type": "text",
            "analyzer": "text_folded",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "source": {"type": "keyword"},
    }
}


def work_to_doc(work: dict) -> dict:
    """MongoDB work document -> Elasticsearch document (the id is the MongoDB _id)."""
    return {
        "title": work["title"],
        "incipit": work.get("incipit"),
        "genre": work["genre"],
        "authors": [a["name"] for a in work["authors"]],
        "author_ids": [a["id"] for a in work["authors"]],
        "language": work.get("language"),
        "year": work.get("year"),
        "subjects": work.get("subjects", []),
        "source": work.get("source"),
    }
