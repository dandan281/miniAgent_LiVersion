# Novokine candidate dossier — ERBB4 + INSR
_Generated from experience buffer record `4ae2f1fa-4dc5-4b90-bc02-ce94493cf893` at 2026-05-05T06:49:16.922248+00:00 (mode=full)._

- **receptor_A:** `ERBB4`
- **receptor_B:** `INSR`
- **linker:** `rigid_helix_20`
- **candidate_id:** `ERBB4_INSR_rigid_helix_20`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
ERBB4+INSR rigid 30Å

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** _(none)_
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `IGFBP7`, `TIMP3`, `CLIC4`, `ITGA8`, _(+3 more)_
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`, `PRUNE2`, `ASB5`, `NEB`, `DNAJA4`, _(+3 more)_

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=15/15 odds=inf p=2.18e-24
- Fisher down vs P1: overlap=15/15 odds=inf p=1.42e-37

## Track B — mechanism coherence
- chain_soundness (Track B): **0.848**

## Composite reward
- **composite reward:** +0.8633  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.56)
  - `track_b`: +0.8477 (weight: 0.33)
  - `track_a5`: +0.2265 (weight: 0.11)

### Atlas seed metadata
- composite_atlas_score: 0.217
