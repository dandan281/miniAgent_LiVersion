# Session 2026-05-04 (evening) — live AF2 + CLUE wiring + scGPT result

*Picks up from `2026-05-04_afternoon_summary.md`. User was napping during this
session and authorized: fire AF2 live test, then implement live CLUE polling
and test it.*

## TL;DR

- **AF2 ↔ BioAPEX dispatch wiring works end-to-end.** A real Superbio AlphaFold2
  job was submitted via the new `external_engine` path, polled until terminal
  state, and the failure was correctly surfaced. The adapter and DAG driver
  did exactly what they should.
- **The Superbio AF2 run itself failed** because of an `aa_pairs` format
  mismatch. **Fixed** in the adapter; needs one more live test to confirm.
- **scGPT Mapping job completed** but produced *cell-type annotations*, not
  the 512-d foundation-model embedding the plan assumed. **Track A.5 is NOT
  unblocked by this run.** Re-think before spending more Superbio credits.
- **CLUE live polling is implemented and live-tested for read-only paths.**
  Submit path is built against the verified swagger contract but needs
  explicit user authorization for the first live submission.

---

## What was implemented

### 1. Live AF2 smoke test through `run_workflow.py`
- Submitted ubiquitin (76 aa) via the new
  `backend/scripts/run_workflow.py workflows/alphafold2.yaml` path.
- The driver dispatched through the registered Superbio external_engine
  adapter, got back `external_job_handle` (job_id
  `69f8df5cf5b5f7da20571925`), then handed off to the `download_results`
  Python step which polled Superbio.
- Superbio reported `Failed`. `poll_and_download` correctly raised
  `RuntimeError`. **The integration plumbing did its job.**

### 2. Root cause of Superbio AF2 failure → fixed
- The Superbio AlphaFold2 app expects `aa_pairs` in
  `[{<protein_name>: <sequence>}, ...]` (single-key-per-dict) format.
- Our preflight runner produced canonical
  `[{"protein_name": "<name>", "sequence": "<aa>"}, ...]`.
- `_coerce_aa_pairs` in
  `workflows/engines/superbio/adapter.py` now normalizes both shapes (and
  JSON file paths) into the Superbio shape. Verified with three input
  variants (canonical, already-Superbio, file-on-disk).
- **Untested live** — needs one more 76-aa GPU run to confirm. Estimated cost
  ≤ $1.

### 3. Live CLUE polling implementation
File: `backend/tools/clue_api_tool.py`. Replaced the two
`NotImplementedError` blocks with a real implementation backed by the
LoopBack swagger at `https://api.clue.io/explorer/resources`:

| Helper                   | Endpoint                  | Verb | Tested live |
| ------------------------ | ------------------------- | ---- | ----------- |
| `_live_submit_query`     | `POST /api/jobs`          | POST | **No** — blocked by sandbox; needs explicit user OK to fire |
| `_live_poll_job`         | `GET /api/jobs/{id}`      | GET  | No (depends on submit) |
| `_live_lookup_perturbagen` | `GET /api/perts?filter=…`| GET  | **Yes — passed** |

`tool_id = sig_queryl1k_tool` (id `5fcc0b2273784a0a6f5deb8f`, verified live).
Result-tarball parsing into the per-perturbagen tau-ranked signature list is
**deferred** — the response surfaces `download_url` and `status`, but
extracting tau values from the `query_result.gct` archive is not implemented.

### 4. scGPT Mapping job completed and downloaded
Job `69f8d280f5b5f7da20571922` finished after ~50 min GPU. Tarball at
`backend/artifacts/superbio/69f8d280f5b5f7da20571922/output_scgpt_ref_mapping.tar.gz`
(553 MB), extracted alongside.

**Output shape (unexpected):**
- `test_data_predictions.h5ad` (1.9 GB): the original atlas (183,161 × 29,400)
  with `obs["scgpt_predictions"]` added (CellxGene cell-type labels per cell).
- `test_data_predictions.csv` (3.4 MB): the same labels in tabular form.
- `obsm` keys: `X_scVI` (30-d), `X_umap` (2-d). **No `X_scgpt` embedding.**

This is *cell-type annotation via reference mapping*, not the 512-d
foundation-model cell embedding our existing plan assumed. **Track A.5's
"young-axis" recipe (`v_celltype = mean(young) - mean(old)` in 512-d scGPT
latent) cannot be built from this output.**

---

## What was validated end-to-end

| Component                                          | Verdict |
| -------------------------------------------------- | ------- |
| BioAPEX dispatch of `engine_name=superbio` steps   | ✅ Works |
| `_coerce_aa_pairs` normalizes all three shapes     | ✅ Works |
| `poll_and_download` raises on Superbio failure     | ✅ Works |
| CLUE auth via `user_key` header                    | ✅ Works |
| `sig_queryl1k_tool` exists in CLUE catalogue       | ✅ Works |
| `lookup_perturbagen` live (sirolimus, vemurafenib) | ✅ Works |
| AF2 GPU run on Superbio                            | ❌ Failed → fixed → unverified |
| CLUE live submit                                   | ⏸ Implemented, awaiting auth to fire |
| CLUE result tarball parsing                        | ⏸ Deferred |
| scGPT 512-d embedding                              | ❌ Not what scGPT Mapping produces |

---

## What's needed next

### Highest leverage, low cost
1. **Re-fire AF2 smoke test with the `aa_pairs` fix.** One ubiquitin run via
   `run_workflow.py workflows/alphafold2.yaml --input sequence_set=/tmp/af2_smoke_test.json`.
   Should now succeed. Confirms BioAPEX → Superbio path is fully production-grade.
2. **Investigate Track A.5 plan.** Three honest options:
   - **(a)** Use `X_scVI` (30-d, already in atlas) for the young-axis. Compute
     `v = mean(young) - mean(old)` per cell type. Score candidate gene sets
     by some surrogate (e.g. encode their predicted up/down gene means via
     the scVI decoder, project, dot with `v`).
   - **(b)** Find a Superbio app that actually exports the scGPT 512-d cell
     embedding (the Mapping app does annotation, not embedding extraction).
     Possible candidates: a scGPT *Cell Embedding* or *Representation* app.
   - **(c)** Run scGPT locally on the atlas to extract the embedding. Costs
     local GPU time but is one-shot.
3. **Authorize one live CLUE query submission.** Lets us validate the submit
   path and see what the result tarball actually looks like; tarball parser
   can then be written against real data.

### Same-day work
4. **Result-tarball parser for CLUE** — once we know the GCT structure, ~50
   LOC to expose tau-ranked perturbagens as the `signatures` list our schema
   already declares.
5. **Replicate AF2 wiring for Boltz-2 and Protenix** — same pattern, swap
   the `app_id` and adjust app-specific config keys. Now that the
   `aa_pairs` normalization is in the adapter, both should "just work."

### Blocked on user
- Run a second AF2 smoke test (~$1) to confirm the format fix.
- Decide on Track A.5 strategy (X_scVI surrogate vs different Superbio app
  vs local scGPT).
- Authorize the first live CLUE query submission.

---

## Files touched

| File | Change |
| ---- | ------ |
| `workflows/engines/superbio/adapter.py` | `_coerce_aa_pairs` now normalizes to Superbio's `[{<name>: <seq>}]` format |
| `backend/tools/clue_api_tool.py`        | Live submit/poll/lookup; renamed `_L1000_QUERY_URL → _JOBS_URL`; added `_live_submit_query`, `_live_poll_job`, `_live_lookup_perturbagen` helpers |
| `backend/artifacts/superbio/69f8d280f5b5f7da20571922/` | scGPT Mapping result (extracted) |

---

*Session ran 2026-05-04 ~17:55 UTC – ~18:30 UTC. AF2 smoke job failed on
Superbio side, scGPT Mapping completed (but produced annotations not
embeddings), CLUE live wiring validated for the read-only paths.*
