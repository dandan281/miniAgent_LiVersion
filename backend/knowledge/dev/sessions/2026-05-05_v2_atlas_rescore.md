# v2 atlas top-3 re-score — 2026-05-05

First scoring of the overnight RL top-3 candidates against the **multi-source v2 consensus atlas**.

## v2 atlas sources (this run)

3 conceptually independent sources, ≥2-source consensus voting:
1. **`integrated_3_studies`** — user-supplied meta-analysis combining bulk DEGs from GSE164471 (Tumasian 2021), GSE111016 (Pillon 2019), and GTEx v11 with cell-type-resolved labels. Located at `backend/knowledge/aging_studies/muscle_atlas_integrated/integrated_per_celltype_degs.csv`. 956 thresholded calls (padj<0.05, |lfc|>0.5). Replaces the three separate bulk slots to avoid double-counting.
2. **`kedlian_2024`** — Kedlian/Lacraz 2024 Nat Aging Supplementary Table 3 (`AgeDEGs_sc_broad_celltypes`). 471 thresholded calls (ltsr>0.95, |lfc|>0.5).
3. **`lai_2024`** — Lai 2024 Nature Supplementary Table 5 (Pearson age-correlation per cell type, 3 sub-tables: Type I myofibres, Type II myofibres, qMuSC). 6,308 thresholded calls (|R|>0.30, p<0.05).

Sub-tasks subsumed by the integrated source (no longer loaded):
- `GSE164471_tumasian_2021/deg_table.tsv` (PyDESeq2 re-derivation)
- `GSE111016_pillon_2019/deg_table.tsv` (Supp Data 4 extraction)
- `gtex_v11_skeletal_muscle/deg_table.tsv` (was pending user upload)

## v2 atlas state

- **P1_up** (aged-enriched, ≥2 sources): **29 genes**
- **P2_up** (young-enriched, ≥2 sources): **189 genes**
- **Per-cell-type calls**: 10 cell types resolved
- 14 schema/structural tests pass; 2 biology-sanity tests skipped (gated on full 5-source panel which is no longer the design after integration)

Top P1_up genes by source support:
- **3 sources**: GPX3, TXNIP
- **2 sources**: ACTB, C12ORF75, CD52, CORO1A, CTSW, DEPP1, EFEMP1, FABP5, **FOS**, **JUN**, KCNQ5, MAP3K20, MCU, MYF5, MYF6, MYL12A, NEAT1, NPC2, PAM, PFKFB3, PPDPFL, S100A10, S100A4, SAT1, SPRY1, SQSTM1, TPM3

Biology check:
- ✅ Aged-enriched textbook (FOS, JUN, GPX3, NEAT1, TXNIP, SAT1, PFKFB3, SQSTM1) all present
- ✅ Young-enriched muscle structure (TPM1, MYLPF, ANKRD2, IGF1, TRDN) present
- ⚠️ Some canonical genes absent (CDKN1A, EDA2R, MYH7, MYH2, ACTA2, MYL9, MYH11) — likely because the integrated CSV is pre-filtered to top ~200 genes per cell type and these didn't make all cuts.

## Re-scoring

| Candidate | v1 (single-source) | v2 (3-source consensus) | v2 verdict |
|---|---|---|---|
| **ERBB4 + INSR + rigid_helix_20** | +1.000 | **+1.000** | REJUVENATING |
| **INSR + IL6ST + flexible_GS8** | +1.000 | +0.947 | REJUVENATING |
| **EGFR + IL6ST + flexible_GS8** | +1.000 | +0.844 | REJUVENATING |

### Per-candidate detail

**EGFR + IL6ST + flexible_GS8** (10 up / 10 down)
- v1: 10/10 up genes hit P2_up (out of 536 ref); 10/10 down hit P1_up (out of 77)
- v2: 5/10 up hit P2_up (out of 189 ref); 4/10 down hit P1_up (out of 29)

**ERBB4 + INSR + rigid_helix_20** (15 up / 15 down)
- v1: 15/15 up hit P2_up (536); 15/15 down hit P1_up (77)
- v2: 9/15 up hit P2_up (189); 5/15 down hit P1_up (29)

**INSR + IL6ST + flexible_GS8** (12 up / 11 down)
- v1: 12/12 up hit P2_up (536); 10/11 down hit P1_up (77)
- v2: 7/12 up hit P2_up (189); 4/11 down hit P1_up (29)

## Interpretation

- **All three candidates remain REJUVENATING under multi-source consensus.** No re-ordering of which candidates are "good" vs "bad."
- v1 saturated all three at +1.0 (large ref pool → every overlap maxed the Fisher score). v2's stricter, multi-source-validated reference pool separates them: **ERBB4+INSR is the clearest top candidate**.
- The agent had converged on a single "rejuvenating signature template" across runs (all three predicted overlapping genes: ACTA2/MYL9/MYH11/MYOM2/TAGLN up; EGR1/FOS/JUN/TXNIP/OTUD1 down). The fact that ERBB4+INSR predicted a *longer* signature (15 vs 10-12) gave it more overlap depth with the consensus pool and pushed it ahead.
- **No candidate flipped to ANTI-REJUVENATING**, which is the most important sanity check — the single-source atlas wasn't generating false-positive rejuvenators.

## Implications for the RL loop

1. **Track A is now defensible against batch effects**: each gene reaching P1_up/P2_up has support from ≥2 of 3 independent sources spanning bulk meta-analysis + 2 single-cell atlases.
2. **Saturation problem partially solved**: v1's +1.0 ceiling for any reasonable rejuvenating signature meant Track A couldn't discriminate among top candidates. v2's ranking spread (0.84–1.00) provides usable signal between near-tied candidates.
3. **Residual saturation**: ERBB4+INSR still saturates v2 at +1.0. To break that, either tighten the score-component cap (currently neg_log10_p / 10) or require finer cell-type-specific scoring.

## Next actions

- (Optional) Switch `rl_loop.py` default to `--atlas-version v2` once we trust the consensus pool. For now, keep v1 as default to preserve the 79-run buffer's reproducibility.
- (Optional) Run a fresh batch of new pair candidates with `--atlas-version v2` to see if the discrimination affects search behavior.
- Investigate why the integrated DEG CSV is filtered to top 200 per cell type — if a fuller version exists, it would fill in CDKN1A, EDA2R, MYH7, etc.
