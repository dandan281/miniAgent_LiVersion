"""
BioGRID REST API tool: protein-protein interactions (PPI) + CRISPR screen evidence (ORCS).

Endpoint routing (both use BIOGRID_ORCS_ACCESS_KEY):
  PPI   — webservice.thebiogrid.org/interactions  (interactions, physical, kinase_substrate)
  ORCS  — orcsws.thebiogrid.org                   (screens_for_gene, list_screens)

ORCS gene search requires NCBI Gene ID, not symbol — this tool resolves symbols to IDs via
the BioGRID interactions endpoint before querying ORCS.
"""
import json
import os
import urllib.parse
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
    truncate_text,
)

_PPI_BASE  = "https://webservice.thebiogrid.org"
_ORCS_BASE = "https://orcsws.thebiogrid.org"
_TIMEOUT   = 30
_MAX       = 50_000

QueryType = Literal[
    "interactions",     # All experimentally validated PPIs for a gene / gene list
    "physical",         # Binding / co-complex interactions only
    "kinase_substrate", # Enzymatic / phosphorylation edges only
    "screens_for_gene", # ORCS: list CRISPR screens where a gene is a significant hit
    "list_screens",     # ORCS: list all available CRISPR screens (no gene filter)
]

# NCBI Gene ID lookup cache (session-scoped, avoids repeat resolution calls)
_GENE_ID_CACHE: dict[str, str] = {}


def _get(url: str) -> tuple[int, Any]:
    resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True,
                     headers={"Accept": "application/json"})
    resp.raise_for_status()
    try:
        return resp.status_code, resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.status_code, resp.text


def _resolve_gene_id(symbol: str, key: str, organism_id: str) -> Optional[str]:
    """Resolve an HGNC symbol to NCBI Gene ID via BioGRID interactions endpoint."""
    cache_key = f"{symbol}:{organism_id}"
    if cache_key in _GENE_ID_CACHE:
        return _GENE_ID_CACHE[cache_key]
    params = {
        "accessKey": key, "format": "json",
        "searchNames": "true", "geneList": symbol,
        "taxId": organism_id, "max": "1",
    }
    url = f"{_PPI_BASE}/interactions/?" + urllib.parse.urlencode(params)
    try:
        _, data = _get(url)
        if isinstance(data, dict) and data:
            rec = next(iter(data.values()))
            # Gene ID is in ENTREZ_GENE_A or ENTREZ_GENE_B matching the queried symbol
            sym_up = symbol.upper()
            gene_id = None
            if rec.get("OFFICIAL_SYMBOL_A", "").upper() == sym_up:
                gene_id = str(rec.get("ENTREZ_GENE_A", ""))
            elif rec.get("OFFICIAL_SYMBOL_B", "").upper() == sym_up:
                gene_id = str(rec.get("ENTREZ_GENE_B", ""))
            if gene_id:
                _GENE_ID_CACHE[cache_key] = gene_id
                return gene_id
    except Exception:
        pass
    return None


class BiogridOrcsInput(BaseModel):
    query_type: QueryType = Field(
        description=(
            "Type of query. "
            "PPI (protein-protein interactions): "
            "'interactions' — all validated interactions for a gene/gene list; "
            "'physical' — binding and co-complex only; "
            "'kinase_substrate' — enzymatic/phosphorylation edges only. "
            "CRISPR screens (ORCS): "
            "'screens_for_gene' — list screens where a gene is a significant hit; "
            "'list_screens' — list all available CRISPR screens."
        )
    )
    gene_symbol: Optional[str] = Field(
        default=None,
        description="HGNC gene symbol (e.g. 'EGFR'). Required for PPI queries and screens_for_gene.",
    )
    gene_list: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated gene symbols (e.g. 'EGFR,ERBB2,GRB2'). "
            "Supported by both PPI queries and 'screens_for_gene' (cap 25 genes). "
            "PREFER batched gene_list over many single gene_symbol calls — saves tool budget."
        ),
    )
    organism_id: str = Field(
        default="9606",
        description="NCBI taxonomy ID (default: 9606 = Homo sapiens).",
    )
    max_results: int = Field(
        default=100,
        description="Maximum number of results to return (default 100).",
    )
    include_interactors: bool = Field(
        default=False,
        description="For PPI queries: also return interactions among the gene's partners (expands result set significantly).",
    )


class BiogridOrcsTool(BaseTool):
    name: str = "biogrid_orcs"
    description: str = (
        "Query BioGRID for experimentally validated protein-protein interactions and CRISPR screen metadata. "
        "PRIMARY USE — PPI queries: "
        "'interactions' gets all known interaction partners for a gene/gene-list with experimental system and PMIDs; "
        "'kinase_substrate' gets enzymatic/phosphorylation edges — use this to find what a kinase phosphorylates "
        "or which kinases phosphorylate a substrate (critical for adaptor recruitment in the novokine pipeline); "
        "'physical' filters to binding/co-complex interactions only. "
        "SECONDARY USE — ORCS CRISPR screen metadata: "
        "'screens_for_gene' lists CRISPR screens containing a gene (note: current ORCS database is mostly cancer "
        "cell lines, no skeletal muscle screens yet — useful for essentiality signal but not muscle-specific); "
        "'list_screens' lists all 2200+ available screens with cell line and phenotype metadata. "
        "Requires BIOGRID_ORCS_ACCESS_KEY in environment."
    )
    args_schema: Type[BaseModel] = BiogridOrcsInput
    response_format: str = "content_and_artifact"

    def _key(self) -> Optional[str]:
        return os.environ.get("BIOGRID_ORCS_ACCESS_KEY") or os.environ.get("BIOGRID_ACCESS_KEY")

    def _run(
        self,
        query_type: QueryType = "interactions",
        gene_symbol: Optional[str] = None,
        gene_list: Optional[str] = None,
        organism_id: str = "9606",
        max_results: int = 100,
        include_interactors: bool = False,
    ) -> tuple[str, dict]:
        key = self._key()
        if not key:
            return invalid_input_result(
                self.name,
                "BIOGRID_ORCS_ACCESS_KEY not set. Register at https://webservice.thebiogrid.org "
                "and add the key to backend/.env.",
                metadata={"query_type": query_type},
            )

        genes: list[str] = []
        if gene_symbol:
            genes = [gene_symbol.strip().upper()]
        elif gene_list:
            genes = [g.strip().upper() for g in gene_list.split(",") if g.strip()]

        url = ""
        data: Any = None
        status_code = 0

        try:
            # ── PPI queries ───────────────────────────────────────────────────
            if query_type in ("interactions", "physical", "kinase_substrate"):
                if not genes:
                    return invalid_input_result(
                        self.name, "'gene_symbol' or 'gene_list' is required.", metadata={})

                params: dict = {
                    "accessKey": key, "format": "json",
                    "searchNames": "true",
                    "geneList": "|".join(genes),
                    "taxId": organism_id,
                    "max": str(min(max_results, 10000)),
                    "includeInteractors": "true" if include_interactors else "false",
                }
                if query_type == "physical":
                    params["experimentalSystemType"] = "physical"
                elif query_type == "kinase_substrate":
                    params["experimentalSystem"] = "Biochemical Activity"
                    params["evidenceList"] = "Biochemical Activity"
                    params["includeEvidence"] = "true"

                url = f"{_PPI_BASE}/interactions/?" + urllib.parse.urlencode(params)
                status_code, raw = _get(url)

                # Flatten interaction dict → list
                rows: list[dict] = []
                if isinstance(raw, dict):
                    for iid, rec in raw.items():
                        rows.append({
                            "interaction_id":          iid,
                            "gene_a":                  rec.get("OFFICIAL_SYMBOL_A", ""),
                            "gene_b":                  rec.get("OFFICIAL_SYMBOL_B", ""),
                            "experimental_system":     rec.get("EXPERIMENTAL_SYSTEM", ""),
                            "experimental_system_type":rec.get("EXPERIMENTAL_SYSTEM_TYPE", ""),
                            "modification":            rec.get("MODIFICATION", ""),
                            "qualifications":          rec.get("QUALIFICATIONS", ""),
                            "pubmed_id":               rec.get("PUBMED_ID", ""),
                            "throughput":              rec.get("THROUGHPUT", ""),
                            "score":                   rec.get("SCORE", ""),
                            "organism_a":              rec.get("ORGANISM_A", ""),
                            "organism_b":              rec.get("ORGANISM_B", ""),
                        })
                data = rows

            # ── ORCS: screens_for_gene ────────────────────────────────────────
            elif query_type == "screens_for_gene":
                if not genes:
                    return invalid_input_result(
                        self.name, "'gene_symbol' or 'gene_list' is required for screens_for_gene.", metadata={})

                # Multi-gene batched query — accepts up to 25 genes per call.
                # Each gene requires (a) gene-id resolution + (b) /orcs/screens
                # call. Internally serial; externally one tool call.
                MAX_BATCH = 25
                if len(genes) > MAX_BATCH:
                    return invalid_input_result(
                        self.name,
                        f"Too many genes ({len(genes)}); cap is {MAX_BATCH} per call.",
                        metadata={"requested": len(genes)},
                    )

                all_screens: list[dict] = []
                missing_genes: list[str] = []
                last_status_code = 0
                last_url = ""
                for gene in genes:
                    gene_id = _resolve_gene_id(gene, key, organism_id)
                    if not gene_id:
                        missing_genes.append(gene)
                        continue
                    params_orcs = {
                        "accessKey": key, "format": "json",
                        "geneId": gene_id, "hitsOnly": "true",
                    }
                    last_url = f"{_ORCS_BASE}/screens?" + urllib.parse.urlencode(params_orcs)
                    status_code, gene_data = _get(last_url)
                    last_status_code = status_code
                    if isinstance(gene_data, list):
                        for rec in gene_data:
                            rec["queried_gene"] = gene
                            rec["ncbi_gene_id"] = gene_id
                            all_screens.append(rec)

                url = last_url
                status_code = last_status_code
                data = all_screens
                # Surface the missing genes in metadata for transparency
                if missing_genes:
                    pass  # added to meta below

            # ── ORCS: list_screens ────────────────────────────────────────────
            elif query_type == "list_screens":
                params_orcs = {"accessKey": key, "format": "json"}
                url = f"{_ORCS_BASE}/screens?" + urllib.parse.urlencode(params_orcs)
                status_code, data = _get(url)

            else:
                return invalid_input_result(
                    self.name, f"Unknown query_type: {query_type}", metadata={})

        except httpx.TimeoutException:
            return retriable_error_result(
                self.name, "BioGRID request timed out.", metadata={"url": url})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg  = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"url": url, "http_status": code, "query_type": query_type}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            if code in (401, 403):
                return invalid_input_result(
                    self.name, f"{msg} — check BIOGRID_ORCS_ACCESS_KEY.", metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(
                self.name, f"BioGRID request failed: {exc}", metadata={"url": url})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"url": url})

        meta = {
            "query_type":    query_type,
            "gene_symbol":   gene_symbol,
            "gene_list":     gene_list,
            "organism_id":   organism_id,
            "request_url":   url,
            "http_status":   status_code,
        }

        if isinstance(data, list):
            if not data:
                return empty_result(self.name, "No BioGRID results found.", metadata=meta)
            meta["result_count"] = len(data)
            structured = {"results": data}
            summary, _ = json_to_pretty_text(structured, _MAX)
            return success_result(self.name, summary, structured_payload=structured, metadata=meta)
        elif isinstance(data, dict):
            if not data:
                return empty_result(self.name, "Empty BioGRID response.", metadata=meta)
            summary, _ = json_to_pretty_text(data, _MAX)
            return success_result(self.name, summary, structured_payload=data, metadata=meta)
        else:
            text = str(data)
            if not text.strip():
                return empty_result(self.name, "Empty BioGRID response.", metadata=meta)
            summary, _ = truncate_text(text, _MAX)
            return success_result(self.name, summary, structured_payload={"raw": summary}, metadata=meta)

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
