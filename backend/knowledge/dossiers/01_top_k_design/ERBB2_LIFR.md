# Novokine candidate dossier — ERBB2 + LIFR
_Generated from experience buffer record `b41c6eba-202b-4998-8578-358dd7d23784` at 2026-05-05T08:24:58.642228+00:00 (mode=full)._

- **receptor_A:** `ERBB2`
- **receptor_B:** `LIFR`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB2_LIFR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB2+LIFR: HER2+LIF axis

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `ASB5`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=9/10 odds=2636.74 p=1.14e-21

## Track B — mechanism coherence
- chain_soundness (Track B): **0.727**

## Composite reward
- **composite reward:** +0.8125  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7268 (weight: 0.33)
  - `track_a5`: +0.1325 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
