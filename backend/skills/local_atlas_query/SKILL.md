---
name: local_atlas_query
description: Query the local human skeletal muscle cell atlas (183k cells, Kedlian/Lai 2024) for per-cell-type, per-age-bin (young/old) expression of genes. Use this when the rejuvenation pipeline needs aged-vs-young stratification that CZ Cell Census WMG cannot provide.
requires_tools: local_atlas_query
version: "1.0"
---

# Local Atlas Query — Age-Stratified Receptor Expression in Skeletal Muscle

## Purpose

Step C-prime of the rejuvenation pipeline (extension of `cellxgene_expression`).
The CZ Cell Census WMG endpoint pools across donor age and is the right
fallback for broad cross-tissue queries, but the rejuvenation pipeline is
specifically about shifting cells from aged → young. This skill calls the
`local_atlas_query` tool against the **183,161-cell SKM atlas** (Kedlian /
Lai 2024) to get per-(`cell_type`, `age_bin`) expression for genes of
interest.

## When to use

- After `cellxgene_expression` returns a borderline co-expression result
  in pooled-WMG mode and you need to know whether the receptor is *still*
  expressed in aged donors, or
- When the COT_Rejuv_Pipeline asks "is gene X depleted in aged MuSC vs
  young MuSC?" (a standard rejuvenation-target screening question), or
- When validating that a candidate novokine's predicted upregulated genes
  actually exist at meaningful levels in the target aged cell type.

If `cellxgene_expression` and `local_atlas_query` give different answers,
trust `local_atlas_query` for muscle-specific calls (the local atlas is
the donor-age-stratified ground truth this pipeline was designed around).

## Inputs

- `genes` — list of HGNC symbols (1–25). E.g. `["FGFR1", "ERBB2"]`.
- `cell_types` — *optional* substring filter against the atlas
  `annotation_level0` labels (case-insensitive). Common labels:
  `MuSC`, `MF-I`, `MF-II`, `FB` (fibroblast), `EnFB` (endomysial FB),
  `PnFB` (perimysial FB), `SMC`, `T-cell`, `Macrophage`, `Monocyte`,
  `NK-cell`, `CapEC`, `VenEC`, `Pericyte`. Default: all.
- `age_bins` — *optional* list, subset of `["young", "old"]`. Default: both.

## Output schema

For each requested gene:
```
{
  "<cell_type>": {
    "young": {"n_cells": int, "n_expressing": int,
              "fraction_expressing": 0..1, "mean_expression": float},
    "old":   {"n_cells": int, "n_expressing": int,
              "fraction_expressing": 0..1, "mean_expression": float},
    "delta_old_minus_young": {"fraction_expressing": float,
                              "mean_expression": float}
  },
  ...
}
```

`delta_old_minus_young` is the most actionable field for rejuvenation
hypotheses:
- **Negative Δpc** (e.g. EGFR in aged MuSC: −0.18) ⇒ the receptor is
  **lost with age** in that cell type ⇒ candidate for **rejuvenating
  restoration** (a novokine that reactivates it could be rejuvenating).
- **Positive Δpc** ⇒ the receptor is **gained with age** ⇒ candidate
  for **rejuvenating downregulation** (or a marker of senescence /
  inflammation).

## Decision rule (co-expression, age-stratified)

For a candidate novokine pair `(receptor_A, receptor_B)` and target cell
type `T`:

1. Both receptors must satisfy `fraction_expressing >= 0.10` AND
   `mean_expression > 0.5` in **at least one** of `young` or `old` cells
   of type `T`.
2. If both satisfy in `old` only, **co_expression_pass = True** and
   the candidate is treated as already acting on aged cells (best case).
3. If both satisfy in `young` only and **not** `old`, the candidate
   targets a population that has *aged out*. Mark
   `co_expression_aged_dropout = True` and treat as
   `chain_soundness_delta = -0.10` (warning, not fail).
4. If neither receptor satisfies in either age bin,
   `co_expression_pass = False` with `chain_soundness_delta = -0.20`
   (same penalty as the WMG-based skill).

## Worked example (live, 2026-05-04)

H2F receptor pair (FGFR1 + ERBB2) in MuSC:

| receptor | age | pc | me | pass (≥0.10 AND >0.5) |
|---|---|---|---|---|
| FGFR1 | young | 0.285 | 0.36 | ❌ (me<0.5) |
| FGFR1 | old | 0.267 | 0.38 | ❌ (me<0.5) |
| ERBB2 | young | 0.053 | 0.06 | ❌ |
| ERBB2 | old | 0.064 | 0.08 | ❌ |

Both receptors miss the gate in MuSC (FGFR1 misses on me, ERBB2 misses
on both). In FB:

| receptor | age | pc | me | pass |
|---|---|---|---|---|
| FGFR1 | young | 0.635 | 0.97 | ✅ |
| FGFR1 | old | 0.575 | 0.95 | ✅ |
| ERBB2 | young | 0.066 | 0.07 | ❌ |
| ERBB2 | old | 0.076 | 0.09 | ❌ |

H2F co-expression also fails in fibroblasts because ERBB2 is essentially
absent (<8 % of FBs at any age). This matches the WMG result and confirms
H2F's known dependence on induced rather than steady-state ERBB2.

## Pitfalls

- **The atlas thresholds (`pc≥0.10`, `me>0.5`) are noisier on small
  cell-type pools.** `n_cells` is reported per group — distrust deltas
  for groups with < 200 cells (a single donor can dominate).
- **`MF-Isc(fg)` / `MF-IIsc(fg)`** etc. labels denote scRNA fragments of
  myofibers (multinucleated cells whose RNA was sampled by partial cell
  capture, not whole). Their counts are typically very low and dominated
  by sample noise — don't draw mechanistic conclusions from them.
- The atlas reports pre-normalized log expression in `.X`. We do NOT
  re-normalize in the tool; values are comparable to the
  `cellxgene_expression` `me` field for cross-checking.
- Atlas snapshot fixed at 2023-06-22 (Kedlian/Lai 2024 Nature). Newer
  donors will not appear here — use `cellxgene_expression` if the
  question is "what does the broader community see in the latest WMG
  release?"

## Related

- `cellxgene_expression/SKILL.md` — pooled-tissue cousin (live WMG).
- `COT_Rejuv_Pipeline/SKILL.md` — Step C of the master pipeline.
- `novokine_validation/SKILL.md` — Stage 2 VALIDATE consumes these
  results.
