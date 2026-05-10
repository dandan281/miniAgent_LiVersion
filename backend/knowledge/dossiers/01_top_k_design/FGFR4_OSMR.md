# Novokine candidate dossier — FGFR4 + OSMR
_Generated from experience buffer record `9c1fe6a7-bf5e-4cc3-8b99-571db309b7b0` at 2026-05-05T08:38:07.972788+00:00 (mode=full)._

- **receptor_A:** `FGFR4`
- **receptor_B:** `OSMR`
- **linker:** `flexible_GS4`
- **candidate_id:** `FGFR4_OSMR_flexible_GS4`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
FGFR4+OSMR

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `DSTN`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `TTN`, `PRUNE2`, `NEB`, `CSRP3`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=12/12 odds=inf p=1.22e-19
- Fisher down vs P1: overlap=12/12 odds=inf p=4.31e-30

## Track B — mechanism coherence
- chain_soundness (Track B): **0.807**

## Composite reward
- **composite reward:** +0.8071  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.8075 (weight: 0.33)
  - `track_a5`: -0.1586 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.05
