# Novokine candidate dossier — ACVR2B + BMPR1A
_Generated from experience buffer record `25a5959f-966d-49b0-9bdc-044f1235936f` at 2026-05-05T08:08:05.667624+00:00 (mode=full)._

- **receptor_A:** `ACVR2B`
- **receptor_B:** `BMPR1A`
- **linker:** `flexible_GS4`
- **candidate_id:** `ACVR2B_BMPR1A_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
TGF-β type II + type I (BMP/myostatin axis)

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ID1`, `ID2`, `ID3`, `TAGLN`, `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`, `NEB`, `CSRP3`, _(+2 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/15 odds=148.56 p=5.14e-17
- Fisher down vs P1: overlap=14/14 odds=inf p=4.49e-35

## Track B — mechanism coherence
- chain_soundness (Track B): **0.498**

## Composite reward
- **composite reward:** +0.7039  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.4978 (weight: 0.33)
  - `track_a5`: -0.1586 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
