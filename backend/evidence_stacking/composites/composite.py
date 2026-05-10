"""Equal-weight additive composite scorer with per-feature min-max normalization.

No machine learning is used for the ranking itself. This mirrors §4.1 of the
attached methods doc: ranks come from a sum of [0,1]-normalized feature scores
divided by the number of present features.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..evidence.envelope import PairEvidence
from ..evidence.store import EvidenceStore
from ..features import registry
from ..features.base import Feature
from ..pair import ReceptorPair
from .loader import CompositeManifest, FeatureRef


@dataclass
class CompositeScore:
    pair_id: str
    score: float                        # mean of normalized component scores
    components: dict[str, float]        # feature_name -> normalized [0,1]
    raw: dict[str, float | None]        # feature_name -> raw value (None = missing)


def _instantiate(feature_refs: Iterable[FeatureRef]) -> list[Feature]:
    return [registry.load(ref.name) for ref in feature_refs]


def score_all(
    manifest: CompositeManifest,
    pairs: Iterable[ReceptorPair],
    *,
    store: EvidenceStore | None = None,
) -> dict[str, CompositeScore]:
    store = store or EvidenceStore()
    pairs = list(pairs)
    features = _instantiate(manifest.features)

    # Phase 1 — collect raw scores per feature across all pairs.
    raw_by_feature: dict[str, dict[str, float | None]] = {f.name: {} for f in features}
    for pair in pairs:
        ev = store.load(pair.pair_id)
        for f in features:
            raw_by_feature[f.name][pair.pair_id] = f.compute(pair, ev)

    # Phase 2 — per-feature min-max normalization.
    norm_by_feature: dict[str, dict[str, float]] = {}
    for f in features:
        norm_by_feature[f.name] = f.normalize(raw_by_feature[f.name])

    # Phase 3 — equal-weight mean per pair.
    scores: dict[str, CompositeScore] = {}
    for pair in pairs:
        components = {fname: norm_by_feature[fname][pair.pair_id] for fname in raw_by_feature}
        composite = sum(components.values()) / max(1, len(components))
        scores[pair.pair_id] = CompositeScore(
            pair_id=pair.pair_id,
            score=composite,
            components=components,
            raw={fname: raw_by_feature[fname][pair.pair_id] for fname in raw_by_feature},
        )
    return scores


def extend(parent: CompositeManifest, feature: Feature, *, stage_index: int, version: str) -> CompositeManifest:
    return CompositeManifest(
        version=version,
        parent=parent.version,
        stage_index=stage_index,
        weights=parent.weights,
        features=parent.features + [FeatureRef(name=feature.name, version=feature.version)],
        agent_rationale="",
        rho_at_commit=None,
    )
