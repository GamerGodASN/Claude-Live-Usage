"""SQLite storage + queries for parsed usage turns. Self-contained DB under data/."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "usage.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_files (
    path  TEXT PRIMARY KEY,
    size  INTEGER NOT NULL,
    mtime REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    uuid           TEXT PRIMARY KEY,
    session_id     TEXT,
    project        TEXT,
    cwd            TEXT,
    model          TEXT,
    ts             TEXT,
    date_local     TEXT,
    input_tokens   INTEGER DEFAULT 0,
    output_tokens  INTEGER DEFAULT 0,
    cache_creation INTEGER DEFAULT 0,
    cache_read     INTEGER DEFAULT 0,
    cost           REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_turns_date    ON turns(date_local);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _totals_row(conn, where: str, params: tuple) -> dict:
    row = conn.execute(
        f"""SELECT COALESCE(SUM(input_tokens),0)   AS inp,
                   COALESCE(SUM(output_tokens),0)  AS out,
                   COALESCE(SUM(cache_creation),0) AS cw,
                   COALESCE(SUM(cache_read),0)     AS cr,
                   COALESCE(SUM(cost),0.0)         AS cost,
                   COUNT(*)                        AS turns
            FROM turns WHERE {where}""",
        params,
    ).fetchone()
    d = dict(row)
    d["tokens"] = d["inp"] + d["out"] + d["cw"] + d["cr"]
    return d


def totals_for_date(conn, day: str) -> dict:
    return _totals_row(conn, "date_local = ?", (day,))


def totals_for_session(conn, session_id: str) -> dict:
    return _totals_row(conn, "session_id = ?", (session_id,))


def totals_all(conn) -> dict:
    return _totals_row(conn, "1=1", ())


def by_model(conn, where: str = "1=1", params: tuple = ()) -> list[dict]:
    rows = conn.execute(
        f"""SELECT model,
                   SUM(input_tokens) inp, SUM(output_tokens) out,
                   SUM(cache_creation) cw, SUM(cache_read) cr,
                   SUM(cost) cost, COUNT(*) turns
            FROM turns WHERE {where}
            GROUP BY model ORDER BY cost DESC""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def by_project(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT project, SUM(cost) cost,
                  SUM(input_tokens+output_tokens+cache_creation+cache_read) tokens,
                  COUNT(*) turns
           FROM turns GROUP BY project ORDER BY cost DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def daily_series(conn, days: int = 7) -> list[dict]:
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        t = totals_for_date(conn, d)
        out.append({"date": d, **t})
    return out
