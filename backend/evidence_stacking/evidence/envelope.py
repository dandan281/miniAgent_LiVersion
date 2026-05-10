"""PairEvidence — per-pair dict of evidence keys -> tool results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PairEvidence:
    """Evidence collected for one ReceptorPair across one or more tool calls.

    Keys are short stable identifiers like ``atlas_co_old``, ``pubmed_cocite``,
    ``reactome_pathways_a``. Each feature declares the keys it reads in
    ``Feature.required_evidence``. Values are JSON-serialisable.
    """

    pair_id: str
    data: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)

    def has(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def put(self, key: str, value: Any, *, source: str, version: str = "1") -> None:
        self.data[key] = value
        self.provenance[key] = {"source": source, "version": version}

    def keys(self) -> set[str]:
        return set(self.data.keys())

    def to_dict(self) -> dict[str, Any]:
        return {"pair_id": self.pair_id, "data": self.data, "provenance": self.provenance}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PairEvidence":
        return cls(
            pair_id=raw["pair_id"],
            data=dict(raw.get("data", {})),
            provenance=dict(raw.get("provenance", {})),
        )
