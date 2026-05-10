# Novokine candidate dossier — MET + OSMR
_Generated from experience buffer record `2c0cff2d-0a8c-439a-85e1-86e9f5801045` at 2026-05-05T08:28:10.743307+00:00 (mode=full)._

- **receptor_A:** `MET`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `MET_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
MET+OSMR: HGF+OSM axis

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `DSTN`, `FMN1`, `MAFB`, `IGFBP7`, _(+1 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`, `ASB5`, `NEB`, _(+1 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=13/13 odds=inf p=3.19e-21
- Fisher down vs P1: overlap=12/13 odds=3677.91 p=5.59e-29

## Track B — mechanism coherence
- chain_soundness (Track B): **0.741**

## Composite reward
- **composite reward:** +0.7938  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7412 (weight: 0.33)
  - `track_a5`: -0.0798 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
