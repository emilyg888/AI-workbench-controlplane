from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          VARCHAR PRIMARY KEY,
    bundle_id       VARCHAR NOT NULL,
    eval_set        VARCHAR NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    total_inputs    INTEGER,
    succeeded       INTEGER,
    failed          INTEGER,
    p50_latency_ms  INTEGER,
    p95_latency_ms  INTEGER,
    status          VARCHAR
);
"""


INFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS inference_requests (
    trace_id       VARCHAR PRIMARY KEY,
    env            VARCHAR NOT NULL,
    bundle_id      VARCHAR NOT NULL,
    request_at     TIMESTAMP NOT NULL,
    input          JSON,
    output         JSON,
    latency_ms     INTEGER,
    policy_action  VARCHAR,
    error          VARCHAR
);
"""


PHASE3_COLUMNS = [
    ("correctness", "DOUBLE"),
    ("groundedness", "DOUBLE"),
    ("policy_compliance", "DOUBLE"),
    ("refusal_quality", "DOUBLE"),
    ("latency_score", "DOUBLE"),
    ("completeness", "DOUBLE"),
    ("aggregate_score", "DOUBLE"),
    ("scoring_profile", "VARCHAR"),
    ("scored_at", "TIMESTAMP"),
]


def db_path(root: Path) -> Path:
    return root / "db" / "workbench.duckdb"


def connect(root: Path) -> duckdb.DuckDBPyConnection:
    p = db_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(p))
    ensure_schema(con)
    return con


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(RUNS_SCHEMA)
    con.execute(INFERENCE_SCHEMA)
    existing = {row[1] for row in con.execute("PRAGMA table_info('runs');").fetchall()}
    for name, typ in PHASE3_COLUMNS:
        if name not in existing:
            con.execute(f"ALTER TABLE runs ADD COLUMN {name} {typ};")


def insert_run(con: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    con.execute(
        """INSERT INTO runs
           (run_id, bundle_id, eval_set, started_at, status)
           VALUES (?, ?, ?, ?, ?)""",
        [row["run_id"], row["bundle_id"], row["eval_set"],
         row["started_at"], row.get("status", "running")],
    )


def update_run(con: duckdb.DuckDBPyConnection, run_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(
        f"UPDATE runs SET {sets} WHERE run_id = ?",
        [*fields.values(), run_id],
    )


def list_runs(
    con: duckdb.DuckDBPyConnection,
    bundle_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    q = "SELECT * FROM runs"
    params: list[Any] = []
    if bundle_id:
        q += " WHERE bundle_id = ?"
        params.append(bundle_id)
    q += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    cur = con.execute(q, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_run(con: duckdb.DuckDBPyConnection, run_id: str) -> dict | None:
    cur = con.execute("SELECT * FROM runs WHERE run_id = ?", [run_id])
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def insert_inference(con: duckdb.DuckDBPyConnection, row: dict[str, Any]) -> None:
    con.execute(
        """INSERT INTO inference_requests
           (trace_id, env, bundle_id, request_at, input, output,
            latency_ms, policy_action, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            row["trace_id"],
            row["env"],
            row["bundle_id"],
            row["request_at"],
            row.get("input"),
            row.get("output"),
            row.get("latency_ms"),
            row.get("policy_action"),
            row.get("error"),
        ],
    )
