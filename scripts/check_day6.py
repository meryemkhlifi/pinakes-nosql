"""Day 6 check: the two benchmarks and the two parts of the report (owner: B).

From the repo root, after BOTH pull requests are merged (pull main first):
    python scripts/check_day6.py
    python scripts/check_day6.py --strict      # also fails while a [A REMPLIR] mark is left
Prints [OK], [WARN] or [FAIL]. Exit code 0 when there is no [FAIL].
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHES = {
    "Elasticsearch vs PostgreSQL (A)": ("benchmarks/es_vs_postgres/results", "query", 3),
    "Neo4j vs PostgreSQL, real graph (B)": (
        "benchmarks/neo4j_vs_postgres/results/real",
        "depth",
        4,
    ),
}
OPTIONAL = {
    "Neo4j vs PostgreSQL, synthetic graph (B)": "benchmarks/neo4j_vs_postgres/results/synthetic"
}
REPORTS = ["docs/a_rapport_sections_1-3.md", "docs/b_rapport_sections_4-6.md"]
MARK = "[A REMPLIR"
FILES = ["results.json", "results.csv", "results.md", "chart.png"]


def is_png(path: Path) -> bool:
    return (
        path.exists()
        and path.stat().st_size > 5000
        and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    )


def check_bench(root: Path, name: str, folder: str, key: str, expected: int, out: list) -> None:
    base = root / folder
    missing = [f for f in FILES if not (base / f).exists()]
    if missing:
        out.append(("FAIL", f"{name}: missing {', '.join(missing)} in {folder}"))
        return
    out.append(("OK", f"{name}: the 4 result files exist"))
    out.append(
        ("OK" if is_png(base / "chart.png") else "FAIL", f"{name}: chart.png is a real image")
    )
    try:
        rows = json.loads((base / "results.json").read_text(encoding="utf-8"))["rows"]
    except (ValueError, KeyError):
        out.append(("FAIL", f"{name}: results.json is not readable"))
        return
    values = {r[key] for r in rows}
    engines = {r["engine"] for r in rows}
    out.append(("OK" if len(engines) == 2 else "FAIL", f"{name}: {len(engines)} engines compared"))
    out.append(
        (
            "OK" if len(values) >= expected else "WARN",
            f"{name}: {len(values)} {key} value(s) measured (plan: {expected})",
        )
    )
    runs = {r["runs"] for r in rows}
    out.append(
        ("OK" if runs == {30} else "WARN", f"{name}: runs per point = {sorted(runs)} (plan: 30)")
    )
    bad = sum(r.get("wrong_answers", 0) for r in rows)
    slow = sum(r.get("timeouts", 0) for r in rows)
    if bad:
        out.append(("FAIL", f"{name}: {bad} wrong answers, do not use these numbers"))
    if slow:
        out.append(("WARN", f"{name}: {slow} timeouts (write it in the report)"))


def run_checks(root: Path, strict: bool = False) -> tuple[list, int]:
    out: list[tuple[str, str]] = []
    for name, (folder, key, expected) in BENCHES.items():
        check_bench(root, name, folder, key, expected, out)
    for name, folder in OPTIONAL.items():
        if (root / folder / "results.json").exists():
            check_bench(root, name, folder, "depth", 4, out)
        else:
            out.append(("WARN", f"{name}: not run (optional but recommended)"))
    for report in REPORTS:
        path = root / report
        if not path.exists():
            out.append(("FAIL", f"{report} is missing"))
            continue
        text = path.read_text(encoding="utf-8")
        left = text.count(MARK)
        out.append(("OK", f"{report} exists ({len(text.split())} words)"))
        if left:
            out.append(
                ("FAIL" if strict else "WARN", f"{report}: {left} mark(s) {MARK}] left to fill")
            )
    problems = sum(1 for level, _ in out if level == "FAIL")
    return out, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    lines, problems = run_checks(ROOT, args.strict)
    for level, text in lines:
        print(f"[{level}]".ljust(7) + text)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
