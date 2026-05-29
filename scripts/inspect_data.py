"""
Data inventory script for the EM-DAT train CSV.
Re-runnable. Outputs all findings needed before writing generate_emdat_stats.py.
Run from project root: python scripts/inspect_data.py
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

CSV_PATH = Path(__file__).parent.parent / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"

def separator(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def main():
    # ── Load ──────────────────────────────────────────────────────────────
    print(f"Reading: {CSV_PATH}")
    if not CSV_PATH.exists():
        print(f"ERROR: file not found at {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH, low_memory=False)

    # ── 1. Shape ──────────────────────────────────────────────────────────
    separator("1. SHAPE")
    print(f"Rows × Cols: {df.shape[0]:,} × {df.shape[1]}")

    # ── 2. Column names + dtypes ──────────────────────────────────────────
    separator("2. COLUMN NAMES & DTYPES")
    col_info = pd.DataFrame({
        "column": df.columns.tolist(),
        "dtype":  [str(df[c].dtype) for c in df.columns],
        "non_null": df.notna().sum().values,
        "missing_%": (df.isna().mean() * 100).round(1).values,
    })
    print(col_info.to_string(index=False))

    # ── 3. First 3 rows ───────────────────────────────────────────────────
    separator("3. FIRST 3 ROWS (all columns)")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 40)
    print(df.head(3).to_string())

    # ── 4. Categorical columns: unique / top-10 ───────────────────────────
    separator("4. CATEGORICAL COLUMNS")

    cat_cols = [
        "Disaster Type",
        "Disaster Subtype",
        "Disaster Group",
        "Country",
        "Region",
        "Continent",
        "Associated Dis",
        "Associated Dis2",
    ]

    for col in cat_cols:
        if col not in df.columns:
            print(f"\n  !! COLUMN NOT FOUND: '{col}'")
            # Try case-insensitive match
            matches = [c for c in df.columns if c.strip().lower() == col.strip().lower()]
            if matches:
                print(f"     Closest match(es): {matches}")
            continue

        n_unique = df[col].nunique()
        print(f"\n  [{col}]  dtype={df[col].dtype}  nunique={n_unique}  missing={df[col].isna().sum()}")
        if n_unique <= 30:
            vals = df[col].value_counts(dropna=False)
            print(vals.to_string())
        else:
            print("  (top 10 most common)")
            print(df[col].value_counts(dropna=False).head(10).to_string())

    # ── 5. Numeric columns: stats + missing% ─────────────────────────────
    separator("5. NUMERIC COLUMNS — stats + missing %")

    numeric_cols = [
        "Start Year",
        "Start Month",
        "Total Deaths",
        "No Injured",
        "Total Affected",
        "Total Damages ('000 US$)",
        "Insured Damages ('000 US$)",
        "Dis Mag Value",
    ]

    for col in numeric_cols:
        if col not in df.columns:
            print(f"\n  !! COLUMN NOT FOUND: '{col}'")
            # Try fuzzy match
            matches = [c for c in df.columns if col.lower().replace("'", "").replace(" ", "") in c.lower().replace("'", "").replace(" ", "")]
            if matches:
                print(f"     Closest match(es): {matches}")
            continue

        s = df[col].dropna()
        missing_pct = df[col].isna().mean() * 100
        print(f"\n  [{col}]")
        print(f"    count={len(s):,}  missing={missing_pct:.1f}%")
        if len(s) > 0:
            print(f"    mean={s.mean():.2f}  median={s.median():.2f}  std={s.std():.2f}")
            print(f"    min={s.min():.2f}  max={s.max():.2f}")
            print(f"    p25={s.quantile(0.25):.2f}  p75={s.quantile(0.75):.2f}  p99={s.quantile(0.99):.2f}")

    # ── 6. Disaster Group filter check ────────────────────────────────────
    separator("6. DISASTER GROUP — exact values (for 'Natural' filter)")
    if "Disaster Group" in df.columns:
        print(df["Disaster Group"].value_counts(dropna=False).to_string())
        natural_rows = df[df["Disaster Group"].str.strip() == "Natural"] if df["Disaster Group"].notna().any() else pd.DataFrame()
        print(f"\n  Rows matching strip()=='Natural': {len(natural_rows):,}")
    else:
        print("  !! 'Disaster Group' column not found")

    # ── 7. Disaster Type — exact unique values (for strip check) ─────────
    separator("7. DISASTER TYPE — all unique values with repr()")
    if "Disaster Type" in df.columns:
        for v in sorted(df["Disaster Type"].dropna().unique()):
            print(f"  {repr(v)}")
    else:
        print("  !! 'Disaster Type' column not found")

    # ── 8. Associated Dis columns (secondary disasters) ───────────────────
    separator("8. ASSOCIATED DISASTERS — columns used for secondary_disasters.json")
    assoc_cols = [c for c in df.columns if "associated" in c.lower() or "assoc" in c.lower()]
    print(f"  Found associated-disaster columns: {assoc_cols}")
    for col in assoc_cols:
        print(f"\n  [{col}]  non-null={df[col].notna().sum():,}  nunique={df[col].nunique()}")
        print(df[col].value_counts(dropna=False).head(15).to_string())

    # ── 9. Country → Region/Continent mapping sample ──────────────────────
    separator("9. COUNTRY -> REGION / CONTINENT mapping sample (first 20 unique countries)")
    region_col = "Region" if "Region" in df.columns else None
    continent_col = "Continent" if "Continent" in df.columns else None
    cols_to_show = ["Country"] + ([region_col] if region_col else []) + ([continent_col] if continent_col else [])
    if len(cols_to_show) > 1:
        sample = df[cols_to_show].drop_duplicates("Country").head(20)
        print(sample.to_string(index=False))
    else:
        print("  Only Country column found — no Region/Continent to map.")

    # ── 10. Dis Mag Value by Disaster Type (for magnitude feature) ────────
    separator("10. DIS MAG VALUE — non-null rows by Disaster Type")
    if "Dis Mag Value" in df.columns and "Disaster Type" in df.columns:
        mag_summary = (
            df[df["Dis Mag Value"].notna()]
            .groupby("Disaster Type")["Dis Mag Value"]
            .agg(count="count", median="median", p25=lambda x: x.quantile(0.25), p75=lambda x: x.quantile(0.75))
            .sort_values("count", ascending=False)
        )
        print(mag_summary.to_string())
    else:
        print("  Required columns missing.")

    separator("DONE — inspect_data.py complete")

if __name__ == "__main__":
    main()
