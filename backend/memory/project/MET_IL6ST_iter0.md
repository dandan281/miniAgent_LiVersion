---
type: project_fact
name: MET_IL6ST_iteration_0
description: Completed iteration 0 of MET+IL6ST (flexible_GS4) novokine candidate for muscle rejuvenation RL loop.
---

## MET_IL6ST_flexible_GS4 — Iteration 0 Summary

**Candidate**: MET (RTK) + IL6ST/gp130 (cytokine receptor), flexible_GS4 linker (~20 Å)
**Output file**: `/gpfs/scrubbed/danlovuw/miniAgent/backend/knowledge/agent_outputs/MET_IL6ST_flexible_GS4.json`

### Key mechanism decisions
- **Transphosphorylation adaptors**: GRB2, SHC1, GAB1, PIK3R1, PTPN11, STAT3
  - MET's multifunctional docking site (Y1349/Y1356, PMID:7513258) recruits GRB2-SHC1-GAB1-PIK3R1
  - IL6ST Y759 recruits PTPN11/SHP-2 which links to MAPK (PMID:10409724)
  - MET kinase transphosphorylates IL6ST tyrosines, creating GRB2/SHC1 docking sites
- **Cis adaptors**: JAK1, JAK2, TYK2 (constitutively associated with IL6ST box1/box2 motifs)
- **Excluded adaptors**: PLCG1, PLCG2 (steric exclusion due to asymmetric ECD geometry: MET=908aa vs IL6ST=597aa)
- **Biased pathways**: MAPK/ERK, PI3K/AKT, JAK/STAT3, RAS/RAF/MEK, RAC1/RAP1

### Gene direction rationale
- **predicted_up** (young-enriched/P2_up): Muscle structural genes (ACTA2, MYL9, MYH11, MYOM2, TAGLN, MYL6, TPM2) + NOTCH3, IGFBP7, TIMP3 — driven by MAPK/ERK and PI3K/AKT activation
- **predicted_down** (aged-enriched/P1_up): IEGs (EGR1, FOS, JUN), aged markers (IL32, TXNIP, MYF5, MYH9, ASB5, OTUD1, CDKN2A) — suppressed by biased signaling away from stress/inflammatory pathways

### Calibration against past wins
- Pattern matches the ERBB2+FGFR wins: muscle structural genes UP, aged IEGs DOWN
- ECD asymmetry (311aa) is a risk factor but flexible linker compensates
- No PLCγ_docking (excluded) — consistent with winning strategy
