"""On-disk evidence cache — one JSON file per pair, sharded by first letter."""
from __future__ import annotations

import json
from pathlib import Path

from .envelope import PairEvidence


_DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "knowledge" / "evidence_cache"


class EvidenceStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, pair_id: str) -> Path:
        shard = pair_id[0].upper() if pair_id else "_"
        d = self.root / shard
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{pair_id}.json"

    def load(self, pair_id: str) -> PairEvidence:
        p = self._path(pair_id)
        if not p.exists():
            return PairEvidence(pair_id=pair_id)
        return PairEvidence.from_dict(json.loads(p.read_text()))

    def save(self, ev: PairEvidence) -> None:
        self._path(ev.pair_id).write_text(json.dumps(ev.to_dict(), indent=2, sort_keys=True))

    def keys_for(self, pair_id: str) -> set[str]:
        return self.load(pair_id).keys()
