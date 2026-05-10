# Novokine candidate dossier — EGFR + INSR
_Generated from experience buffer record `930b66c7-3be7-4cec-9a59-baccb00149e0` at 2026-05-05T05:59:56.973705+00:00 (mode=full)._

- **receptor_A:** `EGFR`
- **receptor_B:** `INSR`
- **linker:** `flexible_GS4`
- **candidate_id:** `EGFR_INSR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `CLIC4`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `TTN`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=9/10 odds=2636.74 p=1.14e-21

## Track B — mechanism coherence
- chain_soundness (Track B): **0.758**

## Composite reward
- **composite reward:** +0.8229  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7579 (weight: 0.33)
  - `track_a5`: +0.1325 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.15
- co-expression in **old**: PnFB
- co-expression in **young**: PnFB, MF-II
- ⚠ aged-dropout cell types: MF-II
- ECD asymmetry ratio: 1.5× (H2F = 1.78×)
- families: RTK_ErbB × RTK_INSR
