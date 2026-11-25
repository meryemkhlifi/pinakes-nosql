Graph: synthetic (20000 nodes, 39993 links). 30 runs per depth and per engine, after 3 warm-up runs.

| Depth | Pairs | Neo4j p50 (ms) | Neo4j p95 (ms) | PostgreSQL p50 (ms) | PostgreSQL p95 (ms) | PostgreSQL / Neo4j (p50) |
|---|---|---|---|---|---|---|
| 2 | 10 | 5.72 | 6.71 | 1.84 | 2.61 | x 0.3 |
| 3 | 10 | 5.50 | 6.16 | 1.97 | 2.86 | x 0.4 |
| 4 | 10 | 6.79 | 9.50 | 3.10 | 4.95 | x 0.5 |
| 5 | 10 | 5.29 | 7.17 | 6.47 | 12.00 | x 1.2 |
