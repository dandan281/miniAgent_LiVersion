"""
STRING DB REST API tool: protein-protein interaction confidence scores.

Free public endpoint at https://string-db.org/api/ — no API key required.
STRING asks API users to identify themselves via a caller_identity query
parameter; we forward `STRING_CALLER_IDENTITY` from env when set (not a
secret, just a courtesy string like an email).

Used by the novokine pipeline for two things:
  - Combined-confidence scores per receptor pair (feature for the v4.0 model)
  - Novelty score = 1 - combined_score (high novelty = low STRING evidence)
"""
from __future__ import annotations

import os
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

_BASE = "https://string-db.org/api/json"
_TIMEOUT = 30
_MAX = 50_000

QueryType = Literal["network", "partners"]


def _split_identifiers(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in raw.replace("\r", "\n").replace(",", "\n").split("\n"):
        token = chunk.strip()
        if token:
            parts.append(token)
    return parts


def _fetch(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    resp = httpx.get(url, params=params, timeout=_TIMEOUT, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.status_code, resp.json()


class StringApiInput(BaseModel):
    query_type: QueryType = Field(
        default="network",
        description=(
            "'network' — return all pairwise interactions among the given identifiers; "
            "'partners' — return the top interaction partners for each identifier."
        ),
    )
    identifiers: str = Field(
        description=(
            "Gene symbols, Ensembl protein IDs, or STRING IDs. "
            "Separate with newlines, commas, or whitespace (e.g. 'EGFR,IL6ST,TGFBR2')."
        )
    )
    species: int = Field(
        default=9606,
        description="NCBI taxon ID. 9606 = Homo sapiens (default), 10090 = Mus musculus.",
    )
    required_score: int = Field(
        default=0,
        description=(
            "Minimum combined-score threshold expressed in STRING's 0-1000 scale "
            "(e.g. 400 = medium confidence, 700 = high). 0 returns every edge."
        ),
    )
    limit: Optional[int] = Field(
        default=None,
        description=(
            "Maximum number of partners per query protein (only used when "
            "query_type='partners'). Omit for STRING's server-side default."
        ),
    )


class StringApiTool(BaseTool):
    name: str = "string_ppi"
    description: str = (
        "Query STRING DB for protein-protein interaction confidence scores. "
        "Use query_type='network' to score every pair among a list of genes, or "
        "query_type='partners' to fetch top partners of each input gene. "
        "Returns combined score plus subscores (experimental, textmining, coexpression, etc.) "
        "on STRING's 0-1 scale. No API key required."
    )
    args_schema: Type[BaseModel] = StringApiInput
    response_format: str = "content_and_artifact"

    def _build_params(
        self,
        identifiers: list[str],
        species: int,
        required_score: int,
        limit: Optional[int],
    ) -> dict[str, Any]:
        # STRING's expected identifier separator on the wire is a carriage return,
        # but httpx URL-encodes newlines in the parameter value to %0d / %0a — both
        # accepted by the server.
        params: dict[str, Any] = {
            "identifiers": "\r".join(identifiers),
            "species": species,
        }
        if required_score and required_score > 0:
            params["required_score"] = required_score
        if limit is not None and limit > 0:
            params["limit"] = limit
        caller = os.getenv("STRING_CALLER_IDENTITY", "").strip()
        if caller:
            params["caller_identity"] = caller
        return params

    def _normalize_edges(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            a = row.get("preferredName_A") or row.get("stringId_A")
            b = row.get("preferredName_B") or row.get("stringId_B")
            try:
                combined = float(row.get("score", 0.0))
            except (TypeError, ValueError):
                combined = 0.0
            edges.append(
                {
                    "node_a": a,
                    "node_b": b,
                    "string_id_a": row.get("stringId_A"),
                    "string_id_b": row.get("stringId_B"),
                    "taxon_id": row.get("ncbiTaxonId"),
                    "combined_score": combined,
                    "novelty_score": round(max(0.0, 1.0 - combined), 4),
                    "experimental": row.get("escore"),
                    "database": row.get("dscore"),
                    "textmining": row.get("tscore"),
                    "coexpression": row.get("ascore"),
                    "fusion": row.get("fscore"),
                    "neighborhood": row.get("nscore"),
                    "phylogenetic_profile": row.get("pscore"),
                }
            )
        return edges

    def _run(
        self,
        identifiers: str,
        query_type: QueryType = "network",
        species: int = 9606,
        required_score: int = 0,
        limit: Optional[int] = None,
    ) -> tuple[str, dict]:
        idents = _split_identifiers(identifiers)
        if not idents:
            return invalid_input_result(
                self.name,
                "No identifiers provided.",
                metadata={"query_type": query_type},
            )
        if query_type == "network" and len(idents) < 2:
            return invalid_input_result(
                self.name,
                "STRING 'network' query needs at least two identifiers.",
                metadata={"identifiers": idents},
            )

        endpoint = "network" if query_type == "network" else "interaction_partners"
        url = f"{_BASE}/{endpoint}"
        params = self._build_params(idents, species, required_score, limit)
        try:
            status_code, data = _fetch(url, params)
        except httpx.TimeoutException:
            return retriable_error_result(self.name, "STRING request timed out.", metadata={"url": url})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"url": url, "http_status": code, "body": exc.response.text[:400]}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(self.name, f"STRING request failed: {exc}", metadata={"url": url})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"url": url})

        rows = data if isinstance(data, list) else []
        edges = self._normalize_edges(rows)
        meta = {
            "query_type": query_type,
            "identifiers": idents,
            "species": species,
            "required_score": required_score,
            "limit": limit,
            "request_url": url,
            "http_status": status_code,
            "edge_count": len(edges),
        }

        if not edges:
            return empty_result(
                self.name,
                (
                    "STRING returned no interactions for the given identifiers. "
                    "Novelty scores can be treated as 1.0 (maximum) for these pairs."
                ),
                metadata=meta,
            )

        structured = {"edges": edges, "raw": rows}
        summary, _ = json_to_pretty_text(
            {
                "query_type": query_type,
                "edge_count": len(edges),
                "edges_preview": edges[:20],
            },
            _MAX,
        )
        return success_result(
            self.name,
            summary,
            structured_payload=structured,
            metadata=meta,
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
