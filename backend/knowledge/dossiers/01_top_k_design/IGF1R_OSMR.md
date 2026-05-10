# Novokine candidate dossier — IGF1R + OSMR
_Generated from experience buffer record `250b5767-f022-4994-9e19-901bda339a1c` at 2026-05-05T08:30:44.901702+00:00 (mode=full)._

- **receptor_A:** `IGF1R`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `IGF1R_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
IGF1R+OSMR: pro-myogenic axis

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `FMN1`, `MAFB`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`, `NEB`, `CSRP3`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.9388  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.061
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.772**

## Composite reward
- **composite reward:** +0.7684  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +0.9388 (weight: 0.56)
  - `track_b`: +0.7716 (weight: 0.33)
  - `track_a5`: -0.0931 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
