"""
CLUE / CMAP / L1000 connectivity API tool.

Wraps the CLUE Touchstone L1000 connectivity gateway for Track C of the
muscle-rejuvenation novokine RL pipeline. Given a predicted up/down gene
signature for a candidate novokine, the CLUE service returns a list of
perturbagen signatures with `tau ∈ [-100, +100]`:

  - tau > +90: the perturbagen produces a transcriptional shift SIMILAR to
    the query (use as Track C reward signal — the candidate "looks like" a
    rejuvenating perturbagen if known senolytics/CR-mimetics dominate the
    high-tau bucket).
  - tau < -90: the perturbagen REVERSES the query.

Public docs: https://clue.io/connectopedia/clue_api_tutorial
Base URL:    https://api.clue.io/api
Auth:        header `user_key: <CMAP_API_KEY>`

Live API contract (verified 2026-05-04 via the LoopBack swagger at
``/explorer/resources``):

  POST /api/jobs                    submit a connectivity query, returns job_id
  GET  /api/jobs/{id}               poll for status  (status='completed' when done)
  GET  /api/perts?filter=...        read-only perturbagen lookup
  GET  /api/sig_tools               list of analysis tools (sig_queryl1k_tool, etc.)

The relevant `tool_id` for an L1000 connectivity query is
``sig_queryl1k_tool`` (newer; ``sig_query_tool`` is the legacy variant).
Job ``params`` use the `(uptag|dntag)-cmapfile` text-blob format that
CLUE inherited from the v1 connectivity tool.

Modes
-----
  CMAP_MODE unset OR "mock"  → deterministic mock responses (default).
  CMAP_MODE = "live"         → CMAP_API_KEY required; submits real jobs to
                                api.clue.io and polls until completion.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Literal, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

try:
    import requests  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — requests is in backend deps
    requests = None  # type: ignore[assignment]

from .contracts import (
    blocked_result,
    execution_error_result,
    invalid_input_result,
    json_to_pretty_text,
    success_result,
)

_BASE_URL = "https://api.clue.io/api"
_JOBS_URL = f"{_BASE_URL}/jobs"
_PERTS_URL = f"{_BASE_URL}/perts"
_SIG_TOOLS_URL = f"{_BASE_URL}/sig_tools"
_L1000_QUERY_TOOL_ID = "sig_queryl1k_tool"
_DEFAULT_DATA_TYPE = "L1000"
_DEFAULT_DATASET = "Touchstone"
_MAX_SUMMARY = 50_000
_MAX_GENES_TOTAL = 200  # L1000 hard cap is ~150 each side; we bound the union
_DEFAULT_POLL_TIMEOUT_S = 1800  # 30 min — typical CLUE L1000 query latency
_DEFAULT_POLL_INTERVAL_S = 20
_HTTP_TIMEOUT_S = 30
# Status strings returned by api.clue.io/api/jobs.status — verified via swagger
# definitions/job and through the public Connectopedia docs. We treat anything
# not in success/failure as still-running.
_SUCCESS_STATES = {"completed", "succeeded", "success", "done"}
_FAILURE_STATES = {"failed", "error", "cancelled", "canceled", "timeout", "killed"}

ActionType = Literal["query_signature", "lookup_perturbagen"]

# Curated mock perturbagen pool (used in mock mode only). Names chosen to
# overlap the rejuvenating / senescence reference lists in the cmap_query
# SKILL so downstream Track C scoring has hits to find.
_MOCK_PERTURBAGEN_POOL: list[dict[str, str]] = [
    {"pert_id": "BRD-K12345678", "pert_iname": "sirolimus",   "moa": "MTOR inhibitor",        "target": "MTOR"},
    {"pert_id": "BRD-K23456789", "pert_iname": "rapamycin",   "moa": "MTOR inhibitor",        "target": "MTOR"},
    {"pert_id": "BRD-K34567890", "pert_iname": "metformin",   "moa": "AMPK activator",        "target": "PRKAA1"},
    {"pert_id": "BRD-K45678901", "pert_iname": "resveratrol", "moa": "SIRT1 activator",       "target": "SIRT1"},
    {"pert_id": "BRD-K56789012", "pert_iname": "dasatinib",   "moa": "Senolytic / SRC inh.",  "target": "SRC"},
    {"pert_id": "BRD-K67890123", "pert_iname": "quercetin",   "moa": "Senolytic flavonoid",   "target": "BCL2L1"},
    {"pert_id": "BRD-K78901234", "pert_iname": "navitoclax",  "moa": "BCL-2 family inhibitor","target": "BCL2"},
    {"pert_id": "BRD-K89012345", "pert_iname": "fisetin",     "moa": "Senolytic flavonoid",   "target": "BCL2L1"},
    {"pert_id": "BRD-K90123456", "pert_iname": "NMN",         "moa": "NAD+ precursor",        "target": "NAMPT"},
    {"pert_id": "BRD-K01234567", "pert_iname": "NAD",         "moa": "NAD+ cofactor",         "target": "NAMPT"},
    {"pert_id": "BRD-K11122233", "pert_iname": "etoposide",   "moa": "Topo II inhibitor / SASP", "target": "TOP2A"},
    {"pert_id": "BRD-K22233344", "pert_iname": "doxorubicin", "moa": "Topo II inhibitor / SASP", "target": "TOP2A"},
    {"pert_id": "BRD-K33344455", "pert_iname": "palbociclib", "moa": "CDK4/6 inhibitor",      "target": "CDK4"},
    {"pert_id": "BRD-K44455566", "pert_iname": "bleomycin",   "moa": "DNA damage / SASP",     "target": "DNA"},
    {"pert_id": "BRD-K55566677", "pert_iname": "ionizing-radiation-sig", "moa": "DNA damage / SASP", "target": "DNA"},
    {"pert_id": "BRD-K66677788", "pert_iname": "vorinostat",  "moa": "HDAC inhibitor",        "target": "HDAC1"},
    {"pert_id": "BRD-K77788899", "pert_iname": "trichostatin-a","moa": "HDAC inhibitor",      "target": "HDAC1"},
    {"pert_id": "BRD-K88899900", "pert_iname": "geldanamycin","moa": "HSP90 inhibitor",       "target": "HSP90AA1"},
    {"pert_id": "BRD-K99900011", "pert_iname": "wortmannin",  "moa": "PI3K inhibitor",        "target": "PIK3CA"},
    {"pert_id": "BRD-K10011122", "pert_iname": "ly294002",    "moa": "PI3K inhibitor",        "target": "PIK3CA"},
]


def _http() -> Any:
    if requests is None:
        raise RuntimeError(
            "The `requests` package is required for CMAP_MODE=live but is "
            "not installed in this environment."
        )
    return requests


def _gene_blob(genes: list[str]) -> str:
    """CLUE's `(up|dn)tag-cmapfile` field expects a newline-separated text blob."""
    return "\n".join(g.strip().upper() for g in genes if g and g.strip())


def _live_submit_query(
    *,
    api_key: str,
    name: str,
    up_genes: list[str],
    down_genes: list[str],
    cell_lines: Optional[list[str]],
    tool_id: str = _L1000_QUERY_TOOL_ID,
    data_type: str = _DEFAULT_DATA_TYPE,
    dataset: str = _DEFAULT_DATASET,
) -> dict[str, Any]:
    """Submit a Touchstone L1000 connectivity job. Returns the API job document
    (must contain ``id`` / ``job_id``) — does not poll.
    """
    http = _http()
    params: dict[str, Any] = {
        "name": name,
        "tag": name,
        "data_type": data_type,
        "uptag-cmapfile": _gene_blob(up_genes),
        "dntag-cmapfile": _gene_blob(down_genes),
    }
    if cell_lines:
        params["cell_id"] = list(cell_lines)
    body = {
        "name": name,
        "tag": name,
        "tool_id": tool_id,
        "data_type": data_type,
        "dataset": dataset,
        "params": params,
    }
    headers = {"user_key": api_key, "Content-Type": "application/json"}
    resp = http.post(_JOBS_URL, json=body, headers=headers, timeout=_HTTP_TIMEOUT_S)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"CLUE submit returned HTTP {resp.status_code}: {resp.text[:500]}"
        )
    job = resp.json()
    job_id = job.get("id") or job.get("job_id")
    if not job_id:
        raise RuntimeError(
            f"CLUE submit returned no job id; raw response: {json.dumps(job)[:500]}"
        )
    return job


def _live_poll_job(
    *,
    api_key: str,
    job_id: str,
    timeout_s: int,
    interval_s: int,
) -> dict[str, Any]:
    """Poll ``GET /api/jobs/{id}`` until terminal state or deadline."""
    http = _http()
    headers = {"user_key": api_key}
    deadline = time.time() + timeout_s
    last_doc: dict[str, Any] = {}
    while time.time() < deadline:
        resp = http.get(
            f"{_JOBS_URL}/{job_id}",
            headers=headers,
            timeout=_HTTP_TIMEOUT_S,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"CLUE poll {job_id} returned HTTP {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        last_doc = resp.json() or {}
        status = str(last_doc.get("status") or "").lower()
        if status in _SUCCESS_STATES:
            return last_doc
        if status in _FAILURE_STATES:
            raise RuntimeError(
                f"CLUE job {job_id} terminated with status={status!r}: "
                f"{last_doc.get('errorMessage') or last_doc.get('error') or ''}"
            )
        time.sleep(interval_s)
    raise TimeoutError(
        f"CLUE job {job_id} did not reach a terminal state within {timeout_s}s; "
        f"last status={last_doc.get('status')!r}"
    )


# GCT format: https://clue.io/connectopedia/gct_format
# A v1.3 GCT is tab-separated with this layout:
#   line 1: '#1.3'
#   line 2: <n_data_rows>\t<n_data_cols>\t<n_row_metadata>\t<n_col_metadata>
#   line 3: 'id' + <row_metadata_field_names> + <column_ids>
#   lines 4..3+n_col_metadata: <col_metadata_field_name> + (n_row_metadata blanks) + <col_metadata_values>
#   lines 4+n_col_metadata..end: <row_id> + <row_metadata_values> + <data_values>
# CLUE's connectivity output puts perturbagen identity in row metadata
# (`pert_iname`, `pert_id`, `moa`, `target`) and tau / fdr_q_nlog10 as
# column-summary values (per-cell-line columns plus a 'summary' column).
_PERT_ROW_METADATA_FIELDS = (
    "pert_id", "pert_iname", "pert_type", "moa", "target",
    "cell_iname", "pert_idose", "pert_itime",
)


def _parse_gct(text: str) -> dict[str, Any]:
    """Parse a v1.x GCT text into a structured dict.

    Returns:
        {
          "version": "1.3",
          "n_rows": int, "n_cols": int,
          "n_row_metadata": int, "n_col_metadata": int,
          "row_metadata_fields": [...],
          "col_metadata_fields": [...],
          "column_ids": [...],
          "rows": [{"id": "...", "row_metadata": {...}, "data": [...]}, ...],
        }
    """
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    if not lines:
        raise ValueError("GCT text is empty.")
    ver_line = lines[0].strip()
    if not ver_line.startswith("#1."):
        raise ValueError(f"Not a GCT file (expected '#1.x' header, got {ver_line!r}).")
    version = ver_line.lstrip("#").strip()

    dims = lines[1].split("\t")
    if len(dims) < 2:
        raise ValueError(f"GCT dimensions line malformed: {lines[1]!r}")
    n_rows = int(dims[0])
    n_cols = int(dims[1])
    n_row_meta = int(dims[2]) if len(dims) >= 3 else 0
    n_col_meta = int(dims[3]) if len(dims) >= 4 else 0

    header = lines[2].split("\t")
    if len(header) != 1 + n_row_meta + n_cols:
        raise ValueError(
            f"GCT header has {len(header)} fields; expected 1 + {n_row_meta} + {n_cols}"
        )
    row_meta_fields = header[1 : 1 + n_row_meta]
    column_ids = header[1 + n_row_meta :]

    col_metadata_fields: list[str] = []
    col_metadata_values: list[list[str]] = []  # parallel to fields; each entry has n_cols values
    for i in range(n_col_meta):
        parts = lines[3 + i].split("\t")
        if len(parts) != 1 + n_row_meta + n_cols:
            raise ValueError(f"GCT column metadata row {i} malformed.")
        field_name = parts[0]
        values = parts[1 + n_row_meta :]
        col_metadata_fields.append(field_name)
        col_metadata_values.append(values)

    data_start = 3 + n_col_meta
    rows: list[dict[str, Any]] = []
    for line in lines[data_start : data_start + n_rows]:
        parts = line.split("\t")
        if len(parts) < 1 + n_row_meta:
            continue
        row_id = parts[0]
        row_meta = {row_meta_fields[i]: parts[1 + i] for i in range(n_row_meta) if (1 + i) < len(parts)}
        raw_data = parts[1 + n_row_meta :]
        data: list[Optional[float]] = []
        for v in raw_data:
            try:
                data.append(float(v))
            except (ValueError, TypeError):
                data.append(None)
        rows.append({"id": row_id, "row_metadata": row_meta, "data": data})

    # Re-shape column metadata into per-column dicts for convenience.
    col_metadata: list[dict[str, str]] = []
    for c_idx in range(n_cols):
        meta: dict[str, str] = {}
        for f_idx, field in enumerate(col_metadata_fields):
            try:
                meta[field] = col_metadata_values[f_idx][c_idx]
            except IndexError:
                pass
        col_metadata.append(meta)

    return {
        "version": version,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "n_row_metadata": n_row_meta,
        "n_col_metadata": n_col_meta,
        "row_metadata_fields": row_meta_fields,
        "col_metadata_fields": col_metadata_fields,
        "column_ids": column_ids,
        "column_metadata": col_metadata,
        "rows": rows,
    }


def _gct_summary_column_index(parsed: dict[str, Any]) -> int:
    """Pick the 'summary' column from a CLUE connectivity GCT.

    CLUE places a per-cell-line column for each cell line plus a single
    summary column (typically named 'summary' or 'all'). When no explicit
    summary column is found, fall back to the first column.
    """
    column_ids = parsed.get("column_ids") or []
    for i, cid in enumerate(column_ids):
        if isinstance(cid, str) and cid.strip().lower() in ("summary", "all", "consensus"):
            return i
    # Some snapshots use a column metadata field 'cell_iname' = 'summary'
    col_metadata = parsed.get("column_metadata") or []
    for i, meta in enumerate(col_metadata):
        for v in (meta or {}).values():
            if isinstance(v, str) and v.strip().lower() in ("summary", "all", "consensus"):
                return i
    return 0


def _parse_clue_result_tarball(
    tarball_source: str,
    *,
    api_key: Optional[str] = None,
    top_n: int = 25,
    bottom_n: int = 25,
) -> dict[str, Any]:
    """Download (if URL) and parse a CLUE query result tarball.

    The tarball typically contains ``query_result.gct`` plus auxiliary
    config / summary files. Returns a structured payload with the top-N
    perturbagens by tau (mimics) and bottom-N perturbagens (reversers).
    """
    if requests is None:
        raise RuntimeError("requests not installed; cannot download CLUE result tarball.")

    # Resolve to a local path
    is_url = tarball_source.startswith("http://") or tarball_source.startswith("https://")
    cleanup_path: Optional[str] = None
    if is_url:
        headers = {"user_key": api_key} if api_key else {}
        resp = requests.get(tarball_source, headers=headers, timeout=120, stream=True)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"CLUE result download HTTP {resp.status_code}: {resp.text[:500]}"
            )
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
        cleanup_path = tmpf.name
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if chunk:
                tmpf.write(chunk)
        tmpf.close()
        local_path = tmpf.name
    else:
        local_path = tarball_source

    try:
        gct_member_text: Optional[str] = None
        gct_member_name: Optional[str] = None
        try:
            with tarfile.open(local_path, "r:*") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    if member.name.endswith("query_result.gct") or member.name.endswith(".gct"):
                        f = tar.extractfile(member)
                        if f is None:
                            continue
                        raw = f.read()
                        try:
                            gct_member_text = raw.decode("utf-8", errors="replace")
                        except Exception:
                            gct_member_text = raw.decode("latin-1", errors="replace")
                        gct_member_name = member.name
                        if member.name.endswith("query_result.gct"):
                            break  # prefer query_result.gct over other gcts
        except tarfile.ReadError as exc:
            raise RuntimeError(f"Could not open {local_path} as a tarball: {exc}") from exc

        if not gct_member_text:
            raise RuntimeError(
                f"No .gct file found inside {Path(local_path).name}; "
                "tarball does not look like a CLUE connectivity result."
            )

        parsed = _parse_gct(gct_member_text)
        summary_idx = _gct_summary_column_index(parsed)

        # Each row is one perturbagen signature
        signatures: list[dict[str, Any]] = []
        for row in parsed.get("rows") or []:
            data = row.get("data") or []
            tau_val = data[summary_idx] if summary_idx < len(data) else None
            row_meta = row.get("row_metadata") or {}
            sig: dict[str, Any] = {
                "row_id": row.get("id"),
                "tau": tau_val,
            }
            for field in _PERT_ROW_METADATA_FIELDS:
                if field in row_meta:
                    sig[field] = row_meta[field]
            signatures.append(sig)

        # Filter out signatures with missing tau, then sort
        with_tau = [s for s in signatures if isinstance(s.get("tau"), (int, float))]
        with_tau.sort(key=lambda s: s["tau"], reverse=True)

        top = with_tau[:top_n]
        bottom = list(reversed(with_tau[-bottom_n:])) if bottom_n > 0 else []

        return {
            "tarball_source": tarball_source,
            "gct_file": gct_member_name,
            "version": parsed.get("version"),
            "n_signatures_total": len(signatures),
            "n_signatures_with_tau": len(with_tau),
            "summary_column_index": summary_idx,
            "summary_column_id": (parsed.get("column_ids") or [None])[summary_idx]
                if summary_idx < len(parsed.get("column_ids") or []) else None,
            "top_signatures": top,
            "bottom_signatures": bottom,
            "row_metadata_fields": parsed.get("row_metadata_fields"),
            "tau_range": [-100.0, 100.0],
        }
    finally:
        if cleanup_path:
            try:
                os.unlink(cleanup_path)
            except OSError:
                pass


def _live_lookup_perturbagen(
    *,
    api_key: str,
    pert_id: str,
) -> dict[str, Any]:
    """Look up a single BRD-* identifier via the read-only perts endpoint."""
    http = _http()
    headers = {"user_key": api_key}
    flt = {"where": {"pert_id": pert_id}, "limit": 1}
    resp = http.get(
        _PERTS_URL,
        params={"filter": json.dumps(flt)},
        headers=headers,
        timeout=_HTTP_TIMEOUT_S,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"CLUE perts lookup returned HTTP {resp.status_code}: "
            f"{resp.text[:500]}"
        )
    rows = resp.json() or []
    if not rows:
        return {
            "pert_id": pert_id,
            "found": False,
            "source": "CLUE / api.clue.io/api/perts",
        }
    row = rows[0]
    return {
        "pert_id": row.get("pert_id") or pert_id,
        "pert_iname": row.get("pert_iname"),
        "pert_type": row.get("pert_type") or "trt_cp",
        "moa": row.get("moa"),
        "target": row.get("target"),
        "canonical_smiles": row.get("canonical_smiles"),
        "inchi_key": row.get("inchi_key"),
        "alt_name": row.get("alt_name"),
        "molecular_formula": row.get("molecular_formula"),
        "logp": row.get("logp"),
        "found": True,
        "source": "CLUE / api.clue.io/api/perts",
    }


def _seeded_rng(*parts: Any) -> random.Random:
    """Deterministic RNG keyed on a sha1 of the inputs."""
    h = hashlib.sha1()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x00")
    seed = int.from_bytes(h.digest()[:8], "big")
    return random.Random(seed)


def _mock_query_signature(
    up_genes: list[str],
    down_genes: list[str],
    cell_lines: Optional[list[str]],
    max_results: int,
) -> dict[str, Any]:
    rng = _seeded_rng(
        sorted(g.upper() for g in up_genes),
        sorted(g.upper() for g in down_genes),
        sorted(cl.upper() for cl in (cell_lines or [])),
    )
    pool = list(_MOCK_PERTURBAGEN_POOL)
    rng.shuffle(pool)

    n = min(max(1, max_results), len(pool))
    chosen = pool[:n]

    cell_choices = list(cell_lines) if cell_lines else ["A375", "MCF7", "PC3", "HEPG2", "VCAP"]

    signatures = []
    for pert in chosen:
        # tau in [-100, +100], two-decimal rounded
        tau = round(rng.uniform(-100.0, 100.0), 2)
        signatures.append({
            "sig_id": f"MOCK_SIG_{pert['pert_id']}_{rng.randint(1000, 9999)}",
            "pert_id": pert["pert_id"],
            "pert_iname": pert["pert_iname"],
            "pert_type": "trt_cp",
            "moa": pert["moa"],
            "target": pert["target"],
            "cell_id": rng.choice(cell_choices),
            "pert_dose": f"{rng.choice([0.1, 1.0, 3.0, 10.0])} um",
            "pert_time": f"{rng.choice([6, 24])} h",
            "tau": tau,
        })

    # Sort high-to-low by tau (CLUE convention for top connectivity)
    signatures.sort(key=lambda s: s["tau"], reverse=True)

    return {
        "mock": True,
        "query": {
            "up_genes": list(up_genes),
            "down_genes": list(down_genes),
            "cell_lines": cell_lines,
            "max_results": max_results,
        },
        "signatures": signatures,
        "n_signatures": len(signatures),
        "tau_range": [-100.0, 100.0],
        "interpretation": (
            "tau > +90: perturbagen mimics the query signature; "
            "tau < -90: perturbagen reverses the query signature."
        ),
    }


def _mock_lookup_perturbagen(pert_id: str) -> dict[str, Any]:
    rng = _seeded_rng("lookup", pert_id.upper())
    # Try to match against the curated pool first; otherwise synthesize one.
    match = next(
        (p for p in _MOCK_PERTURBAGEN_POOL if p["pert_id"].upper() == pert_id.upper()),
        None,
    )
    if match is None:
        match = {
            "pert_id": pert_id,
            "pert_iname": f"mock_compound_{pert_id[-4:].lower()}",
            "moa": "unknown",
            "target": "unknown",
        }
    return {
        "mock": True,
        "pert_id": match["pert_id"],
        "pert_iname": match["pert_iname"],
        "pert_type": "trt_cp",
        "moa": match["moa"],
        "target": match["target"],
        "canonical_smiles": None,
        "inchi_key": None,
        "num_sig": rng.randint(10, 500),
        "first_seen": "2017-01-01",
        "source": "CMAP/L1000 (mock)",
    }


class ClueApiInput(BaseModel):
    action: ActionType = Field(
        description=(
            "Which CLUE API action to invoke. "
            "'query_signature' — submit an up/down gene-set query to the "
            "L1000 Touchstone connectivity gateway and return ranked "
            "perturbagen signatures (tau ∈ [-100, +100]). "
            "'lookup_perturbagen' — fetch metadata for a single BRD-* "
            "perturbagen identifier."
        )
    )
    up_genes: Optional[list[str]] = Field(
        default=None,
        description="HGNC gene symbols expected to be UP-regulated by the candidate "
                    "(used by 'query_signature').",
    )
    down_genes: Optional[list[str]] = Field(
        default=None,
        description="HGNC gene symbols expected to be DOWN-regulated by the candidate "
                    "(used by 'query_signature').",
    )
    cell_lines: Optional[list[str]] = Field(
        default=None,
        description="Optional CMAP/L1000 cell line filter, e.g. ['A375', 'MCF7'] "
                    "(used by 'query_signature').",
    )
    max_results: int = Field(
        default=50,
        description="Max number of ranked perturbagen signatures to return "
                    "(used by 'query_signature').",
    )
    pert_id: Optional[str] = Field(
        default=None,
        description="Broad perturbagen identifier (e.g. 'BRD-K12345678') "
                    "(used by 'lookup_perturbagen').",
    )


class ClueApiTool(BaseTool):
    name: str = "clue_api"
    description: str = (
        "Query the CLUE/CMAP L1000 connectivity API for Track C of the muscle-rejuvenation "
        "RL pipeline. Actions: 'query_signature' submits an up/down gene-set to the L1000 "
        "Touchstone connectivity gateway and returns ranked perturbagens with tau ∈ [-100, "
        "+100] (tau > +90 = signature mimic; tau < -90 = signature reverser). "
        "'lookup_perturbagen' fetches metadata for a single BRD-* identifier. "
        "Reads CMAP_API_KEY from environment. CMAP_MODE='mock' (default) returns "
        "deterministic mock responses; CMAP_MODE='local' uses an offline LINCS "
        "L1000 gene-set index (Enrichr GMTs in backend/storage/lincs_cache/) and "
        "is the recommended mode for production scoring; CMAP_MODE='live' submits "
        "to https://api.clue.io/api/jobs (requires paid CLUE subscription as of 2026)."
    )
    args_schema: Type[BaseModel] = ClueApiInput
    response_format: str = "content_and_artifact"

    # ---------- env helpers ---------------------------------------------------

    def _api_key(self) -> Optional[str]:
        return os.environ.get("CMAP_API_KEY")

    def _mode(self) -> str:
        return (os.environ.get("CMAP_MODE") or "mock").strip().lower()

    # ---------- main dispatcher ----------------------------------------------

    def _run(
        self,
        action: ActionType = "query_signature",
        up_genes: Optional[list[str]] = None,
        down_genes: Optional[list[str]] = None,
        cell_lines: Optional[list[str]] = None,
        max_results: int = 50,
        pert_id: Optional[str] = None,
    ) -> tuple[str, dict]:
        try:
            if action == "query_signature":
                return self._run_query_signature(
                    up_genes=up_genes,
                    down_genes=down_genes,
                    cell_lines=cell_lines,
                    max_results=max_results,
                )
            elif action == "lookup_perturbagen":
                return self._run_lookup_perturbagen(pert_id=pert_id)
            else:
                return invalid_input_result(
                    self.name,
                    f"Unknown action: {action!r}. "
                    "Expected 'query_signature' or 'lookup_perturbagen'.",
                    metadata={"action": action},
                )
        except NotImplementedError as exc:
            # Surface the live-mode TODO clearly without crashing the agent loop.
            return blocked_result(
                self.name,
                str(exc),
                metadata={
                    "action": action,
                    "mode": self._mode(),
                    "live_endpoint": _JOBS_URL,
                },
            )
        except Exception as exc:  # defensive: never let the tool raise
            return execution_error_result(
                self.name,
                f"clue_api failure: {exc}",
                metadata={"action": action, "mode": self._mode()},
            )

    # ---------- action: query_signature --------------------------------------

    def _run_query_signature(
        self,
        up_genes: Optional[list[str]],
        down_genes: Optional[list[str]],
        cell_lines: Optional[list[str]],
        max_results: int,
    ) -> tuple[str, dict]:
        up = [g.strip().upper() for g in (up_genes or []) if g and g.strip()]
        down = [g.strip().upper() for g in (down_genes or []) if g and g.strip()]

        if not up and not down:
            return invalid_input_result(
                self.name,
                "At least one of 'up_genes' or 'down_genes' must be a non-empty list.",
                metadata={"action": "query_signature"},
            )

        total = len(up) + len(down)
        if total > _MAX_GENES_TOTAL:
            return invalid_input_result(
                self.name,
                f"Combined up_genes + down_genes = {total} exceeds maximum of "
                f"{_MAX_GENES_TOTAL} (L1000 hard cap is ~150 each side).",
                metadata={
                    "action": "query_signature",
                    "n_up": len(up),
                    "n_down": len(down),
                    "limit": _MAX_GENES_TOTAL,
                },
            )

        mode = self._mode()
        api_key = self._api_key()

        if mode == "live":
            if not api_key:
                return blocked_result(
                    self.name,
                    "CMAP_MODE=live but CMAP_API_KEY is not set in environment. "
                    "Add CMAP_API_KEY=<key> to backend/.env or set CMAP_MODE=mock.",
                    metadata={"action": "query_signature", "mode": mode},
                )
            query_name = f"miniagent_query_{int(time.time())}_{len(up):d}u_{len(down):d}d"
            job = _live_submit_query(
                api_key=api_key,
                name=query_name,
                up_genes=up,
                down_genes=down,
                cell_lines=cell_lines,
            )
            job_id = job.get("id") or job.get("job_id")
            terminal = _live_poll_job(
                api_key=api_key,
                job_id=str(job_id),
                timeout_s=_DEFAULT_POLL_TIMEOUT_S,
                interval_s=_DEFAULT_POLL_INTERVAL_S,
            )
            # If the job is complete and a download_url is present, fetch and
            # parse the GCT tarball into top/bottom-N perturbagens by tau.
            parsed_signatures: list[dict[str, Any]] = []
            parser_warnings: list[str] = []
            parser_summary: dict[str, Any] = {}
            download_url = terminal.get("download_url")
            if download_url:
                try:
                    parser_result = _parse_clue_result_tarball(
                        download_url,
                        api_key=api_key,
                        top_n=int(max_results) if max_results else 25,
                        bottom_n=int(max_results) if max_results else 25,
                    )
                    parsed_signatures = parser_result.get("top_signatures") or []
                    parser_summary = {
                        "n_signatures_total": parser_result.get("n_signatures_total"),
                        "n_signatures_with_tau": parser_result.get("n_signatures_with_tau"),
                        "summary_column_id": parser_result.get("summary_column_id"),
                        "bottom_signatures": parser_result.get("bottom_signatures") or [],
                        "gct_file": parser_result.get("gct_file"),
                    }
                except Exception as exc:  # noqa: BLE001 — surface parse failures as warnings
                    parser_warnings.append(
                        f"clue_gct_parse_failed: {type(exc).__name__}: {exc}"
                    )

            payload = {
                "live": True,
                "query": {
                    "name": query_name,
                    "up_genes": up,
                    "down_genes": down,
                    "cell_lines": cell_lines,
                    "max_results": max_results,
                },
                "job_id": job_id,
                "tool_id": _L1000_QUERY_TOOL_ID,
                "status": terminal.get("status"),
                "download_url": download_url,
                "standard_result": terminal.get("standard_result"),
                "config_path": terminal.get("config"),
                "submitted_at": job.get("created"),
                "completed_at": terminal.get("last_modified"),
                "signatures": parsed_signatures,
                "n_signatures": len(parsed_signatures),
                "tau_range": [-100.0, 100.0],
                "parser_summary": parser_summary,
                "interpretation": (
                    "Job submitted and reached a completed state."
                    + (
                        f" Result tarball parsed: {parser_summary.get('n_signatures_with_tau')} "
                        f"perturbagen signatures with tau, top {len(parsed_signatures)} returned."
                        if parsed_signatures else
                        " Result tarball not parsed; see parser_warnings or signatures=[]."
                    )
                ),
            }
            summary = (
                f"[CLUE live] Submitted {query_name} (job_id={job_id}); "
                f"final status={terminal.get('status')}.\n"
                f"download_url: {terminal.get('download_url') or '(pending)'}\n"
                f"standard_result: {terminal.get('standard_result') or '(pending)'}\n"
                f"Signatures are not parsed in-process; download and parse the "
                f"`query_result.gct` tarball for tau-ranked perturbagens.\n\n"
            )
            body, _ = json_to_pretty_text(payload, _MAX_SUMMARY - len(summary))
            meta = {
                "action": "query_signature",
                "mode": "live",
                "api_key_present": True,
                "n_up_genes": len(up),
                "n_down_genes": len(down),
                "cell_lines": cell_lines,
                "max_results": max_results,
                "tool_id": _L1000_QUERY_TOOL_ID,
                "job_id": job_id,
                "endpoint": _JOBS_URL,
            }
            warnings_combined = list(parser_warnings)
            if not terminal.get("download_url"):
                warnings_combined.append("cmap_no_download_url_yet")
            return success_result(
                self.name,
                summary + body,
                structured_payload=payload,
                warnings=warnings_combined,
                metadata=meta,
            )

        # ---- local mode (offline LINCS index) -------------------------------
        if mode == "local":
            try:
                from . import lincs_local  # local import to avoid hard dep at import time
            except ImportError as exc:
                return execution_error_result(
                    self.name,
                    f"CMAP_MODE=local but lincs_local module failed to import: {exc}",
                    metadata={"action": "query_signature", "mode": mode},
                )
            try:
                local_result = lincs_local.query_local(
                    up_genes=up,
                    down_genes=down,
                    max_results=max_results,
                )
            except FileNotFoundError as exc:
                return blocked_result(
                    self.name,
                    f"CMAP_MODE=local but LINCS GMT files are missing: {exc}",
                    metadata={"action": "query_signature", "mode": mode},
                )
            sigs = local_result.get("signatures", []) or []
            bottom = local_result.get("bottom_signatures", []) or []
            stats = local_result.get("stats", {}) or {}
            top5 = sigs[:5]
            bot5 = bottom[:5]
            top_str = ", ".join(
                f"{s.get('pert_iname','?')} (tau={s.get('tau','?')})" for s in top5
            )
            bottom_str = ", ".join(
                f"{s.get('pert_iname','?')} (tau={s.get('tau','?')})" for s in bot5
            )
            payload = {
                "live": False,
                "mode": "local",
                "query": {
                    "up_genes": up,
                    "down_genes": down,
                    "cell_lines": cell_lines,
                    "max_results": max_results,
                },
                "signatures": sigs,
                "bottom_signatures": bottom,
                "n_signatures": len(sigs),
                "n_signatures_total": local_result.get("n_signatures_total"),
                "tau_range": local_result.get("tau_range", [-100.0, 100.0]),
                "scoring_algorithm": local_result.get("scoring_algorithm"),
                "stats": stats,
                "interpretation": (
                    "Local LINCS Jaccard-overlap connectivity scorer. "
                    "tau > 0 = mimic; tau < 0 = reverser. Scores compress to "
                    "roughly [-15, +15] in practice because Jaccard overlap is "
                    "conservative; relative ranking is what Track C uses."
                ),
            }
            summary_header = (
                f"[CLUE local] L1000 connectivity query: "
                f"{len(up)} up / {len(down)} down genes → "
                f"{local_result.get('n_signatures_total', 0)} paired signatures scored.\n"
                f"Top by tau:    {top_str}\n"
                f"Bottom by tau: {bottom_str}\n"
                f"Index: {stats.get('chem_pert_signatures', 0)} chem-pert + "
                f"{stats.get('ligand_signatures', 0)} ligand signatures "
                f"(Enrichr LINCS_L1000_*).\n\n"
            )
            body, _ = json_to_pretty_text(payload, _MAX_SUMMARY - len(summary_header))
            meta = {
                "action": "query_signature",
                "mode": "local",
                "api_key_present": bool(api_key),
                "n_up_genes": len(up),
                "n_down_genes": len(down),
                "max_results": max_results,
                "n_signatures_returned": len(sigs),
                "n_signatures_total": local_result.get("n_signatures_total"),
                "scoring_algorithm": local_result.get("scoring_algorithm"),
            }
            return success_result(
                self.name,
                summary_header + body,
                structured_payload=payload,
                warnings=[],
                metadata=meta,
            )

        # ---- mock mode (default) --------------------------------------------
        payload = _mock_query_signature(
            up_genes=up,
            down_genes=down,
            cell_lines=cell_lines,
            max_results=max_results,
        )

        sigs = payload["signatures"]
        top = sigs[:5]
        bottom = sigs[-5:][::-1] if len(sigs) >= 5 else list(reversed(sigs))
        top_str = ", ".join(f"{s['pert_iname']} (tau={s['tau']})" for s in top)
        bottom_str = ", ".join(f"{s['pert_iname']} (tau={s['tau']})" for s in bottom)

        summary_header = (
            f"[CLUE mock] L1000 connectivity query: "
            f"{len(up)} up / {len(down)} down genes → "
            f"{len(sigs)} signatures returned.\n"
            f"Top by tau:    {top_str}\n"
            f"Bottom by tau: {bottom_str}\n"
            f"Interpretation: tau > +90 → mimic; tau < -90 → reverser.\n"
            f"(Mock mode — set CMAP_MODE=live and implement async polling for real CLUE results.)\n\n"
        )
        body, _ = json_to_pretty_text(payload, _MAX_SUMMARY - len(summary_header))
        summary = summary_header + body

        meta = {
            "action": "query_signature",
            "mode": "mock",
            "api_key_present": bool(api_key),
            "n_up_genes": len(up),
            "n_down_genes": len(down),
            "cell_lines": cell_lines,
            "max_results": max_results,
            "n_signatures_returned": len(sigs),
            "endpoint_when_live": _JOBS_URL,
            "base_url": _BASE_URL,
        }
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=["cmap_mock_mode"],
            metadata=meta,
        )

    # ---------- action: lookup_perturbagen -----------------------------------

    def _run_lookup_perturbagen(
        self,
        pert_id: Optional[str],
    ) -> tuple[str, dict]:
        if not pert_id or not pert_id.strip():
            return invalid_input_result(
                self.name,
                "'pert_id' is required for action='lookup_perturbagen'.",
                metadata={"action": "lookup_perturbagen"},
            )

        pert_id_clean = pert_id.strip()
        mode = self._mode()
        api_key = self._api_key()

        if mode == "live":
            if not api_key:
                return blocked_result(
                    self.name,
                    "CMAP_MODE=live but CMAP_API_KEY is not set in environment. "
                    "Add CMAP_API_KEY=<key> to backend/.env or set CMAP_MODE=mock.",
                    metadata={"action": "lookup_perturbagen", "mode": mode},
                )
            payload = _live_lookup_perturbagen(api_key=api_key, pert_id=pert_id_clean)
            payload["live"] = True
            if payload.get("found"):
                summary_header = (
                    f"[CLUE live] perturbagen {payload['pert_id']} → "
                    f"{payload.get('pert_iname')} (MoA: {payload.get('moa')}, "
                    f"target: {payload.get('target')}).\n\n"
                )
            else:
                summary_header = (
                    f"[CLUE live] No perturbagen found for {pert_id_clean!r} "
                    f"on api.clue.io/api/perts.\n\n"
                )
            body, _ = json_to_pretty_text(payload, _MAX_SUMMARY - len(summary_header))
            meta = {
                "action": "lookup_perturbagen",
                "mode": "live",
                "api_key_present": True,
                "pert_id": pert_id_clean,
                "endpoint": _PERTS_URL,
                "found": bool(payload.get("found")),
            }
            return success_result(
                self.name,
                summary_header + body,
                structured_payload=payload,
                warnings=[] if payload.get("found") else ["cmap_pert_not_found"],
                metadata=meta,
            )

        # ---- mock mode ------------------------------------------------------
        payload = _mock_lookup_perturbagen(pert_id_clean)
        summary_header = (
            f"[CLUE mock] perturbagen {payload['pert_id']} → "
            f"{payload['pert_iname']} (MoA: {payload['moa']}, target: {payload['target']}, "
            f"n_sig: {payload['num_sig']}).\n\n"
        )
        body, _ = json_to_pretty_text(payload, _MAX_SUMMARY - len(summary_header))
        summary = summary_header + body

        meta = {
            "action": "lookup_perturbagen",
            "mode": "mock",
            "api_key_present": bool(api_key),
            "pert_id": pert_id_clean,
            "base_url": _BASE_URL,
        }
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=["cmap_mock_mode"],
            metadata=meta,
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
