"""Tests for backend/scripts/atlas_seeded_candidates.py.

Focus on the pair-scoring rubric:
  - co-expression in old (primary signal, weight 0.65)
  - aged-dropout count   (rescue signal, weight 0.25)
  - asymmetry penalty    (ECD ratio > 1.78× incurs increasing penalty)
  - same-family penalty  (forced proximity adds little when natural dimers exist)

We don't run the full main(); we exercise score_pair on synthetic per-gene
expression dicts and verify the composite score moves in the expected
direction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from atlas_seeded_candidates import (  # noqa: E402
    H2F_ASYMMETRY,
    PC_THR,
    ME_THR,
    score_pair,
    already_scored_high,
    already_scored_incoherent,
)


def _expr_passing(pc=0.5, me=1.5):
    """Per-(cell_type, age_bin) record that satisfies the pc/me thresholds."""
    return {"n_cells": 100, "n_expressing": int(100 * pc), "fraction_expressing": pc, "mean_expression": me}


def _expr_failing(pc=0.05, me=0.2):
    return {"n_cells": 100, "n_expressing": int(100 * pc), "fraction_expressing": pc, "mean_expression": me}


def _build_per_ct(*, young: dict, old: dict | None = None):
    """Helper: produce a single cell-type entry with young+old slots."""
    return {
        "young": young,
        "old": old or young,
        "delta_old_minus_young": {"fraction_expressing": 0.0, "mean_expression": 0.0},
    }


# ─────────────────────────────────────────────────────────────────────────
# co-expression in old → high composite score
# ─────────────────────────────────────────────────────────────────────────
def test_co_expression_in_old_dominates_score():
    rec_A = {"symbol": "FGFR1", "family": "RTK_FGFR", "ecd_aa": 350}
    rec_B = {"symbol": "ERBB2", "family": "RTK_ErbB", "ecd_aa": 350}  # ratio 1.0 → no penalty
    expr_A = {
        "MuSC": _build_per_ct(young=_expr_passing(), old=_expr_passing()),
        "FB":   _build_per_ct(young=_expr_passing(), old=_expr_passing()),
    }
    expr_B = {
        "MuSC": _build_per_ct(young=_expr_passing(), old=_expr_passing()),
        "FB":   _build_per_ct(young=_expr_passing(), old=_expr_passing()),
    }
    s = score_pair(rec_A, rec_B, expr_A, expr_B)
    assert "MuSC" in s["co_expression_in_old"]
    assert "FB" in s["co_expression_in_old"]
    assert s["composite_atlas_score"] > 0.15
    assert s["asymmetry_penalty"] == 0.0


def test_no_atlas_data_yields_zero_score():
    rec_A = {"symbol": "FGFR1", "family": "RTK_FGFR", "ecd_aa": 350}
    rec_B = {"symbol": "ERBB2", "family": "RTK_ErbB", "ecd_aa": 630}
    s = score_pair(rec_A, rec_B, None, None)
    assert s["co_expression_in_old"] == []
    assert s["co_expression_in_young"] == []
    assert s["aged_dropout_cell_types"] == []


# ─────────────────────────────────────────────────────────────────────────
# aged dropout → moderate score, but less than full old co-expression
# ─────────────────────────────────────────────────────────────────────────
def test_aged_dropout_correctly_classified():
    rec_A = {"symbol": "EGFR", "family": "RTK_ErbB", "ecd_aa": 600}
    rec_B = {"symbol": "ERBB3", "family": "RTK_ErbB", "ecd_aa": 615}
    expr_A = {"MuSC": _build_per_ct(young=_expr_passing(), old=_expr_failing())}
    expr_B = {"MuSC": _build_per_ct(young=_expr_passing(), old=_expr_failing())}
    s = score_pair(rec_A, rec_B, expr_A, expr_B)
    assert "MuSC" in s["aged_dropout_cell_types"]
    assert "MuSC" in s["co_expression_in_young"]
    assert "MuSC" not in s["co_expression_in_old"]


def test_old_only_pass_does_not_count_as_dropout():
    rec_A = {"symbol": "X", "family": "RTK_FGFR", "ecd_aa": 350}
    rec_B = {"symbol": "Y", "family": "RTK_ErbB", "ecd_aa": 350}
    # Both expressed only in old, not young
    expr_A = {"MuSC": _build_per_ct(young=_expr_failing(), old=_expr_passing())}
    expr_B = {"MuSC": _build_per_ct(young=_expr_failing(), old=_expr_passing())}
    s = score_pair(rec_A, rec_B, expr_A, expr_B)
    assert "MuSC" in s["co_expression_in_old"]
    assert "MuSC" not in s["aged_dropout_cell_types"]


# ─────────────────────────────────────────────────────────────────────────
# asymmetry penalty
# ─────────────────────────────────────────────────────────────────────────
def test_asymmetry_penalty_zero_when_ratio_at_or_below_h2f():
    rec_A = {"symbol": "FGFR1", "family": "RTK_FGFR", "ecd_aa": 350}
    rec_B = {"symbol": "ERBB2", "family": "RTK_ErbB", "ecd_aa": 350}  # ratio 1.0
    s = score_pair(rec_A, rec_B, None, None)
    assert s["ecd_ratio"] == 1.0
    assert s["asymmetry_penalty"] == 0.0


def test_asymmetry_penalty_grows_with_ratio():
    rec_A = {"symbol": "FGFR1", "family": "RTK_FGFR", "ecd_aa": 100}
    rec_B = {"symbol": "ERBB2", "family": "RTK_ErbB", "ecd_aa": 200}  # ratio 2.0 (above 1.78)
    rec_C = {"symbol": "MET",   "family": "RTK_MET",   "ecd_aa": 350}  # ratio 3.5 (above 3.0)
    s_mild = score_pair(rec_A, rec_B, None, None)
    s_extreme = score_pair(rec_A, rec_C, None, None)
    assert s_mild["asymmetry_penalty"] > 0
    assert s_extreme["asymmetry_penalty"] >= s_mild["asymmetry_penalty"]
    assert s_extreme["asymmetry_penalty"] >= 0.30   # hard penalty kicks in


# ─────────────────────────────────────────────────────────────────────────
# same-family penalty
# ─────────────────────────────────────────────────────────────────────────
def test_same_family_pair_is_penalized():
    rec_A = {"symbol": "FGFR1", "family": "RTK_FGFR", "ecd_aa": 350}
    rec_B = {"symbol": "FGFR2", "family": "RTK_FGFR", "ecd_aa": 350}
    expr = {"MuSC": _build_per_ct(young=_expr_passing(), old=_expr_passing())}
    s_same = score_pair(rec_A, rec_B, expr, expr)
    rec_B_diff = {"symbol": "ERBB2", "family": "RTK_ErbB", "ecd_aa": 350}
    s_diff = score_pair(rec_A, rec_B_diff, expr, expr)
    assert s_same["same_family_penalty"] == 0.10
    assert s_diff["same_family_penalty"] == 0.0
    assert s_same["composite_atlas_score"] < s_diff["composite_atlas_score"]


# ─────────────────────────────────────────────────────────────────────────
# Buffer-aware skip helpers
# ─────────────────────────────────────────────────────────────────────────
def test_already_scored_high_only_returns_for_top_k_design():
    records = [
        {
            "mode": "full",
            "candidate": {"receptor_A": "ERBB2", "receptor_B": "FGFR1", "linker": "GS_med"},
            "phenotype": {"phenotype_score": 0.7},
            "decision": {"reward": 0.7, "tier": "TOP_K_DESIGN"},
        }
    ]
    assert already_scored_high(records, "ERBB2", "FGFR1", "GS_med") is True
    assert already_scored_high(records, "ERBB2", "FGFR1", "rigid_helix_40") is False
    assert already_scored_high(records, "EGFR", "MET", "GS_med") is False


def test_already_scored_incoherent_only_returns_for_incoherent():
    records = [
        {
            "mode": "full",
            "candidate": {"receptor_A": "TNFRSF1A", "receptor_B": "IL6R", "linker": "rigid_helix_40"},
            "phenotype": {"phenotype_score": -0.3},
            "decision": {"reward": -0.3, "tier": "INCOHERENT_LOG_ONLY"},
        }
    ]
    assert already_scored_incoherent(records, "TNFRSF1A", "IL6R", "rigid_helix_40") is True
    assert already_scored_incoherent(records, "TNFRSF1A", "IL6R", "GS_med") is False
