"""
Build the v2 consensus muscle aging atlas from multiple independent studies.

Inputs (under `backend/knowledge/aging_studies/`):
  - GSE164471_tumasian_2021/deg_table.tsv   (bulk, USER UPLOAD)
  - GSE111016_pillon_2019/deg_table.tsv     (bulk, USER UPLOAD)
  - gtex_v11_skeletal_muscle/deg_table.tsv  (bulk, USER UPLOAD; logFC pre-scaled x50)
  - kedlian_lacraz_2024_natage/kedlian_2024_SuppTable3_aging_DEGs.xlsx  (sc, fetched)
  - lai_2024_hlma/lai_2024_SuppTable5_age_correlation.xlsx              (sc, fetched)

Output:
  - backend/knowledge/muscle_atlas_DE_v2_consensus.json

Consensus rules:
  - Pooled P1_up (aged-enriched): gene appears `up-in-aged` in >=2 INDEPENDENT sources.
  - Pooled P2_up (young-enriched): symmetric — gene appears `down-in-aged` in >=2 sources.
  - Lai 2024 counts as a TIEBREAKER only (older/sicker cohort, somewhat correlated with v1
    derivation source) — its vote is added but the >=2-source threshold still applies.
  - per_cell_type sub-blocks: derived from Kedlian + Lai single-cell sources;
    flagged with `n_sources_at_celltype` for downstream weighting.
  - Sources gracefully skip if their TSV/xlsx is missing — partial atlas built
    with provenance metadata recording which sources contributed.

Usage:
    python backend/scripts/build_consensus_atlas.py \\
      --aging-studies-dir backend/knowledge/aging_studies \\
      --output backend/knowledge/muscle_atlas_DE_v2_consensus.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

# Uniform DEG cutoff applied to all sources (avoids weighting bias from per-study thresholds)
PADJ_CUTOFF = 0.05
LOG2FC_CUTOFF = 0.5
LTSR_CUTOFF = 0.95          # Kedlian's local-true-sign-rate, ~equivalent to padj < 0.05
PEARSON_R_CUTOFF = 0.30     # Lai's age-correlation effect-size threshold

# Studies considered "primary independent" (vote weight = 1).
# Lai is "secondary" (still vote weight 1, but flagged so future weighting can downweight).
# `integrated_3_studies` is the user-supplied meta-analysis combining the three bulk
# studies (Tumasian + Pillon + GTEx) with cell-type-resolved labels — it replaces
# the three separate slots and counts as ONE primary source.
PRIMARY_SOURCES = {"integrated_3_studies", "kedlian_2024"}
SECONDARY_SOURCES = {"lai_2024"}
LEGACY_SOURCES = {"GSE164471", "GSE111016", "GTEx_v11"}

# Map from each source's cell-type label (in their tables) to canonical names
CELLTYPE_ALIASES: dict[str, str] = {
    # MuSC
    "musc": "MuSC", "satellite_cell": "MuSC", "qmusc": "MuSC", "lpmusc": "MuSC",
    "scmusc": "MuSC", "muscstem": "MuSC", "sc": "MuSC",
    # Type I myofibre
    "mf-i": "Myofiber_TypeI", "mfi": "Myofiber_TypeI", "type1": "Myofiber_TypeI",
    "type i myofibres": "Myofiber_TypeI", "type i myofibre": "Myofiber_TypeI",
    "myhc_slow": "Myofiber_TypeI",
    # Type II myofibre
    "mf-ii": "Myofiber_TypeII", "mfii": "Myofiber_TypeII", "type2": "Myofiber_TypeII",
    "type ii myofibres": "Myofiber_TypeII", "type ii myofibre": "Myofiber_TypeII",
    "myhc_fast": "Myofiber_TypeII", "mf-iia": "Myofiber_TypeII", "mf-iix": "Myofiber_TypeII",
    # Hybrid / generic myofibre
    "hyb": "Myofiber", "myofiber": "Myofiber", "mn": "Myofiber",
    # Fibroblasts / FAP
    "fap": "FAP", "fb": "FAP", "fibroblast": "FAP",
    "pnfb": "FAP", "enfb": "FAP", "perimysium_fb": "FAP",
    # Endothelial
    "venec": "Endothelial", "artec": "Endothelial", "capec": "Endothelial",
    "vein": "Endothelial", "artery": "Endothelial", "capillary": "Endothelial",
    "ec": "Endothelial",
    # Pericyte / smooth muscle
    "pericyte": "Pericyte", "smc": "Pericyte", "smooth_muscle": "Pericyte",
    # Immune
    "macrophage": "Macrophage", "mac": "Macrophage",
    "tcell": "Tcell", "t_cell": "Tcell", "nk": "NK", "nkcell": "NK",
    "monocyte": "Monocyte", "mast": "Mast", "cdc2": "DC",
}


def _normalize_celltype(label: str) -> Optional[str]:
    if not label:
        return None
    key = str(label).strip().lower().replace(" ", "_").replace("+", "")
    return CELLTYPE_ALIASES.get(key)


def _normalize_gene(g) -> Optional[str]:
    if g is None:
        return None
    s = str(g).strip().upper()
    if not s or s in {"NA", "NAN", "NONE"}:
        return None
    return s


# ---------------------------------------------------------------------------
# Per-source loaders. Each returns a list of dicts:
#   {gene, log2fc, padj, direction (up|down), cell_type|None, source_id}
# ---------------------------------------------------------------------------

def _load_bulk_tsv(
    path: Path,
    source_id: str,
    scaling_factor: float = 1.0,
    padj_cutoff: float = PADJ_CUTOFF,
    log2fc_cutoff: float = LOG2FC_CUTOFF,
) -> list[dict]:
    """Load a uniform bulk DEG TSV (gene_symbol, log2fc, padj). Returns thresholded calls.

    Per-source thresholds (`padj_cutoff`, `log2fc_cutoff`) override the global defaults
    when a study's metadata.json specifies `consensus_thresholds`. This handles studies
    like Pillon (n=40, underpowered for genome-wide FDR<0.05) where the paper's own
    published cutoff is FDR<0.10.
    """
    if not path.exists():
        print(f"  [skip] {source_id}: {path.name} not present (user upload pending)")
        return []
    rows: list[dict] = []
    with path.open("r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        gene_col = cols.get("gene_symbol") or cols.get("gene") or cols.get("symbol")
        lfc_col = cols.get("log2fc") or cols.get("log2foldchange") or cols.get("logfc")
        padj_col = cols.get("padj") or cols.get("p_adj") or cols.get("fdr") or cols.get("qvalue")
        if not (gene_col and lfc_col and padj_col):
            raise ValueError(
                f"{source_id}: TSV at {path} missing required columns. "
                f"Found: {reader.fieldnames}. Need: gene_symbol, log2fc, padj."
            )
        for row in reader:
            gene = _normalize_gene(row[gene_col])
            if not gene:
                continue
            try:
                lfc = float(row[lfc_col]) * scaling_factor
                padj = float(row[padj_col])
            except (ValueError, TypeError):
                continue
            if math.isnan(lfc) or math.isnan(padj):
                continue
            if padj >= padj_cutoff:
                continue
            if abs(lfc) < log2fc_cutoff:
                continue
            rows.append({
                "gene": gene,
                "log2fc": lfc,
                "padj": padj,
                "direction": "up" if lfc > 0 else "down",
                "cell_type": None,
                "source_id": source_id,
            })
    cutoff_str = f"padj<{padj_cutoff}, |lfc|>{log2fc_cutoff}"
    print(f"  [loaded] {source_id}: {len(rows):,} thresholded calls from {path.name}  ({cutoff_str})")
    return rows


def _read_metadata_thresholds(meta_path: Path) -> tuple[float, float, float]:
    """Read (padj, log2fc, scaling) from metadata.json.consensus_thresholds.
    Falls back to module defaults. Honors apply_scaling_factor for GTEx."""
    padj = PADJ_CUTOFF
    lfc = LOG2FC_CUTOFF
    scaling = 1.0
    if meta_path.exists():
        with meta_path.open() as f:
            meta = json.load(f)
        ct = meta.get("consensus_thresholds", {})
        if isinstance(ct, dict):
            padj = float(ct.get("padj", padj))
            lfc = float(ct.get("abs_log2fc", lfc))
        scaling = float(meta.get("apply_scaling_factor", 1.0))
    return padj, lfc, scaling


def _load_integrated_per_celltype_csv(
    path: Path,
    source_id: str,
    padj_cutoff: float = PADJ_CUTOFF,
    log2fc_cutoff: float = LOG2FC_CUTOFF,
) -> list[dict]:
    """Load a per-cell-type pseudobulk DEG CSV (the integrated meta-analysis format).

    Expected columns: gene, log2fc, pval, padj, direction, cell_type, score.
    The file is typically pre-filtered to top ~200 genes per cell type with strong
    signal. Default thresholds (padj<0.05, |lfc|>0.5) drop a handful of borderline
    rows; metadata.json may override.
    """
    if not path.exists():
        print(f"  [skip] {source_id}: {path.name} not present")
        return []
    rows: list[dict] = []
    with path.open("r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lfc = float(row["log2fc"])
                padj = float(row["padj"])
            except (ValueError, TypeError, KeyError):
                continue
            if math.isnan(lfc) or math.isnan(padj):
                continue
            if padj >= padj_cutoff:
                continue
            if abs(lfc) < log2fc_cutoff:
                continue
            gene = _normalize_gene(row.get("gene"))
            if not gene:
                continue
            ct_raw = row.get("cell_type", "")
            ct = _normalize_celltype(ct_raw)
            rows.append({
                "gene": gene,
                "log2fc": lfc,
                "padj": padj,
                "direction": row.get("direction", "up" if lfc > 0 else "down"),
                "cell_type": ct,
                "cell_type_raw": ct_raw,
                "source_id": source_id,
            })
    print(f"  [loaded] {source_id}: {len(rows):,} thresholded calls from {path.name}  "
          f"(padj<{padj_cutoff}, |lfc|>{log2fc_cutoff})")
    return rows


def _load_kedlian_xlsx(path: Path) -> list[dict]:
    """Load Kedlian 2024 SI Table 3, sheet AgeDEGs_sc_broad_celltypes.

    Columns: celltype, SYMBOL, ENSEMBL, ltsr, beta_old, beta_young, prop_young,
    prop_old, n_cells_young, n_cells_old, log2fc, REGULATION ('UP'/'DW').
    """
    if not path.exists():
        print(f"  [skip] kedlian_2024: {path.name} not present")
        return []
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = "AgeDEGs_sc_broad_celltypes"
    if sheet not in wb.sheetnames:
        raise ValueError(f"Kedlian xlsx missing expected sheet {sheet!r}; got {wb.sheetnames}")
    ws = wb[sheet]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    idx = {c: i for i, c in enumerate(header)}
    rows: list[dict] = []
    for r in rows_iter:
        try:
            ltsr = float(r[idx["ltsr"]])
            lfc = float(r[idx["log2fc"]])
        except (TypeError, ValueError):
            continue
        if ltsr < LTSR_CUTOFF:
            continue
        if abs(lfc) < LOG2FC_CUTOFF:
            continue
        gene = _normalize_gene(r[idx["SYMBOL"]])
        if not gene:
            continue
        ct_raw = r[idx["celltype"]]
        ct = _normalize_celltype(ct_raw)
        rows.append({
            "gene": gene,
            "log2fc": lfc,
            "padj": 1.0 - ltsr,        # ltsr-based pseudo-padj for downstream uniform handling
            "direction": "up" if lfc > 0 else "down",
            "cell_type": ct,
            "cell_type_raw": ct_raw,
            "source_id": "kedlian_2024",
        })
    print(f"  [loaded] kedlian_2024: {len(rows):,} thresholded calls from {path.name}")
    return rows


def _load_lai_age_correlation_xlsx(path: Path) -> list[dict]:
    """Load Lai 2024 SI Table 5 (age correlation). Three sheets: 5a Type I, 5b Type II, 5c qMuSC.

    Columns: Gene, R (Pearson's correlation), n_obs, CI95%, P, Power.
    R > 0 means up-with-age (= up in aged); R < 0 means down-with-age.
    """
    if not path.exists():
        print(f"  [skip] lai_2024: {path.name} not present")
        return []
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")
    sheet_to_celltype = {
        "Supplementary Table 5a": "Myofiber_TypeI",
        "Supplementary Table 5b": "Myofiber_TypeII",
        "Supplementary Table 5c": "MuSC",
    }
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows: list[dict] = []
    for sheet, ct in sheet_to_celltype.items():
        if sheet not in wb.sheetnames:
            print(f"  [warn] lai_2024: sheet {sheet!r} not found in {path.name}")
            continue
        ws = wb[sheet]
        # Skip 2 caption rows + 1 header row
        rows_iter = ws.iter_rows(min_row=4, values_only=True)
        for r in rows_iter:
            if r is None or len(r) < 5:
                continue
            try:
                R = float(r[1])
                pval = float(r[4])
            except (TypeError, ValueError):
                continue
            if pval >= PADJ_CUTOFF:
                continue
            if abs(R) < PEARSON_R_CUTOFF:
                continue
            gene = _normalize_gene(r[0])
            if not gene:
                continue
            # Encode R as a pseudo-log2fc for uniform downstream handling.
            # Sign carries direction; magnitude isn't used in consensus voting.
            pseudo_lfc = R
            rows.append({
                "gene": gene,
                "log2fc": pseudo_lfc,
                "padj": pval,
                "direction": "up" if R > 0 else "down",
                "cell_type": ct,
                "cell_type_raw": sheet,
                "source_id": "lai_2024",
            })
    print(f"  [loaded] lai_2024: {len(rows):,} thresholded calls from {path.name}")
    return rows


# ---------------------------------------------------------------------------
# Consensus voting
# ---------------------------------------------------------------------------

def _build_consensus(all_rows: list[dict], min_sources: int = 2) -> dict:
    """Aggregate per-gene votes across sources, return v2 atlas dict."""
    # gene -> {direction: set of source_ids}
    pooled_votes: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"up": set(), "down": set()})
    # (cell_type, gene) -> {direction: set of source_ids}
    celltype_votes: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"up": set(), "down": set()}
    )
    for r in all_rows:
        pooled_votes[r["gene"]][r["direction"]].add(r["source_id"])
        if r["cell_type"]:
            key = (r["cell_type"], r["gene"])
            celltype_votes[key][r["direction"]].add(r["source_id"])

    # Pooled consensus
    P1_up: list[str] = []   # aged-enriched
    P2_up: list[str] = []   # young-enriched (= down-in-aged)
    detailed_pooled: dict[str, dict] = {}
    for gene, dirs in pooled_votes.items():
        up_n = len(dirs["up"])
        dn_n = len(dirs["down"])
        if up_n >= min_sources and up_n > dn_n:
            P1_up.append(gene)
            detailed_pooled[gene] = {
                "direction": "up_in_aged",
                "n_sources": up_n,
                "provenance": sorted(dirs["up"]),
                "conflicts_n": dn_n,
            }
        elif dn_n >= min_sources and dn_n > up_n:
            P2_up.append(gene)
            detailed_pooled[gene] = {
                "direction": "down_in_aged",
                "n_sources": dn_n,
                "provenance": sorted(dirs["down"]),
                "conflicts_n": up_n,
            }

    # Per-cell-type consensus (single-source allowed for cell-type resolution; flagged)
    per_celltype: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"P1_up": [], "P2_up": []})
    detailed_celltype: dict[str, dict[str, dict]] = defaultdict(dict)
    for (ct, gene), dirs in celltype_votes.items():
        up_n = len(dirs["up"])
        dn_n = len(dirs["down"])
        if up_n > dn_n and up_n >= 1:
            per_celltype[ct]["P1_up"].append(gene)
            detailed_celltype[ct][gene] = {
                "direction": "up_in_aged",
                "n_sources_at_celltype": up_n,
                "provenance": sorted(dirs["up"]),
            }
        elif dn_n > up_n and dn_n >= 1:
            per_celltype[ct]["P2_up"].append(gene)
            detailed_celltype[ct][gene] = {
                "direction": "down_in_aged",
                "n_sources_at_celltype": dn_n,
                "provenance": sorted(dirs["down"]),
            }

    # Sort lists for stable output
    P1_up.sort()
    P2_up.sort()
    for ct in per_celltype:
        per_celltype[ct]["P1_up"].sort()
        per_celltype[ct]["P2_up"].sort()

    # FAP_P1_up / FAP_P2_up keys for compatibility with v1 schema
    fap_block = per_celltype.get("FAP", {"P1_up": [], "P2_up": []})

    return {
        "P1_up": P1_up,
        "P1_down": P2_up,        # mirror, matches v1 alias convention
        "P2_up": P2_up,
        "P2_down": P1_up,        # mirror
        "FAP_P1_up": fap_block["P1_up"],
        "FAP_P2_up": fap_block["P2_up"],
        "per_cell_type": dict(per_celltype),
        "detailed": {
            "pooled": detailed_pooled,
            "per_cell_type": {ct: dict(d) for ct, d in detailed_celltype.items()},
        },
    }


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build(aging_studies_dir: Path) -> dict:
    """Discover sources, load each, return v2 atlas dict."""
    print(f"Building v2 consensus atlas from {aging_studies_dir}/")

    sources_present: list[str] = []
    sources_skipped: list[str] = []
    all_rows: list[dict] = []

    # 1. Integrated 3-study bulk meta-analysis (replaces separate Tumasian/Pillon/GTEx slots)
    p = aging_studies_dir / "muscle_atlas_integrated" / "integrated_per_celltype_degs.csv"
    padj, lfc, _ = _read_metadata_thresholds(p.parent / "metadata.json")
    rows = _load_integrated_per_celltype_csv(p, "integrated_3_studies", padj, lfc)
    if rows:
        sources_present.append("integrated_3_studies")
        all_rows.extend(rows)
    else:
        sources_skipped.append("integrated_3_studies")

    # Legacy bulk slots — kept for back-compat but DO NOT load if integrated source is present
    # (it would double-count the same biology). When integrated is missing, fall back to bulk.
    if "integrated_3_studies" not in sources_present:
        for legacy_id, folder in [
            ("GSE164471", "GSE164471_tumasian_2021"),
            ("GSE111016", "GSE111016_pillon_2019"),
            ("GTEx_v11",  "gtex_v11_skeletal_muscle"),
        ]:
            p_legacy = aging_studies_dir / folder / "deg_table.tsv"
            padj_l, lfc_l, scaling_l = _read_metadata_thresholds(p_legacy.parent / "metadata.json")
            legacy_rows = _load_bulk_tsv(p_legacy, legacy_id, scaling_l, padj_l, lfc_l)
            if legacy_rows:
                sources_present.append(legacy_id)
                all_rows.extend(legacy_rows)
            else:
                sources_skipped.append(legacy_id)
    else:
        sources_skipped.extend(["GSE164471 (subsumed)", "GSE111016 (subsumed)", "GTEx_v11 (subsumed)"])

    # 4. Kedlian — single-cell SI Table 3
    p = (
        aging_studies_dir
        / "kedlian_lacraz_2024_natage"
        / "kedlian_2024_SuppTable3_aging_DEGs.xlsx"
    )
    rows = _load_kedlian_xlsx(p)
    if rows:
        sources_present.append("kedlian_2024")
        all_rows.extend(rows)
    else:
        sources_skipped.append("kedlian_2024")

    # 5. Lai — age correlation SI Table 5
    p = aging_studies_dir / "lai_2024_hlma" / "lai_2024_SuppTable5_age_correlation.xlsx"
    rows = _load_lai_age_correlation_xlsx(p)
    if rows:
        sources_present.append("lai_2024")
        all_rows.extend(rows)
    else:
        sources_skipped.append("lai_2024")

    if len(sources_present) < 2:
        print(
            f"\nERROR: only {len(sources_present)} source(s) present "
            f"({sources_present}). Need >=2 for any consensus call."
        )
        sys.exit(2)

    consensus = _build_consensus(all_rows, min_sources=2)

    # Stamp metadata
    consensus["version"] = "v2-consensus"
    consensus["description"] = (
        f"v2 multi-source consensus muscle aging atlas. Built {date.today().isoformat()}. "
        f"P1_up = aged-enriched in >=2 of {len(sources_present)} sources; "
        f"P2_up = young-enriched (down-in-aged) in >=2 sources."
    )
    sources_present_set = set(sources_present)
    consensus["metadata"] = {
        "build_date": date.today().isoformat(),
        "sources_present": sources_present,
        "sources_skipped": sources_skipped,
        "primary_sources": sorted(PRIMARY_SOURCES & sources_present_set),
        "secondary_sources": sorted(SECONDARY_SOURCES & sources_present_set),
        "legacy_bulk_sources_present": sorted(LEGACY_SOURCES & sources_present_set),
        "thresholds": {
            "padj": PADJ_CUTOFF,
            "abs_log2fc": LOG2FC_CUTOFF,
            "ltsr": LTSR_CUTOFF,
            "abs_pearson_r": PEARSON_R_CUTOFF,
        },
        "min_sources_for_consensus": 2,
        "direction_convention": "up = upregulated in aged (P1); down = downregulated in aged (P2 enriched)",
        "alias_note": "P1_down == P2_up (mirror lists); P2_down == P1_up",
        "papers": [
            "Tumasian et al. 2021, Nat Comm (GSE164471)",
            "Pillon et al. 2019, Nat Comm (GSE111016, Singapore Sarcopenia)",
            "GTEx Consortium v11",
            "Kedlian/Lacraz et al. 2024, Nat Aging (DOI 10.1038/s43587-024-00613-3)",
            "Lai et al. 2024, Nature (DOI 10.1038/s41586-024-07348-6)",
        ],
        "n_genes_pooled_P1_up": len(consensus["P1_up"]),
        "n_genes_pooled_P2_up": len(consensus["P2_up"]),
        "n_cell_types_resolved": len(consensus["per_cell_type"]),
    }

    return consensus


def main() -> int:
    ap = argparse.ArgumentParser(description="Build v2 consensus muscle aging atlas")
    ap.add_argument(
        "--aging-studies-dir",
        type=Path,
        default=Path("backend/knowledge/aging_studies"),
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("backend/knowledge/muscle_atlas_DE_v2_consensus.json"),
    )
    args = ap.parse_args()

    atlas = build(args.aging_studies_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(atlas, f, indent=2, sort_keys=False)

    print()
    print(f"Wrote {args.output}")
    print(f"  Sources present:  {atlas['metadata']['sources_present']}")
    print(f"  Sources skipped:  {atlas['metadata']['sources_skipped']}")
    print(f"  P1_up genes (aged-enriched, >=2 sources):  {len(atlas['P1_up'])}")
    print(f"  P2_up genes (young-enriched, >=2 sources): {len(atlas['P2_up'])}")
    print(f"  Cell types with per-cell-type calls:        {len(atlas['per_cell_type'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
