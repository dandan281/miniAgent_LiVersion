# Novokine candidate dossier — PDGFRA + IL6ST
_Generated from experience buffer record `9c15ba4d-2976-46dc-92a3-fd1d3d3c3d52` at 2026-05-05T08:45:37.436652+00:00 (mode=full)._

- **receptor_A:** `PDGFRA`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS4`
- **candidate_id:** `PDGFRA_IL6ST_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
PDGFRA+IL6ST: PDGF+JAK/STAT

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `CCND1`, `SOCS3`, `FABP4`, `IGFBP7`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `NFKBIA`, `PRUNE2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9299  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.070
- Fisher up vs P2: overlap=10/12 odds=185.00 p=1.11e-14
- Fisher down vs P1: overlap=9/12 odds=878.82 p=2.50e-20

## Track B — mechanism coherence
- chain_soundness (Track B): **0.728**

## Composite reward
- **composite reward:** +0.7937  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9299 (weight: 0.56)
  - `track_b`: +0.7281 (weight: 0.33)
  - `track_a5`: +0.3095 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
