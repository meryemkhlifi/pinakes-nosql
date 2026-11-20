# API contract (frozen on Day 1)

Base URL: `http://localhost:8000`. All responses are JSON. Errors look like `{"detail": "message"}`.
Status codes: 200 OK, 201 created, 404 not found, 422 invalid input, 429 too many requests,
501 not implemented yet (every endpoint returns 501 until its task is done).

| Endpoint | Owner | Store |
|---|---|---|
| `GET /health` | both | none |
| `GET /catalog/genres` | A | MongoDB |
| `GET /catalog/genres/{genre}/authors` | A | MongoDB |
| `GET /catalog/works/{work_id}` | A | MongoDB, Redis |
| `GET /search`, `GET /suggest` | A | Elasticsearch, Redis |
| `GET /popular` | A | Redis |
| `GET /graph/path`, `/graph/neighbors/{author_id}`, `/graph/influence/top` | B | Neo4j |
| `POST /events/read`, `GET /events/work/{work_id}`, `GET /events/user/{user_id}` | B | Cassandra |
| `GET /monitoring/alerts` | B | Elasticsearch (logs) |

The web page calls `POST /events/read` whenever a work page is opened, so A's code never imports B's code.

## Response shapes

`GET /catalog/genres` ->
`[{"genre": "epic", "count": 120}]`

`GET /catalog/genres/{genre}/authors` ->
`[{"author_id": "a_homer", "name": "Homer", "works": [{"id": "w_0001", "title": "Iliad"}]}]`

`GET /catalog/works/{work_id}` -> one work document (see `schema_work.json`).

`GET /search?q=&genre=&language=&year_from=&year_to=&page=1&size=10` ->
```json
{
  "total": 42, "page": 1, "size": 10,
  "hits": [{"id": "w_0003", "title": "The Republic", "genre": "philosophy",
            "authors": ["Plato"], "year": -375, "score": 7.3,
            "highlight": {"incipit": ["I went down yesterday to the <em>Piraeus</em>"]}}],
  "facets": {"genre": [{"key": "philosophy", "count": 5}],
             "language": [{"key": "en", "count": 20}],
             "year": [{"key": -500, "count": 3}]}
}
```

`GET /suggest?q=` -> `["The Republic", "The Clouds"]`

`GET /popular?n=10` -> `[{"id": "w_0003", "title": "The Republic", "views": 57}]`

`GET /graph/path?from=a_plato&to=a_aristotle` ->
```json
{"found": true, "length": 1,
 "nodes": [{"id": "a_plato", "name": "Plato"}, {"id": "a_aristotle", "name": "Aristotle"}],
 "edges": [{"source": "a_aristotle", "target": "a_plato", "type": "STUDENT_OF"}]}
```

`GET /graph/neighbors/{author_id}?depth=2` -> `{"nodes": [...], "edges": [...]}` (same node and edge format).

`GET /graph/influence/top?n=10` -> `[{"author_id": "a_plato", "name": "Plato", "score": 1.92}]`

`POST /events/read` with body `{"work_id": "w_0003", "user_id": "u_42"}` -> 201 `{"status": "recorded"}`

`GET /events/work/{work_id}?day=2026-11-20` -> `{"work_id": "w_0003", "day": "2026-11-20", "count": 14}`

`GET /events/user/{user_id}?limit=20` -> `[{"work_id": "w_0003", "ts": "2026-11-20T10:15:00Z"}]`

`GET /monitoring/alerts?limit=20` ->
`[{"ts": "2026-11-20T10:15:00Z", "client_ip": "203.0.113.7", "requests_per_min": 300, "z_score": 4.2}]`

## Request log format (one JSON line per request in `logs/api.log`)

`ts` (ISO 8601 UTC), `client_ip`, `method`, `path`, `status`, `latency_ms`, `user_agent`.
The client IP is the first value of `X-Forwarded-For` when present (the bot simulator uses this).
