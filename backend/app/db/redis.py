"""Redis access: search cache and 'most read' list (owner: A).

The cache is optional: if Redis is down, search still works (just without cache).
The 'most read' list needs Redis, so /popular answers 503 when Redis is down.
"""

import hashlib
import json
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from backend.app.config import settings

CACHE_TTL = 60  # seconds
POPULAR_KEY = "popular:works"
HITS_KEY = "cache:hits"
MISSES_KEY = "cache:misses"


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1
    )


def make_key(prefix: str, params: dict) -> str:
    digest = hashlib.sha1(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def cache_get(key: str):
    """The cached value, or None (miss, or Redis down). Counts hits and misses."""
    try:
        r = get_redis()
        value = r.get(key)
        r.incr(HITS_KEY if value is not None else MISSES_KEY)
        return json.loads(value) if value is not None else None
    except RedisError:
        return None


def cache_set(key: str, value, ttl: int = CACHE_TTL) -> None:
    try:
        get_redis().set(key, json.dumps(value), ex=ttl)
    except RedisError:
        pass


def cache_stats() -> dict:
    r = get_redis()
    hits, misses = int(r.get(HITS_KEY) or 0), int(r.get(MISSES_KEY) or 0)
    total = hits + misses
    return {"hits": hits, "misses": misses, "hit_ratio": round(hits / total, 3) if total else None}


def record_view(work_id: str) -> None:
    """Count one view of a work (ZINCRBY popular:works 1 <id>). Never breaks the page."""
    try:
        get_redis().zincrby(POPULAR_KEY, 1, work_id)
    except RedisError:
        pass


def top_works(n: int = 10) -> list[tuple[str, int]]:
    """[(work_id, views)], most read first. Raises RedisError when Redis is down."""
    rows = get_redis().zrevrange(POPULAR_KEY, 0, n - 1, withscores=True)
    return [(work_id, int(score)) for work_id, score in rows]
