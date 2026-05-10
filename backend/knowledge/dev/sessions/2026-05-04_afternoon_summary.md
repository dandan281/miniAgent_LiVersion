# Session 2026-05-04 (afternoon) — BioAPEX × Superbio integration

*Picks up from `MORNING_SUMMARY.md` (overnight RL-loop autonomous work).*

## What was implemented today

### 1. scGPT Mapping submitted to Superbio (Track A.5 unblocked)
- Fixed missing `genename_col_name` parameter in `scripts/scgpt_submit.py` (atlas
  carries gene symbols in column `SYMBOL`).
- Live submission successful: **job_id `69f8d280f5b5f7da20571922`** at
  17:29 UTC, status `Running` (GPU ETA 30–60 min).
- Submission log: `backend/knowledge/scgpt_jobs/submission_20260504_172910.json`.

### 2. AlphaFold2 wired into BioAPEX as a workflow (Spec-30 compliant)
Four files, all parsing cleanly under `backend.workflow_specs`:

- `workflows/alphafold2.yaml` — `engine: external_workflow_adapter_v1`,
  4 steps (preflight → external_engine launch → poll/download → summarize),
  3 QC gates, 2 compliance hooks (privacy preflight + publish review).
- `workflows/runners/alphafold2.py` — `validate_sequence_set` (FASTA + JSON
  normalization, AA validation, length bounds), `poll_and_download`
  (`superbio.Client` poll loop, configurable timeout/interval, manifest.json),
  `summarize_structures` (counts PDB/CIF/confidence files → qa_report).
- `workflows/engines/superbio/alphafold2_entrypoint.md` — declared engine
  entrypoint documenting parameter_bindings → Superbio API contract.
- `workflows/report_templates/alphafold2_summary.md.j2` — Jinja2 markdown for
  the human-readable QA summary.

### 3. Superbio promoted to a first-class BioAPEX external engine
- `backend/workflow_specs.py:20` — `superbio` added to
  `_STRUCTURED_EXTERNAL_ENGINES`. Schema now enforces the structured contract
  (`execution_profile` + `parameter_bindings` + `output_locations` +
  `version_command`) for any spec declaring `engine_name: superbio`.
- `workflows/engines/superbio/adapter.py` — canonical
  `dispatch(parameter_bindings) → external_job_handle` adapter. Maps
  `app_id`/`app_name`/`running_mode` to `Client.post_job` dispatch keys,
  forwards the rest as `config`, parses `aa_pairs` whether passed inline or as
  a file path. Exposes `submit`, `get_status`, `download_results`.
- `workflows/engines/superbio/__init__.py` — package marker re-exporting the
  adapter API.
- `backend/scripts/run_workflow.py` — minimal linear DAG driver. Loads any
  BioAPEX spec, resolves `workflow_input` + `step_output` references,
  substitutes `{placeholder}` tokens in `parameter_bindings`, dispatches Python
  steps via `importlib`, dispatches `external_engine` steps via the Superbio
  adapter (or `--dry-run-engine` for safe testing). Loads `backend/.env`.
  Writes `workflow_run.json` summary into the run dir.

### Validated end-to-end
- All 4 workflow specs parse: `perturb-seq-nextflow`, `rna-seq-qc`,
  `rnaseq_qc_de`, `alphafold2`.
- AF2 dry-run executes: preflight emits validated sequences →
  external_engine step resolves placeholders (`{validated_sequence_set}` →
  JSON path, `{model_preset}` → `monomer`) → DRYRUN job handle written to
  `artifacts/alphafold2/20260504/{run_id}/workflow_run.json`.

## What's needed next (priority order)

### Imminent (auto-progressing)
1. **scGPT Mapping job to finish + download + build_axis.** When the GPU job
   flips to `Succeeded`, run:
   ```bash
   python -c "from tools.superbio_tool import SuperbioTool; ..."
   # then: scgpt_phenotype build_axis
   ```
   Activates Track A.5 in the reward function, lifts the documented
   vocabulary-mismatch ceiling.

### Cheap copy-paste (≤ 1 hr)
2. **Replicate AF2 wiring for Boltz-2 + Protenix.** Same pattern, different
   `app_id`. Boltz-2 = strongest open-source structure predictor; Protenix =
   AF3 reproduction. The Superbio adapter is already generic — only need YAML
   + runner per app.
3. **Replicate AF2 wiring for the rest of the Superbio app catalogue**:
   `boltz1`, `rfdiffusion`, `proteinmpnn`, `rfantibody`, `ligandmpnn`,
   `scgpt_mapping`, `scgpt_grn`, `scgpt_perturbation`, `scgpt_celltype`.

### Single-day work
4. **Live CLUE polling.** Replace `NotImplementedError` in
   `clue_api_tool.py` with the connectivity-map polling gateway. Track C goes
   from mock to real. ~2 hrs.
5. **More receptor pairs through the RL loop.** FGFR2+MET, EGFR+IGF1R,
   INSR+FGFR1, etc. — broaden candidate coverage while scGPT runs.
6. **Multi-iter consensus by default in `rl_loop.py --mode full`.** Variance
   ~0.23 across single runs vs ~0.0002 within-process. Make N=3 the default.

### Bigger lifts (multi-session)
7. **Stage 1 auto-proposal.** A `cellxgene_expression` SKILL.md + agent loop
   that proposes receptor pairs from atlas expression, instead of taking them
   as input.
8. **Negative-control novokine identification.** Anchors the `p_fail_i`
   noisy-OR model in Track B. Currently unanchored — requires literature
   reading.
9. **BioAPEX runtime: QC gate + compliance hook enforcement.** The minimal
   driver in `backend/scripts/run_workflow.py` skips both. Production runtime
   needs to enforce them (privacy preflight, publish review, etc.).
10. **Real GPU binder design.** Fire `--fire-design --design-live` on
    ERBB2+MET to get actual designed minibinder sequences (deferred per user
    request this session).

### Blocked on human
- AlphaFold3 API key approval (Google manual review, 1–3 days).
- PhosphoSitePlus TSV download (5 min, manual).

## Where to read more

- [`MORNING_SUMMARY.md`](2026-05-04_overnight_summary.md) — overnight RL-loop work.
- [`NEXT_ACTIONS.md`](../NEXT_ACTIONS.md) — exact CLI commands cheat sheet.
- [`rejuvenation_rl_plan.md`](../plans/master_rejuvenation_rl_plan.md) — master plan v4.
- `workflows/engines/superbio/alphafold2_entrypoint.md` — adapter dispatch
  contract reference.

---

*Session ran 2026-05-04 ~17:00–17:40 UTC. scGPT job still running at session
end; checked again at 17:55 UTC, status `Running`.*
