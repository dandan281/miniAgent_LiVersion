# Canonical DEG TSV schema

All per-study DEG tables must conform to this schema so `build_consensus_atlas.py` can ingest them uniformly.

## Bulk RNA-seq tables (`deg_table.tsv`)

For: GSE164471, GSE111016, GTEx v11

| column | type | required | notes |
|---|---|---|---|
| `gene_symbol` | str | yes | uppercase HGNC symbol; normalized internally |
| `log2fc` | float | yes | aged − young direction (positive = up in aged). For GTEx, this is `logFC_per_year × 50` (50-year equivalent) |
| `padj` | float | yes | BH-corrected p-value |
| `pvalue` | float | no | raw p-value, optional |
| `n_donors_used` | int | no | per-row sample size for power tracking |
| `notes` | str | no | free-form (e.g. "ischemic-time-corrected") |

`direction` is computed at ingest time from `log2fc` + `padj` (not stored explicitly):
- `up` if `padj < 0.05 AND log2fc > 0.5`
- `down` if `padj < 0.05 AND log2fc < -0.5`
- `ns` otherwise

## Single-cell pseudo-bulk tables (`deg_pseudobulk_per_cell_type.tsv`)

For: Kedlian/Lacraz 2024, Lai 2024

Same columns as bulk, plus:

| column | type | required | notes |
|---|---|---|---|
| `cell_type` | str | yes | normalized cell-type label (see below) |

### Cell-type label normalization

The consensus builder maps source labels to a canonical set:

| canonical | accepted aliases |
|---|---|
| `MuSC` | MuSC, satellite_cell, muscle_stem_cell, SC |
| `Myofiber_TypeI` | MF-I, type1_fiber, slow_twitch, MyHC_slow |
| `Myofiber_TypeII` | MF-II, type2_fiber, fast_twitch, MyHC_fast, MF-IIA, MF-IIX |
| `Myofiber` | myofiber (untyped) |
| `FAP` | FAP, fibro_adipogenic_progenitor, FB, fibroblast |
| `Endothelial` | endothelial, EC, art_EC, cap_EC, ven_EC |
| `Pericyte` | pericyte, mural |
| `Macrophage` | mac, macrophage, MΦ |

Studies that don't cleanly map (e.g. Lai's MF-IIX) are merged into the closest canonical label and flagged in `metadata.json.merged_celltypes`.

## Threshold convention

All studies use the same DEG cutoff for v2 inclusion to avoid weighting bias:
```
padj < 0.05 AND |log2fc| > 0.5
```
Per-study threshold differences (e.g. GTEx originally used `padj < 0.10`) are noted in each `metadata.json.original_threshold` but the consensus builder always re-thresholds at the canonical cutoff.

## Worked example (GTEx scaling)

GTEx v11 outputs `logFC_per_year`. For a gene with `logFC_per_year = 0.012`:
- 50-year equivalent: `0.012 × 50 = 0.60`
- Passes `|log2fc| > 0.5` threshold, votes `up` if `padj < 0.05`.

The user upload should already contain the 50-year-scaled column; if not, the builder will scale on the fly using `metadata.json.scaling_factor: 50`.
