"""Python executors for the Protenix (Superbio) workflow.

Spec: workflows/protenix.yaml

Protenix is ByteDance's open-source AlphaFold3 reproduction.  It accepts a JSON
input describing a multi-chain complex in AF3 format and returns predicted CIF
structures with per-residue pLDDT and per-interface ipTM scores.

Three step functions:
  - validate_and_prepare_input : normalize sequence JSON/FASTA into a Protenix
    AF3-style JSON; supports multi-chain complexes (ideal for novokine+ECD ternary).
  - poll_and_download : wait for the Superbio Protenix job and materialize outputs.
  - summarize_structures : produce a structured qa_report from downloaded CIF/JSON.

Superbio Protenix app ID: 687040d3fd98cd3abe210102
File key for input: ``structure_file`` (JSON/PDB/CIF, required, supports multiple files)
Config params: n_samples (int, default 5), n_steps (int, default 200), n_cycles (int, default 10)

Protenix JSON format (ByteDance/Protenix GitHub — examples/example.json):
The top level is a LIST of prediction jobs.  Each entry has a ``name`` and a
``sequences`` list.  Each chain entry has a typed wrapper (``proteinChain``,
``dnaSequence``, ``rnaSequence``, ``ligand``) and must include an explicit
``id`` list whose length matches ``count``.

  [
    {
      "name": "complex_name",
      "sequences": [
        {"proteinChain": {"sequence": "MKLR...", "count": 1, "id": ["A"]}},
        {"proteinChain": {"sequence": "MVKV...", "count": 1, "id": ["B"]}}
      ]
    }
  ]

The Superbio-hosted Protenix app generates MSAs server-side, so the local
``msa`` block from the GitHub example is omitted here.
``modelSeeds`` is NOT part of the JSON — it is forwarded as an app config
parameter (n_samples / n_steps / n_cycles handle the diffusion sampling).
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
_TOOL_NAME = "protenix"

# Novokine validation thresholds (from novokine_validation SKILL.md v1.1)
_IPTM_WARN_THRESHOLD = 0.75
_PLDDT_WARN_THRESHOLD = 0.80


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


def _build_protenix_json(records: list[dict[str, str]], complex_name: str) -> list[dict[str, Any]]:
    """Build Protenix AF3-style input JSON from normalized chain records.

    Format: ByteDance/Protenix examples/example.json — top-level LIST of jobs.
    Each chain becomes one ``proteinChain`` entry with count=1 and a unique id.
    Chain IDs are assigned alphabetically (A, B, C, ...).
    """
    sequences = []
    for idx, rec in enumerate(records):
        chain_id = chr(65 + idx)  # A, B, C, ...
        sequences.append({
            "proteinChain": {
                "sequence": rec["sequence"],
                "count": 1,
                "id": [chain_id],
            }
        })
    return [{"name": complex_name, "sequences": sequences}]


def validate_and_prepare_input(inputs, context):
    raw_path = _resolve_input_path(context, inputs["sequence_set"])
    if not raw_path.exists():
        raise FileNotFoundError(f"sequence_set artifact not found: {raw_path}")

    records = _normalize_sequence_set(raw_path)
    complex_name = "_".join(rec["protein_name"] for rec in records)[:64] or "complex"

    protenix_input = _build_protenix_json(records, complex_name)

    out_dir = _run_dir(context) / "outputs" / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "protenix_input.json"
    out_path.write_text(json.dumps(protenix_input, indent=2))

    return {"protenix_input_file": str(out_path)}


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
            raise RuntimeError(f"Superbio Protenix job {job_id} terminated with status={status}.")

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
            f"Superbio Protenix job {job_id} did not finish within {timeout_s}s "
            f"(last status={last_status!r})."
        )

    download_dir = (
        _run_dir(context)
        / "outputs" / "generated" / "external" / "protenix" / "structures"
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
    # Protenix emits summary.json and per-seed confidence JSONs.
    confidence_files = sorted(
        list(prediction_dir.rglob("summary*.json"))
        + list(prediction_dir.rglob("*confidence*.json"))
        + list(prediction_dir.rglob("ranking*.json"))
    )
    return {
        "cif_files": [str(p.relative_to(prediction_dir)) for p in cif_files],
        "pdb_files": [str(p.relative_to(prediction_dir)) for p in pdb_files],
        "confidence_files": [str(p.relative_to(prediction_dir)) for p in confidence_files],
    }


def _parse_protenix_confidence(confidence_file: Path) -> dict[str, Any]:
    """Extract key metrics from a Protenix summary/confidence JSON.

    Protenix summary.json keys: iptm, ptm, ranking_score, atom_chain_ids,
    chain_pair_iptm, chain_pair_pae_min, chain_ptm, has_clash, num_recycles.
    Returns empty dict on parse failure (non-fatal).
    """
    try:
        data = json.loads(confidence_file.read_text())
        metrics: dict[str, Any] = {}
        # Protenix uses a list of per-seed summaries in some versions.
        if isinstance(data, list):
            data = data[0] if data else {}
        metrics["iptm"] = data.get("iptm")
        metrics["ptm"] = data.get("ptm")
        metrics["ranking_score"] = data.get("ranking_score")
        metrics["has_clash"] = data.get("has_clash")
        metrics["chain_pair_iptm"] = data.get("chain_pair_iptm")
        return {k: v for k, v in metrics.items() if v is not None}
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
        remediation.append("Inspect Superbio job logs; Protenix produced no CIF or PDB artifacts.")

    confidence_metrics: dict[str, Any] = {}
    if scan["confidence_files"]:
        confidence_metrics = _parse_protenix_confidence(
            prediction_dir / scan["confidence_files"][0]
        )
        iptm = confidence_metrics.get("iptm")
        if iptm is not None and iptm < _IPTM_WARN_THRESHOLD:
            warnings.append(
                f"Protenix ipTM={iptm:.3f} is below the novokine validation threshold (>{_IPTM_WARN_THRESHOLD})."
            )
        if confidence_metrics.get("has_clash"):
            warnings.append("Protenix reports structural clashes — inspect CIF before scoring.")
    else:
        warnings.append("Protenix confidence/summary JSON not found alongside structures.")
        remediation.append("Verify the Superbio Protenix app version emits summary.json outputs.")

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
