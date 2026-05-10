# Novokine candidate dossier — ERBB4 + IL6R
_Generated from experience buffer record `68bedb01-e150-42c7-9154-f75424fbce90` at 2026-05-05T06:31:39.379845+00:00 (mode=full)._

- **receptor_A:** `ERBB4`
- **receptor_B:** `IL6R`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB4_IL6R_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `CSRP3`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=10/10 odds=inf p=3.90e-25

## Track B — mechanism coherence
- chain_soundness (Track B): **0.685**

## Composite reward
- **composite reward:** +0.7899  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.6852 (weight: 0.33)
  - `track_a5`: +0.0533 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.0769
- co-expression in **young**: MF-I, MF-II
- ⚠ aged-dropout cell types: MF-I, MF-II
- ECD asymmetry ratio: 1.86× (H2F = 1.78×)
- families: RTK_ErbB × Cytokine
