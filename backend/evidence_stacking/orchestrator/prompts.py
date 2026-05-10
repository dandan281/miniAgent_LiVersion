"""Agent prompts: PROPOSE_FEATURE, WRITE_MISSES, DECIDE_STOP."""
from __future__ import annotations

from textwrap import dedent


SYSTEM = dedent("""
    You are the orchestrator of an evidence-stacking pipeline that ranks 1,711
    bispecific receptor pairs for muscle rejuvenation and fibroblast→muscle
    transdifferentiation. The methodology mirrors the attached Novokine
    Bispecific Receptor Pair Ranking paper: at each stage you ADD ONE FEATURE
    to an equal-weight additive composite, evaluate the change against held-out
    atlas reward correlation (Spearman ρ on both `aged_young` and `fibro_muscle`
    targets), and write a "Misses and limitations" analysis.

    You have access to 23 LangChain biology tools (omnipath_api, reactome_api,
    biogrid_orcs, phosphosite_plus, uniprot_api, ncbi_eutils, local_atlas_query,
    cellxgene_expression, etc.). You write Python feature classes that read from
    a per-pair `PairEvidence` dict. The evidence-gathering pass calls your tools
    on all 1,711 pairs.

    Retention rule: KEEP iff max(Δρ) > 0 AND min(Δρ) > -0.05 across the two
    targets. Drop otherwise.
""").strip()


PROPOSE_FEATURE = dedent("""
    You are at stage v{stage_index}. Current composite: `{composite_version}`.
    Current Spearman ρ on holdout:
      aged_young:   {rho_aged_young:+.3f}
      fibro_muscle: {rho_fibro_muscle:+.3f}

    Stage seed (paper-aligned, optional): {seed_hint}

    Misses summary from the previous stage:
    {prior_misses}

    Available tools (don't list, just know they exist):
      omnipath_api, reactome_api, biogrid_orcs, phosphosite_plus, uniprot_api,
      ncbi_eutils, local_atlas_query, cellxgene_expression, search_knowledge_base,
      fetch_url, read_file, python_repl, write_file.

    Propose ONE new feature to add to the composite. Return STRICT JSON:
    {{
      "name": "snake_case_name",
      "description": "<= 200 chars, what it computes",
      "biological_motivation": "2-4 sentences, must reference at least one tool you'll call",
      "required_evidence": ["evidence_key_1", "evidence_key_2"],
      "compute_pseudocode": "Python-like, 5-15 lines, deterministic transform of evidence dict to a float",
      "tool_plan": [
        {{"tool": "tool_name", "action": "...", "per_receptor_or_pair": "pair|receptor_a|receptor_b"}}
      ]
    }}

    Constraints:
      - Feature must be DETERMINISTIC given evidence (no randomness, no LLM calls in compute).
      - `required_evidence` keys must be the same ones populated by `tool_plan`.
      - Compute returns a float (any range; the framework normalizes to [0,1]).
      - Do not propose a feature that's already in the composite: {existing_features}.
""").strip()


WRITE_MISSES = dedent("""
    Composite v{composite_version} just scored. Top disagreements between the
    composite ranking and target signal (top-N pairs sorted by |rank_score -
    rank_target|):

    aged_young:
    {disagreements_aged_young}

    fibro_muscle:
    {disagreements_fibro_muscle}

    Per-feature contributions for the worst 3 false negatives (composite ranks
    them low; target ranks them high):
    {feature_contributions}

    Write a "Misses and limitations" section in the format the methods doc uses
    (mirrors §3.X "Misses and limitations at vN"). 3-5 paragraphs. Cover:
      1. Pattern in the worst false negatives (which receptor classes/pairs)
      2. Which feature is over- or under-weighted and why
      3. Mechanistic explanation (what the composite cannot capture)
      4. Concrete next-feature seed: name + which tool would gather it

    Return plain markdown (no JSON, no headers above H3).
""").strip()


DECIDE_STOP = dedent("""
    State:
      stage_index: {stage_index}
      consecutive_drops: {fail_streak}
      latest_rho: aged_young={rho_aged_young:+.3f}, fibro_muscle={rho_fibro_muscle:+.3f}
      max_stages: {max_stages}
      stop_threshold_rho: {stop_rho}

    Should the loop stop? Return strict JSON:
      {{"stop": bool, "reason": "<= 200 chars"}}

    Hard stops (non-negotiable):
      - fail_streak >= {max_fail_streak}
      - stage_index >= max_stages
      - both rho values >= stop_rho
""").strip()
