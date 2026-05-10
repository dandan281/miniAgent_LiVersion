# Novokine candidate dossier — FGFR1 + TNFRSF1A
_Generated from experience buffer record `c01b3c79-eb00-4e7c-9b4a-ff8a5b4d4e1e` at 2026-05-05T05:50:03.596388+00:00 (mode=full)._

- **receptor_A:** `FGFR1`
- **receptor_B:** `TNFRSF1A`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR1_TNFRSF1A_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `PPARGC1A`, `VEGFA`, `CCND1`, `MYC`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `NFKBIA`, `TNFAIP3`, _(+2 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9361  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.064
- Fisher up vs P2: overlap=10/15 odds=73.99 p=4.68e-13
- Fisher down vs P1: overlap=8/14 odds=384.87 p=9.78e-17

## Track B — mechanism coherence
- chain_soundness (Track B): **0.702**

## Composite reward
- **composite reward:** +0.7830  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9361 (weight: 0.56)
  - `track_b`: +0.7021 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.2103
- co-expression in **old**: FB, EnFB
- co-expression in **young**: EnFB
- ECD asymmetry ratio: 1.86× (H2F = 1.78×)
- families: RTK_FGFR × TNFR
