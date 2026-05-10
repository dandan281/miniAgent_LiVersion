# Session 2026-05-04 (evening, second half) — Track A.5 pivot + GRN job submitted

*Picks up from `2026-05-04_evening_summary.md`.*

## TL;DR

- **Track A.5 strategy confirmed**: no Superbio app outputs raw scGPT 512-d cell embeddings. Gene programs via GRN Inference is the correct path. No fine-tuning needed — it's zero-shot inference on pretrained gene co-expression geometry.
- **scGPT GRN Inference job submitted** (`69f8f61cf5b5f7da20571932`). Used balanced 30k-cell subsample (130 MB) after the full 2 GB atlas was killed by upload timeout. Job status: `Runnable`.
- **Master plan updated to v5** — revision history, Step I.5 (GRN gene programs), CLUE partial done, file locations table, vibe-coding table.
- **NEXT_ACTIONS.md fully rewritten** to reflect current state.

---

## What was confirmed / done

### Track A.5 strategy decision
Surveyed all 9 Superbio scGPT apps. None expose a raw cell embedding output:
- Mapping / Zero-Shot Mapping → cell-type annotations
- Annotation → cell-type labels
- GRN Inference → gene programs + pathway enrichment
- Predicting Perturbations → fine-tuning app (not what we want)

**Decision**: use **scGPT GRN Inference** to get ~80 gene programs (Louvain clusters on cosine-sim of pretrained scGPT gene embeddings). Classify programs as young/aged-enriched using the atlas `Age_bin` column. Score candidate gene sets by program activation. This bypasses the vocabulary mismatch problem without needing per-cell embeddings.

No fine-tuning required — the pretrained scGPT encoder is used as-is. The gene programs are data-agnostic structure; only the metagene scoring uses the atlas data.

### Atlas subsampling
Full atlas (2 GB) uploaded but killed at the task level before completion. Wrote `SKM_balanced_30k.h5ad` (130 MB):
- 35,367 cells, all 36 cell types represented
- 800-cell cap per (annotation_level0, Age_bin) combination
- Balanced across young/old for unbiased metagene scoring

### GRN Inference submission
Config used:
| Parameter | Value |
| --------- | ----- |
| atlas | `SKM_balanced_30k.h5ad` (130 MB) |
| celltype_col_name | `annotation_level0` |
| batch_key | `batch` |
| pretrained_model | `human_all` |
| number_hvg | 1200 |
| hvg_flavor | `cell_ranger` |
| db_pathway | `Reactome_2022` |
| gene_program_index | 4 |

Job `69f8f61cf5b5f7da20571932` — status `Runnable` as of ~19:45 UTC.

### Master plan v5 + NEXT_ACTIONS rewrite
Updated `plans/master_rejuvenation_rl_plan.md`:
- v5 revision history entry (BioAPEX wiring, Track A.5 pivot, CLUE live, GRN job)
- Step I.5 added (gene programs)
- Step E updated to 🔶 partial (CLUE live submit/poll/lookup wired, tarball parser pending)
- Step I updated to 🔶 partial (AF2 wired, re-test needed, Boltz-2/Protenix pending)
- Key File Locations table updated with all v4/v5 artifacts
- Part 6 vibe-coding table updated

Rewrote `NEXT_ACTIONS.md` with current pending items in priority order.

---

## Blocked on user

1. **Re-fire AF2 smoke test** (~$1 GPU): `_coerce_aa_pairs` fix is in place; one live run confirms BioAPEX → Superbio path is production-grade
2. **Authorize CLUE live submit**: submit path is implemented; one call needed to see the tarball; then write parser
3. **Poll GRN job**: ~30–60 min from submission; auto-download and `build_programs` once it lands

---

## Files touched this session

| File | Change |
| ---- | ------ |
| `backend/scripts/scgpt_submit.py` | Updated `ATLAS_PATH` to `SKM_balanced_30k.h5ad`; added full GRN config to `APP_CONFIGS` |
| `backend/storage/atlases/SKM_balanced_30k.h5ad` | New — balanced 30k subsample (130 MB, gzip-compressed) |
| `backend/knowledge/scgpt_jobs/submission_20260504_194017.json` | GRN job submission log |
| `backend/knowledge/dev/plans/master_rejuvenation_rl_plan.md` | v5 update |
| `backend/knowledge/dev/NEXT_ACTIONS.md` | Full rewrite |
| `backend/knowledge/dev/sessions/2026-05-04_evening2_summary.md` | This file |

---

*Session ran 2026-05-04 ~19:10 UTC – ~19:55 UTC.*
