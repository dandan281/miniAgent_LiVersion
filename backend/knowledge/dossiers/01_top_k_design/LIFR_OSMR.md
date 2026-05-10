# Novokine candidate dossier — LIFR + OSMR
_Generated from experience buffer record `4906f517-c857-4f1b-8ee3-1177c7e5e218` at 2026-05-05T08:04:36.914863+00:00 (mode=full)._

- **receptor_A:** `LIFR`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `LIFR_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
Same-family gp130 pair (penalty applies)

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `SOCS3`, `CCND1`, `BCL2`, `MYC`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `NFKBIA`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9235  (verdict: **REJUVENATING**)
- P2 (young) overlap: +0.994 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +0.997 | neg_total (anti-rejuv): +0.074
- Fisher up vs P2: overlap=8/12 odds=73.71 p=1.14e-10
- Fisher down vs P1: overlap=8/11 odds=769.86 p=5.43e-18

## Track B — mechanism coherence
- chain_soundness (Track B): **0.757**

## Composite reward
- **composite reward:** +0.7943  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9235 (weight: 0.56)
  - `track_b`: +0.7570 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
