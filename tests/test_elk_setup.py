import httpx

from elk import setup_elk


def test_template_types():
    t = setup_elk.build_template()
    props = t["template"]["mappings"]["properties"]
    assert t["index_patterns"] == ["pinakes-logs-*"]
    assert props["client_ip"]["type"] == "ip"
    assert props["status"]["type"] == "integer"
    assert props["latency_ms"]["type"] == "float"
    assert props["geoip"]["properties"]["location"]["type"] == "geo_point"


def test_data_view_payload():
    body = setup_elk.build_data_view()
    assert body["data_view"]["title"] == "pinakes-logs-*"
    assert body["data_view"]["timeFieldName"] == "@timestamp"


def test_delete_log_indices_deletes_by_name():
    deleted = []

    def handler(request: httpx.Request):
        if request.method == "GET":
            return httpx.Response(200, json=[{"index": "pinakes-logs-2026.11.20"}])
        deleted.append(request.url.path)
        return httpx.Response(200, json={"acknowledged": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    names = setup_elk.delete_log_indices(client, "http://es")
    assert names == ["pinakes-logs-2026.11.20"]
    assert deleted == ["/pinakes-logs-2026.11.20"]
