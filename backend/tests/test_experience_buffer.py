"""Tests for backend/utils/experience_buffer.py.

Pure-Python tests; no network calls, no agent invocation. All buffer files
are written to tmp_path and loaded explicitly so we never touch the real
backend/knowledge/experience_buffer.jsonl during a test run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.experience_buffer import (  # noqa: E402
    bottom_k_failures,
    format_pair_cache_block,
    format_priors_block,
    load_buffer,
    lookup_by_pair,
    pair_key,
    top_k_rejuvenating,
)


# ─────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────
def _record(
    *,
    rA: str,
    rB: str,
    linker: str = "GS_med",
    reward: float = 0.5,
    tier: str = "MIDDLE_HUMAN_REVIEW",
    verdict: str = "NEUTRAL",
    mode: str = "full",
    iteration: int = 0,
    predicted_up: list[str] | None = None,
    predicted_down: list[str] | None = None,
) -> dict:
    return {
        "iteration": iteration,
        "iteration_id": f"iter-{iteration}-{rA}-{rB}",
        "timestamp": "2026-05-04T12:00:00Z",
        "mode": mode,
        "candidate": {
            "candidate_id": f"{rA}_{rB}_{linker}",
            "receptor_A": rA,
            "receptor_B": rB,
            "linker": linker,
            "predicted_up": predicted_up or [],
            "predicted_down": predicted_down or [],
            "biased_output": {
                "transphosphorylation_adaptors": ["GRB2"],
                "cis_adaptors": [],
                "excluded_adaptors": ["PLCG1"],
            },
            "chain_soundness": 0.7,
        },
        "phenotype": {"phenotype_score": reward, "verdict": verdict},
        "decision": {"reward": reward, "tier": tier, "verdict": verdict},
    }


def _write_buffer(path: Path, records: list[dict]) -> None:
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


# ─────────────────────────────────────────────────────────────────────────
# pair_key
# ─────────────────────────────────────────────────────────────────────────
def test_pair_key_order_invariant():
    assert pair_key("ERBB2", "FGFR1") == pair_key("FGFR1", "ERBB2")
    assert pair_key("erbb2", "fgfr1") == pair_key("ERBB2", "FGFR1")  # case insensitive


def test_pair_key_with_linker():
    k1 = pair_key("ERBB2", "FGFR1", "flexible_GS4")
    k2 = pair_key("FGFR1", "ERBB2", "flexible_GS4")
    assert k1 == k2
    # different linker = different key
    assert pair_key("ERBB2", "FGFR1", "rigid_helix_40") != k1


def test_pair_key_order_invariance_can_be_disabled():
    k1 = pair_key("ERBB2", "FGFR1", order_invariant=False)
    k2 = pair_key("FGFR1", "ERBB2", order_invariant=False)
    assert k1 != k2


# ─────────────────────────────────────────────────────────────────────────
# load_buffer
# ─────────────────────────────────────────────────────────────────────────
def test_load_buffer_missing_file_returns_empty(tmp_path):
    p = tmp_path / "does_not_exist.jsonl"
    assert load_buffer(p) == []


def test_load_buffer_skips_malformed_lines(tmp_path):
    p = tmp_path / "buf.jsonl"
    valid = _record(rA="ERBB2", rB="FGFR1", reward=0.7, tier="TOP_K_DESIGN", verdict="REJUVENATING")
    with p.open("w") as f:
        f.write(json.dumps(valid) + "\n")
        f.write("this is not json\n")
        f.write("\n")
        f.write(json.dumps({"random_other": "obj"}) + "\n")
    records = load_buffer(p)
    assert len(records) == 2  # valid + the random_other dict (still a dict)
    assert records[0]["candidate"]["receptor_A"] == "ERBB2"


# ─────────────────────────────────────────────────────────────────────────
# lookup_by_pair
# ─────────────────────────────────────────────────────────────────────────
def test_lookup_by_pair_returns_highest_reward(tmp_path):
    records = [
        _record(rA="ERBB2", rB="FGFR1", reward=0.3, iteration=1),
        _record(rA="ERBB2", rB="FGFR1", reward=0.8, iteration=2, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="ERBB2", rB="FGFR1", reward=0.5, iteration=3),
    ]
    hit = lookup_by_pair(records, "ERBB2", "FGFR1")
    assert hit is not None
    assert (hit["decision"] or {}).get("reward") == 0.8


def test_lookup_by_pair_order_invariant(tmp_path):
    records = [_record(rA="ERBB2", rB="FGFR1", reward=0.7)]
    assert lookup_by_pair(records, "ERBB2", "FGFR1") is not None
    assert lookup_by_pair(records, "FGFR1", "ERBB2") is not None


def test_lookup_by_pair_linker_is_strict():
    """Linker is part of the key when supplied; mismatch = miss."""
    records = [_record(rA="ERBB2", rB="FGFR1", linker="GS_med")]
    assert lookup_by_pair(records, "ERBB2", "FGFR1", "GS_med") is not None
    assert lookup_by_pair(records, "ERBB2", "FGFR1", "rigid_helix_40") is None


def test_lookup_by_pair_excludes_score_only_by_default():
    records = [_record(rA="ERBB2", rB="FGFR1", reward=0.9, mode="score_only")]
    assert lookup_by_pair(records, "ERBB2", "FGFR1") is None
    assert lookup_by_pair(records, "ERBB2", "FGFR1", require_full_mode=False) is not None


def test_lookup_by_pair_min_reward_filter():
    records = [_record(rA="ERBB2", rB="FGFR1", reward=0.2)]
    assert lookup_by_pair(records, "ERBB2", "FGFR1", min_reward=0.5) is None
    assert lookup_by_pair(records, "ERBB2", "FGFR1", min_reward=0.1) is not None


# ─────────────────────────────────────────────────────────────────────────
# top_k_rejuvenating / bottom_k_failures
# ─────────────────────────────────────────────────────────────────────────
def test_top_k_rejuvenating_returns_only_rejuvenating_verdict():
    records = [
        _record(rA="A", rB="B", reward=0.9, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="C", rB="D", reward=0.8, tier="MIDDLE_HUMAN_REVIEW", verdict="NEUTRAL"),
        _record(rA="E", rB="F", reward=0.7, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
    ]
    top = top_k_rejuvenating(records, k=5)
    pairs = [(r["candidate"]["receptor_A"], r["candidate"]["receptor_B"]) for r in top]
    assert ("A", "B") in pairs
    assert ("E", "F") in pairs
    assert ("C", "D") not in pairs   # not REJUVENATING verdict


def test_top_k_rejuvenating_dedupes_by_pair():
    records = [
        _record(rA="A", rB="B", reward=0.9, iteration=1, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="A", rB="B", reward=0.85, iteration=2, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="C", rB="D", reward=0.7, iteration=3, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
    ]
    top = top_k_rejuvenating(records, k=5)
    pairs = [(r["candidate"]["receptor_A"], r["candidate"]["receptor_B"]) for r in top]
    # A+B should appear at most once
    assert pairs.count(("A", "B")) == 1
    assert ("C", "D") in pairs


def test_top_k_rejuvenating_sorted_by_reward_desc():
    records = [
        _record(rA="A", rB="B", reward=0.5, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="C", rB="D", reward=0.9, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
        _record(rA="E", rB="F", reward=0.7, tier="TOP_K_DESIGN", verdict="REJUVENATING"),
    ]
    top = top_k_rejuvenating(records, k=3)
    rewards = [(r.get("decision") or {}).get("reward") for r in top]
    assert rewards == sorted(rewards, reverse=True)


def test_bottom_k_failures_only_includes_failure_tiers():
    records = [
        _record(rA="A", rB="B", reward=-0.5, tier="INCOHERENT_LOG_ONLY", verdict="ANTI-REJUVENATING"),
        _record(rA="C", rB="D", reward=0.3, tier="MIDDLE_HUMAN_REVIEW", verdict="NEUTRAL"),
        _record(rA="E", rB="F", reward=-0.1, tier="BOTTOM_LOG_ONLY", verdict="NEUTRAL"),
    ]
    bot = bottom_k_failures(records, k=5)
    pairs = [(r["candidate"]["receptor_A"], r["candidate"]["receptor_B"]) for r in bot]
    assert ("A", "B") in pairs
    assert ("E", "F") in pairs
    assert ("C", "D") not in pairs   # MIDDLE_HUMAN_REVIEW is not a failure tier


def test_bottom_k_failures_sorted_by_reward_asc():
    records = [
        _record(rA="A", rB="B", reward=-0.1, tier="BOTTOM_LOG_ONLY"),
        _record(rA="C", rB="D", reward=-0.5, tier="BOTTOM_LOG_ONLY"),
    ]
    bot = bottom_k_failures(records, k=5)
    rewards = [(r.get("decision") or {}).get("reward") for r in bot]
    assert rewards == sorted(rewards)   # ascending: most negative first


# ─────────────────────────────────────────────────────────────────────────
# format_priors_block / format_pair_cache_block
# ─────────────────────────────────────────────────────────────────────────
def test_format_priors_block_empty_returns_empty_string():
    assert format_priors_block([], []) == ""


def test_format_priors_block_includes_pair_and_genes():
    rec = _record(
        rA="ERBB2", rB="FGFR1",
        reward=0.7, tier="TOP_K_DESIGN", verdict="REJUVENATING",
        predicted_up=["MYH7", "ACTA1"], predicted_down=["EGR1", "JUN"],
    )
    block = format_priors_block([rec], [])
    assert "ERBB2+FGFR1" in block
    assert "MYH7" in block and "EGR1" in block
    assert "+0.700" in block or "0.700" in block


def test_format_pair_cache_block_handles_missing_reward():
    rec = _record(rA="A", rB="B")
    rec["decision"] = {}  # no reward
    note = format_pair_cache_block(rec)
    assert "A+B" in note
    assert "reward" in note  # mentions reward even if unavailable
