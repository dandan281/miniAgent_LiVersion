"""Persistent file-cache for receptor metadata pre-fetched from UniProt and the
local atlas.

Used by `rl_loop._prefetch_receptor_context` to avoid re-querying UniProt and
the atlas for every RL iteration. Cache entries expire after CACHE_TTL_DAYS
(default 30) so we still pick up upstream annotation refreshes.

Format: a single JSON file with keys = receptor symbol (uppercase), values =
    {
      "uniprot": {accession, name, length, family},
      "atlas":   {<cell_type>: {young: {pc, me}, old: {pc, me}, delta: {pc, me}}},
      "fetched_at": "YYYY-MM-DDTHH:MM:SS+00:00"
    }

Concurrency: serialised on a per-call basis (we read+rewrite). Acceptable
because RL iterations are sequential.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Optional

CACHE_PATH = Path(os.environ.get(
    "RECEPTOR_CACHE_PATH",
    str(Path(__file__).resolve().parent.parent / "storage" / "receptor_cache.json"),
))
CACHE_TTL_DAYS = 30


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _is_fresh(entry: dict, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    fetched = entry.get("fetched_at")
    if not fetched:
        return False
    try:
        fetched_dt = _dt.datetime.fromisoformat(fetched)
    except ValueError:
        return False
    age = _dt.datetime.now(_dt.timezone.utc) - fetched_dt
    return age.total_seconds() < ttl_days * 86400


def load_cache(path: Path = CACHE_PATH) -> dict[str, Any]:
    """Read the cache file. Returns {} if missing or unreadable."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict[str, Any], path: Path = CACHE_PATH) -> None:
    """Atomically write the cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2, default=str)
    tmp.replace(path)


def get(receptor: str, *, ttl_days: int = CACHE_TTL_DAYS,
        path: Path = CACHE_PATH) -> Optional[dict]:
    """Return the cached entry for receptor if fresh, else None."""
    cache = load_cache(path)
    entry = cache.get(receptor.upper())
    if entry and _is_fresh(entry, ttl_days):
        return entry
    return None


def put(receptor: str, *, uniprot: Optional[dict] = None,
        atlas: Optional[dict] = None, path: Path = CACHE_PATH) -> None:
    """Upsert a cache entry for receptor. Merges with any existing fields."""
    cache = load_cache(path)
    key = receptor.upper()
    existing = cache.get(key, {})
    if uniprot is not None:
        existing["uniprot"] = uniprot
    if atlas is not None:
        existing["atlas"] = atlas
    existing["fetched_at"] = _now_iso()
    cache[key] = existing
    save_cache(cache, path)


def invalidate(receptor: str, path: Path = CACHE_PATH) -> bool:
    """Remove the entry for receptor. Returns True if it existed."""
    cache = load_cache(path)
    key = receptor.upper()
    if key in cache:
        del cache[key]
        save_cache(cache, path)
        return True
    return False


def clear(path: Path = CACHE_PATH) -> None:
    """Wipe the entire cache."""
    if path.exists():
        path.unlink()


def stats(path: Path = CACHE_PATH) -> dict:
    """Summarise the cache for observability."""
    cache = load_cache(path)
    fresh = sum(1 for entry in cache.values() if _is_fresh(entry))
    stale = len(cache) - fresh
    return {
        "n_entries": len(cache),
        "n_fresh":   fresh,
        "n_stale":   stale,
        "path":      str(path),
    }
