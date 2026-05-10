# Next Actions — Novokine RL Loop

*Updated: 2026-05-05 evening. Session focus: real data for Tracks B + C, plus v2 multi-source consensus atlas.*

---

## ✅ Completed today (2026-05-05)

### Track B — PhosphoSitePlus parser bugs FIXED
Two latent bugs in `backend/tools/phosphosite_tool.py` were silently returning **zero or wrong** kinase-substrate data through all 79 overnight RL runs:
1. **Metadata preamble** (3 non-data lines: date stamp, license, blank) was being fed to `csv.DictReader` as the column header → `row.get("KINASE")` always None → 0 results. Fix: scan forward for `GENE\t...KINASE` line, slice from there.
2. **Substring match** (`gene in kin_gene`) false-matched "EGFR" against "VEGFR1/2/3", "AKT" against "AKT1/2/3", etc. Fix: exact match only.
3. Confidence sort added (in-vivo+in-vitro → in-vivo → in-vitro → neither).

Verification: EGFR → 126 substrates (STAT3-Y705, SRC-Y416, GAB1-Y627); AKT1 → 26 sites (PDK1→T308, DNAPK→S473). All 79 prior runs scored Track B with **no real signal** — re-score is needed.

### Track C — CLUE/L1000 → local LINCS migration
- CLUE batch API (`/api/jobs`) returns HTTP 401 — moved to paid subscription model in 2026; academic Priority User access discontinued. Email to clue@broadinstitute.org auto-bounced.
- Built `backend/tools/lincs_local.py` — bidirectional Jaccard scoring over 11K+ paired signatures from Enrichr GMTs at `backend/storage/lincs_cache/`:
  - `LINCS_L1000_Chem_Pert_up/down.gmt` (33,132 chem perturbations)
  - `LINCS_L1000_Ligand_Perturbations_up/down.gmt` (96 ligands)
  - `LINCS_L1000_CRISPR_KO_Consensus_Sigs.gmt` (10,423 KOs)
- Scoring: `tau_like = (J(q_up,p_up) + J(q_dn,p_dn) − J(q_up,p_dn) − J(q_dn,p_up)) × 50`. Range ≈ [-15,+15], ~2s runtime, fully offline.
- `clue_api_tool.py` routes to local index when `CMAP_MODE=local` (default in `.env`).
- Validated: EGFR+IL6ST → biologically sensible mimics (TWS-119, PD-184352, afatinib) and reversers (decitabine, CX-5461).

### Boltz-2 / Protenix — confirmed BROKEN server-side
- 9 test submissions across all reasonable input formats (correct mode_id=1 / `running_mode='cpu'`, JSON-list Protenix format, reference Boltz-2 `seq1.a3m`, monomer + dimer + PDB inputs, MSA on/off, n_steps 50/100, n_cycles 1/5/10) — all fail at ~33–45s with `[Errno 2] No such file or directory: '*.tar.gz'`.
- Diagnosis: containers boot, run for ~40s, exit silently, post-processing tar bundle step crashes. Server-side issue; not fixable from our side.
- Built `backend/utils/superbio_predict.py` with `submit_alphafold2_prediction()` (working fallback, job `69f8fbdff5b5f7da20571936` confirmed) plus stub helpers + status flags `SUPERBIO_PROTENIX_BROKEN`, `SUPERBIO_BOLTZ2_BROKEN`, `SUPERBIO_AF2_WORKING`.

### v2 multi-source consensus atlas — infrastructure complete
New folder: `backend/knowledge/aging_studies/` with 5 study subfolders:
- **GSE164471** (Tumasian 2021 vastus lateralis bulk Y/O) — `deg_table.tsv` PENDING USER UPLOAD
- **GSE111016** (Pillon 2019 Singapore Sarcopenia bulk) — `deg_table.tsv` PENDING USER UPLOAD
- **GTEx v11** (818 donors, limma-trend continuous age) — `deg_table.tsv` PENDING USER UPLOAD
- **Kedlian/Lacraz 2024** (Nat Aging 4:727) — SI Table 3 fetched (`MOESM5_ESM.xlsx`, 6.9 MB, 471 thresholded calls)
- **Lai 2024 HLMA** (Nature 629:154) — SI Table 5 fetched (`MOESM7_ESM.xlsx`, 9.3 MB, 6,308 thresholded age-correlation calls)

Code:
- `backend/scripts/build_consensus_atlas.py` — multi-source ingest + ≥2-source voting + per-cell-type sub-blocks (handles missing sources gracefully)
- `backend/tests/test_consensus_atlas.py` — **14 passed, 2 skipped** (biology-sanity tests gated on bulk uploads)
- `backend/utils/phenotype_checkpoint.py` — added `atlas_version: Literal["v1","v2"]` param; v1 stays default for buffer reproducibility
- `backend/tools/phenotype_checkpoint_tool.py` — surfaces `atlas_version` to the agent
- `backend/scripts/rl_loop.py` — `--atlas-version {v1,v2}` CLI flag
- `backend/knowledge/dev/plans/master_rejuvenation_rl_plan.md` — v7 revision entry

Current v2 (Kedlian + Lai only): 6 P1_up + 23 P2_up consensus genes. Biology looks right (TXNIP, GPX3, NEAT1, SAT1 in P1_up; ANKRD2, TPM1, MYLPF, TRDN, IGF1 in P2_up). H2F → +0.6761 v1 / NEUTRAL v2 (sparse — expected without bulk uploads).

---

## 🔥 Immediate — awaiting user action

### 1. Bulk DEG ingestion — 4 of 5 sources present, only GTEx remaining

| Path | Source | Status |
|---|---|---|
| `backend/knowledge/aging_studies/GSE111016_pillon_2019/deg_table.tsv` | limma-voom on RNA-seq counts | ✅ **EXTRACTED FROM PAPER SUPP DATA 4** (16,861 genes; `consensus_thresholds: padj<0.10, |lfc|>0.3` per paper's published cutoff) |
| `backend/knowledge/aging_studies/GSE164471_tumasian_2021/deg_table.tsv` | PyDESeq2 ~ sex + condition (n=8 young / n=22 old) | ✅ **DERIVED VIA NEW AGENT-RUNNABLE TOOLING** — see below. 18,351 rows, 14 padj<0.05; CDKN1A/CDKN2B/EDA2R/OSTN at top |
| `backend/knowledge/aging_studies/gtex_v11_skeletal_muscle/deg_table.tsv` | limma-trend ~ sex + ischemic_time + age (818 donors) | ⏳ **USER UPLOAD NEEDED** — GTEx v11 raw data is dbGaP-gated for individual ischemic times; user's custom analysis cannot be reproduced from public files alone |

**v2 atlas state (4 of 5 sources)**: 9 P1_up + 29 P2_up consensus genes. Highlight: **C12ORF75 has 3-source support** (Tumasian + Kedlian + Lai). PLAG1 added by Tumasian.

### NEW: agent-runnable DESeq pipeline

Built today so future GEO datasets can be added without leaving the loop:
- **Script**: `backend/scripts/run_geo_deseq.py` — downloads GEO supplementary counts, parses sample metadata via regex, runs PyDESeq2 with arbitrary design, writes canonical aging-studies TSV.
- **Skill**: `backend/skills/bulk_rnaseq_de_runner/SKILL.md` — sibling to `differential_expression_helper` (which only interprets); this one executes.
- **Installed**: `pydeseq2 0.5.4`, `GEOparse 2.0.4`.
- **Validated end-to-end**: GSE164471 from URL → DEG TSV → consensus build → biology-correct top hits.

If a study's `padj` distribution doesn't reach < 0.05 (small-cohort issue), set `consensus_thresholds: {padj, abs_log2fc, rationale}` in that study's `metadata.json` and the builder applies the per-source cutoff.

After upload:
```bash
/gpfs/scrubbed/danlovuw/miniAgent/.py311/bin/python backend/scripts/build_consensus_atlas.py
/gpfs/scrubbed/danlovuw/miniAgent/.py311/bin/python -m pytest backend/tests/test_consensus_atlas.py -v
```
Bulk uploads will expand v2 from 6/23 to several thousand consensus genes; biology-sanity tests un-skip (canonical IEGs in P1_up, contractile/anabolic genes in P2_up).

### 2. Re-score top-3 overnight candidates with real Track B + C + v2 atlas
The 79-run sweep produced these mock-scored top-3:
- EGFR + IL6ST + flexible_GS8 — reward **+0.8638** (mock B + mock C)
- ERBB4 + INSR + rigid_helix_20 — reward **+0.8633**
- INSR + IL6ST + flexible_GS8 — reward **+0.8610**

After bulk uploads + v2 build, re-score with **all three reward tracks running on real, multi-source data for the first time**:
```bash
/gpfs/scrubbed/danlovuw/miniAgent/.py311/bin/python backend/scripts/rl_loop.py \
  --mode score_only \
  --atlas-version v2 \
  --input backend/knowledge/top3_candidates.json
```
Log delta vs mock-scored rankings to `backend/knowledge/dev/sessions/2026-05-05_v2_atlas_rescore.md`.

---

## 🏗 Stand-down state (no immediate action)

| Item | Status |
|---|---|
| Boltz-2 + Protenix | Code complete in `backend/utils/superbio_predict.py`; **broken server-side** at Superbio. Re-test only after Superbio fixes their containers. |
| AF2 BioAPEX path | Working — `submit_alphafold2_prediction()` validated on job `69f8fbdff5b5f7da20571936`. Use AF2 multimer for receptor pairs. |
| AF3 API | Deprioritized — AF2 is the active structure-validator path. |
| CLUE live API | Paid-subscription only (2026). Local LINCS is the production path; flip `CMAP_MODE=live` + paid sub to re-enable. |
| scGPT GRN | Job `69f8f61cf5b5f7da20571932` complete; programs cached at `backend/storage/scgpt_cache/gene_programs.json`. |

---

## 📚 Where to read

- [`plans/master_rejuvenation_rl_plan.md`](plans/master_rejuvenation_rl_plan.md) — master design doc (**v7** as of 2026-05-05; multi-source consensus atlas section in Track A)
- [`sessions/`](sessions/) — chronological session writeups
- [`backend/knowledge/aging_studies/README.md`](../aging_studies/README.md) — v2 atlas study index + how to extend
- [`backend/knowledge/aging_studies/_schema.md`](../aging_studies/_schema.md) — canonical DEG TSV column convention

---

*Updated 2026-05-05 evening (post-overnight + post-Track-B/C/v2 atlas wiring).*
