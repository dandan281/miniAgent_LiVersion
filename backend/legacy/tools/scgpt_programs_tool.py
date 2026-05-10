"""
scGPT Programs Tool — gene-program activation scorer for novokine candidates.

Implements the GRN-based Track A regularizer for the muscle rejuvenation RL loop.

scGPT GRN Inference computes (despite the name, this is NOT a TF→target network):
  - Cosine similarity of pretrained scGPT gene embeddings
  - Louvain clustering → ~50–100 "gene programs" (each = a cluster of co-embedded genes)
  - Per-cell metagene activation scores (cell × program matrix)
  - GSEA pathway enrichment per program

Workflow:
  1. action='submit_grn'  — submit the muscle aging atlas to scGPT GRN Inference (Superbio GPU job)
  2. action='build_programs' — parse the result .h5ad / GSEA CSV, classify each program as
       young-enriched / aged-enriched / neutral by differential metagene score across age groups
  3. action='score_geneset' — for a candidate novokine's predicted up/down gene set, compute
       overlap with young-up programs (positive) and aged-up programs (negative)

Cache layout:
  backend/storage/scgpt_cache/
    grn_<job_id>/                 ← downloaded GRN output
    gene_programs.json            ← {program_id → {genes, gsea_label, age_direction, n_genes}}
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    execution_error_result,
    invalid_input_result,
    json_to_pretty_text,
    success_result,
)
from .superbio_tool import APP_IDS

ActionType = Literal[
    "submit_grn",       # Submit atlas .h5ad to scGPT GRN Inference
    "build_programs",   # Parse downloaded GRN output → cached programs JSON
    "score_geneset",    # Score a candidate up/down gene set against the programs
    "show_programs",    # Display cached programs metadata
]


class ScgptProgramsInput(BaseModel):
    action: ActionType = Field(
        description=(
            "Action: "
            "'submit_grn' — submit atlas .h5ad to scGPT GRN Inference (returns job_id); "
            "'build_programs' — parse downloaded GRN output into cached gene programs; "
            "'score_geneset' — score a candidate up/down gene set against young/aged programs; "
            "'show_programs' — display cached program metadata."
        )
    )
    atlas_path: Optional[str] = Field(
        default=None,
        description="Path to atlas .h5ad. For submit_grn. Defaults to the Kedlian atlas in storage/atlases/.",
    )
    grn_output_h5ad: Optional[str] = Field(
        default=None,
        description="Path to GRN output .h5ad with metagene scores in obsm. For build_programs.",
    )
    gsea_csv: Optional[str] = Field(
        default=None,
        description="Path to gsea_analysis.csv (program → pathway labels). For build_programs.",
    )
    age_col: str = Field(
        default="Age_bin",
        description="obs column for age groups (default 'Age_bin', values: young/old).",
    )
    celltype_col: str = Field(
        default="annotation_level0",
        description="obs column for cell-type labels.",
    )
    target_celltype: Optional[str] = Field(
        default=None,
        description="If set, build/score programs only for this cell type (e.g. 'MuSC'). Default: pool MuSC + MF-I + MF-II.",
    )
    diff_threshold: float = Field(
        default=0.1,
        description="Mean metagene score difference (young - old) above which a program is classified as young-enriched (or below -threshold for aged-enriched).",
    )
    min_program_size: int = Field(
        default=5,
        description="Minimum genes per program to keep (default 5; matches scGPT tutorial Louvain res=40).",
    )
    up_genes: Optional[list[str]] = Field(
        default=None,
        description="For score_geneset: HGNC symbols predicted to be UPregulated by the candidate.",
    )
    down_genes: Optional[list[str]] = Field(
        default=None,
        description="For score_geneset: HGNC symbols predicted to be DOWNregulated by the candidate.",
    )


class ScgptProgramsTool(BaseTool):
    name: str = "scgpt_programs"
    description: str = (
        "scGPT GRN Inference-based gene-program scoring for the muscle rejuvenation RL loop. "
        "Replaces noisy raw 77 vs 536 DEG overlap with structured ~80-program overlap (denoised Track A). "
        "Each 'program' is a cluster of co-embedded genes from scGPT's pretrained foundation model, "
        "labeled young-enriched / aged-enriched by differential metagene activation across age groups. "
        "Workflow: (1) action='submit_grn' once on atlas, (2) action='build_programs' after download, "
        "(3) action='score_geneset' per novokine candidate. "
        "Requires SUPERBIO_TOKEN; reads/writes backend/storage/scgpt_cache/."
    )
    args_schema: Type[BaseModel] = ScgptProgramsInput
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    def _cache_dir(self) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(".")
        d = base / "storage" / "scgpt_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _programs_path(self) -> Path:
        return self._cache_dir() / "gene_programs.json"

    def _default_atlas(self) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(".")
        return base / "storage" / "atlases" / "SKM_human_pp_cells2nuclei_2023-06-22.h5ad"

    def _run(
        self,
        action: ActionType,
        atlas_path: Optional[str] = None,
        grn_output_h5ad: Optional[str] = None,
        gsea_csv: Optional[str] = None,
        age_col: str = "Age_bin",
        celltype_col: str = "annotation_level0",
        target_celltype: Optional[str] = None,
        diff_threshold: float = 0.1,
        min_program_size: int = 5,
        up_genes: Optional[list[str]] = None,
        down_genes: Optional[list[str]] = None,
    ) -> tuple[str, dict]:

        try:
            if action == "submit_grn":
                return self._submit_grn(atlas_path)
            elif action == "build_programs":
                return self._build_programs(
                    grn_output_h5ad, gsea_csv, age_col, celltype_col,
                    target_celltype, diff_threshold, min_program_size,
                )
            elif action == "score_geneset":
                return self._score_geneset(up_genes, down_genes)
            elif action == "show_programs":
                return self._show_programs()
            else:
                return invalid_input_result(self.name, f"Unknown action: {action}", metadata={})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"action": action})

    # ── submit_grn ────────────────────────────────────────────────────────────
    def _submit_grn(self, atlas_path: Optional[str]) -> tuple[str, dict]:
        token   = os.environ.get("SUPERBIO_TOKEN")
        user_id = os.environ.get("SUPERBIO_USER_ID")
        if not token or not user_id:
            return invalid_input_result(
                self.name,
                "SUPERBIO_TOKEN and SUPERBIO_USER_ID required.",
                metadata={"action": "submit_grn"},
            )

        path = Path(atlas_path) if atlas_path else self._default_atlas()
        if not path.exists():
            return invalid_input_result(
                self.name,
                f"Atlas not found: {path}. Run scripts/download_muscle_atlas.py first.",
                metadata={"atlas_path": str(path)},
            )

        try:
            from superbio import Client
            client = Client(token=token, user_id=user_id)
            job = client.post_job(
                app_id=APP_IDS["scgpt_grn"],
                running_mode="gpu",
                config={},
                local_files={"file_h5ad": str(path)},
            )
        except Exception as exc:
            return execution_error_result(
                self.name, f"Superbio submit failed: {exc}",
                metadata={"action": "submit_grn"},
            )

        jid = job.get("job_id") or job.get("id") or str(job)
        summary = (
            f"scGPT GRN Inference job submitted.\n"
            f"  job_id: {jid}\n"
            f"  atlas:  {path.name}\n"
            f"  app:    scgpt_grn ({APP_IDS['scgpt_grn']})\n\n"
            f"Outputs (after job completes):\n"
            f"  - <result>.h5ad with metagene scores in obsm\n"
            f"  - gsea_analysis.csv (program → pathway labels)\n"
            f"  - cosine similarity gene network plots\n\n"
            f"Next: superbio download → scgpt_programs action='build_programs'"
        )
        return success_result(
            self.name, summary,
            structured_payload={"job_id": jid, "atlas_path": str(path)},
            metadata={"action": "submit_grn", "job_id": jid},
        )

    # ── build_programs ────────────────────────────────────────────────────────
    def _build_programs(
        self,
        grn_output_h5ad: Optional[str],
        gsea_csv: Optional[str],
        age_col: str,
        celltype_col: str,
        target_celltype: Optional[str],
        diff_threshold: float,
        min_program_size: int,
    ) -> tuple[str, dict]:
        if not grn_output_h5ad:
            return invalid_input_result(
                self.name, "'grn_output_h5ad' required.",
                metadata={"action": "build_programs"},
            )
        h5ad_path = Path(grn_output_h5ad)
        if not h5ad_path.exists():
            return invalid_input_result(
                self.name, f"GRN output not found: {h5ad_path}",
                metadata={"action": "build_programs"},
            )

        try:
            import anndata
            import numpy as np
            import pandas as pd
        except ImportError:
            return invalid_input_result(
                self.name,
                "anndata, numpy, pandas required.",
                metadata={"action": "build_programs"},
            )

        adata = anndata.read_h5ad(h5ad_path)

        # scGPT GRN tutorial stores program-gene memberships in adata.uns or var; metagene scores in obsm.
        # We try standard keys; user can override via input fields if their output schema differs.
        program_genes: dict[str, list[str]] = {}
        if "gene_programs" in adata.uns:
            raw = adata.uns["gene_programs"]
            if isinstance(raw, dict):
                program_genes = {str(k): list(v) for k, v in raw.items()}
            elif isinstance(raw, pd.DataFrame):
                # Common format: program_id, gene_name columns
                for pid, grp in raw.groupby(raw.columns[0]):
                    program_genes[str(pid)] = grp[raw.columns[1]].astype(str).tolist()
        elif "louvain" in adata.var.columns:
            for pid, grp in adata.var.groupby("louvain"):
                program_genes[str(pid)] = grp.index.tolist()
        else:
            return invalid_input_result(
                self.name,
                f"Could not locate gene programs in {h5ad_path}. "
                f"Looked in adata.uns['gene_programs'] and adata.var['louvain']. "
                f"Available uns keys: {list(adata.uns.keys())}; "
                f"var columns: {list(adata.var.columns)}",
                metadata={"action": "build_programs"},
            )

        # Filter by min size
        program_genes = {p: g for p, g in program_genes.items() if len(g) >= min_program_size}

        # Find metagene activation matrix (cell × program). scGPT typically writes obsm['metagene_score'].
        metagene_key = None
        for k in ("metagene_score", "X_metagene", "X_program", "program_scores"):
            if k in adata.obsm:
                metagene_key = k
                break
        if metagene_key is None:
            return invalid_input_result(
                self.name,
                f"Could not find metagene scores in obsm. Available: {list(adata.obsm.keys())}",
                metadata={"action": "build_programs"},
            )

        scores = np.asarray(adata.obsm[metagene_key])
        n_progs_in_matrix = scores.shape[1]
        prog_ids = sorted(program_genes.keys(), key=lambda x: int(x) if x.isdigit() else x)
        if len(prog_ids) != n_progs_in_matrix:
            # Truncate to whichever is smaller, but warn
            n = min(len(prog_ids), n_progs_in_matrix)
            prog_ids = prog_ids[:n]
            scores = scores[:, :n]

        # Subset cells to target cell type(s)
        if celltype_col not in adata.obs.columns:
            return invalid_input_result(
                self.name,
                f"Column '{celltype_col}' not in obs.",
                metadata={"action": "build_programs"},
            )
        ctypes = adata.obs[celltype_col].astype(str).values
        if target_celltype:
            cell_mask = ctypes == target_celltype
        else:
            cell_mask = np.isin(ctypes, ["MuSC", "MF-I", "MF-II"])
        if cell_mask.sum() < 100:
            return invalid_input_result(
                self.name,
                f"Too few cells ({int(cell_mask.sum())}) for target_celltype='{target_celltype}'.",
                metadata={"action": "build_programs"},
            )

        ages = adata.obs[age_col].astype(str).str.lower().values
        mask_young = cell_mask & (ages == "young")
        mask_old   = cell_mask & (ages == "old")
        if mask_young.sum() < 30 or mask_old.sum() < 30:
            return invalid_input_result(
                self.name,
                f"Insufficient young ({int(mask_young.sum())}) or old ({int(mask_old.sum())}) cells.",
                metadata={"action": "build_programs"},
            )

        mean_young = scores[mask_young].mean(axis=0)
        mean_old   = scores[mask_old].mean(axis=0)
        diff       = mean_young - mean_old

        # Optional GSEA labels
        gsea_labels: dict[str, str] = {}
        if gsea_csv and Path(gsea_csv).exists():
            try:
                gsea = pd.read_csv(gsea_csv)
                # Heuristic: first column is program id, find column containing 'pathway' or 'term'
                pid_col = gsea.columns[0]
                label_col = next(
                    (c for c in gsea.columns if any(s in c.lower() for s in ("pathway", "term", "name"))),
                    gsea.columns[1] if len(gsea.columns) > 1 else None,
                )
                if label_col:
                    for _, row in gsea.iterrows():
                        gsea_labels[str(row[pid_col])] = str(row[label_col])
            except Exception:
                pass  # GSEA is optional — keep going

        # Classify
        programs_out: dict[str, dict] = {}
        n_young, n_aged, n_neutral = 0, 0, 0
        for i, pid in enumerate(prog_ids):
            d = float(diff[i])
            if d > diff_threshold:
                direction = "young"; n_young += 1
            elif d < -diff_threshold:
                direction = "aged"; n_aged += 1
            else:
                direction = "neutral"; n_neutral += 1
            programs_out[pid] = {
                "genes":             program_genes[pid],
                "n_genes":           len(program_genes[pid]),
                "mean_young":        float(mean_young[i]),
                "mean_old":          float(mean_old[i]),
                "diff_young_minus_old": d,
                "age_direction":     direction,
                "gsea_label":        gsea_labels.get(pid, ""),
            }

        out = {
            "n_programs":      len(programs_out),
            "n_young_enriched": n_young,
            "n_aged_enriched":  n_aged,
            "n_neutral":        n_neutral,
            "diff_threshold":   diff_threshold,
            "min_program_size": min_program_size,
            "target_celltype":  target_celltype or "MuSC+MF-I+MF-II",
            "n_young_cells":    int(mask_young.sum()),
            "n_old_cells":      int(mask_old.sum()),
            "source_file":      str(h5ad_path),
            "programs":         programs_out,
        }
        out_path = self._programs_path()
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)

        # Top programs by direction for the summary
        sorted_progs = sorted(programs_out.items(), key=lambda kv: kv[1]["diff_young_minus_old"])
        top_aged = sorted_progs[:5]
        top_young = sorted_progs[-5:][::-1]
        def _fmt(pid: str, d: dict) -> str:
            label = d["gsea_label"][:50] if d["gsea_label"] else f"({d['n_genes']} genes)"
            return f"  {pid}: Δ={d['diff_young_minus_old']:+.3f}  {label}"

        summary = (
            f"Built {len(programs_out)} gene programs from {h5ad_path.name}:\n"
            f"  young-enriched: {n_young}   aged-enriched: {n_aged}   neutral: {n_neutral}\n"
            f"  cells used: young={int(mask_young.sum())}, old={int(mask_old.sum())} ({target_celltype or 'MuSC+MF'})\n"
            f"\nTop young-enriched programs:\n"
            + "\n".join(_fmt(p, d) for p, d in top_young)
            + f"\n\nTop aged-enriched programs:\n"
            + "\n".join(_fmt(p, d) for p, d in top_aged)
            + f"\n\nCached to: {out_path}"
        )
        return success_result(
            self.name, summary,
            structured_payload={
                "n_programs":      len(programs_out),
                "n_young_enriched": n_young,
                "n_aged_enriched":  n_aged,
                "cache_path":      str(out_path),
            },
            metadata={"action": "build_programs", "n_programs": len(programs_out)},
        )

    # ── score_geneset ─────────────────────────────────────────────────────────
    def _score_geneset(
        self,
        up_genes: Optional[list[str]],
        down_genes: Optional[list[str]],
    ) -> tuple[str, dict]:
        if not up_genes and not down_genes:
            return invalid_input_result(
                self.name, "Provide at least one of 'up_genes' or 'down_genes'.",
                metadata={"action": "score_geneset"},
            )
        path = self._programs_path()
        if not path.exists():
            return invalid_input_result(
                self.name,
                f"No cached programs at {path}. Run action='build_programs' first.",
                metadata={"action": "score_geneset"},
            )

        with open(path) as f:
            data = json.load(f)
        programs = data["programs"]

        up_set   = {g.upper() for g in (up_genes or [])}
        down_set = {g.upper() for g in (down_genes or [])}

        # For each program, compute fraction of program genes in up_set vs down_set
        # Then aggregate: youthification = sum over young-progs of activation - sum over aged-progs of activation
        # where activation = (fraction_up - fraction_down)
        activations: list[dict] = []
        score_young = 0.0
        score_aged  = 0.0
        n_young_hit, n_aged_hit = 0, 0

        for pid, p in programs.items():
            genes = {g.upper() for g in p["genes"]}
            n = len(genes)
            if n == 0:
                continue
            f_up   = len(genes & up_set)   / n
            f_down = len(genes & down_set) / n
            activation = f_up - f_down
            direction = p["age_direction"]
            entry = {
                "program_id":    pid,
                "direction":     direction,
                "gsea_label":    p["gsea_label"],
                "n_genes":       n,
                "f_up":          f_up,
                "f_down":        f_down,
                "activation":    activation,
                "diff_young_minus_old": p["diff_young_minus_old"],
            }
            if direction == "young" and abs(activation) > 0:
                score_young += activation
                n_young_hit += 1
            elif direction == "aged" and abs(activation) > 0:
                score_aged += activation
                n_aged_hit += 1
            activations.append(entry)

        # Net youthification: activate young programs (good), suppress aged programs (good)
        # → net = score_young - score_aged
        net_score = score_young - score_aged

        # Top contributing programs (by absolute contribution)
        sorted_acts = sorted(activations, key=lambda x: abs(x["activation"]), reverse=True)
        top = sorted_acts[:10]
        def _fmt(e: dict) -> str:
            label = (e["gsea_label"] or "")[:40]
            return (f"  [{e['direction']:>7}] {e['program_id']}: "
                    f"act={e['activation']:+.3f} "
                    f"({int(e['f_up']*e['n_genes'])}↑ {int(e['f_down']*e['n_genes'])}↓ / {e['n_genes']}) "
                    f"{label}")

        summary = (
            f"Gene-set youthification score: {net_score:+.4f}\n"
            f"  young-program activation: {score_young:+.4f}  ({n_young_hit} programs hit)\n"
            f"  aged-program activation:  {score_aged:+.4f}   ({n_aged_hit} programs hit)\n"
            f"  input: {len(up_set)} up genes, {len(down_set)} down genes\n"
            f"\nTop contributing programs (|activation|):\n"
            + "\n".join(_fmt(e) for e in top)
            + f"\n\nInterpretation: positive net = activates young + suppresses aged programs."
        )
        return success_result(
            self.name, summary,
            structured_payload={
                "net_score":    net_score,
                "score_young":  score_young,
                "score_aged":   score_aged,
                "n_young_hit":  n_young_hit,
                "n_aged_hit":   n_aged_hit,
                "top_programs": top,
            },
            metadata={"action": "score_geneset", "net_score": net_score},
        )

    # ── show_programs ─────────────────────────────────────────────────────────
    def _show_programs(self) -> tuple[str, dict]:
        path = self._programs_path()
        if not path.exists():
            return invalid_input_result(
                self.name,
                f"No cached programs at {path}. Run action='build_programs' first.",
                metadata={"action": "show_programs"},
            )
        with open(path) as f:
            data = json.load(f)
        # Strip per-program gene lists for the summary; keep counts and labels
        compact = {
            **{k: v for k, v in data.items() if k != "programs"},
            "programs": {
                pid: {k: v for k, v in p.items() if k != "genes"}
                for pid, p in list(data["programs"].items())[:50]
            },
        }
        summary, _ = json_to_pretty_text(compact, 8000)
        return success_result(
            self.name, summary,
            structured_payload=compact,
            metadata={"action": "show_programs"},
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
