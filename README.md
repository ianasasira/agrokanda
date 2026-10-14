# AgriCredit–Yield Uganda — Analysis Dataset

A clean, analysis-ready dataset built from the **Uganda National Panel Survey (UNPS) 2018/19**
(Wave 7) to study the relationship between **agricultural credit access and maize productivity**
in Uganda.

This folder contains one Excel workbook with three sheets, plus a script that reproduces it
from the raw survey files.

## Project purpose

This dataset links, at the household and plot level:

- **Maize production and yield** (from the agriculture questionnaire),
- **Seed type** (traditional vs improved),
- **Fertilizer use** (organic and inorganic),
- **Household borrowing / credit** (from the household questionnaire), and
- **Geography** (region, district, rural/urban).

It is designed for exploratory data analysis, statistical comparison, Python modelling and
Qlik Sense visualisation. It supports questions such as *"do households that access credit
achieve higher maize yields?"* — with the important caveat that it is an **observational,
cross-sectional** dataset (see limitations).

## Data sources

| UNPS file | What it contributes |
|---|---|
| `Agric/AGSEC4A.csv`, `AGSEC4B.csv` | maize crop code (130), **area planted** (acres), **seed type** |
| `Agric/AGSEC5A.csv`, `AGSEC5B.csv` | **harvest quantity** + conversion factor → kg |
| `Agric/AGSEC3A.csv`, `AGSEC3B.csv` | **fertilizer** use and quantity (plot level) |
| `HH/GSEC7_4.csv` | **credit / borrowing** (person level → aggregated to household) |
| `HH/GSEC1.csv` | **region, district, rural/urban** |

The raw files are in `UNPS DATASET/Agric/` and `UNPS DATASET/HH/`. Documentation of every
mapping decision is in `UNPS DATASET/analysis_docs/`.

## Dataset structure

The workbook `UNPS_AgriCredit_Maize_Analysis.xlsx` has three sheets:

| Sheet | One row = | Used for |
|---|---|---|
| **Maize_Analysis** | one maize plot × crop × season | main analysis (yield, seed, fertilizer, credit) |
| **Household_Credit** | one household | household-level credit profile |
| **Variable_Dictionary** | one variable | documentation / trace-back to UNPS codes |

## Maize yield calculation

```
maize_production_kg = harvest_quantity × conversion_factor
    (AGSEC5A: s5aq06a_1 × a5aq6d   — Season 2 2017)
    (AGSEC5B: s5bq06a_1 × a5bq6d   — Season 1 2018)

maize_area_ha = maize_area_acres × 0.404686
    (AGSEC4A: s4aq07; AGSEC4B: s4bq07 — farmer-reported acres)

maize_yield_kg_ha = maize_production_kg / maize_area_ha
```

Yield is only computed where **area > 0** and production is valid. Suspicious values are
**flagged** in `yield_flag`, never silently removed.

## Seed and fertilizer coding

- **Seed type** (`s4aq13` / `s4bq13`): `1 = Traditional`, `2 = Improved`.
  - `seed_type` → readable label ("Traditional"/"Improved").
  - `improved_seed` → `1` improved, `0` traditional, blank if not recorded.
- **Fertilizer** (`AGSEC3A/3B`, plot level):
  - `organic_fertilizer_used` → `1` if `s3aq04/s3bq04 == 1`, `0` if `== 2`.
  - `inorganic_fertilizer_used` → `1` if `s3aq13/s3bq13 == 1`, `0` if `== 2`.
  - `inorganic_fertilizer_kg` → `s3aq15/s3bq15` (kg).
  - Fertilizer is recorded **per plot**, not per crop (see limitations).

## Credit coding

- `household_borrowed` = `1` if **any** household member borrowed money in the last 12 months
  (`CB12 == 1`), `0` if at least one member answered "No", blank if no member was asked.
- `agricultural_loan` = `1` if any member's loan reason `CB17` is in `{2, 3, 4}`
  (**2 = buy livestock, 3 = buy farm tools, 4 = buy farm inputs**); `0` otherwise.
- `loan_purpose` = readable label(s) of the agricultural loan purpose.
- `borrowing_source` (Household_Credit sheet) = Formal / Informal / Formal & informal,
  derived from the loan-source flags `CB16__*`.

Borrowing is recorded **per person** and then aggregated to the household.

## Important limitations

- **Rainfall is not yet integrated.** `rainfall_mm` is blank; CHIRPS data will be added later.
- **No loan amount** is available in the UNPS 2018/19 credit module.
- **No loan dates** — a loan cannot be matched to a specific planting/harvest. Household
  borrowing is a *contemporaneous* indicator, not a proven cause of yield.
- **Household borrowing does not prove agricultural investment** — only `CB17 ∈ {2,3,4}`
  identifies a loan with an agricultural purpose.
- **Fertilizer is plot-level** and may not be applied exclusively to maize (a plot can grow
  maize + beans).
- **Multiple maize plots can belong to one household** (one row per plot per season).
- **This dataset cannot establish that borrowing *causes* higher yields.**

## How to use the Excel workbook

A few useful analyses:

- **Average maize yield by region:** pivot `region` against `maize_yield_kg_ha` (mean/median).
- **Improved vs traditional seed:** compare `maize_yield_kg_ha` by `improved_seed`.
- **Fertilizer users vs non-users:** compare yields by `inorganic_fertilizer_used`.
- **Borrowing vs non-borrowing households:** compare yields by `household_borrowed` and
  `agricultural_loan`.
- **Agricultural borrowing by region:** cross-tab `region` × `agricultural_loan`.
- **Yield distribution:** histogram / boxplot of `maize_yield_kg_ha` (trim extreme outliers;
  see `yield_flag`).

## Reproducing the dataset

Run, from the `UNPS DATASET/` folder:

```bash
python AgriCredit_Yield_Analysis/prepare_dataset.py
```

The script reads the raw CSVs (without modifying them) and rewrites
`UNPS_AgriCredit_Maize_Analysis.xlsx`.
