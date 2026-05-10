# Master Rejuvenation Plan — v2 (Evidence-Stacking Pivot)

> **Status**: ACTIVE as of 2026-05-10. Supersedes `master_rejuvenation_rl_plan.md` (v1, RL loop + 4-track reward + Superbio).
> **Pipeline**: Iterative agentic evidence stacking, modeled on Novokine Bispecific Receptor Pair Ranking methods (attached).
> **Owner**: liqigong41@gmail.com

---

## Revision history

| Rev | Date | Notes |
|---|---|---|
| v2.0 | 2026-05-10 | Initial v2: pivot away from RL/Superbio. New 59-receptor universe (1,711 pairs), evidence-stacking orchestrator, Claude Opus 4.7 1M executor, Spearman-on-holdout retention rule. |

---

## Part 1 — Why v2

### What v1 did

v1 was an RL loop scoring novokine pairs against a 4-track composite reward (Track A atlas overlap + B chain-soundness + C LINCS + A.5 scGPT). 79-run overnight sweep produced top candidates EGFR+IL6ST, ERBB4+INSR, INSR+IL6ST. It depended on Superbio.ai for structure prediction (Boltz-2/Protenix server-side broken; only AF2 working).

### What changed

Three forces drove the pivot:

1. **Superbio is unreliable** — 9 of 11 structure-prediction jobs failed server-side. Boltz-2 and Protenix output `*.tar.gz` not found errors at ~40s consistently. Cannot ship a pipeline gated on a broken upstream.
2. **The methodology in the attached novokine ranking paper is better suited to our problem** than RL — it builds an interpretable equal-weight additive composite by adding ONE feature at a time, evaluating ΔAUROC, writing a "misses and limitations" analysis, and proposing the next feature. Each stage is auditable and the final score is decomposable into named contributions.
3. **The agent should drive everything end-to-end** — not just propose candidates. v2 has Claude Opus 4.7 1M as full-pipeline orchestrator: it proposes features, queries APIs, computes scores, fits the composite, evaluates against held-out atlas reward, writes the misses analysis, decides keep/drop.

### What v2 does

For 1,711 unordered receptor pairs from a 59-receptor universe, v2 iteratively builds a composite scorer. At each stage the agent:

1. Reads the prior stage report (current ρ on holdout, top false-positives, top false-negatives).
2. Proposes ONE new feature with biological motivation and tool-call plan.
3. Implements the feature (writes a Python class to disk).
4. Drives the 28 LangChain biology tools to gather evidence for all 1,711 pairs (deduping vs. cache).
5. Computes scores, extends the composite, evaluates Spearman ρ on a 30% deterministic holdout for both target phenotypes.
6. Writes a stage report mirroring §3.X of the attached methods doc.
7. Decides keep/drop via the retention rule.

Stops when 3 consecutive features fail or both targets reach ρ ≥ 0.70 on holdout.

---

## Part 2 — Scientific constraints (carried forward from v1)

These survive the pivot intact:

- **Forced-proximity biased signaling**, not pathway union. Output determined by transphosphorylation geometry at co-clustered intracellular domains.
- **H2F is positive control** (HER2 + FGFR1c → MAPK/AKT on, PLCγ off). Must appear in top decile of any ranking.
- **Linker geometry is a first-class action variable** (per Edman 2024). Five linker options per pair. v2 treats linker choice as a feature dimension; composite scoring is per-(pair, linker) for now (1,711 × 5 = 8,555 scoring units), reduced to per-pair via best-linker max for retention evaluation.
- **gp130 family pairings dominate** — IL6ST/LIFR/OSMR + RTK appears in 9 of v1's top 20. v2 retains this as a sanity check on stage outputs.
- **MAPK-driven IEGs (EGR1, FOS, JUN, MYC)** are aged-tissue markers. Any feature that predicts them as upregulated by a "rejuvenating" novokine fails the bio-sanity gate.

---

## Part 3 — Architecture

### 3.1 Module layout

```
backend/evidence_stacking/
├── pair.py                          ReceptorPair dataclass
├── receptor_universe.py             loads YAML, enumerates 1,711 pairs
├── evidence/
│   ├── envelope.py                  PairEvidence schema
│   ├── store.py                     on-disk cache (knowledge/evidence_cache/)
│   └── gather.py                    agentic tool dispatch + dedup
├── features/
│   ├── base.py                      Feature ABC
│   ├── registry.py                  @register decorator
│   ├── atlas_coexpression.py        v40 baseline (migrated from atlas_seeded_candidates)
│   ├── novelty_filter.py            v4 (PubMed + BioGRID PPI penalty)
│   ├── pathway_coactivation.py      v5+PW
│   ├── kegg_antifibrosis.py         v6 (likely DROPPED, mirrors paper)
│   ├── fibro_enrichment.py          v7
│   └── paper_acvrl1_fgfr.py         v8
├── composites/
│   ├── loader.py                    parses vN.json
│   ├── composite.py                 equal-weight additive + min-max normalize
│   └── v{40,4,5_pw,6,7,8}.json      stage manifests (immutable once committed)
├── evaluator/
│   ├── atlas_reward.py              builds aged_young & fibro_muscle reward TSVs
│   ├── synthesize_fibro_signal.py   one-time fibro_muscle target builder
│   ├── metrics.py                   Spearman ρ, P@K, R@K, top-disagreements
│   ├── retention.py                 keep/drop rule
│   └── stage_report.py              writes dev/stage_reports/v{NN}_{feature}.md
├── orchestrator/
│   ├── loop.py                      main agent loop
│   ├── prompts.py                   PROPOSE_FEATURE, WRITE_MISSES, DECIDE_STOP
│   ├── feature_writer.py            agent-spec → Python file
│   └── state.py                     RunLedger (knowledge/dev/v2_run_ledger.jsonl)
└── cli.py                           python -m backend.evidence_stacking.cli
```

### 3.2 Feature contract

Features are pure transforms over a per-pair `PairEvidence` dict. Tool calls happen in the separate evidence-gathering pass, not in `compute()`. This makes features deterministic, testable, and cacheable.

```python
class Feature(ABC):
    name: str
    version: str
    description: str
    required_evidence: list[str]        # keys read from PairEvidence

    def compute(self, pair: ReceptorPair, ev: PairEvidence) -> float | None: ...
    def normalize(self, scores: dict[str, float]) -> dict[str, float]:
        # default: min-max [0,1]; None values map to 0.0 with provenance flag
    def provenance(self) -> dict: ...
    def cache_key(self, pair: ReceptorPair) -> str:
        return f"{self.name}@{self.version}::{pair.pair_id}"
```

### 3.3 Composite manifest schema

`composites/vN.json`:

```json
{
  "version": "v5_pw",
  "parent": "v4",
  "stage_index": 3,
  "weights": "equal",
  "features": [
    {"name": "atlas_coexpression", "version": "1.0"},
    {"name": "novelty_filter", "version": "1.0"},
    {"name": "pathway_coactivation", "version": "1.0"}
  ],
  "agent_rationale": "...",
  "rho_at_commit": {"aged_young": 0.42, "fibro_muscle": 0.38}
}
```

Manifests are immutable once a stage report ships. Drafts under `composites/_drafts/`.

### 3.4 Retention rule

Per stage:

```
Δρ_target = ρ_new[target] − ρ_prev[target]   for each of {aged_young, fibro_muscle}
KEEP iff   max(Δρ) > 0   AND   min(Δρ) > −0.05
```

Mirrors the methods paper's "improves at least one label set without reducing the other by more than 0.05".

### 3.5 Stop rule

```
STOP iff   fail_streak ≥ 3   OR   (ρ_aged_young ≥ 0.70 AND ρ_fibro_muscle ≥ 0.70)   OR   stage_idx ≥ max_stages
```

Default `max_stages=20` for cost safety. Per the autonomous-long-runs preference, 5–7 hour runs are authorized.

### 3.6 Evidence cache

Per-pair cache at `backend/knowledge/evidence_cache/<pair_id>.json` (sharded by first letter for filesystem hygiene). Keyed by `(feature.version, pair_id)` — bumping a feature version triggers re-gather only for that feature's required evidence keys.

### 3.7 Holdout split

Deterministic: `hash(pair_id) % 10 < 3` → 30% holdout (~513 pairs). Same split for both target signals. Rebuildable, no random seed needed.

---

## Part 4 — Stage progression

The agent decides feature order autonomously, but is seeded with the paper-aligned sequence so the first 6 stages parallel §3.1 → §3.7 of the methods doc:

| Stage | Feature | Tools | Mirrors |
|---|---|---|---|
| v40 | `atlas_coexpression` | `local_atlas_query` | §3.1 BMP-arm heuristic baseline |
| v4 | `novelty_filter` | `ncbi_eutils`, `biogrid_orcs` | §3.2 (paper's biggest single-feature win, +0.32 AUROC) |
| v5+PW | `pathway_coactivation` | `reactome_api`, `omnipath_api` | §3.3 |
| v6 | `kegg_antifibrosis` | `reactome_api` (KEGG via Reactome) | §3.5 (mixed; degrades aged_young — likely DROPPED, this is fine) |
| v7 | `fibro_enrichment` | `cellxgene_expression`, `local_atlas_query` | §3.6 |
| v8 | `paper_acvrl1_fgfr` | `search_knowledge_base` (Keshri 2026, Expòsit 2025) | §3.7 |

**After v8 the agent runs unconstrained** — proposed features come from its analysis of stage reports.

### Stage report template

Path: `backend/knowledge/dev/stage_reports/v{NN}_{feature_name}.md`

```markdown
# Stage v{N}: {feature_name}

**Parent composite**: v{N-1}    **Decision**: KEEP | DROP    **Date**: {iso}
**Agent**: claude-opus-4-7-1m

## Feature definition
Name / version / required_evidence / one-paragraph compute description

## Biological motivation
2–4 paragraphs, agent-written, must cite at least one tool result

## Metrics on holdout
| Target | ρ prev | ρ new | Δρ | P@10 | P@50 | R@10 | R@50 |
|---|---|---|---|---|---|---|---|
| aged_young   | … | … | … | … | … | … | … |
| fibro_muscle | … | … | … | … | … | … | … |

## Retention rule check
max(Δρ) = …, min(Δρ) = …; rule satisfied → KEEP|DROP

## Misses and limitations
Top-5 disagreements per target. Per-feature contribution table. Mechanistic
explanation. Mirrors the paper's "Misses and limitations at vN" sections.

## Next-stage hypothesis
Seed for stage N+1, read by next iteration.

## Provenance
Composite manifest, feature source, evidence cache stats, tool call counts.
```

---

## Part 5 — Two-phenotype unified scoring

v2 ranks against TWO target signals; features are kept if they help either without hurting the other.

### 5.1 `aged_young` target

Existing Track A `phenotype_score` from `muscle_atlas_DE_v2_consensus.json` (the v2 multi-source consensus atlas built 2026-05-05). Computed once for all 1,711 pairs; cached at `backend/knowledge/labels/v2_atlas_reward_aged_young.tsv`.

### 5.2 `fibro_muscle` target

NEW. Built by `evaluator/synthesize_fibro_signal.py` from:

- `backend/knowledge/raw_degs/fibroblast/` — fibroblast-up genes a transdifferentiator should DOWN-regulate
- `backend/knowledge/raw_degs/muscle/` — muscle-up genes a transdifferentiator should UP-regulate

Fisher-overlap math identical to Track A; gene sets differ. Cached at `backend/knowledge/labels/v2_atlas_reward_fibro_muscle.tsv`.

### 5.3 Why no wet-lab labels

The attached paper used real desmin tSKM screen data (99 labeled pairs, AUROC). We don't have wet-lab data for either phenotype. Atlas-derived synthetic targets are the gate metric until such data lands. When it does, drop a TSV under `backend/knowledge/labels/wetlab_*.tsv` and add a third track to the retention rule (weight 2.0 vs. 1.0 for the synthetic targets).

---

## Part 6 — Receptor universe v2

`backend/knowledge/receptor_universe_v2.yaml`:

```yaml
version: 2
n_receptors: 59
n_pairs: 1711
classes:
  bmp_type_i:        # BMP-arm type-I receptors
    members: [ACVRL1, BMPR1A, BMPR1B, ACVR1]
  bmp_type_ii:       # BMP-arm type-II receptors
    members: [BMPR2, ACVR2A, ACVR2B]
  tgfb:              # TGF-β arm
    members: [TGFBR1, TGFBR2]
  rtk:               # Growth factor receptors
    members: [EGFR, ERBB2, ERBB3, ERBB4,
              FGFR1, FGFR2, FGFR3, FGFR4,
              IGF1R, IGF2R, INSR,
              NTRK1, NTRK2, NTRK3,
              PDGFRA, PDGFRB,
              MET, KIT, FLT1, KDR, RET,
              LEPR, GHR]
  cytokine_adhesion: # Cytokine + adhesion + JAK-STAT pairs
    members: [IL6ST, IL2RG, OSMR, LIFR, IL6R,
              IFNAR1, IFNAR2,
              TNFRSF1A, TNFRSF1B,
              DDR1, DDR2,
              ITGA7, ITGB1, ITGAV,
              PLAUR, CD44, NOTCH1, NOTCH2, ROBO1]
```

`receptor_universe.py` validates `sum(len(c.members)) == 59` and `n_pairs == 59*58/2 == 1711` at load. UniProt accessions and ECD lengths are populated lazily via `uniprot_api` tool on first reference, cached at `backend/storage/receptor_cache.json`.

---

## Part 7 — What gets retired

Moved to `backend/legacy/` (preserve, don't `rm` — the 79-run experience buffer is too valuable to lose):

- `backend/scripts/rl_loop.py`, `atlas_seeded_candidates.py`, `generate_dossiers.py`
- `backend/utils/superbio_submit.py`, `superbio_predict.py`
- `backend/tools/superbio_tool.py`, `alphafold3_tool.py`, `scgpt_phenotype_tool.py`, `scgpt_programs_tool.py`, `clue_api_tool.py`
- `workflows/{alphafold2,boltz2,protenix}.yaml` + their runners
- `workflows/engines/superbio/` (entire dir)

**NOT retired**: `backend/utils/phenotype_checkpoint.py` and `chain_soundness.py`. Their score functions get wrapped as features in `features/atlas_coexpression.py` and `features/chain_soundness.py` — they become single-feature contributors in the composite instead of dedicated reward tracks.

---

## Part 8 — Implementation order

Numbered for execution. Each step gates the next:

1. **Carve out `backend/legacy/`** with one-line README pointing here.
2. **Write `receptor_universe_v2.yaml`** — 59 receptors, validate `n_pairs == 1711`.
3. **Build `evidence_stacking/` skeleton** — base, pair, registry, evaluator scaffolding (no features yet).
4. **Generate atlas reward caches** — run `synthesize_fibro_signal.py` once + dump aged_young rewards to TSV.
5. **Write v40 baseline feature** (`atlas_coexpression` migrated from `atlas_seeded_candidates.py`). Verify it scores all 1,711 pairs.
6. **Write `composites/v40.json`** + run evaluator on baseline. Establish ρ_aged_young and ρ_fibro_muscle starting numbers.
7. **Swap executor model** in `backend/runtime/model_factory.py` to Claude Opus 4.7 1M.
8. **Wire orchestrator loop** — `loop.py` end-to-end, dry-run with mock agent first.
9. **First live agent run** — `--max-stages 1` smoke test; verify proposal → implementation → score → report flow.
10. **Full multi-stage run** — `--max-stages 20`. Authorized 5–7 hour autonomous run.
11. **Update SKILL.md + retire v1 plan** — final docs alignment.

---

## Part 9 — Verification (smoke tests)

```bash
# Universe loads + enumerates 1,711 pairs
python -c "from backend.evidence_stacking.receptor_universe import load; \
           u = load(); assert len(list(u.pairs())) == 1711"

# Baseline feature scores all pairs without crashing
python -m backend.evidence_stacking.cli score --composite v40

# Atlas reward caches build (both targets)
python -m backend.evidence_stacking.evaluator.synthesize_fibro_signal
python -m backend.evidence_stacking.evaluator.atlas_reward --build aged_young

# Single-stage agent run, mocked
python -m backend.evidence_stacking.cli run --max-stages 1 --mock-agent

# Full live run
python -m backend.evidence_stacking.cli run --max-stages 20 \
    --executor anthropic:claude-opus-4-7-1m
```

### Success criteria

- v40 baseline produces non-degenerate ρ on holdout (>0.10 on at least one target — anything is acceptable for a 1-feature heuristic).
- Final composite achieves ρ ≥ 0.50 on at least one target.
- Stage reports exist for every stage attempted (kept AND rejected).
- H2F-like positive controls (HER2/ERBB2 + FGFR1) appear in top-50 of final ranking.
- IL6ST + RTK pairs appear in top-100 (per the v1 IL6ST winning pattern).
- `grep -ri superbio backend/ workflows/ | grep -v legacy` returns empty.

---

## Part 10 — Open questions

1. **Spearman ρ vs P@K as primary gate metric** — plan picks ρ; revisit after v40 baseline numbers land.
2. **Receptor universe UniProt accessions** — populated lazily; flag for human review if any symbol is ambiguous (NTRK1 vs TRKA).
3. **79-run experience buffer reuse** — keep readable. Optional v2 enhancement: warm-start v40 baseline with high-reward v1 entries.
4. **Skills layer cleanup** — `novokine_validation`, `novokine_design_handoff` may need updates. v2 orchestrator doesn't call skills directly so deferred.
5. **When wet-lab data lands** — third label track L3 with weight 2.0; `backend/knowledge/labels/wetlab_*.tsv` is the drop-in slot.

---

## Appendix A — File map

| Domain | New | Modified | Retired |
|---|---|---|---|
| Plans | `master_rejuvenation_plan_v2.md` (this file) | `master_rejuvenation_rl_plan.md` (banner) | — |
| Receptor universe | `knowledge/receptor_universe_v2.yaml` | — | `RECEPTOR_POOL` in `atlas_seeded_candidates.py` |
| Orchestrator | `evidence_stacking/orchestrator/*` | — | `scripts/rl_loop.py` |
| Features | `evidence_stacking/features/*` | — | — |
| Evaluator | `evidence_stacking/evaluator/*` | — | — |
| Tools | — | `tools/__init__.py` (drop 5 superbio-bound) | 5 tool files → `legacy/tools/` |
| Model config | — | `runtime/model_factory.py` (executor → Opus) | — |
| Skills | — | `skills/COT_Rejuv_Pipeline/SKILL.md` | — |
| Workflows | — | — | `workflows/{alphafold2,boltz2,protenix}.*` + `engines/superbio/` |

---

## Appendix B — Reference docs

- Attached: Novokine Bispecific Receptor Pair Ranking — Methods (the methodology v2 mirrors)
- v1 plan: `backend/knowledge/dev/plans/master_rejuvenation_rl_plan.md` (historical, RL-loop approach)
- Keshri et al. 2026 — bioRxiv doi:10.64898/2026.04.26.720818 (C6-DPC fibroblast→muscle suppression cocktail)
- Expòsit et al. 2025 — bioRxiv doi:10.1101/2025.10.12.681819 (geometric tuning, gp130 vs IL2RG STAT bias)
- Edman 2024 — linker geometry as action variable
