-- Cassandra schema (task B5, owner: B). One table per question we ask.
-- Run by: python -m data_pipeline.cassandra.load_events --schema-only

CREATE KEYSPACE IF NOT EXISTS pinakes
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

-- Question 1: how many times was work W read on day D?
-- The partition is (work, day): it stays small, and one query reads one partition.
CREATE TABLE IF NOT EXISTS pinakes.reads_by_work_day (
  work_id text,
  day     date,
  ts      timestamp,
  user_id text,
  PRIMARY KEY ((work_id, day), ts, user_id)
) WITH CLUSTERING ORDER BY (ts DESC, user_id ASC);

-- Question 2: what did user U read recently?
-- The partition is the user; newest reads first, so LIMIT n gives the last n reads.
CREATE TABLE IF NOT EXISTS pinakes.reads_by_user (
  user_id text,
  ts      timestamp,
  work_id text,
  PRIMARY KEY (user_id, ts, work_id)
) WITH CLUSTERING ORDER BY (ts DESC, work_id ASC);
