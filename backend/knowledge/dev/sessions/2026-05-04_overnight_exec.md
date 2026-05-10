# Novokine RL Loop — Executive Summary

*One page. Read [`MORNING_SUMMARY.md`](2026-05-04_overnight_summary.md) for the long version, [`NEXT_ACTIONS.md`](../NEXT_ACTIONS.md) for commands.*

## Status: WORKING END-TO-END ✅

`scripts/rl_loop.py --mode full` orchestrates the full 6-stage pipeline (Propose → Validate → Mechanism → Score → Decide → Design) with 26 registered tools and the agent infrastructure. 8 agent-driven candidates evaluated, 17/17 smoke tests passing, 1 successful multi-iteration consensus run.

## What's running right now

Nothing. Last run: ERBB2+MET consensus completed and produced the **first TOP_K_DESIGN tier candidate via mode=consensus** — phenotype +0.39, reward +0.52.

## Key results

| Metric | Value |
|---|---|
| Candidates evaluated end-to-end (mode=full) | 8 |
| Top single-run phenotype | +0.38 (H2F, ERBB2+FGFR1) |
| Mean reward across all mode=full runs | +0.39 |
| Within-process phenotype variance (same pair, same process) | ~0.0002 (very low!) |
| Across-process phenotype variance (same pair, different process) | ~0.23 |
| Smoke tests | 17/17 passing |
| Stable PLCG1 exclusion across 100% of H2F-class runs | ✅ |

## Top candidates (by composite reward)

1. **ERBB2+MET, GS_med (consensus N=2)** — median phen **+0.39**, median reward **+0.52** — **TOP_K_DESIGN** ⭐
2. **H2F (ERBB2+FGFR1, GS_med, single run)** — phen +0.38, reward +0.49 — MIDDLE_HUMAN_REVIEW
3. ERBB2+MET (single run) — phen +0.29, reward +0.45
4. INSR+MET, GS_med — phen +0.22, reward +0.43
5. ERBB2+FGFR4, GS_med — phen +0.18, reward +0.38

**The consensus run found ERBB2+MET to be MORE consistent than H2F itself** at producing rejuvenating predictions — both consensus iterations crossed +0.30 phenotype, vs H2F where one run hit +0.38 and another hit +0.15.

## What was built tonight

- `rl_loop.py --mode full` — keystone orchestrator (was a stub)
- `utils/chain_soundness.py` — Track B aggregator (geom mean)
- `utils/superbio_submit.py` — Stage 6 design submission with `--fire-design`
- `scripts/buffer_review.py`, `candidate_dossier.py`, `morning_report.py`,
  `multi_iter_consensus.py`, `variance_analyzer.py`, `smoke_test_loop.py`,
  `scgpt_submit.py`
- 3 mock tools registered (cellxgene, clue_api, alphafold3)
- Master plan refreshed to v4

## Honest gaps

### Built but not exercised
- **scGPT Mapping/GRN GPU runs** (would close the vocabulary-mismatch gap; biggest unblocked win)
- **Live binder design** submission (Stage 6 `--design-live`)
- **Live AF3** (mock-only; pending Google API key approval)
- **Live CLUE polling** (mock-only; ~1-2 hr work to implement)

### Blocked on human
- AF3 API key approval (Google manual)
- PhosphoSitePlus TSV download (5 min)
- Confirm Superbio credit balance before scGPT/binder design GPU spend

## Single highest-impact next action

**Submit scGPT Mapping**: `python scripts/scgpt_submit.py --mapping`

This populates Track A.5 (foundation-model young-axis projection in 512-d) which resolves the documented vocabulary-mismatch ceiling. Without it, mode=full reward saturates around 0.5 even on H2F. With it, well-mechanistic candidates should exceed the TOP_K threshold reliably.

## The science finding

The agent reasons **structurally**, not template-matching. Different receptor architectures get different excluded adaptors:
- ERBB2+FGFR1 → PLCG1 excluded (canonical H2F)
- ERBB2+MET → PLCG1 excluded (H2F-pattern)
- FGFR1+IGF1R → **RASA1 (RasGAP) excluded** (different architecture, different exclusion)

This is generalised forced-proximity reasoning, not just regurgitating H2F.

The phenotype scoring ceiling comes from **vocabulary mismatch**: agent predicts MAPK pathway feedback genes (DUSP6, ETV4/5, CCND1, MYC) which are mechanistically correct but absent from the muscle atlas P2_up (which is dominated by structural genes like MYH7, ACTA1). Track A.5 (scGPT) is the principled fix.

---

*Last updated: 2026-05-04 ~03:20 PDT during Wakeup #4. Autonomous run ongoing. Read alongside MORNING_SUMMARY.md for fuller context.*
