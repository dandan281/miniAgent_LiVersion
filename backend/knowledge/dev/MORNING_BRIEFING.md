# Morning Briefing — what to read first

You authorized an 8-hour autonomous overnight run. Here's what you'll find when you wake up:

## ⭐ The headline result

**Top 3 novokine candidates ready for design pipeline submission**:

1. **EGFR + IL6ST + flexible_GS8 linker** — reward **+0.8638** (vs H2F's +0.7122)
2. **ERBB4 + INSR + rigid_helix_20 linker** — reward +0.8633
3. **INSR + IL6ST + flexible_GS8 linker** — reward +0.8610

Open their dossiers at `backend/knowledge/dossiers/01_top_k_design/EGFR_IL6ST.md`, etc.

## 📊 Numbers

- **79 full-mode RL runs** across 9 batches
- **71 TOP_K_DESIGN** (90% success rate)
- **59 unique receptor pairs** covered
- **5 deployed pipeline optimizations** (43% fewer tool calls; +0.42 reward improvement on retests)
- **74 unit tests** all green

## 🔑 Key biological insight

**The IL6ST/gp130 axis is a privileged partner for muscle rejuvenation.** Of the top 20 candidates, 9 pair an RTK with IL6ST/LIFR/OSMR. gp130-mediated JAK/STAT activation paired with RTK MAPK/AKT appears to be a winning combination distinct from the H2F template.

## 📁 Files to review (in priority order)

1. `backend/knowledge/dossiers/INDEX.md` — sortable list of all 59 candidates
2. `backend/knowledge/dev/OVERNIGHT_REPORT.md` — full report with linker matrices
3. `backend/knowledge/dossiers/01_top_k_design/` — individual candidate dossiers

## 🎯 Recommended next action

Submit top-3 candidates to the AF2 / Boltz-1 binder design pipeline. Use the linker each pair preferred (matrix in OVERNIGHT_REPORT.md Section 1).

Then run `python backend/scripts/atlas_seeded_candidates.py --top 30` to see if a third batch of 10–15 ranks 16–30 surfaces any sleeper hits.

---

**Status of background processes**: All 9 batches completed. Auto-launchers exited cleanly. Receptor cache populated (28 entries fresh). Ready for next session.
