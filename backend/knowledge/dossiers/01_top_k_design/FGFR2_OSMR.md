# Novokine candidate dossier — FGFR2 + OSMR
_Generated from experience buffer record `8362e8a4-71e1-4197-895c-1444e83e6186` at 2026-05-05T08:35:23.731747+00:00 (mode=full)._

- **receptor_A:** `FGFR2`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR2_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
FGFR2+OSMR

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `PPP1R14A`, _(+2 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `PRUNE2`, `DNAJA4`, `HDAC9`, _(+2 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=14/14 odds=inf p=8.35e-23
- Fisher down vs P1: overlap=14/14 odds=inf p=4.49e-35

## Track B — mechanism coherence
- chain_soundness (Track B): **0.690**

## Composite reward
- **composite reward:** +0.7963  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.6901 (weight: 0.33)
  - `track_a5`: +0.0968 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
