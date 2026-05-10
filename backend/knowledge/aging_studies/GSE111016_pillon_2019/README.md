# GSE111016 — Pillon 2019 Singapore Sarcopenia Study

**Citation**: Pillon NJ et al. (2019). Mitochondrial oxidative capacity and NAD(+) biosynthesis are reduced in human sarcopenia across ethnicities. Nat Comm 10:5808.
**DOI**: 10.1038/s41467-019-13694-1 | PMID: 31862890 | PMC: PMC6925228

## Status: DEG TABLE EXTRACTED FROM PAPER SI

Unlike the other two bulk studies in this folder (Tumasian, GTEx — both pending user upload), **Pillon's full bulk DEG table is already public** in their Nature Communications **Supplementary Data 4**. It was downloaded and extracted to `deg_table.tsv` by `backend/scripts/extract_pillon_deg.py` on 2026-05-05.

- `deg_table.tsv` — extracted normalized output (16,861 genes; columns: `gene_symbol`, `log2fc`, `padj`, `pvalue`, `ensembl_id`)
- `pillon_2019_SuppData4_full.xlsx` — original archival xlsx (4 sheets: Sarcopenia, ALMi, Grip Strength, Walking speed)

We use the **`Sarcopenia` sheet** (sarcopenic vs healthy elderly control). Column mapping:
- `gene_symbol` ← `symbol.org.Hs.eg` (HGNC, fallback to `gene_name`)
- `log2fc` ← `coef_sarc` (limma-voom coefficient; positive = up in sarcopenia)
- `padj` ← `adjp_sarc` (BH-corrected)
- `pvalue` ← `pval_sarc`

## Threshold note (consensus_thresholds in metadata.json)

Pillon's n=40 cohort is underpowered for genome-wide `padj < 0.05` — the **minimum padj in the entire table is 0.0796**. The paper's published cutoff is `FDR < 0.10`, which we adopt as Pillon's per-source threshold:

```json
"consensus_thresholds": {
    "padj": 0.10,
    "abs_log2fc": 0.3,
    "rationale": "Pillon n=40 has min padj=0.0796; using paper's published FDR<0.10 cutoff"
}
```

`build_consensus_atlas.py` reads this and applies per-source thresholds; the global default (`padj < 0.05, |lfc| > 0.5`) still applies to other sources unless they override.

## Direction convention

`coef_sarc > 0` ⇒ up in sarcopenic vs healthy elderly. Sarcopenia is treated as **accelerated/advanced muscle aging** (per Pillon's framing), so:
- `coef_sarc > 0` votes `up_in_aged` → `P1_up`
- `coef_sarc < 0` votes `down_in_aged` (= `up_in_young`) → `P2_up`

## What this contributes to v2

Currently (Kedlian + Lai + Pillon, no Tumasian/GTEx yet):
- 8 P1_up consensus genes (Pillon votes for 2: BSN, PCDHGB2)
- 28 P2_up consensus genes (Pillon votes for 5: CKMT2, CYCS, NDUFC1, SLC25A4, TCF15 — exactly the canonical mitochondrial biogenesis genes Pillon's paper highlighted)

Full panel awaits Tumasian + GTEx uploads.
