#!/usr/bin/env python3
"""
prepare_three_crops.py
======================
Build the combined, analysis-ready AgriCredit-Yield Uganda dataset for **three crops**
(maize, common beans and coffee) from the raw UNPS 2018/19 (Wave 7) CSV files.

Output
------
Combined_Crops/UNPS_AgriCredit_Three_Crops.xlsx
    Sheet 1: "Crop_Analysis"       -> one row per plot x crop x season (3 crops)
    Sheet 2: "Household_Credit"    -> one row per household
    Sheet 3: "Crop_Summary"        -> one row per crop (unweighted sample stats)
    Sheet 4: "Variable_Dictionary" -> documentation of every clean column

This script only READS the original survey files. It does not modify them, and it
does not overwrite the existing maize workbook.

Run from anywhere (paths are resolved relative to this script's location):
    python AgriCredit_Yield_Analysis/Combined_Crops/prepare_three_crops.py
"""

import os
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------
# Paths (resolved relative to this file; no dependence on the current directory)
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))          # .../Combined_Crops
BASE = os.path.dirname(os.path.dirname(SCRIPT_DIR))              # .../UNPS_DATASET
AGRIC = os.path.join(BASE, "Agric")
HH = os.path.join(BASE, "HH")
OUT_XLSX = os.path.join(SCRIPT_DIR, "UNPS_AgriCredit_Three_Crops.xlsx")

ACRES_TO_HA = 0.404686  # 1 acre = 0.404686 hectares

# ----------------------------------------------------------------------------
# Verified crop codes (UNPS 2018/19 crop annex)
# ----------------------------------------------------------------------------
# 130 = Maize, 210 = Beans, 810 = Coffee (generic), 811 = Coffee (arabica),
# 812 = Coffee (robusta).  All three coffee codes group under the crop "Coffee".
CROP_NAME = {130: "Maize", 210: "Beans", 810: "Coffee", 811: "Coffee", 812: "Coffee"}
MAIZE_CODES = (130,)
BEANS_CODES = (210,)
COFFEE_CODES = (810, 811, 812)

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

# CB16__* (loan source) flags. Formal vs informal classification (verified).
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
        return g.groupby("hhid")[col].apply(lambda s: (s == val).any()).reset_index(drop=True)

    def answered_col(col):
        return g.groupby("hhid")[col].apply(lambda s: s.notna().any()).reset_index(drop=True)

    hh = pd.DataFrame({"hhid": g["hhid"].drop_duplicates().reset_index(drop=True)})

    any_yes = any_col("CB12", 1)
    any_answered = answered_col("CB12")
    hh["household_borrowed"] = np.where(
        any_yes, 1, np.where(any_answered, 0, np.nan))

    hh["household_goods_credit"] = np.where(
        any_col("CB13", 1), 1, np.where(answered_col("CB13"), 0, np.nan))

    ag = g.groupby("hhid")["CB17"].apply(lambda s: s.isin(AG_REASONS).any()).reset_index(drop=True)
    any_reason = g.groupby("hhid")["CB17"].apply(lambda s: s.notna().any()).reset_index(drop=True)
    hh["agricultural_loan"] = np.where(
        ag, 1, np.where((any_reason) | (hh["household_borrowed"] == 0), 0, np.nan))

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

    formal_cols = [c for c in g.columns if c.startswith("CB16__") and c in FORMAL_SOURCES]
    informal_cols = [c for c in g.columns if c.startswith("CB16__") and c in INFORMAL_SOURCES]
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
# 4. Build one season's crop records (maize / beans / coffee)
# ----------------------------------------------------------------------------
def build_season(a4, a5, a3, season_label, crop_codes, crop_name,
                 area_col, seed_col, qty_col, conv_col, harvest_col,
                 fert_org_col, fert_inorg_col, fert_qty_col):
    """Combine area/seed (a4) + production (a5) + fertilizer (a3) for one season.

    Uses a full-outer join on (hhid, parcelID, pltid, cropID) so records that have
    only area or only production are preserved, not dropped.

    Returns a DataFrame with generic column names shared by all three crops.
    """
    area = a4[a4["cropID"].isin(crop_codes)][
        ["hhid", "parcelID", "pltid", "cropID", area_col, seed_col]
    ].copy()
    prod = a5[a5["cropID"].isin(crop_codes)][
        ["hhid", "parcelID", "pltid", "cropID", qty_col, conv_col, harvest_col]
    ].copy()

    key = ["hhid", "parcelID", "pltid", "cropID"]
    df = area.merge(prod, on=key, how="outer", suffixes=("_area", "_prod"))

    # --- crop code / name -----------------------------------------------------
    df["crop_code"] = df["cropID"]
    df["crop_name"] = crop_name

    # --- production (kg) = quantity * conversion factor -----------------------
    qty = df[qty_col]
    conv = df[conv_col]
    valid_conv = conv.notna() & (conv > 0)
    df["crop_production_kg"] = np.where(
        qty.notna() & valid_conv, qty * conv, np.nan)

    # --- area (acres -> ha) ---------------------------------------------------
    df["crop_area_acres"] = df[area_col]
    df["crop_area_ha"] = df[area_col] * ACRES_TO_HA

    # --- yield -----------------------------------------------------------------
    # Maize and beans: dry-grain / legume yield is meaningful (kg/ha).
    # Coffee: yield is intentionally left missing (mixed product forms and
    #         inconsistent crop codes across area vs production modules).
    if crop_name == "Coffee":
        df["crop_yield_kg_ha"] = np.nan
    else:
        df["crop_yield_kg_ha"] = np.where(
            df["crop_area_ha"].notna() & (df["crop_area_ha"] > 0)
            & df["crop_production_kg"].notna(),
            df["crop_production_kg"] / df["crop_area_ha"],
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
    for c in ("organic_fertilizer_used", "inorganic_fertilizer_used"):
        fert[c] = np.where(fert[c] == 1, 1, np.where(fert[c] == 2, 0, np.nan))
    df = df.merge(fert, on=["hhid", "parcelID", "pltid"], how="left")

    # --- season + key bookkeeping ----------------------------------------------
    df["season"] = season_label
    df = df.rename(columns={"hhid": "household_id",
                            "parcelID": "parcel_id",
                            "pltid": "plot_id"})

    # --- flags (review only, never removal) -------------------------------------
    flags = pd.Series("", index=df.index, dtype=object)
    flags[df["crop_area_acres"].notna() & (df["crop_area_acres"] <= 0)] = "area<=0"
    flags[df["crop_yield_kg_ha"].notna() & (df["crop_yield_kg_ha"] > 10000)] = \
        "suspiciously high yield (>10,000 kg/ha)"
    flags[(df[harvest_col] == 3) & df["crop_production_kg"].notna() & (df["crop_production_kg"] > 0)] = \
        "reported no harvest but quantity recorded"

    if crop_name == "Coffee":
        coffee_reason = ("coffee: yield not computed (mixed product forms - "
                         "fresh/dried cherries vs green coffee - and crop-code "
                         "inconsistency between area and production modules)")
        flags[df["crop_production_kg"].notna() | df["crop_area_acres"].notna()] = \
            _combine_flag(flags[df["crop_production_kg"].notna() | df["crop_area_acres"].notna()],
                          coffee_reason)

    df["yield_flag"] = flags

    keep = [
        "household_id", "parcel_id", "plot_id", "season",
        "crop_code", "crop_name",
        "crop_production_kg", "crop_area_acres", "crop_area_ha", "crop_yield_kg_ha",
        "seed_type", "improved_seed",
        "organic_fertilizer_used", "inorganic_fertilizer_used", "inorganic_fertilizer_kg",
        "yield_flag",
    ]
    return df[keep]


def _combine_flag(existing, new):
    out = existing.copy()
    blank = (out == "") | out.isna()
    out[blank] = new
    out[~blank] = out[~blank].astype(str) + "; " + new
    return out


# Season 2 2017 (A-files) and Season 1 2018 (B-files)
SEASON2_ARGS = dict(
    season_label="Season 2 2017",
    area_col="s4aq07", seed_col="s4aq13",
    qty_col="s5aq06a_1", conv_col="a5aq6d", harvest_col="harvest",
    fert_org_col="s3aq04", fert_inorg_col="s3aq13", fert_qty_col="s3aq15",
)
SEASON1_ARGS = dict(
    season_label="Season 1 2018",
    area_col="s4bq07", seed_col="s4bq13",
    qty_col="s5bq06a_1", conv_col="a5bq6d", harvest_col="harvest_b",
    fert_org_col="s3bq04", fert_inorg_col="s3bq13", fert_qty_col="s3bq15",
)


def build_crop(crop_codes, crop_name):
    """Build a full (both seasons) DataFrame for one crop group."""
    s2 = build_season(agsec4a, agsec5a, agsec3a, crop_codes=crop_codes,
                      crop_name=crop_name, **SEASON2_ARGS)
    s1 = build_season(agsec4b, agsec5b, agsec3b, crop_codes=crop_codes,
                      crop_name=crop_name, **SEASON1_ARGS)
    return pd.concat([s2, s1], ignore_index=True)


def _flag_coffee_duplicate_area(df):
    """Mark coffee rows where the same plot x season records an area under MORE
    than one coffee crop code (a known double-record pattern: 810 plus 811/812
    carrying an identical area)."""
    df = df.copy()
    key = ["household_id", "parcel_id", "plot_id", "season"]
    with_area = df[df["crop_area_acres"].notna()]
    grp = (with_area.groupby(key)["crop_code"]
           .apply(lambda s: len(set(s)) > 1)
           .reset_index(name="_multi_area"))
    df = df.merge(grp, on=key, how="left")

    dup_flag = ("coffee: duplicate area across crop codes "
                "(810 and 811/812 recorded on same plot with identical area)")
    mask = df["_multi_area"].fillna(False) & df["crop_area_acres"].notna()
    df.loc[mask, "yield_flag"] = _combine_flag(df.loc[mask, "yield_flag"], dup_flag)
    df = df.drop(columns=["_multi_area"])
    return df


maize = build_crop(MAIZE_CODES, "Maize")
beans = build_crop(BEANS_CODES, "Beans")
coffee = build_crop(COFFEE_CODES, "Coffee")

# Flag coffee plots where 810 and 811/812 carry an identical (duplicate) area.
coffee = _flag_coffee_duplicate_area(coffee)


crops = pd.concat([maize, beans, coffee], ignore_index=True)


# ----------------------------------------------------------------------------
# 5. Join credit + geography (left joins so missing info does not drop rows)
# ----------------------------------------------------------------------------
crops = crops.merge(
    household_credit[["hhid", "household_borrowed", "agricultural_loan", "ag_loan_purpose"]]
    .rename(columns={"ag_loan_purpose": "loan_purpose", "hhid": "household_id"}),
    on="household_id", how="left",
)
crops = crops.merge(
    location[["hhid", "region_name", "district", "rural_urban"]]
    .rename(columns={"hhid": "household_id", "region_name": "region"}),
    on="household_id", how="left",
)

# rainfall is NOT available in the UNPS folder; leave missing (do not invent)
crops["rainfall_mm"] = np.nan

COL_ORDER = [
    "household_id", "parcel_id", "plot_id", "season",
    "crop_code", "crop_name", "region", "district", "rural_urban",
    "crop_production_kg", "crop_area_acres", "crop_area_ha", "crop_yield_kg_ha",
    "seed_type", "improved_seed",
    "organic_fertilizer_used", "inorganic_fertilizer_used", "inorganic_fertilizer_kg",
    "household_borrowed", "agricultural_loan", "loan_purpose",
    "rainfall_mm", "yield_flag",
]
crops = crops[COL_ORDER]

# convert indicator columns to nullable integer so Excel shows 1/0 and blank (not 1.0)
for c in ["crop_code", "improved_seed", "organic_fertilizer_used",
          "inorganic_fertilizer_used", "household_borrowed", "agricultural_loan"]:
    crops[c] = pd.to_numeric(crops[c], errors="coerce").astype("Int64")


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
# 7. Crop_Summary sheet (one row per crop; unweighted sample statistics)
# ----------------------------------------------------------------------------
def crop_summary(df, crop_name, codes):
    sub = df[df["crop_name"] == crop_name]
    n = len(sub)
    n_hh = sub["household_id"].nunique()
    n_yield = int(sub["crop_yield_kg_ha"].notna().sum())
    n_missing_yield = int(sub["crop_yield_kg_ha"].isna().sum())
    mean_yield = sub["crop_yield_kg_ha"].mean()
    median_yield = sub["crop_yield_kg_ha"].median()

    improved = int((sub["improved_seed"] == 1).sum())
    traditional = int((sub["improved_seed"] == 0).sum())
    seed_rate = improved / (improved + traditional) if (improved + traditional) else np.nan

    def use_rate(col):
        known = int(sub[col].notna().sum())
        used = int((sub[col] == 1).sum())
        return used / known if known else np.nan

    org_rate = use_rate("organic_fertilizer_used")
    inorg_rate = use_rate("inorganic_fertilizer_used")

    hh = sub[["household_id", "household_borrowed", "agricultural_loan"]].drop_duplicates("household_id")
    borrow_known = int(hh["household_borrowed"].notna().sum())
    borrowed = int((hh["household_borrowed"] == 1).sum())
    borrow_rate = borrowed / borrow_known if borrow_known else np.nan
    ag_known = int(hh["agricultural_loan"].notna().sum())
    ag_loan = int((hh["agricultural_loan"] == 1).sum())
    ag_rate = ag_loan / ag_known if ag_known else np.nan

    return {
        "crop_name": crop_name,
        "crop_codes": ", ".join(str(c) for c in codes),
        "total_observations": n,
        "unique_households": n_hh,
        "valid_yield_observations": n_yield,
        "missing_yield_observations": n_missing_yield,
        "mean_yield_kg_ha": mean_yield,
        "median_yield_kg_ha": median_yield,
        "improved_seed_adoption_rate": seed_rate,
        "organic_fertilizer_use_rate": org_rate,
        "inorganic_fertilizer_use_rate": inorg_rate,
        "household_borrowing_rate": borrow_rate,
        "agricultural_borrowing_rate": ag_rate,
    }


summary_rows = [
    crop_summary(crops, "Maize", MAIZE_CODES),
    crop_summary(crops, "Beans", BEANS_CODES),
    crop_summary(crops, "Coffee", COFFEE_CODES),
]
crop_summary_df = pd.DataFrame(summary_rows)

SUMMARY_COLUMNS = [
    "crop_name", "crop_codes",
    "total_observations", "unique_households",
    "valid_yield_observations", "missing_yield_observations",
    "mean_yield_kg_ha", "median_yield_kg_ha",
    "improved_seed_adoption_rate", "organic_fertilizer_use_rate",
    "inorganic_fertilizer_use_rate",
    "household_borrowing_rate", "agricultural_borrowing_rate",
]
crop_summary_df = crop_summary_df[SUMMARY_COLUMNS]


# ----------------------------------------------------------------------------
# 8. Variable dictionary (sheet 4)
# ----------------------------------------------------------------------------
VARIABLE_DICTIONARY_ROWS = [
    ["household_id", "hhid", "GSEC1 / all files",
     "Anonymised household identifier", "32-char string", "household",
     "Links crop, credit and location records; anonymised"],
    ["parcel_id", "parcelID", "AGSEC4A/4B, AGSEC5A/5B, AGSEC3A/3B",
     "Parcel identifier within household", "integer", "parcel",
     "Not unique across households"],
    ["plot_id", "pltid", "AGSEC4A/4B, AGSEC5A/5B, AGSEC3A/3B",
     "Plot identifier within parcel", "integer", "plot",
     "Not unique across parcels"],
    ["season", "derived (file A vs B)", "AGSEC4A/5A & AGSEC4B/5B",
     "Agricultural season", "Season 2 2017 / Season 1 2018", "season",
     "A-files = season 2 2017; B-files = season 1 2018"],
    ["crop_code", "cropID", "AGSEC4A/4B, AGSEC5A/5B",
     "Original UNPS crop code", "130=Maize, 210=Beans, 810=Coffee, 811=Coffee (arabica), 812=Coffee (robusta)", "crop",
     "Coffee uses three codes; group 810/811/812 under 'Coffee'"],
    ["crop_name", "derived from crop_code", "derived",
     "Standardised crop label", "Maize / Beans / Coffee", "crop",
     "811/812 (arabica/robusta) are labelled 'Coffee' to allow grouping"],
    ["region", "region", "GSEC1",
     "Region name", "1=Central, 2=Eastern, 3=Northern, 4=Western", "region",
     "4-region code, stable across waves"],
    ["district", "distirct_name (typo)", "GSEC1",
     "District name", "text", "district",
     "Header spelling 'distirct_name' in source"],
    ["rural_urban", "urban", "GSEC1",
     "Rural/urban classification", "0=Rural, 1=Urban", "household",
     "Do not mix with AGSEC1 coding (1=Urban, 2=Rural)"],
    ["crop_production_kg", "s5aq06a_1 * a5aq6d (A) / s5bq06a_1 * a5bq6d (B)", "AGSEC5A/5B",
     "Crop harvested (kg) = quantity x conversion factor", "kg", "plot-crop",
     "For coffee the kg refers to the harvested product form (see yield_flag); not standardised to green coffee"],
    ["crop_area_acres", "s4aq07 (A) / s4bq07 (B)", "AGSEC4A/4B",
     "Crop area planted, farmer-reported", "acres", "plot-crop",
     "Farmer-reported; intercropped plots noisy"],
    ["crop_area_ha", "crop_area_acres * 0.404686", "derived",
     "Crop area in hectares", "ha", "plot-crop",
     "1 acre = 0.404686 ha"],
    ["crop_yield_kg_ha", "production_kg / area_ha", "derived",
     "Crop yield", "kg/ha", "plot-crop",
     "Maize & beans only where area>0 and production valid. Coffee yield left missing (see README)"],
    ["seed_type", "s4aq13 (A) / s4bq13 (B)", "AGSEC4A/4B",
     "Seed type (label)", "1=Traditional, 2=Improved", "plot-crop",
     "Self-reported. Mostly missing for coffee (perennial)"],
    ["improved_seed", "s4aq13 (A) / s4bq13 (B)", "AGSEC4A/4B",
     "Improved seed indicator", "1=Improved, 0=Traditional, blank=not recorded", "plot-crop",
     "Missing means 'unknown', not 'traditional'. Not meaningful for coffee"],
    ["organic_fertilizer_used", "s3aq04 (A) / s3bq04 (B)", "AGSEC3A/3B",
     "Organic fertilizer used on the plot", "1=Yes, 0=No", "plot",
     "Plot-level, not crop-specific"],
    ["inorganic_fertilizer_used", "s3aq13 (A) / s3bq13 (B)", "AGSEC3A/3B",
     "Inorganic/chemical fertilizer used on the plot", "1=Yes, 0=No", "plot",
     "Plot-level; shared by all crops on the plot"],
    ["inorganic_fertilizer_kg", "s3aq15 (A) / s3bq15 (B)", "AGSEC3A/3B",
     "Inorganic fertilizer quantity", "kg", "plot",
     "Plot-level, not crop-specific"],
    ["household_borrowed", "CB12 (any member==1)", "GSEC7_4",
     "Household has a borrower (money, last 12 months)", "1=Yes, 0=No, blank=unknown", "household",
     "Aggregated from person level"],
    ["agricultural_loan", "CB17 in {2,3,4} (any member)", "GSEC7_4",
     "Agricultural loan identified", "1=Yes, 0=No, blank=unknown", "household",
     "Codes 2=livestock, 3=farm tools, 4=farm inputs"],
    ["loan_purpose", "CB17", "GSEC7_4",
     "Agricultural loan purpose label(s)", "text", "household",
     "Only filled for agricultural loans"],
    ["rainfall_mm", "n/a (CHIRPS, external)", "not in UNPS",
     "Growing-season rainfall", "mm", "household-season",
     "NOT integrated yet; do not invent"],
    ["yield_flag", "derived", "derived",
     "Data-quality flag for review", "text", "plot-crop",
     "Flags area<=0, extreme yield, no-harvest-with-quantity, coffee limitations"],
]

variable_dictionary = pd.DataFrame(VARIABLE_DICTIONARY_ROWS, columns=[
    "Clean column name", "Original UNPS variable", "Original source file",
    "Description", "Code meanings", "Unit of measurement", "Important limitations",
])


# ----------------------------------------------------------------------------
# 9. Validation (printed to the terminal)
# ----------------------------------------------------------------------------
def _reconcile_maize():
    """Compare the maize rows produced here against the existing maize workbook."""
    print("-" * 70)
    print("MAIZE RECONCILIATION vs UNPS_AgriCredit_Maize_Analysis.xlsx")
    print("-" * 70)
    existing_path = os.path.join(BASE, "AgriCredit_Yield_Analysis",
                                 "UNPS_AgriCredit_Maize_Analysis.xlsx")
    if not os.path.exists(existing_path):
        print("Existing maize workbook not found - reconciliation skipped.")
        return
    old = pd.read_excel(existing_path, sheet_name="Maize_Analysis")
    new = crops[crops["crop_name"] == "Maize"].copy()

    old_key = old[["household_id", "parcel_id", "plot_id", "season"]].copy()
    new_key = new[["household_id", "parcel_id", "plot_id", "season"]].copy()
    print(f"Existing maize rows : {len(old)}")
    print(f"New maize rows      : {len(new)}")

    # align key dtypes for comparison
    for df_ in (old_key, new_key):
        for c in ("parcel_id", "plot_id"):
            df_[c] = pd.to_numeric(df_[c], errors="coerce")
    old_set = set(map(tuple, old_key.values))
    new_set = set(map(tuple, new_key.values))
    print(f"Keys identical      : {old_set == new_set}")
    if old_set != new_set:
        print(f"  only in existing  : {len(old_set - new_set)}")
        print(f"  only in new       : {len(new_set - old_set)}")

    # compare key numeric fields on the matched key (old vs new column names differ)
    m = old.merge(new, on=list(old_key.columns), how="inner",
                  suffixes=("_old", "_new"))
    for col in ["maize_production_kg", "maize_area_acres", "maize_yield_kg_ha"]:
        newcol = {"maize_production_kg": "crop_production_kg",
                  "maize_area_acres": "crop_area_acres",
                  "maize_yield_kg_ha": "crop_yield_kg_ha"}[col]
        a = pd.to_numeric(m[col], errors="coerce")
        b = pd.to_numeric(m[newcol], errors="coerce")
        diff = ((a - b).abs() > 1e-6).sum()
        print(f"  {col}: {diff} value mismatches (of {len(m)} matched rows)")


print("=" * 70)
print("VALIDATION")
print("=" * 70)

key = ["household_id", "parcel_id", "plot_id", "crop_code", "season"]
print(f"[1] Total combined observations : {len(crops)}")
print(f"[2] Maize / Beans / Coffee      : "
      f"{int((crops['crop_name']=='Maize').sum())} / "
      f"{int((crops['crop_name']=='Beans').sum())} / "
      f"{int((crops['crop_name']=='Coffee').sum())}")
print(f"[3] Unique households overall   : {crops['household_id'].nunique()}")
for cn in ["Maize", "Beans", "Coffee"]:
    sub = crops[crops["crop_name"] == cn]
    print(f"    {cn:8s} -> obs={len(sub):5d}, households={sub['household_id'].nunique():5d}, "
          f"valid yield={int(sub['crop_yield_kg_ha'].notna().sum()):5d}, "
          f"improved seed={int((sub['improved_seed']==1).sum()):5d}")
print(f"[4] Duplicate (hhid,parcel,plot,crop_code,season) rows: "
      f"{crops.duplicated(key).sum()}")
print(f"[5] Area<=0 rows: {int((crops['crop_area_acres'] <= 0).sum())} | "
      f"missing area: {int(crops['crop_area_acres'].isna().sum())} | "
      f"missing production: {int(crops['crop_production_kg'].isna().sum())}")
print(f"[6] Fertilizer: inorganic users (rows)={int((crops['inorganic_fertilizer_used']==1).sum())}, "
      f"organic users={int((crops['organic_fertilizer_used']==1).sum())}")
print(f"[7] Credit: households borrowed={int((household_credit['household_borrowed']==1).sum())}, "
      f"agricultural loans={int((household_credit['agricultural_loan']==1).sum())}")
print(f"[8] Regions represented: {sorted(crops['region'].dropna().unique())}")
print(f"[9] Coffee rows with duplicate-area flag: "
      f"{int(crops['yield_flag'].str.contains('duplicate area', na=False).sum())}")

_reconcile_maize()


# ----------------------------------------------------------------------------
# 10. Write the Excel workbook
# ----------------------------------------------------------------------------
with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
    crops.to_excel(xw, sheet_name="Crop_Analysis", index=False)
    household_credit_out.to_excel(xw, sheet_name="Household_Credit", index=False)
    crop_summary_df.to_excel(xw, sheet_name="Crop_Summary", index=False)
    variable_dictionary.to_excel(xw, sheet_name="Variable_Dictionary", index=False)

print("\nWrote:", OUT_XLSX)
