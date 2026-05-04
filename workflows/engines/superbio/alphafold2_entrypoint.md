# AlphaFold2 — Superbio external-engine entrypoint

This file is the declared `entrypoint` for the AlphaFold2 (Superbio) workflow
spec at `workflows/alphafold2.yaml`. It exists so that the authored workflow
spec references a real repo path without implying that the BioAPEX
external_engine adapter has Superbio-specific dispatch wired in this phase.

## Engine identity

| Field             | Value                                  |
| ----------------- | -------------------------------------- |
| `engine_name`     | `superbio`                             |
| `app_id`          | `62bf442025b09dead5853d24` (AlphaFold2)|
| `execution_profile` | `superbio_gpu`                       |
| `version_command` | `python -c "import superbio, ..."`     |

## Parameter bindings (consumed from the launch step)

```
app_id          → Superbio Client.post_job(app_id=...)
app_name        → "alphafold2" (used for telemetry / log labelling only)
running_mode    → Superbio Client.post_job(running_mode="gpu")
aa_pairs        → JSON list of {protein_name, sequence}, fed as the
                  Superbio AlphaFold2 app config under `aa_pairs`
model_preset    → Superbio AlphaFold2 app config under `model_preset`
```

## Required environment

- `SUPERBIO_TOKEN`   — Superbio user JWT (from app.superbio.ai cookie)
- `SUPERBIO_USER_ID` — Superbio user id (paired with token)
- Python package `superbio>=0.1.0` installed in the workflow runtime

## Expected outputs (materialized into the run directory)

- `outputs/generated/external/alphafold2/structures/` — predicted PDB/CIF files
- `outputs/generated/external/alphafold2/logs/` — Superbio job logs
- `outputs/generated/external/alphafold2/manifest.json` — job_id + downloaded
  file inventory written by the `download_results` runner.

## Submission contract (informative)

When the BioAPEX external_engine executor adds `engine_name=superbio` support,
the dispatcher should:

1. Read `parameter_bindings` from the resolved step instance.
2. Construct `config = {"aa_pairs": json.loads(aa_pairs), "model_preset": model_preset}`.
3. Call `superbio.Client(token, user_id).post_job(app_id=app_id, running_mode=running_mode, config=config)`.
4. Persist the returned job dict as the step's `external_job_handle` value
   (`{"job_id": ..., "app_id": ..., "submitted_at": ...}`).
5. Defer polling / download to the `download_results` Python step at
   `workflows/runners/alphafold2.py::poll_and_download`.

This entrypoint file is not directly executable — it documents the contract
between BioAPEX and the Superbio HTTP backend.
