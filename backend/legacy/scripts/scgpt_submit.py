"""
One-command Superbio scGPT submission helper.

Submits the muscle aging atlas to scGPT Mapping and/or scGPT GRN Inference
on Superbio.ai, using the credentials in `backend/.env`. Prints the job_id(s)
which can later be polled via `scripts/scgpt_poll.py` or via the agent's
`superbio` tool with action='status' / 'download'.

Usage:
    python scripts/scgpt_submit.py --mapping              # only Mapping
    python scripts/scgpt_submit.py --grn                  # only GRN inference
    python scripts/scgpt_submit.py --mapping --grn        # both
    python scripts/scgpt_submit.py --dry-run --mapping    # show what would happen

Both jobs run on GPU (~30-60 min each, costs Superbio credits).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

ATLAS_PATH = BACKEND / "storage" / "atlases" / "SKM_balanced_30k.h5ad"

# Superbio app IDs (verified 2026-05-03)
APP_IDS = {
    "scgpt_mapping":    "6548f339a9ed6f6e5560b07d",
    "scgpt_grn":        "64b804fb823bc93b64c10a76",
}


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    except ImportError:
        pass


APP_CONFIGS = {
    "scgpt_mapping": {"genename_col_name": "SYMBOL"},
    "scgpt_grn": {
        "genename_col_name": "SYMBOL",
        "celltype_col_name": "annotation_level0",
        "batch_key": "batch",
        "pretrained_model": "human_all",
        "data_is_raw": False,
        "hvg_flavor": "cell_ranger",
        "number_hvg": 1200,
        "filter_genes_on_cluster": 4,
        "filter_gene_counts": 3,
        "filter_cell_counts": -1,
        "gene_program_index": 4,
        "db_pathway": "Reactome_2022",
    },
}


def submit_one(app_name: str, app_id: str, atlas_path: Path,
               dry_run: bool = False) -> dict:
    config = APP_CONFIGS.get(app_name, {})
    info = {
        "app_name":    app_name,
        "app_id":      app_id,
        "atlas":       str(atlas_path),
        "atlas_size_gb": atlas_path.stat().st_size / 1e9 if atlas_path.exists() else None,
        "config":      config,
        "dry_run":     dry_run,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    if not atlas_path.exists():
        info["error"] = f"atlas not found: {atlas_path}. Run scripts/download_muscle_atlas.py."
        return info

    if dry_run:
        info["job_id"] = None
        info["status"] = "dry_run"
        return info

    token = os.environ.get("SUPERBIO_TOKEN")
    user_id = os.environ.get("SUPERBIO_USER_ID")
    if not token or not user_id:
        info["error"] = "SUPERBIO_TOKEN or SUPERBIO_USER_ID not set"
        return info

    try:
        from superbio import Client
        client = Client(token=token, user_id=user_id)
        job = client.post_job(
            app_id=app_id,
            running_mode="gpu",
            config=config,
            local_files={"file_h5ad": str(atlas_path)},
        )
        info["job_id"] = job.get("job_id") or job.get("id") or str(job)
        info["raw"]    = job
        info["status"] = "submitted"
    except Exception as exc:
        info["error"] = f"submission failed: {exc}"

    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", action="store_true", help="Submit scGPT Mapping job")
    ap.add_argument("--grn", action="store_true", help="Submit scGPT GRN Inference job")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Don't actually submit; just print what would happen")
    ap.add_argument("--atlas", type=Path, default=ATLAS_PATH)
    args = ap.parse_args()

    if not (args.mapping or args.grn):
        print("[error] specify at least one of --mapping or --grn", file=sys.stderr)
        return 1

    load_env()

    log_dir = BACKEND / "knowledge" / "scgpt_jobs"
    log_dir.mkdir(parents=True, exist_ok=True)

    results = []
    if args.mapping:
        print(f"[scgpt_submit] {'(dry-run) ' if args.dry_run else ''}Mapping ...")
        r = submit_one("scgpt_mapping", APP_IDS["scgpt_mapping"], args.atlas, args.dry_run)
        results.append(r)
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
        else:
            print(f"  job_id: {r.get('job_id')}")
            print(f"  status: {r.get('status')}")

    if args.grn:
        print(f"[scgpt_submit] {'(dry-run) ' if args.dry_run else ''}GRN Inference ...")
        r = submit_one("scgpt_grn", APP_IDS["scgpt_grn"], args.atlas, args.dry_run)
        results.append(r)
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
        else:
            print(f"  job_id: {r.get('job_id')}")
            print(f"  status: {r.get('status')}")

    # Persist a log
    out_path = log_dir / f"submission_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results}, f, indent=2, default=str)
    print(f"\n[scgpt_submit] log: {out_path}")

    if any(r.get("error") for r in results):
        return 1

    print("\nNext steps:")
    print("  1. Wait ~30-60 min for jobs to complete on Superbio GPU")
    print("  2. Check status:    python -c \"from tools.superbio_tool import SuperbioTool; t=SuperbioTool(); print(t._run('status', job_id='<jid>')[0])\"")
    print("  3. Download:        agent or `superbio` tool action='download'")
    print("  4. Build axis:      `scgpt_phenotype` action='build_axis' on the downloaded mapping output")
    print("  5. Build programs:  `scgpt_programs`  action='build_programs' on the downloaded GRN output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
