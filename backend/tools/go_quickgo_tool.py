"""
QuickGO REST API tool: Gene Ontology annotations for a gene or UniProt entry.

Free public endpoint at https://www.ebi.ac.uk/QuickGO/services/ — no API key
required.

Used by the novokine pipeline to retrieve the GO biological-process (BP)
terms per receptor gene, which feed the "mechanistic plausibility" layer of
the v4.0 feature matrix.

The agent should pass UniProt accessions (resolved via the uniprot_api tool)
when possible — QuickGO accepts plain gene symbols only via a free-text
geneProductSubset path, which is less reliable than the geneProductId path.
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

_BASE = "https://www.ebi.ac.uk/QuickGO/services/annotation/search"
_TIMEOUT = 30
_MAX = 50_000
_HEADERS = {"Accept": "application/json"}

AspectName = Literal["biological_process", "molecular_function", "cellular_component", "any"]


def _fetch(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    resp = httpx.get(url, params=params, timeout=_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    return resp.status_code, resp.json()


def _build_gene_product_ids(raw: str) -> list[str]:
    """Accept UniProt accessions or 'UniProtKB:P00533'-style identifiers and
    return the canonical form QuickGO expects.
    """
    out: list[str] = []
    for token in raw.replace(",", "\n").splitlines():
        s = token.strip()
        if not s:
            continue
        if ":" not in s and s[0:1].isalpha():
            s = f"UniProtKB:{s}"
        out.append(s)
    return out


class GoQuickGoInput(BaseModel):
    gene_product_ids: str = Field(
        description=(
            "Comma- or newline-separated UniProt accessions (e.g. 'P00533, P40189'). "
            "Bare accessions are auto-prefixed with 'UniProtKB:'. The companion "
            "uniprot_api tool can resolve gene symbols to accessions."
        )
    )
    aspect: AspectName = Field(
        default="biological_process",
        description=(
            "GO aspect to filter on: 'biological_process' (default), "
            "'molecular_function', 'cellular_component', or 'any'."
        ),
    )
    taxon_id: int = Field(
        default=9606,
        description="NCBI taxon ID. 9606 = Homo sapiens (default).",
    )
    limit: int = Field(
        default=50,
        description="Maximum annotations per gene product (1-100). QuickGO caps at 100.",
    )
    only_experimental: bool = Field(
        default=False,
        description=(
            "If true, keep only annotations with experimental evidence codes "
            "(EXP, IDA, IPI, IMP, IGI, IEP). Useful for high-confidence BP terms."
        ),
    )


_EXPERIMENTAL_ECO_CODES = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP"}


class GoQuickGoTool(BaseTool):
    name: str = "go_annotations"
    description: str = (
        "Query QuickGO for Gene Ontology annotations of UniProt entries. "
        "Returns GO terms with evidence codes, filtered by aspect (default: biological_process). "
        "Pass UniProt accessions; the uniprot_api tool can resolve gene symbols first. "
        "No API key required."
    )
    args_schema: Type[BaseModel] = GoQuickGoInput
    response_format: str = "content_and_artifact"

    def _normalize_results(
        self, raw: list[dict[str, Any]], only_experimental: bool
    ) -> dict[str, list[dict[str, Any]]]:
        per_gene: dict[str, list[dict[str, Any]]] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            evidence = row.get("evidenceCode") or row.get("goEvidence")
            if only_experimental:
                code = (row.get("goEvidence") or "").upper()
                if code not in _EXPERIMENTAL_ECO_CODES:
                    continue
            gene_product = row.get("geneProductId") or row.get("symbol") or "?"
            per_gene.setdefault(gene_product, []).append(
                {
                    "go_id": row.get("goId"),
                    "go_name": row.get("goName"),
                    "go_aspect": row.get("goAspect"),
                    "evidence_code": evidence,
                    "qualifier": row.get("qualifier"),
                    "reference": row.get("reference"),
                    "symbol": row.get("symbol"),
                }
            )
        return per_gene

    def _run(
        self,
        gene_product_ids: str,
        aspect: AspectName = "biological_process",
        taxon_id: int = 9606,
        limit: int = 50,
        only_experimental: bool = False,
    ) -> tuple[str, dict]:
        idents = _build_gene_product_ids(gene_product_ids)
        if not idents:
            return invalid_input_result(
                self.name,
                "No UniProt accessions provided.",
                metadata={"gene_product_ids": gene_product_ids},
            )

        params: dict[str, Any] = {
            "geneProductId": ",".join(idents),
            "taxonId": taxon_id,
            "limit": max(1, min(int(limit), 100)),
            # QuickGO omits the human-readable goName unless explicitly requested.
            "includeFields": "goName",
        }
        if aspect and aspect != "any":
            params["aspect"] = aspect

        try:
            status_code, data = _fetch(_BASE, params)
        except httpx.TimeoutException:
            return retriable_error_result(self.name, "QuickGO request timed out.", metadata={"url": _BASE})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"url": _BASE, "http_status": code, "body": exc.response.text[:300]}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(self.name, f"QuickGO request failed: {exc}", metadata={"url": _BASE})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"url": _BASE})

        rows = data.get("results", []) if isinstance(data, dict) else []
        per_gene = self._normalize_results(rows, only_experimental)
        total = sum(len(v) for v in per_gene.values())
        meta = {
            "gene_product_ids": idents,
            "aspect": aspect,
            "taxon_id": taxon_id,
            "limit": params["limit"],
            "only_experimental": only_experimental,
            "request_url": _BASE,
            "http_status": status_code,
            "annotation_count": total,
            "total_hits": data.get("numberOfHits") if isinstance(data, dict) else None,
        }
        if total == 0:
            return empty_result(
                self.name,
                "QuickGO returned no annotations for the given gene products and aspect.",
                metadata=meta,
            )
        structured = {"annotations_by_gene": per_gene, "annotation_count": total}
        text, _ = json_to_pretty_text(structured, _MAX)
        return success_result(self.name, text, structured_payload=structured, metadata=meta)

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
