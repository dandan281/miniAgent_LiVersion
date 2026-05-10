"""v40 baseline feature: atlas-class-prior co-expression heuristic.

Mirrors §3.1 of the attached methods doc — a deliberately weak first feature
that combines (i) receptor-class pairing prior + (ii) atlas DEG membership
hint. Produces non-degenerate scores without any tool calls (no required
evidence). Paper's v40 had AUROC ~0.33; we expect a similarly weak but
non-trivial baseline.

The agent's job is to add subsequent features (novelty filter, pathway
co-activation, etc.) that improve on this baseline. The "Misses and
limitations" of v40 is exactly the gap into which v4 inserts itself.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..evidence.envelope import PairEvidence
from ..pair import ReceptorPair
from ..receptor_universe import load as load_universe
from .base import Feature
from .registry import register


# Class-pair priors (symmetric). Higher = more likely to be a productive
# bispecific for muscle rejuvenation / fibroblast→muscle reprogramming.
# Encodes:
#   - BMP type-I × type-II: paper's dominant signal
#   - RTK × cytokine_adhesion: H2F + IL6ST winning pattern from v1
#   - RTK × RTK: H2F class itself
#   - TGF-β × anything: pro-fibrotic baseline (lowered)
_CLASS_PRIOR: dict[frozenset[str], float] = {
    frozenset({"bmp_type_i", "bmp_type_ii"}): 0.9,
    frozenset({"bmp_type_i", "rtk"}): 0.7,
    frozenset({"bmp_type_ii", "rtk"}): 0.7,
    frozenset({"rtk", "cytokine_adhesion"}): 0.65,
    frozenset({"rtk"}): 0.6,                          # rtk × rtk (H2F)
    frozenset({"bmp_type_i"}): 0.6,                   # bmp-i × bmp-i
    frozenset({"bmp_type_ii"}): 0.55,
    frozenset({"cytokine_adhesion"}): 0.45,
    frozenset({"bmp_type_i", "cytokine_adhesion"}): 0.45,
    frozenset({"bmp_type_ii", "cytokine_adhesion"}): 0.45,
    frozenset({"bmp_type_i", "tgfb"}): 0.4,
    frozenset({"bmp_type_ii", "tgfb"}): 0.4,
    frozenset({"rtk", "tgfb"}): 0.3,
    frozenset({"cytokine_adhesion", "tgfb"}): 0.25,
    frozenset({"tgfb"}): 0.2,
}
_DEFAULT_CLASS_PRIOR = 0.5


@lru_cache(maxsize=1)
def _atlas_membership() -> tuple[set[str], set[str]]:
    """Returns (P1_up, P2_up). Empty sets if atlas missing."""
    import json
    knowledge = Path(__file__).resolve().parent.parent.parent / "knowledge"
    for candidate in ("muscle_atlas_DE_v2_consensus.json", "muscle_atlas_DE.json"):
        p = knowledge / candidate
        if p.exists():
            atlas = json.loads(p.read_text())
            return set(atlas.get("P1_up", [])), set(atlas.get("P2_up", []))
    return set(), set()


@lru_cache(maxsize=1)
def _class_lookup() -> dict[str, str]:
    return {r.symbol: r.cls for r in load_universe().receptors}


@register
class AtlasCoexpressionFeature(Feature):
    name = "atlas_coexpression"
    version = "1.0"
    description = (
        "Class-pair prior + atlas-DEG membership bonus. Cheap baseline "
        "(no tool calls) that mirrors the paper's v40 BMP-arm heuristic."
    )
    required_evidence: tuple[str, ...] = ()  # no evidence-gather needed

    def compute(self, pair: ReceptorPair, ev: PairEvidence) -> float | None:
        cls_lookup = _class_lookup()
        cls_a = cls_lookup.get(pair.a)
        cls_b = cls_lookup.get(pair.b)
        if cls_a is None or cls_b is None:
            return None

        key = frozenset({cls_a, cls_b}) if cls_a != cls_b else frozenset({cls_a})
        prior = _CLASS_PRIOR.get(key, _DEFAULT_CLASS_PRIOR)

        # Atlas DEG membership tilts: +0.10 per receptor in P2_up,
        # -0.10 per receptor in P1_up. Keeps signal sign aligned with target.
        p1_up, p2_up = _atlas_membership()
        bonus = 0.0
        for sym in (pair.a, pair.b):
            if sym in p2_up:
                bonus += 0.10
            elif sym in p1_up:
                bonus -= 0.10

        return prior + bonus
