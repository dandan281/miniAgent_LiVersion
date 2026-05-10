"""Python executors for the Boltz-2 (Superbio) workflow.

Spec: workflows/boltz2.yaml

Three step functions:
  - validate_and_prepare_input : normalize sequence JSON/FASTA into a Boltz-2-native
    YAML input file; for single-chain also writes a minimal a3m wrapper accepted by
    the Superbio UI file upload gate.
  - poll_and_download : wait for the Superbio Boltz-2 job and materialize outputs.
  - summarize_structures : produce a structured qa_report from the downloaded CIF/JSON.

Superbio Boltz-2 app ID: 688c728099fcc1d511509092
File key for input: ``input_msa_file`` (a3m, optional — MSA server used if omitted)

Multi-chain complex input:
  Boltz-2 natively accepts a YAML with a top-level ``sequences`` list.  The Superbio
  app accepts .a3m files for the ``input_msa_file`` slot.  For single-chain prediction
  the a3m file is just the query sequence.  For multi-chain complexes the Boltz-2 YAML
  is written to disk and passed via the adapter's ``local_files`` dict under the key
  ``input_msa_file`` (Superbio validates by extension — a .a3m file is expected; the
  multi-chain YAML workaround requires Superbio to accept .yaml, which has not been
  smoke-tested).  NOTE: multi-chain via Superbio is UNVERIFIED; smoke-test before
  relying on it for novokine+ECD complex predictions.  Protenix is the confirmed
  multi-chain path.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

try:
    from runtime.runner_events import emit_runner_event as _emit_runner_event
except Exception:
    def _emit_runner_event(**_kwargs: Any) -> None:
        return None

_VALID_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBJOUXZ\-\*]+$", re.IGNORECASE)
_MAX_SEQ_LEN = 2700
_MIN_SEQ_LEN = 16

_SUCCESS_STATES = {"succeeded", "completed", "success", "done"}
_FAILURE_STATES = {"failed", "error", "cancelled", "canceled", "timeout"}
_HEARTBEAT_INTERVAL_S = 10.0
_TOOL_NAME = "boltz2"


def _run_dir(context: Any) -> Path:
    candidate = (
        getattr(context, "run_dir", None)
        or getattr(context, "working_directory", None)
        or getattr(context, "base_dir", None)
        or "."
    )
    return Path(str(candidate)).resolve()


def _resolve_input_path(context: Any, raw: Any) -> Path:
    base = Path(str(getattr(context, "base_dir", "."))).resolve()
    p = Path(str(raw))
    return p if p.is_absolute() else (base / p)


def _parse_fasta(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    name: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                out.append({"protein_name": name, "sequence": "".join(chunks)})
            name = line[1:].strip().split()[0] or f"seq_{len(out) + 1}"
            chunks = []
        else:
            chunks.append(line.strip())
    if name is not None:
        out.append({"protein_name": name, "sequence": "".join(chunks)})
    return out


def _normalize_sequence_set(raw_path: Path) -> list[dict[str, str]]:
    text = raw_path.read_text()
    suffix = raw_path.suffix.lower()
    if suffix in {".fa", ".faa", ".fasta"} or text.lstrip().startswith(">"):
        records = _parse_fasta(text)
    else:
        try:
            records = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sequence_set is neither FASTA nor JSON: {exc}") from exc
        if not isinstance(records, list):
            raise ValueError("sequence_set JSON must be a list of {protein_name, sequence} objects.")

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"sequence_set entry {idx} is not an object.")
        name = str(rec.get("protein_name") or rec.get("name") or "").strip()
        seq = str(rec.get("sequence") or rec.get("seq") or "").replace(" ", "").replace("\n", "")
        if not name:
            raise ValueError(f"sequence_set entry {idx} is missing protein_name.")
        if name in seen:
            raise ValueError(f"sequence_set has duplicate protein_name {name!r}.")
        if not seq:
            raise ValueError(f"sequence_set entry {name!r} is missing sequence.")
        if not _VALID_AA_RE.fullmatch(seq):
            raise ValueError(f"sequence {name!r} contains invalid amino-acid characters.")
        if len(seq) < _MIN_SEQ_LEN or len(seq) > _MAX_SEQ_LEN:
            raise ValueError(
                f"sequence {name!r} length {len(seq)} outside accepted bounds "
                f"[{_MIN_SEQ_LEN}, {_MAX_SEQ_LEN}]."
            )
        seen.add(name)
        normalized.append({"protein_name": name, "sequence": seq.upper()})

    if not normalized:
        raise ValueError("sequence_set is empty.")
    return normalized


def _write_boltz2_yaml(records: list[dict[str, str]], use_msa_server: bool) -> str:
    """Serialize chains into Boltz-2 YAML format (github.com/jwohlwend/boltz).

    Each chain gets a unique chain ID (A, B, C, ...) derived from its protein_name.
    """
    chain_ids = [chr(65 + i) for i in range(len(records))]
    lines = ["sequences:"]
    for chain_id, rec in zip(chain_ids, records):
        lines.append(f"  - protein:")
        lines.append(f"      id: {chain_id}")
        lines.append(f"      sequence: {rec['sequence']}")
        if use_msa_server:
            lines.append(f"      msa: :msa_server")
    return "\n".join(lines) + "\n"


def _write_single_chain_a3m(name: str, sequence: str) -> str:
    """Minimal a3m file containing just the query sequence (no MSA hits).
    Boltz-2 / MSA server will fill in the alignment automatically.
    """
    return f"#{len(sequence)}\t1\n0\t1\n>{name}\n{sequence}\n"


def validate_and_prepare_input(inputs, context):
    raw_path = _resolve_input_path(context, inputs["sequence_set"])
    if not raw_path.exists():
        raise FileNotFoundError(f"sequence_set artifact not found: {raw_path}")

    use_msa_server = bool(inputs.get("use_msa_server", True))
    records = _normalize_sequence_set(raw_path)

    out_dir = _run_dir(context) / "outputs" / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    if len(records) == 1:
        # Single-chain: write minimal a3m (accepted by Superbio input_msa_file slot).
        rec = records[0]
        out_path = out_dir / f"{rec['protein_name']}.a3m"
        out_path.write_text(_write_single_chain_a3m(rec["protein_name"], rec["sequence"]))
    else:
        # Multi-chain: write Boltz-2 YAML.  NOTE: Superbio's input_msa_file slot
        # expects .a3m extension; multi-chain YAML upload has not been smoke-tested.
        # If Superbio rejects the .yaml extension, pivot to Protenix for complex runs.
        boltz_yaml = _write_boltz2_yaml(records, use_msa_server)
        out_path = out_dir / "boltz2_complex_input.yaml"
        out_path.write_text(boltz_yaml)

    return {"boltz2_input_file": str(out_path)}


def _superbio_client():
    from superbio import Client

    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        raise RuntimeError("SUPERBIO_TOKEN / SUPERBIO_USER_ID not set in environment.")
    return Client(token=token, user_id=user_id)


def poll_and_download(inputs, context):
    handle = inputs.get("external_job_handle")
    if not isinstance(handle, dict):
        raise ValueError("external_job_handle is missing or malformed.")
    job_id = handle.get("job_id") or handle.get("id")
    if not job_id:
        raise ValueError(f"external_job_handle has no job_id: {handle!r}")

    timeout_s = int(inputs.get("poll_timeout_seconds") or 7200)
    interval_s = int(inputs.get("poll_interval_seconds") or 30)
    started_at = time.time()

    _emit_runner_event(
        job_id=job_id, tool=_TOOL_NAME, phase="queued",
        elapsed_s=0.0, eta_s=float(timeout_s),
        payload={"app_id": handle.get("app_id")},
    )

    client = _superbio_client()
    deadline = started_at + timeout_s
    last_status: str | None = None
    last_emit_at = 0.0

    while time.time() < deadline:
        status = client.get_job_status(job_id)
        last_status = str(status).lower()
        elapsed = time.time() - started_at

        if last_status in _SUCCESS_STATES:
            _emit_runner_event(
                job_id=job_id, tool=_TOOL_NAME, phase="downloading",
                elapsed_s=elapsed, log_tail=f"job status: {status}",
            )
            break
        if last_status in _FAILURE_STATES:
            _emit_runner_event(
                job_id=job_id, tool=_TOOL_NAME, phase="failed",
                elapsed_s=elapsed, log_tail=f"job status: {status}",
            )
            raise RuntimeError(f"Superbio Boltz-2 job {job_id} terminated with status={status}.")

        now = time.time()
        if now - last_emit_at >= _HEARTBEAT_INTERVAL_S:
            _emit_runner_event(
                job_id=job_id, tool=_TOOL_NAME, phase="running",
                elapsed_s=elapsed, eta_s=max(0.0, float(timeout_s) - elapsed),
                log_tail=f"job status: {status}",
            )
            last_emit_at = now

        time.sleep(interval_s)
    else:
        _emit_runner_event(
            job_id=job_id, tool=_TOOL_NAME, phase="failed",
            elapsed_s=time.time() - started_at,
            log_tail=f"timed out after {timeout_s}s (last status={last_status!r})",
        )
        raise TimeoutError(
            f"Superbio Boltz-2 job {job_id} did not finish within {timeout_s}s "
            f"(last status={last_status!r})."
        )

    download_dir = (
        _run_dir(context)
        / "outputs" / "generated" / "external" / "boltz2" / "structures"
    )
    download_dir.mkdir(parents=True, exist_ok=True)

    prev_cwd = os.getcwd()
    try:
        os.chdir(download_dir)
        client.download_all_job_results(job_id=job_id, path_to_download_to=".")
    finally:
        os.chdir(prev_cwd)

    files = sorted(str(p.relative_to(download_dir)) for p in download_dir.rglob("*") if p.is_file())
    manifest = {
        "job_id": job_id,
        "app_id": handle.get("app_id"),
        "downloaded_at": time.time(),
        "files": files,
    }
    (download_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    _emit_runner_event(
        job_id=job_id, tool=_TOOL_NAME, phase="done",
        elapsed_s=time.time() - started_at,
        payload={"structure_predictions_dir": str(download_dir), "files": files},
    )
    return {"structure_predictions": str(download_dir)}


def _scan_predictions(prediction_dir: Path) -> dict[str, Any]:
    cif_files = sorted(prediction_dir.rglob("*.cif"))
    pdb_files = sorted(prediction_dir.rglob("*.pdb"))
    # Boltz-2 emits a confidence JSON per prediction: confidence_model_0.json, etc.
    confidence_files = sorted(
        list(prediction_dir.rglob("confidence*.json"))
        + list(prediction_dir.rglob("*confidence*.json"))
    )
    return {
        "cif_files": [str(p.relative_to(prediction_dir)) for p in cif_files],
        "pdb_files": [str(p.relative_to(prediction_dir)) for p in pdb_files],
        "confidence_files": [str(p.relative_to(prediction_dir)) for p in confidence_files],
    }


def _parse_boltz2_confidence(confidence_file: Path) -> dict[str, Any]:
    """Extract key metrics from a Boltz-2 confidence JSON.

    Expected keys: confidence_score, ptm, iptm, complex_plddt, chains_ptm.
    Returns empty dict on parse failure (non-fatal).
    """
    try:
        data = json.loads(confidence_file.read_text())
        return {
            "confidence_score": data.get("confidence_score"),
            "ptm": data.get("ptm"),
            "iptm": data.get("iptm"),
            "complex_plddt": data.get("complex_plddt"),
            "chains_ptm": data.get("chains_ptm"),
        }
    except Exception:
        return {}


def summarize_structures(inputs, context):
    prediction_dir = Path(str(inputs["structure_predictions"]))
    if not prediction_dir.exists():
        raise FileNotFoundError(f"structure_predictions directory not found: {prediction_dir}")

    scan = _scan_predictions(prediction_dir)
    failed_checks: list[str] = []
    warnings: list[str] = []
    remediation: list[str] = []

    if not scan["cif_files"] and not scan["pdb_files"]:
        failed_checks.append("no_predicted_structures")
        remediation.append("Inspect Superbio job logs; Boltz-2 produced no CIF or PDB artifacts.")

    # Parse confidence metrics from the first available confidence JSON.
    confidence_metrics: dict[str, Any] = {}
    if scan["confidence_files"]:
        confidence_metrics = _parse_boltz2_confidence(
            prediction_dir / scan["confidence_files"][0]
        )
        iptm = confidence_metrics.get("iptm")
        if iptm is not None and iptm < 0.75:
            warnings.append(
                f"Boltz-2 ipTM={iptm:.3f} is below the novokine validation threshold (>0.75)."
            )
    else:
        warnings.append("Boltz-2 confidence JSON not found alongside structures.")
        remediation.append("Verify the Superbio Boltz-2 app version emits confidence_*.json outputs.")

    overall_status = "passed" if not failed_checks and not warnings else (
        "failed" if failed_checks else "warning"
    )

    qa_report = {
        "overall_status": overall_status,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "recommended_remediation": remediation,
        "checklist_artifacts": [
            {"artifact_type": "protein_structure_prediction_set", "path": str(prediction_dir)},
        ],
        "metrics": {
            "n_cif_files": len(scan["cif_files"]),
            "n_pdb_files": len(scan["pdb_files"]),
            "n_confidence_files": len(scan["confidence_files"]),
            **confidence_metrics,
        },
        "structure_files": scan,
    }
    return {"qa_report": qa_report}
