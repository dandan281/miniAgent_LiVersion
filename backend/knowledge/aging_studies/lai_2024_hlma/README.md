# Lai 2024 — Human Locomotor Muscle Ageing Atlas (HLMA)

**Citation**: Lai et al. 2024, Nature 629:154-164. DOI: 10.1038/s41586-024-07348-6
**Portal**: https://db.cngb.org/cdcp/hlma/

## Status: literature reference only

We do **NOT** store the raw multimodal atlas (scRNA + snRNA + snATAC-seq + spatial). It would be 10–20+ GB of mixed-modality data and is not needed for the v2 consensus atlas. The Lai HLMA contributes via:

1. `deg_pseudobulk_per_cell_type.tsv` — per-cell-type pseudo-bulk DEG table from the Nature SI (PENDING — see fetch instructions below)
2. Cited findings (recorded in `metadata.json.key_findings`) used to cross-validate computational predictions

## Why HLMA matters even as a secondary source

The aged group (74–99y) is **older** than Kedlian's (60–75y) and includes individuals with sarcopenia. This makes Lai uniquely valuable for catching:
- **Late-aging signatures** absent from Kedlian (e.g. the >=84y profibrotic TGF-β peak)
- **Type IIX myonuclei loss** (Kedlian doesn't separately resolve IIX)
- **Chromatin-level regulatory changes** (snATAC-seq) — used as cross-validation for kinase/TF inferences only, not directly fed into v2

## Voting role in v2 consensus

Treated as a **tiebreaker / secondary** source:
- For pooled `P1_up`/`P2_up`: counts toward consensus only when ≥2 other sources already agree (avoids inflating signal from Lai's older/sicker cohort)
- For per-cell-type sub-blocks: counts when contributing to a cell type **not covered by Kedlian** (e.g. spatial niche markers)

## Fetch the SI table

- https://www.nature.com/articles/s41586-024-07348-6 → Supplementary Information / Source Data
- Look for the pseudo-bulk DEG supplementary table (per-cell-type per-age-group)

If automated fetch fails, download manually and place at `deg_pseudobulk_per_cell_type.tsv`.
