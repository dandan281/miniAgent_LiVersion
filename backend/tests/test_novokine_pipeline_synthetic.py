"""
End-to-end synthetic smoke test for the novokine_pair_ranker pipeline.

Builds a 6-receptor / 15-pair toy dataset, calls each of the 3 new tools
(string_ppi, gtex_expression, go_annotations) against the live public APIs,
and exercises every modeling step (EXP score, v4.0 regression, scale-collision
detection, v4.3, network analysis, permutation test). Emits a real xlsx so
we can verify the artifact_refs plumbing.

Run from the backend dir:
    python -m pytest tests/test_novokine_pipeline_synthetic.py -s
or directly:
    python tests/test_novokine_pipeline_synthetic.py
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import numpy as np

from tools.string_api_tool import StringApiTool
from tools.gtex_api_tool import GtexApiTool
from tools.go_quickgo_tool import GoQuickGoTool


def _line(label: str) -> None:
    print(f"\n{'=' * 12}  {label}  {'=' * 12}")


# --- toy dataset (no hardcoding in the skill — but this *is* a test fixture,
# so concrete numbers are fine here) ---------------------------------------

RECEPTORS = [
    {"gene": "EGFR",   "uniprot": "P00533", "family": "ERBB"},
    {"gene": "ERBB2",  "uniprot": "P04626", "family": "ERBB"},
    {"gene": "IL6ST",  "uniprot": "P40189", "family": "gp130"},
    {"gene": "TGFBR2", "uniprot": "P37173", "family": "TGFb"},
    {"gene": "BMPR2",  "uniprot": "Q13873", "family": "BMP"},
    {"gene": "NTRK1",  "uniprot": "P04629", "family": "RTK"},
]

# Synthetic assay readouts for 8 "tested" pairs (fold-change vs untreated = 1.0).
# Higher numbers = stronger induction. Designed so EGFR+IL6ST wins.
TESTED_ROWS = [
    ("EGFR",  "IL6ST",  1.95, 1.65, 2.40, 1.60),   # strong hit
    ("EGFR",  "TGFBR2", 1.75, 1.55, 2.10, 1.40),   # strong hit
    ("BMPR2", "NTRK1",  1.60, 1.40, 1.85, 1.35),   # moderate
    ("ERBB2", "NTRK1",  1.45, 1.35, 1.70, 1.25),   # moderate
    ("EGFR",  "ERBB2",  1.30, 1.20, 1.45, 1.15),   # weak
    ("EGFR",  "BMPR2",  1.15, 1.10, 1.20, 1.05),   # weak
    ("ERBB2", "TGFBR2", 1.10, 1.05, 1.10, 1.00),   # no effect
    ("IL6ST", "TGFBR2", 1.00, 1.00, 1.05, 1.00),   # no effect
]
ASSAY_COLS = ["desmin", "ocr", "secondary", "myotube"]
ASSAY_WEIGHTS = {"desmin": 0.30, "ocr": 0.15, "secondary": 0.40, "myotube": 0.15}


def step_1_features() -> tuple[pd.DataFrame, dict]:
    """Steps 3-5: call STRING, GTEx, QuickGO for the 6 receptors."""
    _line("Step 3 — QuickGO (BP terms per receptor)")
    qg = GoQuickGoTool()
    bp_terms: dict[str, list[str]] = {}
    for r in RECEPTORS:
        _, art = qg._run(
            gene_product_ids=r["uniprot"],
            aspect="biological_process",
            only_experimental=True,
            limit=25,
        )
        gp_map = (art.get("structured_payload") or {}).get("annotations_by_gene", {})
        terms = []
        for gp, anns in gp_map.items():
            for a in anns:
                if a.get("go_id"):
                    terms.append(a["go_id"])
        bp_terms[r["gene"]] = list(set(terms))
        print(f"  {r['gene']:7s} ({r['uniprot']}): {len(bp_terms[r['gene']])} unique BP terms")

    _line("Step 4 — GTEx (median TPM)")
    gt = GtexApiTool()
    tpm_muscle: dict[str, float] = {}
    tpm_fibro: dict[str, float] = {}
    for r in RECEPTORS:
        _, art = gt._run(gene=r["gene"], tissue_filter="Muscle_Skeletal,Cultured_fibroblasts")
        sp = art.get("structured_payload") or {}
        muscle = sp.get("muscle_tissues", {}) or {}
        fibro = sp.get("fibroblast_tissues", {}) or {}
        tpm_muscle[r["gene"]] = float(muscle.get("Muscle_Skeletal", 0.0))
        tpm_fibro[r["gene"]] = float(fibro.get("Cells_Cultured_fibroblasts", 0.0))
        print(f"  {r['gene']:7s}: muscle={tpm_muscle[r['gene']]:.2f}  fibro={tpm_fibro[r['gene']]:.2f}  TPM")

    _line("Step 5 — STRING (combined score per pair)")
    st = StringApiTool()
    ident = ",".join(r["gene"] for r in RECEPTORS)
    _, art = st._run(identifiers=ident, query_type="network", species=9606)
    edges = (art.get("structured_payload") or {}).get("edges", [])
    string_scores: dict[tuple[str, str], float] = {}
    for e in edges:
        a, b = e["node_a"], e["node_b"]
        key = tuple(sorted([a, b]))
        string_scores[key] = float(e["combined_score"])
    print(f"  edges returned: {len(edges)} (pairs without an edge → novelty=1.0)")
    for key, score in sorted(string_scores.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {key[0]}--{key[1]}: combined={score:.3f}  novelty={1-score:.3f}")

    # Step 6 — assemble per-pair feature matrix for ALL ordered pairs
    families = {r["gene"]: r["family"] for r in RECEPTORS}
    all_pairs = list(itertools.combinations([r["gene"] for r in RECEPTORS], 2))
    rows = []
    for a, b in all_pairs:
        key = tuple(sorted([a, b]))
        combined = string_scores.get(key, 0.0)
        novelty = round(1.0 - combined, 4)
        bp_overlap = len(set(bp_terms[a]) & set(bp_terms[b]))
        rows.append({
            "receptor_a": a, "receptor_b": b,
            "family_a": families[a], "family_b": families[b],
            "family_cross": f"{families[a]}x{families[b]}",
            "gtex_muscle_a": tpm_muscle[a], "gtex_muscle_b": tpm_muscle[b],
            "gtex_fibro_a":  tpm_fibro[a],  "gtex_fibro_b":  tpm_fibro[b],
            "go_bp_overlap": bp_overlap,
            "string_combined": combined,
            "novelty": novelty,
        })
    features = pd.DataFrame(rows).set_index(["receptor_a", "receptor_b"])
    print(f"\nfeature matrix: {features.shape[0]} pairs × {features.shape[1]} columns")
    return features, {"bp_terms": bp_terms, "tpm_muscle": tpm_muscle, "tpm_fibro": tpm_fibro}


def step_7_exp(tested: pd.DataFrame, weights: dict) -> pd.DataFrame:
    _line("Step 7 — EXP score")
    df = tested.copy()
    for assay, w in weights.items():
        max_shift = (df[assay] - 1.0).clip(lower=0).max()
        if max_shift <= 0:
            df[f"{assay}_norm"] = 0.0
        else:
            df[f"{assay}_norm"] = (df[assay] - 1.0).clip(lower=0) / max_shift
    df["EXP"] = sum(w * df[f"{a}_norm"] for a, w in weights.items())
    df = df.sort_values("EXP", ascending=False)
    print(df[ASSAY_COLS + ["EXP"]].head(10).to_string())
    return df


def step_8_v40(features: pd.DataFrame, tested_exp: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    _line("Step 8 — fit v4.0 (mechanistic features → EXP)")
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import LeaveOneOut, cross_val_score

    # Take only numeric pair-level features
    numeric = features.select_dtypes(include="number").copy()
    # Align tested rows to feature index keys (sorted tuple)
    tested_keys = [tuple(sorted([a, b])) for (a, b) in zip(tested_exp["receptor_a"], tested_exp["receptor_b"])]
    feat_keys = [tuple(sorted([a, b])) for (a, b) in numeric.index]
    feat_keys_lookup = {k: i for i, k in enumerate(feat_keys)}
    selected_rows = [feat_keys_lookup[k] for k in tested_keys if k in feat_keys_lookup]
    X = numeric.iloc[selected_rows].copy()
    y = tested_exp["EXP"].values[: len(selected_rows)]

    model = RidgeCV().fit(X.values, y)
    loo_r2 = cross_val_score(model, X.values, y, cv=LeaveOneOut(), scoring="r2").mean()
    pearson = pd.DataFrame({"feature": X.columns, "pearson_r": [X[c].corr(pd.Series(y, index=X.index)) for c in X.columns]})
    print(f"LOO R² = {loo_r2:.3f} (Biomni's original v4.0 LOO R² ≈ −0.04 — synthetic data has stronger signal)")
    print(pearson.to_string(index=False))
    # Score every pair
    v40_scores = pd.Series(model.predict(numeric.values), index=numeric.index, name="v40_score")
    diag = {"loo_r2": loo_r2, "pearson": pearson.to_dict(orient="records")}
    return v40_scores, diag


def step_9_scale_collision(v40_scores: pd.Series, tested_exp: pd.DataFrame) -> dict:
    _line("Step 9 — scale collision diagnosis")
    tested_keys = {tuple(sorted([a, b])) for (a, b) in zip(tested_exp["receptor_a"], tested_exp["receptor_b"])}
    untested_v40 = v40_scores[[i for i in v40_scores.index if tuple(sorted(i)) not in tested_keys]]
    if untested_v40.empty:
        return {"collision": False, "note": "no untested pairs in synthetic data"}
    exp_max = float(tested_exp["EXP"].max())
    v40_min = float(untested_v40.min())
    collision = v40_min > exp_max
    print(f"  tested EXP max:    {exp_max:.3f}")
    print(f"  untested v40 min:  {v40_min:.3f}")
    print(f"  collision detected: {collision}")
    return {"collision": collision, "exp_max": exp_max, "v40_min": v40_min}


def step_10_network(tested_exp: pd.DataFrame) -> dict:
    _line("Step 10 — network analysis + permutation test")
    import networkx as nx
    from scipy import stats
    G = nx.Graph()
    for _, r in tested_exp.iterrows():
        G.add_edge(r["receptor_a"], r["receptor_b"], weight=float(r["EXP"]))
    deg = dict(G.degree(weight="weight"))
    top_hub = max(deg.items(), key=lambda kv: kv[1])
    print(f"  weighted degree top hub: {top_hub[0]} ({top_hub[1]:.3f})")
    # Permutation test: top-half vs rest
    n = len(tested_exp)
    high = tested_exp["EXP"].values[: n // 2]
    rest = tested_exp["EXP"].values[n // 2:]
    u, p = stats.mannwhitneyu(high, rest, alternative="greater")
    print(f"  Mann-Whitney U(top-half > rest): U={u}, p={p:.4f}")
    return {"weighted_degree": deg, "top_hub": top_hub, "mwu_p": float(p), "mwu_u": float(u)}


def step_11_emit_xlsx(
    features: pd.DataFrame,
    tested_exp: pd.DataFrame,
    v40_scores: pd.Series,
    out_dir: Path,
    diag: dict,
    collision: dict,
    network: dict,
) -> Path:
    _line("Step 11 — corrected unified ranking xlsx")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "novokine_ranking.xlsx"

    tested_keys = {tuple(sorted([a, b])) for (a, b) in zip(tested_exp["receptor_a"], tested_exp["receptor_b"])}
    untested_v40 = v40_scores[[i for i in v40_scores.index if tuple(sorted(i)) not in tested_keys]]
    novelty_lookup = features["novelty"].to_dict()
    v43 = 0.90 * untested_v40 + 0.10 * pd.Series({i: novelty_lookup.get(i, 1.0) for i in untested_v40.index})
    untested_table = pd.DataFrame({
        "v40_score": untested_v40,
        "novelty": pd.Series({i: novelty_lookup.get(i, 1.0) for i in untested_v40.index}),
        "v43_score": v43,
    }).sort_values("v43_score", ascending=False).reset_index()

    diagnostics = pd.DataFrame([
        {"metric": "v4.0_loo_r2", "value": diag["loo_r2"]},
        {"metric": "scale_collision_detected", "value": collision["collision"]},
        {"metric": "exp_max", "value": collision.get("exp_max")},
        {"metric": "v40_min_untested", "value": collision.get("v40_min")},
        {"metric": "network_top_hub", "value": str(network["top_hub"])},
        {"metric": "mannwhitneyu_p", "value": network["mwu_p"]},
    ])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        tested_exp.reset_index(drop=True).to_excel(writer, sheet_name="Tested EXP", index=False)
        untested_table.to_excel(writer, sheet_name="Untested v4.3", index=False)
        features.reset_index().to_excel(writer, sheet_name="Feature Matrix", index=False)
        diagnostics.to_excel(writer, sheet_name="Diagnostics", index=False)
        pd.DataFrame(diag["pearson"]).to_excel(writer, sheet_name="v4.0 Pearson r", index=False)

    size = out_path.stat().st_size
    print(f"  wrote {out_path} ({size:,} bytes)")
    return out_path


def main() -> int:
    run_id = time.strftime("%Y%m%d_%H%M%S")
    base = BACKEND_DIR
    out_dir = base / "artifacts" / "novokine_pair_ranker" / f"synthetic_{run_id}"

    features, _ = step_1_features()
    tested_df = pd.DataFrame(TESTED_ROWS, columns=["receptor_a", "receptor_b", *ASSAY_COLS])
    tested_exp = step_7_exp(tested_df, ASSAY_WEIGHTS)
    v40, diag = step_8_v40(features, tested_exp)
    collision = step_9_scale_collision(v40, tested_exp)
    network = step_10_network(tested_exp)
    xlsx = step_11_emit_xlsx(features, tested_exp, v40, out_dir, diag, collision, network)

    # Verify the xlsx is a real Excel file
    import subprocess
    file_out = subprocess.run(["file", str(xlsx)], capture_output=True, text=True).stdout.strip()
    print(f"\nfile(1) verdict: {file_out}")
    assert "Microsoft Excel" in file_out or "Zip archive" in file_out, "xlsx not valid"
    print("\nALL STEPS PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
