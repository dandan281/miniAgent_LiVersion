"""
CellxGene Where-My-Gene tool: query CZ Cell Census for receptor expression
in tissue/cell-type slices. Free, no API key.

Uses the CZ "Where My Gene" (WMG) HTTP endpoint at
  https://api.cellxgene.cziscience.com/wmg/v2/query
which returns per-cell-type fraction-expressing and mean-expression summaries
for a small set of HGNC symbols. The Python SDK (`cellxgene-census`) is
intentionally NOT imported — it would pull a heavy tiledb runtime.

Two actions:
- expression_summary: fraction expressing + mean expression per cell type
- cell_type_inventory: list of CZ cell-ontology cell types in a tissue

Mock mode: set CELLXGENE_MODE=mock to return deterministic synthetic data
without any network call.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
from typing import Any, Literal, Optional, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    execution_error_result,
    invalid_input_result,
    retriable_error_result,
    success_result,
)

_BASE = "https://api.cellxgene.cziscience.com"
_WMG_QUERY = f"{_BASE}/wmg/v2/query"
_WMG_FILTERS = f"{_BASE}/wmg/v2/filters"
_WMG_PRIMARY_FILTERS = f"{_BASE}/wmg/v2/primary_filter_dimensions"
_TIMEOUT = 20.0
_MAX_GENES = 25
_MAX_CALLS_PER_RUN = 2
_GENE_RE = re.compile(r"^[A-Z0-9-]{1,12}$")

# Curated HGNC symbol -> Ensembl gene id for a small set of muscle-relevant
# receptors. The WMG endpoint requires Ensembl IDs in its v2 query body; if we
# don't have the mapping locally we fall back to using the symbol directly,
# which the API may reject — that's caught and surfaced as a retriable error.
_SYMBOL_TO_ENSG: dict[str, str] = {
    "FGFR1": "ENSG00000077782",
    "FGFR2": "ENSG00000066468",
    "FGFR3": "ENSG00000068078",
    "FGFR4": "ENSG00000160867",
    "ERBB2": "ENSG00000141736",
    "ERBB3": "ENSG00000065361",
    "ERBB4": "ENSG00000178568",
    "EGFR": "ENSG00000146648",
    "IGF1R": "ENSG00000140443",
    "INSR": "ENSG00000171105",
    "MET": "ENSG00000105976",
    "IL6R": "ENSG00000160712",
    "IL6ST": "ENSG00000134352",
    "LIFR": "ENSG00000113594",
    "OSMR": "ENSG00000145623",
    "IFNAR1": "ENSG00000142166",
    "IFNAR2": "ENSG00000159110",
    "ACVR2B": "ENSG00000114739",
    "BMPR1A": "ENSG00000107779",
    "TGFBR2": "ENSG00000163513",
    "TNFRSF1A": "ENSG00000067182",
    "TNFRSF1B": "ENSG00000028137",
    "PAX7": "ENSG00000009709",
    "MYOD1": "ENSG00000129152",
}

# Tissue-name -> UBERON id. Mappings restricted to UBERON ids that the CZ
# Cell Census WMG v2 endpoint actually serves (verified 2026-05-04 against
# /wmg/v2/primary_filter_dimensions, 64 human tissues). Notably, WMG does
# NOT carry a specific "skeletal muscle" (UBERON:0001134) slice — the closest
# available proxy is "musculature" (UBERON:0001015), so 'skeletal muscle'
# requests are routed there with a warning.
_TISSUE_TO_UBERON: dict[str, str] = {
    "skeletal muscle": "UBERON:0001015",
    "musculature": "UBERON:0001015",
    "muscle": "UBERON:0001015",
    "heart": "UBERON:0000948",
    "tendon": "UBERON:8480009",
}
_SKELETAL_MUSCLE_PROXY_WARNING = (
    "WMG has no specific 'skeletal muscle' slice; routed to UBERON:0001015 "
    "'musculature' as the closest available proxy."
)

# Curated cell-ontology inventory for skeletal muscle (mock fallback &
# typical members; WMG live cell-type list is fetched via the filters
# endpoint when possible).
_SKM_CELL_TYPES_FALLBACK: list[dict[str, str]] = [
    {"id": "CL:0000056", "label": "myoblast"},
    {"id": "CL:0000515", "label": "skeletal muscle myoblast"},
    {"id": "CL:0000189", "label": "slow muscle cell"},
    {"id": "CL:0000190", "label": "fast muscle cell"},
    {"id": "CL:0000746", "label": "cardiac muscle cell"},
    {"id": "CL:0008002", "label": "skeletal muscle satellite cell"},
    {"id": "CL:0000138", "label": "chondrocyte"},
    {"id": "CL:0000057", "label": "fibroblast"},
    {"id": "CL:0002601", "label": "smooth muscle cell of bladder"},
    {"id": "CL:0000669", "label": "pericyte"},
    {"id": "CL:0000115", "label": "endothelial cell"},
    {"id": "CL:0000235", "label": "macrophage"},
    {"id": "CL:0000084", "label": "T cell"},
    {"id": "CL:0000235", "label": "skeletal muscle myofiber"},
    {"id": "CL:0000800", "label": "mature gamma-delta T cell"},
]


def _is_mock() -> bool:
    return os.environ.get("CELLXGENE_MODE", "").strip().lower() == "mock"


def _mock_fraction(gene: str, cell_type: str) -> float:
    h = int(hashlib.md5(f"{gene}|{cell_type}|frac".encode()).hexdigest(), 16)
    return round((h % 80) / 100.0, 3)


def _mock_mean(gene: str, cell_type: str) -> float:
    h = int(hashlib.md5(f"{gene}|{cell_type}|mean".encode()).hexdigest(), 16)
    return round((h % 50) / 10.0, 3)


def _mock_expression_summary(
    genes: list[str],
    tissue: str,
    cell_types: Optional[list[str]],
) -> dict[str, Any]:
    cts = cell_types or [c["label"] for c in _SKM_CELL_TYPES_FALLBACK[:8]]
    per_gene: dict[str, dict[str, dict[str, float]]] = {}
    for g in genes:
        per_gene[g] = {}
        for ct in cts:
            per_gene[g][ct] = {
                "fraction_expressing": _mock_fraction(g, ct),
                "mean_expression": _mock_mean(g, ct),
            }
    return {
        "mode": "mock",
        "tissue": tissue,
        "organism": "Homo sapiens",
        "genes": genes,
        "cell_types_queried": cts,
        "expression": per_gene,
    }


def _mock_cell_type_inventory(tissue: str) -> dict[str, Any]:
    return {
        "mode": "mock",
        "tissue": tissue,
        "cell_types": _SKM_CELL_TYPES_FALLBACK,
    }


Action = Literal["expression_summary", "cell_type_inventory"]


class CellxgeneInput(BaseModel):
    action: Action = Field(
        description=(
            "Which CZ Cell Census query to run. "
            "'expression_summary' → per-cell-type fraction-expressing + mean "
            "expression for a list of HGNC gene symbols. "
            "'cell_type_inventory' → list of cell-ontology cell types in the tissue."
        )
    )
    genes: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of HGNC gene symbols (1-25), required for 'expression_summary'. "
            "Symbols only (e.g. ['FGFR1','ERBB2']); regex ^[A-Z0-9-]{1,12}$."
        ),
    )
    tissue: str = Field(
        default="skeletal muscle",
        description="Tissue name (default 'skeletal muscle'). Mapped to a UBERON id internally.",
    )
    organism: str = Field(
        default="Homo sapiens",
        description="Organism (default 'Homo sapiens'). Only Homo sapiens has a curated WMG slice.",
    )
    cell_types: Optional[list[str]] = Field(
        default=None,
        description="Optional restriction to specific cell-ontology labels (free text matched against returned list).",
    )


class CellxgeneTool(BaseTool):
    name: str = "cellxgene_expression"
    description: str = (
        "Query the CZ Cell Census 'Where My Gene' (WMG) API for receptor expression "
        "in human tissue/cell-type slices. Free, no API key. "
        "Action 'expression_summary' returns per-cell-type fraction expressing + mean "
        "expression for a small list of HGNC symbols (e.g. confirm a novokine receptor "
        "pair is co-expressed in skeletal muscle satellite cells). "
        "Action 'cell_type_inventory' lists CZ cell-ontology cell types in the tissue. "
        "Set CELLXGENE_MODE=mock to return deterministic synthetic data."
    )
    args_schema: Type[BaseModel] = CellxgeneInput
    response_format: str = "content_and_artifact"

    # ---------- helpers ----------

    def _validate_genes(self, genes: Optional[list[str]]) -> Optional[str]:
        if not genes:
            return "expression_summary requires a non-empty 'genes' list (max 25 HGNC symbols)."
        if len(genes) > _MAX_GENES:
            return f"Too many genes ({len(genes)}); maximum is {_MAX_GENES} per call."
        bad = [g for g in genes if not isinstance(g, str) or not _GENE_RE.match(g)]
        if bad:
            return f"Invalid HGNC symbol(s): {bad[:5]} (regex ^[A-Z0-9-]{{1,12}}$)."
        return None

    def _resolve_tissue(self, tissue: str) -> str:
        return _TISSUE_TO_UBERON.get(tissue.strip().lower(), "")

    def _resolve_genes(self, genes: list[str]) -> tuple[list[str], list[str]]:
        """Return (ensembl_ids, unmapped_symbols)."""
        ens: list[str] = []
        missing: list[str] = []
        for g in genes:
            eid = _SYMBOL_TO_ENSG.get(g)
            if eid:
                ens.append(eid)
            else:
                missing.append(g)
        return ens, missing

    def _live_expression_summary(
        self,
        genes: list[str],
        tissue: str,
        organism: str,
        cell_types: Optional[list[str]],
    ) -> tuple[dict[str, Any], list[str], int, list[str]]:
        """Returns (payload, warnings, http_calls_made, request_urls)."""
        warnings: list[str] = []
        urls: list[str] = []
        ensembl_ids, unmapped = self._resolve_genes(genes)
        if unmapped:
            warnings.append(
                f"unmapped_symbols={unmapped} (no local HGNC→Ensembl mapping; skipped from live query)"
            )
        if not ensembl_ids:
            raise RuntimeError(
                "No HGNC→Ensembl mapping available locally for any of the requested genes; "
                "live WMG call would fail. Use CELLXGENE_MODE=mock or extend _SYMBOL_TO_ENSG."
            )

        uberon = self._resolve_tissue(tissue)
        if not uberon:
            raise RuntimeError(
                f"No UBERON id known for tissue {tissue!r}; extend _TISSUE_TO_UBERON or use mock mode."
            )
        if tissue.strip().lower() == "skeletal muscle":
            warnings.append(_SKELETAL_MUSCLE_PROXY_WARNING)

        # WMG v2 /query does NOT accept tissue filtering in the request body
        # (verified 2026-05-04: only gene_ontology_term_ids and
        # organism_ontology_term_id are valid keys in `filter`). Tissue is
        # filtered client-side from the response.
        body = {
            "filter": {
                "gene_ontology_term_ids": ensembl_ids,
                "organism_ontology_term_id": "NCBITaxon:9606",
            },
            "is_rollup": True,
        }
        urls.append(_WMG_QUERY)
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _WMG_QUERY,
                json=body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        calls = 1
        resp.raise_for_status()
        data = resp.json() if resp.content else {}

        # WMG v2 actual response shape (verified 2026-05-04):
        #   expression_summary[ensg][UBERON_id][CL_id]["aggregated"] = {
        #       "me": mean_expr, "n": n_expressing, "pc": frac_expressing, "tpc": ...
        #   }
        #   term_id_labels.cell_types: list of {ENSG/CL: <human-readable label>}
        expression_map: dict[str, dict[str, dict[str, float]]] = {g: {} for g in genes}
        ensg_to_symbol = {_SYMBOL_TO_ENSG[g]: g for g in genes if g in _SYMBOL_TO_ENSG}

        # Build CL id -> label map from term_id_labels.cell_types.
        # Actual shape (verified 2026-05-04):
        #   term_id_labels.cell_types[UBERON_id][CL_id]["aggregated"]["name"] = "fibroblast"
        cl_label_map: dict[str, str] = {}
        til = (data.get("term_id_labels") or {}).get("cell_types") or {}
        if isinstance(til, dict):
            tissue_block = til.get(uberon, {})
            if isinstance(tissue_block, dict):
                for cl_id, payload in tissue_block.items():
                    if isinstance(payload, dict):
                        agg = payload.get("aggregated") or {}
                        name = agg.get("name") if isinstance(agg, dict) else None
                        if name:
                            cl_label_map[str(cl_id)] = str(name)

        es = data.get("expression_summary") or {}
        if isinstance(es, dict):
            for ensg, by_tissue in es.items():
                sym = ensg_to_symbol.get(ensg, ensg)
                if not isinstance(by_tissue, dict):
                    continue
                tissue_data = by_tissue.get(uberon)
                if not isinstance(tissue_data, dict):
                    continue
                for cl_id, cell_data in tissue_data.items():
                    agg = (cell_data or {}).get("aggregated") if isinstance(cell_data, dict) else None
                    if not isinstance(agg, dict):
                        continue
                    pc = agg.get("pc")
                    me = agg.get("me")
                    label = cl_label_map.get(str(cl_id), str(cl_id))
                    expression_map[sym][label] = {
                        "cell_type_ontology_id": str(cl_id),
                        "fraction_expressing": round(float(pc), 4) if pc is not None else None,
                        "mean_expression": round(float(me), 4) if me is not None else None,
                        "n_cells_expressing": agg.get("n"),
                    }

        if cell_types:
            wanted = {ct.strip().lower() for ct in cell_types}
            for sym in list(expression_map.keys()):
                expression_map[sym] = {
                    k: v for k, v in expression_map[sym].items()
                    if any(w in k.lower() for w in wanted)
                }

        payload = {
            "mode": "live",
            "tissue": tissue,
            "tissue_uberon": uberon,
            "organism": organism,
            "genes": genes,
            "ensembl_ids": ensembl_ids,
            "expression": expression_map,
            "snapshot_id": data.get("snapshot_id"),
        }
        return payload, warnings, calls, urls

    def _live_cell_type_inventory(
        self, tissue: str
    ) -> tuple[dict[str, Any], list[str], int, list[str]]:
        warnings: list[str] = []
        uberon = self._resolve_tissue(tissue)
        if not uberon:
            raise RuntimeError(
                f"No UBERON id known for tissue {tissue!r}; cannot query WMG filters."
            )
        body = {
            "filter": {
                "organism_ontology_term_id": "NCBITaxon:9606",
                "tissue_ontology_term_ids": [uberon],
            }
        }
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _WMG_FILTERS,
                json=body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        cts_raw = (data.get("filter_dims") or {}).get("cell_types") or []
        cts: list[dict[str, str]] = []
        for c in cts_raw:
            if isinstance(c, dict):
                cts.append({
                    "id": c.get("cell_type_ontology_term_id") or c.get("id") or "",
                    "label": c.get("name") or c.get("label") or "",
                })
        if not cts:
            warnings.append("WMG filters returned no cell types; falling back to curated list.")
            cts = _SKM_CELL_TYPES_FALLBACK
        return (
            {"mode": "live", "tissue": tissue, "tissue_uberon": uberon, "cell_types": cts},
            warnings,
            1,
            [_WMG_FILTERS],
        )

    # ---------- entry point ----------

    def _run(
        self,
        action: Action = "expression_summary",
        genes: Optional[list[str]] = None,
        tissue: str = "skeletal muscle",
        organism: str = "Homo sapiens",
        cell_types: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        meta_base: dict[str, Any] = {
            "action": action,
            "tissue": tissue,
            "organism": organism,
            "mode": "mock" if _is_mock() else "live",
        }

        if action == "expression_summary":
            err = self._validate_genes(genes)
            if err:
                return invalid_input_result(self.name, err, metadata=meta_base)
        elif action == "cell_type_inventory":
            pass
        else:
            return invalid_input_result(
                self.name,
                f"Unknown action {action!r}; expected 'expression_summary' or 'cell_type_inventory'.",
                metadata=meta_base,
            )

        # Mock path
        if _is_mock():
            try:
                if action == "expression_summary":
                    payload = _mock_expression_summary(genes or [], tissue, cell_types)
                else:
                    payload = _mock_cell_type_inventory(tissue)
            except Exception as exc:
                return execution_error_result(
                    self.name, f"mock generation failed: {exc}", metadata=meta_base
                )
            summary = json.dumps(
                {"action": action, "mode": "mock", "tissue": tissue, "n_genes": len(genes or [])},
                indent=2,
            )
            return success_result(
                self.name,
                summary,
                structured_payload=payload,
                metadata=meta_base,
            )

        # Live path — at most 1 retry, single small call, 20s timeout
        attempts = 0
        last_exc: Exception | None = None
        while attempts < 2:
            attempts += 1
            try:
                if action == "expression_summary":
                    payload, warnings, calls, urls = self._live_expression_summary(
                        genes or [], tissue, organism, cell_types
                    )
                else:
                    payload, warnings, calls, urls = self._live_cell_type_inventory(tissue)
                meta = {
                    **meta_base,
                    "http_calls": calls,
                    "request_urls": urls,
                    "attempts": attempts,
                }
                if calls > _MAX_CALLS_PER_RUN:
                    warnings.append(f"http_calls={calls} exceeded soft cap {_MAX_CALLS_PER_RUN}")
                summary = json.dumps(
                    {
                        "action": action,
                        "mode": "live",
                        "tissue": tissue,
                        "n_genes": len(genes or []),
                        "snapshot_id": payload.get("snapshot_id"),
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
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempts < 2:
                    time.sleep(1.0)
                    continue
                return retriable_error_result(
                    self.name,
                    f"CellxGene WMG request timed out after {_TIMEOUT}s.",
                    metadata={**meta_base, "attempts": attempts},
                )
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                msg = f"HTTP {code}: {exc.response.reason_phrase}"
                meta = {**meta_base, "http_status": code, "attempts": attempts}
                if code == 429 or code >= 500:
                    if attempts < 2:
                        time.sleep(1.0)
                        continue
                    return retriable_error_result(self.name, msg, metadata=meta)
                return execution_error_result(self.name, msg, metadata=meta)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempts < 2:
                    time.sleep(1.0)
                    continue
                return retriable_error_result(
                    self.name,
                    f"CellxGene WMG request failed: {exc}",
                    metadata={**meta_base, "attempts": attempts},
                )
            except RuntimeError as exc:
                # Local validation failure (e.g. unknown UBERON / no Ensembl mapping)
                return invalid_input_result(
                    self.name, str(exc), metadata={**meta_base, "attempts": attempts}
                )
            except Exception as exc:
                return execution_error_result(
                    self.name,
                    f"CellxGene tool error: {exc}",
                    metadata={**meta_base, "attempts": attempts},
                )

        return retriable_error_result(
            self.name,
            f"CellxGene WMG call failed after {attempts} attempts: {last_exc}",
            metadata={**meta_base, "attempts": attempts},
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)


__all__ = ["CellxgeneTool"]
