import sys
import re
from pathlib import Path

import pandas as pd
import numpy as np


def parse_vizier_tsv(path: Path) -> pd.DataFrame:
    """
    Parse a VizieR ASU-TSV export (the 'asu.tsv' style file this project uses).

    VizieR TSV files have this shape:
      - a block of '#' comment/metadata lines (variable length, includes
        column descriptions we don't need at runtime)
      - a header line: column names, tab-separated
      - a units line: units for each column (often blank for id-like columns)
        this sits directly ABOVE the dashes line
      - a dashes line: '----------\t----------\t...' marking the true start
        of data (header is 2 lines above this, not 1)
      - data rows, tab-separated, values may be padded with leading spaces
      - VizieR sometimes appends a trailing blank line or a row count footer

    This parser finds the dashes line by pattern (a line made up of only
    '-', whitespace and tabs) and uses the line two rows above it as the
    header. It does not hardcode column names, so it works unmodified for
    table2, table3 and table4 even though their schemas differ.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    dash_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.fullmatch(r"[-\t ]+", stripped):
            dash_line_idx = i
            break

    if dash_line_idx is None:
        raise ValueError(
            f"Could not find the VizieR dashes separator line in {path}. "
            "This file may not be a standard VizieR ASU-TSV export - "
            "open it in a text editor and check its structure."
        )

    # layout is: header line, units line, dashes line, data...
    header_idx = dash_line_idx - 2
    data_start_idx = dash_line_idx + 1

    header_cols = [c.strip() for c in lines[header_idx].rstrip("\n").split("\t")]

    data_lines = lines[data_start_idx:]
    # drop trailing blank lines VizieR sometimes appends
    data_lines = [ln for ln in data_lines if ln.strip() != ""]

    rows = [ln.rstrip("\n").split("\t") for ln in data_lines]

    # guard against short/malformed trailing rows
    rows = [r for r in rows if len(r) == len(header_cols)]

    df = pd.DataFrame(rows, columns=header_cols)

    # strip whitespace from every cell, then attempt numeric conversion
    # column by column; columns that fail to convert (e.g. free-text
    # comment columns) are left as cleaned strings
    for col in df.columns:
        df[col] = df[col].str.strip()
        numeric = pd.to_numeric(df[col], errors="coerce")
        # only convert if the whole column is numeric (allow NaN for
        # legitimately blank/null cells, which VizieR marks as empty)
        non_blank = df[col] != ""
        if non_blank.sum() > 0 and numeric[non_blank].notna().all():
            df[col] = numeric

    return df


def summarize(name: str, df: pd.DataFrame, expected_rows=None):
    print(f"\n{'=' * 70}")
    print(f"{name}")
    print(f"{'=' * 70}")
    print(f"Rows: {len(df):,}")
    if expected_rows is not None:
        diff = len(df) - expected_rows
        flag = "OK" if diff == 0 else f"MISMATCH (expected {expected_rows:,}, diff {diff:+,})"
        print(f"Expected: {expected_rows:,}  -> {flag}")
    print(f"Columns ({len(df.columns)}): {list(df.columns)}")
    print(f"\nDtypes:\n{df.dtypes}")
    print(f"\nFirst 3 rows:")
    print(df.head(3).to_string())
    for id_col in ("TIC", "TIC1", "TIC2"):
        if id_col in df.columns:
            n_dupe_ids = df[id_col].duplicated().sum()
            print(f"\nDuplicate {id_col} values: {n_dupe_ids}")
            break


def build_stratified_sample(df: pd.DataFrame, n_total: int = 100, n_bins: int = 5,
                              mag_col: str = "Tmag", seed: int = 42) -> pd.DataFrame:
    """
    Sample n_total rows from df, spread evenly across n_bins brightness bins,
    so the F2 light-curve fetch test covers bright and faint targets rather
    than whatever happens to sort first in the file.
    """
    rng = np.random.default_rng(seed)
    df = df.dropna(subset=[mag_col]).copy()
    df["mag_bin"] = pd.qcut(df[mag_col], q=n_bins, labels=False, duplicates="drop")

    per_bin = n_total // n_bins
    remainder = n_total - per_bin * n_bins

    samples = []
    bins_present = sorted(df["mag_bin"].dropna().unique())
    for i, b in enumerate(bins_present):
        bin_df = df[df["mag_bin"] == b]
        take = per_bin + (1 if i < remainder else 0)
        take = min(take, len(bin_df))
        idx = rng.choice(bin_df.index, size=take, replace=False)
        samples.append(df.loc[idx])

    result = pd.concat(samples).drop(columns=["mag_bin"]).reset_index(drop=True)
    return result


def main():
    if len(sys.argv) != 2:
        print("Usage: py f1_ingest.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    raw_dir = project_root / "data" / "raw"
    processed_dir = project_root / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    downloads = Path.home() / "Downloads"

    sources = {
        "table2_unvetted": (downloads / "asu.tsv", 872720),
        "table3_new_ebs": (downloads / "asu (1).tsv", 7936),
        "table4_known_ebs": (downloads / "asu (2).tsv", 2065),
    }

    parsed = {}

    for key, (src_path, expected_rows) in sources.items():
        if not src_path.exists():
            print(f"\n[SKIP] {key}: source file not found at {src_path}")
            print("       If your file has a different name, edit the 'sources'")
            print("       dict at the top of main() in this script and re-run.")
            continue

        try:
            archive_path = raw_dir / f"{key}.tsv"
            archive_path.write_bytes(src_path.read_bytes())

            df = parse_vizier_tsv(archive_path)
            summarize(key, df, expected_rows=expected_rows)

            out_path = processed_dir / f"{key}.parquet"
            df.to_parquet(out_path, index=False)
            print(f"\nSaved: {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")

            parsed[key] = df
        except Exception as e:
            print(f"\n[ERROR] Failed to parse {key} from {src_path}: {e}")
            print("        Skipping this table; other tables will still be processed.")
            continue

    if "table2_unvetted" in parsed:
        sample = build_stratified_sample(parsed["table2_unvetted"], n_total=100, n_bins=5)
        sample_path = processed_dir / "sample_100.csv"
        sample.to_csv(sample_path, index=False, encoding="utf-8", lineterminator="\n")
        print(f"\n{'=' * 70}")
        print("STRATIFIED SAMPLE (100 targets across 5 Tmag bins)")
        print(f"{'=' * 70}")
        print(sample["Tmag"].describe())
        print(f"\nSaved: {sample_path}")

    print(f"\n{'=' * 70}")
    print("F1 INGESTION COMPLETE")
    print(f"{'=' * 70}")
    print(f"Processed tables: {list(parsed.keys())}")
    if len(parsed) < 3:
        missing = set(sources.keys()) - set(parsed.keys())
        print(f"Missing tables (see SKIP messages above): {missing}")
        print("Re-run this script after locating the missing file(s).")


if __name__ == "__main__":
    main()