"""
LangChain wrapper around utils.phenotype_checkpoint.

This is the Track A (50% of reward) scoring tool: takes a candidate novokine's
predicted gene signature {up, down} and returns a phenotype_score in [-1, +1]
plus full Fisher exact + Jaccard breakdown vs the muscle aging atlas.

The agent calls this once per candidate after it has predicted a transcriptome
shift via the COT_Rejuv_Pipeline reasoning (Steps 3a–3c).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .contracts import (
    execution_error_result,
    invalid_input_result,
    success_result,
)


class PhenotypeCheckpointInput(BaseModel):
    predicted_up: list[str] = Field(
        default_factory=list,
        description="HGNC symbols predicted to be UPregulated by the candidate novokine.",
    )
    predicted_down: list[str] = Field(
        default_factory=list,
        description="HGNC symbols predicted to be DOWNregulated by the candidate novokine.",
    )
    cell_type: Optional[str] = Field(
        default=None,
        description=(
            "Atlas slice to score against. Options: "
            "None or 'pooled' (default) — top-level P1_up / P2_up; "
            "'MuSC' / 'Myofiber' / 'Myofiber_TypeI' / 'Myofiber_TypeII' — per-cell-type slices; "
            "'FAP' — fibroblast-lineage. Pooled is recommended unless the candidate's "
            "predicted output is specifically about one cell type."
        ),
    )
    universe_size: int = Field(
        default=20_000,
        description="Background gene universe size for Fisher exact (default 20,000 ≈ human protein-coding genome).",
    )
    atlas_version: Optional[Literal["v1", "v2"]] = Field(
        default=None,
        description=(
            "Which atlas to score against. "
            "'v1' (default) = single-source pooled atlas (Lai 2024 + fibroblast CSVs). "
            "'v2' = multi-source consensus atlas (>=2 of: GSE164471, GSE111016, GTEx v11, Kedlian 2024, Lai 2024). "
            "Default keeps v1 for reproducibility of the 79-run experience buffer; "
            "set to 'v2' to score against the multi-source consensus."
        ),
    )


class PhenotypeCheckpointTool(BaseTool):
    name: str = "phenotype_checkpoint"
    description: str = (
        "TRACK A reward signal (50% weight) for muscle rejuvenation novokine candidates. "
        "Compares a candidate's predicted gene signature {up, down} against the muscle aging "
        "atlas (muscle_atlas_DE.json) using Fisher exact tests and Jaccard overlap. "
        "Rewards: predicted UP genes overlapping P2_up (young-enriched), predicted DOWN genes "
        "overlapping P1_up (aged-enriched). Penalizes the inverse. "
        "Returns phenotype_score in [-1, +1] (positive = rejuvenating) plus full statistical "
        "breakdown. Use after the COT_Rejuv_Pipeline has predicted the transcriptome shift."
    )
    args_schema: Type[BaseModel] = PhenotypeCheckpointInput
    response_format: str = "content_and_artifact"

    base_dir: str = ""

    def _atlas_path(self, atlas_version: Optional[str] = None) -> Path:
        base = Path(self.base_dir) if self.base_dir else Path(".")
        if atlas_version == "v2":
            return base / "knowledge" / "muscle_atlas_DE_v2_consensus.json"
        return base / "knowledge" / "muscle_atlas_DE.json"

    def _run(
        self,
        predicted_up: Optional[list[str]] = None,
        predicted_down: Optional[list[str]] = None,
        cell_type: Optional[str] = None,
        universe_size: int = 20_000,
        atlas_version: Optional[str] = None,
    ) -> tuple[str, dict]:
        try:
            from utils.phenotype_checkpoint import score_phenotype, format_score_summary
        except ImportError as e:
            return execution_error_result(
                self.name,
                f"phenotype_checkpoint utility not importable: {e}",
                metadata={},
            )

        if not (predicted_up or predicted_down):
            return invalid_input_result(
                self.name,
                "At least one of 'predicted_up' or 'predicted_down' must be a non-empty gene list.",
                metadata={},
            )

        atlas_path = self._atlas_path(atlas_version)
        if not atlas_path.exists():
            return invalid_input_result(
                self.name,
                (
                    f"Atlas not found at {atlas_path}. "
                    + (
                        "Run `python backend/scripts/build_consensus_atlas.py` to build v2."
                        if atlas_version == "v2"
                        else ""
                    )
                ),
                metadata={"atlas_path": str(atlas_path), "atlas_version": atlas_version},
            )

        try:
            result = score_phenotype(
                predicted_up=predicted_up or [],
                predicted_down=predicted_down or [],
                cell_type=cell_type,
                atlas_path=atlas_path,
                universe_size=universe_size,
            )
        except ValueError as e:
            return invalid_input_result(self.name, str(e), metadata={"cell_type": cell_type})
        except Exception as e:
            return execution_error_result(self.name, str(e), metadata={})

        summary = format_score_summary(result)
        return success_result(
            self.name, summary,
            structured_payload=result,
            metadata={
                "phenotype_score": result.get("phenotype_score"),
                "verdict":         result.get("verdict"),
                "reference_label": result.get("reference_label"),
                "atlas_version":   atlas_version or "v1",
                "n_predicted_up":  result.get("n_predicted_up"),
                "n_predicted_down": result.get("n_predicted_down"),
            },
        )

    async def _arun(self, **kwargs) -> tuple[str, dict]:
        return self._run(**kwargs)
