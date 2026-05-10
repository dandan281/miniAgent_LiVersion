"""Receptor universe v2: load YAML, enumerate 1,711 unordered pairs."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterator

import yaml

from .pair import ReceptorPair


_DEFAULT_YAML = Path(__file__).resolve().parent.parent / "knowledge" / "receptor_universe_v2.yaml"


@dataclass(frozen=True, slots=True)
class Receptor:
    symbol: str
    cls: str
    uniprot: str | None = None
    role: str = ""


@dataclass(frozen=True, slots=True)
class Universe:
    receptors: tuple[Receptor, ...]
    by_symbol: dict[str, Receptor] = field(hash=False)

    def pairs(self) -> Iterator[ReceptorPair]:
        symbols = [r.symbol for r in self.receptors]
        for a, b in combinations(symbols, 2):
            yield ReceptorPair(a=a, b=b)

    def n_pairs(self) -> int:
        n = len(self.receptors)
        return n * (n - 1) // 2

    def class_of(self, symbol: str) -> str:
        return self.by_symbol[symbol].cls


def load(path: Path | str | None = None) -> Universe:
    yaml_path = Path(path) if path else _DEFAULT_YAML
    data = yaml.safe_load(yaml_path.read_text())

    receptors: list[Receptor] = []
    for cls_name, cls_block in data["classes"].items():
        for member in cls_block["members"]:
            receptors.append(
                Receptor(
                    symbol=member["symbol"],
                    cls=cls_name,
                    uniprot=member.get("uniprot"),
                    role=member.get("role", ""),
                )
            )

    n = len(receptors)
    expected_n = data.get("n_receptors", n)
    expected_pairs = data.get("n_pairs", n * (n - 1) // 2)
    if n != expected_n:
        raise ValueError(f"receptor count mismatch: yaml says {expected_n}, found {n}")
    if (n * (n - 1) // 2) != expected_pairs:
        raise ValueError(f"pair count mismatch: expected {expected_pairs}, computed {n*(n-1)//2}")

    by_symbol = {r.symbol: r for r in receptors}
    if len(by_symbol) != n:
        raise ValueError("duplicate receptor symbols in universe")

    return Universe(receptors=tuple(receptors), by_symbol=by_symbol)
