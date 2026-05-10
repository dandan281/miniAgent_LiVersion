# Novokine candidate dossier — ERBB2 + IL6ST
_Generated from experience buffer record `e3893a9a-8d02-4a9a-abc5-89a50fe4f85c` at 2026-05-05T08:22:00.133763+00:00 (mode=full)._

- **receptor_A:** `ERBB2`
- **receptor_B:** `IL6ST`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB2_IL6ST_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB2+IL6ST: HER2+gp130, untested

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `FMN1`, `MAFB`, `IGFBP7`, `TIMP3`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`, `PRUNE2`, `ASB5`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/12 odds=inf p=1.22e-19
- Fisher down vs P1: overlap=10/11 odds=2973.43 p=4.27e-24

## Track B — mechanism coherence
- chain_soundness (Track B): **0.771**

## Composite reward
- **composite reward:** +0.8184  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7709 (weight: 0.33)
  - `track_a5`: +0.0533 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
