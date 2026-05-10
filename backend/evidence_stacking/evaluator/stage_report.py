"""Stage-report markdown writer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..composites.loader import CompositeManifest
from .metrics import MetricsBundle
from .retention import RetentionDecision


_REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "dev" / "stage_reports"


def write(
    stage_index: int,
    composite: CompositeManifest,
    metrics_per_target: dict[str, MetricsBundle],
    decision: RetentionDecision,
    misses_md: str,
    *,
    feature_name: str,
    biological_motivation: str = "",
    next_hypothesis: str = "",
    agent_model: str = "claude-opus-4-7-1m",
    out_dir: Path | None = None,
    prev_rho: dict[str, float] | None = None,
) -> Path:
    out_dir = out_dir or _REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    name = feature_name.replace("/", "_")
    path = out_dir / f"v{stage_index:02d}_{name}.md"
    keep = "KEEP" if decision.keep else "DROP"

    rows = []
    for target, m in metrics_per_target.items():
        prev = (prev_rho or {}).get(target, 0.0)
        delta = m.rho - prev
        rows.append(
            f"| {target} | {prev:+.3f} | {m.rho:+.3f} | {delta:+.3f} | "
            f"{m.p_at_10:.3f} | {m.p_at_50:.3f} | {m.r_at_10:.3f} | {m.r_at_50:.3f} |"
        )

    md = f"""# Stage v{stage_index:02d}: {feature_name}

**Parent composite**: `{composite.parent or '—'}`  **Decision**: **{keep}**  **Date**: {ts}
**Agent**: {agent_model}

## Feature definition
- **Name**: `{feature_name}`
- **Composite version**: `{composite.version}`
- **Required evidence**: {[ref.name for ref in composite.features]}

## Biological motivation
{biological_motivation or "_(agent fills in)_"}

## Metrics on holdout
| Target | ρ prev | ρ new | Δρ | P@10 | P@50 | R@10 | R@50 |
|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## Retention rule check
{decision.reason} → **{keep}**

## Misses and limitations
{misses_md or "_(agent fills in)_"}

## Next-stage hypothesis
{next_hypothesis or "_(agent fills in)_"}

## Provenance
- Composite manifest: `composites/{composite.version}.json`
- Stage index: {stage_index}
- Agent rationale: {composite.agent_rationale or "_(none)_"}
"""
    path.write_text(md)
    return path
