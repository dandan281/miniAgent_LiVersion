"""
Local LINCS L1000 connectivity scorer.

Replaces the (now paywalled) clue.io batch query API with a fully offline,
gene-set-based connectivity scorer using publicly available Enrichr LINCS
gene set libraries.

Data sources (downloaded once into ``backend/storage/lincs_cache/``):
  - LINCS_L1000_Chem_Pert_up.gmt           ~33K chemical perturbation up-sigs
  - LINCS_L1000_Chem_Pert_down.gmt         ~33K chemical perturbation down-sigs
  - LINCS_L1000_Ligand_Perturbations_up.gmt    ligand perturbation up-sigs
  - LINCS_L1000_Ligand_Perturbations_down.gmt  ligand perturbation down-sigs
  - LINCS_L1000_CRISPR_KO_Consensus_Sigs.gmt   genetic perturbation sigs

Scoring algorithm — bidirectional overlap (CMap-aligned, simplified):
  For each perturbagen signature with paired (up, down) gene sets:
    mimic    = jaccard(query_up, pert_up)   + jaccard(query_down, pert_down)
    reverser = jaccard(query_up, pert_down) + jaccard(query_down, pert_up)
    tau_like = (mimic - reverser) * 50       # rescaled to roughly [-100, +100]

A positive tau_like means the perturbagen REPRODUCES the query signature
(mimic), a negative tau_like means it REVERSES it. This is the same
semantic the clue.io tau score uses, so downstream Track C reward logic
needs no change.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


_CACHE_DIR_DEFAULT = "backend/storage/lincs_cache"

# Enrichr signature ID format examples:
#   "CPC001 HA1E 24H-hemado-10.0"
#   "CPC006 PC3 24H-BRD-K12345678-10.0"
# We split into components for downstream display + filtering.
_SIG_ID_RE = re.compile(
    r"^(?P<plate>\S+)\s+(?P<cell>\S+)\s+(?P<time>\S+?)-(?P<pert>.+?)(?:-(?P<dose>[0-9.]+))?$"
)


def _parse_gmt(path: Path) -> dict[str, set[str]]:
    """Parse an Enrichr GMT into ``{sig_id: {gene, ...}}``."""
    sigs: dict[str, set[str]] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            sig_id = parts[0].strip()
            # parts[1] is the description column (usually empty in Enrichr GMT)
            genes = {g.strip().upper() for g in parts[2:] if g and g.strip()}
            if sig_id and genes:
                sigs[sig_id] = genes
    return sigs


def _signature_label(sig_id: str) -> dict[str, str]:
    """Best-effort decomposition of an Enrichr signature ID."""
    m = _SIG_ID_RE.match(sig_id)
    if not m:
        return {"raw": sig_id, "pert": sig_id, "cell": "", "time": "", "dose": ""}
    g = m.groupdict()
    return {
        "raw": sig_id,
        "plate": g.get("plate") or "",
        "cell": g.get("cell") or "",
        "time": g.get("time") or "",
        "pert": g.get("pert") or "",
        "dose": g.get("dose") or "",
    }


class LincsLocalIndex:
    """In-memory LINCS index: paired up/down sets per perturbagen signature."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.chem_up: dict[str, set[str]] = {}
        self.chem_down: dict[str, set[str]] = {}
        self.ligand_up: dict[str, set[str]] = {}
        self.ligand_down: dict[str, set[str]] = {}
        self.crispr_consensus: dict[str, set[str]] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        chem_up_path = self.cache_dir / "LINCS_L1000_Chem_Pert_up.gmt"
        chem_dn_path = self.cache_dir / "LINCS_L1000_Chem_Pert_down.gmt"
        lig_up_path = self.cache_dir / "LINCS_L1000_Ligand_Perturbations_up.gmt"
        lig_dn_path = self.cache_dir / "LINCS_L1000_Ligand_Perturbations_down.gmt"
        crispr_path = self.cache_dir / "LINCS_L1000_CRISPR_KO_Consensus_Sigs.gmt"

        if chem_up_path.exists():
            self.chem_up = _parse_gmt(chem_up_path)
        if chem_dn_path.exists():
            self.chem_down = _parse_gmt(chem_dn_path)
        if lig_up_path.exists():
            self.ligand_up = _parse_gmt(lig_up_path)
        if lig_dn_path.exists():
            self.ligand_down = _parse_gmt(lig_dn_path)
        if crispr_path.exists():
            self.crispr_consensus = _parse_gmt(crispr_path)
        self._loaded = True

    def is_available(self) -> bool:
        return (
            (self.cache_dir / "LINCS_L1000_Chem_Pert_up.gmt").exists()
            and (self.cache_dir / "LINCS_L1000_Chem_Pert_down.gmt").exists()
        )

    def stats(self) -> dict[str, int]:
        return {
            "chem_pert_signatures": len(self.chem_up),
            "ligand_signatures": len(self.ligand_up),
            "crispr_consensus_signatures": len(self.crispr_consensus),
        }


@lru_cache(maxsize=1)
def _global_index(cache_dir_str: str) -> LincsLocalIndex:
    idx = LincsLocalIndex(Path(cache_dir_str))
    idx.load()
    return idx


def get_index(cache_dir: Optional[Path | str] = None) -> LincsLocalIndex:
    """Return a process-global lazy-loaded LINCS index."""
    cache = Path(cache_dir) if cache_dir else Path(_CACHE_DIR_DEFAULT)
    return _global_index(str(cache.resolve()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _score_signature(
    query_up: set[str],
    query_down: set[str],
    pert_up: set[str],
    pert_down: set[str],
) -> tuple[float, dict[str, float]]:
    """Return ``(tau_like, breakdown)`` for one perturbagen signature."""
    j_up_up = _jaccard(query_up, pert_up)
    j_dn_dn = _jaccard(query_down, pert_down)
    j_up_dn = _jaccard(query_up, pert_down)
    j_dn_up = _jaccard(query_down, pert_up)
    mimic = j_up_up + j_dn_dn
    reverser = j_up_dn + j_dn_up
    # Scale so that perfect mimic (j=1, j=1) → +100, perfect reverser → -100
    tau_like = (mimic - reverser) * 50.0
    return tau_like, {
        "j_up_up": round(j_up_up, 4),
        "j_dn_dn": round(j_dn_dn, 4),
        "j_up_dn": round(j_up_dn, 4),
        "j_dn_up": round(j_dn_up, 4),
        "mimic_score": round(mimic, 4),
        "reverser_score": round(reverser, 4),
    }


def query_local(
    *,
    up_genes: list[str],
    down_genes: list[str],
    max_results: int = 25,
    cache_dir: Optional[Path | str] = None,
    include_ligands: bool = True,
) -> dict[str, Any]:
    """Run a connectivity query against the local LINCS index.

    Returns
    -------
    dict
        ``signatures`` — top-N mimic perturbagens (highest tau_like)
        ``bottom_signatures`` — top-N reverser perturbagens (lowest tau_like)
        ``n_signatures_total`` — number of paired perturbagen signatures scored
        ``stats`` — index size for transparency
    """
    idx = get_index(cache_dir)
    if not idx.is_available():
        raise FileNotFoundError(
            f"LINCS gene-set libraries not found in {idx.cache_dir}. "
            "Run the download step first."
        )

    q_up = {g.strip().upper() for g in up_genes if g and g.strip()}
    q_dn = {g.strip().upper() for g in down_genes if g and g.strip()}

    scored: list[dict[str, Any]] = []

    # Chemical perturbations (paired up/down)
    chem_ids = set(idx.chem_up.keys()) & set(idx.chem_down.keys())
    for sig_id in chem_ids:
        tau, breakdown = _score_signature(
            q_up, q_dn, idx.chem_up[sig_id], idx.chem_down[sig_id]
        )
        if abs(tau) < 0.01:
            continue  # skip pure-zero hits to keep the result list focused
        label = _signature_label(sig_id)
        scored.append({
            "sig_id": sig_id,
            "pert_iname": label.get("pert", sig_id),
            "cell_line": label.get("cell", ""),
            "time": label.get("time", ""),
            "dose": label.get("dose", ""),
            "perturbation_class": "chem",
            "tau": round(tau, 3),
            **breakdown,
        })

    # Ligand perturbations (paired up/down)
    if include_ligands:
        lig_ids = set(idx.ligand_up.keys()) & set(idx.ligand_down.keys())
        for sig_id in lig_ids:
            tau, breakdown = _score_signature(
                q_up, q_dn, idx.ligand_up[sig_id], idx.ligand_down[sig_id]
            )
            if abs(tau) < 0.01:
                continue
            label = _signature_label(sig_id)
            scored.append({
                "sig_id": sig_id,
                "pert_iname": label.get("pert", sig_id),
                "cell_line": label.get("cell", ""),
                "time": label.get("time", ""),
                "dose": label.get("dose", ""),
                "perturbation_class": "ligand",
                "tau": round(tau, 3),
                **breakdown,
            })

    scored.sort(key=lambda r: r["tau"], reverse=True)
    top = scored[: max(1, int(max_results))]
    bottom = scored[-max(1, int(max_results)) :][::-1]  # most-negative first

    return {
        "signatures": top,
        "bottom_signatures": bottom,
        "n_signatures_total": len(scored),
        "n_signatures_with_tau": len(scored),
        "tau_range": [-100.0, 100.0],
        "stats": idx.stats(),
        "scoring_algorithm": "bidirectional_jaccard_overlap",
    }


# Convenience entrypoint for ad-hoc testing
if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser(description="Test the local LINCS connectivity scorer.")
    p.add_argument("--up", nargs="+", required=True, help="Up-regulated gene symbols")
    p.add_argument("--down", nargs="+", required=True, help="Down-regulated gene symbols")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--cache", default=_CACHE_DIR_DEFAULT)
    args = p.parse_args()

    result = query_local(
        up_genes=args.up,
        down_genes=args.down,
        max_results=args.top,
        cache_dir=args.cache,
    )
    print(json.dumps(result, indent=2))
