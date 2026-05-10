"""Tests for backend/tools/local_atlas_tool.py.

The real atlas is 2 GB; loading it would make the test suite painfully
slow and machine-dependent. We mock `_load_atlas` and the helper so the
tests exercise the public Tool API without touching disk.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import local_atlas_tool  # noqa: E402
from tools.local_atlas_tool import LocalAtlasTool  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Fixture: a fake adata stand-in that supplies just enough surface for the
# tool's public actions (no actual sparse matrix needed because we monkey-
# patch _per_group_expression to avoid real expression queries).
# ─────────────────────────────────────────────────────────────────────────
class _FakeSeries:
    def __init__(self, values: list[str]):
        self._values = values

    def value_counts(self):
        from collections import Counter
        return Counter(self._values)


class _FakeObs:
    def __init__(self, age_bins: list[str], cell_types: list[str]):
        self._cols = {
            "Age_bin": _FakeSeries(age_bins),
            "annotation_level0": _FakeSeries(cell_types),
        }

    @property
    def columns(self):
        return list(self._cols.keys())

    def __getitem__(self, key):
        return self._cols[key]


class _FakeAdata:
    def __init__(self, n_cells: int = 1000):
        # Synthetic mix: 600 young, 400 old; 5 cell types (200 cells each).
        # NOTE: `list(itertools.cycle(...))[:n]` would hang because list()
        # consumes the infinite iterator BEFORE the slice. Use plain * + concat.
        ages = (["young"] * 600) + (["old"] * 400)
        per_type = n_cells // 5
        labels = (
            ["MuSC"] * per_type + ["MF-I"] * per_type + ["MF-II"] * per_type
            + ["FB"] * per_type + ["EnFB"] * per_type
        )
        self.obs = _FakeObs(ages, labels)
        self.shape = (n_cells, 100)


@pytest.fixture
def patched_atlas(monkeypatch):
    """Replace _load_atlas + _per_group_expression with stubs."""
    fake = _FakeAdata()
    monkeypatch.setattr(local_atlas_tool, "_load_atlas", lambda: fake)
    # Reset module cache so each test sees a fresh stub.
    local_atlas_tool._ATLAS_CACHE.clear()
    local_atlas_tool._ATLAS_CACHE["adata"] = fake
    local_atlas_tool._ATLAS_CACHE["path"] = "<fake-atlas>"
    yield fake
    local_atlas_tool._ATLAS_CACHE.clear()


def _make_per_group_stub(per_gene_expr: dict[str, dict]):
    """Returns a function suitable for monkeypatching _per_group_expression."""
    def _stub(adata, gene, cell_types, age_bins):
        if gene not in per_gene_expr:
            return {"missing_gene": True}
        full = per_gene_expr[gene]
        # Apply cell_type substring filter consistently with the real tool
        if cell_types:
            wanted = [c.lower() for c in cell_types]
            filtered = {ct: v for ct, v in full.items() if any(w in ct.lower() for w in wanted)}
            return {"per_cell_type": filtered}
        return {"per_cell_type": full}
    return _stub


# ─────────────────────────────────────────────────────────────────────────
# cell_type_inventory
# ─────────────────────────────────────────────────────────────────────────
def test_cell_type_inventory_returns_counts(patched_atlas):
    tool = LocalAtlasTool()
    content, art = tool._run(action="cell_type_inventory")
    sp = (art or {}).get("structured_payload") or {}
    cts = sp.get("cell_types")
    assert isinstance(cts, list) and len(cts) >= 1
    # Each entry must be {label, n_cells}
    for ct in cts:
        assert "label" in ct and "n_cells" in ct
        assert isinstance(ct["n_cells"], int)


# ─────────────────────────────────────────────────────────────────────────
# expression_summary
# ─────────────────────────────────────────────────────────────────────────
def test_expression_summary_requires_gene_list(patched_atlas):
    tool = LocalAtlasTool()
    _content, art = tool._run(action="expression_summary", genes=[])
    assert (art or {}).get("status") == "error"
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"


def test_expression_summary_caps_at_max_genes(patched_atlas):
    tool = LocalAtlasTool()
    too_many = [f"GENE{i}" for i in range(50)]
    _content, art = tool._run(action="expression_summary", genes=too_many)
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"
    assert "Too many" in err.get("message", "")


def test_expression_summary_rejects_invalid_age_bin(patched_atlas):
    tool = LocalAtlasTool()
    _content, art = tool._run(
        action="expression_summary",
        genes=["FGFR1"],
        age_bins=["young", "ancient"],
    )
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"


def test_expression_summary_returns_per_gene_per_celltype(monkeypatch, patched_atlas):
    tool = LocalAtlasTool()
    fake_data = {
        "FGFR1": {
            "MuSC": {
                "young": {"n_cells": 100, "n_expressing": 60, "fraction_expressing": 0.6, "mean_expression": 1.2},
                "old": {"n_cells": 80, "n_expressing": 30, "fraction_expressing": 0.375, "mean_expression": 0.9},
                "delta_old_minus_young": {"fraction_expressing": -0.225, "mean_expression": -0.3},
            }
        }
    }
    monkeypatch.setattr(local_atlas_tool, "_per_group_expression",
                        _make_per_group_stub(fake_data))
    content, art = tool._run(action="expression_summary", genes=["FGFR1"])
    sp = (art or {}).get("structured_payload") or {}
    expr = sp.get("expression") or {}
    fgfr1 = expr.get("FGFR1") or {}
    assert "MuSC" in fgfr1
    musc = fgfr1["MuSC"]
    assert musc["young"]["fraction_expressing"] == 0.6
    assert musc["old"]["fraction_expressing"] == 0.375
    assert musc["delta_old_minus_young"]["fraction_expressing"] == -0.225


def test_expression_summary_records_missing_genes(monkeypatch, patched_atlas):
    tool = LocalAtlasTool()
    monkeypatch.setattr(local_atlas_tool, "_per_group_expression",
                        _make_per_group_stub({}))   # nothing in the map → all missing
    content, art = tool._run(action="expression_summary",
                              genes=["XYZ_NOT_REAL", "ALSO_FAKE"])
    sp = (art or {}).get("structured_payload") or {}
    assert sp.get("genes_missing") == ["XYZ_NOT_REAL", "ALSO_FAKE"]
    assert sp.get("expression") == {}
    warnings = (art or {}).get("warnings") or []
    assert any("missing_genes" in w for w in warnings)


def test_expression_summary_filters_age_bins(monkeypatch, patched_atlas):
    tool = LocalAtlasTool()
    captured = {}
    def _stub(adata, gene, cell_types, age_bins):
        captured["age_bins"] = list(age_bins)
        return {"per_cell_type": {}}
    monkeypatch.setattr(local_atlas_tool, "_per_group_expression", _stub)
    tool._run(action="expression_summary", genes=["FGFR1"], age_bins=["old"])
    assert captured["age_bins"] == ["old"]


def test_unknown_action_returns_invalid_input(patched_atlas):
    tool = LocalAtlasTool()
    _content, art = tool._run(action="not_a_real_action")
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"


# ─────────────────────────────────────────────────────────────────────────
# atlas-not-found error path
# ─────────────────────────────────────────────────────────────────────────
def test_atlas_not_found_returns_invalid_input(monkeypatch):
    """If the atlas file is missing, we should get a graceful error, not a crash."""
    local_atlas_tool._ATLAS_CACHE.clear()
    def _raise_fnf():
        raise FileNotFoundError("synthetic atlas not found at /tmp/none.h5ad")
    monkeypatch.setattr(local_atlas_tool, "_load_atlas", _raise_fnf)
    tool = LocalAtlasTool()
    _content, art = tool._run(action="cell_type_inventory")
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"
    assert "atlas" in err.get("message", "").lower()
