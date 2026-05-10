"""Tests for the new multi-gene 'screens_for_gene' batching path in biogrid_orcs_tool.

We monkey-patch the _resolve_gene_id and _get helpers so no network calls happen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import biogrid_orcs_tool  # noqa: E402
from tools.biogrid_orcs_tool import BiogridOrcsTool  # noqa: E402


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv("BIOGRID_ORCS_ACCESS_KEY", "fake-key-123")


@pytest.fixture
def stubbed_resolver(monkeypatch):
    """Map gene symbols → fake NCBI gene ids."""
    fake_ids = {"EGFR": "1956", "ERBB2": "2064", "FGFR1": "2260", "FGFR2": "2263"}

    def _stub(symbol, key, organism_id):
        return fake_ids.get(symbol)

    monkeypatch.setattr(biogrid_orcs_tool, "_resolve_gene_id", _stub)
    return fake_ids


@pytest.fixture
def stubbed_get(monkeypatch):
    """Each gene_id returns 1-2 fake screen hits."""
    def _stub(url):
        # Extract geneId from the URL query string
        gene_id = ""
        if "geneId=" in url:
            gene_id = url.split("geneId=")[1].split("&")[0]
        if gene_id == "1956":
            return 200, [{"screen_id": "S100", "phenotype": "viability", "cell_line": "A549"}]
        if gene_id == "2064":
            return 200, [
                {"screen_id": "S200", "phenotype": "muscle differentiation", "cell_line": "C2C12"},
                {"screen_id": "S201", "phenotype": "atrophy", "cell_line": "HSMM"},
            ]
        # Default: empty
        return 200, []

    monkeypatch.setattr(biogrid_orcs_tool, "_get", _stub)


def test_screens_for_gene_single_unchanged(fake_key, stubbed_resolver, stubbed_get):
    """Single-gene request still works (back-compat)."""
    tool = BiogridOrcsTool()
    _content, art = tool._run(query_type="screens_for_gene", gene_symbol="EGFR")
    assert art["status"] == "success"
    sp = art.get("structured_payload") or {}
    results = sp.get("results", [])
    assert len(results) == 1
    assert results[0]["queried_gene"] == "EGFR"
    assert results[0]["ncbi_gene_id"] == "1956"


def test_screens_for_gene_batched(fake_key, stubbed_resolver, stubbed_get):
    """Multi-gene gene_list collapses to one tool call returning combined results."""
    tool = BiogridOrcsTool()
    _content, art = tool._run(query_type="screens_for_gene",
                               gene_list="EGFR,ERBB2,FGFR1")
    assert art["status"] == "success"
    sp = art.get("structured_payload") or {}
    results = sp.get("results", [])
    # EGFR returns 1, ERBB2 returns 2, FGFR1 returns 0 → 3 total
    assert len(results) == 3
    queried = {r["queried_gene"] for r in results}
    assert queried == {"EGFR", "ERBB2"}  # FGFR1 had no screens, so not present


def test_screens_for_gene_no_input_returns_error(fake_key):
    tool = BiogridOrcsTool()
    _content, art = tool._run(query_type="screens_for_gene")
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"


def test_screens_for_gene_too_many_genes_rejected(fake_key, stubbed_resolver, stubbed_get):
    """Cap at 25 genes."""
    too_many = ",".join(f"GENE{i}" for i in range(30))
    tool = BiogridOrcsTool()
    _content, art = tool._run(query_type="screens_for_gene", gene_list=too_many)
    err = (art or {}).get("error") or {}
    assert err.get("code") == "invalid_input"
    assert "Too many" in err.get("message", "")


def test_screens_for_gene_unresolvable_gene_skipped(fake_key, stubbed_resolver, stubbed_get):
    """Genes that can't be resolved to gene_id are skipped, not fatal."""
    tool = BiogridOrcsTool()
    _content, art = tool._run(query_type="screens_for_gene",
                               gene_list="EGFR,UNKNOWN_GENE,ERBB2")
    # Should succeed with EGFR + ERBB2 results only
    assert art["status"] == "success"
    sp = art.get("structured_payload") or {}
    results = sp.get("results", [])
    queried = {r["queried_gene"] for r in results}
    assert "EGFR" in queried
    assert "ERBB2" in queried
    assert "UNKNOWN_GENE" not in queried
