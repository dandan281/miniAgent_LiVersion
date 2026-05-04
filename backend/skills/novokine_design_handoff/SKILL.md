---
name: novokine_design_handoff
description: Translate a novokine candidate that needs new minibinders into a concrete design-pipeline job spec — selects between RFdiffusion+ProteinMPNN, BindCraft, BoltzGen, BoltzDesign1, or ProteinDJ; prepares target inputs, hotspots, and acceptance filters; emits a runnable manifest.
category: bio/compute
version: 1.0
requires_tools: [search_knowledge_base, fetch_url, read_file, python_repl, write_file]
requires_network: true
user_invocable: true
tags: [novokine, minibinder, de-novo-design, RFdiffusion, ProteinMPNN, BindCraft, BoltzGen, BoltzDesign1, ProteinDJ, AlphaFold2, Boltz]
aliases: [novokine_design_spec, design_handoff_minibinder]
species: human
modality: protein_design
stage: design
stability: evolving
safety_level: medium
---

# Novokine Design Handoff — Pipeline Spec for New Minibinders

## Purpose

Given a novokine candidate where one or both minibinders are **novel** (need to be designed), produce a **runnable design-pipeline manifest**: which platform to use, what to feed it, what filters to apply on the way back. This skill stops at the manifest — it does not run the design itself.

## When to use

User asks:
- "Hand off `cand_0042` to the design pipeline."
- "Set up an RFdiffusion / BindCraft / BoltzGen job for a minibinder against {receptor}."
- "I need a design spec for the novel minibinder side of this novokine."
- "Which design tool should I use for this target, and what inputs does it need?"

## Required inputs

- **novokine_id**: Handle for the candidate.
- **target_receptor**: Gene symbol of the receptor to bind (the side that is `novel`).
- **target_structure** (preferred): PDB ID or path to a structure file of the receptor extracellular domain.
- **target_epitope** (optional): Hotspot residues (PDB numbering) the binder should engage. If unspecified, the skill proposes hotspots from prior literature on the receptor.
- **partner_minibinder** (optional): The known side of the novokine; needed for compatibility checks on linker length and second-side geometry.
- **constraints** (optional): Size budget (default 50–110 aa), allowed scaffolds, immunogenicity preferences, deliverable format (linear sequence, expression-ready construct, dimerized novokine fusion).

## Steps

### Step 1 — Read the canonical knowledge
Use `search_knowledge_base` against `knowledge/novokines.md` §6 (design parameters) and §7 (tooling landscape). The user's project default is RFdiffusion → ProteinMPNN → AF2/Boltz-2; this skill can override that based on what fits the target.

### Step 2 — Resolve target structure and epitope
1. If `target_structure` is a PDB ID, `fetch_url` to RCSB to confirm chain composition and resolution.
2. If only a gene symbol is given, look up canonical PDB structures of the extracellular domain via UniProt → RCSB cross-references.
3. If `target_epitope` is unspecified:
   - `ncbi_eutils` for prior published binders/agonists/antagonists at the receptor.
   - Default to surface-exposed loops with high evolutionary conservation, away from glycosylation sites, and **not** on the natural ligand-binding interface unless the design intent is to compete with the natural ligand.
   - Use `python_repl` + a structure parser (Biopython if available) on the cached PDB to compute SASA and propose hotspot residues.

### Step 3 — Select the design platform
Decide based on target type and project constraints. Defaults below; override only with an explicit reason.

| Situation | Recommended platform | Why |
|---|---|---|
| Standard receptor extracellular domain, protein target | **RFdiffusion + ProteinMPNN + AF2/Boltz-2** | Project default; well-validated; both first two stages hosted on Superbio.ai (`https://app.superbio.ai/apps/655b1f47a9ed6f6e5560ba8f` for RFdiffusion). |
| User wants a **one-shot** pipeline with high reported success rate, no scaffold library tuning | **BindCraft** | Pacesa et al., *Nature* 2025; AF2-backprop hallucination; reported 10–100% experimental success on cell-surface receptors. Open source (`https://github.com/martinpacesa/BindCraft`). |
| Target is a **non-protein** (small molecule, RNA, DNA, metal) — rare for novokines but possible for hybrid designs | **BoltzDesign1** | Designs binders to non-protein targets; Boltz-based. |
| User wants the **newest universal binder model** with affinity prediction integrated | **BoltzGen** (BoltzGen + BoltzIF + Boltz-2) | MIT Jameel Clinic, Nov 2025; bioRxiv `10.1101/2025.11.20.689494v1`. |
| User is on an HPC cluster and wants a **reproducible Nextflow pipeline** that chains RFdiffusion or BindCraft → ProteinMPNN or FAMPNN → AF2 or Boltz-2 | **ProteinDJ** | Papenfuss lab, 2025; bioRxiv `10.1101/2025.09.24.678028v2`; GitHub `PapenfussLab/proteindj`. |
| Target is a single-domain antibody / VHH variant | **RFantibody** on Superbio | `https://app.superbio.ai/apps/67e6ba077d733b5d5294fd0c`. |

> **Note on the user-recalled Superbio integrated novokine pipeline.** As of the last check, the agent could not verify a Superbio.ai app that runs **RFdiffusion + ProteinMPNN + a Boltz-family validator** end-to-end as a single integrated novokine workflow. RFdiffusion and ProteinMPNN are exposed as **separate** Superbio apps. If the user provides a direct link to the integrated app, prefer it and update `knowledge/novokines.md` §7. Until then, ProteinDJ is the closest published end-to-end pipeline that matches the described stack.

### Step 4 — Define acceptance filters
Standard filters apply regardless of platform:
- **AF2 / Boltz-2 metrics on the binder–target complex**:
  - `pAE_interaction < 7.5`
  - interface `pLDDT > 85`
  - `iptm > 0.7` (if reported)
- **Rosetta filters** (BindCraft / classical pipelines):
  - shape complementarity (sc) > 0.6
  - interface ddG < −30 REU
  - no buried unsatisfied H-bond donors / acceptors
- **Diversity filter**: cluster top designs at 70% sequence identity; keep ≤ 3 representatives per cluster to avoid ordering near-duplicates.
- **Size budget**: 50–110 aa per the published novokine convention.
- **Cysteine policy**: prefer 0–2 free Cys (avoid disulfide-prone designs unless intentional).
- **Off-target receptor screen**: predict the binder against paralogs of the target (e.g. all FGFR1/2/3/4 if target is FGFR1) and require Δ-pAE_interaction in favor of the target.

### Step 5 — Plan downstream fusion to the partner minibinder
The output of design is a single minibinder. The novokine is the **fused dimer**. The skill must specify:
- **Linker default**: `(GGGGS)x4` flexible (≈ 20 Å reach, ~30 Å fully extended) for first attempts.
- **Linker variants to also screen** (per Expòsit et al. 2025 geometric-tuning result):
  - `(GGGGS)x2` — short, rigid-ish.
  - `(GGGGS)x6` — long flexible.
  - 4-helix-bundle rigid scaffold of length ~25 Å between domain attachment points (if target geometry suggests a specific inter-receptor distance).
- **Order of fusion (N→C)**: typically the receptor with the larger / more complex extracellular domain closer to the C-terminus; flag for empirical screening.
- **Termini blocking residues**: optional N-terminal Met removal and C-terminal stabilizing tag; user-configurable.

### Step 6 — Emit the manifest
Write a runnable manifest to `scratch/novokine_designs/{novokine_id}/manifest.yaml` (use `write_file`). Structure:

```yaml
novokine_id: cand_0042
target_receptor: FGFR4
target_structure: pdb/4uxq.pdb
target_chain: A
target_hotspots: [Y262, R264, L286, K291]
binder_size: [50, 110]
n_designs: 5000
platform:
  primary: RFdiffusion+ProteinMPNN+Boltz2
  alternate: BindCraft
  hpc_pipeline: ProteinDJ
filters:
  pae_interaction_max: 7.5
  plddt_interface_min: 85
  iptm_min: 0.7
  rosetta_sc_min: 0.6
  rosetta_ddg_max: -30
  cluster_identity: 0.7
  per_cluster_keep: 3
off_target_screen:
  paralogs: [FGFR1, FGFR2, FGFR3]
  delta_pae_min: 2.0
fusion_to_partner:
  partner_minibinder: C6-79C-mb7  # the FGFR1/2c side, reused conceptually here
  linker_default: "(GGGGS)x4"
  linker_variants:
    - "(GGGGS)x2"
    - "(GGGGS)x6"
    - "rigid_4HB_25A"
  fusion_order: N_partner__linker__C_novel  # to be empirically inverted
deliverables:
  - top_5_designs.fasta
  - top_5_designs.pdb
  - novokine_constructs.fasta  # post-fusion, all linker variants
  - design_metrics.tsv
post_design_actions:
  - re_run: novokine_validation
  - then: COT_Rejuv_Pipeline
```

### Step 7 — Tell the user how to run it
Print the platform-specific command sketch (do **not** execute the design here — this skill is a handoff, not a runner):

- **RFdiffusion (Superbio.ai)**: link to the app and the JSON / form fields to fill (target PDB, hotspots, num designs).
- **BindCraft (local / HPC)**: example `bindcraft.py --target ... --hotspots ... --binder_length ... --n_designs ...` invocation.
- **ProteinDJ (HPC)**: example Nextflow command — `nextflow run PapenfussLab/proteindj -profile slurm --input manifest.yaml`.
- **BoltzGen / BoltzDesign1**: link to the boltz.bio docs and the configuration block.

If a downstream runner skill exists (e.g. `analysis_to_slurm_runner`), recommend chaining; otherwise leave execution to the user.

## Output format

```
# Novokine Design Handoff — {novokine_id}

**Target receptor**: {gene_symbol}
**Target structure**: {PDB / path}
**Hotspots**: {residue list, with provenance}
**Recommended platform**: {primary} (alternate: {alternate}; HPC: {hpc_pipeline})

## Manifest
{path to manifest.yaml; YAML block above}

## Acceptance filters
{table}

## Fusion plan (post-design)
- Linker default: ...
- Linker variants to screen: ...
- Fusion order: ...

## Run sketch
{platform-specific command or app link}

## Post-design actions
1. Re-run `novokine_validation` with the new minibinder sequences and AF2/Boltz outputs.
2. If PASS, run `COT_Rejuv_Pipeline` in `predict` mode for the phenotype score.
3. Add the result to the RL loop's experience buffer.

## Sources
{links to RFdiffusion / BindCraft / BoltzGen / ProteinDJ; cited papers; knowledge-base section}
```

## Failure modes

- **No structure available for the target receptor** → cannot run RFdiffusion or BindCraft against it. Fallbacks: (a) AF2-multimer or Boltz-2 to predict the receptor structure first, (b) homology model from a paralog, (c) recommend BoltzGen which can take sequence-only input. Document the structure source in the manifest.
- **Target epitope unknown and no published binders** → propose top-3 candidate epitopes from SASA + conservation, mark all as exploratory, request user confirmation before launching.
- **User asks for a Superbio.ai integrated novokine pipeline app** that the agent cannot verify exists → say so plainly, point to the closest equivalents (RFdiffusion + ProteinMPNN as separate Superbio apps; BindCraft / BoltzGen / ProteinDJ as published integrated alternatives), and note this is open question §7 in `knowledge/novokines.md`.
- **Unrealistic compute budget** (e.g. user wants 100k designs on a laptop) → flag and suggest a smaller initial sweep (5k designs) plus an HPC follow-up.
- **Conflicting platform constraints** (e.g. "must be on Superbio.ai" + "must be Boltz-based") → enumerate the conflict, do not silently pick one.

## Examples

- "Hand off the novel FGFR4 minibinder for `cand_0042` to RFdiffusion." → manifest with FGFR4 PDB, hotspots from literature, AF2/Boltz filters, fusion plan to the existing FGFR1/2c partner.
- "Set up a BindCraft job for a novel HER2 minibinder against the H2F-style epitope." → BindCraft-specific manifest with hotspot constraints from the H2F paper.
- "I want to use the newest pipeline — recommend the platform." → BoltzGen, with full manifest and a note on its experimental status.
- "Run the design loop on Superbio.ai end-to-end." → state the platform-availability caveat, recommend ProteinDJ as the equivalent and Superbio's RFdiffusion + ProteinMPNN apps as a manual two-step.

## Related skills

- [novokines knowledge file](../../knowledge/novokines.md) — required reading; tooling landscape lives there.
- [novokine_identification](../novokine_identification/SKILL.md) — upstream: produces the candidate set.
- [novokine_validation](../novokine_validation/SKILL.md) — pre-handoff sanity checks AND post-design re-validation.
- [COT_Rejuv_Pipeline](../COT_Rejuv_Pipeline/SKILL.md) — downstream phenotype scoring after the new minibinder exists.
- [analysis_to_slurm_runner](../analysis_to_slurm_runner/SKILL.md) — for actually launching the design job on HPC.
- [target_dossier](../target_dossier/SKILL.md) — to deepen receptor / epitope knowledge before manifest emission.
