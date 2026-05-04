---
name: novokine_identification
description: Propose candidate novokine receptor pairs (and known minibinders, where available) for a given cell context and phenotype goal, grounded in the novokine knowledge base and the literature.
category: bio/literature
version: 1.0
requires_tools: [search_knowledge_base, fetch_url, ncbi_eutils, uniprot_api, python_repl, write_file]
requires_network: true
user_invocable: true
tags: [novokine, minibinder, receptor-pair, target-discovery, de-novo-design]
aliases: [novokine_proposal, propose_novokine_pairs]
species: human
modality: protein_design
stage: design
stability: evolving
safety_level: medium
---

# Novokine Identification — Propose Candidate Receptor Pairs

## Purpose

Given a **cell context** (e.g. human skeletal muscle stem cells) and a **phenotype goal** (e.g. shift from aged to young transcriptional state, enhance myotube maturation, reactivate quiescent stem cells), propose **ranked novokine candidates** as `(receptor_A, receptor_B)` pairs — with known minibinders identified where they exist in the literature, and gaps flagged where new minibinders would need to be designed.

This skill is the **proposal** step. It does not validate (`novokine_validation`) or hand off to a design pipeline (`novokine_design_handoff`).

## When to use

User asks one of:
- "What novokines should we try for {cell context} / {phenotype}?"
- "Propose minibinder pairs to {achieve goal}."
- "Which receptors should we target on {cell type} to reprogram it?"
- "Suggest novokine candidates for the rejuvenation RL loop."

## Required inputs

- **cell_context**: Cell type or model (e.g. "human skeletal muscle stem cell", "patient-derived myoblast", "iPSC-derived myocyte").
- **goal**: Phenotype or transcriptional goal (e.g. "shift aged → young", "induce myotube maturation", "sustain pluripotency").
- **constraints** (optional): Target receptor families to prefer or exclude, paper-defined controls (e.g. "include H2F as positive control"), known off-targets to avoid.
- **receptor_universe** (optional): If unspecified, default to "any cell-surface receptor expressed in the cell context per Human Protein Atlas".

## Steps

### Step 1 — Load novokine canonical knowledge
Use `search_knowledge_base` against `knowledge/novokines.md`:
- Query 1: "novokine receptor pair {cell_context}"
- Query 2: "minibinder library published {receptor_family}"
- Query 3: "biased signaling {goal}"

This pulls in the H2F exemplar, the IFNAR1-hub finding, geometry-biased pSTAT outputs, and the receptor-family heuristics.

### Step 2 — Identify the relevant pathway / TF program for the goal
Use `search_knowledge_base` and `fetch_url` to map the goal to upstream signaling:
- Reactome pathway lookup for the phenotype (e.g. "myogenesis", "muscle stem cell quiescence", "senescence reversal").
- GO term annotation for relevant TFs (MyoD, MyoG, MEF2, PAX7, FOXO3, NF-κB; for rejuvenation also AMPK, mTOR, autophagy axis).
- Note which pathways converge on the desired program.

### Step 3 — Map pathways back to upstream receptors
For each implicated pathway, identify the receptors that feed it:
- MAPK / AKT in muscle → FGFR1/2c, IGF1R, MET, ERBB family.
- JAK-STAT skewing toward pro-regenerative state → IL-6R / gp130, IFNAR1 (per Abedi et al.), LIFR, OSMR.
- TGF-β / BMP balance for stem cell quiescence vs activation → ACVR2B, BMPR1A, TGFBR2.
- Anti-inflammaging → block IL-6R / TNFR1 axis (note: a single minibinder against these acts as an antagonist; only a fused pair is an agonist novokine).

Filter against the **forced-dimerization-amenable receptor families** listed in `knowledge/novokines.md` §5 — drop GPCRs and ion channels unless the user has a specific reason to keep them.

### Step 4 — Confirm receptor expression in the target cell context
For each candidate receptor, use `fetch_url` to:
- Human Protein Atlas: `https://www.proteinatlas.org/{gene}/tissue/skeletal+muscle`
- Or `search_knowledge_base` for cached muscle-atlas DE tables if available.

Drop receptors with zero or near-zero expression in the cell context. Flag receptors that are *induced* during the relevant biological transition — those are particularly interesting targets.

### Step 5 — Look up minibinder availability
For each surviving receptor, check whether published minibinders exist:
- `search_knowledge_base` for cached minibinder library notes.
- `ncbi_eutils` PubMed search: `"de novo" minibinder {receptor_symbol}`, `Baker lab {receptor_symbol} mini-protein binder`.
- Specifically recall from `knowledge/novokines.md`:
  - The Abedi et al. 2025 set of **33 designed receptor-binding domains** that yielded >1,000 novokines.
  - The C6-79C-mb7 FGFR1/2c minibinder from Edman et al. 2024 (used in H2F).
  - HER2 minibinder used in H2F.

Mark each candidate as:
- **(known, known)**: both minibinders published — skill outputs are immediately actionable.
- **(known, novel)** or **(novel, known)**: one side requires de novo design — hand off to `novokine_design_handoff`.
- **(novel, novel)**: high-cost candidate; only propose if mechanistic upside is large.

### Step 6 — Pair the receptors and rank
Build candidate pairs. Strategies to consider, in order of typical productivity:
1. **Hub × specific**: pair a hub receptor (IFNAR1, gp130, βcommon, γcommon) with a tissue-specific receptor expressed in the cell context. This is the Abedi et al. design philosophy.
2. **Two RTKs in convergent pathways**: e.g. FGFR1 + IGF1R for muscle anabolism + survival.
3. **Orphan + known partner**: H2F template — pair an orphan-like receptor (HER2) with a partner that brings a strong cytoplasmic signaling tail (FGFR1/2c).
4. **Antagonist pair masquerading as a novokine**: only if the user explicitly wants antagonism — most pairings in this list act as agonists once fused.

Use `python_repl` to score each pair on:
- **Pathway-goal alignment** (1–3): how directly the predicted biased output drives the goal.
- **Expression overlap** (1–3): co-expression of A and B in the target cell.
- **Minibinder availability** (1–3): both published > one published > both novel.
- **Mechanistic plausibility** (1–3): both receptors in dimerization-friendly families.
- **Novelty / risk** (1–3): novel mechanism (high reward, high uncertainty) vs. literature-validated.

Sum into a rank score. Surface the **top 5–8** with reasoning.

### Step 7 — Always include positive and negative controls
- **Positive control**: H2F (HER2 + FGFR1/2c) for any muscle / regeneration goal.
- **Negative control**: at least one pair predicted to drive the *opposite* phenotype (e.g. inflammaging axis: TNFR1 + IL6R) so the RL loop and downstream scoring (`COT_Rejuv_Pipeline`) have calibration anchors.

### Step 8 — Save the candidate set
Use `write_file` to `scratch/novokine_proposals/{cell_context}_{goal}_{timestamp}.md` containing the structured table and per-candidate rationale blocks.

## Output format

A structured report with:

1. **Header**: cell context, goal, timestamp.
2. **Goal-to-pathway map** (Steps 2–3): one short paragraph + bullet list.
3. **Candidate table**:

   | Rank | Receptor A | Receptor B | Minibinder A | Minibinder B | Score | Verdict |
   |------|------------|------------|--------------|--------------|-------|---------|
   | 1 | HER2 | FGFR1 | HER2 minibinder (H2F paper) | C6-79C-mb7 (Edman 2024) | 14 | known/known — positive control |
   | ... | | | | | | |

4. **Per-candidate rationale block** (top 5–8):
   ```
   ### {A + B}
   - Predicted biased output: {pathway branches on / off}
   - Why this fits the goal: {1–2 sentences}
   - Minibinder status: {known/known | known/novel | novel/novel}
   - Risks / caveats: {expression, geometry, off-target}
   - Next step: {validate via `novokine_validation` | hand off to `novokine_design_handoff`}
   ```

5. **Controls**: H2F (positive) + an inflammaging pair (negative) — always present.

6. **Sources**: PMIDs, paper titles, HPA links, knowledge-base sources cited inline.

## Failure modes

- **No receptors expressed in cell context** → return "no actionable candidates" rather than fabricate; suggest user re-check the cell context or relax the receptor universe.
- **Goal is too vague** ("make the cell better") → ask user to narrow to a transcriptional or functional readout.
- **All candidates require novel minibinder design on both sides** → still return them but mark the budget as "high"; downstream `novokine_design_handoff` will know.
- **GPCR or ion-channel-only candidate space** → warn that forced-dimerization agonism is unlikely productive; point to alternative skills (small-molecule lookup, etc.).

## Examples

- "Propose novokines for human skeletal muscle stem cells to drive the aged → young transcriptional shift."
- "Suggest minibinder pairs to enhance myotube maturation in patient-derived myoblasts."
- "What novokines should I add to the RL loop's initial pool for the muscle rejuvenation project?"
- "Pair an IFNAR1 hub with a muscle-specific receptor for synthetic immunomodulation in regenerating muscle."

## Related skills

- [novokines knowledge file](../../knowledge/novokines.md) — read first.
- [novokine_validation](../novokine_validation/SKILL.md) — sanity-check a proposed candidate before committing design budget.
- [novokine_design_handoff](../novokine_design_handoff/SKILL.md) — translate a novel candidate into a design-pipeline job spec.
- [COT_Rejuv_Pipeline](../COT_Rejuv_Pipeline/SKILL.md) — downstream RL scoring for each candidate.
- [pathway_lookup](../pathway_lookup/SKILL.md) — used inside Steps 2–3.
- [target_dossier](../target_dossier/SKILL.md) — deeper per-receptor literature pull if needed.
