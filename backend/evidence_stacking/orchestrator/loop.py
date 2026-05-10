"""Main orchestrator loop — propose → implement → gather → score → evaluate → report."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..composites import composite as comp_mod
from ..composites import loader as comp_loader
from ..composites.loader import CompositeManifest, FeatureRef
from ..evidence.envelope import PairEvidence
from ..evidence.store import EvidenceStore
from ..evaluator import atlas_reward, metrics, retention, stage_report
from ..features import registry
from ..pair import ReceptorPair
from ..receptor_universe import load as load_universe
from .agents import ClaudeAgent, MockAgent, OrchestratorAgent, StageContext
from .feature_writer import materialize, archive
from .state import RunLedger


_PAPER_SEED_HINTS = {
    1: "Stage v4 — novelty filter (PubMed cocite + BioGRID PPI), per §3.2 of the methods doc",
    2: "Stage v5+PW — pathway co-activation via reactome_api / omnipath_api, per §3.3",
    3: "Stage v6 — KEGG anti-fibrosis pathway membership, per §3.5 (often dropped — fine)",
    4: "Stage v7 — fibroblast expression enrichment via cellxgene_expression, per §3.6",
    5: "Stage v8 — paper-derived ACVRL1 / FGFR features, per §3.7",
}


def _holdout_scores(score_map: dict[str, float], target_map: dict[str, float]) -> dict[str, float]:
    _, holdout = atlas_reward.split(target_map)
    return {k: v for k, v in score_map.items() if k in holdout}


def _holdout_metrics(score_map: dict[str, float]) -> dict[str, metrics.MetricsBundle]:
    out: dict[str, metrics.MetricsBundle] = {}
    for tgt_name in atlas_reward.TARGETS:
        target = atlas_reward.load(tgt_name)
        _, holdout = atlas_reward.split(target)
        s = {k: v for k, v in score_map.items() if k in holdout}
        out[tgt_name] = metrics.metrics_bundle(s, holdout)
    return out


def _ensure_baseline_evaluated(ledger: RunLedger) -> CompositeManifest:
    """If no v40 record in ledger, score it now and append. Returns v40 manifest."""
    v40 = comp_loader.load("v40")
    if any(r.composite_version == "v40" and r.decision == "KEEP" for r in ledger.records):
        return v40

    universe = load_universe()
    pairs = list(universe.pairs())
    scores = comp_mod.score_all(v40, pairs)
    score_map = {pid: cs.score for pid, cs in scores.items()}
    metr = _holdout_metrics(score_map)

    rho = {t: m.rho for t, m in metr.items()}
    decision = retention.decide({t: 0.0 for t in rho}, rho)
    report = stage_report.write(
        0,
        v40,
        metr,
        decision,
        misses_md="_(baseline — no prior to compare against)_",
        feature_name="atlas_coexpression",
        biological_motivation=(
            "Class-pair prior + atlas DEG membership bonus. Baseline mirrors §3.1 of "
            "the methods doc — a deliberately weak heuristic to be improved via stacking."
        ),
        next_hypothesis="Add a novelty filter (paper §3.2) — likely largest single-feature win.",
        prev_rho={t: 0.0 for t in rho},
    )

    # Stamp rho_at_commit on the manifest
    v40_path = Path(__file__).resolve().parent.parent / "composites" / "v40.json"
    v40_data = json.loads(v40_path.read_text())
    v40_data["rho_at_commit"] = rho
    v40_path.write_text(json.dumps(v40_data, indent=2))

    ledger.append(
        stage_index=0,
        feature_name="atlas_coexpression",
        composite_version="v40",
        decision="KEEP",
        rho=rho,
        deltas={t: rho[t] for t in rho},
        report_path=str(report),
    )
    return comp_loader.load("v40")


def run(
    *,
    max_stages: int = 20,
    stop_consecutive_fails: int = 3,
    stop_rho: float = 0.70,
    agent: OrchestratorAgent | None = None,
) -> dict:
    """Returns a dict summarising the run."""
    ledger = RunLedger()
    agent = agent or MockAgent()
    universe = load_universe()
    all_pairs = list(universe.pairs())
    store = EvidenceStore()

    parent_manifest = _ensure_baseline_evaluated(ledger)
    next_stage_index = ledger.stage_index  # number of KEEPs so far

    while True:
        latest = ledger.latest_kept()
        rho_now = ledger.latest_rho()

        ctx = StageContext(
            stage_index=next_stage_index,
            composite_version=parent_manifest.version,
            rho=rho_now,
            prior_misses="(see prior stage_report)",
            seed_hint=_PAPER_SEED_HINTS.get(next_stage_index, ""),
            existing_features=[f.name for f in parent_manifest.features],
            fail_streak=ledger.fail_streak(),
            max_stages=max_stages,
            stop_rho=stop_rho,
        )

        # Hard stops
        if ctx.stage_index >= max_stages:
            return {"status": "stop", "reason": "max_stages", "ledger": [asdict(r) for r in ledger.records]}
        if ctx.fail_streak >= stop_consecutive_fails:
            return {"status": "stop", "reason": "fail_streak", "ledger": [asdict(r) for r in ledger.records]}
        if rho_now and all(v >= stop_rho for v in rho_now.values()):
            return {"status": "stop", "reason": "rho_threshold", "ledger": [asdict(r) for r in ledger.records]}

        # 1) Propose
        try:
            proposal = agent.propose(ctx)
        except StopIteration:
            return {"status": "stop", "reason": "agent_exhausted", "ledger": [asdict(r) for r in ledger.records]}

        # 2) Materialize feature class
        try:
            feature_path = materialize(proposal, stage_index=ctx.stage_index + 1)
        except FileExistsError:
            # Already on disk from a prior run; skip materialize
            feature_path = Path(__file__).resolve().parent.parent / "features" / f"{proposal.name}.py"

        # Force re-import so the registry picks up the new file
        feature = registry.load(proposal.name)

        # 3) Gather evidence
        keys_needed = list(feature.required_evidence)
        if keys_needed:
            new_data = agent.gather(all_pairs, keys_needed, proposal)
            for pair in all_pairs:
                ev = store.load(pair.pair_id)
                row = new_data.get(pair.pair_id, {})
                for k, v in row.items():
                    ev.put(k, v, source=f"agent:{proposal.name}", version=feature.version)
                store.save(ev)

        # 4) Build candidate composite + score
        candidate_version = f"v{ctx.stage_index + 1}_{proposal.name}"
        candidate = comp_mod.extend(parent_manifest, feature, stage_index=ctx.stage_index + 1, version=candidate_version)
        scores = comp_mod.score_all(candidate, all_pairs)
        score_map = {pid: cs.score for pid, cs in scores.items()}

        # 5) Evaluate
        metr = _holdout_metrics(score_map)
        new_rho = {t: m.rho for t, m in metr.items()}
        decision = retention.decide(rho_now, new_rho)

        # 6) Misses analysis
        disagreements = {t: m.top_disagreements for t, m in metr.items()}
        feat_contrib = ""  # could derive from per-feature components
        misses = agent.write_misses(candidate.version, disagreements, feat_contrib)

        # 7) Stage report
        report = stage_report.write(
            ctx.stage_index + 1,
            candidate,
            metr,
            decision,
            misses_md=misses,
            feature_name=proposal.name,
            biological_motivation=proposal.biological_motivation,
            next_hypothesis=_PAPER_SEED_HINTS.get(ctx.stage_index + 1, ""),
            prev_rho=rho_now,
        )

        # 8) Commit or archive
        if decision.keep:
            comp_loader.save(
                CompositeManifest(
                    version=candidate.version,
                    parent=candidate.parent,
                    stage_index=candidate.stage_index,
                    weights=candidate.weights,
                    features=candidate.features,
                    agent_rationale=proposal.description,
                    rho_at_commit=new_rho,
                )
            )
            ledger.append(
                stage_index=ctx.stage_index + 1,
                feature_name=proposal.name,
                composite_version=candidate.version,
                decision="KEEP",
                rho=new_rho,
                deltas=decision.deltas,
                report_path=str(report),
            )
            parent_manifest = comp_loader.load(candidate.version)
            next_stage_index += 1
        else:
            archive(feature_path, reason=decision.reason)
            ledger.append(
                stage_index=ctx.stage_index + 1,
                feature_name=proposal.name,
                composite_version=candidate.version,
                decision="DROP",
                rho=new_rho,
                deltas=decision.deltas,
                report_path=str(report),
            )
            # Drop the registry entry so a future re-attempt with same name still loads fresh
            registry._REGISTRY.pop(proposal.name, None)
