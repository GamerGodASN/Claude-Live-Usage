import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
import pricing
import scanner
import statusline


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "usage.db")
    c = db.connect()
    yield c
    c.close()


# ---- pricing ----

def test_family_match():
    assert pricing.family("claude-opus-4-7") == "opus"
    assert pricing.family("claude-sonnet-4-6") == "sonnet"
    assert pricing.family("some-local-model") is None


def test_cost_known_vs_unknown():
    # 1M output tokens on opus = $25.00
    assert pricing.cost_usd("claude-opus-4-7", 0, 1_000_000, 0, 0) == pytest.approx(25.0)
    assert pricing.cost_usd("llama-3", 1_000_000, 1_000_000, 0, 0) == 0.0


# ---- scanner ----

def _write_transcript(dirpath: Path, ts: str, uuid: str, model="claude-opus-4-7"):
    rec = {
        "type": "assistant", "uuid": uuid, "sessionId": "sess-1",
        "cwd": "/home/u/Documents/Claude/Projects/Demo", "timestamp": ts,
        "message": {"model": model, "usage": {
            "input_tokens": 100, "output_tokens": 200,
            "cache_creation_input_tokens": 50, "cache_read_input_tokens": 1000}},
    }
    f = dirpath / "session.jsonl"
    with f.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return f


def test_scan_ingests_and_dedups(conn, tmp_path):
    proj = tmp_path / "projects"
    proj.mkdir()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_transcript(proj, ts, "u1")
    added = scanner.scan(projects_dir=str(proj), conn=conn)
    assert added == 1
    # re-scan: file unchanged -> nothing new
    assert scanner.scan(projects_dir=str(proj), conn=conn) == 0
    # append a new record -> incremental picks up exactly one
    _write_transcript(proj, ts, "u2")
    assert scanner.scan(projects_dir=str(proj), conn=conn) == 1
    t = db.totals_all(conn)
    assert t["turns"] == 2
    assert t["tokens"] == 2 * (100 + 200 + 50 + 1000)


def test_skips_non_assistant(conn, tmp_path):
    proj = tmp_path / "projects"
    proj.mkdir()
    (proj / "s.jsonl").write_text(json.dumps({"type": "user", "uuid": "x"}) + "\n")
    assert scanner.scan(projects_dir=str(proj), conn=conn) == 0


def test_local_date_from_utc():
    d = scanner._local_date("2026-05-26T12:43:15.110Z")
    assert d == datetime(2026, 5, 26, 12, 43, tzinfo=timezone.utc).astimezone().date().isoformat()


# ---- db queries ----

def test_today_and_session_totals(conn, tmp_path):
    proj = tmp_path / "projects"
    proj.mkdir()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_transcript(proj, ts, "u1")
    scanner.scan(projects_dir=str(proj), conn=conn)
    today = db.totals_for_date(conn, date.today().isoformat())
    assert today["turns"] == 1
    ses = db.totals_for_session(conn, "sess-1")
    assert ses["turns"] == 1
    assert ses["cost"] > 0


# ---- statusline ----

def test_humanize_and_money():
    assert statusline.humanize_tokens(2_400_000) == "2.4M"
    assert statusline.humanize_tokens(1500) == "1.5K"
    assert statusline.money(0.001) == "$0.00"
    assert statusline.money(12.5) == "$12.50"


def test_build_line_uses_stdin_cost(conn, monkeypatch):
    monkeypatch.setattr(scanner, "scan", lambda **k: 0)
    line = statusline.build_line({
        "model": {"display_name": "Opus 4.7"},
        "session_id": "sess-1",
        "workspace": {"project_dir": "/x/y/Demo"},
        "cost": {"total_cost_usd": 3.5},
    })
    assert "Opus 4.7" in line
    assert "$3.50" in line
    assert "Demo" in line
