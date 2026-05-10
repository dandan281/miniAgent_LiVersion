"""
PhosphoSitePlus data tool: phosphorylation sites, kinase-substrate pairs, and regulatory sites.

PhosphoSitePlus does not have a public REST API. This tool queries their bulk data files
(downloaded to local cache) or falls back to NCBI/UniProt cross-references for the same data.
For automated pipeline use, we use the PhosphoSitePlus bulk TSV download (academic, free).

Cache location: backend/storage/phosphosite_cache/
"""
import csv
import io
import os
import urllib.parse
from pathlib import Path
from typing import Literal, Optional, Type

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

_TIMEOUT = 30
_MAX = 50_000

# PhosphoSitePlus bulk data URLs (public download, academic use)
_PSP_KS_URL = "https://www.phosphosite.org/downloads/Kinase_Substrate_Dataset.gz"
_PSP_REG_URL = "https://www.phosphosite.org/downloads/Regulatory_sites.gz"

QueryType = Literal["kinase_substrates", "substrates_of_kinase", "sites_for_protein"]


class PhosphositeInput(BaseModel):
    query_type: QueryType = Field(
        description=(
            "Type of query: "
            "'kinase_substrates' — find all substrates of a given kinase gene symbol; "
            "'substrates_of_kinase' — alias for kinase_substrates; "
            "'sites_for_protein' — find all phosphorylation sites and their modifying kinases for a protein."
        )
    )
    gene_symbol: str = Field(
        description="HGNC gene symbol of the kinase (for kinase_substrates) or substrate protein (for sites_for_protein).",
    )
    organism: str = Field(
        default="human",
        description="Organism filter: 'human', 'mouse', or 'rat' (default: 'human').",
    )
    cache_dir: Optional[str] = Field(
        default=None,
        description="Path to directory containing pre-downloaded PhosphoSitePlus TSV files. If not provided, uses backend/storage/phosphosite_cache/.",
    )


class PhosphositeTool(BaseTool):
    name: str = "phosphosite_plus"
    description: str = (
        "Query PhosphoSitePlus data for kinase-substrate relationships and phosphorylation sites. "
        "Use 'kinase_substrates' to find what a kinase phosphorylates (e.g. EGFR substrates), "
        "'sites_for_protein' to find all known phosphorylation sites on a protein and their kinases. "
        "Uses locally cached bulk data files (academic free). "
        "IMPORTANT: requires pre-downloaded PhosphoSitePlus data files in storage/phosphosite_cache/. "
        "If cache is missing, returns instructions for downloading."
    )
    args_schema: Type[BaseModel] = PhosphositeInput
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    def _resolve_cache_dir(self, cache_dir: Optional[str]) -> Path:
        if cache_dir:
            return Path(cache_dir)
        if self.base_dir:
            return Path(self.base_dir) / "storage" / "phosphosite_cache"
        return Path("storage/phosphosite_cache")

    def _run(
        self,
        query_type: QueryType = "kinase_substrates",
        gene_symbol: str = "",
        organism: str = "human",
        cache_dir: Optional[str] = None,
    ) -> tuple[str, dict]:
        if not gene_symbol.strip():
            return invalid_input_result(self.name, "'gene_symbol' is required.", metadata={})

        gene = gene_symbol.strip().upper()
        org = organism.lower()
        resolved_cache = self._resolve_cache_dir(cache_dir)

        ks_file = resolved_cache / "Kinase_Substrate_Dataset"
        if not ks_file.exists():
            # Try .gz or .tsv variants
            for suffix in [".tsv", ".txt", ""]:
                candidate = resolved_cache / f"Kinase_Substrate_Dataset{suffix}"
                if candidate.exists():
                    ks_file = candidate
                    break
            else:
                return invalid_input_result(
                    self.name,
                    (
                        f"PhosphoSitePlus cache not found at {resolved_cache}. "
                        "Download the free academic dataset:\n"
                        "1. Go to https://www.phosphosite.org/staticDownloads\n"
                        "2. Download 'Kinase_Substrate_Dataset' (requires free registration)\n"
                        f"3. Extract and place in {resolved_cache}/\n"
                        "Alternative: use omnipath_api with query_type='kinase_substrate' for predicted kinase-substrate edges."
                    ),
                    metadata={"cache_dir": str(resolved_cache), "gene": gene},
                )

        try:
            results = []
            with open(ks_file, "r", encoding="utf-8", errors="replace") as f:
                raw_lines = f.readlines()
            # PhosphoSitePlus bulk files start with 3 preamble lines (date, license
            # blurb, blank) before the tab-separated header beginning with "GENE\t".
            # Skip everything before that header so csv.DictReader picks up the
            # real column names instead of the date stamp.
            header_idx = next(
                (i for i, l in enumerate(raw_lines)
                 if l.startswith("GENE\t") and "KINASE" in l),
                0,
            )
            data_lines = [l for l in raw_lines[header_idx:] if not l.startswith("#")]
            reader = csv.DictReader(io.StringIO("".join(data_lines)), delimiter="\t")

            for row in reader:
                row_org = (row.get("KIN_ORGANISM") or row.get("SUB_ORGANISM") or "").lower()
                if org not in row_org and org != "all":
                    continue

                in_vivo = (row.get("IN_VIVO_RXN", "") or "").strip().upper() == "X"
                in_vitro = (row.get("IN_VITRO_RXN", "") or "").strip().upper() == "X"

                if query_type in ("kinase_substrates", "substrates_of_kinase"):
                    kin_gene = (row.get("KINASE") or row.get("KIN_ACC_ID") or "").upper()
                    if kin_gene == gene:
                        results.append({
                            "kinase": row.get("KINASE", ""),
                            "substrate": row.get("SUBSTRATE", ""),
                            "substrate_gene": row.get("SUB_GENE", ""),
                            "residue": row.get("SUB_MOD_RSD", ""),
                            "organism": row.get("SUB_ORGANISM", ""),
                            "in_vivo": in_vivo,
                            "in_vitro": in_vitro,
                            "cst_catalog": row.get("CST_Catalog#", ""),
                            "references": row.get("SITE_GRP_ID", ""),
                        })
                elif query_type == "sites_for_protein":
                    sub_gene = (row.get("SUB_GENE") or row.get("SUBSTRATE") or "").upper()
                    if sub_gene == gene:
                        results.append({
                            "kinase": row.get("KINASE", ""),
                            "substrate_gene": row.get("SUB_GENE", ""),
                            "residue": row.get("SUB_MOD_RSD", ""),
                            "organism": row.get("SUB_ORGANISM", ""),
                            "in_vivo": in_vivo,
                            "in_vitro": in_vitro,
                            "site_group_id": row.get("SITE_GRP_ID", ""),
                        })

            # Sort by confidence: in_vivo+in_vitro first (gold standard),
            # then in_vivo only, then in_vitro only, then neither.
            def _confidence_key(r: dict) -> int:
                if r.get("in_vivo") and r.get("in_vitro"):
                    return 0
                if r.get("in_vivo"):
                    return 1
                if r.get("in_vitro"):
                    return 2
                return 3

            results.sort(key=_confidence_key)

        except Exception as exc:
            return execution_error_result(
                self.name,
                f"Failed to read PhosphoSitePlus cache: {exc}",
                metadata={"cache_dir": str(resolved_cache), "gene": gene},
            )

        meta = {
            "query_type": query_type,
            "gene_symbol": gene,
            "organism": org,
            "cache_file": str(ks_file),
            "result_count": len(results),
        }

        if not results:
            return empty_result(
                self.name,
                f"No PhosphoSitePlus entries found for {gene} ({org}).",
                metadata=meta,
            )

        structured = {"results": results[:200]}  # cap at 200 rows for context
        summary, _ = json_to_pretty_text(structured, _MAX)
        return success_result(self.name, summary, structured_payload=structured, metadata=meta)

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
