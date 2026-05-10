# Novokine candidate dossier — FGFR1 + IL6ST
_Generated from experience buffer record `9a644dcd-3673-48b5-b1d2-3a5363f09a02` at 2026-05-05T05:54:03.962046+00:00 (mode=full)._

- **receptor_A:** `FGFR1`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR1_IL6ST_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `CCND1`, `MYC`, `BCL2`, `SOCS3`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `NFKBIA`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9235  (verdict: **REJUVENATING**)
- P2 (young) overlap: +0.994 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +0.997 | neg_total (anti-rejuv): +0.074
- Fisher up vs P2: overlap=8/12 odds=73.71 p=1.14e-10
- Fisher down vs P1: overlap=8/11 odds=769.86 p=5.43e-18

## Track B — mechanism coherence
- chain_soundness (Track B): **0.761**

## Composite reward
- **composite reward:** +0.7955  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9235 (weight: 0.56)
  - `track_b`: +0.7606 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.1917
- co-expression in **old**: FB
- co-expression in **young**: FB, EnFB, PnFB
- ⚠ aged-dropout cell types: EnFB, PnFB
- ECD asymmetry ratio: 1.69× (H2F = 1.78×)
- families: RTK_FGFR × Cytokine
