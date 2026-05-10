"""
Extract Pillon 2019 (GSE111016) bulk DEG table from Nat Comm Supplementary Data 4.

Source xlsx (already downloaded to /tmp/):
  https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-019-13694-1/MediaObjects/41467_2019_13694_MOESM4_ESM.xlsx

The 'Sarcopenia' sheet contains the limma-style per-gene DEG output for
sarcopenic vs healthy elderly control with these columns:
  ENSG_ID (column 0)  chr  gene_source  start  end  strand  gene_version
  gene_name  gene_biotype  symbol.org.Hs.eg  title.org.Hs.eg
  Amean  coef_sarc  modt_sarc  pval_sarc  adjp_sarc

Output: gene_symbol \\t log2fc \\t padj \\t pvalue \\t ensembl_id
matching aging_studies/_schema.md.
"""
import csv
import shutil
import sys
from pathlib import Path

SRC_XLSX = Path("/tmp/pillon_supp4.xlsx")
OUT_DIR = Path("backend/knowledge/aging_studies/GSE111016_pillon_2019")
OUT_TSV = OUT_DIR / "deg_table.tsv"
ARCHIVE_XLSX = OUT_DIR / "pillon_2019_SuppData4_full.xlsx"


def main() -> int:
    if not SRC_XLSX.exists():
        print(f"ERROR: source xlsx not at {SRC_XLSX}; download first")
        return 1
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl required")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Archive the original xlsx alongside the extracted TSV for provenance
    shutil.copy2(SRC_XLSX, ARCHIVE_XLSX)
    print(f"  archived xlsx -> {ARCHIVE_XLSX}")

    wb = openpyxl.load_workbook(SRC_XLSX, read_only=True, data_only=True)
    if "Sarcopenia" not in wb.sheetnames:
        print(f"ERROR: 'Sarcopenia' sheet not found; got {wb.sheetnames}")
        return 1
    ws = wb["Sarcopenia"]

    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    # Column index lookup
    idx = {c: i for i, c in enumerate(header) if c is not None}

    needed = ["coef_sarc", "adjp_sarc", "pval_sarc", "symbol.org.Hs.eg", "gene_name"]
    missing = [c for c in needed if c not in idx]
    if missing:
        print(f"ERROR: missing expected columns: {missing}; got {list(idx)}")
        return 1

    n_total = 0
    n_written = 0
    n_no_symbol = 0
    with OUT_TSV.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["gene_symbol", "log2fc", "padj", "pvalue", "ensembl_id"])
        for r in rows_iter:
            n_total += 1
            ensembl = r[0]
            sym = r[idx["symbol.org.Hs.eg"]]
            if sym in (None, "NA", "") or not isinstance(sym, str):
                # Fall back to gene_name
                sym = r[idx["gene_name"]]
            if sym in (None, "NA", "") or not isinstance(sym, str):
                n_no_symbol += 1
                continue
            try:
                lfc = float(r[idx["coef_sarc"]])
                padj = float(r[idx["adjp_sarc"]])
                pval = float(r[idx["pval_sarc"]])
            except (TypeError, ValueError):
                continue
            w.writerow([sym.strip().upper(), lfc, padj, pval, ensembl or ""])
            n_written += 1

    print(f"  total xlsx rows scanned: {n_total}")
    print(f"  rows with symbol + values: {n_written}")
    print(f"  rows skipped (no symbol):  {n_no_symbol}")
    print(f"  wrote {OUT_TSV} ({n_written} lines + header)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
