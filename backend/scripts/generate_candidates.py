"""
Heuristic novokine candidate generator (task-3 of overnight build).

Builds a combinatorial library of (RTK_A, RTK_B, linker) novokine candidates
from a curated set of 12 muscle-relevant receptor tyrosine kinases and 5
linker variants. For each candidate, predicts a (predicted_up, predicted_down)
gene signature using a class-pair × linker heuristic table, then scores it
against muscle_atlas_DE.json via Stage 4 (utils.phenotype_checkpoint).

OUTPUTS
  - backend/knowledge/candidates_v1.jsonl              (all 330 candidate dicts)
  - backend/knowledge/candidates_v1_top20.json         (top 20, valid rl_loop --input)
  - backend/knowledge/candidates_v1_ranked.tsv         (full ranked TSV)

HONESTY NOTE
  This is a HEURISTIC, NOT a mechanism-aware predictor. The real
  (RTK, RTK, linker) → biased-signaling → transcriptome mapping requires the
  agent's mechanism stage (Stages 3a–3c of the COT_Rejuv_Pipeline skill) and
  ultimately ColabFold/Boltz-2 geometry + uncertainty propagation. This script
  exists to (a) seed the experience buffer with a defensible prior and
  (b) give the RL loop something to rank-order at iteration 0.

Constraints obeyed:
  - No outbound network calls; all heuristics are coded in-script.
  - No modification of any existing file.
  - All gene symbols are UPPERCASE HGNC.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Path bootstrap so we can import backend.utils.phenotype_checkpoint
# -----------------------------------------------------------------------------
HERE = Path(__file__).resolve()
BACKEND = HERE.parent.parent          # backend/
sys.path.insert(0, str(BACKEND))

from utils.phenotype_checkpoint import score_phenotype  # noqa: E402

KNOWLEDGE_DIR = BACKEND / "knowledge"
ATLAS_PATH    = KNOWLEDGE_DIR / "muscle_atlas_DE.json"

OUT_JSONL  = KNOWLEDGE_DIR / "candidates_v1.jsonl"
OUT_TOP20  = KNOWLEDGE_DIR / "candidates_v1_top20.json"
OUT_TSV    = KNOWLEDGE_DIR / "candidates_v1_ranked.tsv"

# Composite reward weights (mirroring rl_loop.stage_compose_reward)
W_TRACK_A = 0.50
W_TRACK_B = 0.30


# -----------------------------------------------------------------------------
# Tier classification (mirrors rl_loop.stage_compose_reward thresholds)
# -----------------------------------------------------------------------------
TIER_TOP_DESIGN          = "TOP_K_DESIGN"
TIER_MIDDLE_HUMAN_REVIEW = "MIDDLE_HUMAN_REVIEW"
TIER_BOTTOM_LOG_ONLY     = "BOTTOM_LOG_ONLY"
TIER_INCOHERENT          = "INCOHERENT_LOG_ONLY"


def classify_tier(track_a: float, track_b: float, verdict: str) -> str:
    if verdict == "ANTI-REJUVENATING" or track_b < 0.10:
        return TIER_INCOHERENT
    if track_a > 0.5 and track_b >= 0.3:
        return TIER_TOP_DESIGN
    if track_a > 0.3:
        return TIER_MIDDLE_HUMAN_REVIEW
    return TIER_BOTTOM_LOG_ONLY


# =============================================================================
# 1. Curated RTK panel (12 muscle-relevant receptor tyrosine kinases)
# =============================================================================
# Each entry: HGNC symbol, structural class, primary biased-output pathways,
# canonical UP-regulated downstream targets after activation in muscle/fibroblast
# context, and a one-sentence rationale + literature citation token.
#
# Targets are HGNC symbols. We bias toward genes that ALSO appear in the
# muscle atlas's P1_up or P2_up lists so Fisher overlap has signal.
RTK_PANEL: list[dict[str, Any]] = [
    {
        "symbol": "ERBB2", "class": "ErbB",
        "bias": ["MAPK", "AKT"],
        "targets_up": ["MYC", "JUN", "FOS", "EGR1", "MYOD1", "MEF2C"],
        "rationale": "Co-receptor in HER family; H2F template (ERBB2+FGFR1) "
                     "drives myogenic reprogramming. PMID:39592735",
    },
    {
        "symbol": "EGFR", "class": "ErbB",
        "bias": ["MAPK", "AKT", "STAT3"],
        "targets_up": ["MYC", "FOS", "JUN", "EGR1", "EGFR"],
        "rationale": "Activates Ras/MAPK in satellite cells; modulates muscle "
                     "regeneration. doi:10.1016/j.stem.2018.04.020",
    },
    {
        "symbol": "FGFR1", "class": "FGFR",
        "bias": ["MAPK", "AKT", "PLCG"],
        "targets_up": ["MYOD1", "MEF2C", "MYOG", "EGR1", "FOS", "MYC"],
        "rationale": "FGF2 signaling expands satellite cells and antagonises "
                     "differentiation; partner in published H2F. PMID:31604163",
    },
    {
        "symbol": "FGFR2", "class": "FGFR",
        "bias": ["MAPK", "AKT", "PLCG"],
        "targets_up": ["MYOD1", "MEF2C", "MYOG", "FOS", "MYC"],
        "rationale": "Closely related to FGFR1; expressed on myoblasts and "
                     "fibro-adipogenic progenitors. doi:10.1242/dev.151035",
    },
    {
        "symbol": "FGFR4", "class": "FGFR",
        "bias": ["MAPK", "PLCG"],
        "targets_up": ["MYOD1", "MYOG", "MEF2C", "MYH7"],
        "rationale": "Predominant FGFR on differentiating myoblasts; required "
                     "for myogenic terminal differentiation. PMID:7926719",
    },
    {
        "symbol": "IGF1R", "class": "INSR",
        "bias": ["AKT", "mTOR", "MAPK"],
        "targets_up": ["MYOG", "MYH7", "MYH2", "ACTA1", "TNNT3", "MEF2C"],
        "rationale": "Master regulator of muscle hypertrophy via AKT/mTOR; "
                     "drives myofibre growth. doi:10.1038/ncb1101-1014",
    },
    {
        "symbol": "INSR", "class": "INSR",
        "bias": ["AKT", "mTOR"],
        "targets_up": ["SLC2A4", "PPARGC1A", "MYH7", "FOXO1"],
        "rationale": "Insulin signaling drives glucose uptake and oxidative "
                     "metabolism in muscle. doi:10.1038/372186a0",
    },
    {
        "symbol": "MET", "class": "MET",
        "bias": ["MAPK", "AKT", "STAT3"],
        "targets_up": ["MYOD1", "MYF5", "MYOG", "FOS", "JUN", "MEF2C"],
        "rationale": "HGF/MET activates quiescent satellite cells; required "
                     "for adult muscle regeneration. PMID:9883724",
    },
    {
        "symbol": "PDGFRA", "class": "PDGFR",
        "bias": ["MAPK", "AKT", "PLCG", "STAT3"],
        "targets_up": ["FOS", "JUN", "EGR1", "MYC", "IL6"],
        "rationale": "Marker of FAPs; sustained signaling drives fibrosis "
                     "and adipogenesis (anti-myogenic). doi:10.1038/ncb2025",
    },
    {
        "symbol": "PDGFRB", "class": "PDGFR",
        "bias": ["MAPK", "AKT", "PLCG"],
        "targets_up": ["FOS", "JUN", "EGR1", "MYC", "ACTA2", "TAGLN"],
        "rationale": "Expressed on muscle pericytes; supports vascular and "
                     "stromal niche. doi:10.1242/dev.067595",
    },
    {
        "symbol": "EPHA4", "class": "EPH",
        "bias": ["RHO", "MAPK"],
        "targets_up": ["FOS", "JUN", "EGR1"],
        "rationale": "Eph–ephrin signaling guides satellite-cell positioning "
                     "in the myofibre niche. doi:10.1038/ncb2860",
    },
    {
        "symbol": "NTRK2", "class": "TRK",
        "bias": ["MAPK", "AKT", "PLCG"],
        "targets_up": ["FOS", "JUN", "MYOG", "MYH7", "NTRK2"],
        "rationale": "BDNF/TrkB supports neuromuscular junction integrity and "
                     "motor unit maintenance. doi:10.1523/JNEUROSCI.5037-09.2010",
    },
    # NOTE: TIE2 dropped to keep the panel at 12 most defensible (less
    # muscle-cell-autonomous; mostly endothelial niche).
]

assert len(RTK_PANEL) == 12, f"expected 12 RTKs, got {len(RTK_PANEL)}"


# =============================================================================
# 2. Linker variants
# =============================================================================
LINKERS: list[dict[str, Any]] = [
    {
        "name": "GS_short",
        "sequence": "GGGGS" * 2,           # 10 aa
        "length_aa": 10,
        "flexibility": "flexible",
        "geometry": "tight",
        "notes": "(GGGGS)x2 — short flexible; forces close apposition",
    },
    {
        "name": "GS_med",
        "sequence": "GGGGS" * 4,           # 20 aa  (H2F-like)
        "length_aa": 20,
        "flexibility": "flexible",
        "geometry": "moderate",
        "notes": "(GGGGS)x4 — H2F template length",
    },
    {
        "name": "GS_long",
        "sequence": "GGGGS" * 8,           # 40 aa
        "length_aa": 40,
        "flexibility": "flexible",
        "geometry": "permissive",
        "notes": "(GGGGS)x8 — long flexible; permissive geometry",
    },
    {
        "name": "EAAAK_x4",
        "sequence": "EAAAK" * 4 + "EA",    # 22 aa rigid α-helix
        "length_aa": 22,
        "flexibility": "rigid",
        "geometry": "fixed_orientation",
        "notes": "(EAAAK)x4 — rigid α-helical spacer; fixes A vs B orientation",
    },
    {
        "name": "XTEN_36",
        "sequence": "SGSETPGTSESATPESGPGTSTEPSEGSAPGSPAG",  # 36 aa unstructured XTEN
        "length_aa": 36,
        "flexibility": "unstructured",
        "geometry": "moderate-permissive",
        "notes": "XTEN-36 — unstructured hydrophilic spacer",
    },
]


# =============================================================================
# 3. Class-pair → biased-output heuristic table
# =============================================================================
# Each (sorted) class-pair maps to:
#   adaptors        : transphosphorylation adaptor set when co-clustered
#   biased_pathways : pathways that DOMINATE the dimer's output
#   excluded        : pathways whose docking sites are sterically/biased OFF
#   output_axis     : "myogenic" | "metabolic" | "stress" | "fibrotic" | "neutral"
#   notes           : 1-sentence biology
#
# Output axes drive the predicted_up / predicted_down vocabulary (defined below).
CLASS_PAIR_BIAS: dict[tuple[str, str], dict[str, Any]] = {
    ("ErbB", "FGFR"): {
        "adaptors": ["GRB2", "SHC1", "FRS2", "GAB1", "PIK3R1"],
        "biased_pathways": ["MAPK", "AKT"],
        "excluded": ["PLCG"],   # H2F: PLCγ Y766 site sterically occluded
        "output_axis": "myogenic",
        "notes": "H2F-template; forced co-clustering biases away from FGFR1 "
                 "PLCγ docking → pure MAPK+AKT → myogenic reprogramming.",
    },
    ("ErbB", "ErbB"): {
        "adaptors": ["GRB2", "SHC1", "GAB1"],
        "biased_pathways": ["MAPK", "AKT"],
        "excluded": [],
        "output_axis": "neutral",   # canonical homo-dimer; no novel bias
        "notes": "Same-family forced dimer ≈ canonical signaling; no novel bias.",
    },
    ("FGFR", "FGFR"): {
        "adaptors": ["FRS2", "GRB2", "PLCG1"],
        "biased_pathways": ["MAPK", "PLCG"],
        "excluded": [],
        "output_axis": "neutral",
        "notes": "Same-family forced dimer ≈ canonical FGFR signaling.",
    },
    ("ErbB", "MET"): {
        "adaptors": ["GRB2", "SHC1", "GAB1", "STAT3"],
        "biased_pathways": ["MAPK", "AKT", "STAT3"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "GAB1 is a strong MET adaptor and ErbB co-recruiter; STAT3 "
                 "supports satellite-cell activation.",
    },
    ("FGFR", "MET"): {
        "adaptors": ["GRB2", "FRS2", "GAB1", "STAT3"],
        "biased_pathways": ["MAPK", "AKT", "STAT3"],
        "excluded": ["PLCG"],
        "output_axis": "myogenic",
        "notes": "MET-driven GAB1/STAT3 + FGFR FRS2 → myogenic; PLCγ partly "
                 "occluded by GAB1 competition.",
    },
    ("INSR", "INSR"): {
        "adaptors": ["IRS1", "IRS2", "SHC1"],
        "biased_pathways": ["AKT", "mTOR"],
        "excluded": [],
        "output_axis": "metabolic",   # IGF1R/INSR family → metabolic, hypertrophy
        "notes": "Insulin/IGF family dimer → AKT/mTOR; muscle hypertrophy axis.",
    },
    ("ErbB", "INSR"): {
        "adaptors": ["GRB2", "SHC1", "IRS1"],
        "biased_pathways": ["MAPK", "AKT", "mTOR"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "MAPK from ErbB + AKT/mTOR from IGF1R/INSR → myogenic + "
                 "hypertrophic.",
    },
    ("FGFR", "INSR"): {
        "adaptors": ["FRS2", "GRB2", "IRS1", "SHC1"],
        "biased_pathways": ["MAPK", "AKT", "mTOR"],
        "excluded": ["PLCG"],
        "output_axis": "myogenic",
        "notes": "FRS2 occupies FGFR docking site; IRS1 routes IGF/INSR side "
                 "to AKT/mTOR; PLCγ excluded.",
    },
    ("INSR", "MET"): {
        "adaptors": ["IRS1", "GAB1", "SHC1"],
        "biased_pathways": ["AKT", "mTOR", "STAT3"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "IGF/INSR + MET — both PI3K-strong; supports satellite-cell "
                 "activation and hypertrophy.",
    },
    ("PDGFR", "PDGFR"): {
        "adaptors": ["GRB2", "SHC1", "PIK3R1", "PLCG1", "STAT3"],
        "biased_pathways": ["MAPK", "PLCG", "STAT3"],
        "excluded": [],
        "output_axis": "fibrotic",
        "notes": "PDGFR homo-dimer = canonical FAP fibrotic/adipogenic signaling.",
    },
    ("ErbB", "PDGFR"): {
        "adaptors": ["GRB2", "SHC1", "PIK3R1"],
        "biased_pathways": ["MAPK", "AKT", "PLCG"],
        "excluded": [],
        "output_axis": "fibrotic",
        "notes": "PDGFR PLCγ/STAT routes likely retained; FAP-tropic.",
    },
    ("FGFR", "PDGFR"): {
        "adaptors": ["FRS2", "GRB2", "PIK3R1", "PLCG1"],
        "biased_pathways": ["MAPK", "PLCG"],
        "excluded": [],
        "output_axis": "fibrotic",
        "notes": "Two PLCγ-competent receptors → strong PLCγ/Ca²⁺ → fibrotic.",
    },
    ("INSR", "PDGFR"): {
        "adaptors": ["IRS1", "GRB2", "PIK3R1"],
        "biased_pathways": ["AKT", "MAPK"],
        "excluded": ["PLCG"],
        "output_axis": "metabolic",
        "notes": "IRS1 dominates docking; PDGFR PLCγ partly displaced; "
                 "metabolic-leaning.",
    },
    ("MET", "PDGFR"): {
        "adaptors": ["GAB1", "GRB2", "STAT3", "PIK3R1"],
        "biased_pathways": ["MAPK", "AKT", "STAT3"],
        "excluded": ["PLCG"],
        "output_axis": "myogenic",
        "notes": "GAB1 swap displaces PDGFR PLCγ Y1021; STAT3 + AKT → "
                 "regenerative.",
    },
    ("MET", "MET"): {
        "adaptors": ["GAB1", "GRB2", "STAT3"],
        "biased_pathways": ["MAPK", "AKT", "STAT3"],
        "excluded": [],
        "output_axis": "neutral",
        "notes": "Canonical MET homodimer; no novel forced-proximity bias.",
    },
    ("EPH", "ErbB"): {
        "adaptors": ["GRB2", "SHC1"],
        "biased_pathways": ["MAPK"],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Eph kinases mostly transduce repulsive/RHO signals; "
                 "ErbB MAPK dominates but coupling weak.",
    },
    ("EPH", "FGFR"): {
        "adaptors": ["GRB2", "FRS2"],
        "biased_pathways": ["MAPK"],
        "excluded": ["PLCG"],
        "output_axis": "stress",
        "notes": "Limited shared adaptors; weak coupling.",
    },
    ("EPH", "INSR"): {
        "adaptors": ["GRB2"],
        "biased_pathways": [],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Almost no shared adaptors; geometry mismatch likely.",
    },
    ("EPH", "MET"): {
        "adaptors": ["GRB2"],
        "biased_pathways": ["MAPK"],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Few shared adaptors; weak forced-proximity output.",
    },
    ("EPH", "PDGFR"): {
        "adaptors": ["GRB2"],
        "biased_pathways": [],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Adaptor mismatch; likely incoherent signaling.",
    },
    ("EPH", "EPH"): {
        "adaptors": ["GRB2"],
        "biased_pathways": [],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Eph homo-dimer = repulsion / RHO; non-rejuvenating.",
    },
    ("EPH", "TRK"): {
        "adaptors": ["GRB2", "SHC1"],
        "biased_pathways": ["MAPK"],
        "excluded": [],
        "output_axis": "stress",
        "notes": "Weak; minor MAPK output.",
    },
    ("TRK", "ErbB"): {
        "adaptors": ["GRB2", "SHC1", "FRS2"],
        "biased_pathways": ["MAPK", "AKT"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "TrkB SHC/FRS2 + ErbB GRB2 → MAPK+AKT; could support NMJ + "
                 "myogenic axis.",
    },
    ("TRK", "FGFR"): {
        "adaptors": ["FRS2", "GRB2", "SHC1"],
        "biased_pathways": ["MAPK", "AKT"],
        "excluded": ["PLCG"],
        "output_axis": "myogenic",
        "notes": "FRS2 shared; PLCγ partially excluded.",
    },
    ("TRK", "INSR"): {
        "adaptors": ["GRB2", "SHC1", "IRS1"],
        "biased_pathways": ["AKT", "mTOR", "MAPK"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "TrkB + IGF1R/INSR — strong AKT/mTOR; hypertrophic.",
    },
    ("TRK", "MET"): {
        "adaptors": ["GRB2", "SHC1", "GAB1", "STAT3"],
        "biased_pathways": ["MAPK", "AKT", "STAT3"],
        "excluded": [],
        "output_axis": "myogenic",
        "notes": "Both have strong PI3K coupling; satellite + NMJ.",
    },
    ("TRK", "PDGFR"): {
        "adaptors": ["GRB2", "SHC1", "PIK3R1", "PLCG1"],
        "biased_pathways": ["MAPK", "PLCG"],
        "excluded": [],
        "output_axis": "fibrotic",
        "notes": "PDGFR adaptor profile dominates; fibrotic-leaning.",
    },
    ("TRK", "TRK"): {
        "adaptors": ["GRB2", "SHC1", "FRS2"],
        "biased_pathways": ["MAPK", "AKT"],
        "excluded": [],
        "output_axis": "neutral",
        "notes": "Canonical TrkB homodimer.",
    },
}


def _classpair_key(class_a: str, class_b: str) -> tuple[str, str]:
    return tuple(sorted([class_a, class_b]))   # type: ignore[return-value]


def get_pair_bias(class_a: str, class_b: str) -> dict[str, Any]:
    key = _classpair_key(class_a, class_b)
    if key in CLASS_PAIR_BIAS:
        return CLASS_PAIR_BIAS[key]
    # Fallback for pairs not explicitly listed: low-confidence neutral
    return {
        "adaptors": ["GRB2"],
        "biased_pathways": [],
        "excluded": [],
        "output_axis": "stress",
        "notes": f"unmapped class-pair {key}; default low-confidence stress.",
    }


# =============================================================================
# 4. Output-axis → gene-vocabulary (genes that exist in the atlas P1_up/P2_up)
# =============================================================================
# Verified against backend/knowledge/muscle_atlas_DE.json (P1_up, P2_up).
# myogenic / metabolic axes → predicted_up draws from P2_up (young-enriched);
# stress / fibrotic axes → predicted_up draws from P1_up (aged-enriched).
# predicted_down is the opposite axis's vocabulary.

# Genes confirmed present in P2_up (young-enriched):
P2_MYOGENIC_CONTRACTILE = [
    "ACTA2", "MYL9", "MYH11", "MYOM2", "TAGLN", "MYL6", "TPM2", "TPM1",
    "ACTN1", "ACTN2", "MYBPC1", "MYL11", "MYH7", "ACTB", "ACTG1", "CNN1",
    "MYLK", "LMOD1", "DES", "VIM", "CSRP1", "MYOM1", "MYOM3", "TNNT3",
    "FHL1", "PDLIM3", "PDLIM5",
]
P2_METABOLIC_MITO = [
    "MT-CO1", "MT-CO2", "MT-CO3", "MT-ATP6", "MT-ND1", "MT-ND2", "MT-ND3",
    "MT-ND4", "MT-ND5", "MT-CYB", "PPARGC1A", "PRKAG2", "PRKAG3", "FABP4",
    "SLC2A4", "PDK4", "FOXO1", "ACACB", "HADHA", "HADHB", "LDHB", "NDUFA1",
    "NDUFA4", "NDUFB4", "NDUFB7", "NDUFB8", "COX5B", "COX6A1", "COX6B1",
    "COX6C", "COX7A2", "COX7B", "COX7C", "COX8A", "ATP5MC3", "ATP5F1E",
    "CKMT2", "LPL", "ACSL1", "DIO2", "TBC1D1", "GHR", "IGFBP7", "IGFBP5",
    "IGFBP6",
]
P2_REGEN_NICHE = [
    "NOTCH3", "NTRK2", "EGFR", "LIFR", "FOXO3", "MEF2A", "SMYD1", "RBM24",
    "RBM20", "ANKRD2", "MCAM", "AXL",
]

# Genes confirmed present in P1_up (aged-enriched):
P1_AGED_STRESS = [
    "EGR1", "FOS", "JUN", "OTUD1", "TXNIP", "IL32", "MYF5", "MYH9",
    "DNAJA4", "ETS2", "DEPP1", "MYF6", "CAV1", "HIPK3", "CSRP3", "ADIRF",
    "C1R", "RRAS2", "HDAC9", "GPAT3", "ATP11B", "GPX3", "UBC", "ST3GAL5",
    "MAP3K7CL", "PPDPFL", "FABP5", "PRUNE2", "ASB5", "NEB", "TTN",
]
P1_FIBROTIC_INFLAM = [
    "C1R", "IL32", "MYH9", "FOS", "JUN", "EGR1", "ETS2", "CAV1", "MYF5",
    "TXNIP", "OTUD1",
]


def signature_for_axis(axis: str) -> tuple[list[str], list[str]]:
    """
    Return (predicted_up, predicted_down) gene lists for an output axis.
    Sizes are kept in [3, 10] per task spec.

    - myogenic  : up = young myogenic+contractile+regen; down = aged stress
    - metabolic : up = young mito+metabolic;             down = aged stress
    - fibrotic  : up = aged fibrotic/inflam;             down = young myogenic
    - stress    : up = aged stress (subset);             down = young myogenic
    - neutral   : a small mixed up/down — modest signal either way
    """
    if axis == "myogenic":
        up = (P2_MYOGENIC_CONTRACTILE[:7] + P2_REGEN_NICHE[:2])[:9]
        down = P1_AGED_STRESS[:8]
    elif axis == "metabolic":
        up = (P2_METABOLIC_MITO[:7] + P2_MYOGENIC_CONTRACTILE[:2])[:9]
        down = P1_AGED_STRESS[:7]
    elif axis == "fibrotic":
        up = P1_FIBROTIC_INFLAM[:8]
        down = P2_MYOGENIC_CONTRACTILE[:7]
    elif axis == "stress":
        up = P1_AGED_STRESS[:6]
        down = P2_MYOGENIC_CONTRACTILE[:5]
    else:  # "neutral"
        up = P2_MYOGENIC_CONTRACTILE[:4]
        down = P1_AGED_STRESS[:4]
    return up, down


# =============================================================================
# 5. Linker modulation
# =============================================================================
# Linker length / flexibility modulates how strongly forced-proximity bias is
# expressed. Short flexible linker → tight coupling → strong bias.
# Long flexible linker → permissive → mostly additive (bias diluted).
# Rigid EAAAK → fixes orientation; if class-pair has clear dominant adaptors
# (e.g. ErbB+FGFR), this can ENHANCE bias; otherwise it's risky.
LINKER_BIAS_MULT: dict[str, float] = {
    "GS_short":  1.10,   # tighter coupling → stronger bias signal
    "GS_med":    1.00,   # H2F template (reference)
    "GS_long":   0.70,   # permissive → bias diluted toward neutral
    "EAAAK_x4":  1.05,   # rigid; bias-amplifying when adaptor set is clear
    "XTEN_36":   0.90,   # moderate-permissive
}

# Linker chain-soundness adjustments (additive Δ to base 0.50)
LINKER_SOUNDNESS_DELTA: dict[str, float] = {
    "GS_short":  -0.05,   # short linker risky for incompatible domains
    "GS_med":    +0.05,   # H2F template — proven geometry
    "GS_long":   +0.05,   # safe permissive default
    "EAAAK_x4":  -0.05,   # rigid — only good when orientation is right
    "XTEN_36":    0.00,
}


# =============================================================================
# 6. Predict signature & soundness for one (RTK_A, RTK_B, linker) candidate
# =============================================================================
def predict_signature(
    rtk_a: dict[str, Any],
    rtk_b: dict[str, Any],
    linker: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, Any], float]:
    """
    Returns (predicted_up, predicted_down, biased_output_dict, chain_soundness).
    """
    bias = get_pair_bias(rtk_a["class"], rtk_b["class"])
    axis = bias["output_axis"]
    base_up, base_down = signature_for_axis(axis)

    mult = LINKER_BIAS_MULT.get(linker["name"], 1.0)
    if mult < 1.0:
        # Bias diluted — drop a few predicted genes to weaken the signal
        keep_up   = max(3, int(len(base_up)   * mult + 0.5))
        keep_down = max(3, int(len(base_down) * mult + 0.5))
        pred_up   = base_up[:keep_up]
        pred_down = base_down[:keep_down]
    elif mult > 1.0:
        # Bias amplified — extend with a few additional axis genes (capped at 10)
        if axis == "myogenic":
            extra_up = P2_REGEN_NICHE[2:4]
        elif axis == "metabolic":
            extra_up = P2_METABOLIC_MITO[7:9]
        elif axis == "fibrotic":
            extra_up = P1_FIBROTIC_INFLAM[8:10]
        elif axis == "stress":
            extra_up = P1_AGED_STRESS[6:8]
        else:
            extra_up = []
        pred_up   = (base_up   + extra_up)[:10]
        pred_down = base_down[:10]
    else:
        pred_up   = base_up
        pred_down = base_down

    # Deduplicate while preserving order
    seen: set[str] = set()
    pred_up   = [g for g in pred_up   if not (g in seen or seen.add(g))]
    seen      = set()
    pred_down = [g for g in pred_down if not (g in seen or seen.add(g))]

    biased_output = {
        "transphosphorylation_adaptors": bias["adaptors"],
        "biased_pathways":               bias["biased_pathways"],
        "excluded_adaptors":             [f"{p}_docking" for p in bias["excluded"]],
        "output_axis":                   axis,
        "linker_modulation":             mult,
        "mechanism_notes":               bias["notes"],
    }

    # ── chain_soundness ──────────────────────────────────────────────────────
    # Base 0.50; bumped by:
    #   • shared/relevant adaptor count (≥2 distinct adaptors → +0.10; ≥4 → +0.20)
    #   • clear biased pathway (non-empty → +0.10)
    #   • biology-axis plausibility (myogenic / metabolic → +0.05; stress → −0.10)
    #   • linker appropriateness (per LINKER_SOUNDNESS_DELTA)
    soundness = 0.50
    n_adaptors = len(set(bias["adaptors"]))
    if n_adaptors >= 4:
        soundness += 0.20
    elif n_adaptors >= 2:
        soundness += 0.10
    if bias["biased_pathways"]:
        soundness += 0.10
    if axis in ("myogenic", "metabolic"):
        soundness += 0.05
    elif axis == "stress":
        soundness -= 0.10

    soundness += LINKER_SOUNDNESS_DELTA.get(linker["name"], 0.0)

    # Same-family forced dimer = no novel bias → cap soundness at 0.55
    if rtk_a["class"] == rtk_b["class"]:
        soundness = min(soundness, 0.55)

    soundness = max(0.10, min(0.95, soundness))
    return pred_up, pred_down, biased_output, round(soundness, 3)


# =============================================================================
# 7. Build candidate dict in the H2F_SEED_CANDIDATE schema
# =============================================================================
def build_candidate(
    rtk_a: dict[str, Any],
    rtk_b: dict[str, Any],
    linker: dict[str, Any],
) -> dict[str, Any]:
    pred_up, pred_down, biased_output, soundness = predict_signature(
        rtk_a, rtk_b, linker
    )
    cid = f"{rtk_a['symbol']}_{rtk_b['symbol']}__{linker['name']}"
    return {
        "candidate_id":   cid,
        "receptor_A":     rtk_a["symbol"],
        "receptor_B":     rtk_b["symbol"],
        "linker":         linker["name"],
        "linker_sequence": linker["sequence"],
        "linker_length_aa": linker["length_aa"],
        "biased_output":  biased_output,
        "predicted_up":   pred_up,
        "predicted_down": pred_down,
        "chain_soundness": soundness,
        "track_c_score":  None,
        "literature_refs": [rtk_a["rationale"], rtk_b["rationale"]],
        "notes": (
            f"Heuristic candidate from generate_candidates.py — "
            f"class pair: ({rtk_a['class']}, {rtk_b['class']}); "
            f"axis: {biased_output['output_axis']}; "
            f"linker: {linker['name']} ({linker['length_aa']} aa, {linker['flexibility']})."
        ),
    }


# =============================================================================
# 8. Composite reward (mirrors rl_loop.stage_compose_reward; track_a + track_b only)
# =============================================================================
def compose_reward(track_a: float, track_b: float) -> float:
    w_sum = W_TRACK_A + W_TRACK_B
    return (W_TRACK_A * track_a + W_TRACK_B * track_b) / w_sum


# =============================================================================
# 9. Main
# =============================================================================
def main() -> int:
    # Sanity-load the atlas (don't print contents)
    if not ATLAS_PATH.exists():
        print(f"[ERROR] atlas not found at {ATLAS_PATH}", file=sys.stderr)
        return 2
    with open(ATLAS_PATH) as f:
        atlas = json.load(f)
    print(f"[atlas] loaded {ATLAS_PATH.name} — "
          f"P1_up={len(atlas.get('P1_up', []))} P2_up={len(atlas.get('P2_up', []))}")

    # Build all (RTK_A, RTK_B) unordered pairs × 5 linkers
    pair_keys = list(itertools.combinations(range(len(RTK_PANEL)), 2))
    print(f"[combo] {len(pair_keys)} unordered RTK pairs × {len(LINKERS)} linkers "
          f"= {len(pair_keys) * len(LINKERS)} candidates")

    candidates: list[dict[str, Any]] = []
    for i, j in pair_keys:
        rtk_a, rtk_b = RTK_PANEL[i], RTK_PANEL[j]
        for linker in LINKERS:
            candidates.append(build_candidate(rtk_a, rtk_b, linker))

    print(f"[build] {len(candidates)} candidate dicts assembled")

    # Score each candidate via Stage 4
    scored: list[dict[str, Any]] = []
    for k, cand in enumerate(candidates):
        ph = score_phenotype(
            predicted_up=cand["predicted_up"],
            predicted_down=cand["predicted_down"],
            cell_type=None,                 # pooled atlas
            atlas_path=ATLAS_PATH,
        )
        track_a = float(ph.get("phenotype_score", 0.0))
        track_b = float(cand["chain_soundness"])
        reward  = compose_reward(track_a, track_b)
        verdict = ph.get("verdict", "NEUTRAL")
        tier    = classify_tier(track_a, track_b, verdict)
        scored.append({
            "candidate":        cand,
            "phenotype":        ph,
            "track_a":          track_a,
            "track_b":          track_b,
            "composite_reward": reward,
            "tier":             tier,
            "verdict":          verdict,
        })
        if (k + 1) % 50 == 0:
            print(f"  scored {k+1}/{len(candidates)}")

    # Sort by composite reward descending
    scored.sort(key=lambda r: r["composite_reward"], reverse=True)

    # ── Write JSONL (all candidate dicts, in ranked order) ───────────────────
    with open(OUT_JSONL, "w") as f:
        for r in scored:
            # Annotate with reward fields so the JSONL is self-contained
            cand_out = dict(r["candidate"])
            cand_out["_phenotype_score"]  = r["track_a"]
            cand_out["_chain_soundness"]  = r["track_b"]
            cand_out["_composite_reward"] = r["composite_reward"]
            cand_out["_tier"]             = r["tier"]
            cand_out["_verdict"]          = r["verdict"]
            f.write(json.dumps(cand_out, default=str) + "\n")
    print(f"[write] {OUT_JSONL}  ({len(scored)} rows)")

    # ── Write top-20 JSON list (rl_loop --input compatible) ──────────────────
    top20 = [r["candidate"] for r in scored[:20]]
    with open(OUT_TOP20, "w") as f:
        json.dump(top20, f, indent=2, default=str)
    print(f"[write] {OUT_TOP20}  (top 20 candidates)")

    # ── Write ranked TSV ─────────────────────────────────────────────────────
    cols = [
        "rank", "candidate_id", "receptor_A", "receptor_B", "linker",
        "biased_pathways", "chain_soundness", "track_a", "track_b",
        "composite_reward", "tier", "verdict", "notes",
    ]
    with open(OUT_TSV, "w") as f:
        f.write("\t".join(cols) + "\n")
        for rank, r in enumerate(scored, start=1):
            cand = r["candidate"]
            biased = ",".join(cand["biased_output"]["biased_pathways"]) or "(none)"
            row = [
                str(rank),
                cand["candidate_id"],
                cand["receptor_A"],
                cand["receptor_B"],
                cand["linker"],
                biased,
                f"{r['track_b']:.3f}",
                f"{r['track_a']:+.4f}",
                f"{r['track_b']:.3f}",
                f"{r['composite_reward']:+.4f}",
                r["tier"],
                r["verdict"],
                cand["notes"].replace("\t", " ").replace("\n", " "),
            ]
            f.write("\t".join(row) + "\n")
    print(f"[write] {OUT_TSV}  (ranked TSV)")

    # ── Console summary: top 5 ────────────────────────────────────────────────
    print("\n=== TOP 5 ===")
    for rank, r in enumerate(scored[:5], start=1):
        cand = r["candidate"]
        print(f"  #{rank}  {cand['candidate_id']}  "
              f"reward={r['composite_reward']:+.4f}  "
              f"track_a={r['track_a']:+.4f}  track_b={r['track_b']:.3f}  "
              f"tier={r['tier']}  verdict={r['verdict']}")

    # H2F-template sanity check (ERBB2+FGFR1 with GS_med should land in top 10)
    h2f_keys = {"ERBB2_FGFR1__GS_med", "FGFR1_ERBB2__GS_med"}
    h2f_ranks = [
        (rank, r) for rank, r in enumerate(scored, start=1)
        if r["candidate"]["candidate_id"] in h2f_keys
    ]
    if h2f_ranks:
        rk, rec = h2f_ranks[0]
        print(f"\n[H2F sanity] {rec['candidate']['candidate_id']} ranked #{rk} "
              f"(reward={rec['composite_reward']:+.4f}, tier={rec['tier']})")
        if rk > 10:
            print("[H2F sanity] WARNING: H2F-template (ERBB2+FGFR1, GS_med) "
                  "did not land in top 10 — heuristic likely under-weights it.")
        else:
            print("[H2F sanity] OK — H2F template in top 10.")
    else:
        print("[H2F sanity] WARNING: H2F-template candidate not found in scored set.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
