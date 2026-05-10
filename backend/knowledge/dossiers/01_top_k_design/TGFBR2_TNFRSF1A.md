# Novokine candidate dossier — TGFBR2 + TNFRSF1A
_Generated from experience buffer record `a4ece116-034b-413b-ae3a-c046427b3f07` at 2026-05-05T05:46:40.508335+00:00 (mode=full)._

- **receptor_A:** `TGFBR2`
- **receptor_B:** `TNFRSF1A`
- **linker:** `flexible_GS4`
- **candidate_id:** `TGFBR2_TNFRSF1A_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `FN1`, `COL1A1`, `SERPINE1`, `CTGF`, _(+1 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `IL32`, `TXNIP`, `OTUD1`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `TNFSF10`, `CASP3`, _(+1 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=9/13 odds=83.08 p=4.34e-12
- Fisher down vs P1: overlap=8/13 odds=461.87 p=4.21e-17

## Track B — mechanism coherence
- chain_soundness (Track B): **0.511**

## Composite reward
- **composite reward:** +0.7548  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.5110 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.2167
- co-expression in **old**: FB, PnFB
- ECD asymmetry ratio: 1.39× (H2F = 1.78×)
- families: TGFb_TypeII × TNFR
