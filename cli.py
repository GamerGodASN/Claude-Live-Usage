#!/usr/bin/env python3
"""Claude Live Usage — terminal CLI.

  scan        Incrementally parse transcripts into the usage DB
  today       Today's usage by model
  week        Last 7 days (per-day + by-model)
  stats       All-time totals, by-model, by-project
  statusline  Emit one status-line (reads Claude Code JSON on stdin)
  dashboard   Scan + serve the browser dashboard
  install     Wire the status line into ~/.claude/settings.json
  uninstall   Remove the status line from settings.json
"""

import json
import shlex
import sys
from datetime import date
from pathlib import Path

import db
import pricing
import scanner

SETTINGS = Path.home() / ".claude" / "settings.json"
SELF = Path(__file__).resolve()


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _print_model_rows(rows: list[dict]) -> None:
    if not rows:
        print("  (no usage)")
        return
    print(f"  {'model':<22}{'turns':>7}{'tokens':>16}{'cost':>12}")
    for r in rows:
        tok = r["inp"] + r["out"] + r["cw"] + r["cr"]
        cost = "n/a" if pricing.family(r["model"]) is None else f"${r['cost']:,.2f}"
        print(f"  {r['model'][:22]:<22}{r['turns']:>7}{tok:>16,}{cost:>12}")


def cmd_scan(args) -> None:
    n = scanner.scan(projects_dir=args[0] if args else None)
    print(f"Scanned. {n} new turn(s) ingested into {db.DB_PATH}")


def cmd_today(_args) -> None:
    conn = db.connect()
    scanner.scan(conn=conn)
    today = date.today().isoformat()
    t = db.totals_for_date(conn, today)
    print(f"\nUsage for {today}")
    print(f"  tokens: {_fmt_tokens(t['tokens'])}   cost: ${t['cost']:,.2f}   turns: {t['turns']}\n")
    _print_model_rows(db.by_model(conn, "date_local = ?", (today,)))
    conn.close()


def cmd_week(_args) -> None:
    conn = db.connect()
    scanner.scan(conn=conn)
    print("\nLast 7 days")
    print(f"  {'date':<12}{'tokens':>16}{'cost':>12}")
    grand = 0.0
    for d in db.daily_series(conn, 7):
        print(f"  {d['date']:<12}{d['tokens']:>16,}${d['cost']:>10,.2f}")
        grand += d["cost"]
    print(f"  {'-'*40}\n  {'total':<12}{'':>16}${grand:>10,.2f}\n")
    _print_model_rows(db.by_model(conn))
    conn.close()


def cmd_stats(_args) -> None:
    conn = db.connect()
    scanner.scan(conn=conn)
    t = db.totals_all(conn)
    print("\nAll-time usage")
    print(f"  tokens: {_fmt_tokens(t['tokens'])}   cost: ${t['cost']:,.2f}   turns: {t['turns']}\n")
    print("By model:")
    _print_model_rows(db.by_model(conn))
    print("\nBy project:")
    for p in db.by_project(conn)[:15]:
        print(f"  {p['project'][:28]:<28}{p['tokens']:>16,}${p['cost']:>10,.2f}")
    conn.close()


def cmd_statusline(_args) -> None:
    import statusline
    statusline.main()


def cmd_dashboard(_args) -> None:
    import dashboard
    dashboard.serve()


def _statusline_command() -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(SELF))} statusline"


def cmd_install(_args) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    cfg["statusLine"] = {"type": "command", "command": _statusline_command(), "padding": 0}
    SETTINGS.write_text(json.dumps(cfg, indent=2) + "\n")
    scanner.scan()
    print("Installed status line into", SETTINGS)
    print("Command:", cfg["statusLine"]["command"])
    print("Restart Claude Code (or start a new session) to see it.")


def cmd_uninstall(_args) -> None:
    if not SETTINGS.exists():
        print("No settings.json found.")
        return
    cfg = json.loads(SETTINGS.read_text())
    if cfg.pop("statusLine", None) is None:
        print("No statusLine entry present.")
        return
    SETTINGS.write_text(json.dumps(cfg, indent=2) + "\n")
    print("Removed status line from", SETTINGS)


COMMANDS = {
    "scan": cmd_scan, "today": cmd_today, "week": cmd_week, "stats": cmd_stats,
    "statusline": cmd_statusline, "dashboard": cmd_dashboard,
    "install": cmd_install, "uninstall": cmd_uninstall,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    COMMANDS[sys.argv[1]](sys.argv[2:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
