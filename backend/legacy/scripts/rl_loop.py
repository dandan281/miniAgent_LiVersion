"""
Novokine RL outer loop — orchestrates the six pipeline stages and logs each
iteration to experience_buffer.jsonl.

Pipeline (matches Part 3 of rejuvenation_rl_plan.md):
  1. PROPOSE          — pick a (receptor_A, receptor_B, linker) candidate
  2. VALIDATE         — geometric/expression sanity check
  3. MECHANISM        — predict biased adaptor map → TFs → gene signature
  4. PHENOTYPE SCORE  — Fisher overlap vs muscle_atlas_DE.json (Track A, 50%)
  5. DECISION         — top-K / middle / bottom tier
  6. DESIGN           — submit binder design to Superbio (only top-tier)

Two run modes:
  --mode score_only    : feed candidate(s) directly via JSON; runs only Stage 4.
                         No agent spawn, no Superbio. Used to validate the
                         scoring math against H2F.
  --mode full          : POST to the running miniAgent /api/chat for stages 1–3,
                         compute Stage 4 locally, decide on Stage 5 tier, and
                         optionally fire Stage 6.
                         (Requires miniAgent backend running on $MINIAGENT_URL.)

Default: score_only with the H2F positive-control candidate.

Output: append-only JSONL at backend/knowledge/experience_buffer.jsonl
Each row is one iteration record. See _make_record() for schema.

Usage:
    python rl_loop.py                                       # H2F smoke test
    python rl_loop.py --mode score_only --input cand.json   # score a JSON list
    python rl_loop.py --mode full --iterations 3            # full loop (3 iter)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# Allow imports from backend/utils when running as a script
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from utils.phenotype_checkpoint import format_score_summary, score_phenotype  # noqa: E402

BUFFER_PATH = BACKEND / "knowledge" / "experience_buffer.jsonl"
ATLAS_PATHS = {
    "v1": BACKEND / "knowledge" / "muscle_atlas_DE.json",
    "v2": BACKEND / "knowledge" / "muscle_atlas_DE_v2_consensus.json",
}
ATLAS_VERSION = "v1"  # mutated by --atlas-version CLI flag in main()
ATLAS_PATH = ATLAS_PATHS[ATLAS_VERSION]
SCGPT_PROGRAMS_CACHE = BACKEND / "storage" / "scgpt_cache" / "gene_programs.json"

MINIAGENT_URL = os.environ.get("MINIAGENT_URL", "http://localhost:8002/api/chat")

# ── Decision tiers (from rejuvenation_rl_plan.md Step 6) ─────────────────────
TIER_TOP_DESIGN          = "TOP_K_DESIGN"            # phenotype > 0.5, mech ok → design
TIER_MIDDLE_HUMAN_REVIEW = "MIDDLE_HUMAN_REVIEW"     # 0.3 < phenotype ≤ 0.5
TIER_BOTTOM_LOG_ONLY     = "BOTTOM_LOG_ONLY"         # 0 ≤ phenotype ≤ 0.3
TIER_INCOHERENT          = "INCOHERENT_LOG_ONLY"     # phenotype ≤ 0 or chain broken

# Composite reward weights (per plan v5 — Track A.5 wired to scGPT gene programs)
W_TRACK_A   = 0.50  # phenotype overlap (raw atlas DE)
W_TRACK_B   = 0.30  # mechanism coherence (chain_soundness)
W_TRACK_C   = 0.10  # CMAP/CLUE sanity
W_TRACK_A5  = 0.10  # scGPT gene-program activation (young - aged)

# Normalization for Track A.5 raw score → [-1, +1]:
# raw score is unbounded sum of program activations (H2F ≈ +4.9, anti-rejuv ≈ -3.0).
# tanh(x / TRACK_A5_SCALE) gives a smooth squash that saturates near canonical exemplars.
TRACK_A5_SCALE = 2.5


# ── Positive-control seed: H2F (ERBB2 + FGFR1) ────────────────────────────────
# These are the published H2F outputs (Anand 2025, the Baker / Ruohola-Baker novokine)
# Predicted gene signature per the COT_Rejuv_Pipeline mechanism (MAPK + AKT on,
# PLCγ off → reprograms fibroblasts toward muscle, enhances myotube maturation).
H2F_SEED_CANDIDATE: dict[str, Any] = {
    "candidate_id": "H2F_positive_control",
    "receptor_A": "ERBB2",
    "receptor_B": "FGFR1",
    "linker": "GS×4 flexible (~15 aa)",
    "biased_output": {
        "transphosphorylation_adaptors": ["GRB2", "SHC1", "GAB1", "PIK3R1"],
        "cis_adaptors": [],
        "excluded_adaptors": ["PLCG1", "STAT3"],
    },
    # Predicted transcriptome shift — myogenic / contractile / mitochondrial up,
    # SASP / inflammation / quiescence-stress markers down.
    "predicted_up": [
        "MYH7", "MYH2", "TNNT3", "TNNT1", "MYOG", "MYOD1", "MEF2C",
        "ACTA2", "ACTA1", "MYL9", "DES", "IGFBP7", "MT-CO2",
    ],
    "predicted_down": [
        "EGR1", "IL32", "TXNIP", "JUN", "MYF5", "CDKN2A",
        "IL6", "MYH9", "OTUD1", "FOS",
    ],
    # Mechanism coherence (0–1) — produced by the COT pipeline in full mode.
    # Hardcoded high here because H2F is published and well-established.
    "chain_soundness": 0.85,
    # Optional Track C (CLUE) sanity score — None = not run yet
    "track_c_score": None,
    "literature_refs": ["doi:10.1038/s41586-025-XXXXX (H2F Baker 2025)"],
    "notes": "Positive-control seed — used to verify the loop produces a "
             "high reward for a published rejuvenating novokine.",
}


# ── Stage 4: phenotype score ─────────────────────────────────────────────────
def stage_phenotype_score(candidate: dict, cell_type: Optional[str] = None) -> dict:
    """Run Track A scoring against muscle_atlas_DE.json."""
    return score_phenotype(
        predicted_up=candidate.get("predicted_up", []),
        predicted_down=candidate.get("predicted_down", []),
        cell_type=cell_type,
        atlas_path=ATLAS_PATH,
    )


# ── Stage 4.5: Track A.5 — scGPT gene-program activation score ───────────────
def stage_track_a5_score(candidate: dict) -> Optional[dict]:
    """Score the candidate's predicted up/down gene set against scGPT-derived
    young/aged gene programs (Track A.5).

    Returns a dict with:
        raw_score       — unbounded sum: young_program_activation - aged_program_activation
        normalized      — tanh(raw / TRACK_A5_SCALE) ∈ [-1, +1]; this is what feeds reward
        score_young     — sum over young-enriched programs
        score_aged      — sum over aged-enriched programs (typically negative for rejuvenating)
        n_young_hit     — number of young programs with non-zero overlap
        n_aged_hit      — number of aged programs with non-zero overlap
        top_programs    — top 5 contributors by |activation|

    Returns None (gracefully) if the scGPT programs cache is missing — the
    composite reward will then renormalize over the remaining tracks.
    """
    if not SCGPT_PROGRAMS_CACHE.exists():
        return None

    import math

    with open(SCGPT_PROGRAMS_CACHE) as f:
        data = json.load(f)
    programs = data.get("programs", {})
    if not programs:
        return None

    up_set   = {g.upper() for g in candidate.get("predicted_up", [])}
    down_set = {g.upper() for g in candidate.get("predicted_down", [])}
    if not up_set and not down_set:
        return None

    score_young = 0.0
    score_aged = 0.0
    n_young_hit = 0
    n_aged_hit = 0
    contributions: list[dict] = []
    for pid, p in programs.items():
        genes = {g.upper() for g in p.get("genes", [])}
        if not genes:
            continue
        f_up = len(genes & up_set) / len(genes)
        f_down = len(genes & down_set) / len(genes)
        activation = f_up - f_down
        if activation == 0.0:
            continue
        direction = p.get("age_direction", "neutral")
        if direction == "young":
            score_young += activation
            n_young_hit += 1
        elif direction == "aged":
            score_aged += activation
            n_aged_hit += 1
        contributions.append({
            "program_id": pid,
            "direction": direction,
            "activation": activation,
            "n_genes": len(genes),
        })

    # Net: activate young programs (positive) AND suppress aged programs (positive)
    raw = score_young - score_aged
    normalized = math.tanh(raw / TRACK_A5_SCALE)

    top = sorted(contributions, key=lambda x: abs(x["activation"]), reverse=True)[:5]

    return {
        "raw_score":     raw,
        "normalized":    normalized,
        "score_young":   score_young,
        "score_aged":    score_aged,
        "n_young_hit":   n_young_hit,
        "n_aged_hit":    n_aged_hit,
        "top_programs":  top,
        "n_programs_cached": len(programs),
    }


# ── Stage 5: composite reward + tier ─────────────────────────────────────────
def stage_compose_reward(candidate: dict, phenotype: dict) -> dict:
    """
    Combine Track A (phenotype overlap), Track B (mechanism coherence), and
    optional Track C (CLUE) into a single reward and tier classification.
    """
    track_a = phenotype.get("phenotype_score", 0.0)            # ∈ [-1, +1]
    track_b = float(candidate.get("chain_soundness", 0.0))     # ∈ [0, 1]
    track_c = candidate.get("track_c_score")                   # Optional
    track_a5 = candidate.get("track_a5_score")                 # Optional (scGPT)

    components = {"track_a": track_a, "track_b": track_b}
    weights    = {"track_a": W_TRACK_A, "track_b": W_TRACK_B}
    if track_c is not None:
        components["track_c"] = float(track_c); weights["track_c"] = W_TRACK_C
    if track_a5 is not None:
        components["track_a5"] = float(track_a5); weights["track_a5"] = W_TRACK_A5

    # Renormalise weights over whichever components are present
    w_sum = sum(weights.values())
    weights_norm = {k: v / w_sum for k, v in weights.items()}
    reward = sum(components[k] * weights_norm[k] for k in components)

    # Tier classification
    verdict = phenotype.get("verdict", "NEUTRAL")
    if verdict == "ANTI-REJUVENATING" or track_b < 0.10:
        tier = TIER_INCOHERENT
    elif track_a > 0.5 and track_b >= 0.3:
        tier = TIER_TOP_DESIGN
    elif track_a > 0.3:
        tier = TIER_MIDDLE_HUMAN_REVIEW
    else:
        tier = TIER_BOTTOM_LOG_ONLY

    return {
        "reward":          reward,
        "tier":            tier,
        "components":      components,
        "weights":         weights_norm,
        "verdict":         verdict,
    }


# ── Experience buffer record ──────────────────────────────────────────────────
def _make_record(
    iteration: int,
    candidate: dict,
    phenotype: dict,
    decision: dict,
    *,
    mode: str,
    notes: str = "",
) -> dict:
    return {
        "iteration":        iteration,
        "iteration_id":     str(uuid.uuid4()),
        "timestamp":        _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode":             mode,
        "candidate":        candidate,
        "phenotype":        phenotype,
        "decision":         decision,
        "notes":            notes,
        "schema_version":   "rl_loop.v1",
    }


def append_to_buffer(record: dict, path: Path = BUFFER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ── Run modes ────────────────────────────────────────────────────────────────
def run_score_only(candidates: list[dict], cell_type: Optional[str] = None) -> list[dict]:
    """
    Score a list of pre-built candidates. No agent, no Superbio.
    Used for: smoke testing, validating new scoring math, batch re-scoring.
    """
    records = []
    for i, cand in enumerate(candidates):
        cid = cand.get("candidate_id", f"cand_{i}")
        print(f"\n[{i+1}/{len(candidates)}] scoring {cid} ...")
        phenotype = stage_phenotype_score(cand, cell_type=cell_type)
        a5 = stage_track_a5_score(cand)
        cand_for_score = dict(cand)
        if a5 is not None:
            cand_for_score["track_a5_score"] = a5["normalized"]
            cand_for_score["track_a5_detail"] = a5
        decision  = stage_compose_reward(cand_for_score, phenotype)
        record = _make_record(
            iteration=i, candidate=cand_for_score, phenotype=phenotype, decision=decision,
            mode="score_only",
        )
        append_to_buffer(record)
        records.append(record)
        # Console summary
        print(format_score_summary(phenotype))
        if a5 is not None:
            print(f"  Track A.5 (scGPT programs): raw={a5['raw_score']:+.3f} → normalized={a5['normalized']:+.3f}  "
                  f"({a5['n_young_hit']} young, {a5['n_aged_hit']} aged programs hit)")
        else:
            print(f"  Track A.5: cache missing or no input genes — skipped")
        print(f"  composite reward: {decision['reward']:+.4f}")
        print(f"  tier: {decision['tier']}")
        print(f"  components: {decision['components']}")
        print(f"  weights:    {decision['weights']}")
    print(f"\n[buffer] {len(records)} record(s) appended to {BUFFER_PATH}")
    return records


_FULL_AGENT_PROMPT_TEMPLATE = """\
You are running iteration {iteration} of the muscle-rejuvenation novokine RL loop.

Your task: produce a complete mechanism + transcriptome prediction for ONE
candidate novokine, then write the result to a JSON file.

CANDIDATE TO ANALYZE
  receptor_A: {receptor_A}
  receptor_B: {receptor_B}
  linker:     {linker}

{prefetch_block}

PIPELINE — follow the COT_Rejuv_Pipeline skill (read `skills/COT_Rejuv_Pipeline/SKILL.md` if needed):
  Step 1 — PROPOSE: confirm this pair is a valid forced-proximity novokine candidate (RTK/cytokine families).
            IMPORTANT: UniProt accession + family + atlas expression are PRE-FETCHED above — do NOT call
            uniprot_api for basic receptor identity or local_atlas_query for expression. Use the pre-fetched
            data directly. Only call uniprot_api if you need domain-specific detail not covered above.
  Step 2 — VALIDATE: kinase domain geometry. Check structural evidence via ncbi_eutils / fetch_url to RCSB.
            ⛔ DO NOT call ensembl_api for any reason. OmniPath, Reactome, BioGRID, PhosphoSitePlus
            all accept HGNC gene symbols directly. Calling ensembl_api wastes 5-7 tool calls per run.
  Step 3a — Adaptor classification: which adaptors are recruited via TRANSphosphorylation vs CIS phosphorylation
            vs sterically EXCLUDED. Use omnipath_api(query_type='enz_sub') and phosphosite_plus.
  Step 3b — Pathway cassette: use reactome_api on the **adaptors** (not receptors).
  Step 3c — TF→target mapping: use omnipath_api(query_type='tf_target'), confidence A+B only.
            Atlas calibration: muscle_atlas_DE.json P2_up/P1_up gene lists are PRE-LOADED above — use
            them directly without calling read_file. Move IEG/aged-marker genes out of predicted_up.
  Step 3d — CRISPR support: use biogrid_orcs(query_type='screens_for_gene') for predicted gene set.
  Step 4 — Assemble {{predicted_up, predicted_down}} HGNC symbol gene lists.
            DO NOT compute Track A/B/C scores or run Fisher exact tests — the outer RL loop
            handles all scoring. Your job ends at writing the JSON file.

CRITICAL BIOLOGICAL CONSTRAINT (re-check):
  Output of a forced-proximity novokine is the BIASED SUBSET of pathways that
  survive the geometric filter. It is NOT the union of receptor A and receptor
  B's pathway sets. Excluded adaptors lose their downstream pathway entirely.

OUTPUT FORMAT — at the very end, use the `write_file` tool to write a JSON file
at exactly this path (no other path):
  {output_json_path}

The JSON must have these keys:
{{
  "candidate_id": "{candidate_id}",
  "receptor_A": "{receptor_A}",
  "receptor_B": "{receptor_B}",
  "linker": "{linker}",
  "biased_output": {{
    "transphosphorylation_adaptors": [...],
    "cis_adaptors": [...],
    "excluded_adaptors": [...]
  }},
  "biased_pathways": ["MAPK", "AKT", ...],
  "predicted_up":   ["GENE1", "GENE2", ...],
  "predicted_down": ["GENE3", "GENE4", ...],
  "step_confidences": {{
    "step_1": 0.0-1.0,
    "step_2": 0.0-1.0,
    "step_3a": 0.0-1.0,
    "step_3b": 0.0-1.0,
    "step_3c": 0.0-1.0,
    "step_3d": 0.0-1.0,
    "step_4": 0.0-1.0
  }},
  "mechanism_narrative": "1-3 sentences describing the biased output",
  "literature_refs": ["PMID:...", "doi:..."]
}}

Tips:
- Use HGNC gene symbols (uppercase, no whitespace).
- Predicted gene lists should each have 5-15 entries that are biologically
  defensible based on the biased pathway output.
- step_confidences should reflect REAL confidence given evidence retrieved.
- After writing the JSON, finish with: "DONE iteration {iteration}".
"""


def _prefetch_receptor_context(receptor_A: str, receptor_B: str) -> str:
    """Pre-fetch receptor metadata and atlas expression to inject into the agent prompt.

    Eliminates ~6-10 agent tool calls per iteration:
    - 2-4 uniprot_api calls (basic accession + family lookup)
    - 1-2 local_atlas_query calls (age-stratified expression in muscle)
    - 2-3 read_file calls (muscle_atlas_DE.json reads for calibration + scoring)

    Persistent disk cache (backend/storage/receptor_cache.json) avoids re-fetching
    UniProt and atlas data within a 30-day window, reducing wall-clock by ~5-15s
    per iteration when the cache is warm.
    """
    from utils import receptor_cache  # noqa: E402

    lines: list[str] = ["## PRE-FETCHED DATA (do not re-query these)"]

    # ── 1. UniProt metadata (with disk cache) ─────────────────────────────────
    def _format_uniprot_line(gene: str, info: dict) -> str:
        base = (f"{gene}: UniProt={info.get('accession','?')}  "
                f"name='{info.get('name', gene)}'  "
                f"length={info.get('length','?')}aa  "
                f"family: {info.get('family','unknown family')}")
        # Domain architecture line (ECD, TM, kinase) if present
        ecd = info.get("ecd_range")
        tm = info.get("tm_range")
        kinase = info.get("kinase_range")
        arch_parts = []
        if ecd:
            arch_parts.append(f"ECD={ecd[0]}-{ecd[1]} ({ecd[1]-ecd[0]+1}aa)")
        if tm:
            arch_parts.append(f"TM={tm[0]}-{tm[1]}")
        if kinase:
            arch_parts.append(f"kinase={kinase[0]}-{kinase[1]}")
        if arch_parts:
            base += "\n   architecture: " + " | ".join(arch_parts)
        return base

    try:
        from tools.uniprot_api_tool import fetch_uniprot_response

        def _fetch_uniprot(gene: str) -> dict:
            """Return parsed UniProt info, using disk cache when fresh."""
            cached = receptor_cache.get(gene)
            # Use cache only if it has architecture info (otherwise refetch with new fields)
            if cached and cached.get("uniprot") and cached["uniprot"].get("ecd_range") is not None:
                return cached["uniprot"]
            resp = fetch_uniprot_response(
                query=f"gene_exact:{gene} AND organism_id:9606 AND reviewed:true",
                fields=("accession,gene_names,protein_name,cc_similarity,length,"
                        "ft_topo_dom,ft_transmem,ft_domain"),
                size=1,
            )
            info: dict = {}
            if resp.json_payload:
                results = resp.json_payload.get("results") or []
                if results:
                    r = results[0]
                    acc = r.get("primaryAccession", "?")
                    pd = r.get("proteinDescription") or {}
                    rec_name = pd.get("recommendedName") or {}
                    full_name = (rec_name.get("fullName") or {}).get("value", gene)
                    sim_comments = [
                        c for c in (r.get("comments") or []) if c.get("commentType") == "SIMILARITY"
                    ]
                    family = sim_comments[0].get("texts", [{}])[0].get("value", "unknown family")[:80] if sim_comments else "unknown family"
                    length = (r.get("sequence") or {}).get("length", "?")
                    # Parse domain features
                    ecd_range = None
                    tm_range = None
                    kinase_range = None
                    for ft in (r.get("features") or []):
                        ft_type = ft.get("type", "")
                        loc = ft.get("location") or {}
                        start = (loc.get("start") or {}).get("value")
                        end = (loc.get("end") or {}).get("value")
                        desc = (ft.get("description") or "").lower()
                        if ft_type == "Topological domain" and "extracellular" in desc and ecd_range is None:
                            ecd_range = (start, end) if start and end else None
                        elif ft_type == "Transmembrane" and tm_range is None:
                            tm_range = (start, end) if start and end else None
                        elif ft_type == "Domain" and "kinase" in desc and kinase_range is None:
                            kinase_range = (start, end) if start and end else None
                    info = {
                        "accession": acc, "name": full_name, "length": length, "family": family,
                        "ecd_range": ecd_range, "tm_range": tm_range, "kinase_range": kinase_range,
                    }
                    receptor_cache.put(gene, uniprot=info)
            return info

        lines.append("\n### Receptor UniProt metadata (Step 1a/1c/2 — use directly, skip uniprot_api calls)")
        for gene in (receptor_A, receptor_B):
            info = _fetch_uniprot(gene)
            if info:
                lines.append(_format_uniprot_line(gene, info))
            else:
                lines.append(f"{gene}: UniProt lookup returned no result (proceed with ncbi/PDB fallback)")
    except Exception as exc:
        lines.append(f"\n### UniProt pre-fetch skipped ({exc}) — agent must call uniprot_api normally")

    # ── 2. Local atlas expression (with disk cache) ───────────────────────────
    def _format_atlas_block(gene: str, gene_data: dict) -> list[str]:
        if not gene_data:
            return [f"{gene}: NOT FOUND in atlas (set p_fail_1 += 0.40)"]
        out = [f"{gene}:"]
        for ct, bins in gene_data.items():
            young = bins.get("young") or {}
            old = bins.get("old") or {}
            delta = bins.get("delta_old_minus_young") or {}
            ypc = young.get("fraction_expressing", 0.0)
            yme = young.get("mean_expression", 0.0)
            opc = old.get("fraction_expressing", 0.0)
            ome = old.get("mean_expression", 0.0)
            dpc = delta.get("fraction_expressing", 0.0)
            out.append(
                f"  {ct:10s}: young pc={ypc:.2f} me={yme:.2f} | old pc={opc:.2f} me={ome:.2f} | Δpc={dpc:+.2f}"
            )
        return out

    try:
        # Try cache first
        cached_A = receptor_cache.get(receptor_A)
        cached_B = receptor_cache.get(receptor_B)
        atlas_A = (cached_A or {}).get("atlas")
        atlas_B = (cached_B or {}).get("atlas")

        if atlas_A is None or atlas_B is None:
            from tools.local_atlas_tool import LocalAtlasTool

            tool = LocalAtlasTool()
            _content, art = tool._run(
                action="expression_summary",
                genes=[receptor_A, receptor_B],
                cell_types=["MuSC", "MF-I", "MF-II", "FB"],
            )
            if art and art.get("status") != "error":
                sp = art.get("structured_payload") or {}
                expr = sp.get("expression") or {}
                if atlas_A is None:
                    atlas_A = expr.get(receptor_A, {})
                    receptor_cache.put(receptor_A, atlas=atlas_A)
                if atlas_B is None:
                    atlas_B = expr.get(receptor_B, {})
                    receptor_cache.put(receptor_B, atlas=atlas_B)

        if atlas_A is not None and atlas_B is not None:
            lines.append("\n### Atlas expression summary — aged muscle (Step 1b — use directly, skip local_atlas_query)")
            lines.append("Format: cell_type | young pc/me | old pc/me | Δ(old-young)")
            lines.extend(_format_atlas_block(receptor_A, atlas_A))
            lines.extend(_format_atlas_block(receptor_B, atlas_B))
        else:
            lines.append("\n### Atlas expression: unavailable — call local_atlas_query normally")
    except Exception as exc:
        lines.append(f"\n### Atlas expression pre-fetch skipped ({exc}) — call local_atlas_query normally")

    # ── 3. Muscle atlas DE gene lists ─────────────────────────────────────────
    try:
        with open(ATLAS_PATH) as f:
            atlas = json.load(f)
        p2_up = atlas.get("P2_up", [])[:40]
        p1_up = atlas.get("P1_up", [])[:40]
        p2_dn = atlas.get("P2_down", [])[:20]
        p1_dn = atlas.get("P1_down", [])[:20]
        lines.append("\n### Muscle atlas DE gene lists (Step 3c calibration — use directly, skip read_file)")
        lines.append(f"P2_up  (young-enriched, target UP):   {', '.join(p2_up)}")
        lines.append(f"P1_up  (aged-enriched,  target DOWN):  {', '.join(p1_up)}")
        lines.append(f"P2_down (young-depleted, target DOWN): {', '.join(p2_dn)}")
        lines.append(f"P1_down (aged-depleted,  target UP):   {', '.join(p1_dn)}")
        lines.append("⛔ IEGs in P1_up (aged markers — NEVER put in predicted_up):"
                     " EGR1, FOS, JUN, MYC, MYH9, MYF5, IL32, TXNIP, ASB5")
    except Exception as exc:
        lines.append(f"\n### Atlas DE lists: unavailable ({exc}) — call read_file knowledge/muscle_atlas_DE.json")

    # ── 4. Adaptor → UniProt lookup table ─────────────────────────────────────
    adaptor_lookup_path = BACKEND / "knowledge" / "adaptor_uniprot_lookup.json"
    try:
        with open(adaptor_lookup_path) as f:
            adaptors = json.load(f)
        lines.append("\n### Adaptor → UniProt accession (for Step 3b reactome calls — skip uniprot_api lookups)")
        # Format compactly as gene=accession pairs
        adaptor_str = ", ".join(f"{g}={acc}" for g, acc in adaptors.items())
        lines.append(adaptor_str)
        lines.append("Use these directly in `reactome_api(query_type=\"pathway_for_entity\", identifier=ACC)`.")
    except Exception:
        pass  # silent — adaptor lookup is optional

    return "\n".join(lines)


# ── Stage 1-3: agent invocation (in-process) ────────────────────────────────
async def _run_agent_iteration(
    iteration: int,
    receptor_A: str,
    receptor_B: str,
    linker: str,
    candidate_id: str,
    output_json_path: Path,
    timeout_s: int = 600,
    verbose: bool = True,
) -> dict | None:
    """
    Invoke the in-process agent to perform Stages 1-3.
    Agent is instructed to write its prediction to output_json_path.
    Returns the parsed JSON dict, or None on failure.
    """
    import asyncio

    # Prepare runtime
    BACKEND_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BACKEND_DIR))

    # Load .env for API keys (tools need DEEPSEEK_API_KEY etc.)
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND_DIR / ".env")
    except ImportError:
        pass

    # ── Read the experience buffer BEFORE invoking the agent ──────────────
    # This closes the read side of the RL loop. Two roles:
    #   1. Exact-pair cache hit  → skip the 80-tool-call agent run, reuse the
    #      prior prediction. Per-iteration determinism + ~0.20 USD savings.
    #   2. Top-K wins + bottom-K failures injected into the prompt as a
    #      "PRIOR EXPERIENCE" markdown block so the agent learns from past
    #      iterations rather than redoing every reasoning step from scratch.
    from utils.experience_buffer import (  # noqa: E402
        load_buffer,
        top_k_rejuvenating,
        bottom_k_failures,
        lookup_by_pair,
        format_priors_block,
        format_pair_cache_block,
    )

    buffer_records = load_buffer()
    cache_hit = lookup_by_pair(
        buffer_records, receptor_A, receptor_B, linker, require_full_mode=True
    )
    if cache_hit is not None:
        if verbose:
            print(f"[full] {format_pair_cache_block(cache_hit)}")
            print(f"[full] reusing cached prediction; agent NOT invoked")
        cand = (cache_hit.get("candidate") or {}).copy()
        # Match the shape `_run_agent_iteration` returns to its caller:
        # a dict with predicted_up / predicted_down / step_confidences /
        # mechanism_narrative / biased_output / literature_refs.
        prediction: dict = {
            "candidate_id": candidate_id,
            "receptor_A": cand.get("receptor_A", receptor_A),
            "receptor_B": cand.get("receptor_B", receptor_B),
            "linker": cand.get("linker", linker),
            "biased_output": cand.get("biased_output") or {},
            "biased_pathways": cand.get("biased_pathways") or [],
            "predicted_up": cand.get("predicted_up") or [],
            "predicted_down": cand.get("predicted_down") or [],
            "step_confidences": cand.get("step_confidences") or {},
            "mechanism_narrative": cand.get("mechanism_narrative") or cand.get("notes", ""),
            "literature_refs": cand.get("literature_refs") or [],
            "_meta": {
                "n_tool_calls": 0,
                "n_tokens": 0,
                "cached_from_iteration": cache_hit.get("iteration"),
                "cached_from_iteration_id": cache_hit.get("iteration_id"),
                "cached_prior_reward": (cache_hit.get("decision") or {}).get("reward"),
                "cached_prior_tier": (cache_hit.get("decision") or {}).get("tier"),
            },
        }
        # Persist the cached prediction at output_json_path so downstream
        # stages (including stage 6 design fire) treat it identically to a
        # fresh agent run.
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w") as f:
            json.dump(prediction, f, indent=2)
        return prediction

    from graph.agent import agent_manager  # noqa: E402

    if agent_manager.base_dir is None:
        if verbose:
            print(f"[full] initializing agent_manager (base_dir={BACKEND_DIR})")
        agent_manager.initialize(BACKEND_DIR)

    # Make sure the output path doesn't exist (so we can detect if the agent wrote it)
    if output_json_path.exists():
        output_json_path.unlink()

    # Build the priors block (top-3 wins + bottom-2 failures) and prepend it
    # to the per-iteration prompt. format_priors_block returns "" when the
    # buffer is empty (first run) so this is a no-op on a fresh install.
    priors_block = format_priors_block(
        top_k_rejuvenating(buffer_records, k=3),
        bottom_k_failures(buffer_records, k=2),
    )

    # Pre-fetch receptor metadata + atlas expression + DE gene lists so the agent
    # can skip the corresponding tool calls (saves ~6-10 tool calls per iteration).
    if verbose:
        print(f"[full]   pre-fetching receptor context for {receptor_A} + {receptor_B} ...")
    prefetch_block = _prefetch_receptor_context(receptor_A, receptor_B)

    base_prompt = _FULL_AGENT_PROMPT_TEMPLATE.format(
        iteration=iteration,
        receptor_A=receptor_A,
        receptor_B=receptor_B,
        linker=linker,
        candidate_id=candidate_id,
        output_json_path=str(output_json_path),
        prefetch_block=prefetch_block,
    )
    prompt = (priors_block + "\n\n" + base_prompt) if priors_block else base_prompt

    if verbose:
        n_priors_chars = len(priors_block)
        print(
            f"[full] iter={iteration}  candidate={candidate_id}  "
            f"priors_block={n_priors_chars} chars  prefetch={len(prefetch_block)} chars  → invoking agent"
        )

    history: list[dict] = []
    n_tool_calls = 0
    n_tokens = 0
    final_text_buffer = ""
    error_msg: str | None = None

    try:
        async def _consume():
            nonlocal n_tool_calls, n_tokens, final_text_buffer, error_msg
            async for event in agent_manager.astream(prompt, history):
                etype = event.get("type")
                if etype == "tool_start":
                    n_tool_calls += 1
                    if verbose:
                        tname = event.get("tool", "?")
                        print(f"[full]   tool[{n_tool_calls}]: {tname}")
                elif etype == "token":
                    n_tokens += 1
                    final_text_buffer += event.get("content", "")
                elif etype == "error":
                    error_msg = event.get("error", "unknown")
                    if verbose:
                        print(f"[full]   ERROR: {error_msg}")
                elif etype == "done":
                    if verbose:
                        print(f"[full]   done. tool_calls={n_tool_calls}  tokens={n_tokens}")

        await asyncio.wait_for(_consume(), timeout=timeout_s)
    except asyncio.TimeoutError:
        if verbose:
            print(f"[full]   TIMEOUT after {timeout_s}s")
        error_msg = f"timeout after {timeout_s}s"
    except Exception as exc:
        if verbose:
            print(f"[full]   EXCEPTION: {exc}")
        error_msg = str(exc)

    # Try to load the JSON the agent should have written
    if output_json_path.exists():
        try:
            with open(output_json_path) as f:
                prediction = json.load(f)
            if verbose:
                up = len(prediction.get("predicted_up", []))
                down = len(prediction.get("predicted_down", []))
                print(f"[full]   ✓ JSON parsed: {up} up genes, {down} down genes")
            prediction["_meta"] = {
                "n_tool_calls":   n_tool_calls,
                "n_tokens":       n_tokens,
                "error":          error_msg,
                "agent_text_tail": final_text_buffer[-500:] if final_text_buffer else "",
            }
            return prediction
        except json.JSONDecodeError as e:
            if verbose:
                print(f"[full]   JSON decode error: {e}")
            return {"_error": f"json_decode: {e}", "_text_tail": final_text_buffer[-1000:]}

    if verbose:
        print(f"[full]   no JSON written at {output_json_path}")
    return {"_error": error_msg or "no_output_written", "_text_tail": final_text_buffer[-1000:]}


def run_full_loop(
    candidates: list[dict] | None = None,
    n_iterations: int = 1,
    timeout_per_iter_s: int = 600,
    verbose: bool = True,
    fire_design: bool = False,
    design_dry_run: bool = True,
) -> list[dict]:
    """
    Full agent-driven loop:
      For each candidate (or each iteration), invoke the in-process agent to
      perform Stages 1-3 (mechanism prediction), then score Stage 4-5 locally,
      log to experience_buffer.
    """
    import asyncio

    BACKEND_DIR = Path(__file__).resolve().parent.parent
    work_dir = BACKEND_DIR / "knowledge" / "agent_outputs"
    work_dir.mkdir(parents=True, exist_ok=True)

    # If no candidates supplied, run iteration count using H2F seed receptors as scaffold
    if not candidates:
        candidates = []
        for i in range(n_iterations):
            cid = f"H2F_iter{i}"
            candidates.append({
                "candidate_id": cid,
                "receptor_A": "ERBB2",
                "receptor_B": "FGFR1",
                "linker": "GS_med (~20 aa GS×4)",
            })

    records: list[dict] = []
    for i, cand in enumerate(candidates):
        cid = cand.get("candidate_id", f"cand_{i}")
        print(f"\n[full] [{i+1}/{len(candidates)}] {cid}: ERBB2={cand.get('receptor_A')} ERBB2={cand.get('receptor_B')}")
        out_path = work_dir / f"{cid}.json"

        prediction = asyncio.run(_run_agent_iteration(
            iteration=i,
            receptor_A=cand.get("receptor_A", "ERBB2"),
            receptor_B=cand.get("receptor_B", "FGFR1"),
            linker=cand.get("linker", "GS_med"),
            candidate_id=cid,
            output_json_path=out_path,
            timeout_s=timeout_per_iter_s,
            verbose=verbose,
        ))

        if prediction is None or "_error" in prediction:
            print(f"[full]   FAILED: {prediction.get('_error') if prediction else 'no return'}")
            record = _make_record(
                iteration=i, candidate=cand,
                phenotype={"phenotype_score": 0.0, "verdict": "FAILED", "error": prediction},
                decision={"tier": "INCOHERENT_LOG_ONLY", "reward": 0.0, "components": {}, "weights": {}, "verdict": "FAILED"},
                mode="full",
                notes="agent invocation failed",
            )
            append_to_buffer(record)
            records.append(record)
            continue

        # Stage 4 — phenotype score
        phenotype = stage_phenotype_score({
            "predicted_up":   prediction.get("predicted_up", []),
            "predicted_down": prediction.get("predicted_down", []),
        })

        # Track B from chain_soundness over the agent's reported step confidences
        try:
            from utils.chain_soundness import chain_soundness as _cs
            cs_result = _cs(prediction.get("step_confidences"))
            chain_score = cs_result["chain_soundness"]
        except Exception as exc:
            print(f"[full]   chain_soundness error: {exc}")
            cs_result = None
            chain_score = 0.5

        # Inject chain_soundness + predicted gene set into candidate for compose_reward
        cand_for_score = dict(cand)
        cand_for_score["chain_soundness"] = chain_score
        cand_for_score["predicted_up"]    = prediction.get("predicted_up", [])
        cand_for_score["predicted_down"]  = prediction.get("predicted_down", [])

        # Track A.5 — scGPT gene-program activation (depends on predicted_up/down)
        a5 = stage_track_a5_score(cand_for_score)
        if a5 is not None:
            cand_for_score["track_a5_score"] = a5["normalized"]
            cand_for_score["track_a5_detail"] = a5

        decision = stage_compose_reward(cand_for_score, phenotype)

        record = _make_record(
            iteration=i, candidate=cand_for_score,
            phenotype=phenotype, decision=decision,
            mode="full",
            notes=f"chain_soundness={chain_score:.3f}",
        )
        record["agent_prediction"] = prediction
        record["chain_soundness_detail"] = cs_result
        append_to_buffer(record)
        records.append(record)

        print(f"[full]   phenotype: {phenotype['phenotype_score']:+.4f}  verdict={phenotype['verdict']}")
        print(f"[full]   chain_soundness: {chain_score:.4f}")
        if a5 is not None:
            print(f"[full]   Track A.5 (scGPT): raw={a5['raw_score']:+.3f} → norm={a5['normalized']:+.3f}  "
                  f"({a5['n_young_hit']}Y / {a5['n_aged_hit']}A programs hit)")
        print(f"[full]   composite reward: {decision['reward']:+.4f}  tier={decision['tier']}")

        # Stage 6 — fire binder design submission for TOP_K_DESIGN tier
        if fire_design and decision.get("tier") == TIER_TOP_DESIGN:
            try:
                from utils.superbio_submit import submit_binder_design
                des_result = submit_binder_design(
                    candidate_id=cid,
                    receptor_A=cand_for_score.get("receptor_A", "?"),
                    receptor_B=cand_for_score.get("receptor_B", "?"),
                    num_designs=10,
                    dry_run=design_dry_run,
                )
                record["design_submission"] = des_result
                if design_dry_run:
                    print(f"[full]   stage6: DRY-RUN manifest at {des_result['manifest_path']}")
                else:
                    if des_result.get("submitted"):
                        print(f"[full]   stage6: ✓ submitted job_id={des_result['job_id']}")
                    else:
                        print(f"[full]   stage6: SKIPPED — {des_result.get('error')}")
            except Exception as exc:
                print(f"[full]   stage6: error {exc}")

    print(f"\n[full] {len(records)} record(s) appended to {BUFFER_PATH}")
    return records


def _load_candidates_json(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return [data]
    if not isinstance(data, list):
        raise ValueError(f"candidates JSON must be a list or single object, got {type(data)}")
    return data


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["score_only", "full"], default="score_only")
    ap.add_argument("--input", type=Path, default=None,
                    help="JSON file of candidate(s) to score (score_only mode).")
    ap.add_argument("--cell-type", default=None,
                    help="Atlas slice for Stage 4 scoring (default: pooled).")
    ap.add_argument("--iterations", type=int, default=1,
                    help="Number of iterations for full mode.")
    ap.add_argument("--seed-h2f", action="store_true", default=False,
                    help="Use the H2F positive-control candidate (default if no --input).")
    ap.add_argument("--timeout", type=int, default=600,
                    help="Per-iteration timeout for agent invocation (full mode, seconds; default 600).")
    ap.add_argument("--fire-design", action="store_true", default=False,
                    help="Submit Superbio binder design job for TOP_K_DESIGN tier candidates.")
    ap.add_argument("--design-live", action="store_true", default=False,
                    help="If set with --fire-design, do live submission (costs credits). Default: dry-run.")
    ap.add_argument("--atlas-version", choices=["v1", "v2"], default="v1",
                    help=("Which muscle aging atlas to score Track A against. "
                          "'v1' (default) = single-source pooled atlas (preserves 79-run buffer reproducibility); "
                          "'v2' = multi-source consensus atlas built from GSE164471/GSE111016/GTEx/Kedlian/Lai. "
                          "v2 requires `python backend/scripts/build_consensus_atlas.py` to have been run."))
    args = ap.parse_args()

    # Resolve atlas path before any candidate is scored
    global ATLAS_VERSION, ATLAS_PATH
    ATLAS_VERSION = args.atlas_version
    ATLAS_PATH = ATLAS_PATHS[ATLAS_VERSION]
    if not ATLAS_PATH.exists():
        print(f"ERROR: atlas {ATLAS_VERSION} not found at {ATLAS_PATH}")
        if ATLAS_VERSION == "v2":
            print("Run: python backend/scripts/build_consensus_atlas.py")
        return 1
    print(f"[rl_loop] atlas={ATLAS_VERSION} ({ATLAS_PATH.name})")

    if args.mode == "score_only":
        if args.input:
            cands = _load_candidates_json(args.input)
            print(f"[score_only] loaded {len(cands)} candidate(s) from {args.input}")
        else:
            cands = [H2F_SEED_CANDIDATE]
            print(f"[score_only] no --input supplied; running H2F positive-control seed")
        records = run_score_only(cands, cell_type=args.cell_type)
        # Highlight: how does H2F do?
        for r in records:
            if r["candidate"].get("candidate_id") == "H2F_positive_control":
                p = r["phenotype"]["phenotype_score"]
                v = r["phenotype"]["verdict"]
                t = r["decision"]["tier"]
                print(f"\n[H2F sanity] phenotype={p:+.4f}  verdict={v}  tier={t}")
                if p > 0.5 and v == "REJUVENATING":
                    print("[H2F sanity] ✅ PASS — pipeline correctly rewards the published positive control.")
                else:
                    print("[H2F sanity] ⚠ scoring did not give H2F a strong rejuvenating verdict.")
        return 0

    if args.mode == "full":
        cands: list[dict] | None = None
        if args.input:
            cands = _load_candidates_json(args.input)
            print(f"[full] loaded {len(cands)} candidate(s) from {args.input}")
        records = run_full_loop(
            candidates=cands,
            n_iterations=args.iterations,
            timeout_per_iter_s=getattr(args, "timeout", 600),
            fire_design=getattr(args, "fire_design", False),
            design_dry_run=not getattr(args, "design_live", False),
        )
        return 0 if records else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
