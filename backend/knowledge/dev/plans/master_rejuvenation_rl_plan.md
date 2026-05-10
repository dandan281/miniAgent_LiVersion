# Muscle Rejuvenation Novokine RL Pipeline — Master Plan

> **🛑 SUPERSEDED 2026-05-10** — see [`master_rejuvenation_plan_v2.md`](master_rejuvenation_plan_v2.md). This file is preserved as the historical record of the v1 RL-loop / 4-track-reward / Superbio-bound approach. The v2 evidence-stacking pipeline replaces the orchestrator; the 28→23 LangChain biology tools and the knowledge base were carried forward. Retired files live in `backend/legacy/`.

*Last updated: 2026-05-05 (v7, multi-source consensus atlas + 5-study knowledge base).*
*Persist this file across sessions — it is the single source of truth for the pipeline design.*

## Revision history
- **v7 (2026-05-05, evening)**: Multi-source consensus atlas v2:
  - Five aging studies staged under `backend/knowledge/aging_studies/`: GSE164471 (Tumasian 2021, vastus lateralis bulk Y/O), GSE111016 (Pillon 2019, Singapore Sarcopenia case-control bulk, all male), GTEx v11 (818 donors, continuous limma-trend ~ sex + ischemic_time + age), Kedlian/Lacraz 2024 Nat Aging (sc/sn-RNA pseudobulk DEGs, SI Table 3), Lai 2024 Nature HLMA (age-correlation per cell type, SI Table 5).
  - Pre-computed DEG tables only — no raw counts/atlas downloaded (~50–200 MB total).
  - **`backend/scripts/build_consensus_atlas.py`** ingests all 5 sources → `muscle_atlas_DE_v2_consensus.json`. Consensus rule: gene must appear up-in-aged in ≥2 sources for `P1_up`, ≥2 sources down-in-aged for `P2_up`. Per-gene `provenance` recorded. Lai HLMA flagged as secondary (older/sicker cohort).
  - **v2 is opt-in**: `phenotype_checkpoint.score_phenotype(atlas_version="v2")` and `rl_loop.py --atlas-version v2`. Default remains v1 to preserve 79-run experience buffer reproducibility.
  - Tests: `backend/tests/test_consensus_atlas.py` — 14 schema/biology checks pass; biology sanity (canonical IEGs in P1_up, contractile genes in P2_up) auto-skips until bulk uploads land.
- **v1 (2026-04-30)**: Initial plan. Multiplicative uncertainty, OmniPath as primary adaptor source, CMAP at 0.35 weight, AF on isolated ECDs, blanket GPCR/ion-channel exclusion, fabricated 2× ECD-size heuristic.
- **v2 (2026-05-01)**: Major revisions after independent ChatGPT and Claude critique:
  - Switched multiplicative confidence → noisy-OR + empirical calibration; replaced binary gate with top-K ranking
  - Removed fabricated "ECD size > 2×" hard rule; reframed as H2F-anchored red-flag heuristic
  - Stripped paraphrase quotation marks in §2.2
  - Reweighted reward: CMAP 0.35→0.10, atlas-overlap 0.40→0.50, mechanism-coherence (PhosphoSitePlus/ScanSite layer) 0.20, Biomni AUCell removed (unverified claim)
  - Replaced CMAP `/api/perts` with correct CLUE Query / `/api/jobs` endpoint
  - Replaced "CELLxGENE REST API" with correct CZ Cell Census Python/R API
  - Added PhosphoSitePlus + ScanSite + NetPhorest as residue-level adaptor layer (OmniPath alone insufficient)
  - Reframed receptor-class restriction as H2F-template scope, not biological exclusion
  - AlphaFold usage hierarchy: PDB > AF-Multimer/Boltz-2 on complex > AF on isolated ECD
  - Boltz-1 acceptance thresholds (confidence>0.6, complex_pLDDT>0.7, ipTM, ipSAE) separated from AF2 thresholds
  - Linker geometry promoted to first-class action variable per Edman 2024
  - Phase 2 scGPT zero-shot dropped; scVI+scANVI for mapping, pySCENIC for GRN, scGPT fine-tuned only for perturbation
  - Added explicit hypothesis-tournament posterior weighting
  - Added Cao/Baker library coverage caveat (most RTKs lack published binders)
  - Open-source Biomni (frozen 2025-04-15) and Phylo Lab platform tracked separately
  - Added Lai 2024 Nature + Lacraz 2024 Nature Aging muscle atlases as primary DE source with .h5ad fallback
  - Added Superbio S3 storage privacy note
- **v3 (2026-05-02)**: Implementation sprint — biology API tools built, atlas compiled, COT skill rewritten:
  - **Architecture decision**: individual biology database APIs are now **LangChain `BaseTool` subclasses** (not Biomni wrappers, not skills). Biomni is retained only as a free-tier fallback for complex multi-DB synthesis queries. Direct HTTP calls are cheaper, faster, and more controllable.
  - **4 new LangChain tools built** (`backend/tools/`): `OmnipathApiTool`, `ReactomeApiTool`, `BiogridOrcsTool`, `PhosphositeTool` — all registered in `tools/__init__.py`, all follow the `contracts.py` return convention. Total tool count: 19.
  - **`COT_Rejuv_Pipeline` SKILL.md rewritten to v2**: explicit forced-proximity biased signaling constraint, correct 3a–3d tool call sequence (OmniPath enz_sub → PhosphoSitePlus → Reactome on adaptors only → OmniPath TF-target DoRothEA A+B → BioGRID ORCS), noisy-OR chain_soundness, three-track scoring, H2F calibration check, top-K decision tiers, `experience_buffer.jsonl` log schema. Verified parses correctly via skills scanner.
  - **`muscle_atlas_DE.json` created**: P1_up (77 genes), P2_up (536 genes), FAP_P1_up (141), FAP_P2_up (208). Derived from Lai 2024 + fibroblast aging CSVs, thresholds padj < 0.05 and |log2fc| > 0.5. Per-cell-type and detailed (log2fc + padj per gene) sections included. Raw CSVs saved to `backend/knowledge/raw_degs/`.
  - **Key Reactome bug fixed**: correct UniProt→pathway endpoint is `/data/mapping/UniProt/{acc}/pathways` (not `/data/pathways/low/entity/{acc}/allForms`). Smoke tested: 37 pathways returned for EGFR (P00533).
  - **`.env.example` updated**: added `BIOGRID_ORCS_ACCESS_KEY=` (requires free registration at thebiogrid.org).
- **v6 (2026-05-04, late evening)**: Track A.5 fully wired and validated:
  - **scGPT GRN job `69f8f61cf5b5f7da20571932` completed and downloaded.** Result includes per-cell metagene scores (`SKM_balanced_30k_metegenes_scores.h5ad`, 118 MB) with 298 program score columns + gene memberships in `unfiltered_metagenes.csv`. Workaround: Superbio client's `download_job_result_file` strips leading `/` from absolute paths, so files landed at `/gpfs/scrubbed/danlovuw/gpfs/scrubbed/...` — moved to correct location.
  - **`gene_programs.json` cache built** at `backend/storage/scgpt_cache/`. 296 programs total: **90 young-enriched** (top: prog 251 MYH7/MYOM2, prog 155 ACTA1/DES/ACTC1, prog 39 TNNT2/ACTN2/TRDN), **76 aged-enriched** (top: prog 5 HLA-DP/DQ/CD74, prog 19 CD3D/CD8A/IL32, prog 123 CCL2/CCL8/CCL13, prog 1 MS4A1/CD22/CD79A), 130 neutral. Biology is textbook: structural muscle programs lost, immune/MHC/complement programs gained with age.
  - **Track A.5 wired into `rl_loop.py`**: new `stage_track_a5_score()` reads the cache, computes `score_young - score_aged` (each = sum over programs of `f_up - f_down`), normalizes via `tanh(raw / 2.5)` to ∈ [-1, +1]. Both `run_score_only()` and `run_full()` inject `track_a5_score` into the candidate dict before `stage_compose_reward()`.
  - **3-candidate sanity test**: H2F → reward +0.731 (was ~+0.6), anti-rejuv decoy → -0.077 INCOHERENT (Track A.5 -0.929), neutral → +0.147 BOTTOM. The vocabulary-mismatch problem (predicted MAPK feedback genes don't appear in raw atlas DEGs) is fixed because gene programs cluster MYH7/ACTA1/DES/TNNT2 etc. into a single coherent muscle-structural unit.
  - **AF2 BioAPEX path validated**: job `69f8fbdff5b5f7da20571936` accepted by Superbio (status `Running`) — the `_coerce_aa_pairs` fix passes the input gate that 3 prior web-UI attempts failed.
- **v5 (2026-05-04, evening)**: BioAPEX wiring, Track A.5 pivot to gene programs, CLUE live:
  - **BioAPEX → Superbio dispatch wiring complete.** `workflows/engines/superbio/adapter.py` implements `dispatch()` / `submit()` / `get_status()` / `download_results()`. `_coerce_aa_pairs` normalizes the aa_pairs format (canonical `{protein_name, sequence}` OR single-key Superbio dict OR JSON file) — the live AF2 smoke test failed due to this mismatch, the fix is in place and awaits one re-test.
  - **`workflows/alphafold2.yaml` + `workflows/runners/alphafold2.py`**: full Spec-30-compliant workflow YAML (preflight_check → launch_alphafold2 → download_results → summarize_structures). `scripts/run_workflow.py` is a minimal linear DAG driver that resolves inputs, substitutes templates, and dispatches via `_execute_external_engine_step` (superbio) or `_execute_python_step`. Wrote `workflow_run.json` to `artifacts/{workflow_id}/{date}/{run_id}/`.
  - **Live CLUE polling implemented** in `backend/tools/clue_api_tool.py`: `_live_submit_query` (POST /api/jobs), `_live_poll_job` (GET /api/jobs/{id} loop), `_live_lookup_perturbagen` (GET /api/perts). Auth, catalogue, and perturbagen lookup smoke-tested live. Submit path implemented but not yet fired (gated on user auth). Result tarball parser (GCT → tau-ranked list) deferred until after first live submit.
  - **Track A.5 strategy pivot**: scGPT Mapping job (run ID `69f8d280f5b5f7da20571922`) finished but produced *cell-type annotations*, not the 512-d cell embedding the original plan assumed. No Superbio app exports the raw scGPT cell embedding. Strategy: use **scGPT GRN Inference** (gene programs approach) instead. Gene programs from scGPT's pretrained gene co-expression graph → classify ~80 programs as young/aged enriched → score candidates by program activation. This fixes the vocabulary mismatch problem without requiring per-cell embeddings.
  - **scGPT GRN Inference job submitted** (`69f8f61cf5b5f7da20571932`). Using balanced 30k-cell subsample (`SKM_balanced_30k.h5ad`, 130 MB, 35,367 cells, all 36 cell types × 2 age bins, 800-cell cap per group). Pretrained model: `human_all`. Job status: `Runnable`.
  - **`knowledge/dev/` reorganization**: all developer docs now under `dev/` with `YYYY-MM-DD_<period>_<doctype>.md` naming convention. README.md index, NEXT_ACTIONS.md, plans/, sessions/ subdirs.
- **v4 (2026-05-04)**: Orchestration milestone — RL loop runs end-to-end:
  - **`scripts/rl_loop.py --mode full` is no longer a stub**. It invokes the in-process agent (`graph.agent.agent_manager.astream`) — bypasses HTTP/SSE entirely. Agent reads SKILL files, runs Stages 1-3 with full tool access (26 tools), writes structured JSON to `knowledge/agent_outputs/{candidate_id}.json`, then loop reads and scores Stages 4-6 locally.
  - **First successful end-to-end H2F run**: 72 tool calls, 14+14 predicted up/down genes with PLCG1 correctly classified as sterically excluded (ECD asymmetry 630 vs 353 aa). Phenotype +0.38, chain_soundness 0.65, reward +0.49, tier=MIDDLE_HUMAN_REVIEW.
  - **Stage 6 wired**: `utils/superbio_submit.py` plus `--fire-design` flag. TOP_K_DESIGN tier candidates auto-fire a Binder Design with Boltz-1 manifest (default dry-run; `--design-live` to actually spend GPU credits). Manifests land in `knowledge/design_outputs/{candidate_id}/manifest.json`.
  - **`utils/chain_soundness.py` added**: geometric-mean over per-step confidences (more usable scale than strict product). Joint failure probability also computed for diagnostics. INCOHERENT gate at 0.30.
  - **Mock tools now registered**: `cellxgene_expression`, `clue_api`, `alphafold3_api` were pre-built but not in `tools/__init__.py`. Now registered. AF3 and CLUE remain mock-only (live mode pending external action). Total tool count: **26**.
  - **`scgpt_phenotype` + `scgpt_programs` tools** wrap the Superbio scGPT Mapping and GRN Inference apps. Atlas downloaded (`SKM_human_pp_cells2nuclei_2023-06-22.h5ad`, 2.02 GB, 183k cells, all 4 muscle cell types covered). scGPT GPU jobs not yet submitted (gated on user credit confirmation).
  - **`scripts/generate_candidates.py`** (heuristic, no agent): 12 RTKs × 5 linkers = 330 candidates; ranked TSV + top-20 JSON in `knowledge/`. Used as input to the agent-driven full loop.
  - **Reward composition**: Track A (50%) atlas overlap via `phenotype_checkpoint`; Track B (30%) chain_soundness via geometric mean; Track C (10%) CLUE mock for now; Track A.5 (10%) scGPT gene programs reserved (GRN job pending).
  - **AF3 + live CLUE remain mock**. Implementing live AF3 is blocked on Google manual approval (`AF3_API_KEY`). Live CLUE submit path is implemented but not yet fired (sandbox restriction; needs explicit user auth).

---

## Part 1 — Project Summary

### What are novokines?

A **novokine** is a de novo designed synthetic protein ligand built by fusing two computationally designed receptor-binding domains (minibinders) via a flexible peptide linker. The fused dimer simultaneously engages two distinct cell-surface receptors and forces them into physical proximity, producing **biased agonist signaling** that is mechanistically distinct from natural ligands and cannot be achieved by treating cells with both natural ligands simultaneously.

Critical distinctions:
- **NOT combinatorial**: applying ligand A + ligand B to a cell is NOT equivalent to a novokine. Natural ligands activate the full pathway set of each receptor independently. Forced proximity produces a biased subset.
- **NOT synergistic**: the output is not A-signaling + B-signaling amplified. It is a geometrically constrained, mechanistically distinct output.
- **Biased agonism mechanism**: when receptor A and receptor B are held in physical proximity by a bivalent binder, their intracellular kinase/signaling domains are forced into a specific relative orientation. This geometry determines which transphosphorylation events are productive (adaptors can dock) and which are sterically excluded (adaptors cannot reach or are displaced). The output is the biased subset that survives this geometric filter.

### Canonical exemplar — H2F

H2F (Baker / Ruohola-Baker labs, 2025) pairs HER2 (ERBB2, orphan RTK) with FGFR1/2c:
- Activates: MAPK and AKT branches
- Bypasses: PLCγ / Ca²⁺ branch (which natural FGF ligands always co-activate)
- Functional effects: reprograms fibroblasts toward skeletal muscle, enhances myotube maturation, sustains stem cell pluripotency

H2F is the **positive control** for this entire project. Every algorithmic reasoning step should be benchmarkable against H2F.

### The muscle rejuvenation goal

Use an RL loop to design and score novokine candidates that shift human skeletal muscle cells from an **aged phenotype (P1: donor age ≥ 65)** toward a **young phenotype (P2: donor age 25–35)**, as defined by the human skeletal muscle cell atlas differential expression (DE) signature.

- **P1**: aged skeletal muscle — reference DE gene signature (upregulated: SASP markers, senescence, inflammation; downregulated: myogenic, metabolic, regenerative genes)
- **P2**: young skeletal muscle — reference DE gene signature (upregulated: MYH2/MYH7, TNNT3, myogenic TFs; downregulated: CDKN2A, IL6, SASP)
- **Reward**: GOOD if the novokine's predicted downstream transcriptome resembles P2 more than P1; BAD if P1-like; NEUTRAL if ambiguous

### Three-system architecture

| System | Role | Cost |
|---|---|---|
| **miniAgent (BioAPEX)** | Master orchestrator; all LLM reasoning, skill execution, experience buffer management | ~$0.002–0.01/iteration (DeepSeek) |
| **Biology API tools (LangChain, direct HTTP)** | OmniPath, Reactome, BioGRID ORCS, PhosphoSitePlus, UniProt, Ensembl, NCBI eUtils — all called directly as `BaseTool` subclasses within the agent; no intermediate LLM; free and rate-limit-tolerant | Free (no API keys except BioGRID ORCS requires free academic key) |
| **Biomni (Phylo free tier — fallback only)** | Complex multi-step biology queries requiring simultaneous synthesis across PubMed + BioGRID + STRING; used selectively when the direct API stack is insufficient; daily limits make it unsuitable as primary pipeline component | Free (within daily limit) |
| **Superbio.ai** | GPU compute for protein design: RFdiffusion → ProteinMPNN → Boltz-1 pipeline; only triggered on GOOD-reward candidates needing novel minibinder design | Paid (GPU credits), minimized by gating |

**Architecture decision (v3)**: Individual biology DB APIs (OmniPath, Reactome, BioGRID ORCS, PhosphoSitePlus) were initially planned as Biomni queries. After review, the decision was made to implement them as direct LangChain `BaseTool` subclasses. This gives the agent full structured output (typed Pydantic schemas), deterministic retry/error handling via `contracts.py`, and no nested LLM call overhead. Biomni is retained as a free-tier fallback for queries that genuinely require multi-DB synthesis and narrative reasoning.

Biomni is based on **Qwen-32B** (Alibaba), fine-tuned via multi-turn RL (Biomni-R0). It is not Queen — it is Qianwen. Free tier has daily usage limits and is not suitable as a high-throughput automated backend. Use it for complex queries that would otherwise require 5+ sequential API calls.

Superbio.ai has:
- **Co-Pilot**: conversational agentic workflow builder (free or low-cost). Use for pipeline assembly and one-off design jobs.
- **Binder Design with Boltz-1** pipeline: RFdiffusion → ProteinMPNN → Boltz-1 (confirmed end-to-end, paid GPU).
- **Boltz-2** app (newer, biomolecular interaction scoring).
- scGPT apps (annotation, GRN inference, perturbation prediction, zero-shot mapping) — all require user-uploaded data; NOT zero-shot from prior knowledge alone.

---

## Part 2 — Scientific Constraints and Design Principles

### 2.1 Kinase domain geometry constraint (qualitative — no quantitative threshold)

When two receptors of different sizes (different extracellular domain lengths, different transmembrane helix positions, different juxtamembrane linker lengths) are forced into proximity by a bivalent binder, their intracellular kinase domains end up at a geometrically determined relative position. This position may or may not permit productive transphosphorylation and adaptor recruitment.

**Important caveat (added v2 post-critique)**: The v1 of this plan stated "ECD size differential > 2× predicts poor transphosphorylation geometry." **This 2× rule is NOT in any cited paper and was fabricated.** It has been removed. The qualitative principle (geometry matters, kinase-substrate distance matters) is correct and supported by Expòsit et al. 2025 and Edman et al. 2024, but no validated quantitative threshold exists in the literature for ECD size ratios.

**Replacement heuristic — H2F as calibration anchor**:
- H2F: HER2 ECD ~630 aa, FGFR1c ECD ~325 aa, ratio ~1.94
- Pairs with ECD-size ratio > 1.94 have *less precedent than H2F* and warrant higher-priority structural validation (Step 2b with AF-Multimer or Boltz-2 on the binder–ECD complex)
- This is a red-flag heuristic for triage prioritization, NOT a rejection filter
- Calibrate empirically against the H2F positive control as data accumulates

**Implication for the pipeline**: receptor geometry compatibility is assessed in Step 2 (validation):
- Compare extracellular domain sizes (from UniProt domain annotations and PDB structures where available)
- Use AF-Multimer or Boltz-2 on the binder–ECD complex (not AF on isolated ECDs) when no PDB structure exists
- Flag asymmetric pairs for higher-priority structural validation, not rejection
- Geometry is a confidence modulator, not a binary filter

### 2.2 Biased signaling ≠ additive activation (confirmed by papers)

Expòsit et al. (2025, bioRxiv 10.1101/2025.10.12.681819) demonstrate experimentally that rigidly scaffolded receptor-binding domains placed at defined relative orientations and distances produce geometry-dependent signaling bias — including pSTAT1 vs pSTAT5 ratio shifts in IL-7 signaling, and decoupling of MHC-I from PD-L1 induction in type I interferon signaling. The substantive claim — that geometry alone (not just receptor identity) determines pathway bias — is well-supported. Note: the v1 of this plan placed a paraphrase of this finding inside quotation marks, which was incorrect. This is a paraphrase of the paper's main result, not a verbatim quotation.

The core reasoning principle: focus on the **geometry of forced co-clustering**, not on pathway union. The same minibinder pair in different scaffold configurations can produce qualitatively different signaling outputs.

### 2.3 Uncertainty accumulation across multi-step zero-shot reasoning

The zero-shot pipeline chains ~6 inference steps. Each step introduces assumptions, and v1 proposed multiplicative confidence propagation. **This was wrong.** With even 0.7 per-step confidence, 6 steps multiplicatively yield 0.117 — below the proposed 0.15 gate. The pipeline would never trigger design.

**v2 fix — Noisy-OR with empirical calibration**:

Each step `i` emits a per-step **failure probability** `p_fail_i` (probability that this step's reasoning is wrong, conditional on prior steps being correct). The aggregate probability that the chain is sound:

```
P_chain_sound = Π (1 - p_fail_i)
```

This is mathematically equivalent to noisy-OR over independent failures. Critically, `p_fail_i` is calibrated empirically:
- Hold out H2F (HER2+FGFR1c) as a positive control
- Run the pipeline on H2F, observe step-wise outcomes
- Set `p_fail_i` per step to match observed failure rates on H2F-class candidates
- Recalibrate as more positive controls accumulate (Abedi 2025 IFNAR1 hubs, Expòsit 2025 geometric series)

**Replace the binary gate with top-K ranking**:
- Compute `reward_value` and `chain_soundness` for every candidate in a batch
- Rank by `reward_value × chain_soundness` (or a learned combination)
- Take top-K candidates per batch for design (K = GPU budget / cost-per-design)
- No threshold needed; the ranking absorbs the calibration

**Per-step error sources are correlated, not independent**: when an LLM makes a wrong call at step 3, errors at step 4 are more likely. Independent-failures noisy-OR is still better than multiplicative but understates correlated risk. Future work: replace with a learned Bayesian network where step-level errors share a latent "candidate is fundamentally implausible" variable.

### 2.4 Structure prediction usage hierarchy (revised v2)

**v1 proposed using AlphaFold on isolated receptor ECDs at Step 2b.** Critique pointed out that for nearly all RTKs and cytokine receptors in scope (HER2, EGFR, FGFR1c/2c, MET, AXL, IFNAR1/2, IL-7Rα, gp130, γc, βc, TrkA, TNFR1/2, BMPR1/2, ALK4/5), high-resolution PDB structures of the ECD or ECD-ligand complex already exist. Running AF on isolated ECDs is at best redundant and at worst introduces predicted-structure artifacts.

**v2 hierarchy** for Step 2b structural input:

1. **PDB experimental structure (preferred, free, fastest)**:
   - Query RCSB PDB API for ECD or ECD-ligand complex structures
   - For H2F-relevant pairs: PDB 3SE3 (IFNAR1-IFNAR2-IFNα), 6X93 (IL-10), 5T5W (IFN-λ), 7N1J (FGFR4 D3 + mb7), 1N8Z (HER2 ECD + Herceptin Fab)
   - Extract: domain boundaries, accessible binding surfaces, membrane-proximal distance

2. **AF-Multimer or Boltz-2 on binder–ECD complex (when no PDB exists for the relevant epitope)**:
   - This is the right tool: predict the binder docked against the ECD, not the ECD alone
   - Gives orientation and accessibility information AF on isolated ECD cannot
   - Available via Biomni Phylo Lab (AlphaFold) or Superbio Boltz-2 app
   - Use AF-Multimer's iPAE / Boltz-2's confidence_score for binding plausibility

3. **AF2 on isolated ECD (last resort)**:
   - Only when no PDB exists AND no binder structure is being predicted yet
   - Be aware of failure modes: missing glycosylation, loop conformation artifacts, no co-receptor

4. **UniProt domain annotation alone (fast pre-filter)**:
   - For the first sweep across hundreds of receptor pairs
   - Extract: signal peptide, ECD length, TM helix position, juxtamembrane length, kinase domain boundaries
   - Use to prioritize which pairs warrant full structural work

**Acceptance thresholds — separated by validator (v2 fix)**:

The v1 conflated AF2 thresholds with Boltz-1 outputs. They are different metrics on different scales:

| Validator | Thresholds | Source |
|---|---|---|
| AF2 / AF-Multimer initial guess | pAE_interaction < 7.5, pLDDT > 85 | Bennett et al. 2023; Cao et al. 2022 binder library |
| Boltz-1 | confidence_score > 0.6, complex_pLDDT > 0.7, ipTM ranking | Boltz-1 paper (Wohlwend et al. 2024) |
| Boltz-2 | confidence_score (similar scale to Boltz-1), use ipSAE per Dunbrack 2025 in addition to ipTM | Boltz-2 (2025), Dunbrack 2025 |

**Use the right validator's thresholds**: Superbio's "Binder Design with Boltz-1" pipeline uses Boltz-1 thresholds. Do NOT mix AF2 and Boltz thresholds.

---

## Part 3 — Full Refined RL Loop

### Architecture overview

```
miniAgent (BioAPEX / DeepSeek)
│
├── PROPOSE: novokine_identification skill
├── VALIDATE: novokine_validation skill  
├── MECHANISM RECORD: COT_Rejuv_Pipeline steps 1–4
├── TRANSCRIPTOME PREDICTION: COT_Rejuv_Pipeline step 5
├── PHENOTYPIC CHECKPOINT: COT_Rejuv_Pipeline step 6
└── DESIGN: novokine_design_handoff → Superbio Binder Design with Boltz-1
     [Biomni free tier used selectively at steps 1, 3, 5, 6 for complex queries]
     [OmniPath REST API, CELLxGENE API, CMAP API, BioGRID ORCS: free, direct HTTP]
```

---

### Step 1 — PROPOSE (H2F-templated, biased signaling aware)

**Tool**: miniAgent `novokine_identification` skill + Biomni free tier (complex query)

**Logic** (NOT: query receptors then combine pathways):
- 1a. **CZ Cell Census Python/R API over TileDB-SOMA** (free; not REST — v1 mislabeled this):
  - Use `cellxgene-census` Python package to query the human muscle aging atlas
  - Primary atlases: **Lai et al. 2024 (Nature, doi:10.1038/s41586-024-07348-6)** — 387k cells, age 15–99; and **Lacraz et al. 2024 (Nature Aging)** — 17 donors, ~183k cells/nuclei
  - Verify these atlases are mirrored in CZ Census; if not, fall back to direct .h5ad download from `muscleageingcellatlas.org`
  - Extract receptor-encoding genes expressed in aged (≥65, P1) vs young (25–35, P2) skeletal muscle cell types
  - **Scope (NOT biological exclusion)**: focus on receptor families amenable to the H2F-template mechanism:
    - RTKs (EGFR/ERBB family, FGFR1–4, IGF1R, INSR, MET, VEGFR, AXL/MERTK, etc.)
    - Cytokine/JAK-STAT receptors (gp130, γ-common, β-common, IFNAR1/2, IL10R1/2, etc.)
    - TNFR superfamily (trimerization-dependent — pair design must respect 3-fold symmetry)
    - TGF-β/BMP receptor pairs (type I + type II)
  - **Out of H2F-template scope (NOT inherently non-amenable)**: GPCRs, ion channels, nuclear receptors. v1 stated these were "not amenable to forced-proximity agonism"; this is too strong. Class C GPCRs (mGluR, GABA-B, calcium-sensing receptor) have large extracellular Venus-flytrap domains and obligate dimerization; some ion channels (P2X, TLR4/MD2) are clustering-responsive; nuclear receptors are excluded for subcellular localization (intracellular), not geometry. These are **out of scope for the H2F-template approach** but not inherently incompatible with extracellular bivalent agonism. Defer to future work, not exclude as biologically impossible.
- 1b. **Biomni free tier** (complex multi-step literature + DB query):
  - PubMed + BioGRID + STRING query: "forced receptor co-clustering biased signaling skeletal muscle aging MAPK AKT"
  - "Given H2F (HER2+FGFR1 → MAPK/AKT on, PLCγ off) as template, which receptor pairs from the expressed set would produce an analogous biased output in aged skeletal muscle — activating pro-myogenic/pro-metabolic pathways while suppressing SASP/inflammation?"
  - Returns: candidate pairs with hypothesized biased outputs and literature evidence (not a database lookup — a reasoning step)
- 1c. **Adaptor recruitment prediction — multi-source stack (v2 fix)**:
  v1 used OmniPath alone. Critique: OmniPath is an aggregated activity-flow graph, not a residue-level SH2/PTB binding model. Replace with a stack:

  - **Layer 1 (residue-level binding specificity)**:
    - **PhosphoSitePlus** (curated SH2/PTB binding sites, free academic access) — query each receptor's intracellular domain for known phosphorylation sites and their documented adaptor partners
    - **ScanSite SH2 specificity matrices** (Yaffe lab, free) — for predicting which SH2 domains bind which pY motifs
    - **NetPhorest** — predicted pY motifs for receptors lacking experimental data
  - **Layer 2 (network-level activity flow)**:
    - **OmniPath REST API** (free, no key) — `/interactions?datasets=omnipath,pathwayextra,kinaseextra` for signed/directed adaptor network
    - **OmniPath enzyme-substrate** (`enz_sub` endpoint) for kinase-substrate edges
  - **Layer 3 (pathway cassettes)**:
    - **Reactome / KEGG** for canonical signaling cassettes downstream of activated adaptors
    - **DoRothEA confidence A+B only** for TF-target inference (lower confidence levels are too noisy for reward signal)
  - **Layer 4 (CRISPR functional evidence)**:
    - **BioGRID ORCS REST** (`orcsws.thebiogrid.org`, free with access key) — CRISPR screen evidence for predicted gene changes in muscle/myoblast contexts

  **What we actually predict at this layer**:
  - For each receptor: which adaptors *can* bind based on Layer 1 specificity + Layer 2 connectivity
  - Which adaptors require **trans-phosphorylation** (phosphorylation of receptor B by receptor A's kinase): these are activated only on forced co-clustering
  - Which adaptors are likely **sterically excluded** based on the receptor pair's predicted intracellular domain geometry (informed by Step 2b structural data)
  - **Caveat**: OmniPath cannot definitively identify "excluded" adaptors. This requires the structural step (PDB or AF-Multimer/Boltz-2 on the binder–ECD complex). Layer 2 alone gives candidates; Step 2b confirms or refutes.
- 1d. **Hypothesis tournament with explicit posterior weighting (v2 fix)**:

  v1 said "generate 2–4 hypotheses" but never specified how they propagate. Critique: silent collapse to LLM's favorite. v2 makes this explicit.

  **Action space — linker geometry is a first-class variable** (per Edman 2024, C6-79N at 18 Å vs C6-79C at 54 Å produced qualitatively different FGFR signaling):
  ```
  linker_options = [
    "GS×4 flexible (~15 aa, ~20 Å end-to-end)",
    "GS×8 flexible (~30 aa, ~40 Å)",
    "rigid α-helix 20 aa (~30 Å)",
    "rigid α-helix 40 aa (~60 Å)",
    "Expòsit-style rigid scaffold (defined geometry, multiple variants)"
  ]
  ```

  For each receptor_pair, generate one candidate per `(receptor_pair, linker_option)` combination (5 candidates per pair). Each candidate gets:

  - **Prior weight `w_j`**: based on literature support strength
    - 1.0 if the linker geometry exactly matches a published novokine (e.g., H2F's linker for HER2-FGFR)
    - 0.7 if the linker geometry is analogous to a published case
    - 0.4 if extrapolating from H2F template
    - 0.2 if pure novel pairing
  - **Per-step posterior update**: at each subsequent step k, multiply `w_j` by `(1 - p_fail_i)` where `p_fail_i` is calibrated per §2.3
  - **Final reward (posterior-weighted ensemble)**:
    ```
    reward(receptor_pair) = Σ_j w_j^(6) × reward_j  /  Σ_j w_j^(6)
    ```
  - **Robustness signal**: a receptor_pair where 3 of 5 linker hypotheses score GOOD is more robust than one where only the highest-prior hypothesis squeaks past — track both `mean_reward` and `n_good_hypotheses` per pair
  - **Design selection**: when triggering design, pick the `(receptor_pair, linker_option)` with highest posterior weight × reward, not just highest reward

**Output per candidate**:
```json
{
  "receptor_A": "ERBB2",
  "receptor_B": "MET",
  "hypotheses": [
    {
      "linker_assumption": "flexible 15aa",
      "predicted_bias": {"on": ["MAPK", "PI3K-AKT"], "off": ["PLCγ", "STAT3"]},
      "adaptor_map": {"recruited": ["GRB2", "SHC1", "GAB1"], "excluded": ["PLCγ1"]},
      "confidence": 0.62,
      "literature_refs": ["PMID:xxx"]
    },
    {
      "linker_assumption": "rigid helix 20aa",
      "predicted_bias": {"on": ["MAPK", "STAT3"], "off": ["PLCγ"]},
      "adaptor_map": {"recruited": ["GRB2", "JAK1"], "excluded": ["PLCγ1"]},
      "confidence": 0.41,
      "literature_refs": []
    }
  ]
}
```

---

### Step 2 — VALIDATE (geometric + kinase domain geometry)

**Tool**: miniAgent `novokine_validation` skill + Biomni AlphaFold (free tier)

- 2a. **UniProt REST** (free): fetch domain architecture for both receptors
  - Confirm accessible extracellular binding epitope exists on each
  - Record: signal peptide length, extracellular domain(s) length (aa), transmembrane helix position, juxtamembrane linker length, kinase domain position
  - **Reject** if: no extracellular domain, binding site buried in membrane-proximal stalk, no kinase/signaling domain (pseudokinase without transactivation partners — case by case)
- 2b. **Kinase domain geometry check** (NEW — critical):
  - Estimate relative position of receptor A's kinase activation loop vs. receptor B's substrate tyrosine motifs when their extracellular domains are bridged at a linker-defined distance
  - Use: UniProt domain lengths + literature kinase domain structure annotations
  - Flag pairs where size differential > 2× in extracellular domain length (high risk of kinase-substrate misalignment)
  - **Biomni AlphaFold** (free tier): run AlphaFold on each receptor's extracellular domain in isolation to get accurate domain size and binding surface geometry
    - This is NOT the full complex prediction (novokine doesn't exist yet)
    - Purpose: get accurate domain geometry to estimate intracellular domain positioning
  - Confidence score for geometric feasibility based on: domain size ratio, known structural data, AlphaFold pLDDT of relevant regions
- 2c. **OmniPath check**: does this pair naturally dimerize?
  - If yes: known obligate complex → deprioritize unless forced geometry demonstrably differs from natural
  - If no: novel forced pairing → proceed (higher novelty value)
- 2d. **novokines.md knowledge base + literature**: known minibinders for either receptor?
  - If yes: reuse known binder (skip RFdiffusion for that chain → saves GPU cost)
  - Record: minibinder source (Cao/Baker published library, de novo required, computational variant)
- 2e. **Cell co-expression** (CELLxGENE): confirm both receptors are co-expressed on the same cell subtype in aged skeletal muscle (myoblast, myotube, satellite cell, FAP)
  - Reject if: spatially or cell-type separated

**Geometric feasibility confidence score**:
```
geo_confidence = 0.4 × (1 - domain_size_ratio_penalty) 
               + 0.3 × alphafold_pLDDT_score 
               + 0.3 × literature_structural_evidence
```

**Reject criteria**: no accessible epitope, obligate natural dimer with identical geometry to forced pair, geometric confidence < 0.3, not co-expressed in same cell type.

---

### Steps 3–4 — MECHANISM RECORD (forced proximity signaling COT)

**Tool**: miniAgent `COT_Rejuv_Pipeline` steps 1–4; OmniPath REST + Reactome + BioGRID ORCS (all free)

**Core reasoning frame**: "When receptor A and receptor B are PHYSICALLY HELD TOGETHER by a bivalent binder at distance D, with orientation θ, what adaptor geometry arises at their co-clustered intracellular domains — and which transphosphorylation events are productive given the kinase-to-substrate distance?"

- 3a. **OmniPath intracellular adaptor layer**:
  - For each receptor: SH2/PTB domain binding partners to each phosphotyrosine motif
  - Identify adaptors requiring **transphosphorylation** (one receptor's kinase phosphorylates the other's substrate site):
    - These are activated only when both receptors are proxied — the biased signal
  - Identify adaptors requiring **cis-phosphorylation** (receptor phosphorylates its own substrate site):
    - These are activated regardless of proximity — part of the background signal
  - Identify adaptors **sterically excluded** by the proximity geometry (based on size/angle reasoning from step 2b)
  - Result: `{transphosphorylation_adaptors, cis_adaptors, excluded_adaptors}` — the **biased output map** (NOT the union of both receptor pathways)
  - **Uncertainty**: each assignment gets a confidence score from OmniPath evidence level (experimental > literature > prediction)
- 3b. **Reactome / KEGG** (direct API or Biomni free tier):
  - Transphosphorylation adaptors → downstream TF set (which TFs are activated by these adaptors)
  - Excluded adaptors → TFs that are suppressed
  - Result: `{TF_up: [...], TF_down: [...], pathway_activated: [...]}`
  - Confidence: high if single clear pathway, low if multiple plausible routes
- 3c. **OmniPath TF-target layer**:
  - TF_up → predicted upregulated genes
  - TF_down → predicted downregulated genes
  - Result: `biased_gene_signature {up: [...], down: [...]}`
  - Note: this gene set is the biased output — NOT the union of both receptor pathway gene sets
- 3d. **BioGRID ORCS** (free REST API):
  - Query CRISPR screen evidence in muscle cells for the predicted gene changes
  - Any published screen showing KO/OE of these genes in muscle, satellite cells, or related contexts?
  - Adds experimental confidence to the gene signature prediction

**Uncertainty propagation across steps 3a–3d**:
```
step_confidences = [c_3a, c_3b, c_3c, c_3d]  # each in [0,1]
mechanism_confidence = product(step_confidences)  # multiplicative propagation
```

**Record BEFORE continuing** — to `experience_buffer.jsonl`:
```json
{
  "iteration": i,
  "receptor_pair": ["ERBB2", "MET"],
  "linker_hypothesis": "flexible 15aa",
  "biased_output": {
    "transphosphorylation_adaptors": [...],
    "cis_adaptors": [...],
    "excluded_adaptors": [...]
  },
  "TF_up": [...], "TF_down": [...],
  "predicted_up_genes": [...], "predicted_down_genes": [...],
  "pathway_activated": [...],
  "mechanism_narrative": "When ERBB2 and MET are held at ~60Å separation by the novokine, GRB2 and GAB1 are transphosphorylated by MET's kinase acting on ERBB2's Y1139 substrate site, activating RAS-MAPK and PI3K-AKT. PLCγ1 is excluded because its tandem SH2 domain cannot bridge the ERBB2/MET interface geometry...",
  "step_confidences": {"3a": 0.75, "3b": 0.68, "3c": 0.72, "3d": 0.45},
  "mechanism_confidence": 0.165,
  "literature_refs": [...]
}
```

**Gate**: if mechanism_confidence < 0.10 → reward = BAD, stop iteration (no point continuing with an incoherent mechanism).

**Visualization note**: the hypothesis tree should be rendered as a DAG (directed acyclic graph):
- Root: receptor pair
- Branch 1 per linker/geometry assumption
- Each branch: adaptor layer → TF layer → gene layer
- Node color: confidence score (green = high, red = low)
- Multiple competing hypotheses are shown as parallel branches, not collapsed to one

---

### Step 5 — TRANSCRIPTOME PREDICTION (zero-shot, no user data)

**Tool**: Three parallel tracks using free APIs; input is the biased_gene_signature from step 3–4 (NOT the union of both receptor pathway gene sets)

**Reweighted in v2 post-critique.** v1 placed CMAP at 0.35 and atlas-overlap at 0.40. Critique: CMAP self-replication is ~17% (Lim & Pavlidis 2021), reference panel is overwhelmingly cancer cell lines (no muscle/myoblast representation), and DoRothEA-based TF-target prediction skips multiple causal layers. v2 reweights to make direct atlas overlap dominant.

**Track A — Atlas overlap** (PRIMARY, weight 0.50, pure Python, zero cost):
- Direct overlap of `biased_gene_signature` against the muscle aging atlas reference. Two atlas versions available:
  - **v1 (default)** — single-source pooled atlas derived from Lai 2024 + fibroblast aging CSVs. Used by all 79 overnight RL runs (preserves experience-buffer reproducibility).
  - **v2 multi-source consensus** — built from 5 independent studies via `backend/scripts/build_consensus_atlas.py`:
    - GSE164471 (Tumasian 2021, vastus lateralis bulk Y/O)
    - GSE111016 (Pillon 2019, Singapore Sarcopenia case-control bulk)
    - GTEx v11 (818 donors, continuous limma-trend)
    - Kedlian/Lacraz 2024 Nat Aging (sc/sn-RNA pseudobulk DEGs)
    - Lai 2024 Nature HLMA (age-correlation per cell type)
    - Consensus rule: gene must be up-in-aged in ≥2 sources for `P1_up`, ≥2 sources down-in-aged for `P2_up`. Per-gene provenance recorded.
- Compute: `biased_gene_signature.up ∩ P2_up_genes` → Fisher exact + Jaccard
- Compute: `biased_gene_signature.down ∩ P1_up_genes` → suppressing aged markers
- Score: `track_A = (P2_overlap_score - P1_overlap_score)`, normalized to [-1, 1]
- Confidence: `min(1.0, -log10(fisher_p) / 5)` from Fisher exact test
- This is the strongest signal — direct, in-domain, statistical.
- Atlas selection: `phenotype_checkpoint.score_phenotype(atlas_version="v1"|"v2")` or `rl_loop.py --atlas-version v2`. Default remains v1.

**Track B — Mechanism coherence** (weight 0.30, uses Layer 1+2+3 from Step 3):
- Does the predicted adaptor → TF → gene chain form a coherent mechanism?
- Score components:
  - PhosphoSitePlus / ScanSite confidence for each adaptor recruitment claim (Layer 1)
  - DoRothEA A+B confidence for TF-target edges (Layer 2)
  - Reactome pathway-canonicalness score (Layer 3)
- Score: weighted sum of layer confidences, normalized [0, 1]
- This rewards mechanistic plausibility independent of atlas overlap (so a candidate can score well on both as concurrent evidence)

**Track C — Cross-domain perturbagen lookup** (weight 0.10, sanity filter only):
- Submit `biased_gene_signature` to **CLUE Query app** or **`/api/jobs` endpoint** with API key (v2 fix: v1 incorrectly stated `/api/perts`, which is for perturbagen metadata only — NOT signature query)
- Endpoint reference: clue.io documentation for L1000 query submission; `/api/perts` is metadata lookup, `/api/jobs` is for connectivity scoring
- Interpretation: directional sanity check — does the predicted signature look like ANY known perturbation, or like noise?
- **Off-domain caveat**: CMAP reference is overwhelmingly cancer cell lines (MCF7, A375, A549, PC3, HT29, HepG2, etc.); 17% self-replication rate; no muscle/myoblast in the core panel
- Use top-10 hit pattern as a low-weight prior, NOT as muscle-specific evidence
- Free tier requires clue.io account + access key + rate limits

**Track D — Biomni AUCell** (REMOVED in v2): The v1 plan claimed Biomni Phylo Lab supports AUCell regulon scoring as a routine workflow. This claim was unverified in Biomni public documentation. Removed pending direct vendor confirmation. If AUCell is needed, run pySCENIC AUCell module locally on GPFS using the Layer 2 OmniPath/DoRothEA TF-target network.

**Combined step 5 score (v2)**:
```
predicted_phenotype_score = 0.50 × track_A_score 
                          + 0.30 × track_B_score 
                          + 0.10 × track_C_score
# 0.10 weight remainder reserved for Phase 2 scGPT validation when data exists
chain_soundness = noisy_OR_aggregate([p_fail_step1..6])  # see §2.3
final_rank_metric = predicted_phenotype_score × chain_soundness
```

Top-K selection by `final_rank_metric` per batch; no binary gate.

---

### Step 6 — PHENOTYPIC CHECKPOINT (v2 — top-K ranking, no binary gate)

**Tool**: miniAgent/DeepSeek; pure Python computation

**v2 design — replace binary GOOD/BAD/NEUTRAL gate with top-K ranking**:

The v1 binary gate combined with multiplicative confidence collapsed (see §2.3). v2 uses continuous ranking.

- **Per-candidate metrics** (every candidate logged regardless of score):
  ```
  predicted_phenotype_score  ∈ [-1, 1]  (Track A + B + C combined)
  chain_soundness            ∈ [0, 1]   (noisy-OR over step failure probs)
  rank_metric                = predicted_phenotype_score × chain_soundness
  ```
- **Batch ranking** (per N iterations, e.g., per 100 candidates):
  - Sort batch by `rank_metric`
  - Take top-K for design (K = GPU budget for the batch / cost-per-design)
  - Send middle-tier (middle 33%) to human review queue
  - Bottom-tier logged for negative training signal but no further action
- **Calibration**: H2F is the positive control. It MUST appear in the top decile of any batch including it. If H2F drops below the 75th percentile, recalibrate `p_fail_i` and reweight tracks before proceeding with new candidates.

**Log to experience_buffer.jsonl** (every candidate, all fields):
```json
{
  "iteration": i,
  "receptor_pair": ["ERBB2", "MET"],
  "linker_option": "GS×4 flexible (~15 aa)",
  "hypothesis_prior_weight": 0.7,
  "biased_output": {...},
  "TF_up": [...], "TF_down": [...],
  "predicted_up_genes": [...], "predicted_down_genes": [...],
  "track_A_score": 0.62,    // direct atlas overlap (Lai 2024 + Lacraz 2024)
  "track_B_score": 0.45,    // mechanism coherence (PhosphoSitePlus + DoRothEA + Reactome)
  "track_C_score": 0.20,    // CLUE Query sanity check
  "predicted_phenotype_score": 0.495,
  "p_fail_per_step": [0.12, 0.18, 0.22, 0.15, 0.20, 0.10],
  "chain_soundness": 0.355,  // 1 - P(any step failed)
  "rank_metric": 0.176,
  "batch_percentile": 87,
  "decision": "TOP_K_DESIGN",  // or "MIDDLE_HUMAN_REVIEW", "BOTTOM_LOG_ONLY"
  "literature_refs": [...],
  "h2f_calibration_check_passed": true
}
```

---

### Design Step — Triggered for top-K candidates per batch (v2 — was binary gate)

**Cost reality (v2 addition — Cao/Baker library coverage caveat)**:

The v1 plan implicitly assumed many receptors have published minibinders that could be reused (skipping RFdiffusion). Critique: the Cao 2022 library + Baker lab subsequent disclosures cover ~12–30 therapeutic targets (PD-L1, IL-7Rα, TGF-β, IL-2Rβγ, HER2, IFNAR1/2, FGFR mb7, etc.) but this is **not exhaustive**. Most RTKs and rarer cytokine receptors have NO published minibinder, so de novo design is required for both halves of most novokine candidates.

**Cost implication**: budget for full RFdiffusion → ProteinMPNN → Boltz-1 design on BOTH chains for ~80% of top-K candidates. Only ~20% will benefit from a published binder for one chain. This roughly doubles the GPU cost per candidate vs. the v1 implicit assumption.

**Design step (v2)**:

**Tool**: miniAgent `novokine_design_handoff` skill → Superbio "Binder Design with Boltz-1" (paid GPU)

- `novokine_design_handoff` skill emits a structured design manifest:
  ```json
  {
    "target_receptor_A": "ERBB2",
    "target_receptor_B": "MET",
    "epitope_A": "domain III, residues 561-624",
    "epitope_B": "SEMA domain, residues 25-515",
    "linker_spec": "flexible GGGGS×4, ~15aa",
    "known_minibinder_A": "HER2_mb_Baker2023",  // or null if de novo needed
    "known_minibinder_B": null,  // de novo required (most pairs)
    "acceptance_filters_boltz1": {  // v2 fix: Boltz-1 specific thresholds
      "confidence_score_min": 0.6,
      "complex_pLDDT_min": 0.7,
      "iptm_rank_threshold": "top quartile",
      "ipsae_per_dunbrack_2025": "track but no hard threshold yet"
    },
    "minibinder_size_range_aa": [50, 110],
    "design_pipeline": "RFdiffusion -> ProteinMPNN -> Boltz-1",
    "storage_policy": "default_superbio_s3"  // or "user_owned_s3" for proprietary
  }
  ```
- **Verify the integrated workflow exists in your Superbio account** before committing — critique noted that "Binder Design with Boltz-1" as a single named pipeline could not be verified in the public app store, though all components (RFdiffusion, ProteinMPNN, Boltz-1) are exposed individually. Fall back to chaining the three apps manually via Co-Pilot if needed.
- **State-of-the-art comparator (v2 addition)**: Periodically run **BindCraft** (Pacesa et al., Nature 2025, doi:10.1038/s41586-025-09429-6, 10–100% experimental success on cell-surface receptors) and **BoltzGen** (Stark et al., bioRxiv 2025.11.20.689494, ~66% nM-binder success) on the top-N candidates locally on GPFS as a comparator to RFdiffusion+ProteinMPNN+Boltz-1. Track which pipeline yields better experimental outcomes after wet-lab validation.
- Output: designed minibinder sequence(s) + Boltz confidence scores
- Append design outputs to the `experience_buffer.jsonl` entry

---

## Part 4 — Phase 2: When Experimental Data Exists

After lab synthesizes and tests the first designed novokines on aged muscle cells, scGPT becomes the ground truth verifier:

### Phase 2 — REVISED v2: scGPT zero-shot is NOT used

**Critique-driven revision**: v1 §7 acknowledged that scGPT zero-shot underperforms simple baselines (Kedzierska et al. Genome Biology 2025), then proceeded to use scGPT in zero-shot modes anyway. This is contradictory. v2 fix: replace zero-shot scGPT entirely.

| Phase 2 task | v1 plan | v2 plan |
|---|---|---|
| Reference mapping (does treated cell look like P2?) | scGPT Zero-Shot Reference Mapping (Superbio) | **scVI + scANVI** — Lopez et al., Nature Methods 2018; Xu et al. 2023; proven to outperform scGPT zero-shot on label transfer; runs on local GPU, no Superbio cost |
| GRN inference | scGPT GRN Inference (Superbio) | **pySCENIC** — Aibar et al. Nature Methods 2017; included in Biomni; runs locally; well-validated |
| Perturbation prediction | scGPT zero-shot perturbation | **scGPT FINE-TUNED** on actual treated/untreated muscle data — only mode where scGPT is competitive (Superbio Perturbation Prediction app supports this) |
| Combinatorial perturbation prediction | (not in v1) | **GEARS** — for predicting effects of novel receptor pair combinations after data accumulates |

### Loop upgrade path (v2)

- **Phase 1** (now, no user data): OmniPath/PhosphoSitePlus + atlas overlap (Lai 2024 / Lacraz 2024 muscle aging atlases) + low-weight CLUE Query → ranked candidate list, no GPU cost except design step
- **Phase 2** (after first experimental round): scVI+scANVI label transfer → does treated cluster with P2? Verified outcomes calibrate `p_fail_i` per §2.3
- **Phase 3** (mature, after sufficient training data): scGPT fine-tuned on muscle data replaces Track C; entire loop becomes data-grounded; GEARS for combinatorial prediction

### Storage privacy note (v2 addition)

Superbio default storage is encrypted S3 — uploaded data and design outputs persist on Superbio infrastructure unless the user mounts their own S3 bucket. For proprietary novokine designs, configure user-owned S3 in the Superbio account settings before uploading. The `novokine_design_handoff` skill should default to Superbio's default storage with a flag `--bring-own-s3` for proprietary work.

---

## Part 5 — Implementation Steps

### Ordered by ROI (highest impact first)

#### Step A — `muscle_atlas_DE.json` ✅ DONE (2026-05-02)
`backend/knowledge/muscle_atlas_DE.json` created from Lai 2024 (Nature) + fibroblast aging DEG CSVs.
- **P1_up** (77 genes, aged-enriched): stress/inflammation/cytoskeletal remodeling (EGR1, IL32, TXNIP, MYH9, MYF5, JUN)
- **P2_up** (536 genes, young-enriched): contractile/structural/mitochondrial (ACTA2, MYL9, MYH11, MT-CO2, IGFBP7)
- **FAP_P1_up / FAP_P2_up**: fibroblast-lineage (fibroblast_deseq2 + fibroblast CSV)
- Per-cell-type breakdown: MuSC, Myofiber, Myofiber_TypeI, Myofiber_TypeII
- Full `detailed` dict: log2fc + padj per gene
- Thresholds applied: padj < 0.05, |log2fc| > 0.5
- Raw CSVs stored in: `backend/knowledge/raw_degs/`
- Direction convention: `direction=up` in CSV = upregulated in aged (P1); `direction=down` = upregulated in young (P2)

#### Step B — Biology API tools ✅ DONE (2026-05-02)
**Architecture change from v2 plan**: implemented as LangChain `BaseTool` subclasses (not skills) so the agent calls them directly with structured Pydantic inputs and typed outputs.

Four new tools built and registered in `backend/tools/__init__.py`:

- **`OmnipathApiTool`** (`backend/tools/omnipath_api_tool.py`): query types `interactions`, `tf_target`, `kinase_substrate`, `enz_sub`. No API key. Base URL `https://omnipathdb.org`.
- **`ReactomeApiTool`** (`backend/tools/reactome_api_tool.py`): query types `pathway_for_entity`, `pathways_for_genes`, `pathway_hierarchy`, `entities_in_pathway`. No API key. **Critical fix**: UniProt accession mapping uses `/data/mapping/UniProt/{acc}/pathways`, not the `/data/pathways/low/entity/` endpoint (which returned 404). Smoke tested: 37 pathways for EGFR (P00533).
- **`BiogridOrcsTool`** (`backend/tools/biogrid_orcs_tool.py`): query types `search_genes`, `screen_results`, `screens_for_gene`. Requires `BIOGRID_ORCS_ACCESS_KEY` env var (free at thebiogrid.org). Returns clear error if key missing.
- **`PhosphositeTool`** (`backend/tools/phosphosite_tool.py`): query types `kinase_substrates`, `substrates_of_kinase`, `sites_for_protein`. Uses locally cached `Kinase_Substrate_Dataset` TSV in `backend/storage/phosphosite_cache/`. Returns download instructions if cache missing.

**Pending**: download PhosphoSitePlus `Kinase_Substrate_Dataset` TSV (free academic, https://www.phosphosite.org/staticDownloads) → `backend/storage/phosphosite_cache/`. Also register `BIOGRID_ORCS_ACCESS_KEY` in `backend/.env`.

#### Step C — CELLxGENE receptor expression query [1–2 hrs]
New skill: `backend/skills/cellxgene_expression/SKILL.md`
- Query CZI Cell Census API for gene expression in specific cell types and age groups
- Filter: aged (≥65) human skeletal muscle cells
- Return: list of expressed receptor genes (TPM > threshold) with expression level
- Free REST API, no registration required
- Use to filter step 1 candidates to receptors actually expressed in the target cell

#### Step D — P1/P2 phenotypic checkpoint function [1 hr]
New Python utility (not a skill — called directly from `rl_loop.py`):
- `backend/utils/phenotype_checkpoint.py`
- Input: predicted gene signature {up: [...], down: [...]}, path to `muscle_atlas_DE.json`
- Functions:
  - `fisher_exact_overlap(predicted_up, reference_up)` → (odds_ratio, p_value)
  - `jaccard(predicted_up, reference_up)` → float
  - `compute_phenotype_scores(signature, atlas)` → {P2_score, P1_score, predicted_phenotype, confidence}
- Pure Python + scipy.stats, zero cost

#### Step E — CMAP / L1000 live query ✅ PARTIALLY DONE (2026-05-04 evening)
Live polling wired in `backend/tools/clue_api_tool.py`:
- Auth via `user_key` header — verified working
- Perturbagen lookup (`_live_lookup_perturbagen`): live-tested (sirolimus, vemurafenib) ✅
- Submit (`_live_submit_query`): implemented, not yet fired (awaiting explicit auth)
- Poll (`_live_poll_job`): implemented, depends on submit
- **Pending**: fire one live CLUE submit to see the result tarball; then write the GCT parser (~50 LOC) to extract tau-ranked perturbagen list from `query_result.gct`
- CMAP API key already in `backend/.env` as `CMAP_API_KEY`

#### Step F — Update `COT_Rejuv_Pipeline` SKILL.md ✅ DONE (2026-05-02)
Rewritten to v2 with:
- Explicit CRITICAL BIOLOGICAL CONSTRAINT block at top: forced proximity biased signaling ≠ additive pathway union
- `requires_tools`: `omnipath_api`, `reactome_api`, `biogrid_orcs`, `phosphosite_plus`, `uniprot_api`, `ncbi_eutils`
- Step 3a: calls `omnipath_api(enz_sub)` + `phosphosite_plus(sites_for_protein)` → classifies adaptors into transphosphorylation / cis / excluded buckets
- Step 3b: calls `reactome_api(pathway_for_entity)` on **adaptors** (not receptors) → biased pathway set only
- Step 3c: calls `omnipath_api(tf_target)` filtered to DoRothEA A+B only
- Step 3d: calls `biogrid_orcs(search_genes)` for CRISPR muscle screen support
- Step 4: noisy-OR `chain_soundness = ∏(1 - p_fail_i)` across 6 steps
- Step 5: three-track scoring (Track A 0.50 atlas overlap / Track B 0.30 mechanism coherence / Track C 0.10 CLUE sanity)
- Step 6: H2F calibration check, decision tiers (`TOP_K_DESIGN` / `MIDDLE_HUMAN_REVIEW` / `BOTTOM_LOG_ONLY` / `INCOHERENT_LOG_ONLY`), full `experience_buffer.jsonl` log schema
- Verified: parses correctly via `scan_skills()` skills scanner

**Still needed**: human domain-expert review of the biological reasoning constraints before production use.

#### Step G — Biomni API integration [2–3 hrs — lower priority given v3 architecture]
With direct API tools in place (OmniPath/Reactome/BioGRID/PhosphoSitePlus), Biomni is now a fallback-only component for high-complexity synthesis queries. If still desired:
- Wrapper function: `backend/utils/biomni_client.py`
  - `query_biomni(prompt, tools=["pubmed", "biogrid", "reactome", ...])` → str response
  - Implement retry with daily-limit detection (HTTP 429 → flag for human)
  - Log all Biomni calls to `backend/logs/biomni_usage.log` (track daily quota)
- Use only in: step 1b receptor pair hypothesis (multi-DB synthesis), NOT in steps 3a–3d (direct tool calls are better there)

#### Step H — `rl_loop.py` ✅ DONE (2026-05-04)
`backend/scripts/rl_loop.py` built with `--mode score_only` (works) and `--mode full` (invokes live agent). Logs to `backend/knowledge/experience_buffer.jsonl`. H2F positive control smoke-tested end-to-end.

#### Step I — Superbio design wiring ✅ PARTIALLY DONE (2026-05-04)
- `workflows/engines/superbio/adapter.py`: `dispatch()` / `submit()` / `get_status()` / `download_results()` — full Spec-30 contract
- `workflows/alphafold2.yaml` + `workflows/runners/alphafold2.py`: AF2 workflow spec + runner
- `backend/scripts/run_workflow.py`: minimal DAG driver that runs any workflow YAML
- **Pending**: re-fire AF2 smoke test after `_coerce_aa_pairs` fix (estimated ~$1, needs user go-ahead)
- **Pending**: replicate AF2 wiring pattern for Boltz-2 (`workflows/boltz2.yaml`) and Protenix — same adapter, different `app_id`

#### Step I.5 — Track A.5 gene programs via scGPT GRN Inference ✅ DONE (2026-05-04 late evening)
**Strategy**: scGPT GRN Inference → 296 gene programs → classify young/aged by metagene differential → score candidates by program activation. Replaces the original 512-d cell embedding approach (which the scGPT Mapping app does not produce).

- `backend/tools/scgpt_programs_tool.py`: built (actions: `submit_grn`, `build_programs`, `score_geneset`, `show_programs`). Cache at `backend/storage/scgpt_cache/gene_programs.json`.
- GRN job `69f8f61cf5b5f7da20571932` completed; result downloaded; cache built (90 young-enriched, 76 aged-enriched, 130 neutral programs).
- `rl_loop.py stage_track_a5_score()` injects normalized score (`tanh(raw / 2.5)` ∈ [-1, +1]) into the candidate dict before composite reward; wired in both `score_only` and `full` modes.
- Sanity tested: H2F → +0.645 normalized A.5 (composite reward +0.731 TOP_K_DESIGN); anti-rejuv decoy → -0.929 (composite -0.077 INCOHERENT); neutral random → -0.080 (BOTTOM_LOG_ONLY).

#### Step J — Uncertainty visualization [3–4 hrs, future]
- After `rl_loop.py` is running, add a visualization script
- Read `experience_buffer.jsonl`
- Render hypothesis trees (DAG) with confidence-colored nodes using networkx + matplotlib or a simple HTML/D3 export
- Show: receptor pair → adaptor layer → TF layer → gene layer → phenotype score
- Multiple competing hypotheses shown as parallel branches

---

## Part 6 — Vibe Coding Classification

| Step | Component | Status | Thinking Level | Best Model | Vibe-codable? |
|---|---|---|---|---|---|
| A | `muscle_atlas_DE.json` | ✅ Done | Low — data serialization | **Haiku** | Yes — trivial |
| B | Biology API tools (OmniPath, Reactome, BioGRID ORCS, PhosphoSitePlus as LangChain tools) | ✅ Done | Medium | **Sonnet** | Yes |
| C | CELLxGENE expression query skill | ⬜ Next | Medium | **Sonnet** | Yes |
| D | P1/P2 phenotypic checkpoint (Fisher/Jaccard) | ✅ Done | Low | **Haiku** | Yes |
| E | CLUE/L1000 live query + GCT parser | 🔶 Partial (submit not fired; parser pending) | Medium | **Sonnet** | Yes |
| F | **COT_Rejuv_Pipeline SKILL.md rewrite** | ✅ Done | **Highest** — biological reasoning spec | **Opus 4.7** | Partial — human review still needed |
| G | Biomni API integration (fallback only, lower priority) | ⬜ Deferred | Medium | **Sonnet** | Yes |
| H | `rl_loop.py` orchestration | ✅ Done | Medium | **Sonnet** | Yes |
| I | Superbio dispatch wiring (AF2 + adapter) | 🔶 Partial (AF2 wired; smoke test needs re-run; Boltz-2/Protenix pending) | Medium | **Sonnet** | Yes (code); API access is human task |
| I.5 | Track A.5 gene programs (scGPT GRN) | ✅ Done (job complete, programs built, wired into rl_loop) | Medium | **Sonnet** | Yes |
| J | Uncertainty visualization (DAG rendering) | ⬜ Future | Medium | **Sonnet** | Yes |
| 2b | Kinase domain geometry check logic | ⬜ Future | High — structural biology reasoning | **Opus 4.7** | Partial — threshold values need human validation |

### Cannot be vibe-coded — human expert required

1. **Biased signaling selection criteria for Step 1** — the exact biological rules for what makes a receptor pair a valid novokine candidate (following H2F/Expòsit et al. geometry principles). Must be extracted from the papers by a domain expert and encoded into the SKILL.md. An LLM can draft but cannot validate.

2. **P1/P2 DE gene list (Step A human decision)** — which cell type subsets, which statistical thresholds, pseudobulk or single-cell DE, which age grouping boundaries. This determines everything downstream.

3. **COT_Rejuv_Pipeline biological reasoning spec** — the text that tells the LLM "this is NOT additive pathway union, it is forced proximity transphosphorylation with these specific geometric constraints." The most important intellectual work in the project. Must be reviewed by a biologist.

4. **Kinase domain geometry thresholds** — what kinase-to-substrate distance is acceptable? What extracellular domain size ratio is too large? These numbers must come from structural biology literature, not from LLM reasoning.

5. **Reviewing `experience_buffer.jsonl` after N iterations** — a human biologist must read the mechanistic narratives and validate whether the proposed mechanisms are biologically coherent before committing GPU budget to protein design.

6. **Superbio account/pricing decisions** — which plan, how many credits per week, whether to pay for automated API or stay on free Co-Pilot.

---

## Part 7 — Questions: Resolved (post-critique) + Still Open

### 7.1 Resolved by v2 revision

| # | v1 Question | v2 Resolution |
|---|---|---|
| 1 | Uncertainty propagation method? | **Noisy-OR with empirical calibration**, not multiplicative. Calibrate `p_fail_i` against H2F positive control. Replace binary gate with top-K ranking. |
| 2 | OmniPath adaptor layer completeness? | **Insufficient alone.** Use stack: PhosphoSitePlus + ScanSite + NetPhorest (residue) → OmniPath (network) → DoRothEA A+B / Reactome (pathway) → BioGRID ORCS (CRISPR). |
| 3 | AlphaFold for receptor geometry — alternatives? | **Hierarchy: PDB experimental > AF-Multimer/Boltz-2 on binder-ECD complex > AF on isolated ECD > UniProt annotation.** Most canonical receptors have PDB structures; AF on isolated ECD is rarely the right choice. |
| 4 | CMAP relevance for muscle aging? | **Off-domain (no muscle in core panel) and 17% self-replication.** Drop CMAP weight to 0.10 as sanity-only. Direct atlas overlap (Lai 2024 + Lacraz 2024) at 0.50 weight. |
| 5 | Multiple hypothesis management? | **Posterior-weighted ensemble across linker_options × receptor_pair.** Linker is now first-class action variable. Reward = posterior-weighted sum, not winner-take-all. |
| 6 | Zero-shot reward false-positive rate? | **Estimated 30–60%** based on CMAP self-replication (17%), DoRothEA A-confidence accuracy (~30% vs ChIP-seq), and scGPT zero-shot underperformance. The pipeline is a prioritizer, not an oracle. Top-K design only. |
| 7 | Biomni daily-limit fallback? | **Three-tier strategy**: free unlimited (OmniPath/UniProt/CELLxGENE/BioGRID direct HTTP) → free limited (Biomni Phylo Lab for multi-DB synthesis only) → self-hosted Biomni on GPFS for batch. Downgrade confidence if tier-2 unavailable; do not block loop. |
| 8 | ECD size ratio threshold? | **The 2× rule was fabricated and is removed.** No literature heuristic exists. H2F (ratio 1.94) is the calibration anchor. Asymmetric pairs flag for higher-priority structural validation, not rejection. |
| 9 | Linker as co-optimization target? | **Promoted to first-class action variable.** Per Edman 2024 (18 Å vs 54 Å qualitative differences), linker geometry is the dominant axis when receptor pair is fixed. Five linker options per pair, posterior-weighted. |
| 10 | scGPT zero-shot reliability? | **Drop scGPT zero-shot entirely.** Phase 2: scVI+scANVI for label transfer, pySCENIC for GRN, scGPT FINE-TUNED only for perturbation prediction once muscle-specific data exists. |

### 7.2 Still open — needs human or experimental input

1. **Calibration data scarcity**: H2F is a single positive control. Need at least one published novokine that does NOT cause muscle rejuvenation (negative control) to properly calibrate `p_fail_i`. Best candidates from Abedi 2025 (75 active pSTAT signalers, 925 inactive) — but pSTAT-active ≠ muscle-rejuvenating. Need to identify suitable negative controls from the muscle-rejuvenation phenotype space specifically.

2. **PhosphoSitePlus licensing for high-throughput automated queries**: PSP is free for academic use but has terms of service that may restrict bulk programmatic access. Verify before automated pipeline build-out.

3. **CZ Cell Census coverage of Lai 2024 / Lacraz 2024 atlases**: Confirm whether one or both atlases are mirrored in CZ Cell Census. If not, build the .h5ad fallback from `muscleageingcellatlas.org`.

4. **Superbio "Binder Design with Boltz-1" as a single named pipeline**: Critique flagged that this could not be verified in the public app store, though all components are exposed. Verify in the user's Superbio account before committing the design step to an integrated workflow vs. manual chaining.

5. **CLUE Query API access for muscle-relevant cell context**: clue.io requires a clue.io account + access key + has rate limits. Verify free academic tier is sufficient for the planned query volume.

6. **Open-source Biomni vs. Phylo Lab capability divergence**: OSS Biomni was frozen 2025-04-15. Phylo Lab has continued development. Track which capabilities are in which deployment when planning fallbacks.

7. **Whether to add ipSAE alongside ipTM in Boltz-1 acceptance criteria**: Dunbrack 2025 recommends ipSAE as superior to ipTM. Confirm Superbio's Boltz-1 implementation exposes ipSAE; if not, request it or compute post-hoc.

8. **Negative controls and decoy receptor pairs for validation**: How do we know the pipeline is not just confirmation-biased toward H2F-like outputs? Need a set of receptor pairs that should clearly NOT work (e.g., GPCRs as a sanity check that they score lower than RTK pairs; receptors not co-expressed in any muscle cell type).

---

## Appendix — Biomni: Open-Source vs. Phylo Lab (v2 addition)

These are NOT interchangeable. The open-source release was frozen on **2025-04-15** while the hosted platform has continued to evolve.

| Capability | Open-source (snap-stanford/Biomni, frozen 2025-04-15) | Phylo Lab (hosted, ongoing development) |
|---|---|---|
| Self-hosted | Yes — runs on GPFS | No — cloud only |
| Daily usage limit | None | Free tier limited; Pro tier 10× free; Enterprise unlimited |
| AlphaFold access | Available via local install | Available via hosted GPU |
| pySCENIC, GRNBoost2, AUCell | Yes, locally | Likely yes but verify in current docs |
| Biomni-R0 reasoning model | Available on HuggingFace | Integrated as agent backbone |
| Workflow updates after April 2025 | None | Continuous |
| Cost | Free (your compute) | Free tier + paid tiers |

**Track each capability separately.** Do not assume what is in OSS Biomni is also in Phylo Lab and vice versa. When the plan references "Biomni AlphaFold," specify which deployment.

---

## Appendix — Key File Locations

| File | Status | Purpose |
|---|---|---|
| `backend/knowledge/novokines.md` | ✅ exists | Canonical novokine knowledge base |
| `backend/knowledge/dev/plans/master_rejuvenation_rl_plan.md` | ✅ exists | **This file** — master plan |
| `backend/knowledge/muscle_atlas_DE.json` | ✅ created v3 | P1/P2 DE gene lists (77 P1_up, 536 P2_up, FAP layers, per-cell-type) |
| `backend/knowledge/raw_degs/` | ✅ created v3 | Source DEG CSVs (muscle, fibroblast, tcell, neural aging papers) |
| `backend/knowledge/experience_buffer.jsonl` | ✅ created v4 | RL loop experience log |
| `backend/skills/COT_Rejuv_Pipeline/SKILL.md` | ✅ rewritten v3 | Six-step CoT evaluator skill (v2 — forced proximity biased signaling) |
| `backend/skills/novokine_identification/SKILL.md` | ✅ exists | Propose step skill |
| `backend/skills/novokine_validation/SKILL.md` | ✅ exists | Validate step skill |
| `backend/skills/novokine_design_handoff/SKILL.md` | ✅ exists | Design step skill |
| `backend/tools/omnipath_api_tool.py` | ✅ created v3 | LangChain tool: OmniPath REST API (interactions, tf_target, enz_sub) |
| `backend/tools/reactome_api_tool.py` | ✅ created v3 | LangChain tool: Reactome REST API (pathway lookup, enrichment) |
| `backend/tools/biogrid_orcs_tool.py` | ✅ created v3 | LangChain tool: BioGRID ORCS CRISPR screen data |
| `backend/tools/phosphosite_tool.py` | ✅ created v3 | LangChain tool: PhosphoSitePlus kinase-substrate data (local cache) |
| `backend/tools/clue_api_tool.py` | ✅ live v5 | CLUE/L1000 query: submit/poll/lookup live; tarball parser pending |
| `backend/tools/scgpt_phenotype_tool.py` | ✅ created v4 | LangChain tool: scGPT Mapping phenotype scoring (Superbio app) |
| `backend/tools/scgpt_programs_tool.py` | ✅ created v4 | LangChain tool: scGPT GRN gene programs scoring (Track A.5) |
| `backend/utils/phenotype_checkpoint.py` | ✅ created v4 | P1/P2 Fisher exact + Jaccard overlap utility |
| `backend/utils/chain_soundness.py` | ✅ created v4 | Geometric-mean chain soundness calculator |
| `backend/scripts/rl_loop.py` | ✅ created v4 | RL loop orchestration (score_only + full modes) |
| `backend/scripts/scgpt_submit.py` | ✅ created v4 | scGPT Mapping/GRN Inference job submitter |
| `backend/scripts/run_workflow.py` | ✅ created v5 | Minimal DAG driver for workflow YAML specs |
| `workflows/alphafold2.yaml` | ✅ created v5 | AF2 workflow spec (Spec-30, external_engine=superbio) |
| `workflows/runners/alphafold2.py` | ✅ created v5 | AF2 runner (validate_sequence_set, poll_and_download, summarize) |
| `workflows/engines/superbio/adapter.py` | ✅ created v5 | Superbio dispatch adapter (submit, get_status, download_results) |
| `backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad` | ✅ downloaded v4 | Full muscle aging atlas (2.02 GB, 183k cells) |
| `backend/storage/atlases/SKM_balanced_30k.h5ad` | ✅ created v5 | Balanced 30k subsample (130 MB, 35k cells, 800 cap/group) |
| `backend/storage/scgpt_cache/gene_programs.json` | ⬜ pending GRN job | scGPT gene programs cache (built after GRN job lands) |
| `backend/storage/phosphosite_cache/` | ⬜ download needed | PhosphoSitePlus `Kinase_Substrate_Dataset` TSV (free academic) |
| `backend/skills/cellxgene_expression/SKILL.md` | ⬜ to create | CELLxGENE expression query skill (Step C) |
| `backend/utils/biomni_client.py` | ⬜ deferred | Biomni API wrapper (fallback only, lower priority) |

---

## Appendix — Key Papers

1. **H2F paper** (Baker / Ruohola-Baker, 2025) — HER2 + FGFR1/2c, muscle reprogramming
2. **Abedi, Expòsit, Coventry et al. (2025)** — high-throughput novokines, IFNAR1 hub. bioRxiv `10.1101/2025.10.12.681920v1`
3. **Expòsit, Abedi, Krishnakumar et al. (2025)** — geometric tuning, rigid scaffold, pSTAT bias. bioRxiv `10.1101/2025.10.12.681819v1` ← KEY for kinase geometry reasoning
4. **Silva / Yang / Baker et al. (2022)** — antikines and novokines conceptual framing. Thieme `10.1055/s-0042-1748728`
5. **Zhao et al., Nature (2025)** — synthekines, T cell state diversification. PMID `40804519`
6. **Edman et al., Cell (2024)** — FGF oligomers, FGFR1/2c minibinder C6-79C-mb7. DOI `10.1016/j.cell.2024.05.025`
7. **Pacesa et al., Nature (2025)** — BindCraft
8. **BoltzGen** (Stark et al., MIT, 2025) — bioRxiv `10.1101/2025.11.20.689494v1`
9. **ProteinDJ** — bioRxiv `10.1101/2025.09.24.678028v2`
