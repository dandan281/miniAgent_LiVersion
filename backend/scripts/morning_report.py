"""
Morning report — readable Markdown summary of the RL loop state.

Combines:
  - experience_buffer.jsonl iteration counts and tier distribution
  - Top candidates by composite reward (full mode preferred, score_only fallback)
  - Each top candidate's mechanism narrative (from agent_outputs/*.json)
  - Pending design submissions (from knowledge/design_outputs/)
  - Open issues / next steps

Output: a single Markdown document the user can read in 60 seconds to know
where the project stands.

Usage:
    python scripts/morning_report.py                 # stdout
    python scripts/morning_report.py --output morning_report.md
    python scripts/morning_report.py --top 10
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
BUFFER = BACKEND / "knowledge" / "experience_buffer.jsonl"
AGENT_OUTPUTS = BACKEND / "knowledge" / "agent_outputs"
DESIGN_OUTPUTS = BACKEND / "knowledge" / "design_outputs"


def load_buffer() -> list[dict]:
    rows = []
    if not BUFFER.exists():
        return rows
    with open(BUFFER) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def render_report(top_k: int = 5) -> str:
    rows = load_buffer()
    n_total = len(rows)
    by_mode = Counter(r.get("mode", "?") for r in rows)
    by_tier = Counter((r.get("decision") or {}).get("tier", "?") for r in rows)

    full_rows = [r for r in rows if r.get("mode") == "full"]
    score_rows = [r for r in rows if r.get("mode") == "score_only"]

    # Top by reward (prefer full mode if available)
    def reward_of(r):
        return (r.get("decision") or {}).get("reward", -999) or -999

    top_full = sorted(full_rows, key=reward_of, reverse=True)[:top_k]
    top_score = sorted(score_rows, key=reward_of, reverse=True)[:top_k]

    # Pending design submissions
    pending_designs = []
    if DESIGN_OUTPUTS.exists():
        for cand_dir in DESIGN_OUTPUTS.iterdir():
            if cand_dir.is_dir():
                m = cand_dir / "manifest.json"
                if m.exists():
                    try:
                        with open(m) as f:
                            mf = json.load(f)
                        if mf.get("dry_run") or mf.get("job_id"):
                            pending_designs.append({
                                "candidate_id": mf.get("candidate_id"),
                                "dry_run":      mf.get("dry_run", False),
                                "job_id":       mf.get("job_id"),
                                "submitted_at": mf.get("submitted_at"),
                            })
                    except Exception:
                        pass

    lines = []
    lines.append("# Morning Report — Novokine RL Loop")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")

    # ── Headline ────────────────────────────────────────────────────────────
    lines.append("## Headline")
    if full_rows:
        avg_reward_full = sum(reward_of(r) for r in full_rows) / len(full_rows)
        lines.append(f"- **{n_total}** total iterations logged ({len(full_rows)} agent-driven, {len(score_rows)} heuristic)")
        lines.append(f"- Mean composite reward (agent-driven): **{avg_reward_full:+.4f}**")
    else:
        lines.append(f"- {n_total} total iterations (all heuristic — no agent-driven runs yet)")
    lines.append(f"- Tier distribution: {dict(by_tier)}")
    lines.append(f"- Mode distribution: {dict(by_mode)}")
    if pending_designs:
        lines.append(f"- **{len(pending_designs)}** design submissions queued or pending")
    else:
        lines.append(f"- 0 design submissions yet")
    lines.append("")

    # ── Top candidates (agent-driven, if any) ──────────────────────────────
    if top_full:
        lines.append("## Top candidates — agent-driven (`--mode full`)")
        lines.append("These are the highest-reward candidates the agent has actually evaluated end-to-end.\n")
        lines.append("| rank | candidate_id | pair | linker | phenotype | chain | reward | tier |")
        lines.append("|------|--------------|------|--------|-----------|-------|--------|------|")
        for i, r in enumerate(top_full, 1):
            cand = r.get("candidate", {})
            phen = r.get("phenotype", {}) or {}
            dec = r.get("decision", {}) or {}
            cid = cand.get("candidate_id", "?")
            pair = f"{cand.get('receptor_A','?')}+{cand.get('receptor_B','?')}"
            linker = cand.get("linker", "?")
            psc = phen.get("phenotype_score") or 0.0
            chain = cand.get("chain_soundness") or 0.0
            rew = dec.get("reward") or 0.0
            tier = dec.get("tier", "?")
            lines.append(f"| {i} | {cid} | {pair} | {linker} | {psc:+.4f} | {chain:.3f} | {rew:+.4f} | {tier} |")
        lines.append("")

        # Detailed top-1 dossier
        if top_full:
            lines.append("### Top-1 detailed view")
            r = top_full[0]
            cand = r.get("candidate", {})
            cid = cand.get("candidate_id", "?")
            phen = r.get("phenotype", {}) or {}
            dec = r.get("decision", {}) or {}
            pred = r.get("agent_prediction", {}) or {}

            lines.append(f"**{cid}** — `{cand.get('receptor_A')}+{cand.get('receptor_B')}` with `{cand.get('linker')}` linker\n")
            lines.append(f"- **phenotype_score**: {phen.get('phenotype_score', 0):+.4f}  ({phen.get('verdict', '?')})")
            lines.append(f"- **chain_soundness**: {cand.get('chain_soundness', 0):.4f}")
            lines.append(f"- **composite reward**: {dec.get('reward', 0):+.4f}  → tier **{dec.get('tier', '?')}**\n")

            bo = pred.get("biased_output", {})
            if bo:
                lines.append("**Biased adaptor classification:**")
                lines.append(f"- trans-phospho: `{', '.join(bo.get('transphosphorylation_adaptors', [])) or '(none)'}`")
                lines.append(f"- cis: `{', '.join(bo.get('cis_adaptors', [])) or '(none)'}`")
                lines.append(f"- excluded: `{', '.join(bo.get('excluded_adaptors', [])) or '(none)'}`\n")

            if pred.get("biased_pathways"):
                lines.append(f"**Biased pathways**: {', '.join(pred['biased_pathways'])}\n")

            if pred.get("predicted_up"):
                lines.append(f"**Predicted UP** ({len(pred['predicted_up'])}): `{', '.join(pred['predicted_up'])}`\n")
            if pred.get("predicted_down"):
                lines.append(f"**Predicted DOWN** ({len(pred['predicted_down'])}): `{', '.join(pred['predicted_down'])}`\n")

            if pred.get("mechanism_narrative"):
                lines.append("**Narrative:**")
                lines.append(f"> {pred['mechanism_narrative']}\n")

            if pred.get("literature_refs"):
                lines.append("**Literature:**")
                for ref in pred["literature_refs"][:8]:
                    lines.append(f"- {ref}")
                lines.append("")

    # ── Heuristic top (score_only) ─────────────────────────────────────────
    if top_score:
        lines.append(f"## Top candidates — heuristic (`--mode score_only`)")
        lines.append(f"Generated by `scripts/generate_candidates.py` — class-pair × linker heuristic.\n")
        lines.append(f"_Note: heuristic candidates use hand-curated gene sets matching the atlas vocabulary, so phenotype scores are inflated relative to agent-driven predictions._\n")
        lines.append("| rank | candidate_id | pair | linker | phenotype | reward | tier |")
        lines.append("|------|--------------|------|--------|-----------|--------|------|")
        for i, r in enumerate(top_score[:top_k], 1):
            cand = r.get("candidate", {})
            phen = r.get("phenotype", {}) or {}
            dec = r.get("decision", {}) or {}
            cid = cand.get("candidate_id", "?")
            pair = f"{cand.get('receptor_A','?')}+{cand.get('receptor_B','?')}"
            linker = cand.get("linker", "?")
            psc = phen.get("phenotype_score") or 0.0
            rew = dec.get("reward") or 0.0
            tier = dec.get("tier", "?")
            lines.append(f"| {i} | {cid} | {pair} | {linker} | {psc:+.4f} | {rew:+.4f} | {tier} |")
        lines.append("")

    # ── Design submissions ─────────────────────────────────────────────────
    if pending_designs:
        lines.append("## Pending design submissions")
        lines.append("Manifests in `knowledge/design_outputs/`:\n")
        for d in pending_designs:
            stat = "DRY-RUN" if d["dry_run"] else (f"job_id={d['job_id']}" if d['job_id'] else "?")
            lines.append(f"- **{d['candidate_id']}**: {stat}  ({d.get('submitted_at', '?')})")
        lines.append("")

    # ── What's next ────────────────────────────────────────────────────────
    lines.append("## Next steps (suggested)")
    lines.append("- Spawn more iterations with `python scripts/rl_loop.py --mode full --input <candidates.json>`")
    lines.append("- Submit Superbio scGPT Mapping job to populate Track A.5 (gates Track A.5 reward)")
    lines.append("- For TOP_K_DESIGN candidates, run with `--fire-design --design-live` to actually submit binder design jobs (costs Superbio credits)")
    lines.append("- AlphaFold3 live mode: blocked on Google `AF3_API_KEY` approval")
    lines.append("- CLUE live mode: implementable but ~1-2 hr async polling work; mock provides Track C signal for now")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--output", type=Path, default=None,
                    help="Write report to this file (default: stdout)")
    args = ap.parse_args()

    md = render_report(top_k=args.top)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(md)
        print(f"[morning_report] wrote {args.output}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
