"""Composite manifest loader."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


_DIR = Path(__file__).resolve().parent


@dataclass
class FeatureRef:
    name: str
    version: str


@dataclass
class CompositeManifest:
    version: str
    parent: str | None
    stage_index: int
    weights: str  # "equal" or "logistic_fit"
    features: list[FeatureRef]
    agent_rationale: str = ""
    rho_at_commit: dict[str, float] | None = None
    raw: dict | None = None


def load(version: str, dir_: Path | None = None) -> CompositeManifest:
    p = (dir_ or _DIR) / f"{version}.json"
    raw = json.loads(p.read_text())
    return CompositeManifest(
        version=raw["version"],
        parent=raw.get("parent"),
        stage_index=int(raw["stage_index"]),
        weights=raw.get("weights", "equal"),
        features=[FeatureRef(name=f["name"], version=f.get("version", "1.0")) for f in raw["features"]],
        agent_rationale=raw.get("agent_rationale", ""),
        rho_at_commit=raw.get("rho_at_commit"),
        raw=raw,
    )


def save(manifest: CompositeManifest, dir_: Path | None = None) -> Path:
    p = (dir_ or _DIR) / f"{manifest.version}.json"
    payload = {
        "version": manifest.version,
        "parent": manifest.parent,
        "stage_index": manifest.stage_index,
        "weights": manifest.weights,
        "features": [{"name": f.name, "version": f.version} for f in manifest.features],
        "agent_rationale": manifest.agent_rationale,
        "rho_at_commit": manifest.rho_at_commit,
    }
    p.write_text(json.dumps(payload, indent=2))
    return p
