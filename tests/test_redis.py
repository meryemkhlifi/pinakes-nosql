import fakeredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from backend.app.db import mongo as catalog_db
from backend.app.db import redis as redis_db
from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_db, "get_redis", lambda: r)
    return r


def test_cache_roundtrip_ttl_and_stats(fake_redis):
    key = redis_db.make_key("search", {"q": "republic"})
    assert redis_db.cache_get(key) is None  # miss
    redis_db.cache_set(key, {"total": 1})
    assert 0 < fake_redis.ttl(key) <= 60
    assert redis_db.cache_get(key) == {"total": 1}  # hit
    assert redis_db.cache_get(key) == {"total": 1}  # hit
    assert redis_db.cache_stats() == {"hits": 2, "misses": 1, "hit_ratio": 0.667}


def test_make_key_ignores_parameter_order():
    a = redis_db.make_key("search", {"q": "x", "page": 1})
    assert a == redis_db.make_key("search", {"page": 1, "q": "x"})
    assert a != redis_db.make_key("search", {"q": "x", "page": 2})


def test_views_and_top_works(fake_redis):
    for work_id in ["w_1", "w_2", "w_2", "w_2", "w_3", "w_3"]:
        redis_db.record_view(work_id)
    assert redis_db.top_works(2) == [("w_2", 3), ("w_3", 2)]
    assert fake_redis.zscore("popular:works", "w_1") == 1


class DeadRedis:
    def __getattr__(self, name):
        def boom(*args, **kwargs):
            raise RedisConnectionError("down")

        return boom


@pytest.fixture
def dead_redis(monkeypatch):
    monkeypatch.setattr(redis_db, "get_redis", lambda: DeadRedis())


def test_cache_and_views_survive_a_dead_redis(dead_redis):
    assert redis_db.cache_get("k") is None
    redis_db.cache_set("k", {"a": 1})  # no exception
    redis_db.record_view("w_1")  # no exception


def test_popular_endpoint(fake_redis, monkeypatch):
    fake_redis.zadd("popular:works", {"w_0003": 57, "w_0001": 12})
    monkeypatch.setattr(catalog_db, "titles_of", lambda ids: {"w_0003": "The Republic"})
    r = client.get("/popular", params={"n": 5})
    assert r.status_code == 200
    assert r.json() == [
        {"id": "w_0003", "title": "The Republic", "views": 57},
        {"id": "w_0001", "title": "w_0001", "views": 12},  # no title found: the id is shown
    ]


def test_popular_validation_and_redis_down(dead_redis):
    assert client.get("/popular", params={"n": 0}).status_code == 422
    assert client.get("/popular").status_code == 503
