# backend/legacy/ — retired v1 RL-loop pipeline

Files here were retired on 2026-05-10 when the project pivoted from the RL-loop / 4-track-reward architecture to evidence-stacking. See `backend/knowledge/dev/plans/master_rejuvenation_plan_v2.md`.

Nothing here is on the import path of v2 code. Files are preserved (not deleted) because the 79-run experience buffer at `backend/knowledge/experience_buffer.jsonl` references their schemas, and the dossiers MANIFEST is still readable.

## Contents

| Subdir | What's inside |
|---|---|
| `tools/` | 5 Superbio-bound LangChain tools (alphafold3, scgpt_phenotype, scgpt_programs, superbio, clue_api) |
| `utils/` | Superbio submit + predict helpers |
| `scripts/` | RL loop, atlas-seeded candidate enumerator, dossier generator, scgpt submit helper, smoke test loop, multi-iter consensus |
| `tests/` | Unit tests for the retired tools and scripts |
| `workflows/` | Superbio-bound workflow YAMLs + runners + engines/superbio adapter |

To run anything here you'd need to put it back on the import path and revert `backend/tools/__init__.py` to re-register the dropped tools.
