"""The documents of the benchmark: the real catalog, optionally multiplied (owner: A)."""

import random

from data_pipeline.elastic.index_config import work_to_doc


def real_corpus(collection) -> list[dict]:
    """The works of MongoDB in the flat format used by both engines."""
    docs = []
    for work in collection.find({}):
        doc = work_to_doc(work)
        docs.append(
            {
                "id": work["_id"],
                "title": doc["title"],
                "incipit": doc["incipit"],
                "genre": doc["genre"],
                "authors": doc["authors"],
                "subjects": doc["subjects"],
                "language": doc["language"],
                "year": doc["year"],
            }
        )
    return docs


def scale_corpus(docs: list[dict], target: int, seed: int = 11) -> list[dict]:
    """Add generated works until there are `target` documents.

    A generated work keeps the authors, genre and subjects of a real one, and gets a new title
    made of words drawn from the real titles (so the word frequencies stay realistic).
    """
    if target <= len(docs) or not docs:
        return list(docs)
    rng = random.Random(seed)
    pool = [w for d in docs for w in d["title"].split()]
    out = list(docs)
    for i in range(target - len(docs)):
        base = rng.choice(docs)
        length = max(2, len(base["title"].split()) + rng.randint(-1, 2))
        out.append({**base, "id": f"b_{i:07d}", "title": " ".join(rng.choices(pool, k=length))})
    return out
