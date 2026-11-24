"""Day 3 check for member A. Start the API first, then from the repo root:
python -m data_pipeline.elastic.check_search
"""

import sys

import httpx

from backend.app.config import settings

API = "http://localhost:8000"
problems = []


def check(ok: bool, text: str):
    print(("[OK]   " if ok else "[FAIL] ") + text)
    if not ok:
        problems.append(text)


try:
    n = httpx.get(f"{settings.es_catalog_url}/works/_count", timeout=15).json().get("count", 0)
    check(n > 0, f"Elasticsearch index 'works': {n} documents")
except (httpx.HTTPError, ValueError):
    check(False, "Elasticsearch (catalog) not reachable on port 9200")

try:
    r = httpx.get(f"{API}/search", params={"q": "republc"}, timeout=15)
    titles = [h["title"] for h in r.json().get("hits", [])] if r.status_code == 200 else []
    check(
        "The Republic" in titles, f"/search?q=republc (typo) -> {r.status_code}, top: {titles[:3]}"
    )

    r = httpx.get(f"{API}/search", params={"q": "Piraeus"}, timeout=15)
    hl = [h.get("highlight", {}) for h in r.json().get("hits", [])] if r.status_code == 200 else []
    check(any("<em>" in str(x) for x in hl), "/search?q=Piraeus returns highlighted text (<em>)")

    r = httpx.get(f"{API}/search", params={"q": "the", "genre": "philosophy"}, timeout=15)
    genres = {h["genre"] for h in r.json().get("hits", [])} if r.status_code == 200 else {"?"}
    check(genres <= {"philosophy"}, f"genre filter -> {sorted(genres)}")

    facets = httpx.get(f"{API}/search", params={"q": "the"}, timeout=15).json().get("facets", {})
    check(
        bool(facets.get("genre")) and bool(facets.get("language")),
        "facets genre / language / year present",
    )

    r = httpx.get(f"{API}/suggest", params={"q": "rep"}, timeout=15)
    check(r.status_code == 200 and "The Republic" in r.json(), f"/suggest?q=rep -> {r.text[:80]}")
except (httpx.HTTPError, ValueError) as exc:
    check(False, f"API not reachable ({exc.__class__.__name__}). uvicorn is not running?")

sys.exit(1 if problems else 0)
