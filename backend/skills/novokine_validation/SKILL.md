---
name: novokine_validation
description: Sanity-check a proposed novokine candidate (receptor pair + minibinders) on identity, expression, mechanism, geometry, and design quality before committing experimental or design budget.
category: bio/literature
version: 1.1
requires_tools: [search_knowledge_base, fetch_url, uniprot_api, ncbi_eutils, read_file, python_repl, alphafold3_api]
requires_network: true
user_invocable: true
tags: [novokine, minibinder, validation, receptor-pair, sanity-check, alphafold3, structure-prediction]
aliases: [validate_novokine, novokine_sanity_check]
species: human
modality: protein_design
stage: validation
stability: evolving
safety_level: medium
---

# Novokine Validation — Sanity-Check a Candidate

## Purpose

Given a proposed novokine candidate — `(receptor_A, receptor_B, minibinder_A, minibinder_B, [linker_spec])` — verify in silico that the candidate is **mechanistically defensible** before sending it to a wet-lab assay or expensive design loop. Returns a structured **PASS / WARN / FAIL** verdict per check, an aggregated decision, and a list of specific failures with remediation hints.

This skill **does not design** new minibinders (see `novokine_design_handoff`) and **does not score phenotype** (see `COT_Rejuv_Pipeline`). It is the gating step in between.

## When to use

User asks:
- "Validate this novokine: {spec}."
- "Is `(HER2-mb1 :: linker :: FGFR1-mb7)` sensible? Run the checks."
- "Sanity-check the candidates from `novokine_identification` before we hand them off."
- "Why was candidate X flagged as risky?"

## Required inputs

- **novokine_id**: Handle for the candidate (e.g. `cand_0042`, `H2F`).
- **receptor_A**, **receptor_B**: Gene symbols (e.g. `HER2`, `FGFR1`).
- **minibinder_A**, **minibinder_B**: Either (a) a published name / PDB ID / paper reference, (b) a sequence (FASTA), or (c) `novel` if not yet designed.
- **linker_spec** (optional): Linker length and composition (e.g. `(GGGGS)x4`, `4-helix rigid scaffold`); default `(GGGGS)x4` flexible.
- **cell_context**: Cell type the novokine will act on (default `human skeletal muscle cell`).
- **structure_files** (optional): Paths to predicted complex structures (AF3 / Boltz-2 / AF2 outputs) if the user has them.
- **run_af3** (optional, default `true`): Whether to submit a fresh AF3 prediction for Check 6 when no structure files are provided. Set `false` to skip (saves API quota; use when structures already exist or candidate is clearly going to FAIL earlier checks).

## Steps

Each step writes a **check block** with verdict ∈ `{PASS, WARN, FAIL}`. The skill runs all checks even if early ones fail — failure modes are informative.

### Check 1 — Receptor identity and family
Use `uniprot_api` for both receptors. Confirm:
- Gene symbol resolves to a single human protein.
- Receptor family per `knowledge/novokines.md` §5.
- **Verdict FAIL** if the receptor is intracellular (not addressable by an extracellular novokine) or a GPCR / ion channel where forced-dimerization agonism is implausible (with the documented exceptions).
- **Verdict WARN** if family is single-pass but signaling mechanism is poorly characterized.

### Check 2 — Receptor expression in cell context
Use `fetch_url` to Human Protein Atlas (`https://www.proteinatlas.org/{gene}/tissue`) or `search_knowledge_base` for cached muscle-atlas data. For each receptor:
- **PASS** if expression > tissue median in `cell_context`.
- **WARN** if expression is detectable but low, or restricted to a subpopulation.
- **FAIL** if not expressed.

If both receptors must be on the *same cell* for the novokine to function, also confirm **co-expression** in the same single-cell cluster — not just bulk tissue.

### Check 3 — Minibinder existence / sequence sanity
For each minibinder:
- If **named**: `ncbi_eutils` PubMed lookup + `search_knowledge_base` for the citation; resolve to a sequence if possible.
- If **sequence given**: confirm it is plausible: 30–150 aa, no obvious frameshifts or stop codons, no >40% identity to the target (which would imply it's a fragment of the receptor itself, not a designed binder).
- If **novel**: mark **WARN** and route the user to `novokine_design_handoff`.

Run `python_repl` for trivial sequence sanity (length, AA composition, presence of disulfide-prone Cys pairs).

### Check 4 — Mechanistic plausibility (the agonism-by-proximity check)
Combining Checks 1 and the receptor families:
- **PASS** if both receptors signal via dimerization / clustering and are in compatible families (RTK + RTK, JAK-STAT + JAK-STAT, RTK + cytokine receptor — the H2F precedent).
- **WARN** if one receptor's signaling-by-clustering is uncertain (e.g. some integrins, atypical receptors).
- **FAIL** if mechanism is fundamentally incompatible (e.g. one is a GPCR, one is an RTK — geometry won't drive both productively).

Cite `knowledge/novokines.md` §1 (antagonist→agonist switch) and §5 (receptor families) explicitly in the rationale.

### Check 5 — Geometry / linker compatibility
Per Expòsit et al. 2025 (geometric tuning paper):
- Linker length and rigidity are first-class. Check user-provided `linker_spec`:
  - `(GGGGS)x4` flexible, ~20 Å reach: default; passes for most pairs.
  - Rigid scaffolds: **PASS** if a target inter-domain distance is justified; **WARN** if length looks mismatched to the receptor extracellular domains.
- If a predicted complex structure is provided (`structure_files`): use `read_file` and `python_repl` to estimate the inter-receptor extracellular-domain distance the linker must span; flag mismatches.

### Check 6 — Design quality predictions (structure-based, AF3-preferred)

This check evaluates predicted complex quality for each minibinder–receptor sub-complex AND the full ternary novokine–receptor_A–receptor_B complex.

**Validator priority order**:
1. **AlphaFold 3 (preferred)** — use `alphafold3_api` tool. AF3 jointly models all molecular entities (proteins, PTMs, small molecules, nucleic acids) and produces superior interface metrics vs AF2 on protein-protein complexes.
2. **Boltz-2 (fallback)** — use if AF3 API quota is exhausted or the job fails.
3. **AF2-Multimer (last resort)** — only if both AF3 and Boltz-2 are unavailable.

**When to run AF3**:
- If `structure_files` is provided: parse the supplied structure(s) with `python_repl` (Biopython) and skip the AF3 submission — use the provided structure's metrics directly.
- If `structure_files` is absent AND `run_af3` is `true`: submit a fresh AF3 job via `alphafold3_api` with:
  - **Binary 1**: minibinder_A sequence
  - **Binary 2**: receptor_A extracellular domain sequence (UniProt canonical, residues from signal-peptide end to TM start)
  - Repeat independently for minibinder_B + receptor_B
  - **Ternary complex** (if both minibinders are known sequences): minibinder_A + linker + minibinder_B fused, receptor_A ECD, receptor_B ECD — three-chain submission
- If `run_af3` is `false` or both minibinders are `novel`: mark this check **N/A**.

**AF3 acceptance thresholds** (Abramson et al., *Nature* 2024; Dunbrack 2025 ipSAE recommendation):

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| `ipTM` | > 0.75 | 0.60–0.75 | < 0.60 |
| `ipSAE` (interface surface-area estimated, per Dunbrack 2025) | > 0.70 | 0.55–0.70 | < 0.55 |
| Interface `pLDDT` (chain-averaged over interface residues) | > 0.80 | 0.65–0.80 | < 0.65 |
| Binder pose matches intended epitope (visual / RMSD check) | within 3 Å of hotspots | 3–6 Å drift | > 6 Å or wrong face |

**Boltz-2 fallback thresholds** (Wohlwend et al. 2024; Dunbrack 2025):

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| `confidence_score` | > 0.65 | 0.50–0.65 | < 0.50 |
| `complex_pLDDT` | > 0.75 | 0.60–0.75 | < 0.60 |
| `ipTM` | > 0.75 | 0.60–0.75 | < 0.60 |

**Do NOT mix thresholds across validators.** AF3 ipTM is not the same scale as AF2 PAE. Report which validator was used alongside the raw scores.

**Ternary complex note**: a ternary PASS requires both binary sub-complexes AND the ternary to pass independently. A WARN on the ternary with both binaries at PASS indicates the linker geometry is creating a steric clash — recommend linker length variants before re-running.

### Check 7 — Off-target receptor binding
For each minibinder, search `knowledge/` and via `fetch_url` (UniProt similarity / Pfam) for paralogs of the target receptor that might also be bound:
- e.g. an FGFR1 minibinder may also bind FGFR2c (often desired), but flag if it might bind FGFR3 or FGFR4 (off-target).
- e.g. an IL6R minibinder might cross-react with gp130, IL11R.
- **PASS**: high specificity predicted or confirmed.
- **WARN**: paralog cross-reactivity expected but plausibly tolerable.
- **FAIL**: cross-reactivity hits a receptor in a pathway opposite to the intended phenotype (e.g. would activate an inflammaging axis we wanted to spare).

### Check 8 — Mechanistic precedent
`search_knowledge_base` for prior published novokines on the same receptor pair or family combination. Cite specifically:
- H2F (HER2 + FGFR1/2c).
- Abedi et al. 2025 set (IFNAR1 paired with diverse partners).
- Expòsit et al. 2025 set (geometric tuning of cytokine pairs).
- Synthekines (Zhao 2025).

A precedent doesn't have to be exact; "same family combination has been productively engineered" is enough for a **PASS**.

### Aggregation — Final verdict
Use `python_repl` to combine check results:
- Any **FAIL** → overall **FAIL**, with the failing check(s) named.
- ≥ 2 **WARN** and no **FAIL** → overall **WARN**, do not proceed without addressing.
- All **PASS** (or N/A only) → overall **PASS**.

## Output format

```
# Novokine Validation Report — {novokine_id}

**Spec**: {receptor_A} + {receptor_B} via {minibinder_A} :: {linker} :: {minibinder_B}
**Cell context**: {cell_context}
**Overall verdict**: {PASS | WARN | FAIL}

## Check results
| # | Check | Verdict | Notes |
|---|-------|---------|-------|
| 1 | Receptor identity and family | PASS / WARN / FAIL | {…} |
| 2 | Expression in cell context | … | … |
| 3 | Minibinder existence / sequence | … | … |
| 4 | Mechanistic plausibility | … | … |
| 5 | Geometry / linker compatibility | … | … |
| 6 | Design quality predictions (AF3 / Boltz-2 / AF2) | PASS / WARN / FAIL / N/A | {validator used; ipTM; ipSAE; pLDDT; ternary result} |
| 7 | Off-target receptor binding | … | … |
| 8 | Mechanistic precedent | … | … |

## Specific failures and remediation
- {check #}: {what failed} → {how to fix: redesign minibinder / change linker / drop the candidate}

## Recommendations
- If PASS: send to `novokine_design_handoff` (if any minibinder is novel) and `COT_Rejuv_Pipeline` for phenotype scoring.
- If WARN: address listed warnings, then re-validate.
- If FAIL: do not proceed with this candidate.

## Sources
- {UniProt entries, HPA pages, PMIDs, knowledge-base sections}
```

## Failure modes

- **Both minibinders are `novel` and no structures provided** → most checks reduce to N/A; return verdict `WARN — design first, validate after`, route to `novokine_design_handoff`. AF3 check is automatically skipped.
- **AF3 API quota exhausted or job fails** → fall back to Boltz-2 silently; log which validator was used in the report. If Boltz-2 also unavailable, mark Check 6 `N/A` with a note to rerun after quota resets.
- **AF3 API key not configured** (`AF3_API_KEY` missing from `.env`) → skip Check 6 with a clear message: "Set AF3_API_KEY in backend/.env (Google account required at alphafoldserver.com) to enable structure prediction."
- **Cell context not specified** → use the project default (human skeletal muscle cell) and mark expression check as `WARN` with reduced confidence.
- **Receptor symbol unresolved** → ask user for clarification before running other checks (saves wasted lookups).
- **Conflicting expression data across sources** → report all, do not silently pick one.

## Examples

- "Validate H2F: HER2 + FGFR1 with the published minibinders, flexible linker." → expected PASS (literature positive control).
- "Validate `cand_0042`: GPR40 + GLP1R via novel minibinders." → expected FAIL on Check 4 (two GPCRs).
- "Validate IFNAR1 + IL6R hub novokine in human muscle stem cells." → expected PASS on mechanism, possibly WARN on muscle-stem-cell expression of IFNAR1 — verify via HPA + atlas.
- "Validate IGF1R + FGFR4 with the published IGF1R binder and a novel FGFR4 binder." → expected PASS on identity/expression/mechanism, WARN on Check 3 (one novel side), routed to design handoff.

## Related skills

- [novokines knowledge file](../../knowledge/novokines.md) — canonical reference; required reading.
- [novokine_identification](../novokine_identification/SKILL.md) — upstream proposal step.
- [novokine_design_handoff](../novokine_design_handoff/SKILL.md) — downstream when any minibinder is novel; also uses AF3 for post-design validation.
- [COT_Rejuv_Pipeline](../COT_Rejuv_Pipeline/SKILL.md) — downstream phenotype scoring; only run after PASS.
- [target_dossier](../target_dossier/SKILL.md) — for deeper per-receptor literature pulls when a check is borderline.
- [paralog_redundancy_check](../paralog_redundancy_check/SKILL.md) — reusable inside Check 7.
- `alphafold3_api` tool — LangChain tool wrapping the AF3 hosted API; used directly in Check 6. Requires `AF3_API_KEY` in `backend/.env`.
