# Cassandra and ELK (member B, notes for report sections 5 and 6)

## Cassandra: one table per question
| Question | Table | Partition key | Clustering |
|---|---|---|---|
| How many reads of work W on day D? | `reads_by_work_day` | (work_id, day) | ts DESC, user_id |
| What did user U read recently? | `reads_by_user` | user_id | ts DESC, work_id |

Each event is written twice (once per table). This duplication is the normal Cassandra way:
no joins, no secondary indexes, every query reads one partition. The day is part of the
partition key so that a very popular work does not create one huge partition.
Limit: a user's partition grows forever; a real system would add a month to the key.
Writes are cheap (log-structured storage), which is why Cassandra fits a stream of events.
CAP: Cassandra is usually placed on the AP side (available and partition tolerant, with
tunable consistency: we write and read at level ONE). Defend this choice in the report.
Data: 100,000 fake events over 30 days, users u_1 to u_500, work popularity follows a
Zipf law (1/rank).

## ELK pipeline
`API (JSON line per request) -> logs/api.log -> Filebeat -> Logstash -> Elasticsearch (logs) -> Kibana`
- Filebeat reads the file and decodes each JSON line.
- Logstash puts the API timestamp in `@timestamp`, converts `status` (integer) and
  `latency_ms` (float), adds `geoip` (country and coordinates) from `client_ip`.
- The index template (elk/setup_elk.py) fixes the types: `client_ip` is an `ip`,
  `geoip.location` a `geo_point` (needed for the Kibana map of Day 4).
- Indices are daily: `pinakes-logs-YYYY.MM.dd` (the 7-day deletion policy is Day 4).
