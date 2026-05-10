"""
Superbio.ai tool: submit, poll, and download GPU protein design jobs.

Supports the full novokine design pipeline:
  - Binder Design with Boltz-1 (RFDiffusion → ProteinMPNN → Boltz-1, integrated)
  - RFDiffusion (backbone design)
  - ProteinMPNN (sequence design from backbone)
  - Boltz-1 / Boltz-2 (structure prediction + confidence scoring)
  - AlphaFold2 / Protenix (open-source AF3 reproduction)

Auth: uses SUPERBIO_TOKEN + SUPERBIO_USER_ID from .env (JWT from browser cookie).
Tokens expire after ~72h — if auth fails, re-extract from app.superbio.ai cookies.
"""
import os
import time
from pathlib import Path
from typing import Any, Literal, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    empty_result,
    execution_error_result,
    invalid_input_result,
    json_to_pretty_text,
    retriable_error_result,
    success_result,
)

# ── App IDs (verified 2026-05-03) ─────────────────────────────────────────────
APP_IDS = {
    "binder_design_boltz1": "6823397116b277b0d684d48e",  # RFDiffusion→ProteinMPNN→Boltz-1
    "rfdiffusion":          "655b1f47a9ed6f6e5560ba8f",
    "rfdiffusion_allatom":  "6717bd220d1f1d6ba100a766",
    "proteinmpnn":          "667aae5dad736b102dd32124",
    "boltz1":               "67d2b865209a9f0952578570",
    "boltz2":               "688c728099fcc1d511509092",
    "alphafold2":           "62bf442025b09dead5853d24",
    "protenix":             "687040d3fd98cd3abe210102",  # open-source AF3 reproduction
    "rfantibody":           "67e6ba077d733b5d5294fd0c",
    "ligandmpnn":           "67cedb83209a9f0952578498",
    # scGPT single-cell foundation model apps (Cui et al.)
    "scgpt_grn":            "64b804fb823bc93b64c10a76",  # Gene programs from cosine-sim of pretrained gene embeddings
    "scgpt_annotation":     "64d205cb980ff714de831ee0",  # Cell-type labeling (fine-tuned)
    "scgpt_mapping":        "6548f339a9ed6f6e5560b07d",  # Foundation-model cell embedding (zero-shot)
    "scgpt_perturbation":   "664f7a4afccd5edc65cefc35",  # Perturb-seq fine-tuned KO/OE prediction
    "scgpt_zeroshot_map":   "66548b93fccd5edc65cefdbe",  # Zero-shot reference mapping
}

AppName = Literal[
    "binder_design_boltz1",
    "rfdiffusion",
    "rfdiffusion_allatom",
    "proteinmpnn",
    "boltz1",
    "boltz2",
    "alphafold2",
    "protenix",
    "rfantibody",
    "ligandmpnn",
    "scgpt_grn",
    "scgpt_annotation",
    "scgpt_mapping",
    "scgpt_perturbation",
    "scgpt_zeroshot_map",
]

ActionType = Literal["submit", "status", "download", "list_jobs", "list_apps"]


class SuperbioInput(BaseModel):
    action: ActionType = Field(
        description=(
            "Action to perform: "
            "'submit' — submit a new design job; "
            "'status' — check job status by job_id; "
            "'download' — download results of a completed job to local path; "
            "'list_jobs' — list your recent jobs; "
            "'list_apps' — list available apps with their IDs."
        )
    )
    app_name: Optional[AppName] = Field(
        default=None,
        description=(
            "App to run. For novokine minibinder design use 'binder_design_boltz1' (integrated pipeline). "
            "Options: binder_design_boltz1, rfdiffusion, rfdiffusion_allatom, proteinmpnn, "
            "boltz1, boltz2, alphafold2, protenix, rfantibody, ligandmpnn."
        ),
    )
    job_config: Optional[dict] = Field(
        default=None,
        description=(
            "Job configuration parameters as a dict. App-specific. Examples: "
            "binder_design_boltz1: {'contigs': 'A1-100/0 70-100', 'num_designs': 10, 'model_preset': 'multimer'}; "
            "alphafold2: {'aa_pairs': \"[{'protein_name': 'SEQUENCE'}]\", 'model_preset': 'monomer'}; "
            "rfdiffusion: {'contigs': 'A1-100/0 50-80', 'num_designs': 10}."
        ),
    )
    local_file_path: Optional[str] = Field(
        default=None,
        description="Path to a local PDB or FASTA file to upload as job input.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job ID for 'status' and 'download' actions.",
    )
    download_dir: Optional[str] = Field(
        default=None,
        description="Local directory to download results into. Defaults to backend/artifacts/superbio/{job_id}/.",
    )
    running_mode: str = Field(
        default="gpu",
        description="'gpu' (default, required for design jobs) or 'cpu' (for lightweight jobs).",
    )
    wait_for_completion: bool = Field(
        default=False,
        description=(
            "If True, poll until the job finishes (up to 30 min) before returning. "
            "Use False (default) to submit and return the job_id immediately — "
            "check back later with action='status'."
        ),
    )


class SuperbioTool(BaseTool):
    name: str = "superbio"
    description: str = (
        "Submit and manage GPU protein design jobs on Superbio.ai. "
        "PRIMARY USE: action='submit' with app_name='binder_design_boltz1' to run the integrated "
        "RFDiffusion → ProteinMPNN → Boltz-1 novokine minibinder design pipeline. "
        "Provide a PDB file of the target receptor ECD via local_file_path, and job_config with "
        "contigs specifying the target chain/residues and desired binder length range. "
        "Use action='status' to check progress, action='download' to retrieve results. "
        "Also supports: rfdiffusion, proteinmpnn, boltz1, boltz2, alphafold2, protenix (AF3 open-source), "
        "rfantibody, ligandmpnn. "
        "Requires SUPERBIO_TOKEN and SUPERBIO_USER_ID in environment (refresh from app.superbio.ai cookies if expired)."
    )
    args_schema: Type[BaseModel] = SuperbioInput
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    def _client(self):
        token   = os.environ.get("SUPERBIO_TOKEN")
        user_id = os.environ.get("SUPERBIO_USER_ID")
        if not token or not user_id:
            return None, "SUPERBIO_TOKEN and SUPERBIO_USER_ID not set in .env. Extract from app.superbio.ai browser cookies (SB_TOKEN, SB_USERID)."
        try:
            from superbio import Client
            client = Client(token=token, user_id=user_id)
            return client, None
        except Exception as exc:
            return None, f"Superbio auth failed: {exc}. Token may have expired — re-extract SB_TOKEN from browser cookies."

    def _resolve_download_dir(self, job_id: str, download_dir: Optional[str]) -> Path:
        if download_dir:
            return Path(download_dir)
        base = Path(self.base_dir) if self.base_dir else Path(".")
        return base / "artifacts" / "superbio" / job_id

    def _run(
        self,
        action: ActionType = "status",
        app_name: Optional[AppName] = None,
        job_config: Optional[dict] = None,
        local_file_path: Optional[str] = None,
        job_id: Optional[str] = None,
        download_dir: Optional[str] = None,
        running_mode: str = "gpu",
        wait_for_completion: bool = False,
    ) -> tuple[str, dict]:

        client, err = self._client()
        if err:
            return invalid_input_result(self.name, err, metadata={"action": action})

        try:
            # ── list_apps ────────────────────────────────────────────────────
            if action == "list_apps":
                apps_data = []
                for name_key, aid in APP_IDS.items():
                    apps_data.append({"app_name": name_key, "app_id": aid})
                summary, _ = json_to_pretty_text({"available_apps": apps_data}, 50_000)
                return success_result(self.name, summary,
                                      structured_payload={"available_apps": apps_data},
                                      metadata={"action": action})

            # ── list_jobs ────────────────────────────────────────────────────
            elif action == "list_jobs":
                jobs = client.get_jobs()
                if not jobs:
                    return empty_result(self.name, "No jobs found.", metadata={"action": action})
                # Normalise to list
                job_list = jobs if isinstance(jobs, list) else jobs.get("jobs", jobs.get("hits", [jobs]))
                summary, _ = json_to_pretty_text({"jobs": job_list[:20]}, 50_000)
                return success_result(self.name, summary,
                                      structured_payload={"jobs": job_list[:20]},
                                      metadata={"action": action, "result_count": len(job_list)})

            # ── status ───────────────────────────────────────────────────────
            elif action == "status":
                if not job_id:
                    return invalid_input_result(self.name, "'job_id' is required for action='status'.", metadata={})
                status = client.get_job_status(job_id)
                summary, _ = json_to_pretty_text(status if isinstance(status, dict) else {"status": status}, 50_000)
                return success_result(self.name, summary,
                                      structured_payload=status if isinstance(status, dict) else {"status": status},
                                      metadata={"action": action, "job_id": job_id})

            # ── submit ───────────────────────────────────────────────────────
            elif action == "submit":
                if not app_name:
                    return invalid_input_result(self.name, "'app_name' is required for action='submit'.", metadata={})
                app_id = APP_IDS.get(app_name)
                if not app_id:
                    return invalid_input_result(self.name, f"Unknown app_name: {app_name}.", metadata={})

                local_files: dict[str, str] = {}
                if local_file_path:
                    p = Path(local_file_path)
                    if not p.exists():
                        return invalid_input_result(
                            self.name, f"local_file_path not found: {local_file_path}", metadata={})
                    local_files = {"file": str(p)}

                job = client.post_job(
                    app_id=app_id,
                    running_mode=running_mode,
                    config=job_config or {},
                    local_files=local_files,
                )
                jid = job.get("job_id") or job.get("id") or str(job)
                meta = {
                    "action": "submit", "app_name": app_name,
                    "app_id": app_id, "job_id": jid,
                    "running_mode": running_mode,
                }

                if wait_for_completion:
                    result = self._poll(client, jid)
                    meta["final_status"] = result
                    summary = f"Job {jid} submitted and completed with status: {result}"
                else:
                    summary = (
                        f"Job submitted successfully.\n"
                        f"job_id: {jid}\n"
                        f"app: {app_name} ({app_id})\n"
                        f"running_mode: {running_mode}\n\n"
                        f"Check progress: action='status', job_id='{jid}'\n"
                        f"Download results: action='download', job_id='{jid}'"
                    )

                return success_result(self.name, summary,
                                      structured_payload={"job_id": jid, "app_name": app_name},
                                      metadata=meta)

            # ── download ─────────────────────────────────────────────────────
            elif action == "download":
                if not job_id:
                    return invalid_input_result(self.name, "'job_id' is required for action='download'.", metadata={})

                out_dir = self._resolve_download_dir(job_id, download_dir)
                out_dir.mkdir(parents=True, exist_ok=True)

                client.download_all_job_results(job_id=job_id, path_to_download_to=str(out_dir))
                files = list(out_dir.rglob("*"))
                file_list = [str(f.relative_to(out_dir)) for f in files if f.is_file()]
                summary = (
                    f"Downloaded {len(file_list)} file(s) to {out_dir}:\n"
                    + "\n".join(f"  {f}" for f in file_list[:30])
                )
                return success_result(self.name, summary,
                                      structured_payload={"download_dir": str(out_dir), "files": file_list},
                                      metadata={"action": action, "job_id": job_id, "file_count": len(file_list)})

            else:
                return invalid_input_result(self.name, f"Unknown action: {action}", metadata={})

        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "403" in msg or "token" in msg.lower() or "expired" in msg.lower():
                return retriable_error_result(
                    self.name,
                    f"Superbio auth error (token likely expired): {msg}. "
                    "Re-extract SB_TOKEN and SB_USERID from app.superbio.ai browser cookies and update .env.",
                    metadata={"action": action},
                )
            return execution_error_result(self.name, msg, metadata={"action": action})

    def _poll(self, client: Any, job_id: str, timeout_s: int = 1800, interval_s: int = 30) -> str:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = client.get_job_status(job_id)
            state = status.get("status", "") if isinstance(status, dict) else str(status)
            if state.lower() in ("completed", "failed", "error", "cancelled"):
                return state
            time.sleep(interval_s)
        return "timeout"

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
