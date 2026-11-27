import os

import httpx
import streamlit as st

import ui

API_URL = os.getenv("API_URL", "http://localhost:8000")
MAX_DRAWN_EDGES = 60  # a bigger drawing is unreadable

ui.setup(
    "graph",
    "Graph",
    "Who influenced whom (Neo4j). An arrow goes from the follower to the master.",
)


def api_get(path: str, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    r = httpx.get(f"{API_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def show_error(exc: Exception):
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail", "")
        except ValueError:
            detail = exc.response.text[:200]
        st.error(f"API error {exc.response.status_code}: {detail}")
    else:
        st.error(f"API not reachable at {API_URL}. Start it with: uvicorn backend.app.main:app")


def dot_escape(text) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def to_dot(nodes: list[dict], edges: list[dict], highlight: str | None = None) -> str:
    """Graphviz text of a graph. Streamlit draws it in the browser (nothing to install)."""
    lines = [
        "digraph G {",
        "rankdir=LR;",
        'bgcolor="transparent";',
        'node [shape=box, style="rounded,filled", fillcolor="#F7F6FC", color="#BDB6F2", '
        'fontcolor="#171526", fontname="Helvetica", fontsize=11, margin="0.18,0.1"];',
        'edge [color="#777487", fontcolor="#777487", fontname="Helvetica"];',
    ]
    for n in nodes:
        fill = ', fillcolor="#F4B56F", color="#F4B56F"' if n["id"] == highlight else ""
        lines.append(f'"{dot_escape(n["id"])}" [label="{dot_escape(n["name"])}"{fill}];')
    for e in edges:
        lines.append(
            f'"{dot_escape(e["source"])}" -> "{dot_escape(e["target"])}" '
            f'[label="{dot_escape(e["type"])}", fontsize=10];'
        )
    lines.append("}")
    return "\n".join(lines)


def load_authors() -> dict[str, str]:
    """{author_id: name}: every author of the catalog, or else the 100 top PageRank authors."""
    authors: dict[str, str] = {}
    try:
        for g in api_get("/catalog/genres"):
            for a in api_get(f"/catalog/genres/{g['genre']}/authors"):
                authors[a["author_id"]] = a["name"]
    except Exception:
        authors = {}  # the catalog (stack A) may be off: the graph alone is enough
    if not authors:
        for row in api_get("/graph/influence/top", n=100):
            authors[row["author_id"]] = row["name"]
    return authors


def make_labels(authors: dict[str, str]) -> dict[str, str]:
    """{label: author_id}, sorted by name; the id is added when two authors share a name."""
    counts: dict[str, int] = {}
    for name in authors.values():
        counts[name] = counts.get(name, 0) + 1
    labels = {}
    for author_id, name in sorted(authors.items(), key=lambda kv: (kv[1].lower(), kv[0])):
        labels[f"{name} ({author_id})" if counts[name] > 1 else name] = author_id
    return labels


if "graph_authors" not in st.session_state:
    try:
        st.session_state["graph_authors"] = load_authors()
    except Exception as exc:
        show_error(exc)
        st.stop()
authors = st.session_state["graph_authors"]
if not authors:
    st.warning(
        "No author in the graph. Load Neo4j first (python -m data_pipeline.neo4j.load_neo4j)."
    )
    st.stop()
labels = make_labels(authors)
names = list(labels)

# ---- 1. path between two authors ----
ui.section_title("How are two authors connected?", "Shortest path")
with ui.card():
    left, right = st.columns([1, 2], gap="large")
    with left:
        start = st.selectbox("From", names, index=0)
        end = st.selectbox("To", names, index=min(1, len(names) - 1))
        if st.button("Find the path"):
            try:
                st.session_state["graph_path"] = api_get(
                    "/graph/path", **{"from": labels[start], "to": labels[end]}
                )
            except Exception as exc:
                st.session_state.pop("graph_path", None)
                show_error(exc)
    with right:
        path = st.session_state.get("graph_path")
        if not path:
            ui.empty_state("Pick two authors", "The shortest chain of influences appears here.")
        elif not path["found"]:
            st.warning("No path between these two authors (searched up to 8 links).")
        else:
            st.success(f"Connected in {path['length']} link(s).")
            st.graphviz_chart(to_dot(path["nodes"], path["edges"]))
            by_id = {n["id"]: n["name"] for n in path["nodes"]}
            ui.show(
                ui.steps(
                    [
                        (by_id.get(e["source"], e["source"]), by_id.get(e["target"], e["target"]), e["type"])
                        for e in path["edges"]
                    ]
                )
            )

# ---- 2. PageRank table ----
ui.section_title("Most influential authors", "PageRank, damping 0.85")
with ui.card():
    top_n = st.slider("Number of authors", 5, 50, 10)
    try:
        ranking = api_get("/graph/influence/top", n=top_n)
    except Exception as exc:
        show_error(exc)
    else:
        if ranking:
            best = max(r["score"] for r in ranking) or 1
            ui.show(
                ui.rank_rows(
                    [
                        {"label": r["name"], "value": r["score"], "ratio": r["score"] / best}
                        for r in ranking
                    ]
                )
            )
        else:
            ui.empty_state("No score yet", "Run the PageRank step of the Neo4j pipeline.")

# ---- 3. neighbors ----
ui.section_title("Around one author", "Neighbors up to 3 links away")
with ui.card():
    left, right = st.columns([1, 2], gap="large")
    with left:
        center = st.selectbox("Author", names, index=0, key="graph_center")
        depth = st.slider("Depth (links)", 1, 3, 1)
        if st.button("Show the neighbors"):
            try:
                st.session_state["graph_nb"] = (
                    labels[center],
                    api_get(f"/graph/neighbors/{labels[center]}", depth=depth),
                )
            except Exception as exc:
                st.session_state.pop("graph_nb", None)
                show_error(exc)
    with right:
        neighbors = st.session_state.get("graph_nb")
        if not neighbors:
            ui.empty_state("Pick an author", "Its influences and followers are drawn here.")
        else:
            center_id, graph = neighbors
            st.write(f"{len(graph['nodes'])} authors, {len(graph['edges'])} links.")
            if graph["edges"]:
                shown = graph["edges"][:MAX_DRAWN_EDGES]
                used = {e["source"] for e in shown} | {e["target"] for e in shown}
                st.graphviz_chart(
                    to_dot([n for n in graph["nodes"] if n["id"] in used], shown, center_id)
                )
                if len(graph["edges"]) > len(shown):
                    st.caption(f"Only the first {len(shown)} links are drawn.")
            else:
                st.info("This author has no link.")
