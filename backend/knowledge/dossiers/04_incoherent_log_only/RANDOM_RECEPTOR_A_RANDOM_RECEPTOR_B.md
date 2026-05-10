# Novokine candidate dossier — RANDOM_RECEPTOR_A + RANDOM_RECEPTOR_B
_Generated from experience buffer record `ace87202-3553-49d9-b0ab-21ca6c9cdede` at 2026-05-04T06:53:44.735091+00:00 (mode=score_only)._

- **receptor_A:** `RANDOM_RECEPTOR_A`
- **receptor_B:** `RANDOM_RECEPTOR_B`
- **linker:** `GS×4`
- **candidate_id:** `neutral_decoy`
- **tier:** **INCOHERENT_LOG_ONLY**

## Mechanism narrative
Random non-overlapping genes — should produce neutral/incoherent verdict.

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `FOO1`, `BAR2`, `BAZ3`
- **predicted_down** (top 12): `XYZ1`, `ABC2`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +0.0000  (verdict: **NEUTRAL**)
- P2 (young) overlap: +0.000 | P1 (aged-down) overlap: +0.000
- pos_total (rejuv): +0.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=0/3 odds=0.00 p=1.00e+00
- Fisher down vs P1: overlap=0/2 odds=0.00 p=1.00e+00

## Track B — mechanism coherence
- chain_soundness (Track B): **0.050**

## Composite reward
- **composite reward:** +0.0187  →  tier: **INCOHERENT_LOG_ONLY**
- Component breakdown:
  - `track_a`: +0.0000 (weight: 0.62)
  - `track_b`: +0.0500 (weight: 0.37)
