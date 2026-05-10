"""Evidence-stacking CLI.

Usage:
    python -m evidence_stacking.cli score --composite v40
    python -m evidence_stacking.cli run --max-stages 1 --mock-agent
    python -m evidence_stacking.cli run --max-stages 20 --executor anthropic:claude-opus-4-7
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .composites import composite as comp_mod
from .composites import loader as comp_loader
from .evaluator import atlas_reward, metrics
from .orchestrator.agents import ClaudeAgent, MockAgent
from .orchestrator.loop import run as run_loop
from .receptor_universe import load as load_universe


def _cmd_score(args: argparse.Namespace) -> int:
    manifest = comp_loader.load(args.composite)
    universe = load_universe()
    pairs = list(universe.pairs())
    scores = comp_mod.score_all(manifest, pairs)
    print(f"composite={manifest.version} | features={[f.name for f in manifest.features]}")
    print(f"scored {len(scores)} pairs")
    for tgt in atlas_reward.TARGETS:
        try:
            target = atlas_reward.load(tgt)
        except FileNotFoundError as e:
            print(f"  {tgt}: target missing — {e}")
            continue
        _, holdout = atlas_reward.split(target)
        s = {pid: cs.score for pid, cs in scores.items() if pid in holdout}
        m = metrics.metrics_bundle(s, holdout)
        print(
            f"  {tgt:>14}: rho={m.rho:+.3f} "
            f"P@10={m.p_at_10:.2f} P@50={m.p_at_50:.2f} "
            f"R@10={m.r_at_10:.2f} R@50={m.r_at_50:.2f}"
        )
    if args.dump_top:
        sorted_pairs = sorted(scores.items(), key=lambda kv: kv[1].score, reverse=True)
        print(f"\nTop {args.dump_top}:")
        for pid, cs in sorted_pairs[:args.dump_top]:
            print(f"  {pid}: {cs.score:.3f}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.mock_agent:
        agent = MockAgent()
    else:
        provider, _, model = (args.executor or "anthropic:claude-opus-4-7").partition(":")
        if provider != "anthropic":
            raise SystemExit(f"unsupported executor: {args.executor!r}")
        effort = None if args.thinking_effort == "off" else args.thinking_effort
        agent = ClaudeAgent(
            model=model or "claude-opus-4-7",
            max_tokens=args.max_tokens,
            thinking_effort=effort,
        )

    summary = run_loop(
        max_stages=args.max_stages,
        stop_consecutive_fails=args.stop_consecutive_fails,
        stop_rho=args.stop_rho,
        agent=agent,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "ledger"}, indent=2))
    print(f"\n{len(summary['ledger'])} stage records in ledger")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from .orchestrator.state import RunLedger
    ledger = RunLedger()
    if not ledger.records:
        print("No ledger records yet.")
        return 0
    print(f"{len(ledger.records)} stage records | latest stage_index={ledger.stage_index} | fail_streak={ledger.fail_streak()}")
    print()
    for r in ledger.records:
        deltas = " ".join(f"{t}:{d:+.3f}" for t, d in r.deltas.items())
        print(f"  v{r.stage_index:02d} {r.decision:4s} {r.feature_name:30s} {deltas}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="evidence_stacking")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_score = sub.add_parser("score", help="Score all pairs against a given composite manifest")
    p_score.add_argument("--composite", default="v40")
    p_score.add_argument("--dump-top", type=int, default=0)
    p_score.set_defaults(func=_cmd_score)

    p_run = sub.add_parser("run", help="Run the agentic loop")
    p_run.add_argument("--max-stages", type=int, default=20)
    p_run.add_argument("--stop-consecutive-fails", type=int, default=3)
    p_run.add_argument("--stop-rho", type=float, default=0.70)
    p_run.add_argument("--mock-agent", action="store_true")
    p_run.add_argument("--executor", default="anthropic:claude-opus-4-7")
    p_run.add_argument(
        "--thinking-effort",
        choices=["high", "medium", "low", "off"],
        default="high",
        help="Adaptive extended thinking effort. 'off' disables. Default 'high' for best reasoning.",
    )
    p_run.add_argument(
        "--max-tokens",
        type=int,
        default=32_000,
        help="Output token budget. Default 32000.",
    )
    p_run.set_defaults(func=_cmd_run)

    p_status = sub.add_parser("status", help="Print ledger summary")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
