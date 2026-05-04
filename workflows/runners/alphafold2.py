"""Python executors for the AlphaFold2 (Superbio) workflow.

Spec: workflows/alphafold2.yaml

Three step functions are exposed:
  - validate_sequence_set : normalize input FASTA / JSON sequence list into the
    canonical [{protein_name, sequence}, ...] form and emit it as the
    `validated_sequence_set` artifact for the launch step.
  - poll_and_download : wait for the Superbio AlphaFold2 job to finish and
    materialize predicted structures into the run directory.
  - summarize_structures : produce a structured qa_report from the downloaded
    predictions.

The Superbio submission itself is performed by the BioAPEX external_engine
executor (engine_name=superbio, see launch_alphafold2 step). The
`poll_and_download` runner consumes the job handle that step emits and is
intentionally agnostic to *how* the job was submitted.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

try:  # The runner is importable from CLI / Nextflow contexts where the
    # backend isn't on sys.path. In those cases we degrade gracefully — runner
    # progress simply won't be visible in the UI, but the job still completes.
    from runtime.runner_events import emit_runner_event as _emit_runner_event
except Exception:  # pragma: no cover — import fallback
    def _emit_runner_event(**_kwargs: Any) -> None:
        return None

_VALID_MODEL_PRESETS = {"monomer", "monomer_ptm", "multimer"}
_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBJOUXZ\-\*]+$", re.IGNORECASE)
_MAX_SEQ_LEN = 2700
_MIN_SEQ_LEN = 16


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
    seen_names: set[str] = set()
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"sequence_set entry {idx} is not an object.")
        name = str(rec.get("protein_name") or rec.get("name") or "").strip()
        seq = str(rec.get("sequence") or rec.get("seq") or "").replace(" ", "").replace("\n", "")
        if not name:
            raise ValueError(f"sequence_set entry {idx} is missing protein_name.")
        if name in seen_names:
            raise ValueError(f"sequence_set has duplicate protein_name {name!r}.")
        if not seq:
            raise ValueError(f"sequence_set entry {name!r} is missing sequence.")
        if not _AA_RE.fullmatch(seq):
            raise ValueError(f"sequence {name!r} contains invalid amino-acid characters.")
        if len(seq) < _MIN_SEQ_LEN or len(seq) > _MAX_SEQ_LEN:
            raise ValueError(
                f"sequence {name!r} length {len(seq)} outside accepted bounds "
                f"[{_MIN_SEQ_LEN}, {_MAX_SEQ_LEN}]."
            )
        seen_names.add(name)
        normalized.append({"protein_name": name, "sequence": seq.upper()})

    if not normalized:
        raise ValueError("sequence_set is empty.")
    return normalized


def validate_sequence_set(inputs, context):
    raw_path = _resolve_input_path(context, inputs["sequence_set"])
    if not raw_path.exists():
        raise FileNotFoundError(f"sequence_set artifact not found: {raw_path}")

    model_preset = str(inputs.get("model_preset") or "monomer")
    if model_preset not in _VALID_MODEL_PRESETS:
        raise ValueError(
            f"model_preset {model_preset!r} not in {sorted(_VALID_MODEL_PRESETS)}."
        )

    records = _normalize_sequence_set(raw_path)

    out_dir = _run_dir(context) / "outputs" / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "validated_sequence_set.json"
    out_path.write_text(json.dumps(records, indent=2))
    return {"validated_sequence_set": str(out_path)}


def _superbio_client():
    from superbio import Client  # noqa: WPS433

    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        raise RuntimeError("SUPERBIO_TOKEN / SUPERBIO_USER_ID not set in environment.")
    return Client(token=token, user_id=user_id)


_TOOL_NAME = "alphafold2"

# Status strings the Superbio API may return — split into terminal-success and
# terminal-failure buckets. Anything else is treated as still-running.
_SUCCESS_STATES = {"succeeded", "completed", "success", "done"}
_FAILURE_STATES = {"failed", "error", "cancelled", "canceled", "timeout"}

# Heartbeat cadence for the runner-events bus: emit a fresh event at least
# this often so the UI's elapsed/ETA stays live even when Superbio's status
# doesn't change for many polls in a row.
_HEARTBEAT_INTERVAL_S = 10.0


def poll_and_download(inputs, context):
    handle = inputs.get("external_job_handle")
    if not isinstance(handle, dict):
        raise ValueError(
            "external_job_handle is missing or malformed. "
            "Expected dict produced by the launch_alphafold2 external_engine step."
        )
    job_id = handle.get("job_id") or handle.get("id")
    if not job_id:
        raise ValueError(f"external_job_handle has no job_id: {handle!r}")

    timeout_s = int(inputs.get("poll_timeout_seconds") or 5400)
    interval_s = int(inputs.get("poll_interval_seconds") or 30)
    started_at = time.time()

    _emit_runner_event(
        job_id=job_id,
        tool=_TOOL_NAME,
        phase="queued",
        elapsed_s=0.0,
        eta_s=float(timeout_s),
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
                job_id=job_id,
                tool=_TOOL_NAME,
                phase="downloading",
                elapsed_s=elapsed,
                log_tail=f"job status: {status}",
            )
            break
        if last_status in _FAILURE_STATES:
            _emit_runner_event(
                job_id=job_id,
                tool=_TOOL_NAME,
                phase="failed",
                elapsed_s=elapsed,
                log_tail=f"job status: {status}",
            )
            raise RuntimeError(f"Superbio job {job_id} terminated with status={status}.")

        # Heartbeat / progress event so the UI's elapsed clock stays fresh.
        now = time.time()
        if now - last_emit_at >= _HEARTBEAT_INTERVAL_S:
            _emit_runner_event(
                job_id=job_id,
                tool=_TOOL_NAME,
                phase="running",
                elapsed_s=elapsed,
                eta_s=max(0.0, float(timeout_s) - elapsed),
                log_tail=f"job status: {status}",
            )
            last_emit_at = now

        time.sleep(interval_s)
    else:
        _emit_runner_event(
            job_id=job_id,
            tool=_TOOL_NAME,
            phase="failed",
            elapsed_s=time.time() - started_at,
            log_tail=f"timed out after {timeout_s}s (last status={last_status!r})",
        )
        raise TimeoutError(
            f"Superbio job {job_id} did not finish within {timeout_s}s "
            f"(last status={last_status!r})."
        )

    download_dir = _run_dir(context) / "outputs" / "generated" / "external" / "alphafold2" / "structures"
    download_dir.mkdir(parents=True, exist_ok=True)
    # Superbio client strips leading '/' from path_to_download_to, turning absolute paths
    # into relative ones. Workaround: chdir into the destination and pass "." so the
    # strip is a no-op and files land in the right place.
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
        job_id=job_id,
        tool=_TOOL_NAME,
        phase="done",
        elapsed_s=time.time() - started_at,
        payload={
            "structure_predictions_dir": str(download_dir),
            "files": files,
        },
    )
    return {"structure_predictions": str(download_dir)}


def _scan_predictions(prediction_dir: Path) -> dict[str, Any]:
    pdb_files = sorted(prediction_dir.rglob("*.pdb"))
    cif_files = sorted(prediction_dir.rglob("*.cif"))
    confidence_files = sorted(
        list(prediction_dir.rglob("*plddt*.json"))
        + list(prediction_dir.rglob("*confidence*.json"))
        + list(prediction_dir.rglob("ranking_debug*.json"))
    )
    return {
        "pdb_files": [str(p.relative_to(prediction_dir)) for p in pdb_files],
        "cif_files": [str(p.relative_to(prediction_dir)) for p in cif_files],
        "confidence_files": [str(p.relative_to(prediction_dir)) for p in confidence_files],
    }


def summarize_structures(inputs, context):
    prediction_dir = Path(str(inputs["structure_predictions"]))
    if not prediction_dir.exists():
        raise FileNotFoundError(f"structure_predictions directory not found: {prediction_dir}")

    scan = _scan_predictions(prediction_dir)

    failed_checks: list[str] = []
    warnings: list[str] = []
    remediation: list[str] = []
    missing: list[str] = []

    if not scan["pdb_files"] and not scan["cif_files"]:
        failed_checks.append("no_predicted_structures")
        missing.append("predicted_structure_pdb_or_cif")
        remediation.append("Inspect Superbio job logs; AlphaFold2 produced no PDB or CIF artifacts.")

    if not scan["confidence_files"]:
        warnings.append("AlphaFold2 confidence/pLDDT JSON not found alongside structures.")
        remediation.append("Verify the Superbio AlphaFold2 app version emitted confidence outputs.")

    overall_status = "passed" if not failed_checks and not warnings else (
        "failed" if failed_checks else "warning"
    )

    qa_report = {
        "overall_status": overall_status,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "missing_artifacts": missing,
        "recommended_remediation": remediation,
        "checklist_artifacts": [
            {"artifact_type": "protein_structure_prediction_set", "path": str(prediction_dir)},
        ],
        "metrics": {
            "n_pdb_files": len(scan["pdb_files"]),
            "n_cif_files": len(scan["cif_files"]),
            "n_confidence_files": len(scan["confidence_files"]),
        },
        "structure_files": scan,
    }
    return {"qa_report": qa_report}
