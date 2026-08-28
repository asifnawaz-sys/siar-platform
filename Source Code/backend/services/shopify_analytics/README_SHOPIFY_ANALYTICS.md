# Shopify Analytics Dashboard Generator (offline)

Turn a Shopify **Orders export** and **Products export** into a complete, formula-driven
Excel analytics workbook — locally, on your own PC. No cloud upload, no tokens.

The workbook it builds is identical to the one produced before: 14 sheets (Cover, Dashboard
with 14 charts, Data Audit, and 8 calculation sheets) + the two raw-data sheets. Cancelled
orders are excluded from every KPI, table and chart, and shown separately for reference.

---

## Two tools in one app: Analytics + Reconciliation

The dashboard app (`Shopify_Dashboard_App.html`) now has two tabs in the top bar:

* **Analytics** — the original tool, unchanged. Everything runs client-side in your browser.
* **Reconciliation** — upload a **Reference CSV** and a **Final CSV** and get back the same
  Excel report + PowerPoint as the standalone Reconciliation app (product-by-product,
  field-by-field, plus a dashboard built from the Final CSV). This tab is powered by the
  existing `recon_app.py` code, run by a tiny **local** helper (`server.py`) — nothing is
  uploaded anywhere; it listens on `127.0.0.1` only.

### Launch the full app (both tabs)

Double-click **`Run App (Analytics + Reconciliation).bat`**. It starts the local helper and
opens the app in your browser. Keep that console window open while you use the app.
First run installs `pandas`, `openpyxl`, `python-pptx` automatically.

> The Analytics tab also still works by opening `Shopify_Dashboard_App.html` directly, and the
> classic CSV-picker generator still runs via `Run (pick files).bat`. The **Reconciliation**
> tab needs the helper, so use `Run App (Analytics + Reconciliation).bat` for that.

*Created by Asif Nawaz.*

---

## What makes it "intelligent"

* **Columns are matched by header NAME, not position.** Reorder or rename your export columns
  (e.g. `Total` → `Total Price`, `Shipping Country` → `Country`, `Lineitem quantity` → `Quantity`)
  and it still maps them correctly. It uses alias lists + token/contains matching.
* **Missing columns degrade gracefully.** No discount column? Discounts read 0. No `Cancelled at`?
  All orders count as confirmed. It never crashes on a leaner export.
* **Everything stays formula-driven.** KPIs, tables and charts are live Excel formulas over
  Excel Tables (`tblOrders` / `tblProducts`), so the file recalculates itself.

---

## How to use

### Option A — double-click (easiest)
Double-click **`Run (pick files).bat`**. Three dialogs appear:
1. choose your **Orders** export CSV
2. choose your **Products** export CSV
3. choose where to save the `.xlsx`

### Option B — command line
```
python shopify_analytics_app.py  ORDERS.csv  PRODUCTS.csv  -o  Output.xlsx
```
Add `--open` to open the workbook automatically when it finishes.

Running with **no arguments** also opens the file-picker dialogs:
```
python shopify_analytics_app.py
```

---

## One-time setup

1. Install **Python 3.9+** from https://python.org (tick "Add Python to PATH" during install).
2. Install the two libraries it needs (one time):
   ```
   pip install pandas openpyxl
   ```
3. *(Optional)* Install **LibreOffice** (free). If present, the app pre-computes all formula
   values so the file shows numbers in any viewer. **If you don't have it, nothing is lost** —
   Excel calculates every formula automatically the moment you open the file.

---

## What you get (sheets)

| Sheet | Contents |
|---|---|
| **Cover** | Navigation, assumptions, refresh instructions |
| **Dashboard** | 10 KPI cards + 14 charts (revenue trend, orders, cumulative, local/intl, country, category, top cities, top products, price buckets, size, customers, quarterly, units) |
| **Data_Audit** | 26 validation checks + reconciliation + cancelled-orders reference list |
| **Calc_KPI** | Every headline KPI (single source of truth) |
| **Calc_Monthly** | Monthly orders/revenue/units, MoM growth, running totals, 3/6-mo MA, forecast |
| **Calc_Trend** | Daily / weekly / quarterly / yearly |
| **Calc_Geography** | Local vs International, country-wise, Pakistan city analysis |
| **Calc_Products** | Category, vendor, product master, top/bottom rankings, contribution |
| **Calc_Attributes** | Size, colour, variant, price buckets, basket |
| **Calc_Customers** | New/returning, repeat rate, CLV proxy, top customers |
| **Calc_Business** | Discounts, shipping, weekday/peaks, business KPIs, outliers |
| **Raw_Orders / Raw_Products** | Your source data + auto-generated helper columns (Excel Tables) |

---

## Business rules & assumptions

* **Confirmed order** = `Cancelled at` is blank. Cancelled orders are excluded everywhere.
* **Order revenue** = order `Total` (incl. shipping, net discounts).
  **Product / category / size revenue** = line merchandise value (`price × qty`).
* **Product category** = `Type` if present, otherwise the last segment of the Google
  Product Category taxonomy (e.g. "Dresses", "Outfit Sets").
* **Products are matched to orders by Title** (order-line SKUs are frequently blank).
  Unmatched lines show as `Unmapped`.
* **Size** is parsed from the `Product - Size` line-item name; **colour** is best-effort from
  the product colour metafield.
* **Customer** = lowercased email; orders without an email are grouped as `(guest)` and
  excluded from customer counts (their revenue/units are still included).
* **Local** = Shipping Country `PK`; **International** = everything else.

---

## Refreshing later

Just run the app again on the new exports — it rebuilds the whole workbook. Or, inside an
existing file, paste new rows under the header in `Raw_Orders` / `Raw_Products`; the Tables
expand and every KPI/chart recalculates.

---

## Troubleshooting

* **"python is not recognized"** → Python isn't on PATH; reinstall and tick "Add to PATH", or
  run with the full path to `python.exe`.
* **"No module named pandas/openpyxl"** → run `pip install pandas openpyxl`.
* **The file opens with blank cells** → you don't have LibreOffice; just open it in Excel and
  it calculates automatically (or press `Ctrl+Alt+F9`).
* **A column wasn't detected** → the console prints the full mapping; check the `[--]` lines and
  rename that header in your CSV to a standard Shopify name (or tell me the header and I'll add
  it to the alias list).
