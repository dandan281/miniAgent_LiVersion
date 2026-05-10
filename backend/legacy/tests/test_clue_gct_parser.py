"""Tests for the CLUE / L1000 GCT parser added to clue_api_tool.py.

Covers: GCT v1.x format parsing, summary-column auto-detection, end-to-end
tarball extraction. No network calls — all tarballs are built in-memory.
"""
from __future__ import annotations

import io
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.clue_api_tool import (  # noqa: E402
    _gct_summary_column_index,
    _parse_clue_result_tarball,
    _parse_gct,
)


# ─────────────────────────────────────────────────────────────────────────
# Synthetic GCT helpers
# ─────────────────────────────────────────────────────────────────────────
_FOUR_PERTURBAGEN_GCT = "\n".join([
    "#1.3",
    "4\t3\t4\t1",
    "id\tpert_id\tpert_iname\tmoa\ttarget\tcol_001\tcol_002\tsummary",
    "cell_iname\t\t\t\t\tA549\tMCF7\tsummary",
    "row_1\tBRD-K001\trapamycin\tMTOR inhibitor\tMTOR\t98.2\t95.4\t96.5",
    "row_2\tBRD-K002\tmetformin\tAMPK activator\tPRKAA1\t87.0\t82.1\t84.3",
    "row_3\tBRD-K003\tdoxorubicin\tTopo II inhibitor\tTOP2A\t-91.5\t-88.2\t-89.8",
    "row_4\tBRD-K004\tquercetin\tSenolytic flavonoid\tBCL2L1\t12.3\t8.5\t10.1",
])


def _make_tarball(*, gct_text: str, member_path: str = "results/query_result.gct") -> Path:
    """Write a tar.gz containing one .gct member at the given path."""
    tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    with tarfile.open(fileobj=tmpf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member_path)
        data_bytes = gct_text.encode("utf-8")
        info.size = len(data_bytes)
        tar.addfile(info, io.BytesIO(data_bytes))
    tmpf.close()
    return Path(tmpf.name)


# ─────────────────────────────────────────────────────────────────────────
# _parse_gct
# ─────────────────────────────────────────────────────────────────────────
def test_parse_gct_basic_dimensions():
    parsed = _parse_gct(_FOUR_PERTURBAGEN_GCT)
    assert parsed["version"].startswith("1.")
    assert parsed["n_rows"] == 4
    assert parsed["n_cols"] == 3
    assert parsed["n_row_metadata"] == 4
    assert parsed["n_col_metadata"] == 1


def test_parse_gct_row_metadata_extracted():
    parsed = _parse_gct(_FOUR_PERTURBAGEN_GCT)
    rows = parsed["rows"]
    assert len(rows) == 4
    rapa = next(r for r in rows if r["row_metadata"]["pert_iname"] == "rapamycin")
    assert rapa["row_metadata"]["pert_id"] == "BRD-K001"
    assert rapa["row_metadata"]["target"] == "MTOR"
    assert rapa["data"] == [98.2, 95.4, 96.5]


def test_parse_gct_column_metadata_extracted():
    parsed = _parse_gct(_FOUR_PERTURBAGEN_GCT)
    assert parsed["column_metadata"][0]["cell_iname"] == "A549"
    assert parsed["column_metadata"][2]["cell_iname"] == "summary"


def test_parse_gct_rejects_non_gct_input():
    with pytest.raises(ValueError, match="GCT"):
        _parse_gct("not a gct file at all")


def test_parse_gct_handles_empty_floats_as_none():
    gct = "\n".join([
        "#1.3",
        "1\t2\t1\t0",
        "id\tpert_iname\tcol_001\tcol_002",
        "row_1\trapamycin\t98.2\tNA",
    ])
    parsed = _parse_gct(gct)
    assert parsed["rows"][0]["data"][0] == 98.2
    assert parsed["rows"][0]["data"][1] is None


# ─────────────────────────────────────────────────────────────────────────
# _gct_summary_column_index
# ─────────────────────────────────────────────────────────────────────────
def test_summary_column_detected_by_id():
    parsed = _parse_gct(_FOUR_PERTURBAGEN_GCT)
    idx = _gct_summary_column_index(parsed)
    assert parsed["column_ids"][idx] == "summary"


def test_summary_column_falls_back_to_zero_when_no_summary():
    gct = "\n".join([
        "#1.3", "1\t2\t1\t0",
        "id\tpert_iname\tcol_A\tcol_B",
        "row_1\trapamycin\t10.0\t20.0",
    ])
    parsed = _parse_gct(gct)
    idx = _gct_summary_column_index(parsed)
    assert idx == 0


def test_summary_column_detected_via_metadata():
    """When the column id isn't 'summary' but cell_iname metadata says so."""
    gct = "\n".join([
        "#1.3", "1\t2\t1\t1",
        "id\tpert_iname\tcol_X\tcol_Y",
        "cell_iname\t\tA549\tsummary",
        "row_1\trapamycin\t10.0\t20.0",
    ])
    parsed = _parse_gct(gct)
    idx = _gct_summary_column_index(parsed)
    assert idx == 1   # found via cell_iname=summary


# ─────────────────────────────────────────────────────────────────────────
# _parse_clue_result_tarball
# ─────────────────────────────────────────────────────────────────────────
def test_parse_tarball_returns_top_n_by_tau():
    tarball = _make_tarball(gct_text=_FOUR_PERTURBAGEN_GCT)
    try:
        result = _parse_clue_result_tarball(str(tarball), top_n=3, bottom_n=2)
    finally:
        tarball.unlink()
    assert result["n_signatures_total"] == 4
    assert result["n_signatures_with_tau"] == 4
    top_names = [s["pert_iname"] for s in result["top_signatures"]]
    assert top_names[0] == "rapamycin"  # tau 96.5
    assert top_names[1] == "metformin"   # tau 84.3


def test_parse_tarball_returns_bottom_n_by_tau():
    tarball = _make_tarball(gct_text=_FOUR_PERTURBAGEN_GCT)
    try:
        result = _parse_clue_result_tarball(str(tarball), top_n=2, bottom_n=2)
    finally:
        tarball.unlink()
    bottom_names = [s["pert_iname"] for s in result["bottom_signatures"]]
    assert bottom_names[0] == "doxorubicin"  # tau -89.8


def test_parse_tarball_finds_nested_gct():
    """The .gct can be at any path inside the tarball."""
    tarball = _make_tarball(
        gct_text=_FOUR_PERTURBAGEN_GCT,
        member_path="some/deep/nested/path/query_result.gct",
    )
    try:
        result = _parse_clue_result_tarball(str(tarball))
    finally:
        tarball.unlink()
    assert result["n_signatures_total"] == 4


def test_parse_tarball_raises_when_no_gct_inside(tmp_path):
    """Tarball with only README → meaningful error."""
    p = tmp_path / "no_gct.tar.gz"
    with tarfile.open(p, "w:gz") as tar:
        info = tarfile.TarInfo(name="README.txt")
        data = b"not a gct"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(RuntimeError, match="No .gct file"):
        _parse_clue_result_tarball(str(p))
