"""
Candidate dossier — pretty-prints a single novokine candidate's full record
combining experience_buffer.jsonl + the agent's structured prediction JSON.

Usage:
    python scripts/candidate_dossier.py H2F_iter0
    python scripts/candidate_dossier.py ERBB2_FGFR1__GS_med --markdown
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
BUFFER = BACKEND / "knowledge" / "experience_buffer.jsonl"
AGENT_OUTPUTS = BACKEND / "knowledge" / "agent_outputs"


def load_record(cid: str) -> dict | None:
    """Find the latest record matching candidate_id."""
    if not BUFFER.exists():
        return None
    matches = []
    with open(BUFFER) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            cand = r.get("candidate", {})
            if cand.get("candidate_id") == cid:
                matches.append(r)
    return matches[-1] if matches else None


def load_prediction(cid: str) -> dict | None:
    p = AGENT_OUTPUTS / f"{cid}.json"
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def render(record: dict | None, prediction: dict | None, *, markdown: bool = False) -> str:
    h2 = "##" if markdown else "===="
    h3 = "###" if markdown else "----"

    if not record and not prediction:
        return "(no record found)"

    cand = (record or {}).get("candidate", {})
    phen = (record or {}).get("phenotype", {}) or {}
    dec = (record or {}).get("decision", {}) or {}
    cs = (record or {}).get("chain_soundness_detail") or {}
    ds = (record or {}).get("design_submission") or {}

    # Use prediction fields if record is missing
    if not cand and prediction:
        cand = {k: prediction.get(k) for k in ("candidate_id", "receptor_A", "receptor_B", "linker")}

    lines = []
    cid = cand.get("candidate_id", "?")
    lines.append(f"# Candidate dossier — {cid}" if markdown else f"\n=== CANDIDATE DOSSIER: {cid} ===\n")

    # Top-line summary
    lines.append(f"\n{h2} Summary")
    lines.append(f"- receptor pair: **{cand.get('receptor_A')}+{cand.get('receptor_B')}**" if markdown else
                 f"  receptor pair:  {cand.get('receptor_A')}+{cand.get('receptor_B')}")
    lines.append(f"- linker: {cand.get('linker')}" if markdown else f"  linker:         {cand.get('linker')}")
    lines.append(f"- mode: {(record or {}).get('mode', '?')}" if markdown else f"  mode:           {(record or {}).get('mode', '?')}")
    lines.append(f"- iteration: {(record or {}).get('iteration')}" if markdown else f"  iteration:      {(record or {}).get('iteration')}")
    lines.append(f"- timestamp: {(record or {}).get('timestamp')}" if markdown else f"  timestamp:      {(record or {}).get('timestamp')}")

    # Scores
    lines.append(f"\n{h2} Scores")
    psc = phen.get("phenotype_score")
    chain = cand.get("chain_soundness")
    rew = dec.get("reward")
    tier = dec.get("tier")
    verd = phen.get("verdict")
    lines.append(f"  phenotype_score: {psc:+.4f}" if isinstance(psc, (int, float)) else f"  phenotype_score: --")
    lines.append(f"  chain_soundness: {chain:.4f}" if isinstance(chain, (int, float)) else f"  chain_soundness: --")
    lines.append(f"  composite reward: {rew:+.4f}" if isinstance(rew, (int, float)) else f"  composite reward: --")
    lines.append(f"  tier: {tier}    verdict: {verd}")

    if dec.get("components"):
        lines.append(f"\n  components:")
        for k, v in dec["components"].items():
            lines.append(f"    {k}: {v:+.4f}" if isinstance(v, (int, float)) else f"    {k}: {v}")

    # Phenotype detail
    if phen.get("fisher_up_vs_p2"):
        lines.append(f"\n{h2} Phenotype detail (Fisher overlap)")
        for label, key in [("up vs P2_up (young, target)", "fisher_up_vs_p2"),
                           ("down vs P1_up (aged, target)", "fisher_down_vs_p1"),
                           ("up vs P1_up (aged, penalty)", "fisher_up_vs_p1"),
                           ("down vs P2_up (young, penalty)", "fisher_down_vs_p2")]:
            f = phen.get(key, {})
            if isinstance(f, dict) and f.get("overlap") is not None:
                lines.append(f"  {label}: overlap={f['overlap']}/{f['reference_size']}  "
                             f"odds={f['odds_ratio']:.2f}  p={f['p_value']:.2e}")

    # Mechanism / agent prediction
    pred = prediction or (record or {}).get("agent_prediction") or {}
    if pred:
        lines.append(f"\n{h2} Mechanism (agent prediction)")
        bo = pred.get("biased_output", {})
        if bo:
            lines.append(f"  trans-phosphorylation: {', '.join(bo.get('transphosphorylation_adaptors', []))}")
            lines.append(f"  cis adaptors:          {', '.join(bo.get('cis_adaptors', [])) or '(none)'}")
            lines.append(f"  excluded adaptors:     {', '.join(bo.get('excluded_adaptors', [])) or '(none)'}")
        if pred.get("biased_pathways"):
            lines.append(f"  biased pathways: {', '.join(pred['biased_pathways'])}")
        if pred.get("predicted_up"):
            lines.append(f"\n  predicted UP   ({len(pred['predicted_up'])}): "
                         + ", ".join(pred["predicted_up"]))
        if pred.get("predicted_down"):
            lines.append(f"  predicted DOWN ({len(pred['predicted_down'])}): "
                         + ", ".join(pred["predicted_down"]))
        if pred.get("step_confidences"):
            lines.append(f"\n  step confidences:")
            for k, v in pred["step_confidences"].items():
                lines.append(f"    {k}: {v}")
        if pred.get("mechanism_narrative"):
            lines.append(f"\n  Narrative:")
            lines.append(f"    {pred['mechanism_narrative']}")
        if pred.get("literature_refs"):
            lines.append(f"\n  Literature:")
            for ref in pred["literature_refs"]:
                lines.append(f"    - {ref}")

    # Chain soundness detail
    if cs:
        lines.append(f"\n{h2} Chain soundness")
        lines.append(f"  geom mean: {cs.get('chain_soundness'):.4f}")
        lines.append(f"  joint prob: {cs.get('joint_probability'):.4f}")
        ms = cs.get("min_step", ("", 0))
        xs = cs.get("max_step", ("", 0))
        if ms and xs:
            lines.append(f"  weakest: {ms[0]}={ms[1]:.3f}   strongest: {xs[0]}={xs[1]:.3f}")

    # Stage 6 design submission
    if ds:
        lines.append(f"\n{h2} Stage 6 — Design submission")
        lines.append(f"  submitted: {ds.get('submitted')}    dry_run: {ds.get('dry_run')}")
        lines.append(f"  job_id: {ds.get('job_id')}")
        if ds.get("error"):
            lines.append(f"  error: {ds.get('error')}")
        lines.append(f"  manifest: {ds.get('manifest_path')}")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate_id", help="Candidate id, e.g. H2F_iter0 or ERBB2_FGFR1__GS_med")
    ap.add_argument("--markdown", action="store_true", default=False)
    args = ap.parse_args()

    record = load_record(args.candidate_id)
    prediction = load_prediction(args.candidate_id)

    if not record and not prediction:
        print(f"[error] No record or prediction found for '{args.candidate_id}'.")
        return 1

    print(render(record, prediction, markdown=args.markdown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
