# Novokine candidate dossier — ERBB3 + IL6ST
_Generated from experience buffer record `37805008-1468-45fd-a8fc-a97cc3e78cae` at 2026-05-05T08:43:15.454768+00:00 (mode=full)._

- **receptor_A:** `ERBB3`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB3_IL6ST_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB3+IL6ST: NRG sensing + JAK/STAT

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `TIMP3`, `IGFBP7`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=10/10 odds=inf p=3.90e-25

## Track B — mechanism coherence
- chain_soundness (Track B): **0.709**

## Composite reward
- **composite reward:** +0.7830  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7090 (weight: 0.33)
  - `track_a5`: -0.0798 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
