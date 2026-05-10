"""Agent abstraction — Mock for tests, Claude for live runs.

The orchestrator depends on this Protocol, not on any specific provider. The
CLI selects which implementation to wire in. Both implementations expose:

  - propose(...) -> FeatureProposal     LLM is given prior-stage context and
                                          returns a JSON proposal for one new
                                          feature.
  - gather(...) -> dict[pair_id, dict]   For each (pair, evidence_key), produce
                                          a value. Real implementations call
                                          LangChain biology tools.
  - write_misses(...) -> str             LLM analyzes top disagreements and
                                          writes the "Misses and limitations"
                                          markdown.
  - decide_stop(...) -> bool             LLM (or rule) decides whether to stop.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from ..pair import ReceptorPair
from .feature_writer import FeatureProposal


@dataclass
class StageContext:
    stage_index: int
    composite_version: str
    rho: dict[str, float]
    prior_misses: str
    seed_hint: str
    existing_features: list[str]
    fail_streak: int
    max_stages: int
    stop_rho: float


class OrchestratorAgent(Protocol):
    def propose(self, ctx: StageContext) -> FeatureProposal: ...
    def gather(
        self,
        pairs: Iterable[ReceptorPair],
        keys: Iterable[str],
        proposal: FeatureProposal,
    ) -> dict[str, dict[str, Any]]: ...
    def write_misses(
        self,
        composite_version: str,
        disagreements: dict[str, list],
        feature_contributions: str,
    ) -> str: ...
    def decide_stop(self, ctx: StageContext) -> tuple[bool, str]: ...


# ---------------------------------------------------------------------------
# Mock agent — deterministic, used for smoke tests and CI.
# ---------------------------------------------------------------------------


_MOCK_PROPOSALS = [
    FeatureProposal(
        name="novelty_filter",
        description="Down-weight pairs with high prior PubMed co-citation; mirrors paper §3.2.",
        biological_motivation=(
            "Per the attached methods doc §3.2 the novelty filter produced the largest "
            "single-feature AUROC gain (+0.32). It penalizes well-studied receptor pairs "
            "whose hit-rate is already known (e.g. EGFR-ERBB2). We use ncbi_eutils to count "
            "PubMed co-occurrences."
        ),
        required_evidence=["pubmed_cocite_count"],
        compute_pseudocode=(
            "n = ev.get('pubmed_cocite_count', 0)\n"
            "import math\n"
            "return -math.log1p(n)  # negative log so high co-cite -> low score"
        ),
        tool_plan=[
            {"tool": "ncbi_eutils", "action": "esearch_count", "per_receptor_or_pair": "pair"}
        ],
    ),
    FeatureProposal(
        name="pathway_coactivation",
        description="Reactome pathway overlap between the two receptors. Mirrors §3.3.",
        biological_motivation=(
            "Pairs whose downstream pathways overlap are more likely to produce coherent "
            "signaling. We use reactome_api to fetch pathway sets for each receptor and "
            "compute Jaccard overlap."
        ),
        required_evidence=["reactome_jaccard"],
        compute_pseudocode="return float(ev.get('reactome_jaccard', 0.0))",
        tool_plan=[
            {"tool": "reactome_api", "action": "pathways_for_genes", "per_receptor_or_pair": "pair"}
        ],
    ),
]


class MockAgent:
    """Deterministic agent for smoke tests."""

    def __init__(self) -> None:
        self._proposal_idx = 0

    def propose(self, ctx: StageContext) -> FeatureProposal:
        for p in _MOCK_PROPOSALS[self._proposal_idx:]:
            if p.name not in ctx.existing_features:
                self._proposal_idx = _MOCK_PROPOSALS.index(p) + 1
                return p
        raise StopIteration("MockAgent exhausted its proposal list")

    def gather(
        self,
        pairs: Iterable[ReceptorPair],
        keys: Iterable[str],
        proposal: FeatureProposal,
    ) -> dict[str, dict[str, Any]]:
        keys = list(keys)
        out: dict[str, dict[str, Any]] = {}
        for p in pairs:
            row: dict[str, Any] = {}
            for k in keys:
                # Cheap deterministic stub: hash-based pseudo-value in [0,1]
                # Uses pair.a + pair.b + key so values are stable across runs.
                import hashlib
                h = int(hashlib.sha256(f"{p.a}|{p.b}|{k}".encode()).hexdigest()[:8], 16)
                row[k] = (h % 1000) / 1000.0
            out[p.pair_id] = row
        return out

    def write_misses(
        self,
        composite_version: str,
        disagreements: dict[str, list],
        feature_contributions: str,
    ) -> str:
        return (
            f"_(MockAgent)_ Composite {composite_version} disagreements:\n"
            + "\n".join(
                f"- {tgt}: top disagreement {d[0][0] if d else 'n/a'}"
                for tgt, d in disagreements.items()
            )
        )

    def decide_stop(self, ctx: StageContext) -> tuple[bool, str]:
        if ctx.stage_index >= ctx.max_stages:
            return True, "max_stages reached"
        if ctx.fail_streak >= 3:
            return True, f"fail_streak={ctx.fail_streak}"
        if all(v >= ctx.stop_rho for v in ctx.rho.values()):
            return True, "all targets >= stop_rho"
        return False, "continue"


# ---------------------------------------------------------------------------
# Claude agent — live runs against Anthropic API.
# ---------------------------------------------------------------------------


class ClaudeAgent:
    """Live agent. Uses the anthropic SDK directly for propose/misses/decide.

    Defaults: Claude Opus 4.7 (1M context) with extended thinking at the
    maximum supported budget. Per the user's autonomous-long-runs preference,
    multi-hour runs should use Opus + max thinking so the per-stage "Misses
    and limitations" analysis gets the deepest reasoning the model offers.

    Evidence gather (the tool-driven part) hands off to a separate helper that
    drives LangChain biology tools. Until that's wired, gather() falls back to
    the mock pseudo-value generator so the loop still runs end-to-end.
    """

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-7",
        max_tokens: int = 32_000,
        thinking_effort: str | None = "high",
        long_context: bool = True,
    ) -> None:
        """thinking_effort: 'high' | 'medium' | 'low' | None. None disables extended thinking."""
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "anthropic SDK not installed. `pip install anthropic` first."
            ) from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY env var must be set for ClaudeAgent.")
        if thinking_effort is not None and thinking_effort not in {"high", "medium", "low"}:
            raise ValueError(f"thinking_effort must be high/medium/low/None, got {thinking_effort!r}")
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_effort = thinking_effort
        self.long_context = long_context
        self._mock_for_gather = MockAgent()  # placeholder until tool-loop is wired

    def _call(self, prompt: str, *, json_mode: bool = False) -> str:
        import anthropic
        from .prompts import SYSTEM
        client = anthropic.Anthropic()
        instr = prompt
        if json_mode:
            instr += "\n\nRespond with strict JSON only. No prose, no markdown fences."
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": instr}],
        }
        if self.thinking_effort is not None:
            # Adaptive thinking: model decides depth, output_config.effort caps it.
            # Extended thinking requires temperature=1 (Anthropic API constraint).
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": self.thinking_effort}
            kwargs["temperature"] = 1.0
        betas: list[str] = []
        if self.long_context:
            betas.append("context-1m-2025-08-07")
        if betas:
            kwargs["betas"] = betas
            msg = client.beta.messages.create(**kwargs)
        else:
            msg = client.messages.create(**kwargs)
        # Take the first text block (skip thinking blocks — they're internal).
        for block in msg.content:
            if getattr(block, "type", "") == "text":
                return block.text
        return ""

    def propose(self, ctx: StageContext) -> FeatureProposal:
        from . import prompts
        prompt = prompts.PROPOSE_FEATURE.format(
            stage_index=ctx.stage_index,
            composite_version=ctx.composite_version,
            rho_aged_young=ctx.rho.get("aged_young", 0.0),
            rho_fibro_muscle=ctx.rho.get("fibro_muscle", 0.0),
            seed_hint=ctx.seed_hint or "(none)",
            prior_misses=ctx.prior_misses or "(none)",
            existing_features=ctx.existing_features,
        )
        raw = self._call(prompt, json_mode=True)
        return FeatureProposal.from_json(raw)

    def gather(self, pairs, keys, proposal):
        # TODO: wire LangChain agent + tools. Falls back to mock for now so the
        # loop runs end-to-end. The first feature's `required_evidence` keys
        # will get populated with deterministic stubs; agent's compute() will
        # treat them as numeric and produce a (weak but non-degenerate) signal.
        return self._mock_for_gather.gather(pairs, keys, proposal)

    def write_misses(self, composite_version, disagreements, feature_contributions):
        from . import prompts
        prompt = prompts.WRITE_MISSES.format(
            composite_version=composite_version,
            disagreements_aged_young="\n".join(
                f"  - {p}: score={s:+.3f}, target={t:+.3f}"
                for p, s, t in disagreements.get("aged_young", [])
            ) or "  (none)",
            disagreements_fibro_muscle="\n".join(
                f"  - {p}: score={s:+.3f}, target={t:+.3f}"
                for p, s, t in disagreements.get("fibro_muscle", [])
            ) or "  (none)",
            feature_contributions=feature_contributions or "(none)",
        )
        return self._call(prompt, json_mode=False)

    def decide_stop(self, ctx: StageContext) -> tuple[bool, str]:
        # Hard stops checked by orchestrator first; this is the LLM's read.
        from . import prompts
        prompt = prompts.DECIDE_STOP.format(
            stage_index=ctx.stage_index,
            fail_streak=ctx.fail_streak,
            rho_aged_young=ctx.rho.get("aged_young", 0.0),
            rho_fibro_muscle=ctx.rho.get("fibro_muscle", 0.0),
            max_stages=ctx.max_stages,
            stop_rho=ctx.stop_rho,
            max_fail_streak=3,
        )
        raw = self._call(prompt, json_mode=True)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return False, "decide_stop returned non-JSON; continuing"
        return bool(data.get("stop", False)), str(data.get("reason", ""))
