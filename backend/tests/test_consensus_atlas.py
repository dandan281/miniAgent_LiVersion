"""Tests for the v2 consensus muscle aging atlas builder + output schema.

Two layers:
1. Schema/structural tests — verify aging_studies/ folder layout, metadata.json
   keys, and the v2 JSON conforms to the v1 contract so phenotype_checkpoint
   can load it interchangeably.
2. Biology sanity tests — well-known aging signatures (IEGs aged, contractile
   young) must be in the right list, OR explicitly waived if the >=2-source
   threshold isn't met because bulk uploads haven't arrived yet.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AGING_DIR = REPO / "backend" / "knowledge" / "aging_studies"
V1_PATH = REPO / "backend" / "knowledge" / "muscle_atlas_DE.json"
V2_PATH = REPO / "backend" / "knowledge" / "muscle_atlas_DE_v2_consensus.json"

EXPECTED_STUDIES = [
    "GSE164471_tumasian_2021",
    "GSE111016_pillon_2019",
    "gtex_v11_skeletal_muscle",
    "kedlian_lacraz_2024_natage",
    "lai_2024_hlma",
]
REQUIRED_METADATA_KEYS = {"study_id", "citation", "tissue", "modality", "design"}


# ---------------------------------------------------------------------------
# Folder structure + metadata
# ---------------------------------------------------------------------------

def test_aging_studies_dir_exists():
    assert AGING_DIR.is_dir(), f"missing: {AGING_DIR}"


def test_aging_studies_has_readme_and_schema():
    assert (AGING_DIR / "README.md").exists()
    assert (AGING_DIR / "_schema.md").exists()


@pytest.mark.parametrize("study", EXPECTED_STUDIES)
def test_each_study_has_metadata(study):
    meta_path = AGING_DIR / study / "metadata.json"
    assert meta_path.exists(), f"missing {meta_path}"
    with meta_path.open() as f:
        meta = json.load(f)
    missing = REQUIRED_METADATA_KEYS - meta.keys()
    assert not missing, f"{study}/metadata.json missing keys: {missing}"


# ---------------------------------------------------------------------------
# v2 atlas schema (must match v1 contract for phenotype_checkpoint)
# ---------------------------------------------------------------------------

V1_REQUIRED_KEYS = {"P1_up", "P1_down", "P2_up", "P2_down", "FAP_P1_up", "FAP_P2_up"}


def _load_v2() -> dict:
    if not V2_PATH.exists():
        pytest.skip(f"v2 atlas not built yet: {V2_PATH}")
    with V2_PATH.open() as f:
        return json.load(f)


def test_v2_has_all_v1_top_level_keys():
    v2 = _load_v2()
    missing = V1_REQUIRED_KEYS - v2.keys()
    assert not missing, f"v2 missing v1-contract keys: {missing}"


def test_v2_has_per_cell_type_block():
    v2 = _load_v2()
    assert "per_cell_type" in v2
    assert isinstance(v2["per_cell_type"], dict)
    # each entry should have P1_up + P2_up sub-keys
    for ct, block in v2["per_cell_type"].items():
        assert "P1_up" in block, f"{ct} missing P1_up"
        assert "P2_up" in block, f"{ct} missing P2_up"


def test_v2_has_metadata_with_provenance():
    v2 = _load_v2()
    md = v2.get("metadata", {})
    assert "sources_present" in md
    assert "min_sources_for_consensus" in md
    assert md["min_sources_for_consensus"] == 2
    assert isinstance(md["sources_present"], list)
    assert len(md["sources_present"]) >= 2, (
        f"v2 needs >=2 sources for any consensus call; got {md['sources_present']}"
    )


def test_v2_p1_up_genes_have_multi_source_provenance():
    v2 = _load_v2()
    detailed = v2.get("detailed", {}).get("pooled", {})
    for gene in v2["P1_up"]:
        d = detailed.get(gene)
        assert d is not None, f"P1_up gene {gene} missing detailed.pooled entry"
        assert d["n_sources"] >= 2, f"P1_up gene {gene} has n_sources={d['n_sources']} (<2)"
        assert len(d["provenance"]) >= 2


def test_v2_p2_up_genes_have_multi_source_provenance():
    v2 = _load_v2()
    detailed = v2.get("detailed", {}).get("pooled", {})
    for gene in v2["P2_up"]:
        d = detailed.get(gene)
        assert d is not None, f"P2_up gene {gene} missing detailed.pooled entry"
        assert d["n_sources"] >= 2


def test_v2_p1_p2_disjoint():
    """A gene cannot be both aged-up and young-up in the consensus pool."""
    v2 = _load_v2()
    overlap = set(v2["P1_up"]) & set(v2["P2_up"])
    assert not overlap, f"genes in BOTH P1_up and P2_up: {sorted(overlap)[:10]}"


# ---------------------------------------------------------------------------
# Biology sanity (gated on bulk uploads)
# ---------------------------------------------------------------------------

# Canonical aged-enriched (MAPK-driven IEGs + senescence) — should be in P1_up
# once all 5 sources are present. Until bulk uploads arrive, these may not
# meet the >=2 threshold; tests skip in that case.
KNOWN_AGED_UP = ["EGR1", "FOS", "JUN", "MYC", "TXNIP", "GPX3", "NEAT1"]
# Canonical young-enriched (muscle contractile machinery, anabolic)
KNOWN_YOUNG_UP = ["ACTA2", "MYL9", "MYH11", "TPM1", "MYLPF", "ANKRD2", "IGF1", "TRDN"]


def _has_full_source_panel(v2: dict) -> bool:
    expected_min = {"GSE164471", "GSE111016", "GTEx_v11", "kedlian_2024", "lai_2024"}
    present = set(v2["metadata"]["sources_present"])
    return expected_min.issubset(present)


def test_biology_known_aged_up_in_p1():
    v2 = _load_v2()
    if not _has_full_source_panel(v2):
        pytest.skip("waiting on bulk uploads — full 5-source panel not present yet")
    p1 = set(v2["P1_up"])
    missing = [g for g in KNOWN_AGED_UP if g not in p1]
    # Allow up to 2 misses (some genes may be MuSC-specific and not pooled)
    assert len(missing) <= 2, f"too many canonical aged-up genes missing from P1_up: {missing}"


def test_biology_known_young_up_in_p2():
    v2 = _load_v2()
    if not _has_full_source_panel(v2):
        pytest.skip("waiting on bulk uploads — full 5-source panel not present yet")
    p2 = set(v2["P2_up"])
    missing = [g for g in KNOWN_YOUNG_UP if g not in p2]
    assert len(missing) <= 2, f"too many canonical young-up genes missing from P2_up: {missing}"


# ---------------------------------------------------------------------------
# Phenotype-checkpoint compatibility regression
# ---------------------------------------------------------------------------

def test_phenotype_checkpoint_can_load_v2():
    """The v2 JSON must be loadable by score_phenotype with no code changes."""
    if not V2_PATH.exists():
        pytest.skip("v2 atlas not built")
    from backend.utils.phenotype_checkpoint import score_phenotype  # type: ignore

    # H2F-like signature: predicted-up should overlap with young-enriched.
    out = score_phenotype(
        predicted_up=["MYL9", "ACTA2", "TPM1", "MYLPF", "TRDN"],
        predicted_down=["TXNIP", "NEAT1", "GPX3", "SAT1", "PFKFB3"],
        atlas_path=V2_PATH,
    )
    assert "phenotype_score" in out
    assert "verdict" in out
    # H2F-like positive control should not score as ANTI-REJUVENATING on v2
    assert out["verdict"] != "ANTI-REJUVENATING", (
        f"v2 atlas mis-scored a textbook young-up / aged-down signature as "
        f"ANTI-REJUVENATING: {out}"
    )
