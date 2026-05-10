# Novokine candidate dossier — INSR + MET
_Generated from experience buffer record `ed283eae-cd13-4963-b428-54906bf7470e` at 2026-05-05T07:33:26.681906+00:00 (mode=full)._

- **receptor_A:** `INSR`
- **receptor_B:** `MET`
- **linker:** `flexible_GS4`
- **candidate_id:** `INSR_MET_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
Re-test INSR+MET (original BOTTOM 0.432)

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `DSTN`, `FABP4`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`, `NEB`, `ASB5`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.8918  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.108
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.782**

## Composite reward
- **composite reward:** +0.7781  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.8918 (weight: 0.56)
  - `track_b`: +0.7821 (weight: 0.33)
  - `track_a5`: +0.1974 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
