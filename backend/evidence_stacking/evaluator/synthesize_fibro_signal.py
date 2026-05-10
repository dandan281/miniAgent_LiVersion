"""Build the fibro_muscle target signal — per-receptor delta(muscle - fibroblast).

Two passes:

1. **Live mode (preferred)** — query the local muscle atlas h5ad via
   ``backend.tools.local_atlas_tool`` to compute per-receptor mean expression
   in muscle cell types (MuSC, Myofiber*) and in FAP / fibroblast cell types,
   restricted to young donors to avoid age confounding. delta = muscle - FAP.

2. **Proxy mode (default fallback)** — use a curated muscle-marker / fibroblast-
   marker gene list. Receptors flagged as muscle markers score +1, fibroblast
   markers score -1, others 0. Used when the h5ad is unavailable (CI, smoke
   tests). Mode is logged in the TSV header.

Output: ``backend/knowledge/labels/v2_atlas_reward_fibro_muscle.tsv`` with
columns ``pair_id\\tscore``. Pair score = mean(receptor_A_delta, receptor_B_delta).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..pair import ReceptorPair
from ..receptor_universe import load as load_universe


# Curated lists for proxy mode. Muscle markers favor myogenic / muscle-stem
# fate; fibroblast markers favor fibrotic / collagen-producing fate.
_MUSCLE_MARKERS = {
    "ITGA7",   # laminin receptor; muscle satellite
    "CD36",    # muscle metabolism
    "INSR",    # muscle anabolic / hypertrophy
    "IGF1R",   # muscle anabolic
    "ERBB2",   # H2F muscle reprogramming partner
    "FGFR1",   # H2F + C6-DPC muscle reprogramming partner
    "FGFR2",   # myogenesis
    "FGFR4",   # skeletal muscle FGF21
    "MET",     # satellite cell activation by HGF
    "GHR",     # growth hormone, muscle hypertrophy
    "NOTCH1",  # satellite cell quiescence
    "NOTCH2",  # muscle development
    "BMPR1A",  # BMP myogenesis
    "ACVR2B",  # myostatin axis (muscle hypertrophy when blocked)
    "ACVR2A",  # myostatin axis
    "BMPR2",   # central reprogramming hit (per attached methods doc)
    "ACVRL1",  # ALK1; central reprogramming hit
}

_FIBROBLAST_MARKERS = {
    "PDGFRA",  # canonical FAP / fibroblast marker
    "PDGFRB",  # pericyte / fibroblast
    "DDR1",    # collagen receptor; fibrosis
    "DDR2",    # ECM remodeling fibroblast
    "TGFBR1",  # canonical pro-fibrotic
    "TGFBR2",  # canonical pro-fibrotic (context-dependent)
    "TGFBR3",  # TGF-β co-receptor
    "ITGAV",   # latent TGF-β activation
    "PLAUR",   # ECM remodeling
}


def _proxy_per_receptor() -> dict[str, float]:
    universe = load_universe()
    out: dict[str, float] = {}
    for r in universe.receptors:
        if r.symbol in _MUSCLE_MARKERS:
            out[r.symbol] = +1.0
        elif r.symbol in _FIBROBLAST_MARKERS:
            out[r.symbol] = -1.0
        else:
            out[r.symbol] = 0.0
    return out


def _live_per_receptor() -> dict[str, float] | None:
    """Best-effort live atlas query. Returns None if atlas unreachable."""
    try:
        from tools.local_atlas_tool import _load_atlas, _per_group_expression  # type: ignore
        adata = _load_atlas()
    except Exception:
        return None

    universe = load_universe()
    out: dict[str, float] = {}
    muscle_keys = {"MuSC", "Myofiber", "Myofiber_TypeI", "Myofiber_TypeII"}
    fap_keys = {"FAP", "Fibroblast"}

    for r in universe.receptors:
        try:
            res = _per_group_expression(adata, r.symbol, cell_types=None, age_bins=["young"])
        except Exception:
            out[r.symbol] = 0.0
            continue
        if res.get("missing_gene"):
            out[r.symbol] = 0.0
            continue
        per_ct = res.get("per_cell_type", {})
        muscle_vals = []
        fap_vals = []
        for ct, blocks in per_ct.items():
            young = blocks.get("young") or {}
            mean_e = young.get("mean_expression")
            if mean_e is None:
                continue
            if any(k in ct for k in muscle_keys):
                muscle_vals.append(mean_e)
            if any(k in ct for k in fap_keys):
                fap_vals.append(mean_e)
        m = (sum(muscle_vals) / len(muscle_vals)) if muscle_vals else 0.0
        f = (sum(fap_vals) / len(fap_vals)) if fap_vals else 0.0
        out[r.symbol] = m - f
    return out


def build(
    out_path: Path | None = None,
    *,
    mode: str = "auto",
) -> Path:
    out_path = out_path or (
        Path(__file__).resolve().parent.parent.parent
        / "knowledge"
        / "labels"
        / "v2_atlas_reward_fibro_muscle.tsv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "live":
        per = _live_per_receptor()
        if per is None:
            raise RuntimeError("live atlas unreachable; rerun with mode=proxy or mode=auto")
        chosen = "live"
    elif mode == "proxy":
        per = _proxy_per_receptor()
        chosen = "proxy"
    else:  # auto
        per = _live_per_receptor()
        if per is None:
            per = _proxy_per_receptor()
            chosen = "proxy"
        else:
            chosen = "live"

    universe = load_universe()
    pairs = list(universe.pairs())

    lines = [f"# fibro_muscle target signal | mode={chosen} | n_pairs={len(pairs)}"]
    lines.append("pair_id\tscore")
    for p in pairs:
        score = (per.get(p.a, 0.0) + per.get(p.b, 0.0)) / 2.0
        lines.append(f"{p.pair_id}\t{score:.4f}")
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["auto", "live", "proxy"], default="auto")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = build(out_path=args.out, mode=args.mode)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
