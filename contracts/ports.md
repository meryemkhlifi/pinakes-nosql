# Ports (frozen on Day 1)

| Service | Host port | Owner |
|---|---|---|
| MongoDB | 27017 | A |
| Elasticsearch (catalog) | 9200 | A |
| Redis | 6379 | A |
| PostgreSQL for benchmark A8 | 5432 | A |
| Neo4j Browser / Bolt | 7474 / 7687 | B |
| Cassandra | 9042 | B |
| Elasticsearch (logs) | 9201 | B |
| Kibana | 5601 | B |
| Logstash (beats input) | 5044 | B |
| PostgreSQL for benchmark B8 | 5433 | B |
| FastAPI | 8000 | both |
| Streamlit | 8501 | both |

Changing a port needs a pull request labelled `contract-change` that both members approve.
