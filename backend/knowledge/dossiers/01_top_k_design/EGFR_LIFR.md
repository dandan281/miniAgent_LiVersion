# Novokine candidate dossier — EGFR + LIFR
_Generated from experience buffer record `7a0d2e9d-baad-4d63-b323-4c6e3eb14ca7` at 2026-05-05T06:10:41.141200+00:00 (mode=full)._

- **receptor_A:** `EGFR`
- **receptor_B:** `LIFR`
- **linker:** `flexible_GS4`
- **candidate_id:** `EGFR_LIFR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `CCND1`, `SOCS3`, `BCL2`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=8/11 odds=98.29 p=3.89e-11
- Fisher down vs P1: overlap=8/10 odds=1154.84 p=1.48e-18

## Track B — mechanism coherence
- chain_soundness (Track B): **0.734**

## Composite reward
- **composite reward:** +0.8293  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7344 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.1083
- co-expression in **old**: FB
- co-expression in **young**: FB
- ECD asymmetry ratio: 1.31× (H2F = 1.78×)
- families: RTK_ErbB × Cytokine
