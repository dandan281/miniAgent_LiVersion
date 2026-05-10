# Novokine candidate dossier — TNFRSF1A + IL6R
_Generated from experience buffer record `9c1302ae-18e8-4d25-8941-308a70eb822f` at 2026-05-04T20:18:46.675504+00:00 (mode=score_only)._

- **receptor_A:** `TNFRSF1A`
- **receptor_B:** `IL6R`
- **linker:** `rigid helix 30aa`
- **candidate_id:** `ANTI_REJUV_decoy`
- **tier:** **INCOHERENT_LOG_ONLY**

## Mechanism narrative
_(no narrative provided)_

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `EGR1`, `IL32`, `CDKN2A`, `IL6`, `JUN`, `FOS`, `CD3D`, `CD3E`, `CD8A`, `HLA-DPA1`, `CD74`, `CCL2`, _(+1 more)_
- **predicted_down** (top 12): `MYH7`, `MYH2`, `TNNT3`, `ACTA1`, `DES`, `TNNI1`, `MYOG`, `ENO3`, `ACTC1`, `MYBPC2`, `ACTN2`, `TNNT2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** -0.3425  (verdict: **ANTI-REJUVENATING**)
- P2 (young) overlap: +0.000 | P1 (aged-down) overlap: +0.000
- pos_total (rejuv): +0.000 | neg_total (anti-rejuv): +0.342
- Fisher up vs P2: overlap=1/13 odds=0.00 p=1.00e+00
- Fisher down vs P1: overlap=0/12 odds=0.00 p=1.00e+00

## Track B — mechanism coherence
- chain_soundness (Track B): **0.650**

## Composite reward
- **composite reward:** -0.0768  →  tier: **INCOHERENT_LOG_ONLY**
- Component breakdown:
  - `track_a`: -0.3425 (weight: 0.56)
  - `track_b`: +0.6500 (weight: 0.33)
  - `track_a5`: -0.9287 (weight: 0.11)
