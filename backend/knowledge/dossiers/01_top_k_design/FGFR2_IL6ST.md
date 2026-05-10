# Novokine candidate dossier — FGFR2 + IL6ST
_Generated from experience buffer record `d940d902-9348-40c6-8f99-9582b0bf2363` at 2026-05-05T06:57:39.653009+00:00 (mode=full)._

- **receptor_A:** `FGFR2`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR2_IL6ST_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
FGFR2+IL6ST: FGFR2 highly expressed in muscle stem cells

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `CCND1`, `SOCS3`, `BCL2`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `NFKBIA`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9263  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.074
- Fisher up vs P2: overlap=8/11 odds=98.29 p=3.89e-11
- Fisher down vs P1: overlap=8/11 odds=769.86 p=5.43e-18

## Track B — mechanism coherence
- chain_soundness (Track B): **0.604**

## Composite reward
- **composite reward:** +0.7449  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9263 (weight: 0.56)
  - `track_b`: +0.6039 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.1
