"""Agentic evidence gathering — drives LangChain tools, dedupes vs cache."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from ..pair import ReceptorPair
from .envelope import PairEvidence
from .store import EvidenceStore


# A GatherFn maps (pair, key) -> raw value. The orchestrator wires real tool
# calls; tests pass a simple lambda.
GatherFn = Callable[[ReceptorPair, str], Any]


def gather(
    pairs: Iterable[ReceptorPair],
    keys: Iterable[str],
    gather_fn: GatherFn,
    *,
    store: EvidenceStore | None = None,
    source: str = "gather",
    version: str = "1",
) -> int:
    """Fill cache for ``pairs`` with the listed evidence ``keys``.

    Returns the number of new (pair, key) tuples written. Skips entries that
    already exist in cache.
    """
    store = store or EvidenceStore()
    keys = list(keys)
    n_written = 0
    for pair in pairs:
        ev = store.load(pair.pair_id)
        missing = [k for k in keys if not ev.has(k)]
        if not missing:
            continue
        for k in missing:
            value = gather_fn(pair, k)
            ev.put(k, value, source=source, version=version)
            n_written += 1
        store.save(ev)
    return n_written
