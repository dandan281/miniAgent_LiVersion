# Tool-Call Profiling & Optimization Analysis

**Date**: 2026-05-04 (overnight session)  
**Data**: 9 live full-mode agent runs, avg 62.9 tool calls / run

---

## 1. Tool Distribution (empirical, 566 total tool calls over 9 live runs)

| Tool | Calls | % | Notes |
|---|---|---|---|
| uniprot_api | ~54 | ~10% | 4–8 calls per run; receptor basic info + adaptor accession lookups (Step 3b) |
| omnipath_api | ~38 | ~7% | Steps 3a (enz_sub×2, interactions), 3c (tf_target per TF) |
| biogrid_orcs | ~54 | ~10% | Step 3d: 6 calls per run (top-20 gene set at ~3 genes/call) |
| fetch_url | ~55 | ~10% | PDB structure lookup (Step 2), literature (Step 2a), Protein Atlas fallback |
| python_repl | ~45 | ~8% | Track A Fisher, scGPT self-check, gene-list processing, CRISPR fraction calc |
| read_file | ~27 | ~5% | SKILL.md, muscle_atlas_DE.json ×2–3, biased_signature.tsv |
| local_atlas_query | ~18 | ~3% | 2 calls per run (1 per receptor; should be 1 batched call) |
| ncbi_eutils | ~20 | ~4% | PubMed search (Steps 2, 3a structure literature) |
| reactome_api | ~18 | ~3% | Steps 3b-i (per adaptor) and 3b-iv (multi-gene query) |
| phosphosite_plus | ~18 | ~3% | Step 3a-ii, 3a-iii per receptor |
| search_knowledge_base | ~27 | ~5% | Steps 1b fallback, 3c Track C, 5 calibration fallback |
| ensembl_api | ~18 | ~3% | **SPURIOUS** — agent converts gene symbols → Ensembl IDs before OmniPath calls; OmniPath accepts HGNC symbols directly |
| verification_agent | ~17 | ~3% | Meta-verification of output JSON; adds 3–8 tool calls overhead each time |
| write_file | ~9 | ~2% | Final output + intermediate scratch writes |
| Other | ~50 | ~9% | cellxgene_expression, scgpt_programs, ensembl, terminal |

---

## 2. Key Inefficiencies

### 2a. uniprot_api × 4–8 per run (should be ≤ 2)
The SKILL.md Step 1a calls `uniprot_api(gene_exact:{receptor})` for basic identity.
In practice the agent makes 4–8 calls because:
- 2 calls (one per receptor) for Step 1a basic lookup
- 2–4 additional calls for adaptor UniProt accessions in Step 3b ("call `uniprot_api` first if accession unknown")
- Extra calls when Step 2 structural geometry re-fetches domain info

**Fix implemented**: `_prefetch_receptor_context()` in `rl_loop.py` pre-injects UniProt accession + family + length for both receptors. Saves 2–4 calls.

### 2b. ensembl_api × 2 per run (should be 0)
OmniPath REST API accepts HGNC gene symbols directly. The agent is calling `ensembl_api` to convert EGFR → ENSG00000146648 before querying OmniPath, which is wrong/wasteful.

**Fix**: Added explicit instruction in `_FULL_AGENT_PROMPT_TEMPLATE`: "OmniPath accepts HGNC gene symbols directly — do NOT call ensembl_api for ID conversion."

### 2c. local_atlas_query × 2 per run (should be 1)
SKILL.md Step 1b says `genes=[receptor_A, receptor_B]` (batched), but agent often calls it once per receptor.

**Fix implemented**: `_prefetch_receptor_context()` calls the tool once with both genes and injects the result. Agent is told to skip local_atlas_query entirely.

### 2d. read_file(muscle_atlas_DE.json) × 2–3 per run (should be 0)
The file is read:
- During Step 3c-iv atlas calibration
- During Step 5 Track A scoring (in python_repl via `open(atlas_de_path)`)
- Sometimes again for verification

**Fix implemented**: `_prefetch_receptor_context()` injects P2_up/P1_up/P2_down/P1_down gene lists (top 40 each) directly. Agent is told to skip `read_file knowledge/muscle_atlas_DE.json`.

### 2e. python_repl for Track A scoring (should be 0 agent-side)
Agent runs Fisher exact test, Jaccard, phenotype_score computation in python_repl (Steps 5, 6).
This work is REDUNDANT — `rl_loop.py`'s `stage_phenotype_score()` does the same calculation externally.

**Fix**: Added explicit instruction: "DO NOT compute Track A/B/C scores or run Fisher exact tests — the outer RL loop handles all scoring."

### 2f. verification_agent calls (meta-tool overhead)
The agent sometimes invokes `verification_agent` to double-check its own output JSON. This adds 3–8 tool calls per invocation. While useful for quality, it's expensive for a tight RL loop.

**Recommendation (not yet implemented)**: Consider disabling `verification_agent` in RL mode by removing it from the tools list, or capping its use to TOP_K_DESIGN candidates only.

---

## 3. Expected Savings After Implemented Fixes

| Optimization | Calls Saved | Status |
|---|---|---|
| Pre-inject UniProt receptor metadata | 2–4 | ✅ Implemented |
| Pre-inject local atlas expression | 1–2 | ✅ Implemented |
| Pre-inject muscle_atlas_DE gene lists | 2–3 | ✅ Implemented |
| Block ensembl_api calls | 2 | ✅ Implemented (prompt instruction) |
| Block agent-side Track A scoring | 2–4 | ✅ Implemented (prompt instruction) |
| **Total estimated savings** | **9–15 calls** | **~15–24% reduction** |

Expected new average: ~48–54 tool calls / run (down from 62.9).

---

## 4. Measured Baseline vs New (partial data)

| Candidate | Run date | Tool calls | Reward | Tier |
|---|---|---|---|---|
| ERBB2+FGFR1 (×3, old) | 2026-05-04 | 72/74/80 | 0.71 max | TOP_K_DESIGN (1/3) |
| EGFR+IL6ST (first new) | 2026-05-04 | 67 | **0.8248** | TOP_K_DESIGN |
| EGFR+FGFR1 (new) | 2026-05-04 | TBD | TBD | running |

---

## 5. Reward Quality Analysis (9 completed runs)

| Pair | Tool calls | Reward | Tier |
|---|---|---|---|
| ERBB2+FGFR1 | 80 | 0.7122 | TOP_K_DESIGN |
| ERBB2+FGFR1 | 72 | 0.4854 | MIDDLE |
| ERBB2+MET | 57 | 0.4509 | BOTTOM |
| INSR+MET | 63 | 0.4318 | BOTTOM |
| ERBB2+FGFR1 | 74 | 0.4055 | BOTTOM |
| ERBB2+FGFR4 | 50 | 0.3772 | BOTTOM |
| ERBB2+FGFR2 | 70 | 0.3595 | BOTTOM |
| ERBB2+FGFR1 | 54 | 0.3425 | BOTTOM |
| FGFR1+IGF1R | 46 | 0.2541 | BOTTOM |

Key observations:
- More tool calls ≠ better reward (ERBB2+FGFR1 ran 3× with 54/72/80 calls, getting 0.34/0.49/0.71)
- Quality variance high (0.25–0.71) for same pair — prompt/priors content matters more than tool count
- EGFR+IL6ST at 0.8248 exceeds best H2F run by +0.11, suggesting atlas-seeded candidates outperform random RTK pairs
- Atlas-seed score correlates with RL reward: EGFR+IL6ST atlas_score=0.367, reward=0.82

---

## 6. Recommendations for Future Optimization

1. **Structured receptor cache** (backend/storage/receptor_cache.json): persist UniProt + atlas expression lookups across RL runs. Re-use without network call if <30 days old.

2. **Tool budget cap per run**: add `max_tool_calls=50` to `_run_agent_iteration`; if agent reaches 50 without writing JSON, force output with current best prediction.

3. **Remove verification_agent from RL session tools**: keep it for interactive sessions but exclude for RL batch runs.

4. **Consolidate biogrid_orcs queries**: Step 3d currently issues 1 query per gene. Batch into 3 calls of 7 genes each → saves ~3 calls.
