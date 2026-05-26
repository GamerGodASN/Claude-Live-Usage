"""Incremental scanner: Claude Code JSONL transcripts -> SQLite.

Tracks each file's (size, mtime); on re-scan only new bytes of changed files are
read, so calling scan() from the status line on every update stays cheap.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import db
import pricing

DEFAULT_DIRS = [
    Path.home() / ".claude" / "projects",
    Path.home() / "Library" / "Developer" / "Xcode" / "CodingAssistant"
    / "ClaudeAgentConfig" / "projects",
]


def _local_date(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().date().isoformat()
    except ValueError:
        return ""


def _project_name(cwd: str, file: Path) -> str:
    if cwd:
        return Path(cwd).name
    # Fallback: decode the encoded project dir name (-a-b-c -> c).
    return file.parent.name.strip("-").split("-")[-1] or "unknown"


def _ingest_record(conn, rec: dict) -> bool:
    if rec.get("type") != "assistant":
        return False
    msg = rec.get("message") or {}
    usage = msg.get("usage") or {}
    uuid = rec.get("uuid")
    if not uuid or not usage:
        return False
    model = msg.get("model", "") or ""
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    cwd = rec.get("cwd", "") or ""
    ts = rec.get("timestamp", "") or ""
    cur = conn.execute(
        """INSERT OR IGNORE INTO turns
           (uuid, session_id, project, cwd, model, ts, date_local,
            input_tokens, output_tokens, cache_creation, cache_read, cost)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uuid, rec.get("sessionId", ""), _project_name(cwd, Path(rec.get("__file__", "."))),
         cwd, model, ts, _local_date(ts), inp, out, cw, cr,
         pricing.cost_usd(model, inp, out, cw, cr)),
    )
    return cur.rowcount > 0


def _scan_file(conn, path: Path, seen: dict) -> int:
    try:
        st = path.stat()
    except OSError:
        return 0
    prev = seen.get(str(path))
    start = 0
    if prev:
        psize, pmtime = prev
        if psize == st.st_size and pmtime == st.st_mtime:
            return 0  # unchanged
        if st.st_size >= psize:
            start = psize  # resume from where we left off
    added = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(start)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec["__file__"] = str(path)
                if _ingest_record(conn, rec):
                    added += 1
    except OSError:
        return 0
    conn.execute(
        "INSERT OR REPLACE INTO processed_files(path,size,mtime) VALUES (?,?,?)",
        (str(path), st.st_size, st.st_mtime),
    )
    return added


def scan(projects_dir: str | None = None, conn=None) -> int:
    """Scan transcript dirs; return number of new turns ingested."""
    own = conn is None
    conn = conn or db.connect()
    seen = {r["path"]: (r["size"], r["mtime"])
            for r in conn.execute("SELECT path,size,mtime FROM processed_files")}
    dirs = [Path(projects_dir)] if projects_dir else DEFAULT_DIRS
    total = 0
    for d in dirs:
        if not d.exists():
            continue
        for path in d.rglob("*.jsonl"):
            total += _scan_file(conn, path, seen)
    conn.commit()
    if own:
        conn.close()
    return total
