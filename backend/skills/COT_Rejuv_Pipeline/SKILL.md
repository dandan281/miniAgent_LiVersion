---
name: COT_Rejuv_Pipeline
description: Six-step chain-of-thought pipeline that mechanistically scores a candidate novokine for its ability to shift human skeletal muscle cells from an aged (65+) to a young (25–35) transcriptional phenotype. Produces a continuous rank metric usable by the RL outer loop. v2 — forced-proximity biased signaling, noisy-OR uncertainty, top-K ranking.
category: bio/rejuvenation
version: 2.0
requires_tools: [search_knowledge_base, fetch_url, read_file, python_repl, write_file, omnipath_api, reactome_api, biogrid_orcs, phosphosite_plus, uniprot_api, ncbi_eutils]
requires_network: true
user_invocable: true
tags: [novokine, rejuvenation, muscle, chain-of-thought, reinforcement-learning, signaling, omnipath, reactome, biogrid, phosphosite]
aliases: [novokine_rejuvenation_cot, muscle_rejuv_scorer]
species: human
modality: protein_design
stage: in_silico_evaluation
stability: evolving
safety_level: medium
---

# COT_Rejuv_Pipeline — Chain-of-Thought Novokine Rejuvenation Scorer (v2)

## Purpose

Given a candidate **novokine** (a designed protein dimer fusing two minibinders targeting two cell-surface receptors), execute a six-step mechanistic chain of thought that ends in a continuous rank metric indicating how much the novokine is predicted to shift human skeletal muscle cells from the **aged** phenotype (P1: ≥65 years) toward the **young** phenotype (P2: 25–35 years), as defined by differential expression in the human skeletal muscle cell atlas (Lai et al. 2024, Lacraz et al. 2024).

This skill is the **inner CoT evaluator** of the RL system. The RL outer loop proposes novokines; this skill returns the per-novokine rank metric.

---

## CRITICAL BIOLOGICAL CONSTRAINT — Read before every execution

**Novokine signaling is NOT the union of two receptor pathways. It is FORCED PROXIMITY BIASED SIGNALING.**

- A single minibinder antagonizes its receptor.
- The fused novokine dimer forces two receptors into physical co-clustering, enabling **transphosphorylation**: receptor A's kinase phosphorylates substrate sites on receptor B, and vice versa — events that cannot occur when the receptors are spatially separated.
- The biased signaling output is determined by which **adaptor proteins can productively dock** at the co-clustered intracellular domains given the specific **kinase-to-substrate geometry** enforced by the linker.
- **Adaptors requiring transphosphorylation**: activated only under forced co-clustering → these define the novokine's unique biased output.
- **Adaptors requiring cis-phosphorylation only**: present in both the novokine signal and in natural single-receptor activation → these are background, not the distinguishing biased output.
- **Sterically excluded adaptors**: physically blocked by the co-clustering geometry → suppressed relative to natural activation → this is the "off" side of the bias.

Reference exemplar — **H2F (HER2 + FGFR1/2c)**:
- Transphosphorylation activates: MAPK/AKT (GRB2-SHC-RAS-ERK, PI3K-AKT-mTOR)
- Sterically excluded: PLCγ/Ca²⁺ branch (PLCγ cannot bridge the HER2-FGFR1 geometry)
- Functional outcome: reprograms fibroblasts → muscle, enhances myotube maturation, sustains stem-cell pluripotency
- H2F is the **positive control**: any batch including H2F must place it in the top decile; if not, recalibrate.

Reference: Expòsit et al. 2025 — rigid scaffold geometry biases pSTAT pathway usage.
Reference: Edman 2024 — 18 Å vs 54 Å linker produces qualitatively different FGFR signaling.

**Do NOT compute the union of receptor A's pathways and receptor B's pathways. That is wrong.**

---

## Inputs

- **novokine_id**: name/handle (e.g. `H2F`, `cand_0042`)
- **receptor_A**: gene symbol of receptor targeted by minibinder A (e.g. `ERBB2`)
- **receptor_B**: gene symbol of receptor targeted by minibinder B (e.g. `FGFR1`)
- **linker_option**: one of the five standard linker geometries (see Step 1d below); defaults to `"flexible_GS4"`
- **uniprot_A** (optional): UniProt accession for receptor A — will be looked up if absent
- **uniprot_B** (optional): UniProt accession for receptor B
- **cell_context**: default `human skeletal muscle cell` (myoblast / myotube / satellite cell / FAP)
- **atlas_de_path**: path to `knowledge/muscle_atlas_DE.json`; if absent, use `search_knowledge_base` for "muscle atlas P2 P1 DE"
- **hypothesis_prior_weight**: float in [0.2, 1.0] assigned by the proposal policy (1.0 = exact H2F template match, 0.2 = pure novel)

---

## Uncertainty model — noisy-OR (v2, replaces multiplicative)

Each step produces a **step failure probability** `p_fail_i ∈ [0,1]`. These are aggregated via noisy-OR:

```
chain_soundness = 1 - P(any step failed)
               = 1 - [1 - ∏(1 - p_fail_i)]
               ≈ ∏(1 - p_fail_i)   for small p_fail values
```

Calibrate `p_fail_i` against H2F (positive control): H2F must reach `chain_soundness ≥ 0.30` with its known mechanism. Typical baseline values per step:

| Step | Baseline `p_fail_i` | What inflates it |
|------|---------------------|-----------------|
| 1 — receptor expression | 0.05 | receptor absent in target cell type |
| 2 — structural geometry | 0.20 | no PDB structure, large ECD asymmetry |
| 3a — OmniPath adaptor layer | 0.15 | sparse OmniPath evidence for this receptor |
| 3b — Reactome pathway | 0.12 | receptor is an orphan or poorly annotated |
| 3c — TF-target layer | 0.20 | DoRothEA confidence < A/B |
| 3d — BioGRID CRISPR evidence | 0.25 | no muscle-relevant screens |

**Do not use a binary gate**. All candidates are scored and logged. The outer RL loop ranks by `rank_metric = predicted_phenotype_score × chain_soundness`.

---

## The Six-Step Chain of Thought

Execute in order. Write each structured block to scratch before proceeding. The audit trail is the point — do not skip or compress steps.

---

### Step 1 — Receptor engagement & linker geometry

**Question**: Are both receptors expressed in aged skeletal muscle, is forced-proximity agonism mechanistically defensible, and what does the linker geometry imply about the intracellular domain spacing?

**Actions**:

1a. **Receptor identity** — call `uniprot_api` with `query=gene_exact:{receptor_A}` and `query=gene_exact:{receptor_B}` to retrieve:
- UniProt accession, protein family, domain architecture (extracellular domain length in aa, transmembrane position, kinase domain position)
- If accessions were provided as input, use those directly.

1b. **Expression in target cell** — call `search_knowledge_base` with query `"{receptor_A} {receptor_B} skeletal muscle expression aged"`. If no result, call `fetch_url` to Human Protein Atlas (`https://www.proteinatlas.org/GENENAME/tissue`) for each receptor. Confirm both are expressed (TPM > 1 or annotated "medium"/"high") in myoblast, myotube, satellite cell, or FAP in aged human skeletal muscle.
- If either receptor is absent from the target cell type: set `p_fail_1 = 0.80` and flag `co_expression_risk = true`. Do not stop — log and continue.

1c. **Receptor family check** — confirm both receptors are RTKs, cytokine/JAK-STAT receptors, TGF-β type I/II pairs, or TNFR superfamily members. These are the receptor classes where transphosphorylation-driven agonism is mechanistically established. If either receptor is a GPCR, ion channel, or nuclear receptor: set `p_fail_1 += 0.30` and note scope limitation (NOT a biological impossibility, just outside H2F-template evidence).

1d. **Linker geometry** — record the `linker_option` and its approximate end-to-end distance:
```
"flexible_GS4"     → ~20 Å  (GGGGS×4, ~15 aa)
"flexible_GS8"     → ~40 Å  (GGGGS×8, ~30 aa)
"rigid_helix_20"   → ~30 Å  (α-helix, 20 aa)
"rigid_helix_40"   → ~60 Å  (α-helix, 40 aa)
"exposit_rigid"    → geometry-defined (Expòsit-style scaffold)
```
Estimate the implied intracellular kinase-to-substrate spacing using: ECD lengths from 1a + transmembrane helix (~25 aa, ~37 Å) + juxtamembrane linker (~15 aa). Flag as `geometry_asymmetry_high = true` if |ECD_A_length - ECD_B_length| > 200 aa (informational flag — not a reject criterion; H2F itself has a 1.94× ratio).

**Compute `p_fail_1`** (default 0.05; adjust per above).

**Block to write**:
```
### Step 1 — Receptor engagement
- Receptor A: {symbol} | UniProt: {acc} | family: {RTK/cytokine/...} | ECD: {N} aa | expressed in {cell_context}: {yes/low/no/unknown}
- Receptor B: {symbol} | UniProt: {acc} | family: {RTK/cytokine/...} | ECD: {N} aa | expressed: {yes/low/no/unknown}
- Co-expression confirmed: {yes/no/unknown}
- Linker: {linker_option} → ~{D} Å end-to-end
- Geometry asymmetry flag: {true/false} (|ECD_A - ECD_B| = {N} aa)
- Forced-proximity agonism defensible: {yes/partial/no} — {one-sentence reason}
- p_fail_1: {value}
```

---

### Step 2 — Structural geometry & natural dimerization check

**Question**: Do we have structural evidence for the receptor ECDs? Does this pair naturally dimerize (which would reduce novelty value)?

**Actions**:

2a. **Structure availability** — call `ncbi_eutils` (PubMed search) for `"{receptor_A} {receptor_B} crystal structure extracellular domain"`. Also check via `fetch_url` to PDB search (`https://www.rcsb.org/search/` with gene name). Classify:
- `PDB_experimental`: PDB structure exists for ECD of this receptor → highest confidence
- `AF_multimer`: AF-Multimer or Boltz-2 prediction on binder-ECD complex available
- `AF_isolated`: only AF prediction on isolated ECD
- `uniprot_annotation_only`: no structure, rely on domain lengths from UniProt

Record structure tier for each receptor. Set `p_fail_2` accordingly:
- Both PDB: 0.10; one PDB one AF: 0.18; both AF: 0.25; any annotation-only: 0.35

2b. **Natural dimerization check** — call `omnipath_api` with `query_type="interactions"`, `sources={receptor_A}`, `targets={receptor_B}` (and reverse). If a known interaction exists:
- Obligate natural hetrodimer → `novelty_flag = "low"` (note but do not reject; forced geometry may still differ)
- No known interaction → `novelty_flag = "high"` (preferred; forced pairing is the novel mechanism)

2c. **Geometric feasibility score**:
```
geo_confidence = 0.4 × structure_tier_score   # PDB=1.0, AF_multimer=0.7, AF_isolated=0.4, annotation=0.2
              + 0.3 × (1 - geometry_asymmetry_penalty)   # asymmetry_high → penalty=0.3, else 0.0
              + 0.3 × literature_evidence_score   # 1.0 if kinase domain geometry documented, 0.0 if not
```

Set `p_fail_2 = 1 - geo_confidence`.

**Block to write**:
```
### Step 2 — Structural geometry
- Structure tier A: {PDB_experimental/AF_multimer/AF_isolated/uniprot_annotation_only}
- Structure tier B: {same}
- Natural dimerization: {known/not_known} | novelty_flag: {high/low}
- geo_confidence: {value}
- p_fail_2: {value}
```

---

### Step 3a — OmniPath adaptor layer (BIASED OUTPUT MAP)

**Question**: Given these two receptors held in forced proximity, which adaptors are activated by transphosphorylation (the novokine's unique signal), which by cis-phosphorylation (background), and which are excluded?

**This is the mechanistic core. Do not use pathway union. Reason about transphosphorylation geometry.**

**Actions**:

3a-i. **Kinase-substrate edges for each receptor** — call `omnipath_api` twice:
```
omnipath_api(query_type="enz_sub", sources={receptor_A})   → receptor_A's known substrates
omnipath_api(query_type="enz_sub", sources={receptor_B})   → receptor_B's known substrates
```
Extract: phosphotyrosine (pY) sites on each receptor's intracellular domain and their documented kinases.

3a-ii. **PhosphoSitePlus cross-reference** — call `phosphosite_plus` with `query_type="sites_for_protein"` for each receptor. This gives residue-level SH2/PTB binding site data that OmniPath alone cannot resolve. Record all pY sites with documented adaptor-binding partners.

3a-iii. **Classify adaptors into three categories**:

- **Transphosphorylation adaptors** (the biased signal — unique to forced co-clustering):
  - These bind pY sites on receptor B that are normally phosphorylated by receptor B's own kinase in cis, BUT can also be phosphorylated in trans by receptor A's kinase when they are in proximity.
  - Call `phosphosite_plus(query_type="kinase_substrates", gene_symbol={receptor_A_kinase_domain})` to find what receptor A's kinase can phosphorylate outside its own receptor.
  - A pY site on receptor B that is: (a) in proximity to receptor A's kinase given linker geometry, AND (b) has documented SH2/PTB-binding adaptors → classified as transphosphorylation adaptor candidate.

- **Cis-phosphorylation adaptors** (background signal — present in natural single-receptor activation):
  - pY sites phosphorylated by the receptor's own kinase, activating adaptors regardless of co-clustering.
  - These are real signal but NOT the distinguishing biased output of the novokine.

- **Sterically excluded adaptors**:
  - SH2/PTB-domain proteins that cannot bridge the co-clustered receptor geometry.
  - Use geometry reasoning: if the adaptor requires simultaneous binding to pY sites on BOTH receptors but the linker geometry places those sites on opposite sides of the membrane complex → excluded.
  - Flag as excluded; these define the "off" side of the bias.

3a-iv. **OmniPath signed directed interactions** — call `omnipath_api` with `query_type="interactions"`, `sources={receptor_A},{receptor_B}`, `directed=True`, `signed=True`. This gives the downstream activity-flow graph from both receptors. Filter to keep only edges whose source adaptor is in the transphosphorylation set (step 3a-iii). Discard edges whose source is cis-only.

**OmniPath evidence confidence** — for each retained edge, record the evidence level:
- `experimental` (highest) → `edge_confidence = 0.85`
- `literature_curated` → `edge_confidence = 0.65`
- `predicted` → `edge_confidence = 0.40`

Set `p_fail_3a = 1 - mean(edge_confidence over transphosphorylation adaptors)`. If no transphosphorylation adaptors found: `p_fail_3a = 0.70`.

**Block to write**:
```
### Step 3a — Adaptor biased output map
- Transphosphorylation adaptors (biased on): {list with confidence}
- Cis-phosphorylation adaptors (background): {list}
- Sterically excluded adaptors (biased off): {list with reasoning}
- Biased output map: ON={transphosphorylation_adaptors}, OFF={excluded_adaptors}
- p_fail_3a: {value}
- OmniPath evidence coverage: {fraction experimental vs predicted}
```

---

### Step 3b — Reactome pathway mapping (downstream of BIASED adaptors only)

**Question**: What signaling pathways and transcription factors are activated downstream of the transphosphorylation adaptors identified in Step 3a?

**Do not query Reactome for the receptor directly. Query for the transphosphorylation adaptors. This is the downstream signal of the biased output — not the receptor's full canonical pathway.**

**Actions**:

3b-i. For each transphosphorylation adaptor from Step 3a, call:
```
reactome_api(query_type="pathway_for_entity", identifier={uniprot_accession_of_adaptor})
```
If the adaptor's UniProt accession is unknown, call `uniprot_api(query=gene_exact:{adaptor_gene})` first.

3b-ii. For excluded adaptors, call the same to identify which pathways are suppressed (because these adaptors won't be activated under forced proximity).

3b-iii. Consolidate:
- `pathway_activated` = pathways downstream of transphosphorylation adaptors
- `pathway_suppressed` = pathways downstream of excluded adaptors
- Flag any pathway that appears in both lists as `conflicted` — this indicates the model is uncertain about bias direction for this pathway.

3b-iv. For gene-set validation, run `reactome_api(query_type="pathways_for_genes", gene_list={comma_separated_transphospho_adaptors})` to get enriched pathway set across all biased adaptors together.

**Confidence**: if the activated pathways are canonical (MAPK, PI3K-AKT, JAK-STAT) with multiple adaptor lines of evidence → `p_fail_3b = 0.12`. If pathways are sparse or conflicted → `p_fail_3b = 0.30`.

**Block to write**:
```
### Step 3b — Pathway mapping (biased output)
- Pathways activated (via transphosphorylation adaptors): {list with Reactome IDs}
- Pathways suppressed (excluded adaptors): {list}
- Conflicted pathways: {list or none}
- TF set implied: {list — e.g. ELK1/FOS/JUN for MAPK; FOXO/mTORC1 for AKT; STAT3/5 for JAK}
- p_fail_3b: {value}
```

---

### Step 3c — TF-target layer (OmniPath DoRothEA A+B)

**Question**: What target genes are predicted to change expression given the activated/suppressed TF set from Step 3b?

**Actions**:

3c-i. For each TF in the activated set, call:
```
omnipath_api(query_type="tf_target", sources={TF_gene_symbol})
```
Retain only edges with DoRothEA confidence level A or B (filter by `confidence` field in OmniPath response; discard C/D/E as too noisy for reward signal).

3c-ii. For each TF in the suppressed set, do the same. These target genes will **fail to be induced** (or be relieved from repression) under the novokine treatment.

3c-iii. Build the biased gene signature:
```
predicted_up_genes   = union(TF_activated targets) − union(TF_suppressed targets)
predicted_down_genes = union(TF_suppressed targets) − union(TF_activated targets)
conflicted_genes     = intersection(TF_activated targets, TF_suppressed targets)
```
Resolve conflicts by majority TF count; flag unresolved as `±?`.

3c-iv. Muscle-specific cross-reference — check predicted_up_genes and predicted_down_genes against the canonical muscle rejuvenation marker set:
- Pro-myogenic / young markers (should be UP): PAX7, MYOD1, MYOG, MEF2C, MYH3, MYH2, IGF1, PPARGC1A (PGC-1α), MKI67
- Inflammaging / aged markers (should be DOWN): CDKN2A (p16), IL6, TNF, CXCL1, GDF15, NF-κB targets (NFKBIA, ICAM1, VCAM1)

**Confidence**: `p_fail_3c = 0.20` baseline; add 0.10 for each conflicted muscle-marker gene; subtract 0.05 for each pro-myogenic marker confirmed in predicted_up.

**Block to write**:
```
### Step 3c — TF-target gene signature (biased output)
- TFs activated → target genes (DoRothEA A+B only): {dict TF → top 10 targets}
- TFs suppressed → targets that fail to activate: {dict}
- Predicted up-regulated genes (top 30): {list}
- Predicted down-regulated genes (top 30): {list}
- Conflicted genes (±?): {list}
- Pro-myogenic markers in predicted_up: {list}
- Inflammaging markers in predicted_down: {list}
- p_fail_3c: {value}
- Write predicted gene signature to: scratch/cot_rejuv/{novokine_id}_biased_signature.tsv
```

---

### Step 3d — BioGRID ORCS CRISPR evidence

**Question**: Is there CRISPR screen evidence in muscle-relevant cell lines supporting the predicted gene changes?

**Actions**:

For each gene in the top-20 predicted_up and predicted_down lists, call:
```
biogrid_orcs(query_type="search_genes", gene_symbol={gene}, organism_id="9606", hits_only=True)
```

Filter returned screens for muscle-relevant context: keywords `muscle`, `myoblast`, `myotube`, `satellite`, `FAP`, `differentiation`, `atrophy` in screen name or description.

Score: fraction of predicted genes with muscle-relevant CRISPR evidence.
- `crispr_support_fraction` = (genes with muscle screen hit) / (genes queried)
- `p_fail_3d = 1 - min(1.0, crispr_support_fraction × 4)`  (so 25% hit rate → p_fail=0.0; 0% hit rate → p_fail=1.0)

If BioGRID ORCS key is unavailable: set `p_fail_3d = 0.30` (penalized for missing evidence, not failed).

**Block to write**:
```
### Step 3d — CRISPR evidence (BioGRID ORCS)
- Genes with muscle-relevant CRISPR screen hits: {list}
- Screens referenced: {list of screen IDs / names}
- crispr_support_fraction: {value}
- p_fail_3d: {value}
```

---

### Step 4 — Mechanism narrative & chain soundness

**Question**: Does the proposed mechanism form a coherent causal chain from forced co-clustering to muscle rejuvenation?

**Actions**:

4a. Write a 3–5 sentence **mechanism narrative** in plain language:
- "When {receptor_A} and {receptor_B} are held at ~{D} Å by this novokine, {transphosphorylation_adaptors} are activated by transphosphorylation. This drives {pathway_activated}, activating TFs {TF_up} which induce {pro_myogenic_genes}. The {excluded_adaptors} cannot dock at this geometry, suppressing {pathway_suppressed} and reducing {inflammaging_genes}. This is analogous to H2F's MAPK/AKT-on, PLCγ-off mechanism, [and differs in that...]."

4b. **Compute chain soundness** (noisy-OR):
```python
p_fail = [p_fail_1, p_fail_2, p_fail_3a, p_fail_3b, p_fail_3c, p_fail_3d]
chain_soundness = 1.0
for p in p_fail:
    chain_soundness *= (1.0 - p)
# This is the noisy-OR approximation; interpret as P(all steps non-failed)
```

4c. **Soft threshold check**: if `chain_soundness < 0.05`, the mechanism is incoherent. Still log the full record to `experience_buffer.jsonl` but set `decision = "INCOHERENT_LOG_ONLY"` and return a degraded score. Do not stop iteration.

**Block to write**:
```
### Step 4 — Mechanism narrative & chain soundness
- Narrative: {3–5 sentences describing the biased signaling chain}
- p_fail per step: [p1, p2, p3a, p3b, p3c, p3d]
- chain_soundness: {value}
- Coherence flag: {OK / DEGRADED (< 0.10) / INCOHERENT (< 0.05)}
```

---

### Step 5 — Phenotypic scoring (three tracks)

**Input**: `predicted_up_genes` and `predicted_down_genes` from Step 3c (the biased gene signature — NOT a pathway union).

Load the atlas DE reference: `read_file(atlas_de_path)` → dict with keys `P2_up`, `P2_down`, `P1_up`, `P1_down`.

---

#### Track A — Atlas overlap (weight 0.50, PRIMARY signal)

In `python_repl`:
```python
import json
from scipy.stats import fisher_exact

with open(atlas_de_path) as f:
    atlas = json.load(f)

P2_up = set(atlas["P2_up"])
P1_up = set(atlas["P1_up"])
predicted_up = set(predicted_up_genes)
predicted_down = set(predicted_down_genes)
universe_size = 20000  # approximate human expressed gene count

# Young signature overlap
up_in_P2 = len(predicted_up & P2_up)
table_up = [[up_in_P2, len(P2_up) - up_in_P2],
            [len(predicted_up) - up_in_P2, universe_size - len(P2_up) - len(predicted_up) + up_in_P2]]
OR_up, p_up = fisher_exact(table_up, alternative="greater")

# Aged marker suppression
down_in_P1 = len(predicted_down & P1_up)
table_down = [[down_in_P1, len(P1_up) - down_in_P1],
              [len(predicted_down) - down_in_P1, universe_size - len(P1_up) - len(predicted_down) + down_in_P1]]
OR_down, p_down = fisher_exact(table_down, alternative="greater")

import math
conf_up   = min(1.0, -math.log10(p_up + 1e-300) / 5.0)
conf_down = min(1.0, -math.log10(p_down + 1e-300) / 5.0)

jaccard_up   = up_in_P2 / (len(predicted_up | P2_up) + 1e-9)
jaccard_down = down_in_P1 / (len(predicted_down | P1_up) + 1e-9)

track_A_score = 0.6 * (conf_up + conf_down) / 2  +  0.4 * (jaccard_up + jaccard_down) / 2
# clamp to [-1, 1]; subtract penalty if predicted_up overlaps P1_up heavily
P1_contamination = len(predicted_up & P1_up) / (len(predicted_up) + 1e-9)
track_A_score = track_A_score - P1_contamination * 0.5
track_A_score = max(-1.0, min(1.0, track_A_score))
```

#### Track B — Mechanism coherence (weight 0.30)

Compute from data already gathered in Steps 3a–3d:
```python
# Layer 1: PhosphoSitePlus/OmniPath adaptor evidence quality
layer1_conf = mean(edge_confidence for transphosphorylation adaptors)  # from Step 3a

# Layer 2: DoRothEA A+B TF-target confidence
layer2_conf = fraction of TF-target edges that are DoRothEA A or B confidence

# Layer 3: Reactome pathway canonicalness
# A pathway is "canonical" if it appears in >10 publications (use Reactome hasDiagram=True as proxy)
layer3_conf = fraction of activated pathways with hasDiagram=True in Reactome response

track_B_score = 0.4 * layer1_conf + 0.35 * layer2_conf + 0.25 * layer3_conf
```

#### Track C — Cross-domain sanity check (weight 0.10)

Call `search_knowledge_base` with `"{top 5 predicted_up_genes} muscle aging perturbation"`. If the knowledge base contains CLUE Query results, extract the top similarity score as `clue_score ∈ [-1, 1]`.

If CLUE Query has not been run (typical in Phase 1): `track_C_score = 0.0` (neutral — not penalized for missing data).

If CLUE Query is available (CMAP_API_KEY set): call the CLUE API via `fetch_url` using `/api/jobs` endpoint (NOT `/api/perts`, which is perturbagen metadata only). Treat the result as a low-weight prior.

`track_C_score = clue_score` (or 0.0 if unavailable).

---

#### Combined score

```python
predicted_phenotype_score = (0.50 * track_A_score
                           + 0.30 * track_B_score
                           + 0.10 * track_C_score)
# Note: 0.10 remainder reserved for Phase 2 scGPT fine-tuned validation

rank_metric = predicted_phenotype_score * chain_soundness
```

**Block to write**:
```
### Step 5 — Phenotypic scoring
- Track A (atlas overlap, w=0.50): {value}  [P2_up overlap: {n} genes, p={p_up:.3e}; P1_up suppression: {n} genes]
- Track B (mechanism coherence, w=0.30): {value}  [layer1={l1:.2f}, layer2={l2:.2f}, layer3={l3:.2f}]
- Track C (CLUE sanity, w=0.10): {value}  [available: yes/no]
- predicted_phenotype_score: {value}
- chain_soundness: {value}  (carried from Step 4)
- rank_metric: {value}
```

---

### Step 6 — Final ranking decision & H2F calibration check

**Actions**:

6a. **H2F calibration** — if `novokine_id == "H2F"` or if H2F has been scored in the current batch, check: does H2F's `rank_metric` exceed the current candidate's? If H2F scores below the 75th percentile of any batch it is in, emit a calibration warning: `"H2F_CALIBRATION_WARNING: recalibrate p_fail_i before proceeding"`.

6b. **Batch percentile** — if running inside a batch loop, the RL outer loop assigns this after sorting. If running standalone, set to `null`.

6c. **Decision tier**:
- `rank_metric >= 0.15` → `TOP_K_DESIGN` (recommend for protein design pipeline)
- `0.05 <= rank_metric < 0.15` → `MIDDLE_HUMAN_REVIEW` (flag for biologist inspection)
- `rank_metric < 0.05` → `BOTTOM_LOG_ONLY` (negative training signal; no design)
- `chain_soundness < 0.05` → `INCOHERENT_LOG_ONLY` (override any rank_metric value)

6d. Write the full record to `experience_buffer.jsonl` via `write_file`:
```json
{
  "iteration": null,
  "novokine_id": "{novokine_id}",
  "receptor_pair": ["{receptor_A}", "{receptor_B}"],
  "linker_option": "{linker_option}",
  "hypothesis_prior_weight": {hypothesis_prior_weight},
  "biased_output": {
    "transphosphorylation_adaptors": [...],
    "cis_adaptors": [...],
    "excluded_adaptors": [...]
  },
  "TF_up": [...],
  "TF_down": [...],
  "predicted_up_genes": [...],
  "predicted_down_genes": [...],
  "pathway_activated": [...],
  "pathway_suppressed": [...],
  "track_A_score": 0.0,
  "track_B_score": 0.0,
  "track_C_score": 0.0,
  "predicted_phenotype_score": 0.0,
  "p_fail_per_step": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
  "chain_soundness": 0.0,
  "rank_metric": 0.0,
  "batch_percentile": null,
  "decision": "TOP_K_DESIGN|MIDDLE_HUMAN_REVIEW|BOTTOM_LOG_ONLY|INCOHERENT_LOG_ONLY",
  "mechanism_narrative": "...",
  "h2f_calibration_check_passed": true,
  "literature_refs": []
}
```

**Block to write**:
```
### Step 6 — Final ranking
- rank_metric: {value}
- decision: {TOP_K_DESIGN | MIDDLE_HUMAN_REVIEW | BOTTOM_LOG_ONLY | INCOHERENT_LOG_ONLY}
- H2F calibration check: {passed / warning / N/A}
- Logged to experience_buffer.jsonl: yes
```

---

## Final output format

```
# Novokine CoT Report — {novokine_id} (v2)

**Receptor pair**: {receptor_A} + {receptor_B}
**Linker**: {linker_option}
**Mechanism**: forced proximity biased signaling
**rank_metric**: {value}
**decision**: {TOP_K_DESIGN | MIDDLE_HUMAN_REVIEW | BOTTOM_LOG_ONLY | INCOHERENT_LOG_ONLY}

{Step 1 block}
{Step 2 block}
{Step 3a block}
{Step 3b block}
{Step 3c block}
{Step 3d block}
{Step 4 block}
{Step 5 block}
{Step 6 block}

## Risks and caveats
- {any p_fail > 0.40 flags with explanation}
- {conflicted genes from Step 3c}
- {scope limitations from Step 1c}
- {missing data that would raise chain_soundness}

## Recommended next steps (if TOP_K_DESIGN)
- Submit to novokine_design_handoff skill → RFdiffusion → ProteinMPNN → Boltz-1 pipeline
- Acceptance thresholds (Boltz-1): confidence > 0.6, complex_pLDDT > 0.7, ipTM top quartile
- In vitro validation: H2F-style myotube formation assay on patient-derived myoblasts
- Phase 2: re-run this skill in predict mode after scRNA-seq on treated cells (scVI+scANVI label transfer)
```

If called by the RL outer loop (`output_format=json`), return only:
```json
{
  "novokine_id": "...",
  "receptor_pair": ["{receptor_A}", "{receptor_B}"],
  "linker_option": "...",
  "rank_metric": 0.0,
  "predicted_phenotype_score": 0.0,
  "chain_soundness": 0.0,
  "decision": "...",
  "report_path": "scratch/cot_rejuv/{novokine_id}_report.md",
  "buffer_path": "knowledge/experience_buffer.jsonl"
}
```

---

## Failure modes

- **OmniPath server down (502)**: use `fetch_url` directly to `https://omnipathdb.org/...` as fallback; if still unavailable, set all OmniPath-dependent `p_fail` values to 0.40 and continue in degraded mode. Do not block.
- **PhosphoSitePlus cache absent**: the `phosphosite_plus` tool will return download instructions. Set `p_fail_3a += 0.15` and rely on OmniPath alone for adaptor classification.
- **atlas_de_path missing**: `search_knowledge_base("muscle atlas P2 P1 DE")` — if not found, Track A cannot be computed. Set `track_A_score = 0.0`, `p_fail_5 = 0.80`, and note "atlas DE required to complete scoring".
- **receptor not found in OmniPath**: the receptor may be poorly annotated. Set `p_fail_3a = 0.55`, rely on Reactome only for pathway inference.
- **No transphosphorylation adaptors identified**: this means the mechanism model is undefined for this pair. Set `chain_soundness *= 0.30`, set `decision = "MIDDLE_HUMAN_REVIEW"` regardless of score, note "no transphosphorylation model available — forced proximity advantage unclear".

---

## Examples

- *"Score H2F (ERBB2 + FGFR1, flexible_GS4) in myoblasts."* → expected `decision = TOP_K_DESIGN`, `rank_metric > 0.15`. Use as positive control.
- *"Score IL6R + TNFR1 novokine."* → expected `decision = BOTTOM_LOG_ONLY` (inflammaging axis — both receptors drive NF-κB/SASP).
- *"Score IGF1R + MET, rigid_helix_40."* → expected MIDDLE or TOP (both pro-myogenic RTKs; IGF1R→PI3K-AKT, MET→MAPK; biased output should activate PAX7/MYOD axis).

---

## Related skills and knowledge

- [knowledge/novokines.md](../../knowledge/novokines.md) — canonical reference; H2F biology; receptor families; Expòsit/Abedi 2025 papers. **Read first** for any mechanistic reasoning.
- [knowledge/rejuvenation_rl_plan.md](../../knowledge/rejuvenation_rl_plan.md) — full v2 plan; uncertainty model §2.3; track weights; calibration spec.
- [knowledge/muscle_atlas_DE.json](../../knowledge/muscle_atlas_DE.json) — P1/P2 DE gene lists (Lai 2024, Lacraz 2024). Required for Track A.
- [novokine_identification](../novokine_identification/SKILL.md) — upstream: proposes receptor pairs and linker options.
- [novokine_validation](../novokine_validation/SKILL.md) — gate before this skill: structural sanity, expression check.
- [novokine_design_handoff](../novokine_design_handoff/SKILL.md) — downstream: triggered for TOP_K_DESIGN decisions.
