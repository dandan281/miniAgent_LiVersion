"""Candidate dossier generator.

Reads the experience buffer and produces one markdown dossier per
distinct receptor pair, summarizing for the user / human reviewer:
  - Mechanism narrative (from the agent output)
  - Adaptor classification (transphos / cis / excluded)
  - Predicted gene signature (top up + down)
  - Atlas overlap (Track A) — Fisher tests, Jaccard
  - Mechanism coherence (Track B) — chain_soundness breakdown
  - scGPT gene-program score (Track A.5) — top young/aged programs hit
  - CLUE perturbagen overlap (Track C) if any
  - Composite reward + tier
  - Atlas seed metadata (was the pair atlas-seeded? dropout cell types?)

Writes to backend/knowledge/dossiers/{TIER}/{receptor_pair}.md so the user
can quickly review TOP_K_DESIGN candidates first.

Run:
  python backend/scripts/generate_dossiers.py
  # or to focus on top tier only:
  python backend/scripts/generate_dossiers.py --tier TOP_K_DESIGN
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from utils.experience_buffer import load_buffer  # noqa: E402

DEFAULT_OUT = BACKEND / "knowledge" / "dossiers"

_TIER_DIRS = {
    "TOP_K_DESIGN": "01_top_k_design",
    "MIDDLE_HUMAN_REVIEW": "02_middle_human_review",
    "BOTTOM_LOG_ONLY": "03_bottom_log_only",
    "INCOHERENT_LOG_ONLY": "04_incoherent_log_only",
    "UNCATEGORIZED": "05_uncategorized",
}


def _select_best_per_pair(records: list[dict]) -> dict[str, dict]:
    """Group records by (rA, rB) order-invariant; keep highest-reward rec per pair."""
    by_pair: dict[str, dict] = {}
    for rec in records:
        cand = rec.get("candidate") or {}
        rA, rB = cand.get("receptor_A"), cand.get("receptor_B")
        if not rA or not rB:
            continue
        a, b = sorted([rA.upper(), rB.upper()])
        key = f"{a}_{b}"
        existing = by_pair.get(key)
        if existing is None:
            by_pair[key] = rec
            continue
        rew = (rec.get("decision") or {}).get("reward")
        rew_existing = (existing.get("decision") or {}).get("reward")
        if (rew is not None) and (rew_existing is None or rew > rew_existing):
            by_pair[key] = rec
    return by_pair


def _fmt_genes(genes: list[str], n: int = 12) -> str:
    if not genes:
        return "_(none)_"
    if len(genes) <= n:
        return ", ".join(f"`{g}`" for g in genes)
    return ", ".join(f"`{g}`" for g in genes[:n]) + f", _(+{len(genes) - n} more)_"


def _fmt_adaptors(bias: dict | None, key: str) -> str:
    if not isinstance(bias, dict):
        return "_(no data)_"
    items = bias.get(key) or []
    if not items:
        return "_(none)_"
    return ", ".join(f"`{x}`" for x in items)


def _fmt_phenotype_block(ph: dict | None) -> str:
    if not isinstance(ph, dict):
        return "_(no phenotype data)_"
    score = ph.get("phenotype_score")
    score_str = f"{score:+.4f}" if isinstance(score, (int, float)) else "n/a"
    verdict = ph.get("verdict") or "?"
    p2 = ph.get("P2_score")
    p1 = ph.get("P1_score")
    pos = ph.get("pos_total")
    neg = ph.get("neg_total")
    parts = [
        f"- **phenotype_score:** {score_str}  (verdict: **{verdict}**)",
    ]
    if isinstance(p2, (int, float)) and isinstance(p1, (int, float)):
        parts.append(f"- P2 (young) overlap: {p2:+.3f} | P1 (aged-down) overlap: {p1:+.3f}")
    if isinstance(pos, (int, float)) and isinstance(neg, (int, float)):
        parts.append(f"- pos_total (rejuv): {pos:+.3f} | neg_total (anti-rejuv): {neg:+.3f}")
    fisher_up = ph.get("fisher_up_vs_p2")
    fisher_dn = ph.get("fisher_down_vs_p1")
    if isinstance(fisher_up, dict):
        parts.append(
            f"- Fisher up vs P2: overlap={fisher_up.get('overlap')}/{fisher_up.get('predicted_size')} "
            f"odds={fisher_up.get('odds_ratio'):.2f} p={fisher_up.get('p_value'):.2e}"
        )
    if isinstance(fisher_dn, dict):
        parts.append(
            f"- Fisher down vs P1: overlap={fisher_dn.get('overlap')}/{fisher_dn.get('predicted_size')} "
            f"odds={fisher_dn.get('odds_ratio'):.2f} p={fisher_dn.get('p_value'):.2e}"
        )
    return "\n".join(parts)


def _fmt_decision_block(dec: dict | None) -> str:
    if not isinstance(dec, dict):
        return "_(no decision data)_"
    parts = []
    reward = dec.get("reward")
    tier = dec.get("tier") or "?"
    parts.append(f"- **composite reward:** {reward:+.4f}  →  tier: **{tier}**" if isinstance(reward, (int, float)) else f"- tier: **{tier}**")
    components = dec.get("components") or {}
    weights = dec.get("weights") or {}
    if components:
        parts.append("- Component breakdown:")
        for k, v in components.items():
            w = weights.get(k)
            wstr = f" (weight: {w:.2f})" if isinstance(w, (int, float)) else ""
            parts.append(f"  - `{k}`: {v:+.4f}{wstr}" if isinstance(v, (int, float)) else f"  - `{k}`: {v}")
    return "\n".join(parts)


def _fmt_chain_soundness(rec: dict) -> str:
    cand = rec.get("candidate") or {}
    cs = cand.get("chain_soundness")
    detail = rec.get("chain_soundness_detail") or {}
    parts = []
    if isinstance(cs, (int, float)):
        parts.append(f"- chain_soundness (Track B): **{cs:.3f}**")
    if isinstance(detail, dict) and detail:
        per_step = detail.get("per_step_p_fail") or detail.get("p_fail_per_step") or {}
        if isinstance(per_step, dict) and per_step:
            parts.append("- per-step p_fail:")
            for step, pf in per_step.items():
                if isinstance(pf, (int, float)):
                    parts.append(f"  - {step}: p_fail={pf:.3f}")
    return "\n".join(parts) if parts else "_(no chain-soundness detail)_"


def _fmt_atlas_seed(rec: dict) -> str:
    """If the candidate came from the atlas-seeded generator, surface its seed metadata."""
    cand = rec.get("candidate") or {}
    seed = cand.get("atlas_seed")
    if not isinstance(seed, dict):
        return ""
    parts = ["### Atlas seed metadata"]
    parts.append(f"- composite_atlas_score: {seed.get('composite_atlas_score')}")
    if seed.get("co_expression_in_old"):
        parts.append(f"- co-expression in **old**: {', '.join(seed['co_expression_in_old'])}")
    if seed.get("co_expression_in_young"):
        parts.append(f"- co-expression in **young**: {', '.join(seed['co_expression_in_young'])}")
    if seed.get("aged_dropout_cell_types"):
        parts.append(f"- ⚠ aged-dropout cell types: {', '.join(seed['aged_dropout_cell_types'])}")
    if seed.get("ecd_ratio"):
        parts.append(f"- ECD asymmetry ratio: {seed['ecd_ratio']}× (H2F = 1.78×)")
    if seed.get("family_A") or seed.get("family_B"):
        parts.append(f"- families: {seed.get('family_A')} × {seed.get('family_B')}")
    return "\n".join(parts) + "\n"


def render_dossier(rec: dict) -> str:
    cand = rec.get("candidate") or {}
    ph = rec.get("phenotype") or {}
    dec = rec.get("decision") or {}
    rA, rB = cand.get("receptor_A", "?"), cand.get("receptor_B", "?")
    linker = cand.get("linker", "?")
    cand_id = cand.get("candidate_id", f"{rA}_{rB}")
    bias = cand.get("biased_output") or {}
    iter_id = rec.get("iteration_id", "?")
    ts = rec.get("timestamp", "?")
    mode = rec.get("mode", "?")
    tier = (dec.get("tier") or "?")

    sections = [
        f"# Novokine candidate dossier — {rA} + {rB}",
        f"_Generated from experience buffer record `{iter_id}` at {ts} (mode={mode})._",
        "",
        f"- **receptor_A:** `{rA}`",
        f"- **receptor_B:** `{rB}`",
        f"- **linker:** `{linker}`",
        f"- **candidate_id:** `{cand_id}`",
        f"- **tier:** **{tier}**",
        "",
        "## Mechanism narrative",
        cand.get("mechanism_narrative") or cand.get("notes") or "_(no narrative provided)_",
        "",
        "## Adaptor classification (biased output)",
        f"- **transphosphorylation adaptors:** {_fmt_adaptors(bias, 'transphosphorylation_adaptors')}",
        f"- **cis-only adaptors:** {_fmt_adaptors(bias, 'cis_adaptors')}",
        f"- **sterically excluded:** {_fmt_adaptors(bias, 'excluded_adaptors')}",
        "",
        "## Predicted gene signature",
        f"- **predicted_up** (top 12): {_fmt_genes(cand.get('predicted_up') or [])}",
        f"- **predicted_down** (top 12): {_fmt_genes(cand.get('predicted_down') or [])}",
        "",
        "## Track A — atlas overlap (phenotype score)",
        _fmt_phenotype_block(ph),
        "",
        "## Track B — mechanism coherence",
        _fmt_chain_soundness(rec),
        "",
        "## Composite reward",
        _fmt_decision_block(dec),
        "",
    ]

    seed_block = _fmt_atlas_seed(rec)
    if seed_block:
        sections.append(seed_block)

    refs = cand.get("literature_refs") or []
    if refs:
        sections.append("## Literature references")
        for ref in refs:
            sections.append(f"- {ref}")
        sections.append("")

    return "\n".join(sections)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output dossiers directory.")
    ap.add_argument("--tier", default=None,
                    help="Limit to a single tier (e.g. TOP_K_DESIGN).")
    ap.add_argument("--clean", action="store_true",
                    help="Wipe the dossiers dir before regenerating.")
    args = ap.parse_args()

    records = load_buffer()
    if not records:
        print("[dossiers] experience buffer empty — nothing to render.")
        return 0

    by_pair = _select_best_per_pair(records)
    print(f"[dossiers] {len(records)} records → {len(by_pair)} unique pairs.")

    out_root = args.out
    if args.clean and out_root.exists():
        import shutil
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    for tier_dir in _TIER_DIRS.values():
        (out_root / tier_dir).mkdir(parents=True, exist_ok=True)

    written = 0
    for pair_key, rec in sorted(by_pair.items()):
        tier = (rec.get("decision") or {}).get("tier") or "UNCATEGORIZED"
        if args.tier and tier != args.tier:
            continue
        tier_dir = _TIER_DIRS.get(tier, _TIER_DIRS["UNCATEGORIZED"])
        out_path = out_root / tier_dir / f"{pair_key}.md"
        out_path.write_text(render_dossier(rec))
        written += 1

    print(f"[dossiers] wrote {written} dossiers to {out_root}")

    # Manifest with one-line summaries per dossier, sorted by reward desc
    manifest_rows = []
    for pair_key, rec in by_pair.items():
        tier = (rec.get("decision") or {}).get("tier") or "UNCATEGORIZED"
        if args.tier and tier != args.tier:
            continue
        cand = rec.get("candidate") or {}
        ph = rec.get("phenotype") or {}
        dec = rec.get("decision") or {}
        manifest_rows.append({
            "pair": pair_key,
            "tier": tier,
            "reward": dec.get("reward"),
            "phenotype": ph.get("phenotype_score"),
            "verdict": ph.get("verdict"),
            "linker": cand.get("linker"),
            "iteration": rec.get("iteration"),
            "dossier_path": str((_TIER_DIRS.get(tier, _TIER_DIRS["UNCATEGORIZED"])) + "/" + pair_key + ".md"),
        })
    manifest_rows.sort(key=lambda r: -(r.get("reward") or 0))
    manifest_path = out_root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest_rows, indent=2))
    # Also write a human-readable index
    index_lines = ["# Dossiers index", ""]
    index_lines.append(f"_Generated from {len(records)} experience-buffer records._")
    index_lines.append("")
    index_lines.append("| Pair | Tier | Reward | Verdict | Linker | Dossier |")
    index_lines.append("|---|---|---|---|---|---|")
    for r in manifest_rows:
        rew = r.get("reward")
        rew_str = f"{rew:+.4f}" if isinstance(rew, (int, float)) else "n/a"
        index_lines.append(
            f"| `{r['pair']}` | {r['tier']} | {rew_str} | {r['verdict']} | "
            f"{r['linker']} | [`{r['dossier_path']}`]({r['dossier_path']}) |"
        )
    (out_root / "INDEX.md").write_text("\n".join(index_lines))
    print(f"[dossiers] wrote MANIFEST.json + INDEX.md to {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
