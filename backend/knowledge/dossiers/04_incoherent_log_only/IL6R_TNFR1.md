# Novokine candidate dossier — TNFR1 + IL6R
_Generated from experience buffer record `9042627a-decc-40bd-ab42-8b60238c1050` at 2026-05-04T06:53:44.732501+00:00 (mode=score_only)._

- **receptor_A:** `TNFR1`
- **receptor_B:** `IL6R`
- **linker:** `rigid 40aa`
- **candidate_id:** `anti_rejuv_decoy`
- **tier:** **INCOHERENT_LOG_ONLY**

## Mechanism narrative
Synthetic decoy — predicts aged genes UP, young genes DOWN.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `EGR1`, `IL32`, `TXNIP`, `JUN`, `OTUD1`, `TTN`, `PRUNE2`, `MYF5`
- **predicted_down** (top 12): `ACTA2`, `MYL9`, `MYH7`, `MYH2`, `TNNT3`, `MYOG`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** -0.6000  (verdict: **ANTI-REJUVENATING**)
- P2 (young) overlap: +0.000 | P1 (aged-down) overlap: +0.000
- pos_total (rejuv): +0.000 | neg_total (anti-rejuv): +0.600
- Fisher up vs P2: overlap=1/8 odds=0.00 p=1.00e+00
- Fisher down vs P1: overlap=0/6 odds=0.00 p=1.00e+00

## Track B — mechanism coherence
- chain_soundness (Track B): **0.300**

## Composite reward
- **composite reward:** -0.2625  →  tier: **INCOHERENT_LOG_ONLY**
- Component breakdown:
  - `track_a`: -0.6000 (weight: 0.62)
  - `track_b`: +0.3000 (weight: 0.37)
