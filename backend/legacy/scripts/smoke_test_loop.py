"""
Smoke test for all RL loop utilities — fast (~5 sec), no network, no agent.

Verifies:
  1. utils.phenotype_checkpoint scores H2F-like signatures correctly
  2. utils.chain_soundness aggregates step confidences correctly
  3. utils.superbio_submit dry_run produces a manifest
  4. scripts.buffer_review can read experience_buffer.jsonl
  5. scripts.candidate_dossier can render a record
  6. scripts.morning_report renders without error
  7. tools registry imports the expected tool count

Exit code 0 if all pass; 1 otherwise.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


PASSED, FAILED = 0, 0


def _check(name: str, predicate, *, info: str = "") -> bool:
    global PASSED, FAILED
    try:
        ok = bool(predicate())
    except Exception as exc:
        ok = False
        info = f"{info} — exception: {exc}"
        traceback.print_exc()
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({info})" if info else ""))
    if ok:
        PASSED += 1
    else:
        FAILED += 1
    return ok


# ── Test 1: phenotype_checkpoint ─────────────────────────────────────────────
def test_phenotype_checkpoint() -> None:
    print("\n[1] phenotype_checkpoint")
    from utils.phenotype_checkpoint import score_phenotype

    r = score_phenotype(
        predicted_up=["MYH7", "MYH2", "TNNT3", "MYOG", "MYOD1", "MEF2C", "ACTA2", "MYL9"],
        predicted_down=["EGR1", "IL32", "TXNIP", "JUN", "MYF5", "OTUD1"],
    )
    _check(
        "H2F-like signature scores REJUVENATING",
        lambda: r["verdict"] == "REJUVENATING",
        info=f"phenotype={r['phenotype_score']:+.4f}",
    )
    _check(
        "Empty input returns EMPTY verdict",
        lambda: score_phenotype([], [])["verdict"] == "EMPTY",
    )
    r2 = score_phenotype(
        predicted_up=["EGR1", "IL32", "TXNIP", "JUN", "OTUD1"],
        predicted_down=["MYH7", "MYH2", "TNNT3"],
    )
    _check(
        "Anti-rejuvenation signature scores ANTI-REJUVENATING",
        lambda: r2["verdict"] == "ANTI-REJUVENATING",
        info=f"phenotype={r2['phenotype_score']:+.4f}",
    )


# ── Test 2: chain_soundness ─────────────────────────────────────────────────
def test_chain_soundness() -> None:
    print("\n[2] chain_soundness")
    from utils.chain_soundness import chain_soundness, is_incoherent

    r = chain_soundness({"step_1": 0.85, "step_2": 0.9, "step_3a": 0.8,
                          "step_3b": 0.78, "step_3c": 0.75, "step_3d": 0.65, "step_4": 0.85})
    _check(
        "H2F-style chain ~0.79 (geom mean of {0.85,0.9,0.8,0.78,0.75,0.65,0.85})",
        lambda: 0.7 <= r["chain_soundness"] <= 0.85,
        info=f"got {r['chain_soundness']:.3f}",
    )
    _check(
        "joint probability < geom mean",
        lambda: r["joint_probability"] < r["chain_soundness"],
        info=f"joint={r['joint_probability']:.3f} vs cs={r['chain_soundness']:.3f}",
    )

    r2 = chain_soundness({k: 0.2 for k in
                          ["step_1", "step_2", "step_3a", "step_3b", "step_3c", "step_3d", "step_4"]})
    _check(
        "Low chain marked incoherent (0.2 < 0.30 gate)",
        lambda: is_incoherent(r2["chain_soundness"]),
        info=f"got {r2['chain_soundness']:.3f}",
    )


# ── Test 3: superbio_submit dry-run ─────────────────────────────────────────
def test_superbio_submit() -> None:
    print("\n[3] superbio_submit dry-run")
    from utils.superbio_submit import submit_binder_design

    r = submit_binder_design(
        candidate_id="_smoke_test",
        receptor_A="ERBB2", receptor_B="FGFR1",
        dry_run=True,
    )
    _check(
        "dry_run returns manifest path",
        lambda: r["manifest_path"] and not r["submitted"] and r["dry_run"],
    )
    _check(
        "manifest file written",
        lambda: Path(r["manifest_path"]).exists(),
    )


# ── Test 4: buffer_review reads buffer ─────────────────────────────────────
def test_buffer_review() -> None:
    print("\n[4] buffer_review")
    from scripts.buffer_review import load_buffer, summarize, tier_distribution
    rows = load_buffer()
    _check(
        "buffer non-empty",
        lambda: len(rows) > 0,
        info=f"{len(rows)} records",
    )
    if rows:
        s = summarize(rows[-1])
        _check(
            "summarize returns dict with expected keys",
            lambda: all(k in s for k in
                        ("candidate_id", "receptor_A", "receptor_B",
                         "phenotype_score", "tier", "reward")),
        )
    counts = tier_distribution([summarize(r) for r in rows])
    _check(
        "tier_distribution returns Counter-like dict",
        lambda: isinstance(counts, dict) and len(counts) > 0,
        info=f"tiers={list(counts.keys())}",
    )


# ── Test 5: candidate_dossier renders ──────────────────────────────────────
def test_candidate_dossier() -> None:
    print("\n[5] candidate_dossier")
    from scripts.candidate_dossier import load_record, load_prediction, render

    # Try the H2F_iter0 record
    rec = load_record("H2F_iter0")
    pred = load_prediction("H2F_iter0")
    rendered = render(rec, pred)
    _check(
        "H2F_iter0 record loads",
        lambda: rec is not None,
    )
    _check(
        "render produces non-empty output",
        lambda: rendered and len(rendered) > 100,
        info=f"{len(rendered)} chars",
    )
    _check(
        "render mentions ERBB2+FGFR1",
        lambda: "ERBB2" in rendered and "FGFR1" in rendered,
    )


# ── Test 6: morning_report renders ─────────────────────────────────────────
def test_morning_report() -> None:
    print("\n[6] morning_report")
    from scripts.morning_report import render_report
    md = render_report(top_k=3)
    _check(
        "morning report renders",
        lambda: md and "Morning Report" in md and "Headline" in md,
        info=f"{len(md)} chars",
    )


# ── Test 7: tools registry ──────────────────────────────────────────────────
def test_tools_registry() -> None:
    print("\n[7] tools registry")
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    except Exception:
        pass
    from tools import get_all_tools
    tools = get_all_tools(BACKEND)
    names = sorted(getattr(t, "wrapped_tool", t).name for t in tools)
    _check(
        "≥25 tools registered",
        lambda: len(tools) >= 25,
        info=f"{len(tools)} tools",
    )
    expected = {
        "phenotype_checkpoint", "scgpt_phenotype", "scgpt_programs",
        "superbio", "alphafold3_api", "clue_api", "cellxgene_expression",
    }
    missing = expected - set(names)
    _check(
        "all expected new tools present",
        lambda: not missing,
        info=f"missing={missing}" if missing else f"all 7 critical tools present",
    )


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 70)
    print(" RL Loop Smoke Test Suite")
    print("=" * 70)
    test_phenotype_checkpoint()
    test_chain_soundness()
    test_superbio_submit()
    test_buffer_review()
    test_candidate_dossier()
    test_morning_report()
    test_tools_registry()
    print("\n" + "=" * 70)
    print(f" RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 70)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
