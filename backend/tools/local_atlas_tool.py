"""Local atlas expression query tool.

Queries the local human skeletal muscle cell atlas (Kedlian/Lai 2024,
`SKM_human_pp_cells2nuclei_2023-06-22.h5ad`, 183k cells) for per-cell-type,
per-age-bin expression of genes. Fills the gap that
`cellxgene_expression` (CZ Cell Census WMG) cannot serve: WMG pools across
donor age, but the rejuvenation pipeline specifically needs to know whether
a receptor is expressed in **aged** muscle vs **young** muscle.

Atlas layout (verified 2026-05-04):
- shape: 183,161 cells × 29,400 genes
- obs["Age_bin"]: "young" / "old" (83,921 / 99,240)
- obs["annotation_level0"]: cell type, e.g. MuSC, MF-I, MF-II, FB, SMC, T-cell, FAP-like
- var.index: HGNC symbols
- .X: log-normalized expression (sparse CSR)

Atlas is loaded backed=`r` lazily on first query and cached in module state.
This tool intentionally does NOT support live mode — the atlas is a fixed
local snapshot. Use `cellxgene_expression` for live WMG queries that span
many tissues.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Literal, Optional, Type

import numpy as np
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    execution_error_result,
    invalid_input_result,
    success_result,
)

# Module-level atlas cache so repeated calls don't pay the .h5ad open cost.
_ATLAS_LOCK = threading.Lock()
_ATLAS_CACHE: dict[str, Any] = {}

_DEFAULT_ATLAS_PATH = Path(
    "backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad"
)
_ATLAS_PATH_ENV = "MUSCLE_ATLAS_PATH"

# Decision-rule defaults (same as cellxgene_expression skill for consistency).
_DEFAULT_PC_THRESHOLD = 0.10
_DEFAULT_ME_THRESHOLD = 0.5

_AGE_BINS = ("young", "old")


def _atlas_path() -> Path:
    raw = os.environ.get(_ATLAS_PATH_ENV) or str(_DEFAULT_ATLAS_PATH)
    p = Path(raw)
    if not p.is_absolute():
        # Resolve relative to repo root: backend/scripts/* invoked from miniAgent
        p = (Path.cwd() / p).resolve()
    return p


def _load_atlas() -> Any:
    """Lazy-load the atlas with backed='r' and cache it."""
    with _ATLAS_LOCK:
        if "adata" in _ATLAS_CACHE:
            return _ATLAS_CACHE["adata"]
        path = _atlas_path()
        if not path.exists():
            raise FileNotFoundError(
                f"Local atlas not found at {path}. Set {_ATLAS_PATH_ENV} or "
                f"download the SKM atlas via backend/scripts/download_muscle_atlas.py."
            )
        try:
            import anndata as ad  # noqa: WPS433
        except ImportError as exc:
            raise RuntimeError(
                "anndata is required for local_atlas_query but is not installed. "
                "Install via `pip install --target .py311/lib/python3.11/site-packages anndata>=0.10`."
            ) from exc
        adata = ad.read_h5ad(str(path), backed="r")
        _ATLAS_CACHE["adata"] = adata
        _ATLAS_CACHE["path"] = str(path)
        return adata


def _cell_type_inventory_from_atlas(adata: Any) -> list[dict[str, Any]]:
    counts = adata.obs["annotation_level0"].value_counts()
    return [
        {"label": str(k), "n_cells": int(v)}
        for k, v in counts.items()
    ]


def _per_group_expression(
    adata: Any,
    gene: str,
    cell_types: Optional[list[str]],
    age_bins: list[str],
) -> dict[str, Any]:
    """Compute fraction_expressing + mean_expression per (cell_type, age_bin).

    Uses sparse-aware reductions: total expressed cells / total cells,
    sum of expression / total cells.
    """
    import scipy.sparse as sp  # local import — only needed when querying

    if gene not in adata.var.index:
        return {"missing_gene": True}
    col = adata.var.index.get_loc(gene)

    # Pull the entire gene column once. With backed='r' this lazy-reads from
    # disk; for 183k cells × float32 it's ~0.7 MB so we can keep it in RAM.
    raw = adata.X[:, col]
    if sp.issparse(raw):
        gene_vec = np.asarray(raw.todense()).ravel().astype(np.float32, copy=False)
    else:
        gene_vec = np.asarray(raw).ravel().astype(np.float32, copy=False)

    obs_age = adata.obs["Age_bin"].astype(str).to_numpy()
    obs_ct = adata.obs["annotation_level0"].astype(str).to_numpy()

    if cell_types:
        # Substring-insensitive match against each requested label.
        wanted = [c.strip().lower() for c in cell_types if c]
        ct_keys: set[str] = set()
        for ct_label in np.unique(obs_ct):
            lower = str(ct_label).lower()
            if any(w in lower for w in wanted):
                ct_keys.add(str(ct_label))
        ct_iter = sorted(ct_keys)
    else:
        ct_iter = sorted(np.unique(obs_ct).tolist())

    per_ct: dict[str, dict[str, dict[str, float]]] = {}
    for ct in ct_iter:
        per_ct[ct] = {}
        ct_mask = obs_ct == ct
        for age in age_bins:
            age_mask = obs_age == age
            mask = ct_mask & age_mask
            n_total = int(mask.sum())
            if n_total == 0:
                per_ct[ct][age] = {
                    "n_cells": 0,
                    "n_expressing": 0,
                    "fraction_expressing": None,
                    "mean_expression": None,
                }
                continue
            slice_vec = gene_vec[mask]
            n_expressing = int((slice_vec > 0).sum())
            mean_e = float(slice_vec.mean())
            per_ct[ct][age] = {
                "n_cells": n_total,
                "n_expressing": n_expressing,
                "fraction_expressing": round(n_expressing / n_total, 4),
                "mean_expression": round(mean_e, 4),
            }
        # Aged-vs-young deltas (positive = enriched in aged)
        old = per_ct[ct].get("old") or {}
        young = per_ct[ct].get("young") or {}
        if old.get("fraction_expressing") is not None and young.get("fraction_expressing") is not None:
            per_ct[ct]["delta_old_minus_young"] = {
                "fraction_expressing": round(
                    old["fraction_expressing"] - young["fraction_expressing"], 4
                ),
                "mean_expression": round(
                    (old["mean_expression"] or 0) - (young["mean_expression"] or 0), 4
                ),
            }

    return {"per_cell_type": per_ct}


Action = Literal["expression_summary", "cell_type_inventory"]


class LocalAtlasInput(BaseModel):
    action: Action = Field(
        description=(
            "Which atlas query. 'expression_summary' → per-cell-type, per-age-bin "
            "fraction expressing + mean expression for HGNC genes. "
            "'cell_type_inventory' → list of annotation_level0 cell types in the atlas."
        )
    )
    genes: Optional[list[str]] = Field(
        default=None,
        description="HGNC gene symbols (1-25). Required for 'expression_summary'.",
    )
    cell_types: Optional[list[str]] = Field(
        default=None,
        description=(
            "Optional substring filter against atlas annotation_level0 labels (e.g. "
            "['MuSC','MF-I','FB']). Case-insensitive. If omitted, all cell types returned."
        ),
    )
    age_bins: Optional[list[Literal["young", "old"]]] = Field(
        default=None,
        description="Age bins to include (default: both 'young' and 'old').",
    )


class LocalAtlasTool(BaseTool):
    name: str = "local_atlas_query"
    description: str = (
        "Query the local human skeletal muscle cell atlas (Kedlian/Lai 2024, 183k cells) "
        "for per-cell-type × per-age-bin expression of genes. Use this — NOT cellxgene_expression — "
        "when you need to know whether a receptor is expressed in *aged* muscle specifically (the "
        "rejuvenation pipeline target). Returns fraction_expressing + mean_expression for young vs "
        "old donors stratified by annotation_level0 cell type (MuSC, MF-I, MF-II, FB, etc.), plus "
        "delta_old_minus_young per cell type."
    )
    args_schema: Type[BaseModel] = LocalAtlasInput
    response_format: str = "content_and_artifact"

    _MAX_GENES: int = 25

    def _run(
        self,
        action: Action = "expression_summary",
        genes: Optional[list[str]] = None,
        cell_types: Optional[list[str]] = None,
        age_bins: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        meta = {"action": action}

        try:
            adata = _load_atlas()
        except FileNotFoundError as exc:
            return invalid_input_result(self.name, str(exc), metadata=meta)
        except Exception as exc:  # noqa: BLE001
            return execution_error_result(
                self.name, f"atlas load failed: {exc}", metadata=meta
            )
        meta["atlas_path"] = _ATLAS_CACHE.get("path")

        if action == "cell_type_inventory":
            inventory = _cell_type_inventory_from_atlas(adata)
            payload = {
                "atlas_path": _ATLAS_CACHE.get("path"),
                "n_cells_total": int(adata.shape[0]),
                "cell_types": inventory,
                "age_bins": list(_AGE_BINS),
            }
            summary = json.dumps(
                {
                    "action": "cell_type_inventory",
                    "n_cell_types": len(inventory),
                    "n_cells_total": int(adata.shape[0]),
                },
                indent=2,
            )
            return success_result(
                self.name, summary, structured_payload=payload, metadata=meta,
            )

        if action != "expression_summary":
            return invalid_input_result(
                self.name,
                f"Unknown action {action!r}; expected 'expression_summary' or 'cell_type_inventory'.",
                metadata=meta,
            )

        if not genes:
            return invalid_input_result(
                self.name,
                "expression_summary requires a non-empty 'genes' list (HGNC symbols).",
                metadata=meta,
            )
        if len(genes) > self._MAX_GENES:
            return invalid_input_result(
                self.name,
                f"Too many genes ({len(genes)}); maximum is {self._MAX_GENES} per call.",
                metadata=meta,
            )

        target_age_bins = list(age_bins) if age_bins else list(_AGE_BINS)
        unknown_bins = [b for b in target_age_bins if b not in _AGE_BINS]
        if unknown_bins:
            return invalid_input_result(
                self.name,
                f"Invalid age_bins {unknown_bins}; allowed: {list(_AGE_BINS)}.",
                metadata=meta,
            )

        per_gene: dict[str, Any] = {}
        missing: list[str] = []
        for g in genes:
            symbol = str(g).strip().upper()
            try:
                result = _per_group_expression(adata, symbol, cell_types, target_age_bins)
            except Exception as exc:  # noqa: BLE001
                return execution_error_result(
                    self.name,
                    f"per-gene query failed for {symbol!r}: {exc}",
                    metadata=meta,
                )
            if result.get("missing_gene"):
                missing.append(symbol)
                continue
            per_gene[symbol] = result["per_cell_type"]

        warnings: list[str] = []
        if missing:
            warnings.append(f"missing_genes={missing}")

        payload = {
            "atlas_path": _ATLAS_CACHE.get("path"),
            "genes_requested": genes,
            "genes_missing": missing,
            "age_bins": target_age_bins,
            "cell_type_filter": cell_types,
            "thresholds_for_decision": {
                "fraction_expressing": _DEFAULT_PC_THRESHOLD,
                "mean_expression": _DEFAULT_ME_THRESHOLD,
            },
            "expression": per_gene,
        }
        summary = json.dumps(
            {
                "action": "expression_summary",
                "n_genes_queried": len(genes),
                "n_genes_missing": len(missing),
                "age_bins": target_age_bins,
                "n_cell_types_returned": (
                    len(next(iter(per_gene.values()))) if per_gene else 0
                ),
            },
            indent=2,
        )
        return success_result(
            self.name,
            summary,
            structured_payload=payload,
            warnings=warnings,
            metadata=meta,
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)


__all__ = ["LocalAtlasTool"]
