"""
Reactome REST API tool: pathway lookup, enrichment analysis, and pathway hierarchy queries.
"""
import json
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

_BASE = "https://reactome.org/ContentService"
_ANALYSIS_BASE = "https://reactome.org/AnalysisService"
_TIMEOUT = 45
_MAX = 50_000

QueryType = Literal["pathway_for_entity", "pathways_for_genes", "pathway_hierarchy", "entities_in_pathway"]


def _get_json(url: str) -> tuple[int, Any]:
    resp = httpx.get(url, timeout=_TIMEOUT, headers={"Accept": "application/json"})
    resp.raise_for_status()
    try:
        return resp.status_code, resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.status_code, resp.text


def _post_json(url: str, payload: dict) -> tuple[int, Any]:
    resp = httpx.post(url, json=payload, timeout=_TIMEOUT, headers={"Accept": "application/json"})
    resp.raise_for_status()
    try:
        return resp.status_code, resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.status_code, resp.text


class ReactomeApiInput(BaseModel):
    query_type: QueryType = Field(
        description=(
            "Type of query: "
            "'pathway_for_entity' — fetch pathways for a single UniProt accession or gene symbol; "
            "'pathways_for_genes' — fetch pathways for a comma-separated list of gene symbols (overrepresentation); "
            "'pathway_hierarchy' — get top-level pathway tree for Homo sapiens; "
            "'entities_in_pathway' — list all proteins in a given Reactome pathway stable ID."
        )
    )
    identifier: Optional[str] = Field(
        default=None,
        description=(
            "UniProt accession (e.g. 'P00533'), HGNC gene symbol (e.g. 'EGFR'), "
            "or Reactome stable ID (e.g. 'R-HSA-1257604') depending on query_type."
        ),
    )
    gene_list: Optional[str] = Field(
        default=None,
        description="Comma-separated HGNC gene symbols for 'pathways_for_genes' query (e.g. 'EGFR,FGFR1,GRB2').",
    )
    species: str = Field(
        default="9606",
        description="NCBI taxonomy ID for species filter (default: 9606 = Homo sapiens).",
    )


class ReactomeApiTool(BaseTool):
    name: str = "reactome_api"
    description: str = (
        "Query Reactome REST API for canonical signaling pathway information. "
        "Use 'pathway_for_entity' to find which pathways a protein participates in, "
        "'pathways_for_genes' for pathway overrepresentation across a gene list, "
        "'pathway_hierarchy' for top-level human pathway tree, "
        "'entities_in_pathway' to list all proteins in a specific pathway. "
        "No API key required."
    )
    args_schema: Type[BaseModel] = ReactomeApiInput
    response_format: str = "content_and_artifact"

    def _run(
        self,
        query_type: QueryType = "pathway_for_entity",
        identifier: Optional[str] = None,
        gene_list: Optional[str] = None,
        species: str = "9606",
    ) -> tuple[str, dict]:
        url = ""
        try:
            if query_type == "pathway_for_entity":
                if not identifier:
                    return invalid_input_result(self.name, "'identifier' is required for pathway_for_entity.", metadata={})
                ident = identifier.strip()
                enc = urllib.parse.quote(ident)
                # Use UniProt mapping endpoint for accessions (Pxxxxx), gene lookup otherwise
                if ident.upper().startswith("P") and len(ident) in (6, 7) and ident[1:].isalnum():
                    url = f"{_BASE}/data/mapping/UniProt/{enc}/pathways?speciesId={species}"
                else:
                    url = f"{_BASE}/data/pathways/low/entity/{enc}/allForms?speciesId={species}"
                status_code, data = _get_json(url)

            elif query_type == "pathways_for_genes":
                if not gene_list:
                    return invalid_input_result(self.name, "'gene_list' is required for pathways_for_genes.", metadata={})
                genes = [g.strip() for g in gene_list.split(",") if g.strip()]
                if not genes:
                    return invalid_input_result(self.name, "gene_list is empty after parsing.", metadata={})
                url = f"{_ANALYSIS_BASE}/identifiers/projection?interactors=false&pageSize=20&page=1&sortBy=ENTITIES_PVALUE&order=ASC&resource=TOTAL&pValue=0.05&includeDisease=true"
                payload_str = "\n".join(genes)
                resp = httpx.post(
                    url,
                    content=payload_str,
                    timeout=_TIMEOUT,
                    headers={"Accept": "application/json", "Content-Type": "text/plain"},
                )
                resp.raise_for_status()
                status_code = resp.status_code
                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError):
                    data = resp.text

            elif query_type == "pathway_hierarchy":
                url = f"{_BASE}/data/eventsHierarchy/{species}"
                status_code, data = _get_json(url)

            elif query_type == "entities_in_pathway":
                if not identifier:
                    return invalid_input_result(self.name, "'identifier' (Reactome stable ID) is required for entities_in_pathway.", metadata={})
                enc = urllib.parse.quote(identifier.strip())
                url = f"{_BASE}/data/pathway/{enc}/containedEvents"
                status_code, data = _get_json(url)

            else:
                return invalid_input_result(self.name, f"Unknown query_type: {query_type}", metadata={})

        except httpx.TimeoutException:
            return retriable_error_result(self.name, "Reactome request timed out.", metadata={"url": url, "query_type": query_type})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"url": url, "http_status": code, "query_type": query_type}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            if 400 <= code < 500:
                return invalid_input_result(self.name, msg, metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(self.name, f"Reactome request failed: {exc}", metadata={"url": url})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"url": url})

        meta = {
            "query_type": query_type,
            "identifier": identifier,
            "gene_list": gene_list,
            "species": species,
            "request_url": url,
            "http_status": status_code,
        }

        if isinstance(data, list):
            if not data:
                return empty_result(self.name, "No Reactome results found.", metadata=meta)
            meta["result_count"] = len(data)
            structured = {"results": data}
            summary, _ = json_to_pretty_text(structured, _MAX)
            return success_result(self.name, summary, structured_payload=structured, metadata=meta)
        elif isinstance(data, dict):
            if not data:
                return empty_result(self.name, "Empty Reactome response.", metadata=meta)
            # pathways_for_genes returns an analysis token + pathway list
            if "pathways" in data:
                meta["result_count"] = len(data["pathways"])
            summary, _ = json_to_pretty_text(data, _MAX)
            return success_result(self.name, summary, structured_payload=data, metadata=meta)
        else:
            text = str(data)
            if not text.strip():
                return empty_result(self.name, "Empty Reactome response.", metadata=meta)
            summary, _ = truncate_text(text, _MAX)
            return success_result(self.name, summary, structured_payload={"raw": summary}, metadata=meta)

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
