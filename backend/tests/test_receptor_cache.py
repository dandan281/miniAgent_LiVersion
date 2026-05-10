"""Tests for backend/utils/receptor_cache.py."""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import receptor_cache  # noqa: E402


@pytest.fixture
def tmp_cache(tmp_path):
    """Hand each test a fresh cache file path."""
    return tmp_path / "rc.json"


def test_put_and_get_roundtrip(tmp_cache):
    receptor_cache.put("EGFR", uniprot={"accession": "P00533", "length": 1210}, path=tmp_cache)
    entry = receptor_cache.get("EGFR", path=tmp_cache)
    assert entry is not None
    assert entry["uniprot"]["accession"] == "P00533"
    assert entry["uniprot"]["length"] == 1210


def test_get_missing_returns_none(tmp_cache):
    assert receptor_cache.get("NEVER_HEARD", path=tmp_cache) is None


def test_case_insensitive_lookup(tmp_cache):
    receptor_cache.put("egfr", uniprot={"accession": "P00533"}, path=tmp_cache)
    # Should be retrievable with any casing
    assert receptor_cache.get("EGFR", path=tmp_cache) is not None
    assert receptor_cache.get("Egfr", path=tmp_cache) is not None


def test_stale_entry_returns_none(tmp_cache):
    """Manually craft an entry older than TTL → should not be returned."""
    cache = {
        "OLD": {
            "uniprot": {"accession": "P00533"},
            "fetched_at": (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=100)).isoformat(),
        }
    }
    tmp_cache.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache.write_text(json.dumps(cache))
    assert receptor_cache.get("OLD", path=tmp_cache) is None


def test_merge_uniprot_and_atlas(tmp_cache):
    receptor_cache.put("EGFR", uniprot={"accession": "P00533"}, path=tmp_cache)
    receptor_cache.put("EGFR", atlas={"MuSC": {"young": {"pc": 0.5}}}, path=tmp_cache)
    entry = receptor_cache.get("EGFR", path=tmp_cache)
    # Both fields should still be present
    assert entry["uniprot"]["accession"] == "P00533"
    assert entry["atlas"]["MuSC"]["young"]["pc"] == 0.5


def test_invalidate_removes_entry(tmp_cache):
    receptor_cache.put("EGFR", uniprot={"accession": "P00533"}, path=tmp_cache)
    assert receptor_cache.get("EGFR", path=tmp_cache) is not None
    ok = receptor_cache.invalidate("EGFR", path=tmp_cache)
    assert ok is True
    assert receptor_cache.get("EGFR", path=tmp_cache) is None


def test_invalidate_missing_returns_false(tmp_cache):
    assert receptor_cache.invalidate("NEVER_HERE", path=tmp_cache) is False


def test_clear_wipes_cache(tmp_cache):
    receptor_cache.put("A", uniprot={"x": 1}, path=tmp_cache)
    receptor_cache.put("B", uniprot={"x": 2}, path=tmp_cache)
    assert tmp_cache.exists()
    receptor_cache.clear(tmp_cache)
    assert not tmp_cache.exists()


def test_corrupt_cache_returns_empty(tmp_cache):
    """If the cache file is malformed JSON, load_cache should return {}."""
    tmp_cache.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache.write_text("not json {{")
    assert receptor_cache.load_cache(tmp_cache) == {}
    # And get() should not raise
    assert receptor_cache.get("X", path=tmp_cache) is None


def test_stats_counts_fresh_and_stale(tmp_cache):
    """stats should distinguish fresh vs stale entries."""
    cache = {
        "FRESH": {
            "uniprot": {"accession": "P1"},
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        },
        "STALE": {
            "uniprot": {"accession": "P2"},
            "fetched_at": (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=200)).isoformat(),
        },
    }
    tmp_cache.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache.write_text(json.dumps(cache))
    s = receptor_cache.stats(path=tmp_cache)
    assert s["n_entries"] == 2
    assert s["n_fresh"] == 1
    assert s["n_stale"] == 1


def test_atomic_write_via_tmp_then_rename(tmp_cache, monkeypatch):
    """save_cache should write to .tmp first, then rename. We just check that
    the file ends up correct after save_cache returns (i.e. no half-written state)."""
    # First write
    receptor_cache.save_cache({"X": {"uniprot": {"a": 1}}}, path=tmp_cache)
    assert tmp_cache.exists()
    data = json.loads(tmp_cache.read_text())
    assert data == {"X": {"uniprot": {"a": 1}}}
    # Ensure no leftover .tmp
    assert not tmp_cache.with_suffix(tmp_cache.suffix + ".tmp").exists()


def test_ttl_zero_treats_everything_as_stale(tmp_cache):
    """With ttl_days=0 even a just-written entry should be considered stale."""
    receptor_cache.put("EGFR", uniprot={"accession": "P00533"}, path=tmp_cache)
    # Direct fresh check with ttl=0 → stale
    assert receptor_cache.get("EGFR", ttl_days=0, path=tmp_cache) is None
