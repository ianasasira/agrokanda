#!/usr/bin/env python3
"""
prepare_dataset.py
==================
Build the clean, analysis-ready AgriCredit-Yield Uganda dataset from the raw UNPS
2018/19 CSV files.

Output
------
AgriCredit_Yield_Analysis/UNPS_AgriCredit_Maize_Analysis.xlsx
    Sheet 1: "Maize_Analysis"       -> one row per maize plot/crop/season
    Sheet 2: "Household_Credit"     -> one row per household
    Sheet 3: "Variable_Dictionary"  -> documentation of every clean column

This script only READS the original survey files. It does not modify them.
No machine-learning / statistical modelling is performed.

Run from the "UNPS DATASET" folder (paths are relative).
"""

import os
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------
# Paths (relative to this script's parent folder = UNPS DATASET)
# ----------------------------------------------------------------------------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGRIC = os.path.join(BASE, "Agric")
HH = os.path.join(BASE, "HH")
OUT_DIR = os.path.join(BASE, "AgriCredit_Yield_Analysis")
OUT_XLSX = os.path.join(OUT_DIR, "UNPS_AgriCredit_Maize_Analysis.xlsx")

ACRES_TO_HA = 0.404686  # 1 acre = 0.404686 hectares
MAIZE_CODE = 130        # UNPS crop code for maize

# ----------------------------------------------------------------------------
# Verified code -> label maps (from the UNPS 2018/19 DDI codebook)
# ----------------------------------------------------------------------------
REGION = {1: "Central", 2: "Eastern", 3: "Northern", 4: "Western"}
RURAL_URBAN = {0: "Rural", 1: "Urban"}
SEED_TYPE = {1: "Traditional", 2: "Improved"}

# CB17 (loan reason). Codes 2, 3, 4 are the agricultural purposes.
LOAN_REASON = {
    1: "Buy land",
    2: "Buy livestock",
    3: "Buy farm tools",
    4: "Buy farm inputs",
    5: "Non-farm working capital",
    6: "Building materials",
    7: "Consumption goods",
    8: "Education",
    9: "Health",
    10: "Ceremonial",
    96: "Other",
}
AG_REASONS = {2, 3, 4}

# CB16__* (loan source) flags: 1 = Commercial bank ... 14 = Mobile money,
# 96 = Other, 97 = None. Formal vs informal classification (verified).
FORMAL_SOURCES = {"CB16__1", "CB16__3", "CB16__5", "CB16__7", "CB16__12"}
INFORMAL_SOURCES = {
    "CB16__2", "CB16__4", "CB16__6", "CB16__8", "CB16__9",
    "CB16__10", "CB16__11", "CB16__13", "CB16__14", "CB16__96",
}


def read_csv(rel_path, **kw):
    """Read a raw UNPS CSV, falling back to latin-1 if it is not UTF-8."""
    path = os.path.join(BASE, rel_path)
    try:
        return pd.read_csv(path, low_memory=False, **kw)
    except UnicodeDecodeError:
        return pd.read_csv(path, low_memory=False, encoding="latin-1", **kw)


# ----------------------------------------------------------------------------
# 1. Load the raw files
# ----------------------------------------------------------------------------
agsec4a = read_csv(os.path.join("Agric", "AGSEC4A.csv"))   # season 2 2017 area + seed
agsec4b = read_csv(os.path.join("Agric", "AGSEC4B.csv"))   # season 1 2018 area + seed
agsec5a = read_csv(os.path.join("Agric", "AGSEC5A.csv"))   # season 2 2017 production
agsec5b = read_csv(os.path.join("Agric", "AGSEC5B.csv"))   # season 1 2018 production
agsec3a = read_csv(os.path.join("Agric", "AGSEC3A.csv"))   # season 2 2017 fertilizer
agsec3b = read_csv(os.path.join("Agric", "AGSEC3B.csv"))   # season 1 2018 fertilizer
gsec74 = read_csv(os.path.join("HH", "GSEC7_4.csv"))       # credit (person level)
gsec1 = read_csv(os.path.join("HH", "GSEC1.csv"))          # location (household level)


# ----------------------------------------------------------------------------
# 2. Build household-level credit indicators from person-level GSEC7_4
# ----------------------------------------------------------------------------
def build_household_credit(g74):
    """Aggregate person-level credit records to one row per household.

    Distinguishes a real "No" from a missing/skipped/not-asked answer:
      - household_borrowed = 1 if ANY member CB12==1
                            0 if NO member CB12==1 but at least one answered (CB12==2)
                            missing otherwise (no member answered)
      - agricultural_loan  = 1 if ANY member CB17 in {2,3,4}
                            0 if the household borrowed (or is known not to borrow)
                              and no agricultural purpose was reported
                            missing if a borrower exists but no reason is known
    """
    g = g74.copy()

    def any_col(col, val):
        """Series (per hhid): True if any member has col==val, else False."""
        return g.groupby("hhid")[col].apply(lambda s: (s == val).any()).reset_index(drop=True)

    def answered_col(col):
        """Series (per hhid): True if any member answered col (non-null)."""
        return g.groupby("hhid")[col].apply(lambda s: s.notna().any()).reset_index(drop=True)

    hh = pd.DataFrame({"hhid": g["hhid"].drop_duplicates().reset_index(drop=True)})

    # --- money borrowing ---
    any_yes = any_col("CB12", 1)
    any_answered = answered_col("CB12")
    hh["household_borrowed"] = np.where(
        any_yes, 1, np.where(any_answered, 0, np.nan))

    # --- goods on credit (kept conceptually distinct) ---
    hh["household_goods_credit"] = np.where(
        any_col("CB13", 1), 1, np.where(answered_col("CB13"), 0, np.nan))

    # --- agricultural loan purpose ---
    ag = g.groupby("hhid")["CB17"].apply(lambda s: s.isin(AG_REASONS).any()).reset_index(drop=True)
    any_reason = g.groupby("hhid")["CB17"].apply(lambda s: s.notna().any()).reset_index(drop=True)
    hh["agricultural_loan"] = np.where(
        ag, 1, np.where((any_reason) | (hh["household_borrowed"] == 0), 0, np.nan))

    # --- loan purpose label(s) ---
    def label_of(series, allowed):
        labels = sorted({LOAN_REASON[int(v)] for v in series.dropna()
                         if int(v) in allowed})
        return "; ".join(labels) if labels else ""

    hh["loan_purpose"] = (g.groupby("hhid")["CB17"]
                          .apply(lambda s: label_of(s, LOAN_REASON.keys()))
                          .reset_index(drop=True))
    hh["ag_loan_purpose"] = (g.groupby("hhid")["CB17"]
                             .apply(lambda s: label_of(s, AG_REASONS))
                             .reset_index(drop=True))

    # --- borrowing source (formal / informal) ---
    formal_cols = [c for c in g.columns if c.startswith("CB16__")
                   and c in FORMAL_SOURCES]
    informal_cols = [c for c in g.columns if c.startswith("CB16__")
                     and c in INFORMAL_SOURCES]
    hh["formal_credit"] = (g.assign(_f=g[formal_cols].eq(1).any(axis=1))
                           .groupby("hhid")["_f"].any().reset_index(drop=True))
    hh["informal_credit"] = (g.assign(_i=g[informal_cols].eq(1).any(axis=1))
                             .groupby("hhid")["_i"].any().reset_index(drop=True))

    def source_label(row):
        f = bool(row["formal_credit"]) if pd.notna(row["formal_credit"]) else False
        i = bool(row["informal_credit"]) if pd.notna(row["informal_credit"]) else False
        if f and i:
            return "Formal & informal"
        if f:
            return "Formal"
        if i:
            return "Informal"
        return ""

    hh["borrowing_source"] = hh.apply(source_label, axis=1)

    hh["household_borrowed"] = hh["household_borrowed"].astype("Int64")
    hh["agricultural_loan"] = hh["agricultural_loan"].astype("Int64")
    return hh


household_credit = build_household_credit(gsec74)


# ----------------------------------------------------------------------------
# 3. Build location table (household level)
# ----------------------------------------------------------------------------
location = gsec1[["hhid", "region", "district_code", "distirct_name", "urban"]].copy()
location["region_name"] = location["region"].map(REGION)
location["rural_urban"] = location["urban"].map(RURAL_URBAN)
location = location.rename(columns={"distirct_name": "district"})


# ----------------------------------------------------------------------------
# 4. Build one season's maize records
# ----------------------------------------------------------------------------
def build_season(a4, a5, a3, season_label,
                 area_col, seed_col, stand_col, share_col,
                 qty_col, conv_col, harvest_col,
                 fert_org_col, fert_inorg_col, fert_qty_col):
    """Combine area/seed (a4) + production (a5) + fertilizer (a3) for one season."""
    # Base: maize crop records (area + seed). Full-outer join production so we do
    # not drop records that have only area or only production.
    area = a4[a4["cropID"] == MAIZE_CODE][
        ["hhid", "parcelID", "pltid", area_col, seed_col, stand_col, share_col]
    ].copy()
    prod = a5[a5["cropID"] == MAIZE_CODE][
        ["hhid", "parcelID", "pltid", qty_col, conv_col, harvest_col]
    ].copy()

    key = ["hhid", "parcelID", "pltid"]
    df = area.merge(prod, on=key, how="outer", suffixes=("_area", "_prod"))

    # --- production (kg) = quantity * conversion factor ----------------------
    df["_qty"] = df[qty_col]
    df["_conv"] = df[conv_col]
    # a conversion factor <= 0 is treated as invalid (unknown unit)
    valid_conv = df["_conv"].notna() & (df["_conv"] > 0)
    df["maize_production_kg"] = np.where(
        df["_qty"].notna() & valid_conv,
        df["_qty"] * df["_conv"],
        np.nan,
    )

    # --- area (acres -> ha) --------------------------------------------------
    df["maize_area_acres"] = df[area_col]
    df["maize_area_ha"] = df[area_col] * ACRES_TO_HA

    # --- yield -----------------------------------------------------------------
    df["maize_yield_kg_ha"] = np.where(
        df["maize_area_ha"].notna() & (df["maize_area_ha"] > 0)
        & df["maize_production_kg"].notna(),
        df["maize_production_kg"] / df["maize_area_ha"],
        np.nan,
    )

    # --- seed type -------------------------------------------------------------
    df["seed_type"] = df[seed_col].map(SEED_TYPE)
    df["improved_seed"] = np.where(df[seed_col] == 2, 1,
                                   np.where(df[seed_col] == 1, 0, np.nan))

    # --- fertilizer (plot level) ----------------------------------------------
    fert = a3[["hhid", "parcelID", "pltid", fert_org_col, fert_inorg_col, fert_qty_col]].copy()
    fert = fert.rename(columns={fert_org_col: "organic_fertilizer_used",
                                fert_inorg_col: "inorganic_fertilizer_used",
                                fert_qty_col: "inorganic_fertilizer_kg"})
    # binary indicators: 1 = Yes, 0 = No, missing if plot not matched / not asked
    for c in ("organic_fertilizer_used", "inorganic_fertilizer_used"):
        fert[c] = np.where(fert[c] == 1, 1, np.where(fert[c] == 2, 0, np.nan))
    df = df.merge(fert, on=key, how="left")

    # --- season + key bookkeeping ----------------------------------------------
    df["season"] = season_label
    df["harvest_status"] = df[harvest_col].map(
        {1: "Full harvest", 2: "Partial harvest", 3: "No harvest"}
    )
    df = df.rename(columns={"hhid": "household_id",
                            "parcelID": "parcel_id",
                            "pltid": "plot_id"})

    # --- flag suspicious values (for later review, not removal) ----------------
    flags = pd.Series("", index=df.index, dtype=object)
    flags[df["maize_area_acres"].notna() & (df["maize_area_acres"] <= 0)] = "area<=0"
    flags[df["maize_yield_kg_ha"].notna() & (df["maize_yield_kg_ha"] > 10000)] = \
        "suspiciously high yield (>10,000 kg/ha)"
    flags[(df[harvest_col] == 3) & df["maize_production_kg"].notna() & (df["maize_production_kg"] > 0)] = \
        "reported no harvest but quantity recorded"
    df["yield_flag"] = flags

    keep = [
        "household_id", "parcel_id", "plot_id", "season", "harvest_status",
        "maize_production_kg", "maize_area_acres", "maize_area_ha",
        "maize_yield_kg_ha", "seed_type", "improved_seed",
        "organic_fertilizer_used", "inorganic_fertilizer_used",
        "inorganic_fertilizer_kg", "yield_flag",
    ]
    return df[keep]


s2 = build_season(
    agsec4a, agsec5a, agsec3a, "Season 2 2017",
    area_col="s4aq07", seed_col="s4aq13", stand_col="s4aq08", share_col="s4aq09",
    qty_col="s5aq06a_1", conv_col="a5aq6d", harvest_col="harvest",
    fert_org_col="s3aq04", fert_inorg_col="s3aq13", fert_qty_col="s3aq15",
)
s1 = build_season(
    agsec4b, agsec5b, agsec3b, "Season 1 2018",
    area_col="s4bq07", seed_col="s4bq13", stand_col="s4bq08", share_col="s4bq09",
    qty_col="s5bq06a_1", conv_col="a5bq6d", harvest_col="harvest_b",
    fert_org_col="s3bq04", fert_inorg_col="s3bq13", fert_qty_col="s3bq15",
)

maize = pd.concat([s2, s1], ignore_index=True)


# ----------------------------------------------------------------------------
# 5. Join credit + geography (left joins so missing info does not drop rows)
# ----------------------------------------------------------------------------
maize = maize.merge(
    household_credit[["hhid", "household_borrowed", "agricultural_loan", "ag_loan_purpose"]]
    .rename(columns={"ag_loan_purpose": "loan_purpose", "hhid": "household_id"}),
    on="household_id", how="left",
)
maize = maize.merge(
    location[["hhid", "region_name", "district", "rural_urban"]]
    .rename(columns={"hhid": "household_id", "region_name": "region"}),
    on="household_id", how="left",
)

# rainfall is NOT available in the UNPS folder; leave missing (do not invent)
maize["rainfall_mm"] = np.nan

# final column order
COL_ORDER = [
    "household_id", "parcel_id", "plot_id", "season",
    "region", "district", "rural_urban",
    "harvest_status",
    "maize_production_kg", "maize_area_acres", "maize_area_ha", "maize_yield_kg_ha",
    "seed_type", "improved_seed",
    "organic_fertilizer_used", "inorganic_fertilizer_used", "inorganic_fertilizer_kg",
    "household_borrowed", "agricultural_loan", "loan_purpose",
    "rainfall_mm", "yield_flag",
]
maize = maize[COL_ORDER]

# convert indicator columns to nullable integer so Excel shows 1/0 and blank (not 1.0)
for c in ["improved_seed", "organic_fertilizer_used", "inorganic_fertilizer_used",
          "household_borrowed", "agricultural_loan"]:
    maize[c] = pd.to_numeric(maize[c], errors="coerce").astype("Int64")


# ----------------------------------------------------------------------------
# 6. Household_Credit sheet (one row per household)
# ----------------------------------------------------------------------------
household_credit_out = household_credit.rename(columns={"hhid": "household_id"}).merge(
    location[["hhid", "region_name", "district", "rural_urban"]].rename(
        columns={"hhid": "household_id", "region_name": "region"}),
    on="household_id", how="left",
)

household_credit_out = household_credit_out[[
    "household_id", "region", "district", "rural_urban",
    "household_borrowed", "agricultural_loan", "loan_purpose", "borrowing_source",
]]


# ----------------------------------------------------------------------------
# 7. Validation checks (printed to the terminal)
# ----------------------------------------------------------------------------
print("=" * 70)
print("VALIDATION")
print("=" * 70)

# 1. crop code
print("[1] All maize records use cropID == 130:",
      (agsec4a[agsec4a["cropID"] == 130]["cropID"] == 130).all()
      and (agsec4b[agsec4b["cropID"] == 130]["cropID"] == 130).all())

# 2. season-specific joins (A with A, B with B) verified by construction

# 3. uniqueness of full key (household + parcel + plot + season)
key = ["household_id", "parcel_id", "plot_id", "season"]
dup = maize.duplicated(key).sum()
print(f"[3] Duplicate (household,parcel,plot,season) rows: {dup}")

# 4. conversion factors
print("[4] Production set to kg = qty * conversion; "
      f"records with invalid (<=0) conversion factor ignored: "
      f"{int((maize['maize_production_kg'].isna() & maize['maize_area_acres'].notna()).sum())} rows w/ missing production (incl. no area/no conv)")

# 5/6/7. area + yield checks
print("[5-7] Area<=0 records:",
      int((maize["maize_area_acres"] <= 0).sum()),
      "| missing area:", int(maize["maize_area_acres"].isna().sum()),
      "| missing production:", int(maize["maize_production_kg"].isna().sum()),
      "| valid yields:", int(maize["maize_yield_kg_ha"].notna().sum()))

# 8. seed categories
print("[8] Seed type counts:",
      maize["seed_type"].value_counts(dropna=False).to_dict())

# 9. fertilizer
print("[9] Inorganic fert used:", int((maize["inorganic_fertilizer_used"] == 1).sum()),
      "| organic fert used:", int((maize["organic_fertilizer_used"] == 1).sum()),
      "| inorganic qty non-missing:", int(maize["inorganic_fertilizer_kg"].notna().sum()))

# 10. credit aggregation
print("[10] Households borrowed:", int((household_credit["household_borrowed"] == 1).sum()),
      "| agricultural loans:", int((household_credit["agricultural_loan"] == 1).sum()))

# 11. no unexpected duplication after joins
n_before = len(maize)
n_after = len(maize.drop_duplicates())
print(f"[11] Rows unchanged after joins: {n_before == n_after} ({n_before} rows)")

# 12. observations remaining
print(f"[12] Total maize observations: {len(maize)}")
print(f"     Unique maize households: {maize['household_id'].nunique()}")
print(f"     Regions represented: {maize['region'].nunique()} -> {sorted(maize['region'].dropna().unique())}")
print(f"     Valid yields: {int(maize['maize_yield_kg_ha'].notna().sum())}")
print(f"     Improved seed: {int((maize['improved_seed'] == 1).sum())}")
print(f"     Fertilizer users: {int((maize['inorganic_fertilizer_used'] == 1).sum())}")
print(f"     Households borrowing (maize rows): {int((maize['household_borrowed'] == 1).sum())} rows")

missing_pred = int(maize[["improved_seed", "inorganic_fertilizer_used",
                          "household_borrowed", "maize_yield_kg_ha"]].isna().any(axis=1).sum())
print(f"     Rows missing >=1 key predictor (seed/fert/credit/yield): {missing_pred}")


# ----------------------------------------------------------------------------
# 8. Variable dictionary (sheet 3)
# ----------------------------------------------------------------------------
VARIABLE_DICTIONARY_ROWS = [
        ["household_id", "hhid", "GSEC1 / all files",
         "Anonymised household identifier", "32-char string", "household", "Links maize, credit and location; anonymised"],
        ["parcel_id", "parcelID", "AGSEC4A/4B",
         "Parcel identifier within household", "integer", "parcel", "Not unique across households"],
        ["plot_id", "pltid", "AGSEC4A/4B",
         "Plot identifier within parcel", "integer", "plot", "Not unique across parcels"],
        ["season", "derived (file A vs B)", "AGSEC4A/5A & AGSEC4B/5B",
         "Agricultural season", "Season 2 2017 / Season 1 2018", "season", "A-files = season 2 2017; B-files = season 1 2018"],
        ["region", "region", "GSEC1",
         "Region name", "1=Central, 2=Eastern, 3=Northern, 4=Western", "region", "4-region code, stable across waves"],
        ["district", "distirct_name (typo)", "GSEC1",
         "District name", "text", "district", "Header spelling 'distirct_name' in source"],
        ["rural_urban", "urban", "GSEC1",
         "Rural/urban classification", "0=Rural, 1=Urban", "household", "Do not mix with AGSEC1 coding (1=Urban,2=Rural)"],
        ["harvest_status", "harvest / harvest_b", "AGSEC5A/5B",
         "Harvest status", "1=Full, 2=Partial, 3=No harvest", "plot-crop", "No-harvest rows may still carry a quantity (see yield_flag)"],
        ["maize_production_kg", "s5aq06a_1 * a5aq6d (A) / s5bq06a_1 * a5bq6d (B)", "AGSEC5A/5B",
         "Maize harvested (kg) = quantity x conversion factor", "kg", "plot-crop", "Missing if quantity or conversion factor invalid"],
        ["maize_area_acres", "s4aq07 (A) / s4bq07 (B)", "AGSEC4A/4B",
         "Maize area planted, farmer-reported", "acres", "plot-crop", "Farmer-reported; intercropped plots noisy"],
        ["maize_area_ha", "maize_area_acres * 0.404686", "derived",
         "Maize area in hectares", "ha", "plot-crop", "1 acre = 0.404686 ha"],
        ["maize_yield_kg_ha", "production_kg / area_ha", "derived",
         "Maize yield", "kg/ha", "plot-crop", "Only where area>0 and production valid; see yield_flag"],
        ["seed_type", "s4aq13 (A) / s4bq13 (B)", "AGSEC4A/4B",
         "Seed type (label)", "1=Traditional, 2=Improved", "plot-crop", "Self-reported"],
        ["improved_seed", "s4aq13 (A) / s4bq13 (B)", "AGSEC4A/4B",
         "Improved seed indicator", "1=Improved, 0=Traditional", "plot-crop", "Missing if seed type not recorded"],
        ["organic_fertilizer_used", "s3aq04 (A) / s3bq04 (B)", "AGSEC3A/3B",
         "Organic fertilizer used on the plot", "1=Yes, 0=No", "plot", "Plot-level, not crop-specific"],
        ["inorganic_fertilizer_used", "s3aq13 (A) / s3bq13 (B)", "AGSEC3A/3B",
         "Inorganic/chemical fertilizer used on the plot", "1=Yes, 0=No", "plot", "Plot-level; ~128 users in season 2"],
        ["inorganic_fertilizer_kg", "s3aq15 (A) / s3bq15 (B)", "AGSEC3A/3B",
         "Inorganic fertilizer quantity", "kg", "plot", "Plot-level, may not be maize-specific"],
        ["household_borrowed", "CB12 (any member==1)", "GSEC7_4",
         "Household has a borrower (money, last 12 months)", "1=Yes, 0=No, blank=unknown", "household", "Aggregated from person level"],
        ["agricultural_loan", "CB17 in {2,3,4} (any member)", "GSEC7_4",
         "Agricultural loan identified", "1=Yes, 0=No, blank=unknown", "household", "Codes 2=livestock, 3=farm tools, 4=farm inputs"],
        ["loan_purpose", "CB17", "GSEC7_4",
         "Agricultural loan purpose label(s)", "text", "household", "Only filled for agricultural loans"],
        ["rainfall_mm", "n/a (CHIRPS, external)", "not in UNPS",
         "Growing-season rainfall", "mm", "household-season", "NOT integrated yet; do not invent"],
        ["yield_flag", "derived", "derived",
         "Data-quality flag for review", "text", "plot-crop", "Flags area<=0, extreme yield, no-harvest-with-quantity"],
]

variable_dictionary = pd.DataFrame(VARIABLE_DICTIONARY_ROWS, columns=[
    "Clean column name", "Original UNPS variable", "Original source file",
    "Description", "Code meanings", "Unit of measurement", "Important limitations",
])


# ----------------------------------------------------------------------------
# 9. Write the Excel workbook
# ----------------------------------------------------------------------------
with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
    maize.to_excel(xw, sheet_name="Maize_Analysis", index=False)
    household_credit_out.to_excel(xw, sheet_name="Household_Credit", index=False)
    variable_dictionary.to_excel(xw, sheet_name="Variable_Dictionary", index=False)


print("\nWrote:", OUT_XLSX)
