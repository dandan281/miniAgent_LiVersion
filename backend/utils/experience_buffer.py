"""Experience buffer reader for the muscle-rejuvenation RL loop.

Closes the read side of the loop: every agent iteration consults
`backend/knowledge/experience_buffer.jsonl` BEFORE invoking the agent. This
lets the agent (1) learn from prior wins/losses by surfacing them as a
"prior runs" context block, and (2) skip re-running pairs whose score is
already deterministically computable from a stored prediction.

Public API
----------
- :func:`load_buffer(path=None) -> list[dict]` — read all records.
- :func:`top_k_rejuvenating(records, k=3) -> list[dict]` — top by reward.
- :func:`bottom_k_failures(records, k=2) -> list[dict]` — bottom by reward.
- :func:`pair_key(receptor_A, receptor_B, linker=None) -> str` — order-invariant key.
- :func:`lookup_by_pair(records, receptor_A, receptor_B, linker=None) -> dict|None`
  — best record matching this pair (highest reward), or None.
- :func:`format_priors_block(top, bottom) -> str` — markdown block to
  prepend to the agent prompt.
- :func:`format_pair_cache_block(record) -> str` — concise summary of an
  exact-pair cache hit.

The schema this module assumes (verified against records appended by
`scripts/rl_loop.py`):

    {
      "iteration": int,
      "mode": "score_only" | "full",
      "candidate": {
        "candidate_id": str,
        "receptor_A": str,
        "receptor_B": str,
        "linker": str,
        "predicted_up": [...],
        "predicted_down": [...],
        "biased_output": {transphosphorylation_adaptors, cis_adaptors, excluded_adaptors},
        "chain_soundness": float,
      },
      "phenotype": {"phenotype_score": float, "verdict": str},
      "decision": {"reward": float, "tier": str, "components": {...}}
    }

Older records may be missing `decision` or `agent_prediction`; those are
handled gracefully (records without a usable reward are filtered out of
the priors block but are still indexed for cache lookups).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Default buffer path resolved at import time.
_DEFAULT_BUFFER_PATH = (
    Path(__file__).resolve().parent.parent / "knowledge" / "experience_buffer.jsonl"
)

# Tiers we treat as "win" / "fail" for the priors block.
_WIN_TIERS = {"TOP_K_DESIGN"}
_INTERMEDIATE_TIERS = {"MIDDLE_HUMAN_REVIEW"}
_FAIL_TIERS = {"BOTTOM_LOG_ONLY", "INCOHERENT_LOG_ONLY"}


def load_buffer(path: Path | None = None) -> list[dict[str, Any]]:
    """Read all JSONL records. Skips malformed lines (does not raise)."""
    p = Path(path) if path else _DEFAULT_BUFFER_PATH
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


def _reward(rec: dict) -> Optional[float]:
    dec = rec.get("decision") or {}
    r = dec.get("reward")
    if isinstance(r, (int, float)):
        return float(r)
    # Fallback: phenotype score (older records before track_b/track_a5)
    ph = (rec.get("phenotype") or {}).get("phenotype_score")
    return float(ph) if isinstance(ph, (int, float)) else None


def _tier(rec: dict) -> Optional[str]:
    dec = rec.get("decision") or {}
    t = dec.get("tier")
    return str(t) if t else None


def pair_key(
    receptor_A: str,
    receptor_B: str,
    linker: Optional[str] = None,
    *,
    order_invariant: bool = True,
) -> str:
    """Hash key for a (rA, rB, linker) triple. Order-invariant by default
    because forced-proximity dimers are symmetric in receptor identity."""
    a, b = receptor_A.strip().upper(), receptor_B.strip().upper()
    if order_invariant and a > b:
        a, b = b, a
    if linker:
        return f"{a}|{b}|{linker.strip()}"
    return f"{a}|{b}"


def _pair_key_from_record(rec: dict, *, include_linker: bool = True) -> Optional[str]:
    cand = rec.get("candidate") or {}
    ra, rb = cand.get("receptor_A"), cand.get("receptor_B")
    if not ra or not rb:
        return None
    return pair_key(ra, rb, cand.get("linker") if include_linker else None)


def top_k_rejuvenating(records: list[dict], k: int = 3) -> list[dict]:
    """Top-k records by reward, requires REJUVENATING verdict + numeric reward.
    De-duplicated by (rA, rB) so a single pair doesn't dominate the list."""
    scored = [(rec, r) for rec in records if (r := _reward(rec)) is not None]
    rejuvenating = [
        (rec, r) for rec, r in scored
        if (rec.get("phenotype") or {}).get("verdict") == "REJUVENATING"
    ]
    rejuvenating.sort(key=lambda pair: pair[1], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for rec, _r in rejuvenating:
        key = _pair_key_from_record(rec, include_linker=False)
        if key is None or key in seen:
            continue
        seen.add(key)
        out.append(rec)
        if len(out) >= k:
            break
    return out


def bottom_k_failures(records: list[dict], k: int = 2) -> list[dict]:
    """Bottom-k records by reward where tier indicates failure."""
    scored = [(rec, r) for rec in records if (r := _reward(rec)) is not None]
    failures = [
        (rec, r) for rec, r in scored
        if _tier(rec) in _FAIL_TIERS
    ]
    failures.sort(key=lambda pair: pair[1])
    seen: set[str] = set()
    out: list[dict] = []
    for rec, _r in failures:
        key = _pair_key_from_record(rec, include_linker=False)
        if key is None or key in seen:
            continue
        seen.add(key)
        out.append(rec)
        if len(out) >= k:
            break
    return out


def lookup_by_pair(
    records: list[dict],
    receptor_A: str,
    receptor_B: str,
    linker: Optional[str] = None,
    *,
    require_full_mode: bool = True,
    min_reward: Optional[float] = None,
) -> Optional[dict]:
    """Return the best (highest-reward) prior record matching this pair.

    By default only `mode == 'full'` records are considered cache-eligible
    because score_only records use the hand-curated H2F seed and shouldn't
    short-circuit a real agent run. Pass ``require_full_mode=False`` to
    include score_only records as well (useful for lossy fast-paths).
    """
    target_key = pair_key(receptor_A, receptor_B, linker)
    candidates: list[tuple[dict, float]] = []
    for rec in records:
        rec_key = _pair_key_from_record(rec, include_linker=bool(linker))
        if rec_key != target_key:
            continue
        if require_full_mode and rec.get("mode") != "full":
            continue
        r = _reward(rec)
        if r is None:
            continue
        if min_reward is not None and r < min_reward:
            continue
        candidates.append((rec, r))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return candidates[0][0]


def _summarize_record(rec: dict, *, lead: str) -> str:
    cand = rec.get("candidate") or {}
    ph = rec.get("phenotype") or {}
    dec = rec.get("decision") or {}
    pair = f"{cand.get('receptor_A')}+{cand.get('receptor_B')}"
    linker = cand.get("linker") or "?"
    reward = dec.get("reward")
    tier = dec.get("tier") or "?"
    verdict = ph.get("verdict") or "?"
    up = (cand.get("predicted_up") or [])[:8]
    down = (cand.get("predicted_down") or [])[:8]
    bias = cand.get("biased_output") or {}
    excluded = (bias.get("excluded_adaptors") or [])[:5]
    transp = (bias.get("transphosphorylation_adaptors") or [])[:5]
    reward_str = f"{reward:+.3f}" if isinstance(reward, (int, float)) else "n/a"
    parts = [
        f"- **{lead}** {pair} (linker={linker}) → reward={reward_str} | tier={tier} | verdict={verdict}",
    ]
    if transp:
        parts.append(f"    transphos adaptors: {', '.join(transp)}")
    if excluded:
        parts.append(f"    excluded adaptors: {', '.join(excluded)}")
    if up:
        parts.append(f"    top predicted_up: {', '.join(up)}")
    if down:
        parts.append(f"    top predicted_down: {', '.join(down)}")
    return "\n".join(parts)


def format_priors_block(
    top: list[dict],
    bottom: list[dict],
) -> str:
    """Markdown context block to prepend to the agent's per-iteration prompt."""
    if not top and not bottom:
        return ""
    lines: list[str] = ["## PRIOR EXPERIENCE — read before reasoning",
                         "Past iterations of this RL loop have produced the following calibration data. Use the patterns to inform your reasoning, especially the gene-direction signature; do NOT just copy past predictions.\n"]
    if top:
        lines.append("### Past wins (what scored REJUVENATING)")
        for i, rec in enumerate(top):
            lines.append(_summarize_record(rec, lead=f"Win {i+1}"))
        lines.append("")
    if bottom:
        lines.append("### Past failures (what scored as BOTTOM_LOG_ONLY or INCOHERENT)")
        for i, rec in enumerate(bottom):
            lines.append(_summarize_record(rec, lead=f"Fail {i+1}"))
        lines.append("")
    lines.append("**Use these patterns** to inform Step 3c (gene direction) and Step 4 (chain soundness). Pairs that scored INCOHERENT typically had broken adaptor coverage or invalid receptor classes; do not repeat the same mistake. Wins consistently put muscle structural genes (MYH/ACTA/TNNT/MYL) in predicted_up and aged IEGs (EGR1/JUN/IL32/CDKN2A) in predicted_down.\n")
    return "\n".join(lines)


def format_pair_cache_block(record: dict) -> str:
    """Concise human-readable note when we cache-hit on the exact pair."""
    cand = record.get("candidate") or {}
    ph = record.get("phenotype") or {}
    dec = record.get("decision") or {}
    pair = f"{cand.get('receptor_A')}+{cand.get('receptor_B')}"
    return (
        f"[experience-buffer] cache HIT for pair={pair} linker={cand.get('linker')!r}: "
        f"prior reward={dec.get('reward'):.4f} tier={dec.get('tier')} "
        f"verdict={ph.get('verdict')}"
        if isinstance(dec.get("reward"), (int, float))
        else f"[experience-buffer] cache HIT for pair={pair}; reward unavailable."
    )


__all__ = [
    "load_buffer",
    "top_k_rejuvenating",
    "bottom_k_failures",
    "pair_key",
    "lookup_by_pair",
    "format_priors_block",
    "format_pair_cache_block",
]
