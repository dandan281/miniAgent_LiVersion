# Kedlian/Lacraz 2024 — Human Skeletal Muscle Aging Atlas

**Citation**: Kedlian et al. 2024, Nature Aging 4:727-744. DOI: 10.1038/s43587-024-00613-3
**Portal**: https://www.muscleageingcellatlas.org

## What's here

- `metadata.json` — citation, design, donor counts
- `deg_pseudobulk_per_cell_type.tsv` — per-(cell_type × age_group) DEG table from Nat Aging supplementary tables (PENDING — see fetch instructions below)

## What's NOT here (already lives elsewhere)

The raw atlas h5ad lives at `backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad` (1.9 GB). It backs the `local_atlas_query` tool live — every receptor expression query in Step 1b of the COT_Rejuv_Pipeline goes through it.

A 30k-cell balanced subsample is at `backend/storage/atlases/SKM_balanced_30k.h5ad` (122 MB).

## Why both forms?

- The h5ad is for **live single-cell queries** (receptor expression, fraction expressing, mean expression per cell type × age bin).
- This folder's TSV is for **frozen publication-snapshot DEGs** that feed into the v2 consensus atlas. It locks in the threshold + design used in the Nat Aging publication and stays stable across local atlas re-processing.

## Fetch the SI table

The DEG supplementary tables are hosted on Nature Aging's article page:
- https://www.nature.com/articles/s43587-024-00613-3 → Supplementary Information / Source Data tabs
- Specifically: `Supplementary Table 2` (or equivalent — pseudo-bulk DEG results per cell type)

If automated fetch via WebFetch fails, download manually from the publisher and place at `deg_pseudobulk_per_cell_type.tsv`.

## Cell-type label mapping

The Kedlian atlas uses these labels — the consensus builder normalizes them to canonical names (see `aging_studies/_schema.md`):

| Kedlian label | canonical |
|---|---|
| MuSC | MuSC |
| MF-I | Myofiber_TypeI |
| MF-II | Myofiber_TypeII |
| FB / PnFB / EnFB | FAP |
| art_EC / cap_EC / ven_EC | Endothelial |
| pericyte / smooth_muscle | Pericyte |
| macrophage | Macrophage |
