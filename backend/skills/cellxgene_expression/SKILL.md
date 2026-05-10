---
name: cellxgene_expression
description: Query CZ Cell Census Where-My-Gene API for receptor expression in skeletal muscle cell types (MuSC, myofiber, fibroblast). Used to confirm both novokine receptors are co-expressed in the target cell population.
requires_tools: cellxgene_expression
version: "1.0"
---

# Cellxgene Expression — Confirm Receptor Co-expression in the Target Muscle Cell

## Purpose

Step C of the rejuvenation pipeline (see `COT_Rejuv_Pipeline/SKILL.md`). Before
spending design budget on a candidate novokine, confirm that **both receptors
of the proposed pair are expressed in the same muscle cell type at relevant
levels** in adult human muscle. A novokine that forces proximity between
receptors A and B can only act in a cell that simultaneously displays both A
and B on its surface — otherwise the biased-signaling mechanism cannot fire in
the target tissue, and the candidate fails biologically regardless of how well
it folds.

This skill calls the CZ Cell Census *Where My Gene* (WMG) summary API via the
`cellxgene_expression` tool and applies a simple co-expression decision rule.

## When to use

- After **PROPOSE** (Stage 1, `novokine_identification`).
- Before **MECHANISM** (Stage 3, mechanism scoring).
- Required for any candidate that survives **Stage 2 VALIDATE**
  (`novokine_validation`).
- Optional but recommended when adding a new receptor pair to the RL loop's
  initial pool.

## Inputs

- `receptor_A` — HGNC symbol of the first receptor (e.g. `FGFR1`).
- `receptor_B` — HGNC symbol of the second receptor (e.g. `ERBB2`).
- `target_cell_type` — free-text cell-ontology label, e.g.
  `"skeletal muscle satellite cell"` (MuSC),
  `"skeletal muscle myofiber"`, or
  `"fibroblast"`.

Optional:
- `tissue` — defaults to `"skeletal muscle"`.
- `organism` — defaults to `"Homo sapiens"`. (CZ Cell Census WMG is human-only
  in practice for this skill.)

## Steps

### Step 1 — Pull the per-cell-type summary
Call the tool:

```
cellxgene_expression(
  action="expression_summary",
  genes=[receptor_A, receptor_B],
  tissue="skeletal muscle",
)
```

The tool returns, for each gene, a dict keyed by cell-ontology term containing:
- `fraction_expressing` — fraction of cells of that type with non-zero counts
  for the gene (0–1).
- `mean_expression` — log-normalized mean expression across cells of that type.

If `CELLXGENE_MODE=mock` is set in the environment, the call returns
deterministic synthetic numbers — use mock mode for dry runs and tests.

### Step 2 — Filter to the target cell type
Find the cell-ontology key whose label substring-matches `target_cell_type`
(case-insensitive). If none match, expand to all cell types and surface the
top-3 closest labels in the rationale; do **not** silently fall back to a
different cell type.

If multiple labels match (e.g. `"satellite cell"` matches both
`skeletal muscle satellite cell` and `skeletal muscle satellite stem cell`),
take the union: a receptor counts as expressed if **any** matching subtype
passes the thresholds.

### Step 3 — Decision rule
For each receptor independently, check:
- `fraction_expressing >= 0.10` (≥10 % of cells of that type), AND
- `mean_expression > 0.5` on the WMG log-normalized scale.

A candidate **passes** co-expression iff **both** receptors meet **both**
thresholds in the target cell type.

### Step 4 — Score adjustment
- `co_expression_pass = True` → no change to the chain-soundness score.
- `co_expression_pass = False` → mark the candidate as `co_expression_FAIL`
  and apply a **chain_soundness penalty of −0.20** in the scoring step. The
  candidate is **not killed** — it can still proceed (the receptor may be
  induced in conditions the steady-state atlas does not capture, e.g. injury
  or aging) — but the penalty propagates through the RL loop.

## Aged vs young split

The CZ Cell Census pooled WMG query collapses across donors and does **not**
expose age stratification. For the rejuvenation pipeline we ultimately want
expression specifically in **aged** adult muscle, not pooled. For an
age-stratified read, use the local atlas at:

```
backend/storage/atlases/SKM_human_pp_cells2nuclei_2023-06-22.h5ad
```

(Kedlian / Lai 2024 human skeletal muscle atlas, processed cells2nuclei
release.) That requires loading an `.h5ad` and is deferred to a future
`local_atlas_query` skill — flag the gap rather than approximate.

## Output schema

```
{
  "receptor_A": {
    "symbol": "FGFR1",
    "per_cell_type": { "<ct_label_or_id>": {"fraction_expressing": 0.34, "mean_expression": 1.2}, ... },
    "target_cell_type_match": {"label": "skeletal muscle satellite cell", "fraction_expressing": 0.34, "mean_expression": 1.2}
  },
  "receptor_B": { ... same shape ... },
  "target_cell_type": "skeletal muscle satellite cell",
  "thresholds": {"fraction_expressing": 0.10, "mean_expression": 0.5},
  "co_expression_pass": true,
  "chain_soundness_delta": 0.0,
  "rationale": "Both FGFR1 and ERBB2 exceed the 10% / 0.5 thresholds in MuSC..."
}
```

When `co_expression_pass` is false, `chain_soundness_delta` MUST be `-0.20`
and the `rationale` must name which receptor failed which threshold.

## Pitfalls

- **WMG has no specific "skeletal muscle" tissue slice** (verified live 2026-05-04
  against `/wmg/v2/primary_filter_dimensions`: 64 human tissues, none with
  UBERON:0001134). The tool routes `tissue="skeletal muscle"` to
  **UBERON:0001015 "musculature"** (closest available proxy) and emits a
  warning. This bundles cardiac/smooth/skeletal muscle stromal cells together
  — interpret muscle-specific cell-type labels (e.g. `skeletal muscle satellite
  cell`, `skeletal muscle fibroblast`) preferentially when slicing.
- WMG `/v2/query` does NOT accept tissue filtering in the request body — only
  `gene_ontology_term_ids` + `organism_ontology_term_id`. Tissue filtering is
  done client-side after the response lands. The `compare` field, if set,
  must be one of `['sex', 'self_reported_ethnicity', 'disease', 'publication']`
  (NOT `cell_type`).
- WMG returns **log-normalized mean expression** (`me`) and **fraction
  expressing** (`pc`). The 0.5 / 0.10 cutoffs are heuristics tuned against
  real WMG output — typical mean expression in WMG is ~1.7–2.4, so 0.5 is a
  generous floor. Different snapshots may shift values slightly.
- Skeletal-muscle myofibers are large multinucleated cells and are
  under-represented in droplet scRNA atlases (most muscle scRNA is from
  mononuclear interstitial cells). For myofiber co-expression questions,
  prefer snRNA-seq atlases — the CZ Cell Census mixes both, so a "fail" on
  myofibers may be a sampling artifact. Note this in the rationale.
- The local HGNC→Ensembl map inside `cellxgene_tool.py` is small (curated to
  muscle-relevant receptors). If a requested symbol is unmapped the tool
  returns `invalid_input` in live mode — fall back to mock or extend the map.
- WMG snapshots advance over time; record `snapshot_id` from the structured
  payload alongside the decision so the result is reproducible.

## Worked example (live, 2026-05-04, snapshot 1762972271)

For the H2F receptor pair (FGFR1 + ERBB2) in `tissue="skeletal muscle"`
filtered to `["satellite", "fibroblast", "muscle cell"]`:

| receptor | cell type | pc | me | pass (≥0.10 AND >0.5) |
|---|---|---|---|---|
| FGFR1 | fibroblast | 0.428 | 2.09 | ✅ |
| FGFR1 | skeletal muscle fibroblast | 0.248 | 2.41 | ✅ |
| FGFR1 | skeletal muscle satellite cell | 0.219 | 2.05 | ✅ |
| ERBB2 | fibroblast | 0.036 | 1.86 | ❌ (pc) |
| ERBB2 | skeletal muscle satellite cell | 0.019 | 1.90 | ❌ (pc) |
| ERBB2 | skeletal muscle fibroblast | 0.029 | 2.28 | ❌ (pc) |

This correctly flags H2F's known limitation: ERBB2 is essentially absent
from steady-state human muscle (`pc < 5 %` everywhere), so the FGFR1+ERBB2
co-expression gate FAILS in MuSC and fibroblasts at baseline. H2F's reported
fibroblast→muscle reprogramming requires conditions that induce ERBB2 (e.g.
specific growth-factor cocktails); the steady-state atlas doesn't capture
those, which is why the pipeline applies a `−0.20` chain_soundness penalty
rather than a hard kill.

## Related

- `novokine_identification/SKILL.md` — Stage 1 PROPOSE.
- `novokine_validation/SKILL.md` — Stage 2 VALIDATE; this skill is consumed
  by the validation step.
- `COT_Rejuv_Pipeline/SKILL.md` — overall rejuvenation pipeline; this skill
  is Step C.
