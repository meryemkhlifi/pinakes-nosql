import json
import random
from datetime import datetime, timedelta, timezone

import httpx

from scripts import bot_simulator as bot
from scripts import zscore_alert as za

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def baseline(minutes=3, ips=12, seed=1):
    """Normal traffic: every IP makes 2 to 6 requests per minute."""
    rng = random.Random(seed)
    return [
        (NOW - timedelta(minutes=m), f"198.51.100.{i}", rng.randint(2, 6))
        for m in range(minutes)
        for i in range(1, ips + 1)
    ]


def test_burst_is_detected():
    counts = baseline() + [(NOW, "203.0.113.50", 300)]
    alerts = za.find_alerts(counts, now=NOW)
    assert len(alerts) == 1
    a = alerts[0]
    assert a["client_ip"] == "203.0.113.50" and a["requests_per_min"] == 300
    assert a["z_score"] > 3 and a["minute"] == "2026-11-24T12:00:00Z"
    assert a["mean"] < 15 and a["std"] > 0


def test_z_score_formula():
    counts = [(NOW, f"10.0.0.{i}", c) for i, c in enumerate([2, 4, 4, 4, 5, 5, 7, 9, 3, 7])]
    counts.append((NOW, "10.0.0.99", 40))
    alerts = za.find_alerts(counts, threshold=2, min_requests=1, now=NOW)
    values = [c for *_, c in counts]
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    assert alerts[0]["z_score"] == round((40 - mean) / std, 2)


def test_normal_traffic_gives_no_alert():
    assert za.find_alerts(baseline(), now=NOW) == []


def test_not_enough_history_gives_no_alert():
    assert za.find_alerts([(NOW, "a", 3), (NOW, "b", 400)], now=NOW) == []


def test_identical_counts_give_no_alert():
    assert za.find_alerts([(NOW, f"ip{i}", 5) for i in range(20)], now=NOW) == []


def test_old_burst_is_not_reported_again():
    counts = baseline() + [(NOW - timedelta(minutes=10), "203.0.113.50", 300)]
    assert za.find_alerts(counts, now=NOW) == []


def test_small_burst_below_min_requests_is_ignored():
    counts = baseline() + [(NOW, "203.0.113.50", 15)]
    assert za.find_alerts(counts, now=NOW, min_requests=20) == []
    assert za.find_alerts(counts, now=NOW, min_requests=10)  # the z-score alone would fire


def test_alert_id_is_one_per_ip_and_minute():
    a = za.find_alerts(baseline() + [(NOW, "203.0.113.50", 300)], now=NOW)[0]
    assert za.alert_id(a) == "203.0.113.50_2026-11-24T12:00:00Z"


def es_transport(requests: list, created=True):
    burst_ms = int(NOW.timestamp() * 1000)
    buckets = [
        {
            "key": burst_ms - 60_000 * m,
            "ips": {
                "buckets": [
                    {"key": f"198.51.100.{i}", "doc_count": 3 + i % 3} for i in range(1, 13)
                ]
            },
        }
        for m in range(1, 4)
    ]
    buckets.append(
        {"key": burst_ms, "ips": {"buckets": [{"key": "203.0.113.50", "doc_count": 300}]}}
    )

    def handler(request: httpx.Request):
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, json={"aggregations": {"per_minute": {"buckets": buckets}}})
        if request.method == "HEAD":
            return httpx.Response(404)
        return httpx.Response(200, json={"result": "created" if created else "updated"})

    return httpx.MockTransport(handler)


def test_fetch_counts_parses_the_aggregation():
    seen = []
    client = httpx.Client(transport=es_transport(seen))
    rows = za.fetch_counts(client, "http://es", 30)
    assert len(rows) == 12 * 3 + 1
    assert rows[-1] == (NOW, "203.0.113.50", 300)
    assert seen == [("POST", "/pinakes-logs-*/_search")]


def test_check_once_saves_and_reports_only_new_alerts(monkeypatch):
    class Args:
        window, threshold, min_requests, min_samples = 30, 3.0, 20, 10

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(za, "datetime", FixedDatetime)
    seen = []
    new = za.check_once(httpx.Client(transport=es_transport(seen)), "http://es", Args)
    assert [a["client_ip"] for a in new] == ["203.0.113.50"]
    assert ("PUT", "/pinakes-alerts/_doc/203.0.113.50_2026-11-24T12:00:00Z") in seen
    seen.clear()
    assert (
        za.check_once(httpx.Client(transport=es_transport(seen, created=False)), "http://es", Args)
        == []
    )


def test_ensure_index_creates_it_when_missing():
    seen = []
    za.ensure_index(httpx.Client(transport=es_transport(seen)), "http://es")
    assert seen == [("HEAD", "/pinakes-alerts"), ("PUT", "/pinakes-alerts")]


# ---- bot simulator ----


def bot_client(log):
    def handler(request: httpx.Request):
        log.append((request.url.path, request.headers["x-forwarded-for"]))
        return httpx.Response(200, json={})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")


def test_normal_traffic_uses_the_given_ips():
    log, naps = [], []
    n = bot.normal_traffic(bot_client(log), 50, bot.NORMAL_IPS, 0.3, random.Random(1), naps.append)
    assert n == 50 and len(log) == 50 and naps == [0.3] * 50
    assert {ip for _, ip in log} <= set(bot.NORMAL_IPS)
    assert len({ip for _, ip in log}) > 5


def test_burst_comes_from_a_single_ip():
    log = []
    assert bot.burst(bot_client(log), "203.0.113.50", 300) == 300
    assert {ip for _, ip in log} == {"203.0.113.50"} and len(log) == 300


def test_bot_traffic_triggers_the_alert_logic():
    """Normal phase + burst, counted per (IP, minute) like Elasticsearch would do."""
    log = []
    client = bot_client(log)
    bot.normal_traffic(client, 150, bot.NORMAL_IPS, 0, random.Random(3), lambda s: None)
    bot.burst(client, "203.0.113.50", 300)
    per_ip = {}
    for _, ip in log:
        per_ip[ip] = per_ip.get(ip, 0) + 1
    counts = [(NOW, ip, c) for ip, c in per_ip.items()]
    assert [a["client_ip"] for a in za.find_alerts(counts, now=NOW)] == ["203.0.113.50"]


def test_json_alert_document_is_serialisable():
    a = za.find_alerts(baseline() + [(NOW, "203.0.113.50", 300)], now=NOW)[0]
    assert json.loads(json.dumps(a)) == a


def test_slow_requests_never_stop_the_bot():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")
    assert bot.normal_traffic(client, 5, bot.NORMAL_IPS, 0, random.Random(1), lambda s: None) == 5
    assert bot.burst(client, "203.0.113.50", 5) == 5


def test_error_messages_say_why_elasticsearch_refused():
    request = httpx.Request("POST", "http://es/pinakes-logs-*/_search")
    reason = '{"error":"Text fields are not optimised... fielddata is disabled on text fields"}'
    refused = httpx.HTTPStatusError(
        "bad", request=request, response=httpx.Response(400, text=reason, request=request)
    )
    message = za.describe_error(refused)
    assert "HTTP 400" in message and "setup_elk.py --check" in message
    down = za.describe_error(httpx.ConnectError("down", request=request))
    assert "not reachable" in down and "HTTP" not in down
