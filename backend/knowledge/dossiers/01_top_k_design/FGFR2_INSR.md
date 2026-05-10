# Novokine candidate dossier — FGFR2 + INSR
_Generated from experience buffer record `e961fa99-14d5-4813-8bb8-61577e2e3f68` at 2026-05-04T07:07:21.543033+00:00 (mode=score_only)._

- **receptor_A:** `FGFR2`
- **receptor_B:** `INSR`
- **linker:** `GS_med`
- **candidate_id:** `FGFR2_INSR__GS_med`
- **tier:** **TOP_K_DESIGN**

## Mechanism narrative
Heuristic candidate from generate_candidates.py — class pair: (FGFR, INSR); axis: myogenic; linker: GS_med (20 aa, flexible).

## Adaptor classification (biased output)
- **transphosphorylation adaptors:** `FRS2`, `GRB2`, `IRS1`, `SHC1`
- **cis-only adaptors:** _(none)_
- **sterically excluded:** `PLCG_docking`

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
- Closely related to FGFR1; expressed on myoblasts and fibro-adipogenic progenitors. doi:10.1242/dev.151035
- Insulin signaling drives glucose uptake and oxidative metabolism in muscle. doi:10.1038/372186a0
