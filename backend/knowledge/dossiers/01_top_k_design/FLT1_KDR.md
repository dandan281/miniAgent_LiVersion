# Novokine candidate dossier — KDR + FLT1
_Generated from experience buffer record `e3980dcb-a37a-4a2e-bf52-6bc91e09907e` at 2026-05-05T08:14:02.163732+00:00 (mode=full)._

- **receptor_A:** `KDR`
- **receptor_B:** `FLT1`
- **linker:** `flexible_GS4`
- **candidate_id:** `KDR_FLT1_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
VEGFR2 + VEGFR1 (vascular axis)

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `TAGLN`, `MYH11`, `MYOM2`, `MYL6`, `TIMP3`, `IGFBP7`, `CLIC4`, `PPP1R14A`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CSRP3`, `PRUNE2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=10/10 odds=inf p=3.90e-25

## Track B — mechanism coherence
- chain_soundness (Track B): **0.656**

## Composite reward
- **composite reward:** +0.7776  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.6559 (weight: 0.33)
  - `track_a5`: +0.0305 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
