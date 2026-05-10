"""Keep/drop rule for the evidence-stacking pipeline."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class RetentionDecision:
    keep: bool
    deltas: dict[str, float]
    reason: str


def decide(
    prev_rho: Mapping[str, float],
    new_rho: Mapping[str, float],
    *,
    degrade_tol: float = 0.05,
) -> RetentionDecision:
    """KEEP iff max(Δρ) > 0 AND min(Δρ) > -degrade_tol.

    Mirrors §4.3 of the methods doc:
        "A feature was retained if it improved [the metric] on at least one
        label set without reducing the other by more than 0.05."
    """
    targets = sorted(set(prev_rho) | set(new_rho))
    deltas = {t: new_rho.get(t, 0.0) - prev_rho.get(t, 0.0) for t in targets}
    if not deltas:
        return RetentionDecision(keep=False, deltas={}, reason="no targets")
    max_d = max(deltas.values())
    min_d = min(deltas.values())
    if max_d > 0 and min_d > -degrade_tol:
        return RetentionDecision(
            keep=True,
            deltas=deltas,
            reason=f"max(Δρ)={max_d:+.3f} > 0 and min(Δρ)={min_d:+.3f} > {-degrade_tol:+.3f}",
        )
    return RetentionDecision(
        keep=False,
        deltas=deltas,
        reason=f"max(Δρ)={max_d:+.3f}, min(Δρ)={min_d:+.3f} (need max>0 and min>{-degrade_tol:+.3f})",
    )
