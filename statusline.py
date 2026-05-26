"""Claude Code statusLine command.

Reads the session JSON Claude Code pipes on stdin, refreshes the usage DB with a
cheap incremental scan, and prints ONE line: model, this-session cost, today's
tokens + cost, and the project name. Must never crash the host terminal.
"""

import json
import sys
import time
from datetime import date

import db
import scanner

# 256-colour ANSI
DIM = "\033[2m"
BOLD = "\033[1m"
ORANGE = "\033[38;5;208m"
CYAN = "\033[38;5;44m"
GREEN = "\033[38;5;42m"
YELLOW = "\033[38;5;220m"
RED = "\033[38;5;203m"
GREY = "\033[38;5;245m"
RESET = "\033[0m"
SEP = f" {DIM}│{RESET} "


def humanize_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.005 else "$0.00"


def pct_color(p: float) -> str:
    if p >= 80:
        return RED
    if p >= 50:
        return YELLOW
    return GREEN


def fmt_eta(resets_at) -> str:
    """Unix-epoch reset time -> compact 'until reset' string (e.g. 2h13m, 3d4h)."""
    try:
        secs = int(resets_at) - int(time.time())
    except (TypeError, ValueError):
        return ""
    if secs <= 0:
        return "now"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m}m"
    return f"{m}m"


def limit_seg(label: str, window: dict | None) -> str | None:
    """One rate-limit segment: '5h 23% ↻2h13m', coloured by usage. None if absent."""
    window = window or {}
    p = window.get("used_percentage")
    if p is None:
        return None
    eta = fmt_eta(window.get("resets_at"))
    eta_s = f" {DIM}↻{eta}{RESET}" if eta else ""
    return f"{GREY}{label}{RESET} {pct_color(p)}{p:.0f}%{RESET}{eta_s}"


def _read_stdin() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def build_line(data: dict) -> str:
    model = (data.get("model") or {})
    model_name = model.get("display_name") or model.get("id") or "claude"
    model_name = model_name.replace("claude-", "")
    ws = data.get("workspace") or {}
    project = ws.get("project_dir") or ws.get("current_dir") or data.get("cwd") or ""
    project = project.rsplit("/", 1)[-1] if project else "—"
    session_id = data.get("session_id") or data.get("sessionId") or ""

    conn = db.connect()
    try:
        scanner.scan(conn=conn)
        today = db.totals_for_date(conn, date.today().isoformat())
        ses = db.totals_for_session(conn, session_id) if session_id else None
    finally:
        conn.close()

    # Prefer Claude Code's own session cost if it provides one.
    stdin_cost = (data.get("cost") or {}).get("total_cost_usd")
    if stdin_cost is not None:
        ses_cost = float(stdin_cost)
    else:
        ses_cost = ses["cost"] if ses else 0.0

    # Subscription rate limits (Pro/Max): present only after the first API
    # response, so guard everything — missing windows just drop out.
    rl = data.get("rate_limits") or {}

    parts = [
        f"{ORANGE}●{RESET} {BOLD}{model_name}{RESET}",
        f"{GREY}ses{RESET} {GREEN}{money(ses_cost)}{RESET}",
        f"{GREY}today{RESET} {CYAN}{humanize_tokens(today['tokens'])}{RESET} {GREEN}{money(today['cost'])}{RESET}",
    ]
    for seg in (
        limit_seg("5h", rl.get("five_hour")),   # session window + next reset
        limit_seg("wk", rl.get("seven_day")),   # 7-day (weekly) limit
    ):
        if seg:
            parts.append(seg)
    parts.append(f"{DIM}{project}{RESET}")
    return SEP.join(parts)


def main() -> None:
    try:
        line = build_line(_read_stdin())
    except Exception:  # never break the terminal
        line = f"{ORANGE}●{RESET} {DIM}usage: unavailable{RESET}"
    sys.stdout.write(line + "\n")


if __name__ == "__main__":
    main()
