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


def mapping_response(index_types):
    """What GET <index>/_mapping/field/... answers: {index: {"mappings": {field: {...}}}}."""
    out = {}
    for index, types in index_types.items():
        mappings = {}
        for field, kind in types.items():
            if kind:
                leaf = field.split(".")[-1]
                mappings[field] = {"full_name": field, "mapping": {leaf: {"type": kind}}}
        out[index] = {"mappings": mappings}
    return out


GOOD = dict(setup_elk.EXPECTED_TYPES)
BAD = {**GOOD, "client_ip": "text", "path": "text", "geoip.location": None}


def mapping_client(payload):
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )


def test_check_mapping_accepts_the_right_types():
    client = mapping_client(mapping_response({"pinakes-logs-2026.11.26": GOOD}))
    assert setup_elk.check_mapping(client, "http://es") == []


def test_check_mapping_finds_guessed_types():
    client = mapping_client(mapping_response({"pinakes-logs-2026.11.26": BAD}))
    problems = setup_elk.check_mapping(client, "http://es")
    assert ("FAIL", "pinakes-logs-2026.11.26", "client_ip", "ip", "text") in problems
    assert ("FAIL", "pinakes-logs-2026.11.26", "path", "keyword", "text") in problems
    # a missing geoip.location is only a warning (no public IP has been seen yet)
    assert ("WARN", "pinakes-logs-2026.11.26", "geoip.location", "geo_point", None) in problems


def test_one_bad_index_is_enough_to_fail():
    payload = mapping_response({"pinakes-logs-2026.11.25": BAD, "pinakes-logs-2026.11.26": GOOD})
    problems = setup_elk.check_mapping(mapping_client(payload), "http://es")
    assert {p[1] for p in problems} == {"pinakes-logs-2026.11.25"}


def test_no_index_yet():
    assert setup_elk.field_types(mapping_client({}), "http://es") == {}
