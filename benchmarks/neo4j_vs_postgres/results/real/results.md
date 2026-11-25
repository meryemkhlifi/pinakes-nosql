Graph: real (126 nodes, 192 links). 30 runs per depth and per engine, after 3 warm-up runs.

| Depth | Pairs | Neo4j p50 (ms) | Neo4j p95 (ms) | PostgreSQL p50 (ms) | PostgreSQL p95 (ms) | PostgreSQL / Neo4j (p50) |
|---|---|---|---|---|---|---|
| 2 | 10 | 8.50 | 22.41 | 2.10 | 2.89 | x 0.2 |
| 3 | 10 | 6.78 | 147.94 | 1.97 | 2.22 | x 0.3 |
| 4 | 10 | 7.17 | 9.63 | 2.33 | 2.85 | x 0.3 |
| 5 | 10 | 6.64 | 13.58 | 2.46 | 2.94 | x 0.4 |
