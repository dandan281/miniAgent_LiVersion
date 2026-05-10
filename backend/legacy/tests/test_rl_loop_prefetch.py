"""Tests for rl_loop._prefetch_receptor_context.

Uses monkeypatching to avoid real network calls to UniProt or the 2 GB atlas.
Verifies the output block structure and fallback behavior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rl_loop import _prefetch_receptor_context, ATLAS_PATH  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Helpers / stubs
# ─────────────────────────────────────────────────────────────────────────

def _fake_uniprot_response(gene: str) -> MagicMock:
    """Returns a stub UniprotApiResponse for a given gene."""
    resp = MagicMock()
    resp.json_payload = {
        "results": [
            {
                "primaryAccession": f"P{gene[:5].upper()}1",
                "proteinDescription": {
                    "recommendedName": {"fullName": {"value": f"{gene} receptor"}}
                },
                "comments": [
                    {
                        "commentType": "SIMILARITY",
                        "texts": [{"value": f"Belongs to the {gene} kinase family"}],
                    }
                ],
                "sequence": {"length": 1200},
            }
        ]
    }
    return resp


def _fake_atlas_tool_run(action, genes=None, cell_types=None, **kwargs):
    """Stub for LocalAtlasTool._run that returns synthetic expression data."""
    if action != "expression_summary":
        return ("", {"status": "error", "error": {"code": "invalid_input"}})
    genes = genes or []
    expr = {}
    for gene in genes:
        expr[gene] = {
            "MuSC": {
                "young": {"fraction_expressing": 0.60, "mean_expression": 1.1},
                "old":   {"fraction_expressing": 0.40, "mean_expression": 0.8},
                "delta_old_minus_young": {"fraction_expressing": -0.20, "mean_expression": -0.3},
            }
        }
    payload = {"expression": expr, "genes_missing": []}
    return ("ok", {"status": "success", "structured_payload": payload})


# ─────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────

def test_prefetch_returns_string(monkeypatch, tmp_path):
    """Basic smoke test — function returns a non-empty string."""
    # Patch both external dependencies
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response(kw.get("query", "X").split(":")[1].split(" ")[0])
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("EGFR", "IL6ST")
    assert isinstance(block, str)
    assert len(block) > 100


def test_prefetch_contains_atlas_de_lists(monkeypatch):
    """The DE gene lists should appear in the block (from real ATLAS_PATH)."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("FGFR1", "ERBB2")
    # Key DE gene list sections must appear
    assert "P2_up" in block
    assert "P1_up" in block
    # IEG warning must appear
    assert "EGR1" in block
    assert "FOS" in block


def test_prefetch_contains_both_receptors(monkeypatch):
    """Expression block must mention both receptor gene symbols."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("FGFR1", "IL6ST")
    assert "FGFR1" in block
    assert "IL6ST" in block


def test_prefetch_graceful_uniprot_failure(monkeypatch):
    """If UniProt raises, the block falls back to a warning; does not raise."""
    def _raise(**kw):
        raise RuntimeError("synthetic network failure")

    monkeypatch.setattr("tools.uniprot_api_tool.fetch_uniprot_response", _raise)
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("EGFR", "MET")
    # Must still return a valid string with the atlas data
    assert "PRE-FETCHED DATA" in block
    assert "pre-fetch skipped" in block.lower() or "uniprot" in block.lower()
    assert "P2_up" in block  # DE lists should still be present


def test_prefetch_graceful_atlas_failure(monkeypatch):
    """If local atlas raises, the block falls back; does not raise."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    def _raise(self, **kw):
        raise FileNotFoundError("atlas not available")

    monkeypatch.setattr("tools.local_atlas_tool.LocalAtlasTool._run", _raise)
    block = _prefetch_receptor_context("EGFR", "MET")
    assert "PRE-FETCHED DATA" in block
    # UniProt info should still be present
    assert "pre-fetch skipped" in block.lower() or "atlas" in block.lower()


def test_prefetch_uniprot_section_format(monkeypatch):
    """UniProt block should include accession, length, and family info."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response(kw.get("query", "XGENE1").split(":")[1].split(" ")[0])
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("EGFR", "FGFR1")
    # Should mention UniProt accession
    assert "UniProt=" in block
    # Should mention length
    assert "aa" in block


def test_prefetch_atlas_expression_format(monkeypatch):
    """Atlas expression block should show young/old pc/me for both genes."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("EGFR", "FGFR1")
    # Atlas expression section
    assert "young pc=" in block
    assert "old pc=" in block
    assert "MuSC" in block


def test_prefetch_includes_adaptor_lookup(monkeypatch):
    """Adaptor → UniProt accession table should appear when knowledge file exists."""
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    block = _prefetch_receptor_context("EGFR", "FGFR1")
    # If the knowledge/adaptor_uniprot_lookup.json file is present, the block
    # should mention common adaptors.
    from pathlib import Path
    adaptor_file = Path(__file__).parent.parent / "knowledge" / "adaptor_uniprot_lookup.json"
    if adaptor_file.exists():
        # GRB2 is a canonical adaptor that should always be in the lookup
        assert "GRB2" in block
        # Should link to reactome_api usage
        assert "reactome_api" in block


def test_prefetch_handles_missing_adaptor_file(monkeypatch, tmp_path):
    """If adaptor_uniprot_lookup.json is absent, prefetch should still succeed."""
    # Patch BACKEND constant to point at empty tmp dir → adaptor file won't exist
    import scripts.rl_loop as rl_mod
    monkeypatch.setattr(
        "tools.uniprot_api_tool.fetch_uniprot_response",
        lambda **kw: _fake_uniprot_response("X")
    )
    monkeypatch.setattr(
        "tools.local_atlas_tool.LocalAtlasTool._run",
        lambda self, **kw: _fake_atlas_tool_run(**kw)
    )
    monkeypatch.setattr(rl_mod, "BACKEND", tmp_path)
    monkeypatch.setattr(rl_mod, "ATLAS_PATH", tmp_path / "atlas.json")
    # The atlas DE block will fail gracefully too — but UniProt + atlas expression
    # should still appear. We just want to confirm no exception is raised.
    block = _prefetch_receptor_context("EGFR", "FGFR1")
    assert "PRE-FETCHED DATA" in block
