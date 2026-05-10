# Novokine candidate dossier — MET + LIFR
_Generated from experience buffer record `805cecfb-a910-46ad-a80e-e93bbc16d1f8` at 2026-05-05T07:43:15.611864+00:00 (mode=full)._

- **receptor_A:** `MET`
- **receptor_B:** `LIFR`
- **linker:** `flexible_GS4`
- **candidate_id:** `MET_LIFR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
MET+LIFR new combo: HGF + LIF axis

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `DSTN`, `FMN1`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `ASB5`, `NEB`, `CSRP3`, `HDAC9`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.750**

## Composite reward
- **composite reward:** +0.8041  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.7500 (weight: 0.33)
  - `track_a5`: -0.0133 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
