import json

from scripts import check_day6 as cd


def png(path):
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 6000)


def make_bench(base, key, values, engines=("A", "B"), runs=30, wrong=0, timeouts=0):
    base.mkdir(parents=True)
    rows = [{"engine": e, key: v, "runs": runs, "wrong_answers": wrong, "timeouts": timeouts}
            for e in engines for v in values]  # fmt: skip
    (base / "results.json").write_text(json.dumps({"meta": {}, "rows": rows}))
    for name in ("results.csv", "results.md"):
        (base / name).write_text("x")
    png(base / "chart.png")


def make_all(tmp_path, report_text="done"):
    make_bench(tmp_path / "benchmarks/es_vs_postgres/results", "query", ["q1", "q2", "q3"])
    make_bench(tmp_path / "benchmarks/neo4j_vs_postgres/results/real", "depth", [2, 3, 4, 5])
    (tmp_path / "docs").mkdir()
    for report in cd.REPORTS:
        (tmp_path / report).write_text(report_text)


def levels(lines):
    return [level for level, _ in lines]


def test_everything_present(tmp_path):
    make_all(tmp_path)
    lines, problems = cd.run_checks(tmp_path)
    assert problems == 0 and "FAIL" not in levels(lines)
    assert (
        "WARN",
        "Neo4j vs PostgreSQL, synthetic graph (B): not run (optional but recommended)",
    ) in lines


def test_missing_files_and_reports_fail(tmp_path):
    lines, problems = cd.run_checks(tmp_path)
    assert problems == 4  # 2 benchmarks and 2 reports
    assert any("missing results.json" in t for _, t in lines)


def test_marks_warn_then_fail_in_strict_mode(tmp_path):
    make_all(tmp_path, "intro [A REMPLIR : chiffre] et [A REMPLIR : autre]")
    lines, problems = cd.run_checks(tmp_path)
    assert problems == 0 and any("2 mark(s)" in t for _, t in lines)
    assert cd.run_checks(tmp_path, strict=True)[1] == 2


def test_wrong_answers_fail_and_timeouts_warn(tmp_path):
    make_bench(tmp_path / "x", "depth", [2], wrong=2, timeouts=3)
    out = []
    cd.check_bench(tmp_path, "t", "x", "depth", 4, out)
    assert any(level == "FAIL" and "wrong answers" in text for level, text in out)
    assert any(level == "WARN" and "timeouts" in text for level, text in out)
    assert any(level == "WARN" and "1 depth value(s)" in text for level, text in out)


def test_fake_png_is_refused(tmp_path):
    bad = tmp_path / "chart.png"
    bad.write_bytes(b"not an image" * 1000)
    assert not cd.is_png(bad)
