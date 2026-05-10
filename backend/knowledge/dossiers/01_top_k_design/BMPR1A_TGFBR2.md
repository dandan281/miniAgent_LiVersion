# Novokine candidate dossier — TGFBR2 + BMPR1A
_Generated from experience buffer record `d7b8f4c7-7344-4963-b2ed-0c4ae9d81dcf` at 2026-05-05T08:11:28.127616+00:00 (mode=full)._

- **receptor_A:** `TGFBR2`
- **receptor_B:** `BMPR1A`
- **linker:** `flexible_GS4`
- **candidate_id:** `TGFBR2_BMPR1A_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
TGF-β II + BMP I

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `SERPINE1`, `CTGF`, `SMAD7`, `ID1`, `ID2`, `ID3`, `TAGLN`, `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TIMP3`, _(+1 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `IL32`, `TXNIP`, `OTUD1`, `MYF5`, `MYH9`, `CDKN2A`, `IL6`, `TNFSF10`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.8923  (verdict: **REJUVENATING**)
- P2 (young) overlap: +0.785 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +0.892 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=7/13 odds=42.91 p=1.43e-08
- Fisher down vs P1: overlap=8/11 odds=769.86 p=5.43e-18

## Track B — mechanism coherence
- chain_soundness (Track B): **0.602**

## Composite reward
- **composite reward:** +0.7002  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.8923 (weight: 0.56)
  - `track_b`: +0.6022 (weight: 0.33)
  - `track_a5`: +0.0333 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
