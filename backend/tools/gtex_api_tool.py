"""
GTEx Portal v2 REST API tool: median bulk tissue expression by gene.

Free public endpoint at https://gtexportal.org/api/v2/ — no API key required.

The agent typically wants tissue-level expression for receptor genes to
populate the "generalizability" / tissue-context layer of the v4.0 feature
matrix. We expose two operations:

  - 'resolve' — gene symbol -> canonical gencodeId (GTEx requires the
    version-suffixed gencode ID for expression queries).
  - 'median_expression' — median TPM across all GTEx tissues for one
    gene, returned as a tissue->TPM dict plus highlighted muscle and
    fibroblast values.

The default datasetId is 'gtex_v8'. GTEx's v10 dataset returns 0 rows for
expression endpoints at time of writing, so we default to v8 unless the
caller specifies otherwise. This default lives in code but is overridable
per-call — no hardcoded gene lists or tissue filters.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Type

import httpx
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

_BASE = "https://gtexportal.org/api/v2"
_TIMEOUT = 30
_MAX = 50_000
_DEFAULT_DATASET = "gtex_v8"
_HEADERS = {"accept": "application/json"}

QueryType = Literal["resolve", "median_expression"]


def _fetch(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    resp = httpx.get(url, params=params, timeout=_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    return resp.status_code, resp.json()


def _resolve_gencode_id(gene_symbol: str) -> tuple[Optional[str], Optional[str]]:
    """Look up the canonical GTEx gencodeId for a gene symbol. Returns
    (gencode_id, gtex_dataset_version_used) or (None, None) on miss.
    """
    url = f"{_BASE}/reference/gene"
    _, data = _fetch(url, {"geneId": gene_symbol})
    rows = data.get("data", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("geneSymbol") or "").upper() == gene_symbol.upper():
            return row.get("gencodeId"), row.get("gencodeVersion")
    if rows:
        return rows[0].get("gencodeId"), rows[0].get("gencodeVersion")
    return None, None


class GtexApiInput(BaseModel):
    query_type: QueryType = Field(
        default="median_expression",
        description=(
            "'median_expression' — return median TPM across GTEx tissues for one gene; "
            "'resolve' — look up the canonical gencodeId for a gene symbol."
        ),
    )
    gene: str = Field(
        description="HGNC gene symbol (e.g. 'EGFR') or versioned Ensembl gene ID (e.g. 'ENSG00000146648.17').",
    )
    dataset_id: str = Field(
        default=_DEFAULT_DATASET,
        description=(
            f"GTEx dataset version. Default '{_DEFAULT_DATASET}'. Pass 'gtex_v10' once it ships "
            f"expression data; today v10 returns 0 rows on the expression endpoints."
        ),
    )
    tissue_filter: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated substrings to filter the returned tissues "
            "(e.g. 'Muscle,fibroblast'). Case-insensitive substring match on tissueSiteDetailId."
        ),
    )


class GtexApiTool(BaseTool):
    name: str = "gtex_expression"
    description: str = (
        "Query GTEx Portal v2 for median bulk-tissue expression of a gene. "
        "Returns per-tissue median TPM across GTEx's ~54 tissues, with skeletal-muscle and "
        "cultured-fibroblast values highlighted (the two tissues most relevant to "
        "fibroblast→myotube transdifferentiation work). "
        "No API key required."
    )
    args_schema: Type[BaseModel] = GtexApiInput
    response_format: str = "content_and_artifact"

    def _maybe_resolve(self, gene: str) -> tuple[Optional[str], Optional[str]]:
        if gene.startswith("ENSG"):
            return gene, None
        return _resolve_gencode_id(gene)

    def _filter_tissues(
        self, rows: list[dict[str, Any]], tissue_filter: Optional[str]
    ) -> list[dict[str, Any]]:
        if not tissue_filter:
            return rows
        needles = [t.strip().lower() for t in tissue_filter.split(",") if t.strip()]
        if not needles:
            return rows
        kept: list[dict[str, Any]] = []
        for row in rows:
            tissue = (row.get("tissueSiteDetailId") or "").lower()
            if any(needle in tissue for needle in needles):
                kept.append(row)
        return kept

    def _summarize_expression(
        self, rows: list[dict[str, Any]], gene: str
    ) -> dict[str, Any]:
        tissues: dict[str, float] = {}
        for row in rows:
            t = row.get("tissueSiteDetailId")
            m = row.get("median")
            if isinstance(t, str) and isinstance(m, (int, float)):
                tissues[t] = float(m)
        sorted_tissues = sorted(tissues.items(), key=lambda kv: -kv[1])
        muscle = {t: v for t, v in tissues.items() if "Muscle" in t}
        fibroblast = {t: v for t, v in tissues.items() if "fibroblast" in t.lower()}
        return {
            "gene": gene,
            "tissue_count": len(tissues),
            "max_tissue": sorted_tissues[0] if sorted_tissues else None,
            "muscle_tissues": muscle,
            "fibroblast_tissues": fibroblast,
            "top_10_tissues": sorted_tissues[:10],
            "all_tissues_tpm": tissues,
        }

    def _run(
        self,
        gene: str,
        query_type: QueryType = "median_expression",
        dataset_id: str = _DEFAULT_DATASET,
        tissue_filter: Optional[str] = None,
    ) -> tuple[str, dict]:
        gene = gene.strip()
        if not gene:
            return invalid_input_result(
                self.name, "Gene symbol or Ensembl ID is required.", metadata={"query_type": query_type}
            )

        try:
            if query_type == "resolve":
                gencode_id, version = self._maybe_resolve(gene)
                if not gencode_id:
                    return empty_result(
                        self.name,
                        f"GTEx has no canonical gencodeId for {gene!r}.",
                        metadata={"gene": gene},
                    )
                structured = {"gene": gene, "gencode_id": gencode_id, "gencode_version": version}
                return success_result(
                    self.name,
                    f"{gene} -> {gencode_id} (gencode {version})",
                    structured_payload=structured,
                    metadata={"gene": gene},
                )

            gencode_id, version = self._maybe_resolve(gene)
            if not gencode_id:
                return empty_result(
                    self.name,
                    f"Could not resolve {gene!r} to a GTEx gencodeId.",
                    metadata={"gene": gene},
                )

            url = f"{_BASE}/expression/medianGeneExpression"
            params = {"gencodeId": gencode_id, "datasetId": dataset_id}
            status_code, data = _fetch(url, params)
            rows = data.get("data", []) if isinstance(data, dict) else []
            filtered = self._filter_tissues(rows, tissue_filter)
            summary_payload = self._summarize_expression(filtered, gene)
            meta = {
                "gene": gene,
                "gencode_id": gencode_id,
                "gencode_version": version,
                "dataset_id": dataset_id,
                "tissue_filter": tissue_filter,
                "request_url": url,
                "http_status": status_code,
                "tissue_count": summary_payload["tissue_count"],
            }
            if summary_payload["tissue_count"] == 0:
                return empty_result(
                    self.name,
                    f"GTEx {dataset_id} returned no tissue expression for {gene} ({gencode_id}).",
                    metadata=meta,
                )
            text, _ = json_to_pretty_text(summary_payload, _MAX)
            return success_result(
                self.name,
                text,
                structured_payload=summary_payload,
                metadata=meta,
            )
        except httpx.TimeoutException:
            return retriable_error_result(self.name, "GTEx request timed out.", metadata={"gene": gene})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"gene": gene, "http_status": code, "body": exc.response.text[:300]}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(self.name, f"GTEx request failed: {exc}", metadata={"gene": gene})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"gene": gene})

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
