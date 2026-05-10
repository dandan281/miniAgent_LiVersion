"""Atlas-seeded novokine candidate generator.

Replaces the purely combinatorial `generate_candidates.py` with a
biology-driven seed: pick candidate receptor pairs by querying the local
human muscle atlas (Kedlian/Lai 2024) for per-cell-type, per-age-bin
expression, then score each pair by:

  1. **Co-expression in aged target cell type** (best case — both receptors
     present in old MuSC / MF-I / FB at fraction_expressing >= PC_THR and
     mean_expression > ME_THR). High score → low p_fail_1, high reward
     ceiling. Direct rejuvenation target.

  2. **Aged dropout** (both receptors in young, lost in old). Lower score
     than (1) but still actionable — a novokine could rescue the lost
     coupling. Tagged `co_expression_aged_dropout = True` for downstream.

  3. **Geometry compatibility** (ECD ratio penalty). H2F has a 1.94×
     asymmetry — pairs with extreme asymmetry (>3×) are penalized.

The script writes a `candidates_*.json` list with the same shape that
`scripts/rl_loop.py --mode full --input <path>` consumes: each record has
`candidate_id`, `receptor_A`, `receptor_B`, `linker`, plus an extra
`atlas_seed` block for provenance.

Pairs already scored at TOP_K_DESIGN tier in the experience buffer are
skipped (they would just cache-hit). Pairs scored as INCOHERENT are
similarly skipped (no point re-scoring known failures).

Run:
  python backend/scripts/atlas_seeded_candidates.py \
      --top 20 --linker GS_med --out backend/knowledge/atlas_candidates_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from tools.local_atlas_tool import (  # noqa: E402
    _load_atlas,
    _per_group_expression,
)
from utils.experience_buffer import (  # noqa: E402
    load_buffer,
    pair_key,
    lookup_by_pair,
)

# ─────────────────────────────────────────────────────────────────────────
# Curated receptor pool. Restricted to receptor classes where forced-proximity
# transphosphorylation agonism is mechanistically established (per
# COT_Rejuv_Pipeline Step 1c): RTKs, cytokine/JAK-STAT receptors, TGF-β
# type I/II pairs, TNFR superfamily. Ordered by rough literature priority
# for muscle / aging biology.
# ─────────────────────────────────────────────────────────────────────────
RECEPTOR_POOL: list[dict[str, Any]] = [
    # RTKs — broad muscle-relevant set
    {"symbol": "ERBB2",  "family": "RTK_ErbB",   "ecd_aa": 630, "muscle_role": "orphan; H2F partner"},
    {"symbol": "ERBB3",  "family": "RTK_ErbB",   "ecd_aa": 615, "muscle_role": "neuregulin signaling"},
    {"symbol": "ERBB4",  "family": "RTK_ErbB",   "ecd_aa": 630, "muscle_role": "neuregulin signaling"},
    {"symbol": "EGFR",   "family": "RTK_ErbB",   "ecd_aa": 620, "muscle_role": "MuSC proliferation"},
    {"symbol": "FGFR1",  "family": "RTK_FGFR",   "ecd_aa": 353, "muscle_role": "MuSC self-renewal; H2F partner"},
    {"symbol": "FGFR2",  "family": "RTK_FGFR",   "ecd_aa": 367, "muscle_role": "regeneration"},
    {"symbol": "FGFR3",  "family": "RTK_FGFR",   "ecd_aa": 352, "muscle_role": "regeneration"},
    {"symbol": "FGFR4",  "family": "RTK_FGFR",   "ecd_aa": 350, "muscle_role": "muscle differentiation"},
    {"symbol": "IGF1R",  "family": "RTK_INSR",   "ecd_aa": 906, "muscle_role": "anabolic; declines with age"},
    {"symbol": "INSR",   "family": "RTK_INSR",   "ecd_aa": 929, "muscle_role": "metabolic; declines with age"},
    {"symbol": "MET",    "family": "RTK_MET",    "ecd_aa": 932, "muscle_role": "MuSC migration; HGF receptor"},
    {"symbol": "KIT",    "family": "RTK_PDGFR",  "ecd_aa": 503, "muscle_role": "stem cell maintenance"},
    {"symbol": "FLT1",   "family": "RTK_VEGFR",  "ecd_aa": 758, "muscle_role": "vascular niche"},
    {"symbol": "KDR",    "family": "RTK_VEGFR",  "ecd_aa": 763, "muscle_role": "vascular niche"},
    {"symbol": "NTRK2",  "family": "RTK_TRK",    "ecd_aa": 380, "muscle_role": "neuromuscular junction"},
    {"symbol": "RET",    "family": "RTK_RET",    "ecd_aa": 636, "muscle_role": "GDNF; neurotrophic"},
    # Cytokine receptors / JAK-STAT
    {"symbol": "IL6R",   "family": "Cytokine",   "ecd_aa": 339, "muscle_role": "myokine signaling"},
    {"symbol": "IL6ST",  "family": "Cytokine",   "ecd_aa": 597, "muscle_role": "gp130; common cytokine receptor"},
    {"symbol": "LIFR",   "family": "Cytokine",   "ecd_aa": 813, "muscle_role": "myogenesis"},
    {"symbol": "OSMR",   "family": "Cytokine",   "ecd_aa": 717, "muscle_role": "muscle stem cell quiescence"},
    {"symbol": "IFNAR1", "family": "Cytokine",   "ecd_aa": 410, "muscle_role": "antiviral; inflammation"},
    {"symbol": "IFNAR2", "family": "Cytokine",   "ecd_aa": 217, "muscle_role": "antiviral; inflammation"},
    # TGF-β superfamily — type I/II pairs
    {"symbol": "ACVR1",  "family": "TGFb_TypeI",  "ecd_aa": 102, "muscle_role": "BMP signaling"},
    {"symbol": "ACVR2B", "family": "TGFb_TypeII", "ecd_aa": 116, "muscle_role": "myostatin receptor"},
    {"symbol": "BMPR1A", "family": "TGFb_TypeI",  "ecd_aa": 130, "muscle_role": "BMP myogenesis"},
    {"symbol": "TGFBR2", "family": "TGFb_TypeII", "ecd_aa": 137, "muscle_role": "fibrosis"},
    # TNFR
    {"symbol": "TNFRSF1A", "family": "TNFR",     "ecd_aa": 190, "muscle_role": "TNFα; inflammaging"},
    {"symbol": "TNFRSF1B", "family": "TNFR",     "ecd_aa": 235, "muscle_role": "TNFα; inflammaging"},
]

# Cell types we care about for muscle rejuvenation — both atlas labels and
# convenient short names. The local atlas uses MuSC, MF-I, MF-II, FB, EnFB,
# PnFB, SMC, Macrophage, T-cell, etc.
TARGET_CELL_TYPES = ["MuSC", "MF-I", "MF-II", "FB", "EnFB", "PnFB"]

# Decision thresholds — match cellxgene_expression / local_atlas_query skill defaults
PC_THR = 0.10
ME_THR = 0.5

# Linker geometries (per COT_Rejuv_Pipeline Step 1d)
LINKER_OPTIONS = [
    "flexible_GS4",   # ~20 Å
    "flexible_GS8",   # ~40 Å
    "rigid_helix_20", # ~30 Å
    "rigid_helix_40", # ~60 Å
    "exposit_rigid",
]

# H2F has 630/353 = 1.78× asymmetry — pairs above this are progressively
# penalized but not blocked.
H2F_ASYMMETRY = 1.78
ASYMMETRY_HARD_PENALTY = 3.0  # >3× → penalty bites


# ─────────────────────────────────────────────────────────────────────────
# Atlas query
# ─────────────────────────────────────────────────────────────────────────
def query_atlas_for_pool(
    pool: list[dict[str, Any]],
    *,
    cell_types: list[str],
    age_bins: tuple[str, ...] = ("young", "old"),
    verbose: bool = False,
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """Returns a nested dict:
      result[gene][cell_type][age_bin] = {fraction_expressing, mean_expression, n_cells, ...}

    Calls the LocalAtlasTool internals directly to bypass the contract.py
    payload-size cap (which is meant for agent-facing tool calls and would
    truncate this script's bulk query).
    """
    adata = _load_atlas()
    by_gene: dict[str, dict] = {}
    for rec in pool:
        sym = rec["symbol"]
        try:
            result = _per_group_expression(adata, sym, cell_types, list(age_bins))
        except Exception as exc:
            if verbose:
                print(f"[atlas] {sym}: query failed: {exc}")
            continue
        if result.get("missing_gene"):
            if verbose:
                print(f"[atlas] {sym}: not in atlas var.index, skipped")
            continue
        per_ct = result.get("per_cell_type") or {}
        if isinstance(per_ct, dict) and per_ct:
            by_gene[sym] = per_ct
            if verbose:
                print(f"[atlas] {sym}: {len(per_ct)} cell types matched filter")
    return by_gene


def _has_min_expression(group: dict | None) -> bool:
    if not isinstance(group, dict):
        return False
    pc = group.get("fraction_expressing")
    me = group.get("mean_expression")
    if pc is None or me is None:
        return False
    return pc >= PC_THR and me > ME_THR


# ─────────────────────────────────────────────────────────────────────────
# Pair scoring
# ─────────────────────────────────────────────────────────────────────────
def score_pair(
    rec_A: dict[str, Any],
    rec_B: dict[str, Any],
    expr_A: dict[str, dict] | None,
    expr_B: dict[str, dict] | None,
) -> dict[str, Any]:
    """Score a single (rA, rB) pair across all target cell types."""
    sym_A, sym_B = rec_A["symbol"], rec_B["symbol"]

    # Expression by cell type for each receptor
    ecd_a, ecd_b = rec_A.get("ecd_aa", 0) or 0, rec_B.get("ecd_aa", 0) or 0
    ecd_ratio = max(ecd_a, ecd_b) / max(min(ecd_a, ecd_b), 1)

    co_expr_old: list[str] = []      # cell types where BOTH pass in old
    co_expr_young: list[str] = []    # cell types where BOTH pass in young
    aged_dropout: list[str] = []     # young pass, old fail (rescue target)

    if not isinstance(expr_A, dict) or not isinstance(expr_B, dict):
        # Treat missing expression as no signal
        atlas_match_count = 0
    else:
        atlas_match_count = 1
        # Iterate over all cell types either receptor has data for
        all_cts = set(expr_A.keys()) | set(expr_B.keys())
        for ct in all_cts:
            a_ct = expr_A.get(ct) or {}
            b_ct = expr_B.get(ct) or {}
            a_old = a_ct.get("old") if isinstance(a_ct, dict) else None
            a_young = a_ct.get("young") if isinstance(a_ct, dict) else None
            b_old = b_ct.get("old") if isinstance(b_ct, dict) else None
            b_young = b_ct.get("young") if isinstance(b_ct, dict) else None
            old_ok = _has_min_expression(a_old) and _has_min_expression(b_old)
            young_ok = _has_min_expression(a_young) and _has_min_expression(b_young)
            if old_ok:
                co_expr_old.append(ct)
            if young_ok:
                co_expr_young.append(ct)
            if young_ok and not old_ok:
                aged_dropout.append(ct)

    # Composite atlas score:
    #   weight co-expression in old (most actionable) heavily, dropout moderately.
    #   normalize per-cell-type counts (max 6 target cell types).
    n_targets = len(TARGET_CELL_TYPES)
    score_co_old = len(co_expr_old) / n_targets        # 0..1
    score_dropout = len(aged_dropout) / n_targets       # 0..1
    asymmetry_penalty = 0.0
    if ecd_ratio > ASYMMETRY_HARD_PENALTY:
        asymmetry_penalty = 0.30
    elif ecd_ratio > H2F_ASYMMETRY:
        asymmetry_penalty = 0.10 * (ecd_ratio - H2F_ASYMMETRY) / (ASYMMETRY_HARD_PENALTY - H2F_ASYMMETRY)

    # Family compatibility: same family pairs (e.g. FGFR1+FGFR2) are degenerate,
    # they form natural homo/hetero dimers and forced proximity adds little.
    family_penalty = 0.10 if rec_A.get("family") == rec_B.get("family") else 0.0

    composite = (
        0.65 * score_co_old
        + 0.25 * score_dropout
        - asymmetry_penalty
        - family_penalty
    )

    return {
        "co_expression_in_old": co_expr_old,
        "co_expression_in_young": co_expr_young,
        "aged_dropout_cell_types": aged_dropout,
        "n_atlas_match": atlas_match_count,
        "ecd_ratio": round(ecd_ratio, 2),
        "asymmetry_penalty": round(asymmetry_penalty, 3),
        "same_family_penalty": family_penalty,
        "composite_atlas_score": round(composite, 4),
        "score_co_old": round(score_co_old, 3),
        "score_dropout": round(score_dropout, 3),
    }


# ─────────────────────────────────────────────────────────────────────────
# Buffer-aware filtering
# ─────────────────────────────────────────────────────────────────────────
def already_scored_high(records: list[dict], rA: str, rB: str, linker: str) -> bool:
    """Skip a pair that already has a TOP_K_DESIGN result in the buffer."""
    hit = lookup_by_pair(records, rA, rB, linker, require_full_mode=True)
    if not hit:
        return False
    tier = (hit.get("decision") or {}).get("tier")
    return tier == "TOP_K_DESIGN"


def already_scored_incoherent(records: list[dict], rA: str, rB: str, linker: str) -> bool:
    """Skip a pair that consistently scored INCOHERENT in the buffer."""
    hit = lookup_by_pair(records, rA, rB, linker, require_full_mode=True)
    if not hit:
        return False
    tier = (hit.get("decision") or {}).get("tier")
    return tier == "INCOHERENT_LOG_ONLY"


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=20,
                    help="Number of pairs to output (after linker expansion).")
    ap.add_argument("--linker", default="flexible_GS4",
                    help=f"Linker to attach to each pair. One of {LINKER_OPTIONS} "
                         "or 'all' to expand each pair × 5 linkers.")
    ap.add_argument("--out", type=Path,
                    default=BACKEND / "knowledge" / "atlas_candidates_v1.json",
                    help="Output JSON path.")
    ap.add_argument("--include-cached", action="store_true",
                    help="Do NOT skip pairs already in experience buffer.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.linker != "all" and args.linker not in LINKER_OPTIONS:
        print(f"[error] unknown linker {args.linker!r}; expected one of {LINKER_OPTIONS} or 'all'.")
        return 2

    # ── Step 1: query atlas for all receptors in pool ──────────────────────
    print(f"[gen] querying local atlas for {len(RECEPTOR_POOL)} receptors × "
          f"{len(TARGET_CELL_TYPES)} target cell types...")
    by_gene = query_atlas_for_pool(
        RECEPTOR_POOL,
        cell_types=TARGET_CELL_TYPES,
        verbose=args.verbose,
    )
    n_with_data = sum(1 for r in RECEPTOR_POOL if r["symbol"] in by_gene)
    print(f"[gen] atlas data available for {n_with_data}/{len(RECEPTOR_POOL)} receptors.")

    # ── Step 2: score every receptor pair ──────────────────────────────────
    pair_records: list[dict[str, Any]] = []
    for rec_A, rec_B in combinations(RECEPTOR_POOL, 2):
        score = score_pair(
            rec_A, rec_B,
            by_gene.get(rec_A["symbol"]),
            by_gene.get(rec_B["symbol"]),
        )
        pair_records.append({
            "receptor_A": rec_A["symbol"],
            "receptor_B": rec_B["symbol"],
            "family_A": rec_A.get("family"),
            "family_B": rec_B.get("family"),
            "ecd_A": rec_A.get("ecd_aa"),
            "ecd_B": rec_B.get("ecd_aa"),
            **score,
        })

    pair_records.sort(key=lambda d: -d["composite_atlas_score"])

    # ── Step 3: linker expansion + buffer dedup ────────────────────────────
    linkers = LINKER_OPTIONS if args.linker == "all" else [args.linker]
    buffer_records = load_buffer()
    print(f"[gen] experience buffer has {len(buffer_records)} prior records.")

    out: list[dict[str, Any]] = []
    for pr in pair_records:
        if len(out) >= args.top:
            break
        for linker in linkers:
            cand_id = f"{pr['receptor_A']}_{pr['receptor_B']}_{linker}"
            if not args.include_cached:
                if already_scored_high(buffer_records, pr["receptor_A"], pr["receptor_B"], linker):
                    if args.verbose:
                        print(f"[gen] skip cached TOP_K: {cand_id}")
                    continue
                if already_scored_incoherent(buffer_records, pr["receptor_A"], pr["receptor_B"], linker):
                    if args.verbose:
                        print(f"[gen] skip cached INCOHERENT: {cand_id}")
                    continue
            out.append({
                "candidate_id": cand_id,
                "receptor_A": pr["receptor_A"],
                "receptor_B": pr["receptor_B"],
                "linker": linker,
                "atlas_seed": {
                    "composite_atlas_score": pr["composite_atlas_score"],
                    "co_expression_in_old": pr["co_expression_in_old"],
                    "co_expression_in_young": pr["co_expression_in_young"],
                    "aged_dropout_cell_types": pr["aged_dropout_cell_types"],
                    "ecd_ratio": pr["ecd_ratio"],
                    "asymmetry_penalty": pr["asymmetry_penalty"],
                    "family_A": pr["family_A"],
                    "family_B": pr["family_B"],
                },
                "notes": "atlas-seeded; ranked by co-expression in aged target cells.",
            })
            if len(out) >= args.top:
                break

    # ── Step 4: write output ──────────────────────────────────────────────
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(out, f, indent=2)
    print(f"[gen] wrote {len(out)} candidates → {args.out}")

    # Brief top-10 summary to stdout
    print(f"\n[gen] Top 10 atlas-ranked pairs:")
    for i, c in enumerate(out[:10]):
        s = c["atlas_seed"]
        print(f"  {i+1:2d} {c['candidate_id']:28s}  "
              f"atlas={s['composite_atlas_score']:+.3f}  "
              f"old={len(s['co_expression_in_old'])}/{len(TARGET_CELL_TYPES)}  "
              f"dropout={len(s['aged_dropout_cell_types'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
