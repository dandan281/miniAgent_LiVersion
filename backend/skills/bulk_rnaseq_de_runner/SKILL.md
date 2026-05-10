---
name: bulk_rnaseq_de_runner
description: Run a fresh DESeq2 differential-expression analysis on a public GEO bulk RNA-seq dataset and emit a canonical aging-studies TSV that the v2 consensus atlas builder can ingest.
category: bio/bulk_rna
version: 1.0
requires_tools: [terminal, python_repl, fetch_url, read_file]
requires_network: true
user_invocable: true
tags: [bulk-rnaseq, deseq2, geo, differential-expression, consensus-atlas]
aliases: [geo_deseq, run_deseq, bulk_de_runner]
species: human
modality: bulk_rna
stage: data_intake
stability: stable
safety_level: low
---

# Bulk RNA-seq DESeq2 Runner

## Purpose

Convert a public GEO bulk RNA-seq study into a canonical DEG TSV that drops directly into `backend/knowledge/aging_studies/{study_id}/deg_table.tsv` and is auto-ingested by `backend/scripts/build_consensus_atlas.py`. **This is the execution counterpart to the existing `differential_expression_helper` skill**, which only interprets pre-computed tables.

Use when:
- The user wants to add a new aging dataset to the v2 consensus atlas and has only the GEO accession (not a pre-computed DEG table).
- You need to reproduce a published bulk RNA-seq DE result with a custom design.
- A study's published Supp Data has gene lists but no logFC/padj (e.g. Tumasian 2021).

Do **not** use when:
- The study is single-cell — use `local_atlas_query` or scGPT-based skills instead.
- The dataset is GTEx-scale (~800+ donors) — PyDESeq2 is slow at that size; either down-sample or use the user's R/limma output.
- A clean DEG table is already public (e.g. Pillon's Supp Data 4) — just extract the xlsx with a script under `backend/scripts/`.

## Required inputs

- **`accession`**: GEO Series ID (e.g. `GSE164471`).
- **`counts_url`**: HTTP(S) URL of the supplementary counts file (gene × sample matrix). Find it at `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}` under Supplementary Files, OR by listing `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE{NNN}nnn/{accession}/suppl/`.
- **`sample_regex`**: Python regex with named groups extracted from sample column names. **Must include `age` (int)**. Common covariates: `sex` (M/F), `donor`, `batch`. Example: `MUSCLE_AGE(?P<age>\d+)_(?P<sex>[MF])_GROUP`.
- **`condition_rule`**: Semicolon-separated `expr:label` clauses, evaluated against the metadata DataFrame. Examples:
    - `age<=30:young;age>=60:old` → strict young/old, drop middle.
    - `disease=='sarcopenic':old;disease=='control':young` (if regex captured `disease`).
- **`design`**: DESeq2-style formula. Last term is treated as the test variable. Default `~ condition`. With confounders: `~ sex + condition` (recommended for human bulk).
- **`gene_id_col`** + **`gene_symbol_col`**: column names in the counts file for Ensembl ID and HGNC symbol.

## Steps

1. **Confirm the GEO supplementary file is appropriate** — use `fetch_url` to GET `https://ftp.ncbi.nlm.nih.gov/geo/series/.../suppl/` and identify a counts file (not just TPM, not just raw FASTQ pointers). Look for filenames containing `count`, `htseq`, `featurecounts`, or similar.
2. **Inspect the header** — use `terminal` to `zcat <file> | head -3 | cut -c 1-400` to verify:
    - One column per sample
    - Sample names embed metadata (age, sex, condition) OR a separate sample-attributes file is needed
    - Gene IDs in row labels (Ensembl is preferred; gene symbols also fine)
    - Annotation columns at end (chromosome, biotype, symbol) for gene-name resolution
3. **Compose the regex** — fit a Python regex against ONE sample column to verify the `age` group captures correctly. Use `terminal` to test: `python3 -c "import re; print(re.search(r'PATTERN', 'SAMPLE_NAME').groupdict())"`.
4. **Run the script**:
    ```bash
    python backend/scripts/run_geo_deseq.py \
      --accession GSE_ID \
      --counts-url URL \
      --sample-regex 'REGEX' \
      --condition-rule 'EXPR:young;EXPR:old' \
      --design '~ sex + condition' \
      --gene-id-col Tracking_ID \
      --gene-symbol-col 'GENE_SYMBOL_COLUMN_NAME' \
      --output backend/knowledge/aging_studies/{study_id}/deg_table.tsv
    ```
5. **Verify the result** — top hits in the script output should include canonical aging biology (CDKN1A/p21, CDKN2B/p15, EDA2R, OSTN for muscle aging; GPX3, NEAT1, TXNIP, SAT1 for senescence). If top hits are nonsensical, re-check the contrast direction (`--contrast-test old --contrast-ref young` means logFC = old − young; positive = up in aged).
6. **Set `consensus_thresholds` in metadata.json** if `padj < 0.05` yields too few hits (under ~50 for n<60 cohorts). Use the per-paper published cutoff. Document the rationale in the metadata.
7. **Rebuild the v2 atlas**:
    ```bash
    python backend/scripts/build_consensus_atlas.py
    pytest backend/tests/test_consensus_atlas.py -v
    ```

## Output format

The script writes a tab-separated file:
```
gene_symbol  log2fc  padj  pvalue  ensembl_id
ACTA1        +1.42   0.0023 1.4e-5  ENSG00000143632
TXNIP        +0.85   0.012  6.7e-4  ENSG00000265972
...
```

This matches `backend/knowledge/aging_studies/_schema.md` exactly. The consensus builder's `_load_bulk_tsv()` ingests it without further conversion.

## Failure modes

- **Counts file is TPM/FPKM, not raw counts**: DESeq2 requires integer counts. Find the right supplementary file (often labeled `counts`, `htseq`, `featureCounts`).
- **Sample regex doesn't match**: re-inspect the column header and adjust. Common pitfalls: extra underscores, mixed-case `M`/`F`, age embedded in a separate file.
- **No condition assigned to any sample**: the rule's expression syntax must use pandas `eval()` semantics. Check named groups vs string vs int comparisons (regex captures are strings unless coerced, and `age` is auto-coerced to int).
- **PyDESeq2 deprecation warning** about `design_factors`: ignore, doesn't affect output.
- **Re-derivation is not byte-identical to published paper**: expected. Document this in `metadata.json.table_provenance`.

## Examples

- `"Add the GSE164471 Tumasian skeletal muscle aging dataset to the v2 atlas."` → run with strict ≤30/≥60 + `~ sex + condition`.
- `"We need DEG calls for [GSE_NEW] case-control comparison."` → identify counts file, parse sample metadata, run `~ condition`.
- `"Reproduce the muscle disuse signature from Wickramasinghe 2022."` → counts URL + sample regex + `~ donor + condition` for paired-design studies.

## Cross-references

- **Sibling skill**: `differential_expression_helper` (interprets a DE table, doesn't run one).
- **Atlas integration**: `backend/scripts/build_consensus_atlas.py` and `backend/knowledge/aging_studies/_schema.md` define the canonical ingestion format.
- **Source script**: `backend/scripts/run_geo_deseq.py` is the implementation; this skill documents how to drive it.
