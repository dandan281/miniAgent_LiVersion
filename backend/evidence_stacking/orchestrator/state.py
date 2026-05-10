"""RunLedger — append-only JSONL of stage commits + rejections."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..composites.loader import CompositeManifest


_DEFAULT_LEDGER = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "dev"
    / "v2_run_ledger.jsonl"
)


@dataclass
class StageRecord:
    stage_index: int
    feature_name: str
    composite_version: str
    decision: str  # "KEEP" | "DROP"
    rho: dict[str, float] = field(default_factory=dict)
    deltas: dict[str, float] = field(default_factory=dict)
    report_path: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class RunLedger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _DEFAULT_LEDGER
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[StageRecord] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.records.append(StageRecord(**json.loads(line)))

    @property
    def stage_index(self) -> int:
        keep_records = [r for r in self.records if r.decision == "KEEP"]
        return len(keep_records)

    def latest_kept(self) -> StageRecord | None:
        for r in reversed(self.records):
            if r.decision == "KEEP":
                return r
        return None

    def latest_rho(self) -> dict[str, float]:
        last = self.latest_kept()
        return dict(last.rho) if last else {}

    def fail_streak(self) -> int:
        streak = 0
        for r in reversed(self.records):
            if r.decision == "DROP":
                streak += 1
            else:
                break
        return streak

    def append(
        self,
        *,
        stage_index: int,
        feature_name: str,
        composite_version: str,
        decision: str,
        rho: dict[str, float],
        deltas: dict[str, float],
        report_path: str,
    ) -> StageRecord:
        rec = StageRecord(
            stage_index=stage_index,
            feature_name=feature_name,
            composite_version=composite_version,
            decision=decision,
            rho=rho,
            deltas=deltas,
            report_path=report_path,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.records.append(rec)
        with self.path.open("a") as f:
            f.write(json.dumps(rec.to_dict()) + "\n")
        return rec
