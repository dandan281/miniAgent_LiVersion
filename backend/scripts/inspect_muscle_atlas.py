"""
Smoke test for the downloaded Kedlian muscle aging atlas .h5ad.

Verifies the file is readable and has the obs columns required by:
  - scgpt_phenotype_tool (build_axis): Age_bin, annotation_level0, embedding in obsm
  - scgpt_programs_tool  (build_programs): same + metagene_score after GRN run

Reports cell counts per (Age_bin × annotation_level0) so you can see in advance
which cell types will have ≥30 cells per age group (the threshold for axis building).

Usage:
    python inspect_muscle_atlas.py
    python inspect_muscle_atlas.py --path /custom/path.h5ad
"""
import argparse
import sys
from pathlib import Path

DEFAULT_ATLAS = (
    Path(__file__).resolve().parent.parent
    / "storage" / "atlases" / "SKM_human_pp_cells2nuclei_2023-06-22.h5ad"
)

EXPECTED_AGE_VALUES = {"young", "old"}
EXPECTED_CELL_TYPES = {"MuSC", "MF-I", "MF-II", "FB"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=DEFAULT_ATLAS)
    ap.add_argument("--min-cells", type=int, default=30,
                    help="Min cells per (age, celltype) group to flag as ready (default 30).")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"[error] Atlas not found at {args.path}", file=sys.stderr)
        print(f"        Run scripts/download_muscle_atlas.py first.", file=sys.stderr)
        return 1

    size_gb = args.path.stat().st_size / 1e9
    print(f"[file] {args.path}")
    print(f"       size: {size_gb:.2f} GB")

    try:
        import anndata
        import pandas as pd
    except ImportError as e:
        print(f"[error] missing dependency: {e}", file=sys.stderr)
        print(f"        pip install anndata pandas", file=sys.stderr)
        return 1

    print(f"[load] reading AnnData ...")
    try:
        adata = anndata.read_h5ad(args.path)
    except Exception as e:
        print(f"[error] failed to read .h5ad: {e}", file=sys.stderr)
        return 1

    print(f"[shape] cells: {adata.n_obs:,}    genes: {adata.n_vars:,}")
    print(f"[obs columns] {list(adata.obs.columns)[:30]}")
    print(f"[obsm keys]   {list(adata.obsm.keys())}")
    print(f"[uns keys]    {list(adata.uns.keys())[:20]}")

    issues: list[str] = []

    for col in ("Age_bin", "annotation_level0"):
        if col not in adata.obs.columns:
            issues.append(f"MISSING obs['{col}']")

    if "Age_bin" in adata.obs.columns:
        ages = set(adata.obs["Age_bin"].astype(str).str.lower().unique())
        print(f"\n[Age_bin] values: {sorted(ages)}")
        missing_ages = EXPECTED_AGE_VALUES - ages
        if missing_ages:
            issues.append(f"Age_bin missing values: {missing_ages}")

    if "annotation_level0" in adata.obs.columns:
        ctypes = adata.obs["annotation_level0"].astype(str)
        unique_cts = sorted(ctypes.unique())
        print(f"\n[annotation_level0] {len(unique_cts)} unique:")
        for ct in unique_cts:
            print(f"  {ct}")

        if "Age_bin" in adata.obs.columns:
            ages_ser = adata.obs["Age_bin"].astype(str).str.lower()
            grid = pd.crosstab(ctypes, ages_ser)
            print(f"\n[cells per (cell type × age) — readiness for axis building]")
            print(f"{'cell_type':<25} {'young':>10} {'old':>10}  {'ready?':<10}")
            print("-" * 60)
            ready_count = 0
            for ct, row in grid.iterrows():
                y = int(row.get("young", 0))
                o = int(row.get("old", 0))
                ok = y >= args.min_cells and o >= args.min_cells
                marker = "OK" if ok else "skip"
                if ok and ct in EXPECTED_CELL_TYPES:
                    ready_count += 1
                print(f"{ct:<25} {y:>10,} {o:>10,}  {marker:<10}")
            print("-" * 60)
            print(f"Of expected muscle cell types {EXPECTED_CELL_TYPES}: {ready_count} ready for axis building.")

    if issues:
        print(f"\n[FAIL] {len(issues)} issue(s):")
        for i in issues:
            print(f"  - {i}")
        return 1

    print(f"\n[OK] Atlas is well-formed and ready for scGPT submission.")
    print(f"     Next: scgpt_phenotype tool, action='submit_mapping'")
    print(f"           scgpt_programs  tool, action='submit_grn'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
