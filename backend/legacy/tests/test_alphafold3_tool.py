"""
Tests for the AlphaFold 3 tool wrapper (mock mode).

The live branch is intentionally a NotImplementedError stub — see
backend/tools/alphafold3_tool.py — so all tests stay in mock mode and
make no outbound network calls.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.alphafold3_tool import Alphafold3Tool  # noqa: E402


@pytest.fixture
def tool(tmp_path, monkeypatch):
    # Force mock mode and isolate the cache dir to a tmp location.
    monkeypatch.delenv("AF3_MODE", raising=False)
    monkeypatch.delenv("AF3_API_KEY", raising=False)
    monkeypatch.delenv("AF3_ENDPOINT_URL", raising=False)
    return Alphafold3Tool(base_dir=str(tmp_path))


def test_submit_job_mock(tool):
    summary, env = tool._run(
        action="submit_job",
        name="test",
        sequences=[{"kind": "protein", "sequence": "MKTII"}],
    )
    assert env["status"] == "success"
    assert env["outcome"] == "success"
    payload = env["structured_payload"]
    assert payload["mock"] is True
    assert payload["status"] == "queued"
    assert payload["job_id"].startswith("af3_mock_")
    assert "alphafold3_mock_mode" in env["warnings"]


def test_poll_job_mock_returns_metrics(tool):
    _, submit_env = tool._run(
        action="submit_job",
        name="poll-case",
        sequences=[{"kind": "protein", "sequence": "MKTIIALSY"}],
    )
    job_id = submit_env["structured_payload"]["job_id"]

    _, poll_env = tool._run(action="poll_job", job_id=job_id)
    assert poll_env["status"] == "success"
    payload = poll_env["structured_payload"]
    assert payload["status"] == "succeeded"
    metrics = payload["metrics"]
    for key in ("ipTM", "ipSAE", "interface_pLDDT"):
        assert 0.0 <= metrics[key] <= 1.0
    assert len(metrics["plddt_per_residue"]) == 5


def test_get_results_mock_returns_pdb(tool):
    _, submit_env = tool._run(
        action="submit_job",
        name="results-case",
        sequences=[
            {"kind": "protein", "sequence": "MKTII"},
            {"kind": "ligand", "smiles": "CCO"},
        ],
    )
    job_id = submit_env["structured_payload"]["job_id"]

    _, results_env = tool._run(action="get_results", job_id=job_id)
    assert results_env["status"] == "success"
    payload = results_env["structured_payload"]
    assert payload["mock"] is True
    assert payload["status"] == "succeeded"
    assert "metrics" in payload
    assert isinstance(payload["pdb"], str)
    assert payload["pdb"].startswith("HEADER")
    assert "ATOM" in payload["pdb"]


def test_invalid_input_rejected(tool):
    _, env = tool._run(action="submit_job", name="", sequences=[{"kind": "protein", "sequence": "A"}])
    assert env["outcome"] == "invalid_input"

    _, env2 = tool._run(action="submit_job", name="x", sequences=[{"kind": "bogus", "sequence": "A"}])
    assert env2["outcome"] == "invalid_input"


def test_live_mode_without_env_is_blocked(tool, monkeypatch):
    monkeypatch.setenv("AF3_MODE", "live")
    monkeypatch.delenv("AF3_API_KEY", raising=False)
    monkeypatch.delenv("AF3_ENDPOINT_URL", raising=False)
    _, env = tool._run(
        action="submit_job",
        name="x",
        sequences=[{"kind": "protein", "sequence": "A"}],
    )
    assert env["outcome"] == "blocked"


def test_deterministic_mock_metrics(tool):
    _, e1 = tool._run(
        action="submit_job", name="same", sequences=[{"kind": "protein", "sequence": "MMM"}]
    )
    _, e2 = tool._run(
        action="submit_job", name="same", sequences=[{"kind": "protein", "sequence": "MMM"}]
    )
    assert e1["structured_payload"]["job_id"] == e2["structured_payload"]["job_id"]
