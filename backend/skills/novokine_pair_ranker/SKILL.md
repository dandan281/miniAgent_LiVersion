---
name: novokine_pair_ranker
description: Rank novokine receptor heterodimer pairs from screen readouts and biological features. Reproduces the Biomni-style pipeline (Edelson 2026) for fibroblast-to-myotube transdifferentiation — composite EXP score, v4.0 mechanistic model, scale-collision diagnosis, and v4.3 corrected unified ranking across all candidate pairs.
category: bio/literature
version: 1.0
requires_tools: [string_ppi, gtex_expression, go_annotations, uniprot_api, ncbi_eutils, search_knowledge_base, read_file, python_repl, write_file]
requires_network: true
user_invocable: true
tags: [novokine, receptor-pair, heterodimer, ranking, EXP-score, scale-collision, STRING, GTEx, GO, transdifferentiation, fibroblast, myotube]
aliases: [novokine_ranker, biomni_replication, exp_score_pipeline]
species: human
modality: protein_design
stage: interpretation
stability: evolving
safety_level: low
paths: [knowledge/novokine, artifacts/novokine, knowledge/novokines.md]
---

# Novokine Pair Ranker — Biomni-style Replication Pipeline

## Purpose

Given a working spreadsheet of screen readouts (e.g. `novokine_v43.xlsx`) plus a receptor gene list, **reproduce the two-stage Biomni → Python pipeline** described in Edelson (2026) entirely inside bioAPEX:

- **Stage A — feature extraction** for every receptor: GO biological processes, GTEx tissue expression, STRING PPI confidence, UniProt-derived receptor family. These are the same external sources Biomni used.
- **Stage B — modeling**: assemble a per-pair feature matrix, compute the composite **EXP** score for the tested pairs, fit the v4.0 mechanistic model on the Biomni features, diagnose the scale-collision artifact in the all-pairs ranking, then fit v4.3 (90 % v4.0 + 10 % novelty) to score every untested pair.

The output is a single corrected, unified xlsx ranking of all candidate pairs — tested by EXP, untested by v4.3 model score — separated into clearly labeled sheets so the scale collision can never recur.

## When to use

The user asks any of:

- "rank the novokine pairs"
- "reproduce the Biomni novokine pipeline"
- "score the untested pairs"
- "fix the scale-collision in `novokine_v43.xlsx`"
- "build the EXP score for these screen readouts"

or attaches a spreadsheet shaped like `novokine_v43.xlsx`.

## When NOT to use

- The user only wants the **proposal** step (which receptors to test) — use `novokine_identification` instead.
- The user wants to **design new minibinders** for a confirmed pair — use `novokine_design_handoff`.
- The user wants **single-cell expression** in muscle aging — use `local_atlas_query` / `cellxgene_expression`.

## Inputs you should expect (do NOT hardcode any of these)

The user provides these files, typically uploaded to `backend/knowledge/novokine/` or attached to the chat. Resolve actual paths via `search_knowledge_base` or by asking the user — do not assume hardcoded paths.

| Input | Conventional name | Content |
|---|---|---|
| Working spreadsheet | `novokine_v43.xlsx` | Per-pair assay readouts, prior v4.0 / v4.3 model scores, "All Pairs Ranked" sheet |
| Receptor gene list | `receptor_genes.tsv` | TSV with columns: `gene_symbol`, `family`, `uniprot_id` (uniprot_id optional — resolve via `uniprot_api` if blank) |
| Tested-pair assays | `tested_pairs.tsv` | TSV with columns: `receptor_a`, `receptor_b`, then one numeric column per assay (e.g. `desmin`, `ocr`, `secondary`, `myotube`). Column names define the assay axis — read them, don't assume. |
| Assay weights | `assay_weights.json` (optional) | JSON map `{assay_column_name: weight}` summing to 1.0. If missing, ask the user. |
| Construct decoder | `abedi_binder_library.md` (or `.pdf`) | Heterodimer naming-convention reference from Abedi et al. 2025 |
| Reference docs | `novokine_session_reasoning.pdf`, `novokine_ontology_and_biology.pdf` | Optional — context for prior Biomni interpretation |

If any of these are missing, stop and ask the user where to find them. Do not guess column names, weights, or thresholds.

## Steps

The pipeline is 11 steps total. Steps 1–5 are feature extraction (Biomni's role in the original); steps 6–11 are modeling (Python). Each step that touches external state should be its own tool call so the user can inspect inputs and outputs.

### Step 1 — Locate inputs

1. `search_knowledge_base` for `novokine_v43.xlsx` and the related TSV files. Confirm paths with the user if multiple matches.
2. `read_file` the optional construct decoder (`abedi_binder_library.md`) and reference PDFs to seed context.

### Step 2 — Resolve receptor identifiers

For every gene in `receptor_genes.tsv`:

1. If `uniprot_id` is blank: call `uniprot_api` with the gene symbol → UniProt accession.
2. Call `ncbi_eutils` with the gene symbol → Entrez Gene ID, official symbol, aliases, family hints.
3. Build a normalized table: `{gene_symbol, uniprot_id, entrez_id, official_symbol, family}`.

### Step 3 — Pull GO biological processes (mechanistic layer)

For each UniProt accession, call `go_annotations`:

```
go_annotations(
    gene_product_ids="P00533,P40189,P36897,...",
    aspect="biological_process",
    only_experimental=true,
    limit=50,
)
```

Group GO terms per gene. These feed the **mechanistic plausibility** layer.

### Step 4 — Pull GTEx tissue expression (generalizability layer)

For each gene, call `gtex_expression`:

```
gtex_expression(gene="EGFR", tissue_filter="Muscle,fibroblast,heart,adipose,blood")
```

Capture **median TPM** in skeletal muscle and cultured fibroblasts at minimum — these are the two tissues directly relevant to fibroblast→myotube transdifferentiation. The full tissue panel goes into `structured_payload.all_tissues_tpm` for downstream features.

### Step 5 — Pull STRING PPI confidence (novelty layer)

Send **all receptor symbols at once** to `string_ppi`:

```
string_ppi(
    identifiers="EGFR,IL6ST,TGFBR2,BMPR2,NTRK1,...",
    query_type="network",
    species=9606,
)
```

Returned `combined_score` (0–1) feeds the mechanistic prior. `novelty_score = 1 - combined_score` populates the novelty layer. **Pairs with no STRING edge get novelty_score = 1.0** (maximum novelty).

### Step 6 — Build the per-pair feature matrix

In `python_repl`, assemble a pandas DataFrame indexed by ordered pair `(receptor_a, receptor_b)`:

```python
import pandas as pd
features = pd.DataFrame(index=all_pairs, columns=[
    "family_a", "family_b", "family_cross",
    "gtex_muscle_a", "gtex_muscle_b", "gtex_fibro_a", "gtex_fibro_b",
    "go_bp_overlap",       # |GO_BP(a) ∩ GO_BP(b)|
    "string_combined",     # 0..1
    "novelty",             # 1 - string_combined
])
```

Persist a hash of the feature table so reruns are reproducible.

### Step 7 — Compute the composite EXP score (tested pairs only)

Use the assay weights from `assay_weights.json` (or whatever the user supplies). Do not hardcode them. The canonical formula is:

```python
def compute_exp_score(df, weights):
    """weights: dict mapping assay column name -> weight; weights must sum to 1.0."""
    for assay, w in weights.items():
        if assay not in df.columns:
            raise KeyError(f"Assay column {assay!r} missing from tested_pairs DataFrame")
        max_shift = (df[assay] - 1.0).clip(lower=0).max()
        if max_shift <= 0:
            df[f"{assay}_norm"] = 0.0
        else:
            df[f"{assay}_norm"] = (df[assay] - 1.0).clip(lower=0) / max_shift
    df["EXP"] = sum(w * df[f"{a}_norm"] for a, w in weights.items())
    return df
```

- `- 1.0` subtracts the untreated baseline so the score reflects induction only.
- `.clip(lower=0)` means suppression is not penalized.
- Dividing by `max_shift` normalizes against the best observed pair per assay.

Flag any pair with **off-scale** (saturating) values — e.g. orders of magnitude above the second-place pair — and exclude from normalization with a warning. The Biomni report calls these out explicitly (`EGFRcside_TGFbR2` in the original).

### Step 8 — Fit the v4.0 model (mechanistic features → EXP)

On the tested-pairs subset, fit a regression of EXP against the Biomni-style features (no experimental data):

```python
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import LeaveOneOut, cross_val_score
X = features.loc[tested].select_dtypes("number")
y = exp_scores.loc[tested]
model_v40 = RidgeCV().fit(X, y)
loo_r2 = cross_val_score(model_v40, X, y, cv=LeaveOneOut(), scoring="r2").mean()
pearson_r = X.assign(EXP=y).corr().loc["EXP", model_v40.feature_names_in_].rename(...)
```

Report Pearson r per feature and LOO R². The Biomni run got Pearson r ≈ −0.12 with LOO R² ≈ −0.04 — i.e. the v4.0 model fails empirically. **Do not hide this**; report it explicitly. The point of the pipeline is that v4.0 fails and v4.3 recovers.

### Step 9 — Diagnose the scale collision in the all-pairs sheet

If the user's spreadsheet has an "All Pairs Ranked" sheet (or similar), compare:

- EXP score range on the tested rows (typically 0.000 – 0.5)
- Model score range on the untested rows (typically 0.4 – 0.9)

If the **untested minimum exceeds the tested maximum**, every untested pair structurally outranks every tested pair — a unit-mismatch artifact, NOT biology. Flag every affected row in a `scale_collision_flags.tsv` artifact and propose a corrected unified ranking (Step 11) instead of using the buggy column directly.

### Step 10 — Network analysis & family-level permutation tests

Use `networkx` for the receptor graph, `scipy.stats` for permutations:

```python
import networkx as nx
G = nx.Graph()
for (a, b), exp in exp_scores.items():
    G.add_edge(a, b, weight=exp)
print("weighted degree:", sorted(dict(G.degree(weight="weight")).items(), key=lambda kv: -kv[1])[:10])
print("betweenness:", sorted(nx.betweenness_centrality(G, weight="weight").items(), key=lambda kv: -kv[1])[:10])
```

Run a 10 000-permutation test of family-cross enrichment (e.g. BMP/TGFβ × ERBB vs. random pairs). Report Z and p, and note explicitly that no FDR correction was applied (the family-level p-values are exploratory).

### Step 11 — Fit v4.3 and emit the corrected unified ranking

```python
v43 = 0.90 * v40_score + 0.10 * novelty   # weights are inputs, not hardcoded
ranked_tested   = sort tested pairs by EXP score, descending
ranked_untested = sort untested pairs by v43, descending
```

Write `artifacts/novokine_pair_ranker/<run_id>/novokine_ranking.xlsx` with at least these sheets (all data-driven, no hardcoded gene names or thresholds):

1. **`Tested EXP`** — the 64 tested pairs ranked by EXP score, with all assay readouts and per-assay normalized contributions visible.
2. **`Untested v4.3`** — every untested pair ranked by v4.3 score, with v4.0 and novelty as separate columns so the contribution split is visible.
3. **`Feature Matrix`** — the full per-pair feature table from Step 6.
4. **`Diagnostics`** — Pearson r per feature, LOO R², scale-collision flags, permutation test outputs.
5. **`Tier Summary`** — strong / moderate / weak / no-effect tier counts using thresholds from the user (or `[0.45, 0.25, 0.10, 0.0]` if they don't specify, surfaced as a flag).

Use `python_repl` (post-Fix-1) so the xlsx surfaces in the Files panel as an `artifact_ref`. The user should see one file appear in the right pane on completion.

## Outputs

- **One xlsx ranking** at `artifacts/novokine_pair_ranker/<run_id>/novokine_ranking.xlsx` (surfaces in the Files panel).
- **One markdown summary** at `artifacts/novokine_pair_ranker/<run_id>/summary.md` with the top 4 hits, the v4.0 failure metrics, the scale-collision count, and the permutation test outputs.
- **Top-of-summary table** with the four strongest hits identified by EXP score — `EGFR + IL6ST`, `EGFR + TGFBR2`, `BMPR2 + NTRK1`, `ERBB2 + PDGFRA` in Jacob's run, but **do not assume these names** — surface whatever the data shows.

## Anti-hardcoding rules

- Weights come from `assay_weights.json` or the user's prompt — never from this skill body.
- Gene/family list comes from the input TSV — no hardcoded gene names anywhere in code.
- Tier thresholds (strong/moderate/weak/no-effect) come from the user or surface as flagged defaults.
- Output paths are derived from a generated `run_id`, not constants.
- Species (default 9606) and dataset versions (default `gtex_v8`) are tool defaults but exposed as parameters — override when the user specifies.

## Cross-references

- The construct-name decoding step uses the Abedi et al. binder library; check `knowledge/novokine/` for the upload.
- The post-experimental update flow ties into `novokine_validation`. After a v4.3 prediction is experimentally tested, the new EXP scores should feed back into a v4.4 fit — that's a separate skill invocation.
- For follow-up design of novel minibinders against the top-ranked untested pairs, hand off to `novokine_design_handoff`.

## Known failure modes

- **openpyxl import error** if running on a backend without the `safe_import` level-0 fix — pip-install `xlsxwriter` and use `pd.ExcelWriter(..., engine="xlsxwriter")` as a workaround.
- **GTEx returns 0 rows** if `datasetId=gtex_v10` is forced — v10 has no expression data yet. Stick with `gtex_v8` until that ships.
- **STRING returns a different protein** when a gene symbol is ambiguous. If the agent sees a `preferredName` that doesn't match what the user typed, log it and confirm before proceeding.
- **QuickGO `goName` is null** unless `includeFields=goName` is passed — already handled inside `go_annotations`.
