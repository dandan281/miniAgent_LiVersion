"""
Track B (mechanism coherence) score from per-step reasoning confidences.

Plan §2.3 spec mentions noisy-OR with a chain_soundness gate at 0.10 and a
"high coherence" threshold near 0.85 for the H2F positive control. Pure product
∏ c_i over 7 steps would crush even strong chains to ~0.2, which is
inconsistent with using the same scale as a single-step confidence.

Therefore the headline `chain_soundness` returned here is the **geometric mean**
of step confidences — it lives on the same [0, 1] scale as a single step and is
directly comparable to the gate thresholds used in rl_loop. We also return the
**joint-success probability** (the strict product) for diagnostic use.

Formulas:
  c_geo  = ( ∏ c_i ) ** (1/n)              ← chain_soundness (headline)
  joint  =   ∏ c_i                          ← joint probability all steps correct
  p_fail =   1 - joint                      ← joint failure probability

H2F with 7 step confidences ≈ 0.85 → c_geo = 0.85, joint ≈ 0.32, p_fail ≈ 0.68.
A weak link (e.g. one step at 0.20) drops c_geo to ~0.65 and joint to ~0.05.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

# Ordered step keys per the COT_Rejuv_Pipeline skill (steps 1, 2, 3a-d, 4).
DEFAULT_STEP_KEYS: tuple[str, ...] = (
    "step_1", "step_2", "step_3a", "step_3b", "step_3c", "step_3d", "step_4",
)

# Default confidence for any step the agent did not report. Mid-range (0.7)
# so missing steps are penalised but not catastrophic.
DEFAULT_PRIOR_CONFIDENCE = 0.70

# A candidate with c_geo below this gate is marked INCOHERENT and not advanced.
# Per plan v2: top-K ranking, no binary gate at the reward level — but if
# mechanism is below 0.30 average, the chain is too weak to bother.
DEFAULT_INCOHERENT_GATE = 0.30


def chain_soundness(
    step_confidences: Mapping[str, float] | None,
    *,
    expected_keys: tuple[str, ...] = DEFAULT_STEP_KEYS,
    prior: float = DEFAULT_PRIOR_CONFIDENCE,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """
    Compute chain_soundness (geometric mean) and joint-success probability
    from a dict of per-step confidences in [0, 1].

    Args:
        step_confidences: dict like {"step_1": 0.8, "step_3a": 0.75, ...}
        expected_keys:    full ordered list of steps that should be present
        prior:            default for any missing step (default 0.70)
        weights:          optional per-step weights (default: equal). When
                          provided, GM is replaced by a weighted geometric mean:
                            c_geo = exp( Σ w_i log c_i  /  Σ w_i )

    Returns dict with keys:
        chain_soundness   geometric mean of step confidences (∈ [0, 1])
        joint_probability strict product (joint correctness probability)
        p_fail_total      1 - joint_probability
        min_step          (key, value) of weakest link
        max_step          (key, value) of strongest link
        n_steps           number of steps aggregated
        n_missing         how many used the prior
        per_step          full c_i used after fill
    """
    confs = dict(step_confidences or {})
    full: dict[str, float] = {}
    n_missing = 0
    eps = 1e-9
    for k in expected_keys:
        v = confs.get(k)
        if v is None:
            full[k] = prior
            n_missing += 1
        else:
            full[k] = float(v)

    # Clamp to (eps, 1] to avoid log(0)
    full = {k: max(eps, min(1.0, v)) for k, v in full.items()}

    # Joint probability (strict product)
    joint = 1.0
    for v in full.values():
        joint *= v

    # Geometric mean (weighted if requested)
    n = len(full)
    if not n:
        return {
            "chain_soundness": 0.0, "joint_probability": 0.0,
            "p_fail_total": 1.0, "min_step": ("", 0.0), "max_step": ("", 0.0),
            "n_steps": 0, "n_missing": 0, "per_step": {},
        }
    if weights is None:
        log_sum = sum(math.log(v) for v in full.values())
        c_geo = math.exp(log_sum / n)
    else:
        wsum = 0.0
        log_sum = 0.0
        for k, v in full.items():
            w = float(weights.get(k, 1.0))
            wsum += w
            log_sum += w * math.log(v)
        c_geo = math.exp(log_sum / wsum) if wsum > 0 else 0.0

    items_sorted = sorted(full.items(), key=lambda kv: kv[1])
    min_step = items_sorted[0]
    max_step = items_sorted[-1]

    return {
        "chain_soundness":   max(0.0, min(1.0, c_geo)),
        "joint_probability": max(0.0, min(1.0, joint)),
        "p_fail_total":      1.0 - max(0.0, min(1.0, joint)),
        "min_step":          min_step,
        "max_step":          max_step,
        "n_steps":           n,
        "n_missing":         n_missing,
        "per_step":          full,
    }


def is_incoherent(chain_score: float, threshold: float = DEFAULT_INCOHERENT_GATE) -> bool:
    """Below this threshold, mechanism is too weak to be meaningful."""
    return chain_score < threshold


def format_chain_summary(result: dict[str, Any]) -> str:
    cs = result["chain_soundness"]
    jp = result["joint_probability"]
    mins = result["min_step"]
    maxs = result["max_step"]
    nm = result["n_missing"]
    n = result["n_steps"]
    return (
        f"chain_soundness (geom mean): {cs:.4f}   joint_prob: {jp:.4f}\n"
        f"  weakest: {mins[0]} = {mins[1]:.3f}\n"
        f"  strongest: {maxs[0]} = {maxs[1]:.3f}\n"
        f"  steps: {n}  ({nm} used prior {DEFAULT_PRIOR_CONFIDENCE})\n"
        f"  p_fail (any step wrong): {result['p_fail_total']:.4f}"
    )
