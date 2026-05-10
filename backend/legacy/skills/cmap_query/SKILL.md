---
name: cmap_query
description: Query the CLUE/CMAP L1000 connectivity database with a candidate's predicted up/down gene signature to obtain Track C sanity score (tau ∈ [-100, +100]).
requires_tools: clue_api
version: "1.0"
---

# cmap_query — CLUE/CMAP L1000 Track C Sanity Score

## Purpose

This skill produces **Track C** of the rejuvenation reward composite used by
`COT_Rejuv_Pipeline` (10% weight). Tracks A and B do the heavy lifting (atlas
overlap and mechanism coherence respectively); Track C is a **cross-domain
sanity check**: does the candidate novokine's predicted gene signature have a
connectivity profile in CMAP that resembles other rejuvenating perturbagens
(rapamycin, metformin, NMN-style NAD+ precursors, senolytics) and is
**anti-correlated** with senescence inducers (etoposide, doxorubicin,
ionizing-radiation-style DNA damage)?

A high Track C score means the predicted signature lives in the same L1000
neighborhood as compounds that empirically extend healthspan or clear
senescent cells — it does **not** prove the novokine works, but it raises
prior probability that the predicted up/down list is biologically coherent.

## When to use

- Run **after Stage 4 phenotype score lands** in `COT_Rejuv_Pipeline`, once
  `predicted_up_genes` / `predicted_down_genes` are committed to the experience
  buffer.
- **Skip** for candidates with `decision == INCOHERENT_LOG_ONLY`
  (`chain_soundness < 0.05`) — there is no point CMAP-checking a signature
  the mechanism layer already considers noise.
- May be batched across all `MIDDLE_HUMAN_REVIEW` and `TOP_K_DESIGN`
  candidates before the RL outer loop ranks the batch.

## Inputs

- `predicted_up: list[str]` — HGNC symbols predicted up-regulated, from
  Step 3c of `COT_Rejuv_Pipeline` (the biased TF-target signature).
- `predicted_down: list[str]` — HGNC symbols predicted down-regulated, same source.
- `cell_lines: list[str] | None` — optional CMAP cell-line filter (default: none).
- `max_results: int` — default 50; the tool ranks high-tau→low-tau.

## Steps

1. **Submit the connectivity query** via the `clue_api` tool:

   ```
   clue_api(
     action="query_signature",
     up_genes=predicted_up,
     down_genes=predicted_down,
     max_results=50,
   )
   ```

   The structured payload contains a `signatures` list, each carrying
   `pert_iname`, `moa`, `target`, `cell_id`, and `tau ∈ [-100, +100]`,
   sorted high-to-low by tau.

2. **Inspect top 5 / bottom 5 by tau.** Top-5 are putative mimics of the
   query signature (the candidate's predicted shift); bottom-5 are putative
   reversers. Both ends are informative for Track C scoring.

3. **Compute `track_c_score`.** Take the top decile of returned signatures
   (the 10% with highest tau). Count how many of those `pert_iname` values
   match the **rejuvenating** positive list vs. the **senescence-inducer**
   negative list (case-insensitive substring match on `pert_iname` is fine
   for this sanity check). Then:

   ```
   rejuv_hits  = #(top-decile pert_iname ∈ positive_list)
   sasp_hits   = #(top-decile pert_iname ∈ negative_list)
   raw_score   = rejuv_hits - sasp_hits
   max_possible = max(len(positive_list), 1)
   track_c_score = max(-1.0, min(1.0, raw_score / max_possible))
   ```

   `verdict` is `REJUV_LIKE` if `track_c_score > 0.2`, `SASP_LIKE` if
   `track_c_score < -0.2`, otherwise `NEUTRAL`.

## Known rejuvenating perturbagens (positive list)

`sirolimus`, `rapamycin`, `metformin`, `resveratrol`, `dasatinib` (senolytic),
`quercetin` (senolytic), `navitoclax`, `NMN`, `NAD`, `fisetin`.

Citations: literature-supported senolytics + caloric-restriction mimetics —
see PMID:32268001 for the senolytic class; rapamycin / metformin geroscience
rationale per Barzilai 2017 (TAME trial).

## Known senescence inducers (negative list)

`etoposide`, `doxorubicin`, `palbociclib`, `bleomycin`, `ionizing-radiation`
signatures. These are the canonical SASP / DNA-damage-induced-senescence
inducers used to build CMAP senescence reference signatures.

## Output schema

Return a single JSON object:

```json
{
  "track_c_score": 0.0,
  "top_perturbagens": [
    {"pert_iname": "...", "tau": 0.0, "moa": "...", "cell_id": "..."}
  ],
  "bottom_perturbagens": [
    {"pert_iname": "...", "tau": 0.0, "moa": "...", "cell_id": "..."}
  ],
  "rejuv_hits": 0,
  "sasp_hits": 0,
  "verdict": "REJUV_LIKE | SASP_LIKE | NEUTRAL"
}
```

This object is consumed directly by `COT_Rejuv_Pipeline` Step 5 Track C
(replacing the placeholder `track_C_score = 0.0`).

## Mock-mode caveat

Until the CLUE live submission loop is implemented (the L1000 query gateway is
asynchronous: submit → poll for ~10–30 min → download tarball), the
`clue_api` tool returns a **deterministic mock** (sha1-seeded RNG over the
input gene lists). Mock results carry `mock: true` and the warning
`cmap_mock_mode` in the envelope. **Down-weight Track C by a factor of 0.3 in
the composite reward while in mock mode** — i.e. effective weight 0.10 ×
0.3 = 0.03 of total reward — so a synthetic CMAP score cannot dominate the
mechanistic signal from Tracks A/B. Once `CMAP_MODE=live` is enabled and the
polling loop is implemented, restore full 0.10 weight.
