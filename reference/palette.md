# APEX Color Palette Reference — Toronto Shelter Analytics

Extracted from `apex_app_export.sql` (exported 2026-05-15, app 101, page 4 "Historical Trends").
Colors marked **auto** are not set explicitly in the export — APEX assigns them from the Universal Theme
JET chart palette. Miriam should confirm these visually against the live APEX dashboard before finalizing.

---

## Historical Trends — Page 4

### Chart 1 · Actively Homeless (line)

| Series | Hex | Notes |
|--------|-----|-------|
| Actively Homeless | `#FF2D55` | Explicit `p_color` on series |

Marker size is 0.125 (near-invisible dots via JS override — the line dominates).
Legend is **off** (single series, label implied by chart title).

---

### Chart 2 · Net Change (line)

| Series | Hex | Notes |
|--------|-----|-------|
| Net Change | **auto** | No `p_color` set — APEX uses first palette color |

Formula: `newly_identified + returned_from_housing + returned_to_shelter − moved_to_housing − became_inactive`
Y-axis: decimal, 0 decimal places, zero baseline (rule at y=0 is important for readability).
Legend is **off**.

---

### Chart 3 · Age Composition (multi-line, % of age-banded total)

No explicit colors set — APEX assigns them in series order from the JET palette.
Series rendered in alphabetical order by age_band value (APEX `ORDER BY 1, 2`):

| # | Age Band | Hex | Notes |
|---|----------|-----|-------|
| 1 | 16–24 | **auto** | First in alpha sort |
| 2 | 25–34 | **auto** | |
| 3 | 35–44 | **auto** | |
| 4 | 45–54 | **auto** | |
| 5 | 55–64 | **auto** | |
| 6 | 65+ | **auto** | |
| 7 | Under 16 | **auto** | Last in alpha sort ("U" > digits) |

Denominator: sum of all seven age bands (not `actively_homeless`).
Y-axis: percent format, 0 decimal places. Legend rendered at **bottom**.

**Action required: Miriam to confirm exact colors against APEX dashboard.**

---

### Chart 4 · Gender Composition (multi-line, % of gender total)

No explicit colors set. Series in alphabetical order:

| # | Category | Hex | Notes |
|---|----------|-----|-------|
| 1 | Men | **auto** | |
| 2 | Transgender, Non-Binary, or Two-Spirit | **auto** | Long label — legend may truncate |
| 3 | Women | **auto** | |

Denominator: `gender_male + gender_female + gender_trans_nb_two_spirit`.
Y-axis: percent format. Legend rendered at **bottom**.

**Action required: Miriam to confirm exact colors against APEX dashboard.**

---

### Chart 5 · Total Inflow and Outflow (stacked/mirrored bar)

| Series | Hex | Direction |
|--------|-----|-----------|
| Inflow | `#E63946` | Positive (above zero) |
| Outflow | `#66CC66` | Negative (below zero, stored as `-1 * total`) |

Stack mode **on**. Legend at **bottom**.

---

### Chart 6 · Detailed Inflow and Outflow (stacked mirrored bar, 5 series)

Colors are embedded per-row in the SQL as `color_val` and bound via `p_color=>'&COLOR_VAL.'`.

| Series Name (FLOW_TYPE) | Hex | Direction |
|------------------------|-----|-----------|
| Inflow - Newly Identified | `#E63946` | Positive |
| Inflow - Returned from Permanent Housing | `#FFD600` | Positive |
| Inflow - Returned to Shelter | `#FB8C00` | Positive |
| Outflow - Became Inactive | `#512DA8` | Negative (stored as `−1 × became_inactive`) |
| Outflow - Moved to Permanent Housing | `#66CC66` | Negative (stored as `−1 × moved_to_housing`) |

Stack mode **on**. Legend at **bottom**.
Series ordering in stacked bars follows alphabetical FLOW_TYPE sort (ORDER BY 1, 3) — but visual stacking order is determined by series index, not alphabetical.

---

## Filter Dropdowns (all single-select, not multi-select)

| Item | Default | Values |
|------|---------|--------|
| P3_POPULATION_GROUP | `All Population` | Dynamic: `SELECT DISTINCT population_group … ORDER BY population_group` |
| P3_YEAR | `All` | `All` + distinct years from DB, ascending |
| P3_MONTH | `All` | `All` + January through December (display), `1`–`12` (return value) |

---

## Monthly Snapshot — Page 2

### KPI Cards

| Card | Background | Text Hex | Notes |
|------|-----------|----------|-------|
| Inflow | `#FBE4EB` | `#C2185B` | Always pink |
| Net Change (positive) | `#FFEBEE` | `#C62828` | Red = more homeless |
| Net Change (negative) | `#E8F5E9` | `#2E7D32` | Green = fewer homeless |
| Net Change (zero) | `#E8E8E8` | `#333333` | Neutral |
| Outflow | `#E8F5E9` | `#2E7D32` | Always green |

### YTD Comparison Charts (appear on both Monthly Snapshot and YTD Comparison pages)

| Series | Hex | Semantic |
|--------|-----|----------|
| Newly Identified — current year | `#FF2D55` | Matches Actively Homeless line color |
| Newly Identified — prior year | `#FFB3C1` | Light pink, same hue |
| Moved to Housing — current year | `#5BA75B` | Darker green |
| Moved to Housing — prior year | `#AED5AE` | Light green |

---

## Colors Used Elsewhere in the App

| Location | Hex | Semantic |
|----------|-----|----------|
| Monthly Snapshot — donut (Chronic share) | `#5856D6` | Chronic share of total |
| Monthly Snapshot — donut (remainder) | `#CCCCCC` | Other population groups |
| KPI value box background | `#E8E8E8` | Neutral card background |
| KPI value text | `#333333` | Dark text |
| KPI label text | `#666666` | Muted label |
| YTD bar chart (color-coded by year) | dynamic | Color assigned per year in SQL CASE |
