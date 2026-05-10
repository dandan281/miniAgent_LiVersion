# Novokine candidate dossier — INSR + IL6ST
_Generated from experience buffer record `1c828b86-2cc5-468b-afb0-6a14987e9468` at 2026-05-05T09:01:23.702518+00:00 (mode=full)._

- **receptor_A:** `INSR`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS8`
- **candidate_id:** `INSR_IL6ST_flexible_GS8`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
Complete linker matrix for INSR+IL6ST

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `RGCC`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `ASB5`, `PRUNE2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/12 odds=inf p=1.22e-19
- Fisher down vs P1: overlap=10/11 odds=2973.43 p=4.27e-24

## Track B — mechanism coherence
- chain_soundness (Track B): **0.834**

## Composite reward
- **composite reward:** +0.8610  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.8337 (weight: 0.33)
  - `track_a5`: +0.2480 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.15
