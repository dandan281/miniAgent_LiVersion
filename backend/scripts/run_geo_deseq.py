"""
GEO accession → DESeq2 differential expression → canonical aging-studies TSV.

Downloads a public GEO supplementary counts file, parses sample metadata,
runs PyDESeq2 with a user-specified design, and writes a TSV that conforms
to ``backend/knowledge/aging_studies/_schema.md`` (gene_symbol, log2fc, padj,
pvalue, ensembl_id).

This is the **execution counterpart** to the existing interpretation skill
``backend/skills/differential_expression_helper/SKILL.md``. The agent invokes
it to convert any sufficiently well-organized GEO study into a v2-consensus-atlas
ingestible DEG table without leaving the loop.

Usage (GSE164471 / Tumasian 2021):
    python backend/scripts/run_geo_deseq.py \\
      --accession GSE164471 \\
      --counts-url https://ftp.ncbi.nlm.nih.gov/geo/series/GSE164nnn/GSE164471/suppl/GSE164471_GESTALT_Muscle_ENSG_counts_annotated.csv.gz \\
      --sample-regex 'MUSCLE_AGE(?P<age>\\d+)_(?P<sex>[MF])_GROUP' \\
      --condition-rule 'age<=30:young;age>=60:old' \\
      --design '~ sex + condition' \\
      --gene-id-col Tracking_ID \\
      --gene-symbol-col 'HG19en82 Gene Name' \\
      --output backend/knowledge/aging_studies/GSE164471_tumasian_2021/deg_table.tsv

For other studies, point ``--counts-url`` at the right supplementary file,
adjust ``--sample-regex`` to capture per-sample metadata from column names,
and tune ``--condition-rule`` to bin samples into ``young``/``old``.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def _download(url: str, out_path: Path) -> Path:
    """Idempotent download — skip if file already present and non-empty."""
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [cache] {out_path.name} already present ({out_path.stat().st_size//1024} KB)")
        return out_path
    print(f"  [download] {url} -> {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
    return out_path


def _open(path: Path):
    """Open .gz or plain text."""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path, "r")


def _parse_sample_metadata(
    sample_columns: list[str],
    sample_regex: str,
    condition_rule: str,
) -> pd.DataFrame:
    """Parse named groups from each sample column, then apply the condition rule.

    sample_regex must contain at least named group ``age`` (int) and may include
    other covariates (``sex``, ``batch``, ``donor``, ...).

    condition_rule example: ``"age<=30:young;age>=60:old"`` → samples with
    age <= 30 get condition='young', samples with age >= 60 get 'old', others
    are dropped from the analysis.
    """
    pat = re.compile(sample_regex)
    rows = []
    for col in sample_columns:
        m = pat.search(col)
        if not m:
            continue
        meta: dict = {"sample": col, **m.groupdict()}
        if "age" in meta:
            meta["age"] = int(meta["age"])
        rows.append(meta)
    df = pd.DataFrame(rows).set_index("sample")

    rules = []
    for clause in condition_rule.split(";"):
        clause = clause.strip()
        if not clause:
            continue
        cond_expr, label = clause.split(":")
        rules.append((cond_expr.strip(), label.strip()))

    df["condition"] = pd.NA
    for cond_expr, label in rules:
        try:
            mask = df.eval(cond_expr)
        except Exception as e:
            raise ValueError(f"condition_rule clause {cond_expr!r} failed to evaluate: {e}")
        df.loc[mask & df["condition"].isna(), "condition"] = label

    keep = df["condition"].notna()
    print(f"  [metadata] parsed {len(df)} samples; "
          f"{keep.sum()} kept after condition rule, {len(df) - keep.sum()} dropped (middle/no match)")
    print(f"  [metadata] condition counts: {df.loc[keep,'condition'].value_counts().to_dict()}")
    return df.loc[keep].copy()


def _load_counts_matrix(
    counts_path: Path,
    sample_metadata: pd.DataFrame,
    gene_id_col: str,
    gene_symbol_col: Optional[str],
) -> tuple[pd.DataFrame, pd.Series]:
    """Load counts CSV → integer matrix [gene × sample] aligned to sample_metadata.

    Also returns gene_id -> gene_symbol mapping (Series indexed by gene_id).
    """
    print(f"  [counts] loading {counts_path}")
    with _open(counts_path) as f:
        reader = csv.reader(f)
        header = next(reader)

    keep_cols = [gene_id_col] + list(sample_metadata.index)
    if gene_symbol_col:
        keep_cols.append(gene_symbol_col)

    missing = [c for c in keep_cols if c not in header]
    if missing:
        raise ValueError(f"counts file missing expected columns: {missing[:5]} ... (header has {len(header)} cols)")

    df = pd.read_csv(counts_path, usecols=keep_cols)
    df = df.set_index(gene_id_col)
    sym = None
    if gene_symbol_col:
        sym = df[gene_symbol_col]
        df = df.drop(columns=[gene_symbol_col])

    # Keep only the sample columns, in metadata order
    df = df[list(sample_metadata.index)]

    # Coerce to int (counts), drop NaN rows
    df = df.fillna(0).astype(int)
    print(f"  [counts] matrix: {df.shape[0]:,} genes x {df.shape[1]} samples")
    return df, sym


def run_deseq(
    counts: pd.DataFrame,
    metadata: pd.DataFrame,
    design_factors: list[str],
    contrast: tuple[str, str, str],
) -> pd.DataFrame:
    """Run PyDESeq2 with the requested design + contrast.

    Returns a DataFrame indexed by gene_id with columns
    log2FoldChange, lfcSE, stat, pvalue, padj, baseMean, etc.
    """
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    # PyDESeq2 expects samples as rows
    counts_t = counts.T
    print(f"  [deseq] design: {design_factors}, contrast: {contrast}")
    dds = DeseqDataSet(
        counts=counts_t,
        metadata=metadata,
        design_factors=design_factors,
        refit_cooks=True,
        quiet=True,
    )
    dds.deseq2()

    stats = DeseqStats(dds, contrast=list(contrast), quiet=True)
    stats.summary()
    res = stats.results_df.copy()
    print(f"  [deseq] result rows: {len(res):,}")
    return res


def write_canonical_tsv(
    results: pd.DataFrame,
    sym_map: Optional[pd.Series],
    output_path: Path,
) -> int:
    """Project DESeq2 results into the canonical TSV schema."""
    df = results.copy()
    df["ensembl_id"] = df.index.astype(str)
    if sym_map is not None:
        df["gene_symbol"] = df["ensembl_id"].map(sym_map).fillna("").astype(str).str.upper().str.strip()
    else:
        df["gene_symbol"] = df["ensembl_id"].str.upper()
    df = df.rename(columns={"log2FoldChange": "log2fc"})
    df = df[df["gene_symbol"].astype(bool)]                             # drop empty symbols
    df = df.dropna(subset=["log2fc", "padj"])
    out = df[["gene_symbol", "log2fc", "padj", "pvalue", "ensembl_id"]]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, sep="\t", index=False)
    print(f"  [output] wrote {output_path} ({len(out):,} rows)")
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accession", required=True, help="GEO Series ID (for logging)")
    ap.add_argument("--counts-url", required=True, help="HTTP(S) URL of the supplementary counts file")
    ap.add_argument("--sample-regex", required=True,
                    help="Regex with named groups extracted from sample column names (must include 'age')")
    ap.add_argument("--condition-rule", required=True,
                    help="Semicolon-separated 'expr:label' clauses, e.g. 'age<=30:young;age>=60:old'")
    ap.add_argument("--design", default="~ condition",
                    help="DESeq2 design formula. Last term is treated as the test variable.")
    ap.add_argument("--contrast-test", default="old", help="Test level in 'condition' column")
    ap.add_argument("--contrast-ref",  default="young", help="Reference level (logFC direction: test - ref)")
    ap.add_argument("--gene-id-col", default="Tracking_ID", help="Counts file column with gene IDs (Ensembl)")
    ap.add_argument("--gene-symbol-col", default=None,
                    help="Optional column with HGNC gene symbols (else use ensembl_id as gene_symbol)")
    ap.add_argument("--cache-dir", type=Path, default=Path("/tmp/geo_cache"))
    ap.add_argument("--output", type=Path, required=True, help="Output TSV path")
    args = ap.parse_args()

    print(f"=== {args.accession} → DESeq2 ===")

    # 1. Download counts (cached)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    counts_path = args.cache_dir / Path(args.counts_url).name
    _download(args.counts_url, counts_path)

    # 2. Get sample column names by reading the header alone
    with _open(counts_path) as f:
        header = next(csv.reader(f))
    # Sample columns are everything between gene-id col and the annotation tail
    annotation_keywords = ("Chromosome", "Cytoband", "Biotype", "Description", "Strand", "GC Content")
    sample_cols = [
        c for c in header
        if c != args.gene_id_col
        and c != args.gene_symbol_col
        and not any(kw in c for kw in annotation_keywords)
        and not c.startswith("HG19")  # Tumasian-specific annotation prefix
    ]

    # 3. Parse per-sample metadata + apply condition rule
    metadata = _parse_sample_metadata(sample_cols, args.sample_regex, args.condition_rule)
    if len(metadata) < 6:
        print(f"ERROR: only {len(metadata)} samples retained after condition rule; aborting")
        return 2

    # 4. Load counts matrix aligned to metadata
    counts, sym_map = _load_counts_matrix(
        counts_path,
        metadata,
        gene_id_col=args.gene_id_col,
        gene_symbol_col=args.gene_symbol_col,
    )

    # 5. Build design factors list from formula
    # Strip leading '~' and split on '+'; condition must be last (the test variable)
    formula_terms = [t.strip() for t in args.design.lstrip("~").split("+") if t.strip()]
    if "condition" not in formula_terms:
        formula_terms.append("condition")
    print(f"  [design] factors: {formula_terms}")

    # 6. Run DESeq2
    results = run_deseq(
        counts,
        metadata,
        design_factors=formula_terms,
        contrast=("condition", args.contrast_test, args.contrast_ref),
    )

    # 7. Write canonical TSV
    n_written = write_canonical_tsv(results, sym_map, args.output)

    # 8. Quick sanity print
    sig = results.dropna(subset=["padj"]).query("padj < 0.05").copy()
    print(f"\n  Summary: {len(sig):,} genes with padj < 0.05  ({n_written:,} total rows in output)")
    if len(sig):
        sig["abs_lfc"] = sig["log2FoldChange"].abs()
        top = sig.sort_values("abs_lfc", ascending=False).head(10)
        if sym_map is not None:
            top["sym"] = top.index.map(sym_map)
        print("  Top 10 by |log2fc|:")
        for gid, row in top.iterrows():
            sym = sym_map.get(gid, "") if sym_map is not None else gid
            print(f"    {sym:12} {gid:18} log2fc={row['log2FoldChange']:+.2f}  padj={row['padj']:.2e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
