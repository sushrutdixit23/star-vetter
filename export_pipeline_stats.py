import sys
import json
from pathlib import Path

import pandas as pd
import numpy as np


def read_csv_safe(path):
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"WARNING: could not read {path}: {e}")
        return None


def read_parquet_rowcount_safe(path):
    """Row count of the full unvetted catalog, without loading its data -
    this is the fixed denominator for the "how far through the catalog are
    we" progress figure. Reads only the parquet file's own metadata (a
    committed ~20MB file), so this stays cheap even though the file itself
    is never loaded into memory here."""
    if not path.exists():
        return None
    try:
        import pyarrow.parquet as pq
        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception as e:
        print(f"WARNING: could not read row count from {path}: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: py export_pipeline_stats.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"
    out_path = project_root / "site" / "public" / "data" / "pipeline_stats.json"

    # This funnel reads the pipeline's own on-disk CSVs directly - the same
    # files the orchestrator itself reads and writes - so every number on
    # the About page is the real cumulative total to date, not a
    # description of what the pipeline is supposed to do.
    #
    # Stage 1/2: f2c_manifest.csv accumulates one row per TIC ever attempted,
    # across every batch the orchestrator has run. status == "OK" means a
    # usable light curve was obtained.
    #
    # Stage 3/4: f4f_novelty_results.csv only contains TICs that passed the
    # F3i statistical vetting gates (the pipeline only forwards PASS
    # candidates to the novelty-checking stage), so its row count is the
    # real count of light curves that passed vetting. verdict == "NOVEL"
    # is the subset with no match in any of the 6 cross-matched catalogs.
    #
    # Stage 5/6: diag_pixel_results_v2.csv holds one row per NOVEL candidate
    # that survived the contamination/blend check and was pixel-checked;
    # verdict == "ON_TARGET" is the confirmed count.
    manifest = read_csv_safe(proc / "f2c_manifest.csv")
    novelty = read_csv_safe(proc / "f4f_novelty_results.csv")
    pix = read_csv_safe(proc / "diag_pixel_results_v2.csv")

    funnel = []
    sampled_to_date = 0

    if manifest is not None and "status" in manifest.columns:
        sampled_to_date = int(len(manifest))
        fetched_ok = int((manifest["status"] == "OK").sum())
        funnel.append({"label": "Targets sampled and fetch attempted", "count": sampled_to_date})
        funnel.append({"label": "Usable light curve obtained", "count": fetched_ok})
    else:
        print("WARNING: f2c_manifest.csv missing or malformed - skipping sample/fetch funnel steps.")

    # How far through the whole unvetted catalog the pipeline has gotten -
    # the fixed denominator is the full table2_unvetted.parquet row count
    # (a committed, static reference table: not something the CI checkout
    # regenerates or trims, so this stays the real remaining-work figure
    # even though data/logs/ and data/lightcurves/ do not persist between
    # runs). Left out of the JSON entirely if either number isn't available,
    # rather than shipping a zero or a guess.
    total_catalog = read_parquet_rowcount_safe(proc / "table2_unvetted.parquet")
    catalog_progress = None
    if total_catalog:
        catalog_progress = {
            "total_catalog": total_catalog,
            "sampled_to_date": sampled_to_date,
            "fraction": sampled_to_date / total_catalog,
        }
        print(f"Catalog progress: {sampled_to_date:,} / {total_catalog:,} "
              f"({100 * sampled_to_date / total_catalog:.3f}%) targets screened so far")
    else:
        print("WARNING: could not read table2_unvetted.parquet - catalog progress left blank.")

    if novelty is not None and "verdict" in novelty.columns:
        vetted = int(len(novelty))
        novel = int((novelty["verdict"] == "NOVEL").sum())
        funnel.append({"label": "Passed statistical vetting gates", "count": vetted})
        funnel.append({"label": "Flagged novel (no catalog match)", "count": novel})
    else:
        print("WARNING: f4f_novelty_results.csv missing or malformed - skipping vetting/novelty funnel steps.")

    if pix is not None and "role" in pix.columns and "verdict" in pix.columns:
        candidates = pix[pix["role"] == "candidate"]
        pixel_checked = int(len(candidates))
        confirmed = int((candidates["verdict"] == "ON_TARGET").sum())
        funnel.append({"label": "Survived contamination check, pixel-checked", "count": pixel_checked})
        funnel.append({"label": "Confirmed on-target", "count": confirmed})
    else:
        print("WARNING: diag_pixel_results_v2.csv missing or malformed - skipping pixel-check funnel steps.")

    if not funnel:
        print("ERROR: none of the expected pipeline CSVs were found under "
              f"{proc} - nothing to export. Run this after the orchestrator "
              "has completed at least one stage.")
        sys.exit(1)

    stats = {
        "funnel": funnel,
        "catalog_progress": catalog_progress,
        "catalogs": [
            "VSX",
            "ASAS-SN",
            "Gaia eclipsing-binary table",
            "Gaia variable classification",
            "TESS EB catalog (Prsa+2022)",
            "ExoFOP TOI list",
        ],
        "vetting_gates": [
            {
                "name": "Eclipse count",
                "text": "At least the minimum number of eclipses required to trust a period, so a single noisy dip can never pass on its own.",
            },
            {
                "name": "Odd/even depth consistency",
                "text": "Alternating eclipses must be statistically consistent in depth. A significant odd/even split is often the signature of an undetected period alias rather than two different eclipse depths.",
            },
            {
                "name": "Robust detection significance",
                "text": "The in-eclipse dip must clear a signal-to-noise threshold computed with an outlier-robust noise estimate, not a plain standard deviation that outliers could inflate.",
            },
            {
                "name": "Secondary eclipse search",
                "text": "The phase-folded curve is searched for a secondary eclipse independent of the primary detection, informing the tier and caveats even when none is required to pass.",
            },
            {
                "name": "BLS signal-to-noise",
                "text": "The Box Least Squares periodogram signal-to-noise ratio must clear a minimum threshold for the detected period to be trusted.",
            },
        ],
        "pixel_gates": [
            {
                "name": "In-eclipse light curve dip",
                "text": "The dip must independently reappear at the same phase in this sector's own light curve, at significance.",
            },
            {
                "name": "Difference-image peak SNR",
                "text": "The out-of-eclipse minus in-eclipse pixel difference image must show a significant, spatially compact source, not scattered noise.",
            },
            {
                "name": "Epoch-shift consistency",
                "text": "The eclipse timing recovered independently at the pixel level must line up with the light-curve ephemeris, ruling out an unrelated nearby variable aligning by chance.",
            },
            {
                "name": "Source compactness",
                "text": "The difference-image source must be consistent with a single point spread function, not a diffuse or multi-peaked pattern that would suggest blended light.",
            },
            {
                "name": "Centroid offset",
                "text": "The photometric centroid shift between in- and out-of-eclipse images must stay within the target's own pixel, or the signal is charged to a neighbour instead.",
            },
            {
                "name": "Nearest-neighbour contamination",
                "text": "Catalog neighbours within the aperture are checked by brightness and distance, so a bright nearby star cannot masquerade as the target dimming.",
            },
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(stats, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {out_path}")
    for step in funnel:
        print(f"  {step['label']}: {step['count']}")


if __name__ == "__main__":
    main()