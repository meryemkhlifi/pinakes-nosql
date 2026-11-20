import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Pinakes 2.0", layout="wide")
st.title("Pinakes 2.0")
st.write(
    "A modern Pinakes: the catalog of the Library of Alexandria rebuilt on MongoDB, "
    "Elasticsearch, Redis, Neo4j, Cassandra and ELK. Use the pages in the left menu."
)

try:
    r = httpx.get(f"{API_URL}/health", timeout=2)
    st.success(f"API reachable at {API_URL} (status {r.status_code})")
except Exception:
    st.error(
        f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app --reload"
    )
