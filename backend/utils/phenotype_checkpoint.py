"""
Track A scoring: compare a candidate's predicted gene signature against the
muscle aging atlas reference (muscle_atlas_DE.json).

A novokine "rejuvenates" if its predicted up-regulated genes overlap with the
P2_up reference (young-enriched) AND its predicted down-regulated genes overlap
with the P1_up reference (aged-enriched).

  predicted UP  vs  P2_up  (young-enriched)  → reward this overlap
  predicted DOWN vs P1_up  (aged-enriched)   → reward this overlap
  predicted UP  vs  P1_up  (aged-enriched)   → penalize (anti-rejuvenation)
  predicted DOWN vs P2_up  (young-enriched)  → penalize

Outputs Fisher exact p-values, odds ratios, Jaccard indices, and a single
composite phenotype_score in [-1, +1].

Usage:
    from utils.phenotype_checkpoint import score_phenotype
    result = score_phenotype(
        predicted_up=["MYH2", "MYH7", "TNNT3", ...],
        predicted_down=["EGR1", "IL32", "TXNIP", ...],
        cell_type="MuSC",  # or None to use pooled atlas
    )
    # → {"phenotype_score": +0.42, "P2_score": ..., "P1_score": ...,
    #    "fisher_p2_up": (odds, p), "fisher_p1_up": (odds, p), ...}
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal, Optional

from scipy.stats import fisher_exact

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
ATLAS_PATHS: dict[str, Path] = {
    "v1": _KNOWLEDGE_DIR / "muscle_atlas_DE.json",
    "v2": _KNOWLEDGE_DIR / "muscle_atlas_DE_v2_consensus.json",
}
DEFAULT_ATLAS_VERSION: Literal["v1", "v2"] = "v1"
DEFAULT_ATLAS_PATH = ATLAS_PATHS[DEFAULT_ATLAS_VERSION]


def _resolve_atlas_path(
    atlas_version: Optional[Literal["v1", "v2"]],
    atlas_path: Optional[Path],
) -> Path:
    """Pick the atlas JSON path. Explicit atlas_path wins, else atlas_version,
    else the v1 default. Errors if both are supplied with conflicting values."""
    if atlas_path is not None:
        return Path(atlas_path)
    if atlas_version is None:
        atlas_version = DEFAULT_ATLAS_VERSION
    if atlas_version not in ATLAS_PATHS:
        raise ValueError(
            f"Unknown atlas_version {atlas_version!r}; expected one of {sorted(ATLAS_PATHS)}"
        )
    return ATLAS_PATHS[atlas_version]

# Gene universe size — rough proxy for the protein-coding genome the atlas
# tested. Used as the denominator for Fisher exact test contingency tables.
# Human protein-coding genes ≈ 19,500–20,000.
DEFAULT_UNIVERSE_SIZE = 20_000

# Minimum overlap to be statistically meaningful — avoid spurious 1-vs-1 hits
MIN_OVERLAP_FOR_FISHER = 2


def _load_atlas(
    path: Path | None = None,
    atlas_version: Optional[Literal["v1", "v2"]] = None,
) -> dict[str, Any]:
    p = _resolve_atlas_path(atlas_version, path)
    if not p.exists():
        raise FileNotFoundError(
            f"Atlas JSON not found at {p}. "
            f"For v2, run `python backend/scripts/build_consensus_atlas.py` first."
        )
    with open(p) as f:
        return json.load(f)


def _normalize_gene_set(genes: list[str] | set[str] | None) -> set[str]:
    """Uppercase HGNC symbols, strip whitespace, drop empties."""
    if not genes:
        return set()
    return {g.strip().upper() for g in genes if g and g.strip()}


def _resolve_reference_sets(
    atlas: dict[str, Any], cell_type: Optional[str]
) -> tuple[set[str], set[str], str]:
    """
    Return (P1_up_ref, P2_up_ref, label) for the requested cell type.
    cell_type=None or 'pooled' → use top-level pooled lists.
    cell_type='MuSC'/'Myofiber'/etc → use per-cell-type lists.
    cell_type='FAP' → use FAP_P1_up / FAP_P2_up (fibroblast-lineage).
    """
    if cell_type is None or cell_type.lower() == "pooled":
        return (
            _normalize_gene_set(atlas.get("P1_up", [])),
            _normalize_gene_set(atlas.get("P2_up", [])),
            "pooled",
        )
    if cell_type.upper() == "FAP":
        return (
            _normalize_gene_set(atlas.get("FAP_P1_up", [])),
            _normalize_gene_set(atlas.get("FAP_P2_up", [])),
            "FAP",
        )
    pct = atlas.get("per_cell_type", {})
    if cell_type in pct:
        node = pct[cell_type]
        return (
            _normalize_gene_set(node.get("P1_up", [])),
            _normalize_gene_set(node.get("P2_up", [])),
            cell_type,
        )
    available = list(pct.keys()) + ["pooled", "FAP"]
    raise ValueError(f"Unknown cell_type '{cell_type}'. Available: {available}")


def fisher_exact_overlap(
    predicted: set[str], reference: set[str], universe_size: int
) -> dict[str, Any]:
    """
    Two-sided Fisher exact test for over-representation.

    Contingency table:
                       in_reference   not_in_reference
        predicted      a              b
        not_predicted  c              d

    where a + b = |predicted|, a + c = |reference|, a+b+c+d = universe.
    """
    a = len(predicted & reference)
    b = len(predicted - reference)
    c = len(reference - predicted)
    d = max(0, universe_size - a - b - c)

    if a < MIN_OVERLAP_FOR_FISHER:
        # Too few overlaps for the test to be informative; return p=1.0
        return {
            "overlap": a,
            "predicted_size": len(predicted),
            "reference_size": len(reference),
            "odds_ratio": 0.0,
            "p_value": 1.0,
            "neg_log10_p": 0.0,
            "table": [[a, b], [c, d]],
        }

    odds, p = fisher_exact([[a, b], [c, d]], alternative="greater")
    neg_log10_p = -math.log10(p) if p > 0 else float("inf")
    return {
        "overlap": a,
        "predicted_size": len(predicted),
        "reference_size": len(reference),
        "odds_ratio": float(odds) if math.isfinite(odds) else float("inf"),
        "p_value": float(p),
        "neg_log10_p": float(neg_log10_p) if math.isfinite(neg_log10_p) else 999.0,
        "table": [[a, b], [c, d]],
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score_component(fisher_result: dict[str, Any]) -> float:
    """
    Map a Fisher result to a [0, 1] score. Uses neg_log10_p capped at 10
    (i.e. p=1e-10 → score 1.0). Score 0 means p≥1.
    """
    nlp = fisher_result["neg_log10_p"]
    if nlp <= 0:
        return 0.0
    return min(1.0, nlp / 10.0)


def score_phenotype(
    predicted_up: list[str] | set[str] | None,
    predicted_down: list[str] | set[str] | None,
    cell_type: Optional[str] = None,
    atlas_path: Path | None = None,
    universe_size: int = DEFAULT_UNIVERSE_SIZE,
    atlas_version: Optional[Literal["v1", "v2"]] = None,
) -> dict[str, Any]:
    """
    Score a predicted gene signature against the muscle aging atlas.

    Returns a dict with:
      phenotype_score : float in [-1, +1]   (positive = rejuvenating)
      P2_score        : float in [0, 1]     (predicted up matches young-enriched)
      P1_score        : float in [0, 1]     (predicted down matches aged-enriched — anti-aged)
      penalty_up_aged   : float in [0, 1]   (predicted up matches aged genes — bad)
      penalty_down_young: float in [0, 1]   (predicted down matches young genes — bad)
      jaccard_*       : raw Jaccard overlaps
      fisher_*        : full Fisher exact result dicts
      reference_label : which atlas slice was used
      verdict         : "REJUVENATING" / "ANTI-REJUVENATING" / "NEUTRAL"
    """
    atlas = _load_atlas(atlas_path, atlas_version=atlas_version)
    P1_up, P2_up, label = _resolve_reference_sets(atlas, cell_type)
    resolved_version = atlas.get("version", "v1")
    label = f"{label}|atlas={resolved_version}"

    pred_up = _normalize_gene_set(predicted_up)
    pred_down = _normalize_gene_set(predicted_down)

    if not pred_up and not pred_down:
        return {
            "phenotype_score": 0.0,
            "verdict": "EMPTY",
            "warning": "no genes provided",
            "reference_label": label,
        }

    # Rejuvenating signals
    f_up_vs_p2   = fisher_exact_overlap(pred_up, P2_up, universe_size)   # +
    f_down_vs_p1 = fisher_exact_overlap(pred_down, P1_up, universe_size) # +
    # Anti-rejuvenating signals
    f_up_vs_p1   = fisher_exact_overlap(pred_up, P1_up, universe_size)   # -
    f_down_vs_p2 = fisher_exact_overlap(pred_down, P2_up, universe_size) # -

    P2_score          = _score_component(f_up_vs_p2)
    P1_score          = _score_component(f_down_vs_p1)
    penalty_up_aged   = _score_component(f_up_vs_p1)
    penalty_down_young = _score_component(f_down_vs_p2)

    # Composite: rejuvenating contributions minus anti-rejuvenating
    # Each side averaged so a candidate predicting only UP genes can still score.
    pos = (P2_score + P1_score) / 2.0
    neg = (penalty_up_aged + penalty_down_young) / 2.0
    phenotype_score = max(-1.0, min(1.0, pos - neg))

    # Verdict
    if phenotype_score > 0.3 and pos > 2 * neg:
        verdict = "REJUVENATING"
    elif phenotype_score < -0.3 and neg > 2 * pos:
        verdict = "ANTI-REJUVENATING"
    else:
        verdict = "NEUTRAL"

    return {
        "phenotype_score":     phenotype_score,
        "verdict":             verdict,
        "P2_score":            P2_score,
        "P1_score":            P1_score,
        "penalty_up_aged":     penalty_up_aged,
        "penalty_down_young":  penalty_down_young,
        "pos_total":           pos,
        "neg_total":           neg,
        "jaccard_up_vs_p2":    jaccard(pred_up, P2_up),
        "jaccard_down_vs_p1":  jaccard(pred_down, P1_up),
        "jaccard_up_vs_p1":    jaccard(pred_up, P1_up),
        "jaccard_down_vs_p2":  jaccard(pred_down, P2_up),
        "fisher_up_vs_p2":     f_up_vs_p2,
        "fisher_down_vs_p1":   f_down_vs_p1,
        "fisher_up_vs_p1":     f_up_vs_p1,
        "fisher_down_vs_p2":   f_down_vs_p2,
        "reference_label":     label,
        "n_predicted_up":      len(pred_up),
        "n_predicted_down":    len(pred_down),
        "universe_size":       universe_size,
    }


def format_score_summary(result: dict[str, Any]) -> str:
    """Human-readable summary for the agent / experience buffer."""
    if result.get("verdict") == "EMPTY":
        return "[EMPTY] No genes provided to score."
    lines = [
        f"Phenotype score: {result['phenotype_score']:+.4f}   verdict: {result['verdict']}",
        f"  reference slice: {result['reference_label']}",
        f"  rejuvenating signal:  P2_score={result['P2_score']:.3f}  P1_score={result['P1_score']:.3f}  → pos={result['pos_total']:.3f}",
        f"  anti-rejuv penalty:   up-vs-aged={result['penalty_up_aged']:.3f}  down-vs-young={result['penalty_down_young']:.3f}  → neg={result['neg_total']:.3f}",
        "",
        f"  predicted up   ({result['n_predicted_up']} genes):",
        f"    vs P2_up (young, target):  overlap={result['fisher_up_vs_p2']['overlap']}/{result['fisher_up_vs_p2']['reference_size']}  "
        f"odds={result['fisher_up_vs_p2']['odds_ratio']:.2f}  p={result['fisher_up_vs_p2']['p_value']:.2e}",
        f"    vs P1_up (aged, penalty):  overlap={result['fisher_up_vs_p1']['overlap']}/{result['fisher_up_vs_p1']['reference_size']}  "
        f"odds={result['fisher_up_vs_p1']['odds_ratio']:.2f}  p={result['fisher_up_vs_p1']['p_value']:.2e}",
        "",
        f"  predicted down ({result['n_predicted_down']} genes):",
        f"    vs P1_up (aged, target):   overlap={result['fisher_down_vs_p1']['overlap']}/{result['fisher_down_vs_p1']['reference_size']}  "
        f"odds={result['fisher_down_vs_p1']['odds_ratio']:.2f}  p={result['fisher_down_vs_p1']['p_value']:.2e}",
        f"    vs P2_up (young, penalty): overlap={result['fisher_down_vs_p2']['overlap']}/{result['fisher_down_vs_p2']['reference_size']}  "
        f"odds={result['fisher_down_vs_p2']['odds_ratio']:.2f}  p={result['fisher_down_vs_p2']['p_value']:.2e}",
    ]
    return "\n".join(lines)
