"""
Superbio.ai structure prediction submitters for Boltz-2 and Protenix.

⚠️ **STATUS (2026-05-05): Protenix and Boltz-2 are BROKEN on Superbio's
   hosted infrastructure.** Both containers crash silently after ~40s
   regardless of input format (verified across 7 Protenix attempts with
   list-JSON, single-dict JSON, PDB file, MSA-on, MSA-off and 2 Boltz-2
   attempts with reference seq1.a3m). The failure is server-side, not
   an input-format problem.

   For now, all callers should use AlphaFold2 (62bf442025b09dead5853d24)
   via :class:`tools.superbio_tool.SuperbioTool` instead. AF2 has a
   confirmed working path (job 69f8fbdff5b5f7da20571936, ~56 min runtime,
   ubiquitin smoke pLDDT 94-95).

   Once Superbio fixes the Protenix/Boltz-2 containers, the helpers below
   will work as-is — they already encode the two non-obvious quirks
   needed for correct submission:

     1. **mode_id mapping is app-specific.** Protenix and Boltz-2 only
        accept ``mode_id=1``. The Superbio SDK maps ``running_mode='gpu'``
        to ``mode_id=2`` (works for AF2 but REJECTED by Protenix/Boltz-2),
        so we pass ``running_mode='cpu'`` — which the SDK maps to
        ``mode_id=1``, the actual GPU mode for these two apps.

     2. **Protenix expects a JSON LIST of structures**, each with a
        top-level ``name`` and ``sequences`` list. The older format
        (single dict with ``sequences`` and ``modelSeeds``) silently
        uploaded but caused the container to crash before output.

Public API:
    submit_protenix_prediction(...)  → submit a Protenix job (CURRENTLY UNUSABLE)
    build_protenix_input_json(...)   → build a Protenix input JSON file
    submit_boltz2_prediction(...)    → submit a Boltz-2 job (CURRENTLY UNUSABLE)
    SUPERBIO_PROTENIX_BROKEN, SUPERBIO_BOLTZ2_BROKEN — module-level flags
        callers can check before submitting (set to True until verified
        working again)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

# App IDs — kept in sync with tools.superbio_tool.APP_IDS.
PROTENIX_APP_ID = "687040d3fd98cd3abe210102"
BOLTZ2_APP_ID = "688c728099fcc1d511509092"

# For these two apps the SDK string "cpu" maps to mode_id=1, which the
# app schema labels as `label_as_gpu: true`. Don't change this without
# verifying mode_id in the resulting job record.
_GPU_MODE_FOR_PROTENIX_BOLTZ2 = "cpu"

# Module-level flags reflecting Superbio infrastructure status.
# Re-verify by re-running tests; flip to False once a job completes successfully.
SUPERBIO_PROTENIX_BROKEN = True   # 2026-05-05: 7/7 test jobs failed with tar.gz error
SUPERBIO_BOLTZ2_BROKEN = True     # 2026-05-05: 2/2 test jobs failed with tar.gz error
SUPERBIO_AF2_WORKING = True       # confirmed via job 69f8fbdff5b5f7da20571936


def _client():
    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        raise RuntimeError(
            "SUPERBIO_TOKEN / SUPERBIO_USER_ID not set in environment. "
            "Re-extract from app.superbio.ai cookies and update .env."
        )
    from superbio import Client
    return Client(token=token, user_id=user_id)


def build_protenix_input_json(
    *,
    name: str,
    chains: list[dict[str, Any]],
    output_path: Optional[str | Path] = None,
) -> Path:
    """Build a Protenix-compatible input JSON file for one complex.

    Parameters
    ----------
    name:
        Identifier for this prediction (becomes the structure name).
    chains:
        List of chain spec dicts, each like:
        ``{"sequence": "MQIFV...", "count": 1, "id": ["A"]}``
        for proteins. For DNA/RNA/ligand support, pass directly as the
        target dict (e.g. ``{"_kind": "dnaSequence", "sequence": ..., ...}``);
        the ``_kind`` key gets popped and used as the wrapping field.
        Default kind is ``proteinChain``.
    output_path:
        Where to write the JSON. Defaults to ``./{name}_protenix_input.json``.

    Returns
    -------
    Path to the written JSON file.
    """
    sequences: list[dict[str, Any]] = []
    for ch in chains:
        kind = ch.pop("_kind", "proteinChain") if isinstance(ch, dict) else "proteinChain"
        sequences.append({kind: ch})

    payload = [{"name": name, "sequences": sequences}]

    if output_path is None:
        output_path = Path(f"{name}_protenix_input.json")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    return output_path


def submit_protenix_prediction(
    *,
    input_json_path: str | Path,
    n_samples: int = 5,
    n_steps: int = 200,
    n_cycles: int = 10,
    use_msa: bool = True,
    seeds: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Submit a Protenix structure prediction job to Superbio.

    Parameters
    ----------
    input_json_path:
        Path to the Protenix input JSON (use :func:`build_protenix_input_json`).
    n_samples, n_steps, n_cycles:
        Diffusion sampling parameters. Defaults match Protenix's recommended
        production setting (5 samples, 200 steps, 10 cycles ≈ 5–8 min on GPU
        for a small heterodimer).
    use_msa:
        Whether to compute an MSA for each chain (recommended True; doubles
        runtime).
    seeds:
        Optional list of integer seeds for reproducibility.

    Returns
    -------
    dict with ``job_id`` (and other API-returned fields).
    """
    p = Path(input_json_path)
    if not p.exists():
        raise FileNotFoundError(f"Protenix input JSON not found: {p}")

    config: dict[str, Any] = {
        "n_samples": int(n_samples),
        "n_steps": int(n_steps),
        "n_cycles": int(n_cycles),
        "use_msa": bool(use_msa),
    }
    if seeds:
        config["seeds"] = ",".join(str(int(s)) for s in seeds)

    client = _client()
    return client.post_job(
        app_id=PROTENIX_APP_ID,
        running_mode=_GPU_MODE_FOR_PROTENIX_BOLTZ2,  # "cpu" → mode_id=1 (GPU for Protenix)
        config=config,
        local_files={"structure_file": str(p)},
        validate=False,  # Protenix's parameter_settings dict is empty → SDK validate raises KeyError
    )


def submit_alphafold2_prediction(
    *,
    name: str,
    sequence: str,
    model_preset: str = "monomer",
    extra_chains: Optional[list[tuple[str, str]]] = None,
) -> dict[str, Any]:
    """Submit an AlphaFold2 structure prediction job to Superbio.

    This is the **working fallback path** while Protenix and Boltz-2 are
    broken on Superbio's hosted infrastructure (verified 2026-05-05).

    Parameters
    ----------
    name:
        Identifier for the prediction (becomes the chain name in Superbio's
        ``aa_pairs`` config).
    sequence:
        Single-letter amino-acid sequence (no gaps, uppercase).
    model_preset:
        ``"monomer"`` (single chain) or ``"multimer"`` (paired complex).
        For ``multimer``, pass the second chain via ``extra_chains``.
    extra_chains:
        Optional list of ``(name, sequence)`` tuples for the additional
        chains in a multimer prediction. Ignored if ``model_preset='monomer'``.

    Returns
    -------
    dict with ``job_id``.

    Notes
    -----
    AF2 uses ``running_mode='gpu'`` (mode_id=2), the inverse of
    Protenix/Boltz-2. The config shape is the canonical Superbio one:
    ``{"aa_pairs": [{name1: sequence1}, {name2: sequence2}, ...]}``.
    Reference: working job ``69f8fbdff5b5f7da20571936`` (ubiquitin
    monomer, pLDDT 94-95, ~56 min runtime).
    """
    if not sequence or not sequence.strip():
        raise ValueError("sequence must be a non-empty amino-acid string")

    aa_pairs: list[dict[str, str]] = [{name: sequence.strip().upper()}]
    if model_preset == "multimer" and extra_chains:
        for chain_name, chain_seq in extra_chains:
            if chain_seq and chain_seq.strip():
                aa_pairs.append({chain_name: chain_seq.strip().upper()})

    config: dict[str, Any] = {
        "aa_pairs": aa_pairs,
        "model_preset": model_preset,
    }

    client = _client()
    return client.post_job(
        app_id="62bf442025b09dead5853d24",  # AlphaFold2
        running_mode="gpu",  # mode_id=2 for AF2 (different from Protenix/Boltz-2!)
        config=config,
        local_files={},
        validate=False,  # bypass SDK's KeyError on apps with empty parameter_settings
    )


def submit_boltz2_prediction(
    *,
    msa_file_path: Optional[str | Path] = None,
    batch_csv_path: Optional[str | Path] = None,
    template_cif_paths: Optional[list[str | Path]] = None,
) -> dict[str, Any]:
    """Submit a Boltz-2 structure prediction job to Superbio.

    Boltz-2 accepts:
      - a single ``.a3m`` MSA file (single-chain prediction; auto-MSA toggles
        on if no file is given), OR
      - a ``.csv`` batch file describing one or more multi-chain complexes,
        OR
      - one or more ``.cif`` template files for templated prediction.

    Note: The exact CSV column schema is documented only in Superbio's web
    UI demo download. If batch submission fails, fall back to Protenix
    (which has a well-documented JSON input format) for multi-chain work.
    """
    local_files: dict[str, str] = {}
    if msa_file_path:
        p = Path(msa_file_path)
        if not p.exists():
            raise FileNotFoundError(f"MSA file not found: {p}")
        local_files["input_msa_file"] = str(p)
    if batch_csv_path:
        p = Path(batch_csv_path)
        if not p.exists():
            raise FileNotFoundError(f"Batch CSV not found: {p}")
        local_files["input_batch_file"] = str(p)
    if template_cif_paths:
        # Multi-file slot — SDK accepts a list of paths under one key.
        paths = [Path(t) for t in template_cif_paths]
        for t in paths:
            if not t.exists():
                raise FileNotFoundError(f"Template CIF not found: {t}")
        local_files["input_template_file"] = [str(t) for t in paths]  # type: ignore[assignment]

    if not local_files:
        raise ValueError(
            "submit_boltz2_prediction needs at least one input "
            "(msa_file_path, batch_csv_path, or template_cif_paths)."
        )

    client = _client()
    return client.post_job(
        app_id=BOLTZ2_APP_ID,
        running_mode=_GPU_MODE_FOR_PROTENIX_BOLTZ2,  # "cpu" → mode_id=1 (GPU for Boltz-2)
        config={},
        local_files=local_files,
        validate=False,  # Boltz-2's parameter_settings is empty → same KeyError quirk as Protenix
    )
