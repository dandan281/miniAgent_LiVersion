# Novokine candidate dossier — ERBB2 + MET
_Generated from experience buffer record `519166f8-e20e-482d-b3de-20a8a61e424f` at 2026-05-04T07:07:21.527677+00:00 (mode=score_only)._

- **receptor_A:** `ERBB2`
- **receptor_B:** `MET`
- **linker:** `GS_med`
- **candidate_id:** `ERBB2_MET__GS_med`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
Heuristic candidate from generate_candidates.py — class pair: (ErbB, MET); axis: myogenic; linker: GS_med (20 aa, flexible).

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** `GRB2`, `SHC1`, `GAB1`, `STAT3`
- **cis-only adaptors:** _(none)_
- **sterically excluded:** _(none)_

## Predicted gene signature
- **predicted_up** (top 12): `ACTA2`, `MYL9`, `MYH11`, `MYOM2`, `TAGLN`, `MYL6`, `TPM2`, `NOTCH3`, `NTRK2`
- **predicted_down** (top 12): `EGR1`, `FOS`, `JUN`, `OTUD1`, `TXNIP`, `IL32`, `MYF5`, `MYH9`

## Track A — atlas overlap (phenotype score)
- **phenotype_score:** +1.0000  (verdict: **REJUVENATING**)
- P2 (young) overlap: +1.000 | P1 (aged-down) overlap: +1.000
- pos_total (rejuv): +1.000 | neg_total (anti-rejuv): +0.000
- Fisher up vs P2: overlap=9/9 odds=inf p=6.68e-15
- Fisher down vs P1: overlap=8/8 odds=inf p=3.32e-20

## Track B — mechanism coherence
- chain_soundness (Track B): **0.900**

## Composite reward
- **composite reward:** +0.9625  →  tier: **TOP_K_DESIGN**
- Component breakdown:
  - `track_a`: +1.0000 (weight: 0.62)
  - `track_b`: +0.9000 (weight: 0.37)

## Literature references
- Co-receptor in HER family; H2F template (ERBB2+FGFR1) drives myogenic reprogramming. PMID:39592735
- HGF/MET activates quiescent satellite cells; required for adult muscle regeneration. PMID:9883724
