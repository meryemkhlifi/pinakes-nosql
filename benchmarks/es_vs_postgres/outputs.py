"""Benchmark results: JSON, CSV, a Markdown table for the report, and the chart (owner: A)."""

import csv
import json
from pathlib import Path

ENGINES = ("Elasticsearch", "PostgreSQL")
FIELDS = ["engine", "query", "kind", "matches", "runs", "p50_ms", "p95_ms", "mean_ms", "min_ms",
          "max_ms", "top_titles"]  # fmt: skip


def table_markdown(rows: list[dict]) -> str:
    by = {(r["engine"], r["query"]): r for r in rows}
    queries = list(dict.fromkeys(r["query"] for r in rows))
    lines = [
        "| Query | Kind | Matches ES | Matches PG | ES p50 (ms) | ES p95 (ms) "
        "| PG p50 (ms) | PG p95 (ms) | Top result ES | Top result PG |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for q in queries:
        e, p = by.get(("Elasticsearch", q)), by.get(("PostgreSQL", q))
        if not e or not p:
            continue
        top_e = e["top_titles"][0] if e["top_titles"] else "(none)"
        top_p = p["top_titles"][0] if p["top_titles"] else "(none)"
        lines.append(
            f"| {q} | {e['kind']} | {e['matches']} | {p['matches']} | {e['p50_ms']:.2f} | "
            f"{e['p95_ms']:.2f} | {p['p50_ms']:.2f} | {p['p95_ms']:.2f} | {top_e} | {top_p} |"
        )
    return "\n".join(lines) + "\n"


def write_results(rows: list[dict], outdir, meta: dict) -> Path:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "top_titles": " | ".join(r["top_titles"])})
    note = (
        f"Corpus: {meta['docs']} documents ({meta['real_docs']} real works). "
        f"{meta['runs']} runs per query and per engine, after {meta['warmup']} warm-up runs.\n\n"
    )
    (out / "results.md").write_text(note + table_markdown(rows), encoding="utf-8")
    return out


def make_chart(rows: list[dict], path, title: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    queries = list(dict.fromkeys(r["query"] for r in rows))
    colors = {"Elasticsearch": "#00a9a5", "PostgreSQL": "#336791"}
    width = 0.2
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for i, engine in enumerate(ENGINES):
        for j, (key, hatch) in enumerate((("p50_ms", ""), ("p95_ms", "//"))):
            values = []
            for q in queries:
                match = [r for r in rows if r["engine"] == engine and r["query"] == q]
                values.append(match[0][key] if match else 0)
            x = [k + (2 * i + j - 1.5) * width for k in range(len(queries))]
            ax.bar(
                x,
                values,
                width,
                color=colors[engine],
                hatch=hatch,
                alpha=0.9 if j == 0 else 0.55,
                label=f"{engine} {key[:3]}",
            )
    ax.set_yscale("log")
    ax.set_xticks(range(len(queries)))
    kinds = {r["query"]: r["kind"] for r in rows}
    ax.set_xticklabels([f"{q}\n({kinds[q]})" for q in queries])
    ax.set_ylabel("Time per query (ms, log scale)")
    ax.set_title(title)
    ax.grid(True, axis="y", which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return Path(path)
