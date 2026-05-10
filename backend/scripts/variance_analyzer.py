"""
Inter-run variance analyzer.

Reads experience_buffer.jsonl and groups records by (receptor_A, receptor_B,
linker). For pairs that have been run multiple times in mode='full', reports:
  - Number of independent runs
  - Phenotype score: min/median/max, range
  - Chain soundness: min/median/max
  - Gene prediction stability: Jaccard between successive runs' predicted_up
    and predicted_down sets
  - Adaptor classification stability (if available)

This quantifies the DeepSeek non-determinism that motivates the
multi_iter_consensus.py approach.

Usage:
    python scripts/variance_analyzer.py
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
BUFFER = BACKEND / "knowledge" / "experience_buffer.jsonl"
AGENT_OUTPUTS = BACKEND / "knowledge" / "agent_outputs"


def load_full_runs() -> list[dict]:
    if not BUFFER.exists():
        return []
    rows = []
    with open(BUFFER) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("mode") != "full":
                continue
            rows.append(r)
    return rows


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def main() -> int:
    rows = load_full_runs()
    if not rows:
        print("No mode=full records yet. Run with `--mode full` first.")
        return 0

    # Group by (recA, recB, linker_normalized)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        cand = r.get("candidate", {})
        recA = (cand.get("receptor_A") or "").upper()
        recB = (cand.get("receptor_B") or "").upper()
        linker = (cand.get("linker") or "").split()[0]  # crude normalization
        # Sort pair so (A,B) and (B,A) collide
        pair = tuple(sorted([recA, recB]))
        key = (pair[0], pair[1], linker)
        groups[key].append(r)

    print(f"\nfound {len(rows)} agent-driven runs across {len(groups)} unique pair+linker groups")

    multi_run_groups = [(k, v) for k, v in groups.items() if len(v) >= 2]
    print(f"groups with ≥2 runs (variance analyzable): {len(multi_run_groups)}")
    if not multi_run_groups:
        print("\n(no pair has been run more than once via --mode full)")
        print("To populate: run the same pair through `python scripts/rl_loop.py --mode full --iterations 3`")
        return 0

    print("\n" + "=" * 80)
    for key, runs in multi_run_groups:
        recA, recB, linker = key
        print(f"\n## {recA}+{recB} / {linker}    n={len(runs)}")
        phens = [(r.get("phenotype", {}) or {}).get("phenotype_score") for r in runs]
        phens = [p for p in phens if p is not None]
        if phens:
            print(f"  phenotype: min={min(phens):+.4f}  median={statistics.median(phens):+.4f}  max={max(phens):+.4f}  range={max(phens)-min(phens):.4f}")
            if len(phens) >= 2:
                print(f"  stdev:     {statistics.stdev(phens):.4f}")

        chains = []
        for r in runs:
            cand = r.get("candidate", {}) or {}
            c = cand.get("chain_soundness")
            if c is not None:
                chains.append(c)
        if chains:
            print(f"  chain:     min={min(chains):.4f}  median={statistics.median(chains):.4f}  max={max(chains):.4f}")

        # Gene set Jaccard between consecutive runs
        ups, downs = [], []
        for r in runs:
            cand = r.get("candidate", {}) or {}
            ups.append(set(g.upper() for g in cand.get("predicted_up", []) if g))
            downs.append(set(g.upper() for g in cand.get("predicted_down", []) if g))

        if len(ups) >= 2:
            j_ups = []
            for i in range(len(ups) - 1):
                j_ups.append(jaccard(ups[i], ups[i+1]))
            j_downs = []
            for i in range(len(downs) - 1):
                j_downs.append(jaccard(downs[i], downs[i+1]))
            print(f"  Jaccard predicted_up   between consecutive runs: {[f'{j:.3f}' for j in j_ups]}")
            print(f"  Jaccard predicted_down between consecutive runs: {[f'{j:.3f}' for j in j_downs]}")

            # Consensus genes (in ALL runs)
            consensus_up   = set.intersection(*ups) if ups else set()
            consensus_down = set.intersection(*downs) if downs else set()
            print(f"  consensus UP   (all {len(runs)} runs): {sorted(consensus_up) if consensus_up else '(none)'}")
            print(f"  consensus DOWN (all {len(runs)} runs): {sorted(consensus_down) if consensus_down else '(none)'}")

    print("\n" + "=" * 80)
    print(f"\n[summary] {len(multi_run_groups)} pair(s) have been run multiple times.")
    print("[summary] Use multi_iter_consensus.py to systematically run N iterations and aggregate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
