# Novokines — Canonical Knowledge

This is the reference document for any skill that touches **novokines**, **minibinders**, or **de novo synthetic receptor agonists**. Skills should `search_knowledge_base` here before falling back to the open web.

---

## 1. Concept

A **novokine** is a de novo designed synthetic protein ligand built by **fusing two computationally designed receptor-binding domains (minibinders)** via a flexible peptide linker. The dimer simultaneously engages two distinct cell-surface receptors and forces them into proximity, producing **biased agonist signaling** that natural ligands often cannot reproduce.

Key conceptual moves:

- **Minibinder**: a small (~50–110 aa) de novo designed mini-protein that binds a single defined receptor at a defined epitope. Designed via RFdiffusion / ProteinMPNN / AlphaFold2 (or BindCraft / BoltzGen).
- **Antagonist as monomer**: a single minibinder bound to its receptor occupies the binding surface but typically fails to drive productive signaling — it acts as an **antagonist**.
- **Agonist as fused dimer**: connecting two minibinders with a linker yields a single bivalent molecule that drags two receptors into proximity. For receptor families that signal via dimerization / clustering (RTKs, cytokine receptors of the JAK-STAT family, TNFR superfamily, etc.), forced co-clustering triggers cross-phosphorylation and downstream signaling — often a **biased subset** of the natural pathway.
- **Programmable platform**: any AI-designed minibinder pair defines a new novokine. The receptor pair does **not** need to dimerize naturally; it does not even need to share a natural ligand.

---

## 2. Exemplar — H2F

H2F is the canonical published novokine (Edman / Cheng / ... / Baker / Ruohola-Baker, 2025).

- **Pairs**: HER2 (ERBB2; no known natural ligand) + FGFR1/2c.
- **Activates**: MAPK and AKT branches.
- **Bypasses**: PLCγ / Ca²⁺ branch — a **biased output** unattainable with natural FGF ligands, which co-engage all three branches.
- **Functional consequences**:
  - Reprograms fibroblasts toward skeletal muscle cells.
  - Enhances myotube formation and maturation in patient-derived myoblasts.
  - Sustains stem cell pluripotency.
  - Biases vascular differentiation toward perivascular over endothelial fate.

H2F is the **positive control** for any rejuvenation / muscle-regeneration screen built on novokines.

---

## 3. Generalized findings from the companion papers

Three papers from the Baker lab and collaborators released together on Oct 13, 2025 establish novokines as a platform, not a single molecule:

### 3a. High-Throughput De Novo Protein Design Yields Novel Immunomodulatory Agonists
*Abedi, Expòsit, Coventry, ... Ruohola-Baker, Wherry, Baker (2025)*
- bioRxiv: `https://www.biorxiv.org/content/10.1101/2025.10.12.681920v1`
- PubMed: `https://pubmed.ncbi.nlm.nih.gov/41279583/`

Key findings:
- Generated **>1,000 novokines from 33 designed receptor-binding domains**.
- **75 activated pSTAT signaling** in human PBMCs.
- **IFNAR1 emerged as a versatile common receptor** — analogous to γcommon or βcommon — that, when paired with diverse partner receptors, can generate distinct cytokine-like outputs. This is a major finding: it identifies a "hub" receptor for novokine engineering.
- Demonstrates that novokine biology is **statistically tractable**: a meaningful fraction of random pairings produce signal.

### 3b. Geometric Tuning of Cytokine Receptor Association Modulates Synthetic Agonist Signaling
*Expòsit, Abedi, Krishnakumar, ... Baker (2025)*
- bioRxiv: `https://www.biorxiv.org/content/10.1101/2025.10.12.681819v1`

Key findings:
- A **rigidly scaffolded** de novo design platform places two receptor-binding domains at *defined* relative orientations and distances.
- Applied to: IL-7, type I/III interferons, IL-10, gp130, βcommon, and synthetic pairs.
- **Receptor geometry biases pSTAT pathway usage** — the same minibinder pair can produce different signaling outputs purely by changing the inter-domain rigid scaffold.
- Implication for design: linker / scaffold rigidity and length is a **first-class design variable**, not an afterthought.

### 3c. De novo design of cytokines, antikines, and novokines (2022, Thieme)
- `https://www.thieme-connect.com/products/ejournals/html/10.1055/s-0042-1748728`
- Earlier conceptual framing: cytokines (natural agonists), **antikines** (designed antagonists, single minibinders), and **novokines** (designed agonists, fused minibinder pairs).

---

## 4. Adjacent / foundational work the agent should know

### Synthekines — Zhao et al., *Nature* 2025
- PubMed: `40804519`
- Cited as ref. 32 in the H2F paper.
- Uses **non-native receptor pairings** to produce JAK-STAT signals that diversify T cell states. Same conceptual family as novokines — different design approach (not necessarily fused minibinders), same outcome: receptor remixing produces new signals.

### Edman et al., *Cell* 2024 — FGF pathway designed oligomers
- DOI: `10.1016/j.cell.2024.05.025`
- Cited as ref. 1 in the H2F paper.
- Designed oligomeric assemblies that target FGFR1/2c, including **C6-79C-mb7** — the FGFR-side minibinder later reused in H2F.
- Establishes that **oligomeric state** (not just pair geometry) tunes FGF pathway output and vascular differentiation.

---

## 5. Receptor families amenable to forced-dimerization agonism

Forced-proximity agonism works best when the receptor's natural signaling mechanism is **clustering- or dimerization-dependent**. The agent should expect productive novokine design for:

- **Receptor tyrosine kinases (RTKs)**: EGFR/ERBB family, FGFR1–4, IGF1R, INSR, MET, VEGFR, TIE1/2, AXL/MERTK, EPHA/EPHB, RET, PDGFRα/β, KIT, NTRK1/2/3.
- **Cytokine / JAK-STAT receptors**: type I and type II receptors that signal via heterodimer assembly with γcommon, βcommon, gp130, IFNAR1/2, IFNGR1/2, IL10R1/2, etc.
- **TNFR superfamily**: trimerization-dependent; pair design must respect 3-fold symmetry, but multimerization can be engineered.
- **TGF-β / BMP receptors**: type I + type II heterodimer requirement makes them a natural fit.
- **Single-pass adhesion / Notch-family receptors**: dimerization sometimes productive, sometimes not — case-by-case.

Receptor families where forced-proximity agonism is **less plausible**:

- **GPCRs**: most signal monomerically through conformational change in the 7TM bundle; dragging two GPCRs together rarely substitutes for the cognate ligand-induced conformational switch. (Some exceptions for class C dimers — mGluR, GABA-B — and biased cases.)
- **Ion channels**: ligand-gated channels do not generally respond to extracellular dimerization.
- **Intracellular / nuclear receptors**: not on the cell surface, not addressable by an extracellular novokine.

---

## 6. Design parameters worth tracking for any candidate

| Parameter | Why it matters |
|---|---|
| Receptor identity (A, B) | Determines the natural pathway space; some receptors are orphan (HER2, IFNAR1 as hub) |
| Minibinder source | Published library (Cao / Baker releases), de novo designed per project, or computational variant |
| Minibinder size (aa) | Typically 50–110; affects expression, immunogenicity, structural rigidity |
| Epitope on each receptor | Different epitopes on the same receptor can produce different biased outputs |
| Linker length and composition | Glycine-serine flexible vs. rigid helical scaffold; per Expòsit et al., this is a first-class variable |
| Inter-domain geometry (if rigid scaffold) | Distance and rotation between the two binding domains tunes pSTAT pathway bias |
| Cell-surface co-expression of A and B in target cell | If both receptors are not present on the same cell, the novokine cannot act |
| Predicted affinity for each receptor (KD) | Single-digit nM is the typical target |
| Predicted complex (AF2 / Boltz pAE_interaction, pLDDT) | Standard filters: pAE_interaction < 7.5, pLDDT > 85 for the binding interface |

---

## 7. Tooling landscape (for design hand-off)

| Tool | Role | Where it runs |
|---|---|---|
| **RFdiffusion** | Backbone generation for the minibinder against a target receptor surface | Open source; hosted on Superbio.ai (`https://app.superbio.ai/apps/655b1f47a9ed6f6e5560ba8f`) |
| **ProteinMPNN** | Sequence design conditioned on the RFdiffusion backbone | Open source; downstream of RFdiffusion |
| **AlphaFold2 / AF2 Initial Guess** | Structure validation and pAE_interaction filtering | Open source; many platforms |
| **Boltz-2 / BoltzGen / BoltzDesign1** | Newer alternatives to AF2 — Boltz-2 for structure + affinity prediction; BoltzGen for end-to-end binder generation; BoltzDesign1 for non-protein targets | Open source / Rowan / boltz.bio |
| **BindCraft** | One-shot binder design via backprop through AF2; high reported success rate | Open source (Pacesa et al., *Nature* 2025) |
| **ProteinDJ** | Nextflow pipeline that chains RFdiffusion or BindCraft → ProteinMPNN or FAMPNN → AF2 or Boltz-2 | Open source (Papenfuss lab, 2025) |
| **RFantibody** | RFdiffusion variant for VHH / antibody design | Hosted on Superbio.ai (`https://app.superbio.ai/apps/67e6ba077d733b5d5294fd0c`) |

**Open question to resolve**: Lab user recalls a Superbio.ai app that runs the full novokine design loop (RFdiffusion + ProteinMPNN + a Boltz-family validator) end-to-end. As of the last check, Superbio.ai exposes RFdiffusion and ProteinMPNN as **separate** apps and we have not verified an integrated one-shot novokine pipeline. The closest functional equivalents are **BindCraft**, **BoltzGen**, **BoltzDesign1**, and **ProteinDJ**, none of which appear to be currently hosted on Superbio. Update this section when the app is confirmed.

---

## 8. Source papers — cite when reasoning

1. **H2F paper** (Baker / Ruohola-Baker labs, 2025) — primary novokine demonstration, HER2 + FGFR1/2c, muscle reprogramming.
2. **Abedi, Expòsit, Coventry, ... Baker (2025)** — high-throughput novokine generation, IFNAR1 hub. bioRxiv `10.1101/2025.10.12.681920v1`, PMID `41279583`.
3. **Expòsit, Abedi, Krishnakumar, ... Baker (2025)** — geometric tuning of receptor association. bioRxiv `10.1101/2025.10.12.681819v1`.
4. **Silva / Yang / Baker et al. (2022)** — "De novo design of cytokines, antikines, and novokines" — Thieme `10.1055/s-0042-1748728`.
5. **Zhao et al., *Nature* (2025)** — synthekines, T cell state diversification. PMID `40804519`.
6. **Edman et al., *Cell* (2024)** — FGF designed oligomers. DOI `10.1016/j.cell.2024.05.025`.
7. **Pacesa et al., *Nature* (2025)** — BindCraft.
8. **ProteinDJ** — bioRxiv `10.1101/2025.09.24.678028v2`.
9. **BoltzGen** (Stark et al., MIT Jameel Clinic, 2025) — bioRxiv `10.1101/2025.11.20.689494v1`.

---

## 9. Standing assumptions used by downstream skills

When a downstream skill does not explicitly override:

- "Novokine" = fused dimer of two minibinders, intended as an agonist by forced co-clustering.
- The two minibinders are assumed to bind their stated receptors with reasonable affinity — upstream affinity validation is a separate skill (`novokine_validation`).
- Default cell context for the muscle rejuvenation project: human skeletal muscle (myoblast, myotube, muscle stem cell, FAP).
- Default scoring frame: P2 (young, 25–35) vs P1 (aged, 65+) DE from the human skeletal muscle cell atlas.
- Default design pipeline: RFdiffusion → ProteinMPNN → AF2-or-Boltz-2 validation, unless the user names a specific platform (BindCraft, BoltzGen, ProteinDJ).
