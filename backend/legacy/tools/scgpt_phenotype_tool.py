"""
scGPT Phenotype Tool — "Young-Axis Score" for novokine candidates.

Implements the Mapping-based Track A.5 reward signal for the muscle rejuvenation RL loop:
  1. Submit the muscle aging atlas .h5ad to scGPT Mapping on Superbio.ai.
     scGPT encodes each cell into a 512-d foundation-model embedding (pretrained, no fine-tune).
  2. Build per-cell-type rejuvenation axes from the resulting embeddings:
        v_celltype = centroid(young, celltype) - centroid(old, celltype)
     One axis per cell type (MuSC, MF-I, MF-II, FB, ...).
  3. Score a novokine candidate's predicted gene-shift Δg by projecting it onto the axis:
        score = cos(Δembedding, v)   ∈ [-1, 1]
     Positive score → moves cells toward young centroid; negative → toward old.

The expensive step (1) is run once per atlas; the cheap steps (2,3) run per candidate.

Requires: superbio_tool (for GPU job), and locally:
  - scanpy, anndata     (read embeddings from result .h5ad)
  - numpy

Cache layout:
  backend/storage/scgpt_cache/
    mapping_<job_id>/                    ← downloaded mapping output
    young_axis.json                      ← computed centroids + axes
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
    "submit_mapping",  # Submit atlas .h5ad to scGPT Mapping (Superbio GPU job)
    "build_axis",      # Build young-axis from downloaded mapping output
    "score_delta",     # Score a candidate Δg vector against the axis
    "show_axis",       # Display the cached axis metadata
]


class ScgptPhenotypeInput(BaseModel):
    action: ActionType = Field(
        description=(
            "Action: "
            "'submit_mapping' — submit atlas .h5ad to scGPT Mapping on Superbio (returns job_id); "
            "'build_axis' — compute per-cell-type young-vs-old axes from mapped embeddings; "
            "'score_delta' — score a candidate gene-shift Δg vector against the axis; "
            "'show_axis' — display cached axis metadata (centroids, axis norms, cell types)."
        )
    )
    atlas_path: Optional[str] = Field(
        default=None,
        description="Path to atlas .h5ad. For submit_mapping. Defaults to backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad.",
    )
    mapping_h5ad: Optional[str] = Field(
        default=None,
        description="Path to the mapped .h5ad (output of scGPT Mapping). For build_axis. Must contain obsm['X_scGPT'] (or similar) and obs['Age_bin'], obs['annotation_level0'].",
    )
    age_col: str = Field(
        default="Age_bin",
        description="obs column name for age groups (default 'Age_bin' for Kedlian atlas; values: young/old).",
    )
    celltype_col: str = Field(
        default="annotation_level0",
        description="obs column name for cell-type labels (default 'annotation_level0').",
    )
    embedding_key: str = Field(
        default="X_scGPT",
        description="obsm key for scGPT cell embedding (typically 'X_scGPT' or 'X_scgpt').",
    )
    cell_types: Optional[list[str]] = Field(
        default=None,
        description="Subset of cell types to build axes for. Default: ['MuSC', 'MF-I', 'MF-II', 'FB'] (the muscle-relevant compartments).",
    )
    delta_embedding: Optional[list[float]] = Field(
        default=None,
        description="For score_delta: 512-d Δembedding vector (predicted change in scGPT space).",
    )
    target_celltype: Optional[str] = Field(
        default=None,
        description="For score_delta: which cell-type axis to score against (e.g. 'MuSC').",
    )


class ScgptPhenotypeTool(BaseTool):
    name: str = "scgpt_phenotype"
    description: str = (
        "scGPT-based phenotype scoring for the muscle rejuvenation RL loop (Track A.5 reward signal). "
        "Submits the muscle aging atlas to scGPT Mapping (Superbio GPU), builds per-cell-type "
        "young-vs-old rejuvenation axes in 512-d foundation-model embedding space, and scores "
        "novokine candidates by cosine projection onto these axes. "
        "Cleanest unsupervised 'youthification score' available — H2F is the calibration positive control. "
        "Workflow: (1) action='submit_mapping' once on the atlas, (2) download via superbio tool, "
        "(3) action='build_axis' to cache centroids, (4) action='score_delta' per candidate. "
        "Requires SUPERBIO_TOKEN in env; reads/writes backend/storage/scgpt_cache/."
    )
    args_schema: Type[BaseModel] = ScgptPhenotypeInput
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    def _cache_dir(self) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(".")
        d = base / "storage" / "scgpt_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _axis_path(self) -> Path:
        return self._cache_dir() / "young_axis.json"

    def _default_atlas(self) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(".")
        return base / "storage" / "atlases" / "SKM_human_pp_cells2nuclei_2023-06-22.h5ad"

    def _run(
        self,
        action: ActionType,
        atlas_path: Optional[str] = None,
        mapping_h5ad: Optional[str] = None,
        age_col: str = "Age_bin",
        celltype_col: str = "annotation_level0",
        embedding_key: str = "X_scGPT",
        cell_types: Optional[list[str]] = None,
        delta_embedding: Optional[list[float]] = None,
        target_celltype: Optional[str] = None,
    ) -> tuple[str, dict]:

        try:
            if action == "submit_mapping":
                return self._submit_mapping(atlas_path)
            elif action == "build_axis":
                return self._build_axis(
                    mapping_h5ad, age_col, celltype_col, embedding_key, cell_types
                )
            elif action == "score_delta":
                return self._score_delta(delta_embedding, target_celltype)
            elif action == "show_axis":
                return self._show_axis()
            else:
                return invalid_input_result(self.name, f"Unknown action: {action}", metadata={})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"action": action})

    # ── submit_mapping ────────────────────────────────────────────────────────
    def _submit_mapping(self, atlas_path: Optional[str]) -> tuple[str, dict]:
        token   = os.environ.get("SUPERBIO_TOKEN")
        user_id = os.environ.get("SUPERBIO_USER_ID")
        if not token or not user_id:
            return invalid_input_result(
                self.name,
                "SUPERBIO_TOKEN and SUPERBIO_USER_ID required. See superbio tool description for token extraction.",
                metadata={"action": "submit_mapping"},
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
                app_id=APP_IDS["scgpt_mapping"],
                running_mode="gpu",
                config={},
                local_files={"file_h5ad": str(path)},
            )
        except Exception as exc:
            return execution_error_result(
                self.name,
                f"Superbio submit failed: {exc}",
                metadata={"action": "submit_mapping"},
            )

        jid = job.get("job_id") or job.get("id") or str(job)
        summary = (
            f"scGPT Mapping job submitted.\n"
            f"  job_id: {jid}\n"
            f"  atlas:  {path.name} ({path.stat().st_size / 1e9:.2f} GB)\n"
            f"  app:    scgpt_mapping ({APP_IDS['scgpt_mapping']})\n\n"
            f"Next steps:\n"
            f"  1. Check status:    superbio tool, action='status', job_id='{jid}'\n"
            f"  2. Download:        superbio tool, action='download', job_id='{jid}'\n"
            f"  3. Build axis:      scgpt_phenotype, action='build_axis', mapping_h5ad=<downloaded path>"
        )
        return success_result(
            self.name, summary,
            structured_payload={"job_id": jid, "atlas_path": str(path)},
            metadata={"action": "submit_mapping", "job_id": jid},
        )

    # ── build_axis ────────────────────────────────────────────────────────────
    def _build_axis(
        self,
        mapping_h5ad: Optional[str],
        age_col: str,
        celltype_col: str,
        embedding_key: str,
        cell_types: Optional[list[str]],
    ) -> tuple[str, dict]:
        if not mapping_h5ad:
            return invalid_input_result(
                self.name, "'mapping_h5ad' required for build_axis.",
                metadata={"action": "build_axis"},
            )
        path = Path(mapping_h5ad)
        if not path.exists():
            return invalid_input_result(
                self.name, f"Mapping output not found: {path}",
                metadata={"action": "build_axis"},
            )

        try:
            import anndata
            import numpy as np
        except ImportError:
            return invalid_input_result(
                self.name,
                "anndata and numpy required. pip install anndata numpy",
                metadata={"action": "build_axis"},
            )

        adata = anndata.read_h5ad(path)
        if embedding_key not in adata.obsm:
            available = list(adata.obsm.keys())
            return invalid_input_result(
                self.name,
                f"Embedding key '{embedding_key}' not in obsm. Available: {available}",
                metadata={"action": "build_axis"},
            )
        for col in (age_col, celltype_col):
            if col not in adata.obs.columns:
                return invalid_input_result(
                    self.name,
                    f"Column '{col}' not in obs. Available: {list(adata.obs.columns)[:30]}",
                    metadata={"action": "build_axis"},
                )

        emb = np.asarray(adata.obsm[embedding_key])
        ages = adata.obs[age_col].astype(str).str.lower().values
        ctypes = adata.obs[celltype_col].astype(str).values

        targets = cell_types or ["MuSC", "MF-I", "MF-II", "FB"]
        axes_data: dict[str, dict] = {}
        skipped: list[str] = []

        for ct in targets:
            mask_ct = ctypes == ct
            mask_young = mask_ct & (ages == "young")
            mask_old   = mask_ct & (ages == "old")
            n_young, n_old = int(mask_young.sum()), int(mask_old.sum())
            if n_young < 30 or n_old < 30:
                skipped.append(f"{ct} (young={n_young}, old={n_old})")
                continue
            c_young = emb[mask_young].mean(axis=0)
            c_old   = emb[mask_old].mean(axis=0)
            v = c_young - c_old
            v_norm = float(np.linalg.norm(v))
            axes_data[ct] = {
                "centroid_young": c_young.tolist(),
                "centroid_old":   c_old.tolist(),
                "axis":           v.tolist(),
                "axis_norm":      v_norm,
                "n_young_cells":  n_young,
                "n_old_cells":    n_old,
            }

        if not axes_data:
            return invalid_input_result(
                self.name,
                f"No cell types had ≥30 young & ≥30 old cells. Skipped: {skipped}",
                metadata={"action": "build_axis"},
            )

        out = {
            "embedding_dim": int(emb.shape[1]),
            "embedding_key": embedding_key,
            "age_col":       age_col,
            "celltype_col":  celltype_col,
            "source_file":   str(path),
            "n_cells_total": int(emb.shape[0]),
            "axes":          axes_data,
            "skipped":       skipped,
        }
        axis_path = self._axis_path()
        with open(axis_path, "w") as f:
            json.dump(out, f, indent=2)

        ct_summary = "\n".join(
            f"  {ct}: ||v||={d['axis_norm']:.3f}  young={d['n_young_cells']}  old={d['n_old_cells']}"
            for ct, d in axes_data.items()
        )
        summary = (
            f"Built {len(axes_data)} young-axis vector(s) in {emb.shape[1]}-d scGPT space:\n"
            f"{ct_summary}\n"
            f"Cached to: {axis_path}\n"
            + (f"\nSkipped (insufficient cells): {', '.join(skipped)}" if skipped else "")
        )
        # Drop the per-cell-type centroid vectors from the structured payload to keep it compact
        compact_axes = {
            ct: {k: v for k, v in d.items() if k not in ("centroid_young", "centroid_old", "axis")}
            for ct, d in axes_data.items()
        }
        return success_result(
            self.name, summary,
            structured_payload={"axes": compact_axes, "cache_path": str(axis_path)},
            metadata={"action": "build_axis", "n_cell_types": len(axes_data)},
        )

    # ── score_delta ───────────────────────────────────────────────────────────
    def _score_delta(
        self,
        delta_embedding: Optional[list[float]],
        target_celltype: Optional[str],
    ) -> tuple[str, dict]:
        if not delta_embedding:
            return invalid_input_result(
                self.name, "'delta_embedding' required (list of 512 floats).",
                metadata={"action": "score_delta"},
            )
        if not target_celltype:
            return invalid_input_result(
                self.name, "'target_celltype' required (e.g. 'MuSC').",
                metadata={"action": "score_delta"},
            )
        axis_path = self._axis_path()
        if not axis_path.exists():
            return invalid_input_result(
                self.name,
                f"No cached axis at {axis_path}. Run action='build_axis' first.",
                metadata={"action": "score_delta"},
            )

        try:
            import numpy as np
        except ImportError:
            return invalid_input_result(
                self.name, "numpy required.",
                metadata={"action": "score_delta"},
            )

        with open(axis_path) as f:
            data = json.load(f)
        if target_celltype not in data["axes"]:
            return invalid_input_result(
                self.name,
                f"No axis for '{target_celltype}'. Available: {list(data['axes'].keys())}",
                metadata={"action": "score_delta"},
            )

        d = data["axes"][target_celltype]
        v = np.asarray(d["axis"])
        delta = np.asarray(delta_embedding)
        if delta.shape != v.shape:
            return invalid_input_result(
                self.name,
                f"Shape mismatch: delta is {delta.shape}, axis is {v.shape}.",
                metadata={"action": "score_delta"},
            )

        delta_norm = float(np.linalg.norm(delta))
        v_norm = float(np.linalg.norm(v))
        if delta_norm == 0 or v_norm == 0:
            return invalid_input_result(
                self.name, "Zero-norm vector — cannot compute cosine.",
                metadata={"action": "score_delta"},
            )
        cos_score = float(np.dot(delta, v) / (delta_norm * v_norm))
        # Signed projection (in axis units, not normalized) — useful for magnitude interpretation
        proj = float(np.dot(delta, v) / v_norm)

        summary = (
            f"Young-axis score for {target_celltype}:\n"
            f"  cosine similarity: {cos_score:+.4f}   ({'youthifying' if cos_score > 0 else 'aging'})\n"
            f"  signed projection: {proj:+.4f} (in 512-d embedding units)\n"
            f"  ||Δ||  = {delta_norm:.4f}\n"
            f"  ||v||  = {v_norm:.4f}\n"
            f"\nInterpretation: cosine ∈ [-1, 1]. Higher = stronger shift toward young centroid."
        )
        return success_result(
            self.name, summary,
            structured_payload={
                "celltype":     target_celltype,
                "cosine_score": cos_score,
                "projection":   proj,
                "delta_norm":   delta_norm,
                "axis_norm":    v_norm,
            },
            metadata={"action": "score_delta", "celltype": target_celltype},
        )

    # ── show_axis ─────────────────────────────────────────────────────────────
    def _show_axis(self) -> tuple[str, dict]:
        axis_path = self._axis_path()
        if not axis_path.exists():
            return invalid_input_result(
                self.name,
                f"No cached axis at {axis_path}. Run action='build_axis' first.",
                metadata={"action": "show_axis"},
            )
        with open(axis_path) as f:
            data = json.load(f)
        compact = {
            "embedding_dim":  data["embedding_dim"],
            "n_cells_total":  data["n_cells_total"],
            "source_file":    data["source_file"],
            "skipped":        data.get("skipped", []),
            "axes": {
                ct: {k: v for k, v in d.items() if k not in ("centroid_young", "centroid_old", "axis")}
                for ct, d in data["axes"].items()
            },
        }
        summary, _ = json_to_pretty_text(compact, 8000)
        return success_result(
            self.name, summary,
            structured_payload=compact,
            metadata={"action": "show_axis"},
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
