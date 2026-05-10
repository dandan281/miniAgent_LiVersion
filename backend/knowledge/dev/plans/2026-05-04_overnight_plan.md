# Overnight autonomous build plan — 2026-05-04

## Goal
Land 5 building blocks for the muscle-rejuvenation novokine RL loop:
1. AlphaFold 3 tool wrapper (referenced by `novokine_validation/SKILL.md` but missing).
2. CLUE/CMAP Track C tool + skill (env key already present as `CMAP_API_KEY`).
3. Candidate generator: enumerate (RTK_A, RTK_B, linker) over ~12 muscle-relevant RTKs × 5 linkers, score each with the existing Stage 4 `phenotype_checkpoint`, write ranked TSV to `backend/knowledge/candidates_v1_ranked.tsv`.
4. CZ Cell Census expression tool + `cellxgene_expression` skill (Step C — receptor expression in aged muscle).
5. Integration tests for the new tools + the existing `phenotype_checkpoint`, `omnipath_api`, `reactome_api`, `scgpt_*`. (Deferred until 1, 2, 4 land.)
6. Wire `rl_loop.py --mode full` (SSE → /api/chat). (Deferred — risk; orchestrator handles after others.)

## Why these and not Superbio/AF3 live runs
Live Superbio Mapping/GRN, live AF3 jobs, and PhosphoSitePlus license require explicit human gating. Tool *plumbing* is built tonight; live spend happens with the user awake.

## Execution
- Spawn tasks 1, 2, 3, 5 as parallel `general-purpose` background agents.
- Self-pace `/loop` wakes every 25–35 min, checks completed agents, runs smoke tests, queues task 6 (and task 4 if window remains).
- All registrations into `tools/__init__.py` are batched by the orchestrator at the end.

## Definition of done
- Each new file passes `python -c "import …"` with no error.
- Each new tool has at least one mock-mode smoke test.
- STATUS.md has one block per task with verifiable smoke-test output.
- Final orchestrator pass: registrations added, full `pytest backend/tests` runs to a clean exit (or the failures are pre-existing, not introduced).
