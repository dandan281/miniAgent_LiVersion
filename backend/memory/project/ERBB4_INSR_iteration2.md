---
type: project_fact
name: ERBB4_INSR_iteration2
description: Iteration 2 of the muscle-rejuvenation novokine RL loop — ERBB4+INSR with flexible_GS4 linker
---

# ERBB4+INSR Iteration 2 — Summary

**Candidate**: ERBB4 (HER4) + INSR (Insulin Receptor), linker = flexible_GS4 (~20 Å)

**Key findings from Step 1 (expression)**:
- ERBB4: expressed in MF-I (young pc=0.44, me=0.96; old pc=0.42, me=0.94) and MF-II (young pc=0.50, me=1.22; old pc=0.43, me=1.06). NOT expressed in MuSC (pc<0.04) or FB (pc<0.02).
- INSR: expressed in MF-I (young pc=0.48, me=0.88; old pc=0.50, me=1.04), MF-II (young pc=0.36, me=0.70; old pc=0.30, me=0.62), FB (young pc=0.37, me=0.47; old pc=0.22, me=0.31), and MuSC (young pc=0.20, me=0.27; old pc=0.14, me=0.20).
- **Co-expression sweet spot**: MF-I and MF-II myofibers (both receptors pass threshold in young AND old).
- **Aged dropout concern**: INSR shows reduced expression in old MuSC (pc 0.20→0.14) and old FB (pc 0.37→0.22), but both receptors remain well-expressed in aged myofibers.

**Key findings from Step 3a (adaptor classification)**:
- **Transphosphorylation adaptors**: GRB2, SHC1, PIK3R1, PTPN11, NCK1, CRK — these bind ERBB4 pY motifs and can be transphosphorylated by INSR kinase, or vice versa.
- **Cis adaptors**: IRS1, IRS2 (INSR-specific NPXY motif), FRS2, SH2B1, GRB10, CBL, SOCS3 — these are INSR-specific and function regardless of co-clustering.
- **Excluded adaptors**: PLCG1 (steric exclusion due to asymmetric ECD geometry, ~302 aa difference), YAP1 (WW-domain interaction with ERBB4 C-terminal tail likely blocked by INSR co-clustering).

**Predicted biased pathways**: MAPK/ERK (via GRB2-SHC1-SOS-RAS), PI3K/AKT/mTOR (via PIK3R1 + IRS1/2), STAT5.

**Predicted gene signature**: Up → muscle structural genes (MYH, ACTA, TPM, TNNT, DES, MYOG); Down → aged IEGs (EGR1, FOS, JUN, CDKN2A) and inflammatory mediators (IL32, IL6).

**Confidence assessment**: Moderate-high (0.65-0.85) for most steps except Step 3d (CRISPR support, 0.40) due to lack of muscle-specific CRISPR screens for these receptors.

**Output file**: `/gpfs/scrubbed/danlovuw/miniAgent/backend/knowledge/agent_outputs/ERBB4_INSR_flexible_GS4.json`
