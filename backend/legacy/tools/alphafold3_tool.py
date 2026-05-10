"""
AlphaFold 3 hosted-server tool: submit, poll, and fetch results from the
AF3 server (https://alphafoldserver.com — Google account API).

Default mode is MOCK (deterministic from input hash), because as of late 2025
the alphafoldserver.com hosted endpoint exposes only a manual web UI; there
is no stable public REST endpoint. Live mode is a documented stub that
requires AF3_MODE=live, AF3_API_KEY, and AF3_ENDPOINT_URL.

Mock metric ranges line up with the thresholds documented in
backend/skills/novokine_validation/SKILL.md (ipTM > 0.75, ipSAE > 0.70,
interface_pLDDT > 0.80) — values straddle the thresholds so a stream of
candidates yields both PASS and FAIL results, keeping the downstream
validator and RL scorer honest.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    blocked_result,
    execution_error_result,
    invalid_input_result,
    json_to_pretty_text,
    success_result,
)

ActionType = Literal["submit_job", "poll_job", "get_results"]
SequenceKind = Literal["protein", "rna", "dna", "ligand"]

_MOCK_WARNING = "alphafold3_mock_mode"
_CACHE_SUBDIR = "alphafold3_cache"
_MAX_TEXT = 50_000
_MOCK_PLDDT_PREVIEW_LEN = 5

# Synthetic single-ATOM PDB so downstream Biopython parsers see a valid record.
_MOCK_PDB = (
    "HEADER    MOCK ALPHAFOLD3 OUTPUT\n"
    "TITLE     ALPHAFOLD3_MOCK_MODE deterministic stub structure\n"
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C\n"
    "TER\n"
    "END\n"
)


def _input_hash(payload: Any) -> str:
    """Deterministic 8-hex hash of any JSON-serialisable payload."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:8]


def _mock_metrics(seed_hex: str) -> dict[str, Any]:
    """Generate deterministic mock confidence metrics in a sensible range.

    Values land in [0.65, 0.95) so half pass / half fail the validation
    thresholds (ipTM > 0.75, ipSAE > 0.70, interface_pLDDT > 0.80).
    """
    base = int(seed_hex, 16)
    iptm = round(0.65 + ((base % 30) / 100.0), 4)
    ipsae = round(0.65 + (((base >> 5) % 30) / 100.0), 4)
    iface_plddt = round(0.65 + (((base >> 10) % 30) / 100.0), 4)
    plddt_per_residue = [
        round(0.60 + (((base >> (i * 3)) % 35) / 100.0), 4)
        for i in range(_MOCK_PLDDT_PREVIEW_LEN)
    ]
    return {
        "ipTM": iptm,
        "ipSAE": ipsae,
        "interface_pLDDT": iface_plddt,
        "plddt_per_residue": plddt_per_residue,
    }


def _validate_sequences(sequences: Any) -> str | None:
    """Return an error message if `sequences` is malformed, else None."""
    if not isinstance(sequences, list) or not sequences:
        return "'sequences' must be a non-empty list of dicts."
    valid_kinds = {"protein", "rna", "dna", "ligand"}
    for idx, seq in enumerate(sequences):
        if not isinstance(seq, dict):
            return f"sequences[{idx}] must be a dict."
        kind = seq.get("kind")
        if kind not in valid_kinds:
            return (
                f"sequences[{idx}].kind must be one of "
                f"{sorted(valid_kinds)}; got {kind!r}."
            )
        if kind == "ligand":
            if not seq.get("smiles") and not seq.get("sequence"):
                return f"sequences[{idx}] (ligand) must include 'smiles' or 'sequence'."
        else:
            seq_str = seq.get("sequence")
            if not isinstance(seq_str, str) or not seq_str.strip():
                return f"sequences[{idx}] must include a non-empty 'sequence' string."
    return None


class Alphafold3Input(BaseModel):
    action: ActionType = Field(
        description=(
            "Action to perform: "
            "'submit_job' — submit a new AF3 prediction (requires name + sequences); "
            "'poll_job' — check status of a submitted job (requires job_id); "
            "'get_results' — fetch metrics + structure of a completed job (requires job_id)."
        )
    )
    name: Optional[str] = Field(
        default=None,
        description="Human-readable job name. Required for action='submit_job'.",
    )
    sequences: Optional[list[dict]] = Field(
        default=None,
        description=(
            "List of sequence dicts for action='submit_job'. Each dict requires "
            "'kind' ∈ {'protein','rna','dna','ligand'} and either 'sequence' "
            "(for protein/rna/dna) or 'smiles' (for ligand). Optional keys are "
            "passed through to the underlying AF3 schema."
        ),
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job identifier returned by 'submit_job'. Required for 'poll_job' and 'get_results'.",
    )


class Alphafold3Tool(BaseTool):
    name: str = "alphafold3_api"
    description: str = (
        "Submit, poll, and retrieve results from AlphaFold 3 (alphafoldserver.com). "
        "Used inside the novokine_validation skill (Check 6) to score predicted "
        "minibinder–receptor complexes via ipTM, ipSAE, and interface pLDDT. "
        "Actions: 'submit_job' (name + sequences[{kind, sequence|smiles}]), "
        "'poll_job' (job_id), 'get_results' (job_id → metrics + PDB). "
        "Defaults to MOCK mode (deterministic from input hash) because the "
        "alphafoldserver.com endpoint has no stable public REST API as of late "
        "2025. To enable live submission, set AF3_MODE=live, AF3_API_KEY, and "
        "AF3_ENDPOINT_URL — but the live branch is currently a NotImplementedError "
        "stub by design (no outbound calls from this build)."
    )
    args_schema: Type[BaseModel] = Alphafold3Input
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    # ── helpers ──────────────────────────────────────────────────────────────
    def _mode(self) -> str:
        return (os.environ.get("AF3_MODE") or "mock").strip().lower()

    def _cache_dir(self) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(__file__).resolve().parents[1]
        return base / "storage" / _CACHE_SUBDIR

    def _cache_path(self, job_id: str) -> Path:
        return self._cache_dir() / f"{job_id}.json"

    def _write_cache(self, job_id: str, payload: dict[str, Any]) -> Optional[str]:
        try:
            d = self._cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(job_id)
            path.write_text(json.dumps(payload, indent=2, default=str))
            return str(path)
        except Exception:
            return None

    def _read_cache(self, job_id: str) -> Optional[dict[str, Any]]:
        try:
            path = self._cache_path(job_id)
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            return None
        return None

    def _live_guard(self, action: ActionType) -> Optional[tuple[str, dict]]:
        """Return a blocked/NotImplementedError result if live mode is misconfigured.

        In live mode without both env vars, return a blocked_result. With both
        set, raise NotImplementedError (caught at the top of _run) — this is
        intentional: the live branch is a documented stub so no outbound call
        ever leaves this process in this build.
        """
        api_key = os.environ.get("AF3_API_KEY")
        endpoint = os.environ.get("AF3_ENDPOINT_URL")
        if not api_key or not endpoint:
            return blocked_result(
                self.name,
                "AF3 live mode requires AF3_API_KEY and AF3_ENDPOINT_URL env "
                "vars; remaining in mock mode is recommended.",
                metadata={"action": action, "af3_mode": "live"},
            )
        raise NotImplementedError(
            "Live AF3 submission not implemented in this build. The hosted "
            "alphafoldserver.com has no stable public REST endpoint. To enable, "
            "replace this branch with httpx calls to your configured "
            "AF3_ENDPOINT_URL."
        )

    # ── mock action implementations ──────────────────────────────────────────
    def _mock_submit(self, name: str, sequences: list[dict]) -> tuple[str, dict]:
        seed = _input_hash({"name": name, "sequences": sequences})
        job_id = f"af3_mock_{seed}"
        payload = {
            "mock": True,
            "job_id": job_id,
            "status": "queued",
            "name": name,
            "n_sequences": len(sequences),
            "input_hash": seed,
        }
        # Persist enough state for poll/get_results to remain deterministic
        # (they re-derive from job_id, but cache enables get_results to return
        # the original input echo).
        self._write_cache(job_id, {"action": "submit_job", "input": {"name": name, "sequences": sequences}, "result": payload})
        summary, _ = json_to_pretty_text(payload, _MAX_TEXT)
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=[_MOCK_WARNING],
            metadata={"action": "submit_job", "af3_mode": "mock", "job_id": job_id},
        )

    def _mock_poll(self, job_id: str) -> tuple[str, dict]:
        seed = job_id.removeprefix("af3_mock_") or _input_hash(job_id)
        metrics = _mock_metrics(seed)
        payload = {
            "mock": True,
            "job_id": job_id,
            "status": "succeeded",
            "metrics": metrics,
        }
        summary, _ = json_to_pretty_text(payload, _MAX_TEXT)
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=[_MOCK_WARNING],
            metadata={"action": "poll_job", "af3_mode": "mock", "job_id": job_id},
        )

    def _mock_results(self, job_id: str) -> tuple[str, dict]:
        seed = job_id.removeprefix("af3_mock_") or _input_hash(job_id)
        metrics = _mock_metrics(seed)
        cached = self._read_cache(job_id) or {}
        payload = {
            "mock": True,
            "job_id": job_id,
            "status": "succeeded",
            "metrics": metrics,
            "pdb": _MOCK_PDB,
            "n_atoms": 1,
            "input_echo": cached.get("input"),
        }
        cache_path = self._write_cache(job_id, {"action": "get_results", "result": payload})
        meta: dict[str, Any] = {
            "action": "get_results",
            "af3_mode": "mock",
            "job_id": job_id,
        }
        if cache_path:
            meta["cache_path"] = cache_path
        summary, _ = json_to_pretty_text(
            {k: v for k, v in payload.items() if k != "pdb"} | {"pdb_preview": _MOCK_PDB.splitlines()[0]},
            _MAX_TEXT,
        )
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=[_MOCK_WARNING],
            metadata=meta,
        )

    # ── BaseTool entrypoint ──────────────────────────────────────────────────
    def _run(
        self,
        action: ActionType = "submit_job",
        name: Optional[str] = None,
        sequences: Optional[list[dict]] = None,
        job_id: Optional[str] = None,
    ) -> tuple[str, dict]:
        mode = self._mode()
        try:
            if mode == "live":
                guard = self._live_guard(action)
                if guard is not None:
                    return guard
                # Unreachable: _live_guard either returns blocked_result or raises.

            # Default = mock
            if action == "submit_job":
                if not isinstance(name, str) or not name.strip():
                    return invalid_input_result(
                        self.name,
                        "'name' is required and must be a non-empty string for action='submit_job'.",
                        metadata={"action": action},
                    )
                err = _validate_sequences(sequences)
                if err:
                    return invalid_input_result(self.name, err, metadata={"action": action})
                return self._mock_submit(name.strip(), sequences or [])

            if action == "poll_job":
                if not isinstance(job_id, str) or not job_id.strip():
                    return invalid_input_result(
                        self.name,
                        "'job_id' is required for action='poll_job'.",
                        metadata={"action": action},
                    )
                return self._mock_poll(job_id.strip())

            if action == "get_results":
                if not isinstance(job_id, str) or not job_id.strip():
                    return invalid_input_result(
                        self.name,
                        "'job_id' is required for action='get_results'.",
                        metadata={"action": action},
                    )
                return self._mock_results(job_id.strip())

            return invalid_input_result(
                self.name,
                f"Unknown action: {action!r}. Expected one of submit_job, poll_job, get_results.",
                metadata={"action": action},
            )

        except NotImplementedError as exc:
            # Live-mode stub raised — surface as execution_error so the caller
            # sees the NotImplementedError message in a normal envelope.
            return execution_error_result(
                self.name,
                str(exc),
                metadata={"action": action, "af3_mode": mode, "stub": True},
            )
        except Exception as exc:  # pragma: no cover — defensive
            return execution_error_result(
                self.name,
                f"AF3 tool internal error: {exc}",
                metadata={"action": action, "af3_mode": mode},
            )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
