# Novokine candidate dossier — INSR + OSMR
_Generated from experience buffer record `921b2c7c-95ae-48fe-b620-200e6cc92bb9` at 2026-05-05T07:47:13.973730+00:00 (mode=full)._

- **receptor_A:** `INSR`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `INSR_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
INSR+OSMR new combo

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `ITGA8`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `NEB`, `DNAJA4`, `ETS2`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.830**

## Composite reward
- **composite reward:** +0.8408  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.8302 (weight: 0.33)
  - `track_a5`: +0.0770 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
