# Combined UNPS Crop Dataset — Maize, Beans & Coffee

A single, clean, analysis-ready Excel workbook built from the **Uganda National Panel
Survey (UNPS) 2018/19** (Wave 7) that links **agricultural credit access** to **crop
production and yield** for three crops in Uganda: **maize, common beans and coffee**.

This workbook (`UNPS_AgriCredit_Three_Crops.xlsx`) replaces the earlier single-crop
maize workbook with a combined, multi-crop version. The original UNPS files and the
previous maize workbook are **not** modified.

---

## Project purpose

AgriCredit–Yield Uganda analyses how household access to credit relates to crop
productivity. The workbook links, at household, plot and crop level:

- **Crop production, area and yield** (agriculture questionnaire),
- **Seed type** (traditional vs improved),
- **Fertilizer use** (organic and inorganic),
- **Household borrowing / credit** (household questionnaire), and
- **Geography** (region, district, rural/urban).

It is designed for exploratory analysis, statistical comparison, Python modelling and
Qlik Sense visualisation. It is an **observational, cross-sectional** dataset — it
cannot by itself establish that credit *causes* higher yields.

---

## The three crops and their verified crop codes

Crop codes come from the official UNPS 2018/19 crop annex (verified against
`analysis_docs/UNPS_KEY_VARIABLE_CODEBOOK.csv` and the raw `AGSEC4A/4B` data).

| Crop | `crop_code` | Notes |
|---|---|---|
| **Maize** | `130` | Annual grain; same code as the earlier maize workbook. |
| **Common beans** | `210` | Annual legume. |
| **Coffee** | `810`, `811`, `812` | `810` = Coffee (generic), `811` = Coffee (arabica), `812` = Coffee (robusta). All three are labelled `crop_name = "Coffee"` and grouped for analysis. |

> **Coffee varieties are recorded separately.** Arabica (`811`) and robusta (`812`) are
> distinct crop codes in the survey and are retained verbatim in `crop_code`. They are
> grouped under `crop_name = "Coffee"` so the three crop families remain comparable.
> No crop code has been invented.

---

## Original UNPS files used

| UNPS file | What it contributes |
|---|---|
| `Agric/AGSEC4A.csv`, `AGSEC4B.csv` | crop code, **area planted** (acres), **seed type** |
| `Agric/AGSEC5A.csv`, `AGSEC5B.csv` | **harvest quantity** + conversion factor → kg |
| `Agric/AGSEC3A.csv`, `AGSEC3B.csv` | **fertilizer** use and quantity (plot level) |
| `HH/GSEC7_4.csv` | **credit / borrowing** (person level → aggregated to household) |
| `HH/GSEC1.csv` | **region, district, rural/urban** |

The raw files live in `UNPS DATASET/Agric/` and `UNPS DATASET/HH/`.

---

## Workbook structure

`UNPS_AgriCredit_Three_Crops.xlsx` has four sheets:

| Sheet | One row = | Used for |
|---|---|---|
| **Crop_Analysis** | one plot × crop × season | main analysis (yield, seed, fertilizer, credit) |
| **Household_Credit** | one household | household-level credit profile |
| **Crop_Summary** | one crop | unweighted sample statistics per crop |
| **Variable_Dictionary** | one variable | documentation / trace-back to UNPS codes |

---

## How the datasets were joined

Agricultural data are at the **parcel × plot × crop** level; the survey has **two
seasons** that are kept strictly separate:

| Season | Area/seed | Production | Fertilizer | Reference |
|---|---|---|---|---|
| Season 2 2017 | AGSEC4A | AGSEC5A | AGSEC3A | visit 1 |
| Season 1 2018 | AGSEC4B | AGSEC5B | AGSEC3B | visit 2 |

Join rules (verified, see `analysis_docs/UNPS_JOIN_KEYS.md`):

1. **Area + production** are joined on `(hhid, parcelID, pltid, cropID)` with a
   *full outer* join, so records that have only area or only production are kept
   (not silently dropped). A↔A and B↔B only — never mix seasons.
2. **Fertilizer** is plot-level (no `cropID`) and is joined on
   `(hhid, parcelID, pltid)` — a crop row inherits the whole plot's fertilizer.
3. **Credit** is person-level and is first aggregated to the household
   ("any member") and then joined on `hhid`.
4. **Geography** is household-level and joined on `hhid`.

All joins use left/outer merges so missing information does not delete crop rows.

---

## How crop yields were calculated

```
crop_production_kg = harvest_quantity × conversion_factor
    Season 2 2017:  s5aq06a_1 × a5aq6d
    Season 1 2018:  s5bq06a_1 × a5bq6d

crop_area_ha  = crop_area_acres × 0.404686
    (s4aq07 / s4bq07 — farmer-reported acres)

crop_yield_kg_ha = crop_production_kg / crop_area_ha     (maize & beans only)
```

Yield is computed only where area > 0 and production is valid. Suspicious values are
**flagged** in `yield_flag`, never removed.

### Maize and beans

Both are annual crops harvested as a **grain/legume**, so a kg/ha yield is meaningful.
The existing maize logic is preserved exactly — the new maize rows were **reconciled
against `UNPS_AgriCredit_Maize_Analysis.xlsx`** (identical 2,928 rows, zero value
differences).

### Coffee (perennial) — yield is intentionally left missing

Coffee is a **perennial tree crop** and is treated differently:

1. **Mixed product forms.** The survey records coffee production in different physical
   forms — **fresh cherries** (condition `24`), **dried cherries / kiboko** (`44`) and
   **dry green coffee** (`45`/`35`). A kg of fresh cherries is *not* comparable to a kg
   of green coffee (roughly 5–6 kg cherries or ~2.5 kg kiboko ≈ 1 kg green). There is no
   processing ratio in the data to standardise these.
2. **Inconsistent crop codes between modules.** Coffee **area** is mostly recorded under
   `810`, but coffee **production** for many plots is recorded under `811`/`812`. The
   area↔production linkage at the plot-crop level is therefore broken for those plots.
3. **Productive vs planted area.** The recorded area may include non-bearing young trees,
   and the single recorded harvest may not cover coffee's full (often two) harvest cycles.

For these reasons `crop_yield_kg_ha` is **left missing (blank) for all coffee rows**, and
`crop_production_kg` / `crop_area_*` are preserved so a future analyst can build a coffee
yield only after standardising the product form. Do **not** treat coffee yield as
directly comparable to maize/bean grain yield.

---

## Seed-type coding

- Source: `s4aq13` / `s4bq13` — "What type of seed/seedlings did you use?"
  (`1 = Traditional`, `2 = Improved`).
- `seed_type` → readable label ("Traditional" / "Improved").
- `improved_seed` → `1` improved, `0` traditional, blank if not recorded.

**Maize and beans** use this mapping directly.

**Coffee** is a perennial crop and the seed-type question largely does **not** apply:
the great majority of coffee rows have no seed-type answer. Coffee varieties (arabica /
robusta) are **not** treated as "improved seed". Only the tiny number of coffee rows that
actually answered the seed question (63 rows, mostly "Traditional") carry a value.

---

## Fertilizer variables

Recorded at **plot level** (`AGSEC3A/3B`), so a plot growing maize *and* beans reports
one fertilizer value that is shared by both crop rows:

- `organic_fertilizer_used` → `1` if `s3aq04/s3bq04 == 1`, `0` if `== 2`.
- `inorganic_fertilizer_used` → `1` if `s3aq13/s3bq13 == 1`, `0` if `== 2`.
- `inorganic_fertilizer_kg` → `s3aq15/s3bq15` (kg).

---

## Household credit variables

Recorded per **person** in `GSEC7_4` ("last 12 months"), then aggregated to the household:

- `household_borrowed` = `1` if any member `CB12 == 1`; `0` if at least one member
  answered "No"; blank if no member was asked.
- `agricultural_loan` = `1` if any member's loan purpose `CB17 ∈ {2, 3, 4}`
  (**2 = buy livestock, 3 = buy farm tools, 4 = buy farm inputs**); `0` otherwise.
- `loan_purpose` (in `Crop_Analysis`) = the *agricultural* loan purpose label(s).
- `borrowing_source` (in `Household_Credit`) = Formal / Informal / Formal & informal,
  from the loan-source flags `CB16__*`.

Missing borrowing information is **not** treated as "no borrowing".

> A household loan is *not* assumed to have financed maize, beans or coffee in
> particular — `agricultural_loan` only means the loan had *some* agricultural purpose.

---

## Geographic variables

- `region` → `1 = Central, 2 = Eastern, 3 = Northern, 4 = Western`.
- `district` → district name (`distirct_name` — note the spelling typo in the source header).
- `rural_urban` → `0 = Rural, 1 = Urban` (from GSEC1 `urban`).

⚠️ `AGSEC1.csv` uses a *different* urban coding (`1 = Urban, 2 = Rural`); this dataset
always uses the GSEC1 `0/1` coding. UNPS and FinScope geographic definitions are **not**
assumed to match — check before comparing.

---

## Rainfall

`rainfall_mm` is **intentionally blank**. Rainfall is not in the UNPS folder and will be
added later from CHIRPS (matched by the household coordinates in
`unps_geovars_2018_19.csv` and by season). Do not invent values.

---

## Crop-specific limitations

**Maize & beans**

- Heavily intercropped; farmer-reported area is noisy.
- Production uses local-unit × conversion factor; the "condition/state" varies
  (fresh vs dry), so kg are not perfectly comparable across households.

**Coffee**

- Perennial crop; **yield left missing** (see above).
- Area may include non-bearing trees; recorded harvest may be incomplete.
- `810` vs `811`/`812` are recorded inconsistently between area and production modules,
  and ~116 plots list coffee twice (a generic `810` area *and* a `811`/`812` area with an
  identical value). These rows are flagged, not deleted.

---

## How to analyse the crops

- **Each crop separately:** filter `crop_name == "Maize"` (or "Beans", or "Coffee") and
  work within that subset. For maize/beans, analyse `crop_yield_kg_ha` vs seed /
  fertilizer / credit.
- **Comparing crops appropriately:** maize and beans are annual grains/legumes and can be
  compared (e.g. a crop fixed effect in a pooled model). **Coffee is perennial and its
  yield is not comparable** — model coffee separately, or model credit/cropping decisions
  (not yield) if pooling all three.
- **Credit rates:** compute borrowing rates using **unique households**
  (`household_borrowed` / `agricultural_loan` at the household level), not repeated crop
  rows. The `Crop_Summary` sheet already does this.
- **Survey weights:** all statistics here are **unweighted sample statistics**. Use UNPS
  survey weights (e.g. from `AGSEC1.csv` / `pov2018_19.csv`) only when the correct weight
  and design are applied.

---

## Reproducing the dataset

From anywhere (paths are resolved relative to the script):

```bash
python AgriCredit_Yield_Analysis/Combined_Crops/prepare_three_crops.py
```

The script only reads the raw CSVs and writes `UNPS_AgriCredit_Three_Crops.xlsx`.
