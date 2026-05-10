# Aging Studies Knowledge Base

Multi-source DEG / age-regression tables used to build the **v2 consensus muscle aging atlas** (`backend/knowledge/muscle_atlas_DE_v2_consensus.json`). v1 (`muscle_atlas_DE.json`) was a single-source pooled atlas; v2 requires gene support from ≥2 independent studies for `P1_up`/`P2_up` membership, increasing robustness against batch effects and study-specific noise.

## Studies included

| Folder | Citation | n donors | Design | Tissue |
|---|---|---|---|---|
| `GSE164471_tumasian_2021/` | Tumasian et al. 2021, Nat Comm | 39 (17Y/22O) | DESeq2 ~ sex + condition | vastus lateralis bulk |
| `GSE111016_pillon_2019/` | Pillon et al. 2019, Nat Comm | 40 (20S/20C, all male 65–79) | DESeq2 ~ condition | vastus lateralis bulk (sarcopenia case-control) |
| `gtex_v11_skeletal_muscle/` | GTEx Consortium v11 | 818 | limma-trend ~ sex + ischemic_time + age | skeletal muscle bulk, continuous age |
| `kedlian_lacraz_2024_natage/` | Kedlian/Lacraz et al. 2024, Nat Aging | 17 (8Y/9O, 60–75) | pseudo-bulk limma-voom | intercostal sc/sn-RNA-seq |
| `lai_2024_hlma/` | Lai et al. 2024, Nature | 31 (12Y/19O, 74–99) | pseudo-bulk | hindlimb sc/sn-RNA-seq + snATAC + spatial |

Both single-cell atlases are **literature references** providing per-cell-type pseudo-bulk DEG tables. The Kedlian h5ad backs `local_atlas_query` directly (`backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad`); Lai HLMA is cited only — no raw data stored.

## File conventions

Each study folder contains:
- `deg_table.tsv` (bulk) **or** `deg_pseudobulk_per_cell_type.tsv` (single-cell) — see `_schema.md`
- `metadata.json` — citation, design, donor counts, processing notes, source URL

## How to extend

1. Drop a new study folder with `deg_table.tsv` + `metadata.json` matching `_schema.md`.
2. Add the folder name to `KNOWN_SOURCES` in `backend/scripts/build_consensus_atlas.py`.
3. Re-run `python backend/scripts/build_consensus_atlas.py` to regenerate `muscle_atlas_DE_v2_consensus.json`.
4. Run `pytest backend/tests/test_consensus_atlas.py` to verify schema + biology sanity.

## Build

```
python backend/scripts/build_consensus_atlas.py \
  --aging-studies-dir backend/knowledge/aging_studies \
  --output backend/knowledge/muscle_atlas_DE_v2_consensus.json
```

## Use in RL loop

```
python backend/scripts/rl_loop.py --atlas-version v2 ...
```

Default remains `v1` to preserve reproducibility of the 79-run experience buffer.
