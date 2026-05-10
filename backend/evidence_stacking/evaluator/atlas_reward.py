"""Atlas reward — target signals (aged_young, fibro_muscle) per pair.

Loads cached TSVs from ``backend/knowledge/labels/v2_atlas_reward_<target>.tsv``.
Targets are continuous in roughly [-1, 1].

Holdout split: deterministic by stable hash of pair_id mod 10 < 3 → 30% holdout.
The same split is shared across both targets and across stages, so retention
deltas are comparable.
"""
from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from ..pair import ReceptorPair
from ..receptor_universe import load as load_universe


_KNOWLEDGE = Path(__file__).resolve().parent.parent.parent / "knowledge"
_LABELS_DIR = _KNOWLEDGE / "labels"

Target = Literal["aged_young", "fibro_muscle"]
TARGETS: tuple[Target, ...] = ("aged_young", "fibro_muscle")


def _path(target: Target) -> Path:
    return _LABELS_DIR / f"v2_atlas_reward_{target}.tsv"


def load(target: Target) -> dict[str, float]:
    p = _path(target)
    if not p.exists():
        raise FileNotFoundError(
            f"No reward TSV at {p}. Run "
            f"`python -m evidence_stacking.evaluator.atlas_reward --build {target}`."
        )
    out: dict[str, float] = {}
    for line in p.read_text().splitlines():
        if not line or line.startswith("#") or line.startswith("pair_id"):
            continue
        pid, score = line.split("\t", 1)
        out[pid] = float(score)
    return out


def load_all() -> dict[Target, dict[str, float]]:
    return {t: load(t) for t in TARGETS}


def is_holdout(pair_id: str) -> bool:
    h = int(hashlib.sha256(pair_id.encode()).hexdigest(), 16)
    return (h % 10) < 3


def split(target_map: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Returns (train, holdout)."""
    train: dict[str, float] = {}
    holdout: dict[str, float] = {}
    for k, v in target_map.items():
        (holdout if is_holdout(k) else train)[k] = v
    return train, holdout


# ----- builders -----------------------------------------------------------


def _build_aged_young(out_path: Path) -> Path:
    """Per-pair score = mean(receptor_A_atlas_signal, receptor_B_atlas_signal).

    Per-receptor signal: +1 if symbol in P2_up (young-enriched), -1 if in P1_up
    (aged-enriched), else 0. Pulled from muscle_atlas_DE_v2_consensus.json
    (preferred) falling back to muscle_atlas_DE.json.
    """
    import json

    consensus = _KNOWLEDGE / "muscle_atlas_DE_v2_consensus.json"
    fallback = _KNOWLEDGE / "muscle_atlas_DE.json"
    atlas_path = consensus if consensus.exists() else fallback
    atlas = json.loads(atlas_path.read_text())

    p1 = set(atlas.get("P1_up", []))
    p2 = set(atlas.get("P2_up", []))

    universe = load_universe()
    per: dict[str, float] = {}
    for r in universe.receptors:
        if r.symbol in p2:
            per[r.symbol] = +1.0
        elif r.symbol in p1:
            per[r.symbol] = -1.0
        else:
            per[r.symbol] = 0.0

    pairs = list(universe.pairs())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# aged_young target signal | atlas={atlas_path.name} | n_pairs={len(pairs)}",
        "pair_id\tscore",
    ]
    for p in pairs:
        score = (per[p.a] + per[p.b]) / 2.0
        lines.append(f"{p.pair_id}\t{score:.4f}")
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def build(target: Target, *, out_path: Path | None = None) -> Path:
    out_path = out_path or _path(target)
    if target == "aged_young":
        return _build_aged_young(out_path)
    if target == "fibro_muscle":
        from .synthesize_fibro_signal import build as build_fibro
        return build_fibro(out_path=out_path, mode="auto")
    raise ValueError(f"unknown target: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", choices=list(TARGETS) + ["all"], required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    targets = TARGETS if args.build == "all" else (args.build,)
    for t in targets:
        out = build(t, out_path=args.out if args.build != "all" else None)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
