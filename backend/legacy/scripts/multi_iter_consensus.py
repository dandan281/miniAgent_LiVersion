"""
Multi-iteration consensus runner.

Runs the SAME (receptor_A, receptor_B, linker) candidate through the agent N
times, then aggregates predictions to produce a more stable estimate:

  - phenotype_score:  median across iterations
  - chain_soundness:  median across iterations
  - composite reward: median across iterations
  - predicted_up:     genes appearing in ≥majority of iterations (e.g. 2/3)
  - predicted_down:   same

This addresses the DeepSeek non-determinism we observed in the first batch,
where the same ERBB2+FGFR1+GS_med pair scored phenotype +0.38 in one run and
+0.15 in another. Aggregating multiple runs gives:
  - lower variance per pair
  - robust gene predictions (only those that survive across runs)
  - explicit consensus probabilities (gene_X appeared in 3/3 runs → high prior)

Usage:
    python scripts/multi_iter_consensus.py --pair ERBB2 FGFR1 --linker GS_med --n 3
    python scripts/multi_iter_consensus.py --candidate-id MyCandidate --pair INSR MET --n 5

Outputs:
  - knowledge/consensus_outputs/<candidate_id>__consensus.json
  - one experience_buffer.jsonl record per iteration (mode=full_consensus)
  - one summary record at end (mode=consensus)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from utils.phenotype_checkpoint import score_phenotype  # noqa: E402
from utils.chain_soundness import chain_soundness as _cs  # noqa: E402

CONSENSUS_DIR = BACKEND / "knowledge" / "consensus_outputs"
BUFFER = BACKEND / "knowledge" / "experience_buffer.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_buffer(record: dict) -> None:
    BUFFER.parent.mkdir(parents=True, exist_ok=True)
    with open(BUFFER, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


async def _one_iteration(
    receptor_A: str,
    receptor_B: str,
    linker: str,
    iter_idx: int,
    candidate_id: str,
    timeout_s: int = 900,
) -> dict | None:
    """Invoke the agent once, return the parsed prediction dict."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    except ImportError:
        pass
    from graph.agent import agent_manager

    if agent_manager.base_dir is None:
        agent_manager.initialize(BACKEND)

    from scripts.rl_loop import _FULL_AGENT_PROMPT_TEMPLATE  # reuse the prompt
    out_path = BACKEND / "knowledge" / "agent_outputs" / f"{candidate_id}__iter{iter_idx}.json"
    if out_path.exists():
        out_path.unlink()

    prompt = _FULL_AGENT_PROMPT_TEMPLATE.format(
        iteration=iter_idx,
        receptor_A=receptor_A,
        receptor_B=receptor_B,
        linker=linker,
        candidate_id=f"{candidate_id}__iter{iter_idx}",
        output_json_path=str(out_path),
    )

    print(f"  [iter {iter_idx}] invoking agent ...")
    n_tool_calls = 0
    error_msg: str | None = None
    try:
        async def _consume():
            nonlocal n_tool_calls, error_msg
            async for event in agent_manager.astream(prompt, []):
                if event.get("type") == "tool_start":
                    n_tool_calls += 1
                    if n_tool_calls % 10 == 0:
                        print(f"  [iter {iter_idx}]   tool {n_tool_calls} ...")
                elif event.get("type") == "error":
                    error_msg = event.get("error", "unknown")
        await asyncio.wait_for(_consume(), timeout=timeout_s)
    except asyncio.TimeoutError:
        error_msg = f"timeout after {timeout_s}s"
    except Exception as exc:
        error_msg = str(exc)

    if not out_path.exists():
        print(f"  [iter {iter_idx}] no JSON written. error={error_msg}")
        return None

    try:
        with open(out_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [iter {iter_idx}] JSON decode error: {e}")
        return None


def _consensus_genes(per_iter_lists: list[list[str]], min_fraction: float = 0.5) -> list[tuple[str, int]]:
    """
    Return genes appearing in at least ceil(N * min_fraction) iterations,
    sorted by frequency (descending).
    """
    if not per_iter_lists:
        return []
    n = len(per_iter_lists)
    threshold = max(1, int(n * min_fraction + 0.999))  # ceil
    counts = Counter()
    for genes in per_iter_lists:
        seen = set()
        for g in genes:
            gu = g.strip().upper()
            if gu and gu not in seen:
                counts[gu] += 1
                seen.add(gu)
    consensus = [(g, c) for g, c in counts.items() if c >= threshold]
    consensus.sort(key=lambda x: (-x[1], x[0]))
    return consensus


def aggregate(predictions: list[dict], candidate_id: str,
              receptor_A: str, receptor_B: str, linker: str) -> dict:
    """Produce consensus prediction from N iterations."""
    valid = [p for p in predictions if p is not None]
    n = len(valid)

    # Gather per-iteration metrics
    phen_scores = []
    chain_scores = []
    rewards = []
    ups = []
    downs = []
    for p in valid:
        phen = score_phenotype(
            predicted_up=p.get("predicted_up", []),
            predicted_down=p.get("predicted_down", []),
        )
        cs_r = _cs(p.get("step_confidences"))
        chain = cs_r["chain_soundness"]
        phen_scores.append(phen["phenotype_score"])
        chain_scores.append(chain)
        # Composite reward (50% A, 30% B re-normalised when only A+B present)
        # match rl_loop's stage_compose_reward
        rew = 0.625 * phen["phenotype_score"] + 0.375 * chain
        rewards.append(rew)
        ups.append(p.get("predicted_up", []))
        downs.append(p.get("predicted_down", []))

    median_phen   = statistics.median(phen_scores) if phen_scores else 0.0
    median_chain  = statistics.median(chain_scores) if chain_scores else 0.0
    median_reward = statistics.median(rewards) if rewards else 0.0

    consensus_up   = _consensus_genes(ups,   min_fraction=0.5)
    consensus_down = _consensus_genes(downs, min_fraction=0.5)

    return {
        "candidate_id":        candidate_id,
        "receptor_A":          receptor_A,
        "receptor_B":          receptor_B,
        "linker":              linker,
        "n_iterations":        n,
        "n_failed":            len(predictions) - n,
        "median_phenotype":    median_phen,
        "median_chain":        median_chain,
        "median_reward":       median_reward,
        "phenotype_per_iter":  phen_scores,
        "chain_per_iter":      chain_scores,
        "reward_per_iter":     rewards,
        "consensus_up":        [{"gene": g, "n": c} for g, c in consensus_up[:25]],
        "consensus_down":      [{"gene": g, "n": c} for g, c in consensus_down[:25]],
        "stable_up_genes":     [g for g, _ in consensus_up],
        "stable_down_genes":   [g for g, _ in consensus_down],
        "timestamp":           _now(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, required=True, metavar=("RECA", "RECB"))
    ap.add_argument("--linker", default="GS_med")
    ap.add_argument("--n", type=int, default=3, help="Iterations (default 3)")
    ap.add_argument("--candidate-id", default=None,
                    help="ID stem (default: <recA>_<recB>_<linker>)")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    cid = args.candidate_id or f"{args.pair[0]}_{args.pair[1]}_{args.linker}_consensus"
    print(f"[consensus] {cid}: pair={args.pair}, linker={args.linker}, n={args.n}")

    CONSENSUS_DIR.mkdir(parents=True, exist_ok=True)

    predictions: list[dict | None] = []
    for i in range(args.n):
        pred = asyncio.run(_one_iteration(
            receptor_A=args.pair[0],
            receptor_B=args.pair[1],
            linker=args.linker,
            iter_idx=i,
            candidate_id=cid,
            timeout_s=args.timeout,
        ))
        predictions.append(pred)
        if pred:
            print(f"  [iter {i}] ✓ {len(pred.get('predicted_up', []))} up, "
                  f"{len(pred.get('predicted_down', []))} down")
        else:
            print(f"  [iter {i}] ✗ failed")

    consensus = aggregate(predictions, cid, args.pair[0], args.pair[1], args.linker)
    out_path = CONSENSUS_DIR / f"{cid}.json"
    with open(out_path, "w") as f:
        json.dump(consensus, f, indent=2, default=str)

    print(f"\n[consensus] median_phenotype: {consensus['median_phenotype']:+.4f}")
    print(f"[consensus] median_chain:     {consensus['median_chain']:.4f}")
    print(f"[consensus] median_reward:    {consensus['median_reward']:+.4f}")
    print(f"[consensus] stable up genes ({len(consensus['stable_up_genes'])}): "
          f"{', '.join(consensus['stable_up_genes'][:10])}")
    print(f"[consensus] stable down genes ({len(consensus['stable_down_genes'])}): "
          f"{', '.join(consensus['stable_down_genes'][:10])}")
    print(f"[consensus] saved to {out_path}")

    # Append a synthetic record to the experience buffer
    rec = {
        "iteration":      0,
        "iteration_id":   str(uuid.uuid4()),
        "timestamp":      _now(),
        "mode":           "consensus",
        "candidate":      {
            "candidate_id":   cid,
            "receptor_A":     args.pair[0],
            "receptor_B":     args.pair[1],
            "linker":         args.linker,
            "chain_soundness": consensus["median_chain"],
            "predicted_up":   consensus["stable_up_genes"],
            "predicted_down": consensus["stable_down_genes"],
        },
        "phenotype": {
            "phenotype_score": consensus["median_phenotype"],
            "verdict":         "REJUVENATING" if consensus["median_phenotype"] > 0.3
                                else ("ANTI-REJUVENATING" if consensus["median_phenotype"] < -0.3 else "NEUTRAL"),
            "n_iterations":    consensus["n_iterations"],
        },
        "decision": {
            "reward":    consensus["median_reward"],
            "tier":      "TOP_K_DESIGN" if consensus["median_phenotype"] > 0.5
                          else ("MIDDLE_HUMAN_REVIEW" if consensus["median_phenotype"] > 0.3
                                else "BOTTOM_LOG_ONLY"),
            "components": {"track_a": consensus["median_phenotype"], "track_b": consensus["median_chain"]},
        },
        "consensus_summary": consensus,
        "schema_version":    "consensus.v1",
    }
    _append_buffer(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
