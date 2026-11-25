"""Benchmark results: JSON, CSV, a Markdown table for the report, and the chart (owner: B)."""

import csv
import json
from pathlib import Path

ENGINES = ("Neo4j", "PostgreSQL")
FIELDS = ["engine", "depth", "pairs", "runs", "p50_ms", "p95_ms", "mean_ms", "min_ms", "max_ms",
          "wrong_answers", "timeouts"]  # fmt: skip


def table_markdown(rows: list[dict]) -> str:
    by = {(r["engine"], r["depth"]): r for r in rows}
    depths = sorted({r["depth"] for r in rows})
    lines = [
        "| Depth | Pairs | Neo4j p50 (ms) | Neo4j p95 (ms) | PostgreSQL p50 (ms) "
        "| PostgreSQL p95 (ms) | PostgreSQL / Neo4j (p50) |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in depths:
        n, p = by.get(("Neo4j", d)), by.get(("PostgreSQL", d))
        if not n or not p:
            continue
        ratio = p["p50_ms"] / n["p50_ms"] if n["p50_ms"] else float("nan")
        lines.append(
            f"| {d} | {n['pairs']} | {n['p50_ms']:.2f} | {n['p95_ms']:.2f} | "
            f"{p['p50_ms']:.2f} | {p['p95_ms']:.2f} | x {ratio:.1f} |"
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
        writer.writerows(rows)
    note = (
        f"Graph: {meta['dataset']} ({meta['nodes']} nodes, {meta['edges']} links). "
        f"{meta['runs']} runs per depth and per engine, after {meta['warmup']} warm-up runs.\n\n"
    )
    (out / "results.md").write_text(note + table_markdown(rows), encoding="utf-8")
    return out


def make_chart(rows: list[dict], path, title: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"Neo4j": "#018bff", "PostgreSQL": "#336791"}
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for engine in ENGINES:
        pts = sorted((r for r in rows if r["engine"] == engine), key=lambda r: r["depth"])
        if not pts:
            continue
        x = [r["depth"] for r in pts]
        ax.plot(x, [r["p50_ms"] for r in pts], "o-", color=colors[engine], label=f"{engine} p50")
        ax.plot(
            x,
            [r["p95_ms"] for r in pts],
            "s--",
            color=colors[engine],
            alpha=0.6,
            label=f"{engine} p95",
        )
    ax.set_yscale("log")
    ax.set_xlabel("Depth (number of links of the shortest path)")
    ax.set_ylabel("Time per query (ms, log scale)")
    ax.set_xticks(sorted({r["depth"] for r in rows}))
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return Path(path)
