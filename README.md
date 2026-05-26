# Claude Live Usage — Terminal Plugin

Live Claude Code token/cost usage rendered **in the terminal itself**, via Claude
Code's `statusLine` hook — plus a terminal CLI and a browser dashboard.

```
● Opus 4.7 (1M) │ ses $0.42 │ today 9.9M $10.02 │ 5h 23% ↻2h13m │ wk 41% ↻3d4h │ Projects
```

The status line updates live while you work: current model, this-session cost,
today's tokens + cost, your **5-hour session** and **7-day (weekly) rate-limit**
usage with reset ETAs, and the active project name.

Inspired by [phuryn/claude-usage](https://github.com/phuryn/claude-usage); the new
part here is the live status-line integration so usage updates as you work.

## Highlights

- **Zero dependencies** — Python 3.10+ standard library only (`sqlite3`,
  `http.server`, `json`, `pathlib`). No `pip install`, no virtualenv.
- **Live in the status line** — usage refreshes on every Claude Code update.
- **Rate-limit aware** — surfaces Pro/Max 5-hour and weekly limit percentages with
  colour (green/yellow/red) and time-until-reset, as soon as Claude Code reports
  them.
- **Incremental & cheap** — only new bytes of changed transcripts are parsed, so
  running on every conversation update stays fast.
- **Self-contained** — its own DB at `data/usage.db`; never touches
  `~/.claude/usage.db` or modifies your transcripts.
- **Crash-proof** — the status-line command can never break your terminal; on any
  error it prints `usage: unavailable` and exits cleanly.

## How the live status line works

Claude Code runs the configured `statusLine.command` on every conversation update
and pipes session JSON on stdin. `statusline.py`:

1. Reads that JSON (model, workspace, session id, `cost.total_cost_usd`, and
   `rate_limits`).
2. Runs a cheap **incremental** scan of `~/.claude/projects/*.jsonl` (only new
   bytes of changed files, resuming by byte offset).
3. Prints one line: model · this-session cost · today's tokens + cost · 5h limit ·
   weekly limit · project.

Session cost prefers Claude Code's own `cost.total_cost_usd` when present, falling
back to the value computed from the DB. Rate-limit segments only appear once Claude
Code has reported them (i.e. after the first API response of a session) — which is
why they "pop in" shortly after you send your first message.

### Status-line anatomy

| Segment | Source | Example |
|---|---|---|
| `● model` | `model.display_name` / `id` | `● Opus 4.7 (1M)` |
| `ses $` | stdin `cost.total_cost_usd`, else DB by session | `ses $0.42` |
| `today <tok> $` | DB totals for local date | `today 9.9M $10.02` |
| `5h <pct> ↻<eta>` | stdin `rate_limits.five_hour` | `5h 23% ↻2h13m` |
| `wk <pct> ↻<eta>` | stdin `rate_limits.seven_day` | `wk 41% ↻3d4h` |
| `project` | workspace dir basename | `Projects` |

Percentages are coloured by usage: **green** < 50%, **yellow** 50–80%, **red** ≥ 80%.

## Install / uninstall

```bash
python3 cli.py install     # adds statusLine to ~/.claude/settings.json (other keys preserved)
python3 cli.py uninstall   # removes the statusLine entry
```

`install` writes a `statusLine` block of the form:

```json
{
  "statusLine": {
    "type": "command",
    "command": "/usr/bin/python3 /abs/path/to/statusline.py statusline",
    "padding": 0
  }
}
```

It preserves any other keys already in `settings.json`. Restart Claude Code (or
start a new session) to see the line.

## Terminal commands

```bash
python3 cli.py scan        # incremental parse into data/usage.db
python3 cli.py today       # today's usage by model
python3 cli.py week        # last 7 days (per-day + by-model totals)
python3 cli.py stats       # all-time totals, by-model, by-project (top 15)
python3 cli.py statusline  # emit one status line (reads Claude Code JSON on stdin)
python3 cli.py dashboard   # scan + serve the browser dashboard
python3 cli.py install     # wire the status line into settings.json
python3 cli.py uninstall   # remove it
```

`scan` accepts an optional path to override the transcript directory:
`python3 cli.py scan /path/to/projects`.

## Browser dashboard

```bash
python3 cli.py dashboard           # serves http://localhost:8080, opens browser
HOST=0.0.0.0 PORT=9000 python3 cli.py dashboard
```

A single-page, dark-themed dashboard (stdlib `http.server` + Chart.js via CDN) with
summary cards, a 7-day daily-cost bar chart, and a cost-by-model doughnut. It
auto-refreshes every 30s and re-scans on each `/api/summary` request.

## Module map

| File | Responsibility |
|---|---|
| `pricing.py` | Model → USD rates; per-record cost (opus/sonnet/haiku only) |
| `db.py` | SQLite schema, connection, aggregate queries |
| `scanner.py` | Incremental JSONL → SQLite (size+mtime tracked, resumes by offset) |
| `statusline.py` | Reads stdin JSON, prints the one-line status |
| `dashboard.py` | stdlib HTTP server + Chart.js single-page dashboard |
| `cli.py` | Subcommand dispatch + install/uninstall |
| `tests/test_core.py` | Unit tests (pricing, scan, aggregates) |

## Data model

A self-contained SQLite DB at `data/usage.db` with two tables:

- **`processed_files`** — `(path, size, mtime)` per scanned transcript, enabling
  incremental resume: unchanged files are skipped, grown files are read only from
  the last offset.
- **`turns`** — one row per assistant turn, keyed by `uuid` (`INSERT OR IGNORE`
  makes re-scans idempotent). Stores `session_id`, `project`, `cwd`, `model`,
  timestamp, local date, the four token counts (input / output / cache-creation /
  cache-read) and the computed `cost`. Indexed on `date_local` and `session_id`.

The scanner reads from `~/.claude/projects/` (and the Xcode CodingAssistant path on
macOS), ingesting only records of `type == "assistant"` that carry a `usage` block.

## Cost basis

Anthropic API per-MTok rates used for estimates:

| Model | Input | Output | Cache write (5m) | Cache read |
|---|---|---|---|---|
| Opus | $5.00 | $25.00 | $6.25 | $0.50 |
| Sonnet | $3.00 | $15.00 | $3.75 | $0.30 |
| Haiku | $1.00 | $5.00 | $1.25 | $0.10 |

Only models whose name contains `opus`/`sonnet`/`haiku` are priced; anything else
(unknown or local models) reports `$0.00` / `n/a`. **Subscription (Pro/Max) real
cost differs** — these are API-equivalent estimates of what the same usage would
cost on pay-as-you-go.

## Requirements

- Python **3.10+** (uses `X | Y` type unions)
- Claude Code (for the live status line; the CLI and dashboard work standalone
  against existing transcripts)
- No third-party packages

## Privacy

Everything runs locally. Transcripts are read from your machine, parsed into a
local SQLite file, and never sent anywhere. The dashboard binds to `localhost` by
default.

## Tests

```bash
python3 -m pytest -q     # 8 tests
```

## Troubleshooting

- **Status line shows nothing / `usage: unavailable`** — confirm
  `~/.claude/settings.json` has the `statusLine` entry (re-run `cli.py install`)
  and restart Claude Code.
- **Rate-limit segments (`5h`/`wk`) missing** — they only appear after Claude Code
  reports `rate_limits`, i.e. once the session has made its first API call. They
  also require a Pro/Max subscription; API-key billing has no such windows.
- **Costs look low / `n/a`** — the model isn't in the priced set, or usage came
  from a local/unknown model.
- **Nothing ingested** — check that `~/.claude/projects/` exists and contains
  `*.jsonl` transcripts; pass an explicit path to `cli.py scan`.

## License

Personal project. See repository for terms.

## Acknowledgments

- [phuryn/claude-usage](https://github.com/phuryn/claude-usage) for the original
  idea of parsing Claude Code transcripts for usage.
- Chart.js for the dashboard charts.
