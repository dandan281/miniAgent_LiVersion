"""
OmniPath REST API tool: query protein interactions, TF-target edges, and kinase-substrate edges.
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

_BASE = "https://omnipathdb.org"
_TIMEOUT = 30
_MAX = 50_000

QueryType = Literal["interactions", "tf_target", "kinase_substrate", "enz_sub"]


def _fetch_omnipath(url: str) -> tuple[int, Any]:
    resp = httpx.get(url, timeout=_TIMEOUT, headers={"Accept": "application/json"})
    resp.raise_for_status()
    try:
        return resp.status_code, resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.status_code, resp.text


class OmnipathApiInput(BaseModel):
    query_type: QueryType = Field(
        description=(
            "Type of query: "
            "'interactions' — signed directed interactions (source→target); "
            "'tf_target' — transcription factor to target gene edges; "
            "'kinase_substrate' — kinase to substrate phosphorylation edges; "
            "'enz_sub' — all enzyme-substrate post-translational modification edges."
        )
    )
    sources: Optional[str] = Field(
        default=None,
        description="Comma-separated HGNC gene symbols to use as source nodes (e.g. 'EGFR,FGFR1').",
    )
    targets: Optional[str] = Field(
        default=None,
        description="Comma-separated HGNC gene symbols to use as target nodes.",
    )
    datasets: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated OmniPath dataset names to include. "
            "Defaults: interactions→'omnipath,pathwayextra,kinaseextra'; "
            "tf_target→'tf_target'; kinase_substrate/enz_sub→'kinaseextra,enz_sub'."
        ),
    )
    directed: bool = Field(default=True, description="Return only directed edges (interactions only).")
    signed: bool = Field(default=True, description="Return only signed edges (interactions only).")


class OmnipathApiTool(BaseTool):
    name: str = "omnipath_api"
    description: str = (
        "Query OmniPath REST API for protein-protein interactions, TF-target gene edges, "
        "and kinase-substrate edges. Free, no API key required. "
        "Use query_type='interactions' for signaling network edges, "
        "'tf_target' for transcription factor targets, "
        "'kinase_substrate' or 'enz_sub' for phosphorylation sites."
    )
    args_schema: Type[BaseModel] = OmnipathApiInput
    response_format: str = "content_and_artifact"

    def _build_url(
        self,
        query_type: QueryType,
        sources: Optional[str],
        targets: Optional[str],
        datasets: Optional[str],
        directed: bool,
        signed: bool,
    ) -> str:
        params: dict[str, str] = {"format": "json"}

        if query_type == "interactions":
            endpoint = "interactions"
            params["datasets"] = datasets or "omnipath,pathwayextra,kinaseextra"
            if directed:
                params["directed"] = "1"
            if signed:
                params["signed"] = "1"
        elif query_type == "tf_target":
            endpoint = "interactions"
            params["datasets"] = datasets or "tf_target"
        elif query_type == "kinase_substrate":
            endpoint = "interactions"
            params["datasets"] = datasets or "kinaseextra"
        else:  # enz_sub
            endpoint = "enz_sub"
            params["datasets"] = datasets or "kinaseextra,enz_sub"

        if sources:
            params["sources"] = sources
        if targets:
            params["targets"] = targets

        qs = urllib.parse.urlencode(params)
        return f"{_BASE}/{endpoint}?{qs}"

    def _run(
        self,
        query_type: QueryType = "interactions",
        sources: Optional[str] = None,
        targets: Optional[str] = None,
        datasets: Optional[str] = None,
        directed: bool = True,
        signed: bool = True,
    ) -> tuple[str, dict]:
        if not sources and not targets:
            return invalid_input_result(
                self.name,
                "At least one of 'sources' or 'targets' must be provided.",
                metadata={"query_type": query_type},
            )

        url = self._build_url(query_type, sources, targets, datasets, directed, signed)
        try:
            status_code, data = _fetch_omnipath(url)
        except httpx.TimeoutException:
            return retriable_error_result(self.name, "OmniPath request timed out.", metadata={"url": url})
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"HTTP {code}: {exc.response.reason_phrase}"
            meta = {"url": url, "http_status": code}
            if code == 429 or code >= 500:
                return retriable_error_result(self.name, msg, metadata=meta)
            return execution_error_result(self.name, msg, metadata=meta)
        except httpx.RequestError as exc:
            return retriable_error_result(self.name, f"OmniPath request failed: {exc}", metadata={"url": url})
        except Exception as exc:
            return execution_error_result(self.name, str(exc), metadata={"url": url})

        meta = {
            "query_type": query_type,
            "sources": sources,
            "targets": targets,
            "datasets": datasets,
            "directed": directed,
            "signed": signed,
            "request_url": url,
            "http_status": status_code,
        }

        if isinstance(data, list):
            if not data:
                return empty_result(self.name, "No OmniPath interactions found.", metadata=meta)
            meta["result_count"] = len(data)
            structured = {"interactions": data}
            summary, _ = json_to_pretty_text(structured, _MAX)
            return success_result(self.name, summary, structured_payload=structured, metadata=meta)
        elif isinstance(data, str):
            if not data.strip():
                return empty_result(self.name, "Empty response from OmniPath.", metadata=meta)
            summary, _ = truncate_text(data, _MAX)
            return success_result(self.name, summary, structured_payload={"raw": summary}, metadata=meta)
        else:
            summary, _ = json_to_pretty_text(data, _MAX)
            return success_result(self.name, summary, structured_payload=data, metadata=meta)

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
