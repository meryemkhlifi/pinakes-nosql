import json

import httpx
from fastapi.testclient import TestClient

from backend.app.db import es_logs
from backend.app.main import app
from elk import dashboard_io, setup_ilm

client = TestClient(app)

ES_RESPONSE = {
    "hits": {
        "hits": [
            {
                "_source": {
                    "@timestamp": "2026-11-20T10:15:00Z",
                    "minute": "2026-11-20T10:14:00Z",
                    "client_ip": "203.0.113.7",
                    "requests_per_min": 300,
                    "z_score": 4.2,
                    "mean": 5.1,
                    "std": 12.0,
                }
            }
        ]
    }
}


def test_parse_alerts_follows_the_contract():
    assert es_logs.parse_alerts(ES_RESPONSE) == [
        {
            "ts": "2026-11-20T10:15:00Z",
            "client_ip": "203.0.113.7",
            "requests_per_min": 300,
            "z_score": 4.2,
        }
    ]


def fake_post(status, payload=None):
    def post(url, json=None, timeout=None):
        assert url.endswith("/pinakes-alerts/_search")
        assert json["sort"] == [{"@timestamp": "desc"}]
        return httpx.Response(status, json=payload or {}, request=httpx.Request("POST", url))

    return post


def test_latest_alerts_when_index_does_not_exist_yet(monkeypatch):
    monkeypatch.setattr(es_logs.httpx, "post", fake_post(404))
    assert es_logs.latest_alerts() == []


def test_latest_alerts_reads_elasticsearch(monkeypatch):
    monkeypatch.setattr(es_logs.httpx, "post", fake_post(200, ES_RESPONSE))
    assert es_logs.latest_alerts(5)[0]["z_score"] == 4.2


def test_alerts_endpoint(monkeypatch):
    monkeypatch.setattr(es_logs, "latest_alerts", lambda limit: [{"ts": "t", "limit": limit}])
    assert client.get("/monitoring/alerts?limit=3").json() == [{"ts": "t", "limit": 3}]
    assert client.get("/monitoring/alerts?limit=0").status_code == 422


def test_alerts_endpoint_when_elasticsearch_is_down(monkeypatch):
    def boom(limit):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(es_logs, "latest_alerts", boom)
    r = client.get("/monitoring/alerts")
    assert r.status_code == 503 and "stack B" in r.json()["detail"]


# ---- ILM and dashboard export ----


def test_policy_deletes_after_seven_days():
    delete = setup_ilm.build_policy()["policy"]["phases"]["delete"]
    assert delete["min_age"] == "7d" and delete["actions"] == {"delete": {}}
    assert setup_ilm.build_policy(3)["policy"]["phases"]["delete"]["min_age"] == "3d"


def test_template_carries_the_policy_and_keeps_the_types():
    t = setup_ilm.template_with_policy()
    assert t["template"]["settings"]["index.lifecycle.name"] == "pinakes-logs-7d"
    assert t["template"]["mappings"]["properties"]["client_ip"]["type"] == "ip"


def test_export_asks_for_the_dashboard_and_its_references():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"], seen["body"] = request.url.path, request.read()
        seen["xsrf"] = request.headers["kbn-xsrf"]
        return httpx.Response(200, text='{"type":"dashboard","id":"d1"}\n')

    text = dashboard_io.export_dashboard(
        httpx.Client(transport=httpx.MockTransport(handler)), "http://kb"
    )
    assert seen["path"] == "/api/saved_objects/_export" and seen["xsrf"] == "true"
    assert b'"includeReferencesDeep":true' in seen["body"].replace(b" ", b"")
    assert '"type":"dashboard"' in text


def test_import_overwrites():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json={"success": True, "successCount": 4})

    out = dashboard_io.import_dashboard(
        httpx.Client(transport=httpx.MockTransport(handler)), "http://kb", b'{"type":"dashboard"}\n'
    )
    assert out["successCount"] == 4
    assert "overwrite=true" in seen["url"] and b"dashboard.ndjson" in seen["body"]


def test_monitoring_is_not_a_stub_anymore(monkeypatch):
    monkeypatch.setattr(es_logs, "latest_alerts", lambda limit: [])
    assert client.get("/monitoring/alerts").status_code == 200


def test_export_drops_the_cached_field_list():
    exported = (
        '{"type":"index-pattern","id":"pinakes-logs","attributes":{"title":"pinakes-logs-*",'
        '"fields":"[{\\"name\\":\\"path\\",\\"type\\":\\"string\\",\\"aggregatable\\":false}]"}}\n'
        '{"type":"dashboard","id":"d1","attributes":{"title":"Pinakes"}}\n'
    )
    cleaned = dashboard_io.strip_field_cache(exported)
    first, second = [json.loads(line) for line in cleaned.splitlines()]
    assert "fields" not in first["attributes"] and first["attributes"]["title"] == "pinakes-logs-*"
    assert second["attributes"]["title"] == "Pinakes"
    assert cleaned.endswith("\n")
