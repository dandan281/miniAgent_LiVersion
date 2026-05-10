"""
RCSB PDB Search API helper.

The agent has historically tried to hand-craft search.rcsb.org JSON URLs and
consistently picks the wrong attribute path (e.g.
`rcsb_polymer_entity_annotation.annotation_lineage.id` for a gene symbol),
which returns HTTP 400. This tool builds the JSON correctly given a
UniProt accession or a gene + organism.
"""
from dataclasses import dataclass
import json
from typing import Any, Optional, Type

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

_BASE = "https://search.rcsb.org/rcsbsearch/v2/query"
_MAX = 50_000


@dataclass(frozen=True)
class RcsbSearchResponse:
    url: str
    body: dict
    status_code: int
    json_payload: Any | None


def _build_query(
    *,
    uniprot: Optional[str],
    gene: Optional[str],
    organism_taxid: Optional[int],
    return_type: str,
    rows: int,
) -> dict:
    nodes: list[dict] = []
    if uniprot:
        nodes.append({
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": (
                    "rcsb_polymer_entity_container_identifiers."
                    "reference_sequence_identifiers.database_accession"
                ),
                "operator": "in",
                "value": [uniprot],
            },
        })
        nodes.append({
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": (
                    "rcsb_polymer_entity_container_identifiers."
                    "reference_sequence_identifiers.database_name"
                ),
                "operator": "exact_match",
                "value": "UniProt",
            },
        })
    if gene:
        nodes.append({
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
                "operator": "exact_match",
                "value": gene,
            },
        })
    if organism_taxid is not None:
        nodes.append({
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_entity_source_organism.taxonomy_lineage.id",
                "operator": "exact_match",
                "value": str(organism_taxid),
            },
        })
    if not nodes:
        raise ValueError("Provide uniprot, gene, or both.")

    if len(nodes) == 1:
        query_node: dict = nodes[0]
    else:
        query_node = {"type": "group", "logical_operator": "and", "nodes": nodes}

    return {
        "query": query_node,
        "return_type": return_type,
        "request_options": {
            "paginate": {"start": 0, "rows": rows},
            "results_content_type": ["experimental"],
            "sort": [{"sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc"}],
        },
    }


class RcsbSearchInput(BaseModel):
    uniprot: Optional[str] = Field(
        default=None,
        description="UniProt accession (e.g. P04626 for HER2/ERBB2). Most reliable way to find PDB entries for a protein.",
    )
    gene: Optional[str] = Field(
        default=None,
        description="HGNC-style gene symbol (e.g. ERBB2). Use together with organism_taxid for specificity.",
    )
    organism_taxid: Optional[int] = Field(
        default=None,
        description="NCBI taxonomy id (9606 human, 10090 mouse). Optional but reduces ambiguous hits.",
    )
    return_type: str = Field(
        default="polymer_entity",
        description="One of: polymer_entity, entry, assembly, polymer_instance. Default polymer_entity.",
    )
    rows: int = Field(default=10, description="Max results to return (default 10).")


class RcsbSearchTool(BaseTool):
    name: str = "rcsb_search"
    description: str = (
        "Search RCSB PDB for structures by UniProt accession or gene symbol. "
        "Prefer this over hand-crafted fetch_url calls to search.rcsb.org — "
        "the JSON schema there is easy to get wrong (HTTP 400). "
        "Provide `uniprot` (best), or `gene` plus optional `organism_taxid`. "
        "Returns the matching PDB IDs sorted by resolution."
    )
    args_schema: Type[BaseModel] = RcsbSearchInput
    response_format: str = "content_and_artifact"

    def _run(
        self,
        uniprot: Optional[str] = None,
        gene: Optional[str] = None,
        organism_taxid: Optional[int] = None,
        return_type: str = "polymer_entity",
        rows: int = 10,
    ) -> tuple[str, dict]:
        if not uniprot and not gene:
            return invalid_input_result(
                self.name,
                "Provide at least one of `uniprot` or `gene`.",
                metadata={},
            )
        try:
            body = _build_query(
                uniprot=uniprot,
                gene=gene,
                organism_taxid=organism_taxid,
                return_type=return_type,
                rows=rows,
            )
        except ValueError as exc:
            return invalid_input_result(self.name, str(exc), metadata={})

        import httpx

        try:
            response = httpx.post(_BASE, json=body, timeout=25)
            if response.status_code == 204:
                return empty_result(
                    self.name,
                    "RCSB returned no matching structures.",
                    structured_payload={"results": []},
                    metadata={"request_url": _BASE, "request_body": body, "http_status": 204},
                )
            response.raise_for_status()
            parsed = response.json()
            ids = [r.get("identifier") for r in parsed.get("result_set", []) if isinstance(r, dict)]
            summary_obj = {
                "total_count": parsed.get("total_count"),
                "returned": len(ids),
                "identifiers": ids,
            }
            summary, _ = json_to_pretty_text(summary_obj, _MAX)
            return success_result(
                self.name,
                summary,
                structured_payload=parsed,
                metadata={
                    "request_url": _BASE,
                    "request_body": body,
                    "http_status": response.status_code,
                    "result_count": len(ids),
                },
            )
        except httpx.TimeoutException:
            return retriable_error_result(
                self.name,
                "RCSB search timed out.",
                metadata={"request_url": _BASE, "request_body": body},
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            message = f"HTTP {status_code}: {exc.response.reason_phrase}"
            metadata = {"request_url": _BASE, "request_body": body, "http_status": status_code}
            if status_code == 429 or status_code >= 500:
                return retriable_error_result(self.name, message, metadata=metadata)
            return invalid_input_result(self.name, message, metadata=metadata)
        except httpx.RequestError as exc:
            return retriable_error_result(
                self.name,
                f"RCSB request failed: {exc}",
                metadata={"request_url": _BASE, "request_body": body},
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return execution_error_result(
                self.name,
                f"Could not parse RCSB response: {exc}",
                metadata={"request_url": _BASE, "request_body": body},
            )

    async def _arun(
        self,
        uniprot: Optional[str] = None,
        gene: Optional[str] = None,
        organism_taxid: Optional[int] = None,
        return_type: str = "polymer_entity",
        rows: int = 10,
    ) -> tuple[str, dict]:
        return self._run(
            uniprot=uniprot,
            gene=gene,
            organism_taxid=organism_taxid,
            return_type=return_type,
            rows=rows,
        )
