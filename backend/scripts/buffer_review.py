"""
experience_buffer.jsonl review utility.

Prints a ranked summary of all iterations logged to the experience buffer:
candidate_id, receptor pair, linker, phenotype score, chain_soundness,
composite reward, tier, verdict.

Useful when a human (or future automated step) needs to audit which
candidates the RL loop has scored, where they landed, and whether anything
hit the TOP_K_DESIGN tier.

Usage:
    python scripts/buffer_review.py
    python scripts/buffer_review.py --tier TOP_K_DESIGN --top 10
    python scripts/buffer_review.py --mode full   # only agent-driven runs
    python scripts/buffer_review.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
BUFFER = BACKEND / "knowledge" / "experience_buffer.jsonl"


TIER_RANK = {
    "TOP_K_DESIGN":         0,
    "MIDDLE_HUMAN_REVIEW":  1,
    "BOTTOM_LOG_ONLY":      2,
    "INCOHERENT_LOG_ONLY":  3,
}


def load_buffer(path: Path = BUFFER) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] skipping malformed line: {e}", file=sys.stderr)
    return records


def summarize(record: dict) -> dict:
    cand = record.get("candidate", {})
    phen = record.get("phenotype", {}) or {}
    dec = record.get("decision", {}) or {}
    return {
        "iteration":       record.get("iteration"),
        "timestamp":       record.get("timestamp"),
        "mode":            record.get("mode", "?"),
        "candidate_id":    cand.get("candidate_id"),
        "receptor_A":      cand.get("receptor_A"),
        "receptor_B":      cand.get("receptor_B"),
        "linker":          cand.get("linker"),
        "phenotype_score": phen.get("phenotype_score"),
        "verdict":         phen.get("verdict"),
        "reference":       phen.get("reference_label"),
        "chain_soundness": cand.get("chain_soundness"),
        "track_a":         dec.get("components", {}).get("track_a"),
        "track_b":         dec.get("components", {}).get("track_b"),
        "track_c":         dec.get("components", {}).get("track_c"),
        "reward":          dec.get("reward"),
        "tier":            dec.get("tier"),
        "n_predicted_up":  phen.get("n_predicted_up"),
        "n_predicted_down": phen.get("n_predicted_down"),
        "notes":           record.get("notes", ""),
    }


def filter_records(rows: list[dict], *, tier: str | None, mode: str | None,
                   min_reward: float | None, top: int | None) -> list[dict]:
    out = list(rows)
    if tier:
        out = [r for r in out if r["tier"] == tier]
    if mode:
        out = [r for r in out if r["mode"] == mode]
    if min_reward is not None:
        out = [r for r in out if (r["reward"] or 0.0) >= min_reward]
    out.sort(
        key=lambda r: (
            TIER_RANK.get(r["tier"] or "", 99),
            -(r["reward"] or -999),
        )
    )
    if top:
        out = out[:top]
    return out


def format_table(rows: list[dict]) -> str:
    if not rows:
        return "(empty)"
    cols = [
        ("rank",       3),
        ("candidate_id",        32),
        ("recA→recB",  18),
        ("linker",     12),
        ("mode",        6),
        ("phen",        7),
        ("chain",       6),
        ("reward",      8),
        ("tier",       21),
        ("verdict",    18),
    ]
    header = "  ".join(f"{c[0]:>{c[1]}}" if c[0] in ("rank","phen","chain","reward") else f"{c[0]:<{c[1]}}" for c in cols)
    lines = [header, "-" * len(header)]
    for i, r in enumerate(rows, 1):
        recA = r.get("receptor_A") or "?"
        recB = r.get("receptor_B") or "?"
        pair = f"{recA}+{recB}"[:18]
        lk = (r.get("linker") or "")[:12]
        cid = (r.get("candidate_id") or "")[:32]
        phen = r.get("phenotype_score")
        chain = r.get("chain_soundness")
        reward = r.get("reward")
        tier = (r.get("tier") or "")[:21]
        verdict = (r.get("verdict") or "")[:18]
        mode = (r.get("mode") or "?")[:6]
        line = (
            f"{i:>3}  "
            f"{cid:<32}  "
            f"{pair:<18}  "
            f"{lk:<12}  "
            f"{mode:<6}  "
            f"{(f'{phen:+.4f}' if phen is not None else '   --   '):>7}  "
            f"{(f'{chain:.3f}' if chain is not None else '  --  '):>6}  "
            f"{(f'{reward:+.4f}' if reward is not None else '   --   '):>8}  "
            f"{tier:<21}  "
            f"{verdict:<18}"
        )
        lines.append(line)
    return "\n".join(lines)


def tier_distribution(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        t = r.get("tier") or "UNKNOWN"
        counts[t] = counts.get(t, 0) + 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--buffer", type=Path, default=BUFFER)
    ap.add_argument("--tier", choices=list(TIER_RANK.keys()) + [None], default=None)
    ap.add_argument("--mode", choices=["score_only", "full", None], default=None)
    ap.add_argument("--min-reward", type=float, default=None)
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--json", type=Path, default=None,
                    help="Write filtered rows as JSON to this path")
    args = ap.parse_args()

    raw = load_buffer(args.buffer)
    rows = [summarize(r) for r in raw]
    filtered = filter_records(rows, tier=args.tier, mode=args.mode,
                              min_reward=args.min_reward, top=args.top)

    print(f"buffer: {args.buffer}")
    print(f"  total iterations: {len(rows)}")
    counts = tier_distribution(rows)
    print(f"  tier distribution: {counts}")
    if args.tier or args.mode or args.min_reward is not None or args.top:
        print(f"  filtered: {len(filtered)} (tier={args.tier}  mode={args.mode}  "
              f"min_reward={args.min_reward}  top={args.top})")
    print()
    print(format_table(filtered))

    if args.json:
        with open(args.json, "w") as f:
            json.dump(filtered, f, indent=2, default=str)
        print(f"\n[json] wrote {len(filtered)} records to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
