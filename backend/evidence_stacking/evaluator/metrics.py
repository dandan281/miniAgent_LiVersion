"""Spearman rho, top-K precision/recall, top-disagreement extraction.

No AUROC, no Youden J — there are no binary labels in v2. The gate signal is
``aged_young`` and ``fibro_muscle`` atlas reward, which is continuous in [-1, 1].
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class MetricsBundle:
    rho: float
    p_at_10: float
    p_at_50: float
    r_at_10: float
    r_at_50: float
    top_disagreements: list[tuple[str, float, float]]  # (pair_id, score, target)


def _ranks(values: list[float]) -> list[float]:
    """Average-rank handling of ties."""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg
        i = j + 1
    return ranks


def spearman(scores: Mapping[str, float], target: Mapping[str, float]) -> float:
    keys = [k for k in scores if k in target]
    if len(keys) < 3:
        return 0.0
    s = [scores[k] for k in keys]
    t = [target[k] for k in keys]
    rs = _ranks(s)
    rt = _ranks(t)
    n = len(keys)
    ms, mt = sum(rs) / n, sum(rt) / n
    num = sum((rs[i] - ms) * (rt[i] - mt) for i in range(n))
    den_s = sum((rs[i] - ms) ** 2 for i in range(n)) ** 0.5
    den_t = sum((rt[i] - mt) ** 2 for i in range(n)) ** 0.5
    if den_s == 0 or den_t == 0:
        return 0.0
    return num / (den_s * den_t)


def precision_recall_at_k(
    scores: Mapping[str, float],
    target: Mapping[str, float],
    k: int,
    *,
    target_quantile: float = 0.9,
) -> tuple[float, float]:
    """Treats top-quantile of target as the relevant set."""
    keys = [k_ for k_ in scores if k_ in target]
    if not keys:
        return 0.0, 0.0
    sorted_targets = sorted(target[k_] for k_ in keys)
    cutoff = sorted_targets[int(target_quantile * len(sorted_targets))]
    relevant = {k_ for k_ in keys if target[k_] >= cutoff}
    if not relevant:
        return 0.0, 0.0
    top_k = sorted(keys, key=lambda x: scores[x], reverse=True)[:k]
    hits = sum(1 for k_ in top_k if k_ in relevant)
    return hits / k, hits / len(relevant)


def top_disagreements(
    scores: Mapping[str, float],
    target: Mapping[str, float],
    n: int = 5,
) -> list[tuple[str, float, float]]:
    """Returns pair_ids where (rank_score - rank_target) is largest in either direction."""
    keys = [k for k in scores if k in target]
    if not keys:
        return []
    s_ranks = dict(zip(keys, _ranks([scores[k] for k in keys])))
    t_ranks = dict(zip(keys, _ranks([target[k] for k in keys])))
    deltas = sorted(
        ((k, s_ranks[k] - t_ranks[k]) for k in keys),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )
    return [(k, scores[k], target[k]) for k, _ in deltas[:n]]


def metrics_bundle(scores: Mapping[str, float], target: Mapping[str, float]) -> MetricsBundle:
    p10, r10 = precision_recall_at_k(scores, target, 10)
    p50, r50 = precision_recall_at_k(scores, target, 50)
    return MetricsBundle(
        rho=spearman(scores, target),
        p_at_10=p10,
        p_at_50=p50,
        r_at_10=r10,
        r_at_50=r50,
        top_disagreements=top_disagreements(scores, target, n=5),
    )
