# Novokine candidate dossier — FGFR1 + OSMR
_Generated from experience buffer record `8595cf98-0a7a-4422-8025-6a7de967b80c` at 2026-05-05T06:19:40.238256+00:00 (mode=full)._

- **receptor_A:** `FGFR1`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR1_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
atlas-seeded; ranked by co-expression in aged target cells.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `FMN1`, `MAFB`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `CDKN2A`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=10/10 odds=inf p=1.76e-16
- Fisher down vs P1: overlap=8/9 odds=2309.80 p=2.98e-19

## Track B — mechanism coherence
- chain_soundness (Track B): **0.772**

## Composite reward
- **composite reward:** +0.8417  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7716 (weight: 0.33)
  - `track_a5`: +0.2605 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.0877
- co-expression in **old**: FB
- ECD asymmetry ratio: 2.03× (H2F = 1.78×)
- families: RTK_FGFR × Cytokine
