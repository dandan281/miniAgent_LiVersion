# Novokine candidate dossier — FGFR4 + IGF1R
_Generated from experience buffer record `8619f45f-f417-4988-bffe-8d8118a93c68` at 2026-05-04T07:07:21.546394+00:00 (mode=score_only)._

- **receptor_A:** `FGFR4`
- **receptor_B:** `IGF1R`
- **linker:** `GS_med`
- **candidate_id:** `FGFR4_IGF1R__GS_med`
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
- Predominant FGFR on differentiating myoblasts; required for myogenic terminal differentiation. PMID:7926719
- Master regulator of muscle hypertrophy via AKT/mTOR; drives myofibre growth. doi:10.1038/ncb1101-1014
