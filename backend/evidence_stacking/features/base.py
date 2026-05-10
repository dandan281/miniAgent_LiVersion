"""Feature ABC — pure transform from PairEvidence to a [0,1] score."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..evidence.envelope import PairEvidence
from ..pair import ReceptorPair


class Feature(ABC):
    """Subclasses set ``name``, ``version``, and ``required_evidence`` as class vars."""

    name: ClassVar[str]
    version: ClassVar[str] = "1.0"
    description: ClassVar[str] = ""
    required_evidence: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def compute(self, pair: ReceptorPair, ev: PairEvidence) -> float | None:
        """Return raw score for the pair; None means missing evidence."""

    def normalize(self, scores: dict[str, float | None]) -> dict[str, float]:
        """Default min-max to [0,1]. None values map to 0.0."""
        present = [s for s in scores.values() if s is not None]
        if not present:
            return {k: 0.0 for k in scores}
        lo, hi = min(present), max(present)
        if hi == lo:
            return {k: 0.5 if scores[k] is not None else 0.0 for k in scores}
        return {
            k: ((s - lo) / (hi - lo)) if s is not None else 0.0
            for k, s in scores.items()
        }

    def provenance(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "required_evidence": list(self.required_evidence),
        }

    def cache_key(self, pair: ReceptorPair) -> str:
        return f"{self.name}@{self.version}::{pair.pair_id}"
