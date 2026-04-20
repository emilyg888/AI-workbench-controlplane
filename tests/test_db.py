from __future__ import annotations

from datetime import datetime, timezone

from workbench import db


def test_schema_and_crud(workbench_root) -> None:
    con = db.connect(workbench_root)

    row = {
        "run_id": "run_001",
        "bundle_id": "b_v1",
        "eval_set": "smoke",
        "started_at": datetime.now(timezone.utc),
    }
    db.insert_run(con, row)

    assert db.get_run(con, "run_001")["status"] == "running"

    db.update_run(con, "run_001", status="completed", succeeded=5, failed=0,
                  p50_latency_ms=100, p95_latency_ms=200)
    fetched = db.get_run(con, "run_001")
    assert fetched["status"] == "completed"
    assert fetched["succeeded"] == 5
    assert fetched["p95_latency_ms"] == 200

    rows = db.list_runs(con, bundle_id="b_v1")
    assert len(rows) == 1

    con.close()


def test_phase3_columns_added(workbench_root) -> None:
    con = db.connect(workbench_root)
    cols = {row[1] for row in con.execute("PRAGMA table_info('runs');").fetchall()}
    assert {"correctness", "aggregate_score", "scoring_profile"}.issubset(cols)
    con.close()


def test_inference_table_exists(workbench_root) -> None:
    con = db.connect(workbench_root)
    con.execute(
        "INSERT INTO inference_requests (trace_id, env, bundle_id, request_at) "
        "VALUES (?, ?, ?, ?)",
        ["t_1", "dev", "b_v1", datetime.now(timezone.utc)],
    )
    cur = con.execute("SELECT COUNT(*) FROM inference_requests").fetchone()
    assert cur[0] == 1
    con.close()
