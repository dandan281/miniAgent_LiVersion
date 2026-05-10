"""
Stage 6 — automatic Superbio binder design submission.

For TOP_K_DESIGN tier candidates (high reward, high mechanism coherence),
submit a Binder Design with Boltz-1 job to Superbio.ai. The job:
  1. RFdiffusion samples backbones for receptor A (and receptor B if needed)
  2. ProteinMPNN designs sequences on those backbones
  3. Boltz-1 scores complex confidence (ipTM, ipSAE, complex_pLDDT)

This module wraps the Superbio SDK directly (not via the LangChain tool) so
it can be called from the rl_loop without spinning up a full agent.
Requires: SUPERBIO_TOKEN, SUPERBIO_USER_ID env vars; receptor PDB or sequence.

GATING — by design:
  - Only invoked for tier=TOP_K_DESIGN candidates with reward > 0.5.
  - Job submission writes a manifest to knowledge/design_outputs/<cid>/manifest.json
    and the returned job_id back to the experience_buffer record (via caller).
  - We do NOT poll for completion in this function — the caller can use the
    superbio tool action='status' / 'download' to retrieve results later.

USAGE:
  from utils.superbio_submit import submit_binder_design
  result = submit_binder_design(
      candidate_id="ERBB2_FGFR1__GS_med",
      receptor_A="ERBB2",
      receptor_B="FGFR1",
      target_pdb_path="path/to/erbb2_ecd.pdb",
      contigs="A1-630/0 70-100",  # ERBB2 ECD plus 70-100aa binder hotspot
      num_designs=10,
  )
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Superbio app IDs — copied from tools.superbio_tool to avoid a runtime import
# dependency on langchain.
APP_IDS = {
    "binder_design_boltz1": "6823397116b277b0d684d48e",
    "rfdiffusion":          "655b1f47a9ed6f6e5560ba8f",
    "rfdiffusion_allatom":  "6717bd220d1f1d6ba100a766",
    "proteinmpnn":          "667aae5dad736b102dd32124",
    "boltz1":               "67d2b865209a9f0952578570",
    "boltz2":               "688c728099fcc1d511509092",
    "alphafold2":           "62bf442025b09dead5853d24",
}


def _get_credentials() -> tuple[str, str] | None:
    """Pull SUPERBIO_TOKEN + SUPERBIO_USER_ID from env. Returns None if missing."""
    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        return None
    return token, user_id


def _get_design_outputs_dir(base_dir: Path | None = None) -> Path:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    out = base_dir / "knowledge" / "design_outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def submit_binder_design(
    candidate_id: str,
    receptor_A: str,
    receptor_B: str,
    target_pdb_path: Optional[str | Path] = None,
    target_sequence: Optional[str] = None,
    contigs: Optional[str] = None,
    num_designs: int = 10,
    binder_min_aa: int = 70,
    binder_max_aa: int = 100,
    model_preset: str = "multimer",
    base_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Submit a Binder Design with Boltz-1 job to Superbio.

    Args:
        candidate_id: stable identifier for the novokine candidate
        receptor_A:   primary target receptor HGNC symbol
        receptor_B:   partner receptor HGNC symbol (for record only;
                      this submission designs binders to receptor_A's ECD)
        target_pdb_path: path to the receptor_A ECD PDB file (REQUIRED for live)
        target_sequence: alternative — receptor_A ECD sequence (will require
                         PDB upload separately or use of fetch_url)
        contigs:      RFdiffusion contigs string. Default builds from
                      binder_min_aa / binder_max_aa.
        num_designs:  how many backbones to sample (default 10)
        binder_min_aa, binder_max_aa: binder length range
        model_preset: 'monomer' or 'multimer' (default 'multimer' for paired ECD)
        dry_run:      if True, build the manifest but don't submit.

    Returns dict like:
        {"submitted": bool, "job_id": str|None, "manifest_path": str,
         "error": str|None, "dry_run": bool}
    """
    out_dir = _get_design_outputs_dir(base_dir)
    cand_dir = out_dir / candidate_id
    cand_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cand_dir / "manifest.json"

    # Default contigs string if not supplied
    if contigs is None:
        contigs = f"A1-630/0 {binder_min_aa}-{binder_max_aa}"

    manifest: dict[str, Any] = {
        "candidate_id":   candidate_id,
        "receptor_A":     receptor_A,
        "receptor_B":     receptor_B,
        "app":            "binder_design_boltz1",
        "app_id":         APP_IDS["binder_design_boltz1"],
        "num_designs":    num_designs,
        "binder_min_aa":  binder_min_aa,
        "binder_max_aa":  binder_max_aa,
        "model_preset":   model_preset,
        "contigs":        contigs,
        "target_pdb_path": str(target_pdb_path) if target_pdb_path else None,
        "target_sequence": target_sequence,
        "submitted_at":   datetime.now(timezone.utc).isoformat(),
        "dry_run":        dry_run,
    }

    if dry_run:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return {
            "submitted":     False,
            "job_id":        None,
            "manifest_path": str(manifest_path),
            "error":         None,
            "dry_run":       True,
        }

    # Live submission ---------------------------------------------------------
    creds = _get_credentials()
    if creds is None:
        manifest["error"] = "missing SUPERBIO_TOKEN or SUPERBIO_USER_ID"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return {
            "submitted":     False,
            "job_id":        None,
            "manifest_path": str(manifest_path),
            "error":         manifest["error"],
            "dry_run":       False,
        }

    if target_pdb_path is None:
        manifest["error"] = "target_pdb_path required for live submission"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return {
            "submitted":     False,
            "job_id":        None,
            "manifest_path": str(manifest_path),
            "error":         manifest["error"],
            "dry_run":       False,
        }

    pdb_path = Path(target_pdb_path)
    if not pdb_path.exists():
        manifest["error"] = f"target_pdb_path not found: {pdb_path}"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return {
            "submitted":     False,
            "job_id":        None,
            "manifest_path": str(manifest_path),
            "error":         manifest["error"],
            "dry_run":       False,
        }

    token, user_id = creds
    try:
        from superbio import Client
    except ImportError as exc:
        manifest["error"] = f"superbio SDK not installed: {exc}"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return {
            "submitted":     False,
            "job_id":        None,
            "manifest_path": str(manifest_path),
            "error":         manifest["error"],
            "dry_run":       False,
        }

    try:
        client = Client(token=token, user_id=user_id)
        config = {
            "contigs":      contigs,
            "num_designs":  num_designs,
            "model_preset": model_preset,
        }
        job = client.post_job(
            app_id=APP_IDS["binder_design_boltz1"],
            running_mode="gpu",
            config=config,
            local_files={"file": str(pdb_path)},
        )
        job_id = job.get("job_id") or job.get("id") or str(job)
        manifest["job_id"]      = job_id
        manifest["job_response"] = job
        manifest["error"]       = None
    except Exception as exc:
        manifest["error"]  = f"superbio submission failed: {exc}"
        manifest["job_id"] = None

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    return {
        "submitted":     manifest["error"] is None,
        "job_id":        manifest.get("job_id"),
        "manifest_path": str(manifest_path),
        "error":         manifest.get("error"),
        "dry_run":       False,
    }


def list_pending_designs(base_dir: Path | None = None) -> list[dict[str, Any]]:
    """List manifests in design_outputs/ that haven't completed."""
    out_dir = _get_design_outputs_dir(base_dir)
    pending = []
    for cand_dir in out_dir.iterdir():
        if not cand_dir.is_dir():
            continue
        m = cand_dir / "manifest.json"
        if not m.exists():
            continue
        try:
            with open(m) as f:
                manifest = json.load(f)
            if manifest.get("job_id") and not manifest.get("completed"):
                pending.append({
                    "candidate_id": manifest.get("candidate_id"),
                    "job_id":       manifest.get("job_id"),
                    "submitted_at": manifest.get("submitted_at"),
                    "manifest":     str(m),
                })
        except Exception:
            continue
    return pending
