"""Superbio HTTP external-engine adapter.

Implements the dispatch contract documented in
``workflows/engines/superbio/alphafold2_entrypoint.md``.

A BioAPEX runtime that encounters a step with
``executor.executor_type == 'external_engine'`` and ``executor.engine_name == 'superbio'``
should call :func:`dispatch` with the resolved ``parameter_bindings`` mapping
and the step's working context. The adapter:

1. Submits a Superbio job via ``superbio.Client.post_job``.
2. Returns an ``external_job_handle`` (job_id, app_id, submitted_at, raw response)
   that downstream Python steps consume to poll and download results.

The adapter intentionally does NOT poll or download — that work belongs to a
dedicated Python step (e.g. ``workflows.runners.alphafold2.poll_and_download``)
so that BioAPEX retains structured retry / resume semantics on the long-running
half of the job.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_NAME = "superbio"


@dataclass
class JobHandle:
    """Result of a successful Superbio job submission."""

    job_id: str
    app_id: str
    app_name: str | None
    submitted_at: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_name": ENGINE_NAME,
            "job_id": self.job_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "submitted_at": self.submitted_at,
            "raw": self.raw,
        }


class SuperbioAdapterError(RuntimeError):
    """Raised when the Superbio external-engine dispatch fails."""


def _client():
    from superbio import Client  # noqa: WPS433

    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        raise SuperbioAdapterError(
            "SUPERBIO_TOKEN / SUPERBIO_USER_ID must be set in the environment "
            "to dispatch engine_name='superbio' steps."
        )
    return Client(token=token, user_id=user_id)


def _coerce_aa_pairs(raw: Any) -> list[dict[str, str]]:
    """Resolve aa_pairs into the single-key-per-dict format Superbio's structure
    apps (AlphaFold2, Boltz-1/2, Protenix) accept: ``[{<protein_name>: <sequence>}, ...]``.

    Accepts:
      - already-canonical Superbio shape: ``[{"my_seq": "MKLR..."}, ...]``
      - canonical workflow shape: ``[{"protein_name": "my_seq", "sequence": "MKLR..."}, ...]``
        (produced by ``workflows.runners.alphafold2.validate_sequence_set``)
      - path to a JSON file containing either of the above

    The Superbio AlphaFold2 app rejects the canonical-workflow shape with a
    silent failure, so this normalization is mandatory.
    """
    if isinstance(raw, (str, Path)):
        candidate = Path(str(raw))
        if candidate.exists():
            text = candidate.read_text()
        else:
            text = str(raw)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SuperbioAdapterError(
                f"aa_pairs must resolve to JSON list; got non-JSON content "
                f"(first 80 chars: {text[:80]!r}, error: {exc})"
            ) from exc
        records = parsed
    elif isinstance(raw, list):
        records = raw
    else:
        raise SuperbioAdapterError(
            f"aa_pairs has unsupported type {type(raw).__name__}; "
            "expected list or path to JSON file."
        )

    if not isinstance(records, list):
        raise SuperbioAdapterError(
            f"aa_pairs JSON must decode to a list; got {type(records).__name__}"
        )

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise SuperbioAdapterError(
                f"aa_pairs entry {idx} is not a dict (got {type(rec).__name__})"
            )
        if "protein_name" in rec and "sequence" in rec:
            name = str(rec["protein_name"]).strip()
            seq = str(rec["sequence"]).strip()
        elif len(rec) == 1:
            name, seq = next(iter(rec.items()))
            name = str(name).strip()
            seq = str(seq).strip()
        else:
            raise SuperbioAdapterError(
                f"aa_pairs entry {idx} has unexpected shape: keys={sorted(rec.keys())}; "
                "expected `{protein_name, sequence}` or `{<name>: <sequence>}`"
            )
        if not name or not seq:
            raise SuperbioAdapterError(
                f"aa_pairs entry {idx} missing protein_name or sequence."
            )
        if name in seen:
            raise SuperbioAdapterError(
                f"aa_pairs has duplicate protein_name {name!r}."
            )
        seen.add(name)
        out.append({name: seq})

    if not out:
        raise SuperbioAdapterError("aa_pairs is empty.")
    return out


_REQUIRED_BINDINGS = {"app_id"}
# Bindings consumed directly by the Client.post_job call (not part of `config`).
_DISPATCH_KEYS = {"app_id", "app_name", "running_mode"}


def submit(
    parameter_bindings: dict[str, Any],
    *,
    local_files: dict[str, str] | None = None,
) -> JobHandle:
    """Submit a Superbio job using the resolved parameter bindings.

    Parameters
    ----------
    parameter_bindings:
        Mapping from the workflow spec's ``parameter_bindings`` block AFTER
        the workflow runtime has resolved any ``{placeholder}`` references.
        Required keys:

        - ``app_id``: the Superbio app id to invoke

        Optional dispatch keys:

        - ``app_name`` (string, telemetry only)
        - ``running_mode`` (e.g. ``"gpu"``, ``"cpu"``); defaults to ``"gpu"``

        All remaining keys are forwarded to the Superbio app's ``config``
        argument verbatim, except for ``aa_pairs``, which is parsed as JSON if
        a file path or string is provided.
    local_files:
        Optional ``Client.post_job(local_files=...)`` mapping, e.g. a path to
        an h5ad atlas for scGPT apps. Not required for AlphaFold2.

    Returns
    -------
    JobHandle
    """

    missing = _REQUIRED_BINDINGS - parameter_bindings.keys()
    if missing:
        raise SuperbioAdapterError(
            f"parameter_bindings missing required keys: {sorted(missing)}"
        )

    app_id = str(parameter_bindings["app_id"])
    app_name = parameter_bindings.get("app_name")
    running_mode = str(parameter_bindings.get("running_mode") or "gpu")

    # Build the app-side config dict (everything except dispatch keys).
    config: dict[str, Any] = {}
    for key, value in parameter_bindings.items():
        if key in _DISPATCH_KEYS:
            continue
        if key == "aa_pairs":
            config[key] = _coerce_aa_pairs(value)
        else:
            config[key] = value

    client = _client()
    try:
        raw = client.post_job(
            app_id=app_id,
            running_mode=running_mode,
            config=config,
            local_files=local_files or {},
        )
    except Exception as exc:  # noqa: BLE001 — surface the underlying error verbatim
        raise SuperbioAdapterError(f"Superbio post_job failed: {exc}") from exc

    job_id = raw.get("job_id") or raw.get("id") or raw.get("_id")
    if not job_id:
        raise SuperbioAdapterError(
            f"Superbio post_job returned without a job_id; raw response: {raw!r}"
        )

    return JobHandle(
        job_id=str(job_id),
        app_id=app_id,
        app_name=str(app_name) if app_name is not None else None,
        submitted_at=datetime.now(timezone.utc).isoformat(),
        raw=raw,
    )


def get_status(job_id: str) -> str:
    return str(_client().get_job_status(job_id))


def download_results(job_id: str, destination: Path | str) -> Path:
    """Download all job results to ``destination``.

    Workaround for a bug in ``superbio.Client.download_job_result_file``: it
    calls ``path_to_download_to.strip('/')`` which silently turns absolute
    paths into relative ones (so files end up at ``./gpfs/scrubbed/...`` under
    CWD). We work around this by chdir'ing into the destination and passing
    ``.``, then restoring CWD.
    """
    import os as _os

    dest = Path(str(destination)).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    prev_cwd = _os.getcwd()
    try:
        _os.chdir(dest)
        _client().download_all_job_results(job_id=job_id, path_to_download_to=".")
    finally:
        _os.chdir(prev_cwd)
    return dest


def dispatch(
    parameter_bindings: dict[str, Any],
    *,
    context: Any = None,
    local_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Top-level entrypoint a BioAPEX runtime calls for an external_engine step.

    Returns the JobHandle as a plain dict suitable for use as the step's
    ``external_job_handle`` value output.

    The ``context`` parameter is accepted for API parity with Python step
    runners and may be used by the runtime to scope file resolution; it is
    currently unused by the Superbio dispatch path because Superbio is a
    pure HTTP backend.
    """

    del context  # unused; kept for API parity
    handle = submit(parameter_bindings, local_files=local_files)
    return handle.as_dict()


__all__ = [
    "ENGINE_NAME",
    "JobHandle",
    "SuperbioAdapterError",
    "dispatch",
    "submit",
    "get_status",
    "download_results",
]
