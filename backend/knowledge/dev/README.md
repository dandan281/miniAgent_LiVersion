# Developer plans, sessions, and status reports

This folder is for developer-facing project state — plans, session writeups,
chronological logs, and the current next-action cheatsheet. **Biological
reference docs and SOPs do NOT belong here**; they stay in
`backend/knowledge/` directly.

## Layout

```
dev/
├── NEXT_ACTIONS.md                          # evergreen cheatsheet of commands to run today
├── plans/                                   # design docs and session-scoped plans
│   ├── master_rejuvenation_plan_v2.md       # ACTIVE master plan (evidence-stacking pivot)
│   ├── master_rejuvenation_rl_plan.md       # SUPERSEDED — historical RL-loop record
│   └── YYYY-MM-DD_<period>_plan.md          # session-specific plans
├── sessions/                                # one folder of artifacts per work session
│   └── YYYY-MM-DD_<period>_<doctype>.md
├── stage_reports/                           # v2 evidence-stacking per-stage reports
│   └── vNN_<feature_name>.md                # one per attempted feature (KEEP and DROP)
└── v2_run_ledger.jsonl                      # append-only ledger of stage commits/rejections
```

## Naming convention

All session files use the pattern:

    YYYY-MM-DD_<period>_<doctype>.md

- `YYYY-MM-DD` — UTC date the session started
- `<period>` — one of `morning | afternoon | evening | overnight`
- `<doctype>` — one of:
  - `summary`  — full session writeup (long form)
  - `exec`     — one-page executive snapshot
  - `live`     — auto-generated state at session time (e.g. leaderboard)
  - `run_log`  — chronological event log written during the session
  - `plan`     — pre-session plan (lives under `plans/`, not `sessions/`)

Example:

- `plans/2026-05-04_overnight_plan.md` — what we intended to do
- `sessions/2026-05-04_overnight_summary.md` — what actually happened
- `sessions/2026-05-04_overnight_exec.md` — one-page version for fast review
- `sessions/2026-05-04_overnight_live.md` — auto-leaderboard captured during the run
- `sessions/2026-05-04_overnight_run_log.md` — chronological events
- `sessions/2026-05-04_afternoon_summary.md` — followup session

## What goes where

| File type                                | Folder                |
| ---------------------------------------- | --------------------- |
| Master design doc                        | `dev/plans/`          |
| Pre-session plan                         | `dev/plans/`          |
| Post-session writeup / exec / log / live | `dev/sessions/`       |
| Today's command cheatsheet               | `dev/NEXT_ACTIONS.md` |
| Biological SOPs / playbooks / domain notes | `backend/knowledge/` (parent dir) |
| Atlas DEG JSONs, raw data caches         | `backend/knowledge/<topic>/` (parent dir) |

## Adding a new session

1. Pick `YYYY-MM-DD_<period>` for the session.
2. (Optional) write `dev/plans/<that>_plan.md` before starting.
3. After the session, write `dev/sessions/<that>_summary.md` with what
   happened, what was implemented, and what's left.
4. Update `dev/NEXT_ACTIONS.md` with the immediate cheatsheet for tomorrow.
