# Novokine candidate dossier — ERBB4 + LIFR
_Generated from experience buffer record `0dab21b8-003c-4c5d-989a-d8dc79916b0d` at 2026-05-05T07:45:22.623831+00:00 (mode=full)._

- **receptor_A:** `ERBB4`
- **receptor_B:** `LIFR`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB4_LIFR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB4+LIFR new combo: NRG + LIF

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `FMN1`, `MAFB`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `PRUNE2`, `ASB5`, `TTN`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/12 odds=inf p=1.22e-19
- Fisher down vs P1: overlap=11/12 odds=3320.33 p=1.56e-26

## Track B — mechanism coherence
- chain_soundness (Track B): **0.748**

## Composite reward
- **composite reward:** +0.7960  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7480 (weight: 0.33)
  - `track_a5`: -0.0798 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
