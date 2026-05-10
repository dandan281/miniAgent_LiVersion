# Stage v00: atlas_coexpression

**Parent composite**: `—`  **Decision**: **KEEP**  **Date**: 2026-05-10T14:19:37+00:00
**Agent**: claude-opus-4-7-1m

## Feature definition
- **Name**: `atlas_coexpression`
- **Composite version**: `v40`
- **Required evidence**: ['atlas_coexpression']

## Biological motivation
Class-pair prior + atlas DEG membership bonus. Baseline mirrors §3.1 of the methods doc — a deliberately weak heuristic to be improved via stacking.

## Metrics on holdout
| Target | ρ prev | ρ new | Δρ | P@10 | P@50 | R@10 | R@50 |
|---|---|---|---|---|---|---|---|
| aged_young | +0.000 | +0.252 | +0.252 | 0.300 | 0.700 | 0.040 | 0.467 |
| fibro_muscle | +0.000 | +0.276 | +0.276 | 0.800 | 0.500 | 0.034 | 0.107 |

## Retention rule check
max(Δρ)=+0.276 > 0 and min(Δρ)=+0.252 > -0.050 → **KEEP**

## Misses and limitations
_(baseline — no prior to compare against)_

## Next-stage hypothesis
Add a novelty filter (paper §3.2) — likely largest single-feature win.

## Provenance
- Composite manifest: `composites/v40.json`
- Stage index: 0
- Agent rationale: Initial baseline. Mirrors §3.1 of attached methods doc — class-pair prior plus atlas DEG membership bonus. No tool calls.
