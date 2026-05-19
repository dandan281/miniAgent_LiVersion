# Novokine Analysis Report — HFF 8-Day Protocol

**Date:** Analysis session  
**Cell type:** Primary human dermal fibroblasts (HFF)  
**Protocol:** 8-day transdifferentiation (Riya's paper)  
**Assays analyzed:** Primary screen (Desmin, 155 cond.), Secondary screen (Desmin, 48 cond.), Max respiration (Seahorse OCR, 137 cond.)

---

## 1. Screen Overview

| Metric | Value |
|--------|-------|
| Total unique constructs tested | 186 |
| Unique receptor fragments | 20 |
| Unique canonical genes | 16 |
| Constructs with all 3 assays | 23 |
| Control | No minibinder |

## 2. Receptor Fragment Inventory

| Fragment | Gene (HGNC) | Receptor Family |
|----------|-------------|-----------------|
| Alk1 | ACVRL1 | BMP/TGFb type I |
| BMPR2 | BMPR2 | BMP/TGFb type II |
| EGFR2 | ERBB2 | ERBB/RTK |
| EGFRcside | EGFR | ERBB/RTK |
| FGFR | FGFR1 | FGF RTK |
| FGFR2 | FGFR2 | FGF RTK |
| GF1R | IGF1R | Insulin/IGF RTK |
| Her2 | ERBB2 | ERBB/RTK |
| IGF1R | IGF1R | Insulin/IGF RTK |
| IGF2R | IGF2R | M6P/IGF2 |
| IGFR2 | IGF2R | M6P/IGF2 |
| Neo2 | NEO2 | Unknown |
| PDGFR | PDGFRA | PDGF RTK |
| TGFbR2 | TGFBR2 | BMP/TGFb type II |
| TrkA | NTRK1 | Neurotrophin RTK |
| gammac | IL2RG | Cytokine/JAK-STAT |
| gp130 | IL6ST | Cytokine/JAK-STAT |
| insulin | INSR | Insulin/IGF RTK |
| insulinR | INSR | Insulin/IGF RTK |
| lytac | LTBR | TNFR superfamily |

## 3. EXP Score Ranking (Constructs with all 3 assays)

Formula: EXP = 0.30 × Primary + 0.15 × Respiration + 0.40 × Secondary  
(Myotube assay not available)

| Rank | Construct | EXP | Tier |
|------|-----------|-----|------|
| 1 | Neo2_EGFRcside | 0.605 | ★★★ Strong |
| 2 | Alk1_EGFRcside | 0.489 | ★★★ Strong |
| 3 | Alk1_Alk1 | 0.457 | ★★★ Strong |
| 4 | TrkA_BMPR2 | 0.447 | ★★★ Strong |
| 5 | Alk1_lytac | 0.383 | ★★ Moderate |
| 6 | TGFbR2_IGF2R | 0.379 | ★★ Moderate |
| 7 | TGFbR2_BMPR2 | 0.347 | ★★ Moderate |
| 8 | IGF2R_FGFR | 0.345 | ★★ Moderate |
| 9 | Alk1_Her2 | 0.316 | ★★ Moderate |
| 10 | Her2_FGFR | 0.307 | ★★ Moderate |

## 4. Top Hits by Assay

**Primary (Desmin):** Alk1_EGFRcside (2.58×), TrkA_BMPR2 (2.22×), TGFbR2_insulin (2.18×)  
**Secondary (Desmin):** Neo2_EGFRcside (2.97×), Alk1_Alk1 (2.68×), gammac_PDGFR (2.27×)  
**Respiration (OCR):** FGFR_EGFRcside (2.33×), lytac_Neo2 (2.04×), FGFR_FGFR (2.04×)

## 5. Cross-Assay Stars (≥2 assays above 1.3×)

TrkA_BMPR2, Alk1_EGFRcside, Alk1_Alk1, TGFbR2_IGF2R, IGF2R_FGFR, Alk1_Her2, Alk1_lytac, TGFbR2_BMPR2, TGFbR2_Her2, Her2_FGFR

## 6. New Untested Pairs

From 16 canonical genes: 120 possible heterodimer pairs, 105 tested, **25 untested**.

### Top 10 Recommended New Pairs

| # | Gene Pair | Construct Name | Rationale |
|---|-----------|---------------|-----------|
| 1 | **EGFR+IL6ST** | EGFRcside_gp130 | #1 hit in PDF (EXP 0.549). Both fragments available. |
| 2 | **EGFR+FGFR2** | EGFRcside_FGFR2 | EGFR hub × novel FGFR2. Cross-RTK synergy. |
| 3 | **ERBB2+NTRK1** | Her2_TrkA | HER2 (H2F) × TrkA (strong with BMPR2). |
| 4 | **FGFR1+IL6ST** | FGFR_gp130 | Cross-family (RTK × cytokine). High potential. |
| 5 | **IL6ST+NTRK1** | gp130_TrkA | Cytokine × neurotrophin RTK. Novel axis. |
| 6 | **IGF1R+IL6ST** | IGF1R_gp130 | Anabolic RTK × cytokine co-receptor. |
| 7 | **IL6ST+PDGFRA** | gp130_PDGFR | Cytokine × RTK. PDGFR strong in respiration. |
| 8 | **BMPR2+IL6ST** | BMPR2_gp130 | BMP type II × cytokine. Risk: needs type I partner. |
| 9 | **FGFR1+FGFR2** | FGFR_FGFR2 | Dual FGF receptor. Novel homotypic pair. |
| 10 | **INSR+NTRK1** | insulinR_TrkA | Metabolic × neurotrophin. |

## 7. Comparison with PDF Top Hits

| PDF Hit | Our Result | Status |
|---------|-----------|--------|
| EGFR+IL6ST (#1, EXP 0.549) | Not tested | **Top priority to test** |
| EGFR+TGFBR2 (#2, EXP 0.528) | 1.37× primary, 0.68× resp | Underperformed in HFF |
| BMPR2+NTRK1 (#3, EXP 0.484) | 2.22× primary, EXP 0.447 | ✅ **Validated** |
| ERBB2+PDGFRA (#4, EXP 0.462) | 1.61× respiration only | Limited data |

## 8. Key Observations

1. **Alk1 (ACVRL1) performs well in HFFs** when paired with EGFR — contradicts PDF's finding that ALK1 underperforms in fibroblasts
2. **Neo2 is a mystery receptor** — performs exceptionally well with EGFRcside (EXP 0.605, #1 overall)
3. **TGFbR2 is versatile** — strong with many partners (insulin, IGF1R, IGF2R, Her2)
4. **BMPR2+NTRK1 (TrkA_BMPR2)** is validated as a strong hit across both studies
5. **EGFR+IL6ST** is the single highest-priority untested pair
