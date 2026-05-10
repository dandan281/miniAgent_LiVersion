"""ReceptorPair — canonical unordered pair with sorted pair_id."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceptorPair:
    a: str
    b: str

    def __post_init__(self) -> None:
        lo, hi = sorted((self.a, self.b))
        object.__setattr__(self, "a", lo)
        object.__setattr__(self, "b", hi)
        if self.a == self.b:
            raise ValueError(f"self-pair not allowed: {self.a}")

    @property
    def pair_id(self) -> str:
        return f"{self.a}__{self.b}"

    @classmethod
    def from_id(cls, pair_id: str) -> "ReceptorPair":
        a, b = pair_id.split("__", 1)
        return cls(a=a, b=b)

    def __iter__(self):
        yield self.a
        yield self.b
