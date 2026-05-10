# Novokine candidate dossier — ERBB3 + FGFR1
_Generated from experience buffer record `86491d75-b671-4154-be50-daa312f8dcb4` at 2026-05-05T08:40:31.194809+00:00 (mode=full)._

- **receptor_A:** `ERBB3`
- **receptor_B:** `FGFR1`
- **linker:** `flexible_GS4`
- **candidate_id:** `ERBB3_FGFR1_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB3+FGFR1: kinase-dead RTK + active RTK

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `TIMP3`, `IGFBP7`, `CLIC4`, `ITGA8`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `PRUNE2`, `DNAJA4`, `ETS2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/12 odds=inf p=1.22e-19
- Fisher down vs P1: overlap=12/12 odds=inf p=4.31e-30

## Track B — mechanism coherence
- chain_soundness (Track B): **0.467**

## Composite reward
- **composite reward:** +0.7245  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.4671 (weight: 0.33)
  - `track_a5`: +0.1194 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
