"""
Download the Kedlian/Lai 2024 human skeletal muscle aging cell atlas (.h5ad).

Source: https://www.muscleageingcellatlas.org/  → cellgeni.cog.sanger.ac.uk
Citation: Kedlian VR et al., Nature Aging 2024 (E-MTAB-13874)

Two files available:
  - PROCESSED (default): SKM_human_pp_cells2nuclei_2023-06-22.h5ad  (~2.02 GB, log-normalized + annotated)
  - RAW:                 SKM_human_raw_cells2nuclei_2023-06-22.h5ad (~4.03 GB, raw counts)

obs columns (verified): Age_bin {old, young}, Age_group, DonorID, SampleID, Sex,
annotation_level0/1/2 (cell types: MuSC, MF-I, MF-II, FB, etc.).

Usage:
    python download_muscle_atlas.py                    # processed
    python download_muscle_atlas.py --raw              # raw counts
    python download_muscle_atlas.py --output-dir /path/to/dir
"""
import argparse
import sys
from pathlib import Path

import httpx

PROCESSED_URL = "https://cellgeni.cog.sanger.ac.uk/muscleageingcellatlas/SKM_human_pp_cells2nuclei_2023-06-22.h5ad"
RAW_URL       = "https://cellgeni.cog.sanger.ac.uk/muscleageingcellatlas/raw/SKM_human_raw_cells2nuclei_2023-06-22.h5ad"

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "storage" / "atlases"


def download(url: str, dest: Path, chunk_size: int = 1024 * 1024) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        size_mb = dest.stat().st_size / 1e6
        print(f"[skip] {dest.name} already exists ({size_mb:.1f} MB). Delete to re-download.")
        return

    print(f"[download] {url}")
    print(f"[dest]     {dest}")

    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        total_mb = total / 1e6
        downloaded = 0

        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=chunk_size):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    sys.stdout.write(
                        f"\r  {downloaded/1e6:.0f} / {total_mb:.0f} MB  ({pct:.1f}%)"
                    )
                    sys.stdout.flush()
        print()

    final_mb = dest.stat().st_size / 1e6
    print(f"[done] {final_mb:.1f} MB written to {dest}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", action="store_true",
                    help="Download raw counts instead of processed atlas (4 GB vs 2 GB).")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).")
    args = ap.parse_args()

    url = RAW_URL if args.raw else PROCESSED_URL
    filename = url.rsplit("/", 1)[-1]
    dest = args.output_dir / filename

    try:
        download(url, dest)
    except httpx.HTTPError as exc:
        print(f"[error] download failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nNext steps:")
    print(f"  1. Upload to Superbio scGPT Mapping: superbio tool, action=submit, app_name=scgpt_mapping,")
    print(f"     local_file_path={dest}")
    print(f"  2. Or run scGPT GRN inference: app_name=scgpt_grn_inference")
    print(f"  3. Cached atlas embeddings will land in backend/storage/scgpt_cache/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
