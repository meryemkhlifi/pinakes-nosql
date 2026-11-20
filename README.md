# Pinakes 2.0

A polyglot NoSQL library catalog inspired by Callimachus' Pinakes.
MongoDB, Elasticsearch, Redis (member A) and Neo4j, Cassandra, ELK (member B), behind one FastAPI API and a Streamlit UI.

## First-time setup

```bash
git clone https://github.com/meryemkhlifi/pinakes-nosql.git
cd pinakes-nosql
python -m venv .venv
source .venv/Scripts/activate        # Git Bash. PowerShell: .venv\Scripts\Activate.ps1 | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # PowerShell: copy .env.example .env
mkdir -p logs
```

## Run your own stack (not both at once on a small laptop)

```bash
# A: MongoDB, Elasticsearch (catalog), Redis
docker compose -p pinakes-a --env-file .env -f docker/stack-a.yml up -d
# B: Neo4j, Cassandra, Elasticsearch (logs), Kibana, Logstash, Filebeat
docker compose -p pinakes-b --env-file .env -f docker/stack-b.yml up -d

docker compose -p pinakes-a -f docker/stack-a.yml ps          # use pinakes-b / stack-b.yml for B
docker compose -p pinakes-a -f docker/stack-a.yml logs mongo  # logs of one service
docker compose -p pinakes-a -f docker/stack-a.yml down        # stop (data is kept in volumes)
```

`docker-compose.yml` at the root starts everything; use it only for the final demo.
Do not mix the two ways of starting containers on the same laptop (ports would clash).

## Run the API and the UI

```bash
uvicorn backend.app.main:app --reload --port 8000     # http://localhost:8000/docs
streamlit run frontend/Home.py                        # http://localhost:8501
pytest                                                # smoke tests
```

Web addresses: Kibana http://localhost:5601, Neo4j Browser http://localhost:7474.

## Team rules

- Each file has one owner (see the folder layout in the plan). Never edit the other member's files.
- `contracts/` is frozen: change it only with a pull request labelled `contract-change` that both approve.
- Branches are named `a/...` or `b/...`. Every morning: `git pull --rebase`. Merge to `main` at least once a day.
- Never commit `.env`, raw data or logs.
