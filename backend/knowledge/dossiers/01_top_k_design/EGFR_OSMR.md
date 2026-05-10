# Novokine candidate dossier — EGFR + OSMR
_Generated from experience buffer record `204337ca-44a8-4bbc-b5f6-69e1472763e3` at 2026-05-05T06:14:24.262920+00:00 (mode=full)._

- **receptor_A:** `EGFR`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `EGFR_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `ITGA8`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `PRUNE2`, `CSRP3`, `HDAC9`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.8918  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.108
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.826**

## Composite reward
- **composite reward:** +0.7903  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.8918 (weight: 0.56)
  - `track_b`: +0.8261 (weight: 0.33)
  - `track_a5`: +0.1753 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.1083
- co-expression in **old**: FB
- ECD asymmetry ratio: 1.16× (H2F = 1.78×)
- families: RTK_ErbB × Cytokine
