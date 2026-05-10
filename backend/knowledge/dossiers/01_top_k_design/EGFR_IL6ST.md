# Novokine candidate dossier — EGFR + IL6ST
_Generated from experience buffer record `10e78111-acff-47ba-b93b-980277264c4b` at 2026-05-05T06:47:00.865807+00:00 (mode=full)._

- **receptor_A:** `EGFR`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS8`
- **candidate_id:** `EGFR_IL6ST_flexible_GS8`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
EGFR+IL6ST flexible 40Å

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `TIMP3`, `CLIC4`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `DNAJA4`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=10/10 odds=inf p=3.90e-25

## Track B — mechanism coherence
- chain_soundness (Track B): **0.838**

## Composite reward
- **composite reward:** +0.8638  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.8379 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.367
