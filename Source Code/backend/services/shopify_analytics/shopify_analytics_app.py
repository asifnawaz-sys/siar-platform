#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shopify Orders & Products -> Analytics Dashboard  (offline generator)
=====================================================================
Feed it a Shopify ORDERS export CSV and a Shopify PRODUCTS export CSV; it writes a
fully formula-driven Excel analytics workbook (KPIs, monthly/trend, geography,
products, attributes, customers, business, data audit, dashboard with charts).

Columns are matched by HEADER NAME (alias + fuzzy), never by position, so it works
across brands/stores. Cancelled orders are excluded from all analytics.

USAGE
  Double-click / no args ...... a file picker asks for the two CSVs + output path
  python shopify_analytics_app.py ORDERS.csv PRODUCTS.csv [-o OUTPUT.xlsx] [--open]

REQUIREMENTS
  pip install pandas openpyxl
  (LibreOffice optional: if found, values are pre-computed; otherwise Excel
   computes every formula automatically the moment you open the file.)
"""
import os, sys, re, argparse, subprocess, tempfile, shutil, pathlib
from datetime import date, timedelta

try:
    import pandas as pd
except ImportError:
    sys.exit("Missing dependency: pandas.  Run:  pip install pandas openpyxl")
try:
    import openpyxl
    from openpyxl.utils import get_column_letter, column_index_from_string
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.chart import BarChart, LineChart, PieChart, DoughnutChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.text import RichText
    from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.series import DataPoint
    from openpyxl.worksheet.properties import PageSetupProperties
except ImportError:
    sys.exit("Missing dependency: openpyxl.  Run:  pip install pandas openpyxl")

# =====================================================================
# 1.  COLUMN RESOLVER  (header-name based, brand-agnostic)
# =====================================================================
def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s).lower())).strip()

# canonical field -> list of acceptable header aliases (order = priority)
ORDER_ALIASES = {
    "name":            ["name", "order name", "order", "order id", "order number", "order no"],
    "email":           ["email", "contact email", "customer email"],
    "financial_status":["financial status", "payment status", "financial"],
    "total":           ["total", "total price", "order total", "grand total"],
    "subtotal":        ["subtotal", "subtotal price", "sub total"],
    "shipping":        ["shipping", "shipping price", "shipping amount", "shipping total"],
    "taxes":           ["taxes", "tax", "total tax"],
    "discount_amount": ["discount amount", "discount", "total discount", "discounts", "discount value"],
    "discount_code":   ["discount code", "discount codes", "coupon", "coupon code"],
    "created_at":      ["created at", "created", "order date", "processed at", "date", "opened at"],
    "lineitem_qty":    ["lineitem quantity", "line item quantity", "item quantity", "quantity", "qty"],
    "lineitem_name":   ["lineitem name", "line item name", "item name", "product name", "product"],
    "lineitem_price":  ["lineitem price", "line item price", "item price", "unit price", "price"],
    "lineitem_sku":    ["lineitem sku", "line item sku", "item sku", "sku"],
    "lineitem_compare":["lineitem compare at price", "compare at price"],
    "lineitem_discount":["lineitem discount", "line item discount"],
    "ship_city":       ["shipping city", "ship city", "delivery city", "city"],
    "ship_country":    ["shipping country", "ship country", "delivery country", "country", "shipping country code"],
    "ship_province":   ["shipping province", "shipping province name", "shipping state", "province", "state"],
    "billing_city":    ["billing city", "bill city"],
    "billing_country": ["billing country", "bill country", "billing country code"],
    "cancelled_at":    ["cancelled at", "canceled at", "cancelled", "canceled", "cancellation date"],
    "vendor":          ["vendor", "brand", "supplier"],
    "currency":        ["currency", "presentment currency"],
}
PRODUCT_ALIASES = {
    "handle":          ["handle", "product handle", "url handle"],
    "title":           ["title", "product title", "product name", "name"],
    "vendor":          ["vendor", "brand", "supplier"],
    "product_category":["product category", "google shopping google product category",
                        "google product category", "standard product type", "category"],
    "type":            ["type", "product type", "custom product type"],
    "variant_sku":     ["variant sku", "sku"],
    "variant_price":   ["variant price", "price"],
    "variant_compare": ["variant compare at price", "compare at price"],
    "option1_name":    ["option1 name", "option 1 name"],
    "option1_value":   ["option1 value", "option 1 value"],
    "option2_name":    ["option2 name", "option 2 name"],
    "option2_value":   ["option2 value", "option 2 value"],
    "color_metafield": ["color product metafields shopify color pattern", "colour product metafields shopify color pattern",
                        "color", "colour", "color pattern", "colour pattern"],
    "size_metafield":  ["size product metafields shopify size", "size"],
    "status":          ["status"],
}
# fields whose values must be numeric in the sheet
NUMERIC_ORDER  = {"total","subtotal","shipping","taxes","discount_amount","lineitem_qty",
                  "lineitem_price","lineitem_compare","lineitem_discount"}
NUMERIC_PRODUCT= {"variant_price","variant_compare"}

def resolve(headers, alias_map):
    """Return {field: header_name or None} plus a report list."""
    norm_headers = {norm(h): h for h in headers}   # normalized -> original (first wins)
    used = set(); out = {}; report = []
    for field, aliases in alias_map.items():
        found = None
        # 1) exact normalized alias match
        for al in aliases:
            na = norm(al)
            if na in norm_headers and norm_headers[na] not in used:
                found = norm_headers[na]; break
        # 2) token-subset / contains match (e.g. long metafield headers)
        if not found:
            for al in aliases:
                na = norm(al); na_tokens = set(na.split())
                for nh, oh in norm_headers.items():
                    if oh in used: continue
                    # keep shipping/billing fields from stealing each other's columns
                    if field.startswith("ship") and "billing" in nh: continue
                    if field.startswith("billing") and ("shipping" in nh or "ship " in nh): continue
                    if na and (na in nh or na_tokens.issubset(set(nh.split()))):
                        found = oh; break
                if found: break
        if found:
            used.add(found); report.append(("OK", field, found))
        else:
            report.append(("--", field, None))
        out[field] = found
    return out, report

# =====================================================================
# 2.  Excel-equivalent text helpers (so Python dim labels == formula output)
# =====================================================================
def xtrim(s):
    return re.sub(r"\s+", " ", str(s)).strip()

def xproper(s):
    out=[]; prev_alpha=False
    for ch in str(s):
        if ch.isalpha():
            out.append(ch.lower() if prev_alpha else ch.upper()); prev_alpha=True
        else:
            out.append(ch); prev_alpha=False
    return "".join(out)

def norm_size(raw):
    if raw is None or str(raw).strip()=="":
        return "(No Size)"
    u = str(raw).strip().upper()
    if u in ("XS","EXTRA SMALL","XSMALL"): return "Extra Small"
    if u in ("S","SMALL"): return "Small"
    if u in ("M","MEDIUM"): return "Medium"
    if u in ("L","LARGE"): return "Large"
    if u in ("XL","EXTRA LARGE"): return "XL"
    if u == "XXL": return "XXL"
    if u == "XXXL": return "XXXL"
    return "Other"

def split_name(nm):
    nm = str(nm)
    if " - " in nm:
        base, sz = nm.rsplit(" - ", 1)
        return xtrim(base), sz.strip()
    return xtrim(nm), ""

def last_segment(cat):
    cat = str(cat)
    if ">" in cat:
        seg = cat.split(">")[-1].strip()
        return seg if seg else "Uncategorized"
    return cat.strip() if cat.strip() else "Uncategorized"

def category_final(type_val, prodcat_val):
    if str(type_val).strip(): return str(type_val).strip()
    if str(prodcat_val).strip(): return last_segment(prodcat_val)
    return "Uncategorized"

def excel_weeknum2(d):
    jan1 = date(d.year,1,1)
    week1_start = jan1 - timedelta(days=jan1.weekday())   # Monday of week containing Jan 1
    return (d - week1_start).days // 7 + 1

WEEKDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

# =====================================================================
# 3.  LOAD + ENRICH (pandas) -> dims, controls, cancelled list
# =====================================================================
def read_csv(path):
    for enc in ("utf-8-sig","utf-8","latin-1"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
        except (UnicodeDecodeError, Exception):
            continue
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="latin-1", engine="python")

def to_num(x):
    try:
        return float(str(x).replace(",","")) if str(x).strip()!="" else None
    except ValueError:
        return None

def enrich(orders_df, products_df, OC, PC):
    # ---- product title -> category / vendor / color map ----
    def pcol(df, field):
        h = PC.get(field); return df[h] if h else pd.Series([""]*len(df))
    p = pd.DataFrame({
        "handle": pcol(products_df,"handle"),
        "title":  pcol(products_df,"title"),
        "vendor": pcol(products_df,"vendor"),
        "prodcat":pcol(products_df,"product_category"),
        "ptype":  pcol(products_df,"type"),
        "color":  pcol(products_df,"color_metafield"),
    })
    # fill down product-level fields within a product (handle groups if present else identity)
    if PC.get("handle"):
        gid = (p["handle"] != p["handle"].shift()).cumsum()
        for c in ["title","vendor","prodcat","ptype","color"]:
            p[c] = p[c].replace("", pd.NA)
            p[c] = p.groupby(gid)[c].transform(lambda s: s.ffill())
            p[c] = p[c].fillna("")
    p["cat_final"] = [category_final(t,pc) for t,pc in zip(p["ptype"], p["prodcat"])]
    p["color_first"] = [xproper(str(c).split(";")[0].strip()) if str(c).strip() else "" for c in p["color"]]
    title_cat, title_ven, title_col = {}, {}, {}
    for t,cf,v,co in zip(p["title"], p["cat_final"], p["vendor"], p["color_first"]):
        if str(t).strip() and t not in title_cat:
            title_cat[t]=cf; title_ven[t]=v; title_col[t]=co

    # ---- orders ----
    def ocol(field):
        h = OC.get(field); return orders_df[h] if h else pd.Series([""]*len(orders_df))
    o = pd.DataFrame({f: ocol(f) for f in OC})
    if OC.get("name") is None:
        raise ValueError("Could not find an order identifier column (e.g. 'Name') in the orders file.")
    o["_name"] = o["name"]
    gid = (o["_name"] != o["_name"].shift()).cumsum()
    o["_first"] = (o["_name"] != o["_name"].shift())
    # fill-down order-level fields
    for f in ["total","subtotal","shipping","discount_amount","cancelled_at","financial_status",
              "ship_city","ship_country","billing_city","billing_country","email","discount_code"]:
        if f in o.columns:
            s = o[f].replace("", pd.NA)
            o[f] = o.groupby(gid)[s.name].transform(lambda x: x.ffill()).fillna("") if False else \
                   s.groupby(gid).transform("first").fillna("")
    # numeric
    for f in ["total","subtotal","shipping","discount_amount","lineitem_qty","lineitem_price"]:
        if f in o.columns: o[f+"_n"] = o[f].map(to_num)
        else: o[f+"_n"] = None
    # confirmed = NOT cancelled (Cancelled at blank) AND financial status not refunded/voided
    if OC.get("cancelled_at"):
        not_cancelled = o["cancelled_at"].astype(str).str.strip().eq("")
    else:
        not_cancelled = pd.Series([True]*len(o), index=o.index)
    if "financial_status" in o.columns:
        fs = o["financial_status"].astype(str).str.strip().str.lower()
        not_refund_void = ~fs.isin(["refunded", "voided"])
    else:
        not_refund_void = pd.Series([True]*len(o), index=o.index)
    o["_confirmed"] = not_cancelled & not_refund_void
    # date parts
    def parse_date(s):
        s=str(s).strip()
        if len(s)>=10:
            try: return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
            except Exception: return None
        return None
    o["_date"] = o["created_at"].map(parse_date) if "created_at" in o.columns else None
    o["_ym"]   = o["_date"].map(lambda d: d.strftime("%Y-%m") if d else "")
    o["_qtr"]  = o["_date"].map(lambda d: f"{d.year}-Q{(d.month-1)//3+1}" if d else "")
    o["_year"] = o["_date"].map(lambda d: d.year if d else "")
    o["_week"] = o["_date"].map(lambda d: f"{d.year}-W{excel_weeknum2(d):02d}" if d else "")
    o["_wd"]   = o["_date"].map(lambda d: WEEKDAYS[d.weekday()] if d else "")
    o["_dt"]   = o["_date"].map(lambda d: d.isoformat() if d else "")
    # geography
    # geography from BILLING city/country (fallback to shipping when billing is absent/blank)
    def geo_pref(bfield, sfield):
        b = o[bfield] if bfield in o.columns else pd.Series([""]*len(o))
        s = o[sfield] if sfield in o.columns else pd.Series([""]*len(o))
        return [ (str(bv).strip() or str(sv).strip()) for bv,sv in zip(b,s) ]
    ctry = pd.Series(geo_pref("billing_country","ship_country"))
    o["_local"] = ctry.astype(str).str.strip().eq("PK")
    o["_ctry"]  = ctry.astype(str).str.strip()
    city = geo_pref("billing_city","ship_city")
    o["_city"] = [xproper(xtrim(c)) if str(c).strip() else "" for c in city]
    # size / product
    names = o["lineitem_name"] if "lineitem_name" in o.columns else pd.Series([""]*len(o))
    bt, sz = zip(*[split_name(n) for n in names]) if len(o) else ([],[])
    o["_base"] = list(bt); o["_size"] = [norm_size(s) for s in sz]
    o["_cat"] = [title_cat.get(b, "Unmapped") for b in o["_base"]]
    o["_color"] = [title_col.get(b, "") for b in o["_base"]]
    # customer key
    em = o["email"] if "email" in o.columns else pd.Series([""]*len(o))
    o["_cust"] = [ (str(e).strip().lower() if str(e).strip() else "(guest)") for e in em ]

    fc = o["_first"] & o["_confirmed"]        # confirmed order header rows
    lc = o["_confirmed"]                       # confirmed line rows

    def dist(series, mask):
        vals = [v for v,m in zip(series, mask) if m and str(v).strip()!=""]
        return sorted(set(vals))

    dims = {
        "months":   dist(o["_ym"], fc),
        "quarters": dist(o["_qtr"], fc),
        "years":    [int(y) for y in dist(o["_year"], fc)],
        "weeks":    dist(o["_week"], fc),
        "weekdays": [w for w in WEEKDAYS if w in set(dist(o["_wd"], fc))],
        "dates":    dist(o["_dt"], fc),
        "countries":dist(o["_ctry"], fc),
        "cities":   dist(o["_city"], o["_first"] & o["_confirmed"] & o["_local"]),
        "cats":     dist(o["_cat"], lc),
        "products": dist(o["_base"], lc),
        "customers":[c for c in dist(o["_cust"], fc) if c != "(guest)"],
        "vendors":  dist(pd.Series([title_ven.get(b, OC.get("vendor") and o["vendor"].iloc[i] or "Unmapped")
                                    for i,b in enumerate(o["_base"])]), lc),
        "colors":   dist(o["_color"], lc),
        "variants": dist(names, lc),
    }
    # controls (for validation print)
    n = lambda s: pd.to_numeric(pd.Series(s), errors="coerce").fillna(0)
    ctrl = {
        "conf_orders": int(fc.sum()),
        "canc_orders": int((o["_first"] & ~o["_confirmed"]).sum()),
        "total_rev":  round(float(n(o["total_n"])[fc].sum()),2),
        "merch_rev":  round(float((n(o["lineitem_price_n"])*n(o["lineitem_qty_n"]))[lc].sum()),2),
        "units":      int(n(o["lineitem_qty_n"])[lc].sum()),
        "customers":  len(dims["customers"]),
        "cancelled":  [nm for nm,f,c in zip(o["_name"], o["_first"], o["_confirmed"]) if f and not c],
    }
    cur = ""
    if OC.get("currency"):
        vals=[v for v in o["currency"] if str(v).strip()]
        cur = max(set(vals), key=vals.count) if vals else ""
    return dims, ctrl, cur

# =====================================================================
# 4.  STYLE HELPERS
# =====================================================================
FN="Arial"; NAVY="1F3864"; BLUE="305496"; TEAL="1F6F54"; LIGHT="D9E1F2"; GREY="F2F2F2"
thin=Side(style="thin",color="BFBFBF"); BORDER=Border(left=thin,right=thin,top=thin,bottom=thin)
CUR='#,##0'; PCT='0.0%'; INT='#,##0'; DEC1='#,##0.0'
def Fnt(sz=10,b=False,color="000000",italic=False): return Font(name=FN,size=sz,bold=b,color=color,italic=italic)
def fill(h): return PatternFill("solid",fgColor=h)
def title(ws,text,sub=None):
    ws["A1"]=text; ws["A1"].font=Fnt(18,True,NAVY)
    if sub: ws["A2"]=sub; ws["A2"].font=Fnt(10,False,"808080",italic=True)
def section(ws,row,text,span=8):
    c=ws.cell(row,1,text); c.font=Fnt(12,True,"FFFFFF")
    for i in range(1,span+1): ws.cell(row,i).fill=fill(NAVY)
    ws.cell(row,1).font=Fnt(12,True,"FFFFFF"); return row
def headers(ws,row,hdrs,startcol=1,fillc=BLUE):
    for i,h in enumerate(hdrs):
        c=ws.cell(row,startcol+i,h); c.font=Fnt(10,True,"FFFFFF"); c.fill=fill(fillc)
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=BORDER
    return row
def mini_header(ws,row,col,text,span):
    ws.cell(row,col,text).font=Fnt(12,True,"FFFFFF")
    for i in range(col,col+span): ws.cell(row,i).fill=fill(NAVY)
    ws.cell(row,col).font=Fnt(12,True,"FFFFFF")
def widths(ws,w):
    for i,x in enumerate(w,1): ws.column_dimensions[get_column_letter(i)].width=x

# =====================================================================
# 5.  RAW SHEETS + HELPER COLUMNS
# =====================================================================
HDR_FILL=fill(BLUE); HELPER_FILL=fill(TEAL)
def write_raw(ws, df, numeric_idx):
    for c,h in enumerate(df.columns,1):
        cell=ws.cell(1,c,h); cell.font=Fnt(10,True,"FFFFFF"); cell.fill=HDR_FILL
        cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
    for r,(_,row) in enumerate(df.iterrows(),2):
        for c,val in enumerate(row,1):
            v = to_num(val) if (c-1) in numeric_idx else (val if val!="" else None)
            if v is not None:
                cell=ws.cell(r,c,v); cell.font=Fnt(10)
    return len(df.columns)

def add_helper_header(ws,idx,name):
    cell=ws.cell(1,idx,name); cell.font=Fnt(10,True,"FFFFFF"); cell.fill=HELPER_FILL
    cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
    return get_column_letter(idx)

def build_raw_products(wb, df, PC):
    ws=wb.create_sheet("Raw_Products")
    numeric_idx={i for i,h in enumerate(df.columns) if any(PC.get(f)==h for f in NUMERIC_PRODUCT)}
    ncols=write_raw(ws, df, numeric_idx); nrows=len(df)+1
    def L(field):
        h=PC.get(field); return get_column_letter(list(df.columns).index(h)+1) if h else None
    H=L("handle"); T=L("title"); V=L("vendor"); C=L("product_category"); TY=L("type"); CO=L("color_metafield")
    PSKU=L("variant_sku"); PPRICE=L("variant_price")
    names=["Title_F","Vendor_F","Type_F","Category_F","Category_Short","Category_Final","Color_F","Color_First",
           "Handle_K","SKU_K","Price_K","Type_K"]
    HL={}
    for i,nm in enumerate(names): HL[nm]=add_helper_header(ws,ncols+1+i,nm)
    grp = H if H else T                       # group key for fill-down
    for r in range(2,nrows+1):
        a=r-1
        tsrc=f"{T}{r}" if T else '""'
        vsrc=f"{V}{r}" if V else '""'
        tysrc=f"{TY}{r}" if TY else '""'
        csrc=f"{C}{r}" if C else '""'
        cosrc=f"{CO}{r}" if CO else '""'
        grpr=f"{grp}{r}" if grp else f'ROW()'
        grpa=f"{grp}{a}" if grp else f'ROW()-1'
        ws[f"{HL['Title_F']}{r}"]   = f'=IF({tsrc}<>"",{tsrc},IF({grpr}={grpa},{HL["Title_F"]}{a},""))'
        ws[f"{HL['Vendor_F']}{r}"]  = f'=IF({vsrc}<>"",{vsrc},IF({grpr}={grpa},{HL["Vendor_F"]}{a},""))'
        ws[f"{HL['Type_F']}{r}"]    = f'=IF({tysrc}<>"",{tysrc},IF({grpr}={grpa},{HL["Type_F"]}{a},""))'
        ws[f"{HL['Category_F']}{r}"]= f'=IF({csrc}<>"",{csrc},IF({grpr}={grpa},{HL["Category_F"]}{a},""))'
        ws[f"{HL['Category_Short']}{r}"]=f'=IF(TRIM({HL["Category_F"]}{r})="","Uncategorized",TRIM(RIGHT(SUBSTITUTE({HL["Category_F"]}{r},">",REPT(" ",200)),200)))'
        ws[f"{HL['Category_Final']}{r}"]=f'=IF(TRIM({HL["Type_F"]}{r})<>"",TRIM({HL["Type_F"]}{r}),{HL["Category_Short"]}{r})'
        ws[f"{HL['Color_F']}{r}"]   = f'=IF({cosrc}<>"",{cosrc},IF({grpr}={grpa},{HL["Color_F"]}{a},""))'
        ws[f"{HL['Color_First']}{r}"]=f'=IF(TRIM({HL["Color_F"]}{r})="","",PROPER(TRIM(IFERROR(LEFT({HL["Color_F"]}{r},SEARCH(";",{HL["Color_F"]}{r})-1),{HL["Color_F"]}{r}))))'
        ws[f"{HL['Handle_K']}{r}"] = f'={H}{r}' if H else '=""'
        ws[f"{HL['SKU_K']}{r}"]    = f'={PSKU}{r}' if PSKU else '=""'
        ws[f"{HL['Price_K']}{r}"]  = f'=N({PPRICE}{r})' if PPRICE else '=0'
        ws[f"{HL['Type_K']}{r}"]   = f'={TY}{r}' if TY else '=""'
        for cc in range(ncols+1,ncols+1+len(names)): ws.cell(r,cc).font=Fnt(10)
    tab=Table(displayName="tblProducts", ref=f"A1:{get_column_letter(ncols+len(names))}{nrows}")
    tab.tableStyleInfo=TableStyleInfo(name="TableStyleLight9",showRowStripes=True); ws.add_table(tab)
    ws.freeze_panes="A2"
    return nrows

def build_raw_orders(wb, df, OC):
    ws=wb.create_sheet("Raw_Orders")
    numeric_idx={i for i,h in enumerate(df.columns) if any(OC.get(f)==h for f in NUMERIC_ORDER)}
    ncols=write_raw(ws, df, numeric_idx); nrows=len(df)+1
    def L(field):
        h=OC.get(field); return get_column_letter(list(df.columns).index(h)+1) if h else None
    N=L("name"); EM=L("email"); FS=L("financial_status"); TOT=L("total"); SUB=L("subtotal")
    SHP=L("shipping"); DA=L("discount_amount"); DC=L("discount_code"); CR=L("created_at")
    LQ=L("lineitem_qty"); LN=L("lineitem_name"); LP=L("lineitem_price"); SC=L("ship_city")
    SCO=L("ship_country"); CX=L("cancelled_at"); OV=L("vendor"); SK=L("lineitem_sku")
    BCITY=L("billing_city"); BCTRY=L("billing_country")
    if not N: raise ValueError("Orders file has no recognizable order-id column (e.g. 'Name').")
    helpers=["IsFirstLine","Cancelled_At_F","Financial_Status_F","Order_Total_F","Order_Subtotal_F",
        "Order_Shipping_F","Order_Discount_F","DiscCode_F","Ship_City_F","Ship_Country_F","Confirmed",
        "Order_Date","Year","Month_Num","YearMonth","Quarter","WeekLabel","Weekday","Region","Is_Local",
        "City_Clean","Size_Raw","Size","Base_Title","Prod_Row","Prod_Category","Prod_Vendor","Prod_Color",
        "Line_Revenue","Conf_Order_Rev","Conf_Order_NetRev","Conf_Order_Flag","Items_In_Order","Price_Bucket","Prod_First","Prod_Seq","Cust_Key",
        "Cust_Conf_Orders","Cust_FirstConf",
        "Cat_First","Cat_Seq","Ven_First","Ven_Seq","Col_First","Col_Seq","Var_First","Var_Seq",
        "City_MFirst","City_MSeq","Ctry_First","Ctry_Seq","Qtr_First","Qtr_Seq","Yr_First","Yr_Seq",
        "Wk_First","Wk_Seq","Dt_First","Dt_Seq","Cust_MFirst","Cust_MSeq","Canc_First","Canc_Seq",
        "Order_ID","Line_Name","Qty","Line_Price","Line_SKU","Email_K"]
    HL={}
    for i,h in enumerate(helpers): HL[h]=add_helper_header(ws,ncols+1+i,h)
    g=lambda k: HL[k]
    def cellref(Lx,r,fb='""'): return f"{Lx}{r}" if Lx else fb
    def fillcol(name, src, r, a, numeric=False):
        fb = '0' if numeric else '""'
        if not src: return f'={fb}'
        return f'=IF({src}{r}<>"",{src}{r},IF({N}{r}={N}{a},{g(name)}{a},{fb}))'
    def geofill(name, bcol, scol, r, a):
        # geography source: prefer BILLING, fall back to shipping, then fill down within the order
        if bcol and scol: src=f'IF({bcol}{r}<>"",{bcol}{r},{scol}{r})'
        elif bcol: src=f'{bcol}{r}'
        elif scol: src=f'{scol}{r}'
        else: return '=""'
        return f'=IF(({src})<>"",({src}),IF({N}{r}={N}{a},{g(name)}{a},""))'
    for r in range(2,nrows+1):
        a=r-1
        ws[f"{g('IsFirstLine')}{r}"]      = f'=IF({N}{r}<>{N}{a},1,0)'
        ws[f"{g('Cancelled_At_F')}{r}"]   = fillcol("Cancelled_At_F",CX,r,a) if CX else '=""'
        ws[f"{g('Financial_Status_F')}{r}"]=fillcol("Financial_Status_F",FS,r,a) if FS else '=""'
        ws[f"{g('Order_Total_F')}{r}"]    = fillcol("Order_Total_F",TOT,r,a,True) if TOT else '=0'
        ws[f"{g('Order_Subtotal_F')}{r}"] = fillcol("Order_Subtotal_F",SUB,r,a,True) if SUB else '=0'
        ws[f"{g('Order_Shipping_F')}{r}"] = fillcol("Order_Shipping_F",SHP,r,a,True) if SHP else '=0'
        ws[f"{g('Order_Discount_F')}{r}"] = fillcol("Order_Discount_F",DA,r,a,True) if DA else '=0'
        ws[f"{g('DiscCode_F')}{r}"]       = fillcol("DiscCode_F",DC,r,a) if DC else '=""'
        ws[f"{g('Ship_City_F')}{r}"]      = geofill("Ship_City_F",BCITY,SC,r,a)
        ws[f"{g('Ship_Country_F')}{r}"]   = geofill("Ship_Country_F",BCTRY,SCO,r,a)
        ws[f"{g('Confirmed')}{r}"]        = (f'=IF(AND(TRIM({g("Cancelled_At_F")}{r})="",'
                                             f'LOWER(TRIM({g("Financial_Status_F")}{r}))<>"refunded",'
                                             f'LOWER(TRIM({g("Financial_Status_F")}{r}))<>"voided"),1,0)')
        crsrc = cellref(CR,r)
        ws[f"{g('Order_Date')}{r}"]       = (f'=IFERROR(DATE(VALUE(LEFT({crsrc},4)),VALUE(MID({crsrc},6,2)),VALUE(MID({crsrc},9,2))),"")'
                                             if CR else '=""')
        OD=f'{g("Order_Date")}{r}'
        ws[f"{g('Year')}{r}"]     = f'=IFERROR(YEAR({OD}),"")'
        ws[f"{g('Month_Num')}{r}"]= f'=IFERROR(MONTH({OD}),"")'
        ws[f"{g('YearMonth')}{r}"]= f'=IFERROR(TEXT({OD},"YYYY-MM"),"")'
        ws[f"{g('Quarter')}{r}"]  = f'=IFERROR(TEXT({OD},"YYYY")&"-Q"&ROUNDUP(MONTH({OD})/3,0),"")'
        ws[f"{g('WeekLabel')}{r}"]= f'=IFERROR(TEXT({OD},"YYYY")&"-W"&TEXT(WEEKNUM({OD},2),"00"),"")'
        ws[f"{g('Weekday')}{r}"]  = f'=IFERROR(TEXT({OD},"ddd"),"")'
        ws[f"{g('Region')}{r}"]   = f'=IF({g("Ship_Country_F")}{r}="","Unknown",IF({g("Ship_Country_F")}{r}="PK","Local","International"))'
        ws[f"{g('Is_Local')}{r}"] = f'=IF({g("Ship_Country_F")}{r}="PK",1,0)'
        ws[f"{g('City_Clean')}{r}"]=f'=IF({g("Ship_City_F")}{r}="","",PROPER(TRIM({g("Ship_City_F")}{r})))'
        LNr=cellref(LN,r)
        ws[f"{g('Size_Raw')}{r}"] = (f'=IF(ISNUMBER(SEARCH(" - ",{LNr})),TRIM(RIGHT(SUBSTITUTE({LNr}," - ",REPT(" ",200)),200)),"")'
                                     if LN else '=""')
        SR=f'{g("Size_Raw")}{r}'; U=f'UPPER(TRIM({SR}))'
        ws[f"{g('Size')}{r}"] = (f'=IF({SR}="","(No Size)",IF(OR({U}="XS",{U}="EXTRA SMALL",{U}="XSMALL"),"Extra Small",'
            f'IF(OR({U}="S",{U}="SMALL"),"Small",IF(OR({U}="M",{U}="MEDIUM"),"Medium",'
            f'IF(OR({U}="L",{U}="LARGE"),"Large",IF(OR({U}="XL",{U}="EXTRA LARGE"),"XL",'
            f'IF({U}="XXL","XXL",IF({U}="XXXL","XXXL","Other")))))))) ')
        ws[f"{g('Base_Title')}{r}"] = (f'=IF({SR}="",{LNr},TRIM(LEFT({LNr},LEN({LNr})-LEN({SR})-3)))' if LN else '=""')
        BT=f'{g("Base_Title")}{r}'
        ws[f"{g('Prod_Row')}{r}"] = f'=IFERROR(MATCH({BT},tblProducts[Title_F],0),"")'
        PR=f'{g("Prod_Row")}{r}'
        ws[f"{g('Prod_Category')}{r}"]=f'=IF({PR}="","Unmapped",INDEX(tblProducts[Category_Final],{PR}))'
        ovsrc=cellref(OV,r,'"Unmapped"')
        ws[f"{g('Prod_Vendor')}{r}"]=f'=IF({PR}="",{ovsrc},INDEX(tblProducts[Vendor_F],{PR}))'
        ws[f"{g('Prod_Color')}{r}"]=f'=IF({PR}="","",INDEX(tblProducts[Color_First],{PR}))'
        lpsrc=cellref(LP,r,'0'); lqsrc=cellref(LQ,r,'0')
        ws[f"{g('Line_Revenue')}{r}"]=f'=IFERROR(N({lpsrc})*N({lqsrc}),0)'
        ws[f"{g('Conf_Order_Rev')}{r}"]=f'=IF(AND({g("IsFirstLine")}{r}=1,{g("Confirmed")}{r}=1),N({g("Order_Total_F")}{r}),0)'
        ws[f"{g('Conf_Order_NetRev')}{r}"]=f'=IF(AND({g("IsFirstLine")}{r}=1,{g("Confirmed")}{r}=1),N({g("Order_Total_F")}{r})-N({g("Order_Shipping_F")}{r}),0)'
        ws[f"{g('Conf_Order_Flag')}{r}"]=f'=IF(AND({g("IsFirstLine")}{r}=1,{g("Confirmed")}{r}=1),1,0)'
        qty_range=f'{lqsrc if LQ else "0"}'
        if LQ:
            ws[f"{g('Items_In_Order')}{r}"]=f'=IF({g("IsFirstLine")}{r}=1,SUMIFS({LQ}$2:{LQ}${nrows},{N}$2:{N}${nrows},{N}{r}),"")'
        else:
            ws[f"{g('Items_In_Order')}{r}"]='=""'
        T_=f'N({g("Order_Total_F")}{r})'
        ws[f"{g('Price_Bucket')}{r}"]=(f'=IF({g("Order_Total_F")}{r}="","",IF({T_}<2000,"Under 2,000",'
            f'IF({T_}<5000,"2,000-4,999",IF({T_}<8000,"5,000-7,999",IF({T_}<10000,"8,000-9,999",'
            f'IF({T_}<15000,"10,000-14,999",IF({T_}<25000,"15,000-24,999","25,000+")))))))')
        # first confirmed occurrence of this product Base_Title + its sequential index (drives the dynamic product list)
        ws[f"{g('Prod_First')}{r}"]=(f'=IF(AND({g("Confirmed")}{r}=1,{g("Base_Title")}{r}<>""),'
            f'IF(COUNTIFS({g("Base_Title")}$2:{g("Base_Title")}{r},{g("Base_Title")}{r},{g("Confirmed")}$2:{g("Confirmed")}{r},1)=1,1,0),0)')
        ws[f"{g('Prod_Seq')}{r}"]=f'=IF({g("Prod_First")}{r}=1,SUM({g("Prod_First")}$2:{g("Prod_First")}{r}),"")'
        emsrc=cellref(EM,r,'""')
        ws[f"{g('Cust_Key')}{r}"]=(f'=IF(TRIM({emsrc})="","(guest)",LOWER(TRIM({emsrc})))' if EM else '="(guest)"')
        CK=f'{g("Cust_Key")}{r}'
        ws[f"{g('Cust_Conf_Orders')}{r}"]=(f'=IF({g("Conf_Order_Flag")}{r}=1,'
            f'SUMIFS({g("Conf_Order_Flag")}$2:{g("Conf_Order_Flag")}${nrows},{g("Cust_Key")}$2:{g("Cust_Key")}${nrows},{CK}),"")')
        ws[f"{g('Cust_FirstConf')}{r}"]=(f'=IF({g("Conf_Order_Flag")}{r}=1,'
            f'IF(SUMIFS({g("Conf_Order_Flag")}$2:{g("Conf_Order_Flag")}{r},{g("Cust_Key")}$2:{g("Cust_Key")}{r},{CK})=1,1,0),0)')
        # ---- first-occurrence flags + sequential indexes: drive fully dynamic member lists ----
        def fs(first,seq,val,gate,extra_and="",extra_ci=""):
            ws[f"{g(first)}{r}"]=(f'=IF(AND({g(gate)}{r}=1,{g(val)}{r}<>""{extra_and}),'
                f'IF(COUNTIFS({g(val)}$2:{g(val)}{r},{g(val)}{r},{g(gate)}$2:{g(gate)}{r},1{extra_ci})=1,1,0),0)')
            ws[f"{g(seq)}{r}"]=f'=IF({g(first)}{r}=1,SUM({g(first)}$2:{g(first)}{r}),"")'
        fs("Cat_First","Cat_Seq","Prod_Category","Confirmed")
        fs("Ven_First","Ven_Seq","Prod_Vendor","Confirmed")
        fs("Col_First","Col_Seq","Prod_Color","Confirmed")
        fs("Var_First","Var_Seq","Line_Name","Confirmed")
        fs("City_MFirst","City_MSeq","City_Clean","Conf_Order_Flag",
           extra_and=f',{g("Is_Local")}{r}=1',extra_ci=f',{g("Is_Local")}$2:{g("Is_Local")}{r},1')
        fs("Ctry_First","Ctry_Seq","Ship_Country_F","Conf_Order_Flag")
        fs("Qtr_First","Qtr_Seq","Quarter","Conf_Order_Flag")
        fs("Yr_First","Yr_Seq","Year","Conf_Order_Flag")
        fs("Wk_First","Wk_Seq","WeekLabel","Conf_Order_Flag")
        fs("Dt_First","Dt_Seq","Order_Date","Conf_Order_Flag")
        fs("Cust_MFirst","Cust_MSeq","Cust_Key","Conf_Order_Flag",extra_and=f',{g("Cust_Key")}{r}<>"(guest)"')
        # cancelled/refunded/voided orders (first line of each non-confirmed order) -> dynamic reference list
        ws[f"{g('Canc_First')}{r}"]=f'=IF(AND({g("IsFirstLine")}{r}=1,{g("Confirmed")}{r}=0),1,0)'
        ws[f"{g('Canc_Seq')}{r}"]=f'=IF({g("Canc_First")}{r}=1,SUM({g("Canc_First")}$2:{g("Canc_First")}{r}),"")'
        # ---- stable-name mirrors of raw fields (so calc/audit never depend on brand headers) ----
        ws[f"{g('Order_ID')}{r}"]  = f'={N}{r}'
        ws[f"{g('Line_Name')}{r}"] = f'={LN}{r}' if LN else '=""'
        ws[f"{g('Qty')}{r}"]       = f'=N({LQ}{r})' if LQ else '=0'
        ws[f"{g('Line_Price')}{r}"]= f'=N({LP}{r})' if LP else '=0'
        ws[f"{g('Line_SKU')}{r}"]  = f'={SK}{r}' if SK else '=""'
        ws[f"{g('Email_K')}{r}"]   = f'={EM}{r}' if EM else '=""'
        for cc in range(ncols+1,ncols+len(helpers)+1): ws.cell(r,cc).font=Fnt(10)
    tab=Table(displayName="tblOrders", ref=f"A1:{get_column_letter(ncols+len(helpers))}{nrows}")
    tab.tableStyleInfo=TableStyleInfo(name="TableStyleLight9",showRowStripes=True); ws.add_table(tab)
    ws.freeze_panes="A2"
    return nrows

# =====================================================================
# 6.  CALCULATION SHEETS
# =====================================================================
O="tblOrders"
COF=f"{O}[Conf_Order_Flag]"; COR=f"{O}[Conf_Order_Rev]"; CNR=f"{O}[Conf_Order_NetRev]"; CONF=f"{O}[Confirmed]"
YM=f"{O}[YearMonth]"; QTR=f"{O}[Quarter]"; YR=f"{O}[Year]"; MN=f"{O}[Month_Num]"; WK=f"{O}[WeekLabel]"; WD=f"{O}[Weekday]"
CAT=f"{O}[Prod_Category]"; CITY=f"{O}[City_Clean]"; CTRY=f"{O}[Ship_Country_F]"
ISLOC=f"{O}[Is_Local]"; SIZE=f"{O}[Size]"; PB=f"{O}[Price_Bucket]"; BT=f"{O}[Base_Title]"; CK=f"{O}[Cust_Key]"
QTY=f"{O}[Qty]"; LREV=f"{O}[Line_Revenue]"; PVEN=f"{O}[Prod_Vendor]"; PCOL=f"{O}[Prod_Color]"
IIO=f"{O}[Items_In_Order]"; OTOT=f"{O}[Order_Total_F]"; DISC=f"{O}[Order_Discount_F]"; SHIP=f"{O}[Order_Shipping_F]"
ISF=f"{O}[IsFirstLine]"; CCO=f"{O}[Cust_Conf_Orders]"; CFC=f"{O}[Cust_FirstConf]"; LNAME=f"{O}[Line_Name]"
ODATE=f"{O}[Order_Date]"; NAME=f"{O}[Order_ID]"; FSF=f"{O}[Financial_Status_F]"
PF=f"{O}[Prod_First]"; PSEQ=f"{O}[Prod_Seq]"
CATSEQ=f"{O}[Cat_Seq]"; VENSEQ=f"{O}[Ven_Seq]"; COLSEQ=f"{O}[Col_Seq]"; VARSEQ=f"{O}[Var_Seq]"
CITYSEQ=f"{O}[City_MSeq]"; CTRYSEQ=f"{O}[Ctry_Seq]"; QTRSEQ=f"{O}[Qtr_Seq]"; YRSEQ=f"{O}[Yr_Seq]"
WKSEQ=f"{O}[Wk_Seq]"; DTSEQ=f"{O}[Dt_Seq]"; CUSTSEQ=f"{O}[Cust_MSeq]"; CANCSEQ=f"{O}[Canc_Seq]"

def uniq_member(value_col, seq_col, k):
    """Formula for the k-th (1-based) unique member: INDEX/MATCH on the sequential-index
    helper column, so the member list is fully formula-driven off tblOrders and updates
    automatically when raw rows are added/removed (blank once k exceeds the unique count)."""
    return f'=IFERROR(INDEX({value_col},MATCH({k},{seq_col},0)),"")'

def dim_table(ws,start_row,members,cols,member_header="Item",startcol=1,total_row=True,ratio_cols=(),dyn=None):
    """dyn=(value_col, seq_col, slots): member labels are formula-extracted (INDEX/MATCH on the
    sequence helper) into `slots` pre-allocated rows, so the list auto-updates when raw rows change.
    Metric formulas are guarded to stay blank until a slot is populated."""
    headers(ws,start_row,[member_header]+[c[0] for c in cols],startcol=startcol)
    r=start_row+1; first=r; mcol=get_column_letter(startcol)
    if dyn:
        value_col, seq_col, slots = dyn
        for k in range(1,slots+1):
            mcell=f"{mcol}{r}"
            mc=ws.cell(r,startcol,uniq_member(value_col,seq_col,k)); mc.font=Fnt(10); mc.border=BORDER
            guard=f'=IF(${mcol}{r}="","",'
            for j,(h,tpl,nf) in enumerate(cols):
                expr=tpl.format(m=mcell,r=r)
                c=ws.cell(r,startcol+1+j); c.value=f'{guard}{expr[1:] if expr.startswith("=") else expr})'
                c.font=Fnt(10); c.number_format=nf; c.border=BORDER
            r+=1
    else:
        for m in members:
            mc=ws.cell(r,startcol,m); mc.font=Fnt(10); mc.border=BORDER
            mcell=f"{mcol}{r}"
            for j,(h,tpl,nf) in enumerate(cols):
                c=ws.cell(r,startcol+1+j); c.value=tpl.format(m=mcell,r=r); c.font=Fnt(10); c.number_format=nf; c.border=BORDER
            r+=1
    last=r-1
    if total_row:
        tc=ws.cell(r,startcol,"TOTAL"); tc.font=Fnt(10,True); tc.fill=fill(LIGHT); tc.border=BORDER
        for j,(h,tpl,nf) in enumerate(cols):
            col=get_column_letter(startcol+1+j); c=ws.cell(r,startcol+1+j)
            if j in ratio_cols or last<first:               # no members -> no SUM over a reversed range
                c.value = "" if j in ratio_cols else 0
            else:
                c.value = f"=SUM({col}{first}:{col}{last})"
            c.font=Fnt(10,True); c.number_format=nf; c.fill=fill(LIGHT); c.border=BORDER
        r+=1
    return first,last,r

def build_calcs(wb, dims, cur):
    CT = cur or "amount"
    # pre-allocated slot counts for the formula-extracted (dynamic) member lists
    SL_QTR=40; SL_YR=25; SL_WK=160; SL_DT=370; SL_CTRY=80; SL_CITY=120
    SL_CAT=50; SL_VEN=50; SL_COL=50; SL_VAR=150; SL_CUST=300
    KPIS="Calc_KPI"; ws=wb.create_sheet(KPIS)
    title(ws,"Key Performance Indicators  (Confirmed orders only)",
          "Cancelled orders (Cancelled at <> blank) are excluded from every metric below.")
    widths(ws,[34,18,2,80]); ws.sheet_view.showGridLines=False
    kdef=[
     ("conf_orders","Confirmed Orders",f"=SUM({COF})",INT),
     ("canc_orders","Cancelled Orders (reference)",f"=SUMPRODUCT(({ISF}=1)*({CONF}=0))",INT),
     ("total_orders","Total Orders (all)",f"=SUM({ISF})",INT),
     ("total_rev",f"Revenue incl. Shipping (order total, {CT})",f"=SUM({COR})",CUR),
     ("net_rev_ex_ship",f"Net Revenue Without Shipping (Revenue - Shipping, {CT})","={total_rev}-{total_ship}",CUR),
     ("merch_rev",f"Merchandise Revenue (line, {CT})",f"=SUMIFS({LREV},{CONF},1)",CUR),
     ("units","Total Units Sold",f"=SUMIFS({QTY},{CONF},1)",INT),
     ("aov",f"Average Order Value ({CT})","=IFERROR({total_rev}/{conf_orders},0)",CUR),
     ("units_per_order","Average Units per Order","=IFERROR({units}/{conf_orders},0)",DEC1),
     ("customers","Total Customers (identified)",f'=SUMIFS({CFC},{CK},"<>(guest)")',INT),
     ("guest_orders","Guest Orders (no email)",f'=SUMIFS({COF},{CK},"(guest)")',INT),
     ("repeat_cust","Repeat Customers (>1 order)",f'=SUMPRODUCT(({CFC}=1)*({CK}<>"(guest)")*({CCO}>1))',INT),
     ("new_cust","New Customers (1 order)",f'=SUMPRODUCT(({CFC}=1)*({CK}<>"(guest)")*({CCO}=1))',INT),
     ("repeat_rate","Repeat Purchase Rate","=IFERROR({repeat_cust}/{customers},0)",PCT),
     ("rev_per_cust",f"Revenue per Customer ({CT})","=IFERROR({total_rev}/{customers},0)",CUR),
     ("rev_per_order",f"Revenue per Order ({CT})","=IFERROR({total_rev}/{conf_orders},0)",CUR),
     ("rev_per_unit",f"Revenue per Unit ({CT})","=IFERROR({total_rev}/{units},0)",CUR),
     ("local_orders","Local Orders (PK)",f"=SUMIFS({COF},{ISLOC},1)",INT),
     ("intl_orders","International Orders","={conf_orders}-{local_orders}",INT),
     ("local_rev",f"Local Revenue ({CT})",f"=SUMIFS({COR},{ISLOC},1)",CUR),
     ("intl_rev",f"International Revenue ({CT})","={total_rev}-{local_rev}",CUR),
     ("local_rev_pct","Local Revenue %","=IFERROR({local_rev}/{total_rev},0)",PCT),
     ("gross_sales",f"Gross Sales (line, {CT})",f"=SUMIFS({LREV},{CONF},1)",CUR),
     ("total_disc",f"Total Discounts ({CT})",f"=SUMIFS({DISC},{CONF},1,{ISF},1)",CUR),
     ("total_ship",f"Total Shipping Charged ({CT})",f"=SUMIFS({SHIP},{CONF},1,{ISF},1)",CUR),
     ("net_sales",f"Net Sales (Gross - Discount, {CT})","={gross_sales}-{total_disc}",CUR),
     ("single_item","Single-Item Orders",f'=SUMPRODUCT(({COF}=1)*({IIO}=1))',INT),
     ("multi_item","Multi-Item Orders",f'=SUMPRODUCT(({COF}=1)*({IIO}>1))',INT),
     ("max_order",f"Highest Order Value ({CT})",f"=_xlfn.MAXIFS({OTOT},{COF},1)",CUR),
     ("min_order",f"Lowest Order Value ({CT})",f"=_xlfn.MINIFS({OTOT},{COF},1)",CUR),
    ]
    row0=4
    K={k:f"{KPIS}!B{row0+i}" for i,(k,*_)in enumerate(kdef)}
    Kl={k:f"B{row0+i}" for i,(k,*_)in enumerate(kdef)}
    for i,(k,lbl,tpl,nf) in enumerate(kdef):
        r=row0+i; ws.cell(r,1,lbl).font=Fnt(10,True); ws.cell(r,1).border=BORDER
        vc=ws.cell(r,2); vc.value=tpl.format(**Kl); vc.font=Fnt(10); vc.number_format=nf; vc.border=BORDER; vc.fill=fill(GREY)
    ws.cell(row0-1,4,"Definitions & assumptions").font=Fnt(11,True,NAVY)
    for i,nt in enumerate([
      "Confirmed order = 'Cancelled at' blank AND Financial Status not 'refunded'/'voided'. Revenue incl. shipping = order Total (net of discounts); Net Revenue Without Shipping = Revenue - Shipping.",
      "Merchandise (line) revenue = Lineitem price x quantity — used for product / category / size / variant breakdowns.",
      "Customer = lowercased email; orders without an email are grouped as '(guest)' and excluded from customer counts.",
      f"Local = Shipping Country 'PK'. Currency detected/assumed: {CT}.",
      "Product category = 'Type' if present, else the last segment of the product's Google Product Category taxonomy.",
    ]): ws.cell(row0+i,4,nt).font=Fnt(9,False,"606060",italic=True)

    # ---- Monthly ----
    wm=wb.create_sheet("Calc_Monthly")
    title(wm,"Monthly Performance, Growth, Running Totals & Forecast",
          "Continuous month grid from order dates; blank beyond latest month. Confirmed only.")
    widths(wm,[6,12,10,15,9,13,12,12,16,15,15,15,17]); wm.sheet_view.showGridLines=False
    headers(wm,4,["Idx","Month","Orders",f"Revenue incl. Ship ({CT})","Units",f"AOV ({CT})","MoM Ord %","MoM Rev %",
                  "Running Rev","Running Ord","3-Mo MA Rev","6-Mo MA Rev",f"Net Rev excl. Ship ({CT})"])
    NM=31; start=5; end=start+NM-1
    wm.cell(start,2,f"=DATE(YEAR(MIN({ODATE})),MONTH(MIN({ODATE})),1)")
    for i in range(NM):
        r=start+i; wm.cell(r,1,i+1).font=Fnt(10); wm.cell(r,1).border=BORDER
        if i>0: wm.cell(r,2,f"=EDATE(B{r-1},1)")
        wm.cell(r,2).number_format="yyyy-mm"; wm.cell(r,2).font=Fnt(10); wm.cell(r,2).border=BORDER
        lbl=f'TEXT(B{r},"YYYY-MM")'; act=f'B{r}<=DATE(YEAR(MAX({ODATE})),MONTH(MAX({ODATE})),1)'
        wm.cell(r,3,f'=IF({act},SUMIFS({COF},{YM},{lbl}),"")')
        wm.cell(r,4,f'=IF({act},SUMIFS({COR},{YM},{lbl}),"")')
        wm.cell(r,5,f'=IF({act},SUMIFS({QTY},{YM},{lbl},{CONF},1),"")')
        wm.cell(r,6,f'=IF(OR(C{r}="",C{r}=0),"",D{r}/C{r})')
        if i>0:
            wm.cell(r,7,f'=IF(OR(C{r}="",C{r-1}="",C{r-1}=0),"",(C{r}-C{r-1})/C{r-1})')
            wm.cell(r,8,f'=IF(OR(D{r}="",D{r-1}="",D{r-1}=0),"",(D{r}-D{r-1})/D{r-1})')
        wm.cell(r,9,f'=IF(D{r}="","",SUM($D${start}:D{r}))')
        wm.cell(r,10,f'=IF(C{r}="","",SUM($C${start}:C{r}))')
        wm.cell(r,11,f'=IF(D{r}="","",AVERAGE(D{max(start,r-2)}:D{r}))')
        wm.cell(r,12,f'=IF(D{r}="","",AVERAGE(D{max(start,r-5)}:D{r}))')
        wm.cell(r,13,f'=IF({act},SUMIFS({CNR},{YM},{lbl}),"")')
        for c,nf in [(3,INT),(4,CUR),(5,INT),(6,CUR),(7,PCT),(8,PCT),(9,CUR),(10,INT),(11,CUR),(12,CUR),(13,CUR)]:
            cell=wm.cell(r,c); cell.font=Fnt(10); cell.number_format=nf; cell.border=BORDER
    tr=end+1; wm.cell(tr,2,"TOTAL").font=Fnt(10,True); wm.cell(tr,2).fill=fill(LIGHT); wm.cell(tr,2).border=BORDER
    for c,nf in [(3,INT),(4,CUR),(5,INT),(13,CUR)]:
        col=get_column_letter(c); cell=wm.cell(tr,c,f"=SUM({col}{start}:{col}{end})")
        cell.font=Fnt(10,True); cell.number_format=nf; cell.fill=fill(LIGHT); cell.border=BORDER
    fr=tr+3; section(wm,fr,"Forecast (formula-based)",span=2); cnt=f"COUNT(C{start}:C{end})"
    fc=[("Active months (with data)",f"={cnt}",INT),
        ("Next-Month Revenue (linear)",f"=IFERROR(FORECAST({cnt}+1,OFFSET($D${start},0,0,{cnt},1),OFFSET($A${start},0,0,{cnt},1)),0)",CUR),
        ("Next-Month Orders (linear)",f"=IFERROR(FORECAST({cnt}+1,OFFSET($C${start},0,0,{cnt},1),OFFSET($A${start},0,0,{cnt},1)),0)",INT),
        ("3-Month MA Revenue (latest)",f"=AVERAGE(OFFSET($D${start},{cnt}-3,0,3,1))",CUR),
        ("6-Month MA Revenue (latest)",f"=AVERAGE(OFFSET($D${start},{cnt}-6,0,6,1))",CUR),
        ("Trend slope (per month)",f"=SLOPE(OFFSET($D${start},0,0,{cnt},1),OFFSET($A${start},0,0,{cnt},1))",CUR),
        ("Avg Monthly Rev Growth %",f"=IFERROR(AVERAGE(H{start+1}:H{end}),0)",PCT)]
    for i,(n,f_,nf) in enumerate(fc):
        rr=fr+1+i; wm.cell(rr,1,n).font=Fnt(10,True); wm.cell(rr,1).border=BORDER
        c=wm.cell(rr,2,f_); c.font=Fnt(10); c.number_format=nf; c.border=BORDER; c.fill=fill(GREY)
    wm.freeze_panes=f"A{start}"; MR=(start,end)

    # ---- Trend ----
    wt=wb.create_sheet("Calc_Trend")
    title(wt,"Sales Trend – Quarterly / Yearly / Weekly / Daily","Confirmed orders only.")
    widths(wt,[14,10,14,9,14,2,10,10,14,9,14,2,12,10,14,9,14]); wt.sheet_view.showGridLines=False
    mini_header(wt,4,1,"Quarterly",5)
    dim_table(wt,5,None,[("Orders",f"=SUMIFS({COF},{QTR},{{m}})",INT),("Revenue incl. Ship",f"=SUMIFS({COR},{QTR},{{m}})",CUR),("Units",f"=SUMIFS({QTY},{QTR},{{m}},{CONF},1)",INT),("Net Rev excl. Ship",f"=SUMIFS({CNR},{QTR},{{m}})",CUR)],member_header="Quarter",startcol=1,dyn=(QTR,QTRSEQ,SL_QTR))
    mini_header(wt,4,7,"Yearly",5)
    dim_table(wt,5,None,[("Orders",f"=SUMIFS({COF},{YR},{{m}})",INT),("Revenue incl. Ship",f"=SUMIFS({COR},{YR},{{m}})",CUR),("Units",f"=SUMIFS({QTY},{YR},{{m}},{CONF},1)",INT),("Net Rev excl. Ship",f"=SUMIFS({CNR},{YR},{{m}})",CUR)],member_header="Year",startcol=7,dyn=(YR,YRSEQ,SL_YR))
    mini_header(wt,4,13,"Weekly (ISO)",5)
    dim_table(wt,5,None,[("Orders",f"=SUMIFS({COF},{WK},{{m}})",INT),("Revenue incl. Ship",f"=SUMIFS({COR},{WK},{{m}})",CUR),("Units",f"=SUMIFS({QTY},{WK},{{m}},{CONF},1)",INT),("Net Rev excl. Ship",f"=SUMIFS({CNR},{WK},{{m}})",CUR)],member_header="Week",startcol=13,total_row=False,dyn=(WK,WKSEQ,SL_WK))
    drow=5+SL_QTR+4; mini_header(wt,drow,1,"Daily Sales (distinct order dates)",5)
    headers(wt,drow+1,["Date","Orders","Revenue incl. Ship","Units","Net Rev excl. Ship"],startcol=1); rr=drow+2
    for k in range(1,SL_DT+1):
        m=f"A{rr}"
        dc=wt.cell(rr,1); dc.value=uniq_member(ODATE,DTSEQ,k); dc.number_format="yyyy-mm-dd"; dc.font=Fnt(10); dc.border=BORDER
        guard=f'=IF($A{rr}="","",'
        wt.cell(rr,2,f'{guard}SUMIFS({COF},{ODATE},{m}))').number_format=INT
        wt.cell(rr,3,f'{guard}SUMIFS({COR},{ODATE},{m}))').number_format=CUR
        wt.cell(rr,4,f'{guard}SUMIFS({QTY},{ODATE},{m},{CONF},1))').number_format=INT
        wt.cell(rr,5,f'{guard}SUMIFS({CNR},{ODATE},{m}))').number_format=CUR
        for c in range(2,6): wt.cell(rr,c).font=Fnt(10); wt.cell(rr,c).border=BORDER
        rr+=1

    # ---- Geography ----
    wg=wb.create_sheet("Calc_Geography")
    title(wg,"Geography – Local vs International, Country & City","Confirmed orders only.")
    widths(wg,[24,10,15,12,9,12,15]); wg.sheet_view.showGridLines=False
    section(wg,4,"Local vs International",span=7); headers(wg,5,["Region","Orders",f"Revenue incl. Ship ({CT})","AOV","Units","% Revenue",f"Net Rev excl. Ship ({CT})"])
    for i,(lab,val) in enumerate([("Local","1"),("International","0")]):
        r=6+i; wg.cell(r,1,lab).font=Fnt(10); wg.cell(r,1).border=BORDER
        wg.cell(r,2,f"=SUMIFS({COF},{ISLOC},{val})").number_format=INT
        wg.cell(r,3,f"=SUMIFS({COR},{ISLOC},{val})").number_format=CUR
        wg.cell(r,4,f"=IFERROR(C{r}/B{r},0)").number_format=CUR
        wg.cell(r,5,f"=SUMIFS({QTY},{ISLOC},{val},{CONF},1)").number_format=INT
        wg.cell(r,6,f"=IFERROR(C{r}/{K['total_rev']},0)").number_format=PCT
        wg.cell(r,7,f"=SUMIFS({CNR},{ISLOC},{val})").number_format=CUR
        for c in range(2,8): wg.cell(r,c).font=Fnt(10); wg.cell(r,c).border=BORDER
    crow=9; section(wg,crow,"Country-wise",span=7)
    dim_table(wg,crow+1,None,[("Orders",f"=SUMIFS({COF},{CTRY},{{m}})",INT),(f"Revenue incl. Ship ({CT})",f"=SUMIFS({COR},{CTRY},{{m}})",CUR),("AOV","=IFERROR(C{r}/B{r},0)",CUR),("Units",f"=SUMIFS({QTY},{CTRY},{{m}},{CONF},1)",INT),("% Revenue","=IFERROR(C{r}/"+K['total_rev']+",0)",PCT),(f"Net Rev excl. Ship ({CT})",f"=SUMIFS({CNR},{CTRY},{{m}})",CUR)],member_header="Country",startcol=1,ratio_cols={2},dyn=(CTRY,CTRYSEQ,SL_CTRY))
    crow2=crow+1+SL_CTRY+3; section(wg,crow2,"Pakistan City Analysis (Local orders)",span=7)
    dim_table(wg,crow2+1,None,[("Orders",f"=SUMIFS({COF},{CITY},{{m}},{ISLOC},1)",INT),(f"Revenue incl. Ship ({CT})",f"=SUMIFS({COR},{CITY},{{m}},{ISLOC},1)",CUR),("AOV","=IFERROR(C{r}/B{r},0)",CUR),("Units",f"=SUMIFS({QTY},{CITY},{{m}},{ISLOC},1,{CONF},1)",INT),("% Local Rev","=IFERROR(C{r}/"+K['local_rev']+",0)",PCT),(f"Net Rev excl. Ship ({CT})",f"=SUMIFS({CNR},{CITY},{{m}},{ISLOC},1)",CUR)],member_header="City",startcol=1,ratio_cols={2},dyn=(CITY,CITYSEQ,SL_CITY))

    # ---- Products ----
    wp=wb.create_sheet("Calc_Products")
    title(wp,"Product Performance, Category, Vendor & Contribution","Product/category revenue = merchandise (line) value, which already excludes shipping — so Net Rev = Merch Revenue here. Confirmed only.")
    widths(wp,[34,10,10,15,11,11,11,15]); wp.sheet_view.showGridLines=False
    section(wp,4,"Product Category  ('Type' if present, else Google Product Category)",span=8)
    dim_table(wp,5,None,[("Line Items",f"=SUMIFS({CONF},{CAT},{{m}})",INT),("Units",f"=SUMIFS({QTY},{CAT},{{m}},{CONF},1)",INT),("Merch Revenue",f"=SUMIFS({LREV},{CAT},{{m}},{CONF},1)",CUR),("% Rev","=IFERROR(D{r}/"+K['merch_rev']+",0)",PCT),("Net Rev excl. Ship",f"=SUMIFS({LREV},{CAT},{{m}},{CONF},1)",CUR)],member_header="Category",startcol=1,dyn=(CAT,CATSEQ,SL_CAT))
    vrow=5+SL_CAT+3; section(wp,vrow,"Vendor / Brand",span=8)
    dim_table(wp,vrow+1,None,[("Line Items",f"=SUMIFS({CONF},{PVEN},{{m}})",INT),("Units",f"=SUMIFS({QTY},{PVEN},{{m}},{CONF},1)",INT),("Merch Revenue",f"=SUMIFS({LREV},{PVEN},{{m}},{CONF},1)",CUR),("% Rev","=IFERROR(D{r}/"+K['merch_rev']+",0)",PCT),("Net Rev excl. Ship",f"=SUMIFS({LREV},{PVEN},{{m}},{CONF},1)",CUR)],member_header="Vendor",startcol=1,dyn=(PVEN,VENSEQ,SL_VEN))
    prow=vrow+1+SL_VEN+3; section(wp,prow,"Product Master (auto-updates from tblOrders)",span=8)
    headers(wp,prow+1,["Product","Line Items","Units","Merch Revenue","% Rev","RankRev","RankUnits","Net Rev excl. Ship"])
    pstart=prow+2
    PRODSLOTS=max(200,len(dims['products'])+20)   # pre-allocated slots; product list is formula-extracted
    for i in range(PRODSLOTS):
        r=pstart+i; m=f"A{r}"; guard=f'IF($A{r}="","",'
        wp.cell(r,1,uniq_member(BT,PSEQ,i+1)).font=Fnt(10); wp.cell(r,1).border=BORDER
        wp.cell(r,2,f'={guard}SUMIFS({CONF},{BT},{m}))').number_format=INT
        wp.cell(r,3,f'={guard}SUMIFS({QTY},{BT},{m},{CONF},1))').number_format=INT
        wp.cell(r,4,f'={guard}SUMIFS({LREV},{BT},{m},{CONF},1))').number_format=CUR
        wp.cell(r,5,f'={guard}IFERROR(D{r}/{K["merch_rev"]},0))').number_format=PCT
        wp.cell(r,6,f'={guard}D{r}+ROW()/1000000)').number_format='0.00'
        wp.cell(r,7,f'={guard}C{r}+ROW()/1000000)').number_format='0.00'
        wp.cell(r,8,f'={guard}D{r})').number_format=CUR
        for c in range(2,9): wp.cell(r,c).font=Fnt(10); wp.cell(r,c).border=BORDER
    pend=pstart+PRODSLOTS-1
    wp.column_dimensions['F'].hidden=True; wp.column_dimensions['G'].hidden=True
    RRR=f"$F${pstart}:$F${pend}"; RUU=f"$G${pstart}:$G${pend}"; LBL=f"$A${pstart}:$A${pend}"; REVR=f"$D${pstart}:$D${pend}"; UNR=f"$C${pstart}:$C${pend}"
    srow=pend+3; section(wp,srow,"Rankings & Special Segments",span=7); rrow=srow+1
    headers(wp,rrow,["Top 20 by Revenue","Merch Revenue","","Top 10 by Units","Units"],startcol=1)
    for i in range(20):
        r=rrow+1+i
        wp.cell(r,1,f'=IFERROR(INDEX({LBL},MATCH(LARGE({RRR},{i+1}),{RRR},0)),"")').font=Fnt(10)
        wp.cell(r,2,f'=IFERROR(INDEX({REVR},MATCH(LARGE({RRR},{i+1}),{RRR},0)),"")').number_format=CUR
        if i<10:
            wp.cell(r,4,f'=IFERROR(INDEX({LBL},MATCH(LARGE({RUU},{i+1}),{RUU},0)),"")').font=Fnt(10)
            wp.cell(r,5,f'=IFERROR(INDEX({UNR},MATCH(LARGE({RUU},{i+1}),{RUU},0)),"")').number_format=INT
        for c in [1,2,4,5]: wp.cell(r,c).font=Fnt(10); wp.cell(r,c).border=BORDER
    brow=rrow+22; headers(wp,brow,["Lowest 10 by Units (ordered)","Units"],startcol=1)
    for i in range(10):
        r=brow+1+i
        wp.cell(r,1,f'=IFERROR(INDEX({LBL},MATCH(SMALL({RUU},{i+1}),{RUU},0)),"")').font=Fnt(10)
        wp.cell(r,2,f'=IFERROR(INDEX({UNR},MATCH(SMALL({RUU},{i+1}),{RUU},0)),"")').number_format=INT
        for c in [1,2]: wp.cell(r,c).font=Fnt(10); wp.cell(r,c).border=BORDER
    sc=brow+1
    for i,(n,f_,nf) in enumerate([("Distinct products sold",f'=SUMPRODUCT(({UNR}<>"")*({UNR}>0))',INT),
          ("Products ordered only once (units=1)",f'=SUMPRODUCT(({UNR}<>"")*({UNR}=1))',INT),
          ("Catalog products (tblProducts)",f"=SUMPRODUCT(1/COUNTIF(tblProducts[Title_F],tblProducts[Title_F]))",INT),
          ("Zero-sales catalog products (est.)",f"=E{sc+2}-E{sc}",INT)]):
        r=sc+i; wp.cell(r,4,n).font=Fnt(10,True); wp.cell(r,4).border=BORDER
        c=wp.cell(r,5,f_); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)

    # ---- Attributes ----
    wa=wb.create_sheet("Calc_Attributes")
    title(wa,"Size, Color, Variant, Price Bucket & Basket Analysis","Confirmed only.")
    widths(wa,[16,12,10,14,10,14,2,34,10,14,14]); wa.sheet_view.showGridLines=False
    section(wa,4,"Size Analysis",span=6)
    sizes=["Extra Small","Small","Medium","Large","XL","XXL","XXXL","Other","(No Size)"]
    dim_table(wa,5,sizes,[("Line Items",f"=SUMIFS({CONF},{SIZE},{{m}})",INT),("Units",f"=SUMIFS({QTY},{SIZE},{{m}},{CONF},1)",INT),("Merch Revenue",f"=SUMIFS({LREV},{SIZE},{{m}},{CONF},1)",CUR),("% Units","=IFERROR(C{r}/"+K['units']+",0)",PCT),("Net Rev excl. Ship",f"=SUMIFS({LREV},{SIZE},{{m}},{CONF},1)",CUR)],member_header="Size",startcol=1)
    crow=5+len(sizes)+3; section(wa,crow,"Color Analysis (best-effort from product colour metafield)",span=6)
    dim_table(wa,crow+1,None,[("Line Items",f"=SUMIFS({CONF},{PCOL},{{m}})",INT),("Units",f"=SUMIFS({QTY},{PCOL},{{m}},{CONF},1)",INT),("Merch Revenue",f"=SUMIFS({LREV},{PCOL},{{m}},{CONF},1)",CUR),("% Units","=IFERROR(C{r}/"+K['units']+",0)",PCT),("Net Rev excl. Ship",f"=SUMIFS({LREV},{PCOL},{{m}},{CONF},1)",CUR)],member_header="Color",startcol=1,dyn=(PCOL,COLSEQ,SL_COL))
    prow2=crow+1+SL_COL+3; section(wa,prow2,f"Price Bucket Analysis (order total, {CT})",span=6)
    buckets=["Under 2,000","2,000-4,999","5,000-7,999","8,000-9,999","10,000-14,999","15,000-24,999","25,000+"]
    dim_table(wa,prow2+1,buckets,[("Orders",f"=SUMIFS({COF},{PB},{{m}})",INT),("Revenue incl. Ship",f"=SUMIFS({COR},{PB},{{m}})",CUR),("Units",f"=SUMIFS({QTY},{PB},{{m}},{CONF},1)",INT),("% Rev","=IFERROR(C{r}/"+K['total_rev']+",0)",PCT),("Net Rev excl. Ship",f"=SUMIFS({CNR},{PB},{{m}})",CUR)],member_header="Bucket",startcol=1)
    brow=prow2+1+len(buckets)+3; section(wa,brow,"Basket Analysis",span=6)
    for i,(n,f_,nf) in enumerate([("Average Items per Order",f"=IFERROR({K['units']}/{K['conf_orders']},0)",DEC1),
            ("Single-Item Orders",f'=SUMPRODUCT(({COF}=1)*({IIO}=1))',INT),("Multi-Item Orders",f'=SUMPRODUCT(({COF}=1)*({IIO}>1))',INT),
            (f"Highest Basket Value ({CT})",f"=_xlfn.MAXIFS({OTOT},{COF},1)",CUR),(f"Lowest Basket Value ({CT})",f"=_xlfn.MINIFS({OTOT},{COF},1)",CUR),
            ("Highest Basket Units",f"=_xlfn.MAXIFS({IIO},{COF},1)",INT)]):
        r=brow+1+i; wa.cell(r,1,n).font=Fnt(10,True); wa.cell(r,1).border=BORDER
        c=wa.cell(r,2,f_); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
    mini_header(wa,4,8,"Variant Analysis (Lineitem name)",4); headers(wa,5,["Variant","Units","Merch Rev","Net Rev excl. Ship"],startcol=8)
    for i in range(SL_VAR):
        r=6+i; m=f"H{r}"; guard=f'=IF($H{r}="","",'
        wa.cell(r,8,uniq_member(LNAME,VARSEQ,i+1)).font=Fnt(9); wa.cell(r,8).border=BORDER
        wa.cell(r,9,f'{guard}SUMIFS({QTY},{LNAME},{m},{CONF},1))').number_format=INT
        wa.cell(r,10,f'{guard}SUMIFS({LREV},{LNAME},{m},{CONF},1))').number_format=CUR
        wa.cell(r,11,f'{guard}SUMIFS({LREV},{LNAME},{m},{CONF},1))').number_format=CUR
        for c in [9,10,11]: wa.cell(r,c).font=Fnt(9); wa.cell(r,c).border=BORDER

    # ---- Customers ----
    wc=wb.create_sheet("Calc_Customers")
    title(wc,"Customer Analytics","Identified customers (email); guests excluded from counts. Confirmed only.")
    widths(wc,[36,10,10,15,12,12,15]); wc.sheet_view.showGridLines=False
    section(wc,4,"Customer Summary",span=7)
    for i,(n,f_,nf) in enumerate([("Total Customers (identified)",K['customers'],INT),("New Customers (1 order)",K['new_cust'],INT),
          ("Returning Customers (>1 order)",K['repeat_cust'],INT),("Repeat Purchase Rate",K['repeat_rate'],PCT),
          ("Avg Revenue per Customer (incl. ship)",K['rev_per_cust'],CUR),("Avg Net Revenue per Customer (excl. ship)",f"=IFERROR({K['net_rev_ex_ship']}/{K['customers']},0)",CUR),
          ("Avg Orders per Customer",f"=IFERROR({K['conf_orders']}/{K['customers']},0)",DEC1),
          ("Guest Orders (no email)",K['guest_orders'],INT)]):
        r=5+i; wc.cell(r,1,n).font=Fnt(10,True); wc.cell(r,1).border=BORDER
        c=wc.cell(r,2, f_ if str(f_).startswith('=') else f"={f_}"); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
    mrow=5+8+2; section(wc,mrow,"Customer Master",span=7)
    headers(wc,mrow+1,["Customer (email)","Orders","Units",f"Revenue incl. Ship ({CT})","Type","RankRev",f"Net Rev excl. Ship ({CT})"]); cst=mrow+2
    for i in range(SL_CUST):
        r=cst+i; m=f"A{r}"; guard=f'=IF($A{r}="","",'
        wc.cell(r,1,uniq_member(CK,CUSTSEQ,i+1)).font=Fnt(9); wc.cell(r,1).border=BORDER
        wc.cell(r,2,f'{guard}SUMIFS({COF},{CK},{m}))').number_format=INT
        wc.cell(r,3,f'{guard}SUMIFS({QTY},{CK},{m},{CONF},1))').number_format=INT
        wc.cell(r,4,f'{guard}SUMIFS({COR},{CK},{m}))').number_format=CUR
        wc.cell(r,5,f'{guard}IF(B{r}>1,"Returning","New"))').font=Fnt(9)
        wc.cell(r,6,f'{guard}D{r}+ROW()/1000000)').number_format='0.00'
        wc.cell(r,7,f'{guard}SUMIFS({CNR},{CK},{m}))').number_format=CUR
        for c in range(2,8): wc.cell(r,c).font=Fnt(9); wc.cell(r,c).border=BORDER
    cend=cst+SL_CUST-1; wc.column_dimensions['F'].hidden=True
    trow=cend+3; section(wc,trow,"Top 15 Customers by Revenue",span=6); headers(wc,trow+1,["Customer",f"Revenue ({CT})","Orders"])
    RC=f"$F${cst}:$F${cend}"; LC=f"$A${cst}:$A${cend}"; RVC=f"$D${cst}:$D${cend}"; OCc=f"$B${cst}:$B${cend}"
    for i in range(15):
        r=trow+2+i
        wc.cell(r,1,f'=IFERROR(INDEX({LC},MATCH(LARGE({RC},{i+1}),{RC},0)),"")').font=Fnt(9)
        wc.cell(r,2,f'=IFERROR(INDEX({RVC},MATCH(LARGE({RC},{i+1}),{RC},0)),"")').number_format=CUR
        wc.cell(r,3,f'=IFERROR(INDEX({OCc},MATCH(LARGE({RC},{i+1}),{RC},0)),"")').number_format=INT
        for c in [1,2,3]: wc.cell(r,c).font=Fnt(9); wc.cell(r,c).border=BORDER

    # ---- Business ----
    wbz=wb.create_sheet("Calc_Business")
    title(wbz,"Business KPIs, Discount, Shipping, Time & Outliers","Confirmed only.")
    widths(wbz,[32,15,2,28,15,2,24,14]); wbz.sheet_view.showGridLines=False
    section(wbz,4,"Discount Analysis",span=2)
    for i,(n,f_,nf) in enumerate([("Orders with Discount",f'=SUMPRODUCT(({COF}=1)*({DISC}>0))',INT),
          ("Orders without Discount",f'=SUMPRODUCT(({COF}=1)*(N({DISC})=0))',INT),(f"Total Discount Given ({CT})",K['total_disc'],CUR),
          (f"Average Discount (per disc order)",f"=IFERROR({K['total_disc']}/SUMPRODUCT(({COF}=1)*({DISC}>0)),0)",CUR),(f"Revenue Lost to Discounts ({CT})",K['total_disc'],CUR)]):
        r=5+i; wbz.cell(r,1,n).font=Fnt(10,True); wbz.cell(r,1).border=BORDER
        c=wbz.cell(r,2, f_ if str(f_).startswith('=') else f"={f_}"); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
    mini_header(wbz,4,4,"Shipping Analysis",2)
    for i,(n,f_,nf) in enumerate([(f"Total Shipping Charged ({CT})",K['total_ship'],CUR),("Free Shipping Orders",f'=SUMPRODUCT(({COF}=1)*(N({SHIP})=0))',INT),
          ("Paid Shipping Orders",f'=SUMPRODUCT(({COF}=1)*({SHIP}>0))',INT),("Avg Shipping (paid orders)",f"=IFERROR({K['total_ship']}/SUMPRODUCT(({COF}=1)*({SHIP}>0)),0)",CUR),
          (f"Local Shipping ({CT})",f"=SUMIFS({SHIP},{CONF},1,{ISF},1,{ISLOC},1)",CUR),(f"International Shipping ({CT})",f"=SUMIFS({SHIP},{CONF},1,{ISF},1,{ISLOC},0)",CUR)]):
        r=5+i; wbz.cell(r,4,n).font=Fnt(10,True); wbz.cell(r,4).border=BORDER
        c=wbz.cell(r,5, f_ if str(f_).startswith('=') else f"={f_}"); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
    mini_header(wbz,4,7,"Business KPIs",2)
    for i,(n,f_,nf) in enumerate([(f"Gross Sales (line, {CT})",K['gross_sales'],CUR),(f"Total Discounts ({CT})",K['total_disc'],CUR),
         (f"Net Sales ({CT})",K['net_sales'],CUR),(f"Total Shipping ({CT})",K['total_ship'],CUR),(f"Revenue incl. Shipping (order, {CT})",K['total_rev'],CUR),
         (f"Net Revenue Without Shipping ({CT})",K['net_rev_ex_ship'],CUR),
         ("Revenue per Order",K['rev_per_order'],CUR),("Revenue per Unit",K['rev_per_unit'],CUR),("Revenue per Customer",K['rev_per_cust'],CUR),("Units per Order",K['units_per_order'],DEC1)]):
        r=5+i; wbz.cell(r,7,n).font=Fnt(10,True); wbz.cell(r,7).border=BORDER
        c=wbz.cell(r,8, f_ if str(f_).startswith('=') else f"={f_}"); c.number_format=nf; c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
    trow=15; section(wbz,trow,"Orders by Weekday",span=4)
    dim_table(wbz,trow+1,dims['weekdays'],[("Orders",f"=SUMIFS({COF},{WD},{{m}})",INT),("Revenue incl. Ship",f"=SUMIFS({COR},{WD},{{m}})",CUR),("Net Rev excl. Ship",f"=SUMIFS({CNR},{WD},{{m}})",CUR)],member_header="Weekday",startcol=1)
    wd_first=trow+2; wd_last=trow+1+len(dims['weekdays'])
    brow=trow+1+len(dims['weekdays'])+3; section(wbz,brow,"Peaks",span=2)
    for i,(n,f_,nf) in enumerate([("Best Weekday (orders)",f"=IFERROR(INDEX(A{wd_first}:A{wd_last},MATCH(MAX(B{wd_first}:B{wd_last}),B{wd_first}:B{wd_last},0)),\"\")",None),
           ("Best Month (revenue)",f"=IFERROR(INDEX(Calc_Monthly!B{MR[0]}:B{MR[1]},MATCH(MAX(Calc_Monthly!D{MR[0]}:D{MR[1]}),Calc_Monthly!D{MR[0]}:D{MR[1]},0)),\"\")","yyyy-mm"),
           (f"Best Month Revenue ({CT})",f"=MAX(Calc_Monthly!D{MR[0]}:D{MR[1]})",CUR)]):
        r=brow+1+i; wbz.cell(r,1,n).font=Fnt(10,True); wbz.cell(r,1).border=BORDER
        c=wbz.cell(r,2,f_); c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
        if nf: c.number_format=nf
    mini_header(wbz,16,7,"Outlier Detection",2)
    for i,(n,f_,nf) in enumerate([("High-Value Orders (> AOV x 3)",f'=SUMPRODUCT(({COF}=1)*({OTOT}>{K["aov"]}*3))',INT),
         ("Low-Value Orders (< AOV x 0.25)",f'=SUMPRODUCT(({COF}=1)*({OTOT}<{K["aov"]}*0.25))',INT),
         (f"Max Order Value ({CT})",K['max_order'],CUR),(f"Min Order Value ({CT})",K['min_order'],CUR),("Customers with multiple orders",K['repeat_cust'],INT)]):
        r=17+i; wbz.cell(r,7,n).font=Fnt(10,True); wbz.cell(r,7).border=BORDER
        c=wbz.cell(r,8, f_ if str(f_).startswith('=') else f"={f_}"); c.font=Fnt(10); c.border=BORDER; c.fill=fill(GREY)
        if nf: c.number_format=nf
    # data-first rows + seq refs of the dynamic (formula-extracted) tables, for dynamic chart ranges
    dpos={"cat":(6,SL_CAT,CATSEQ),"qtr":(6,SL_QTR,QTRSEQ),
          "ctry":(11,SL_CTRY,CTRYSEQ),"city":(15+SL_CTRY,SL_CITY,CITYSEQ)}
    return {"K":K,"month_range":MR,"seg_row":sc,"top20_rev_row":rrow,"dpos":dpos,"buckets":buckets,"sizes":sizes}

def build_gmv(wb, cur):
    """Year-wise GMV (confirmed order total) by month, with a PER-MONTH next-year projection:
    each month has its own editable growth-% cell (defaulting to the master input B3), plus
    year-over-year growth. Fully formula-driven off tblOrders.
    Columns: A Month | B-F Years | G Growth % (per-month input) | H Projection | I YoY %."""
    CT=cur or "amount"
    ws=wb.create_sheet("Calc_GMV")
    title(ws,"GMV Analysis by Year & Month",
          "GMV = confirmed order total. Projection = last year x (1 + that month's growth %). Set the master % (B3) for all months, or override any month in the 'Growth %' column.")
    widths(ws,[16,15,15,15,15,15,12,18,16]); ws.sheet_view.showGridLines=False
    # ---- master default growth-% input (feeds every month unless a month is overridden) ----
    ws["A3"]="Default growth % (INPUT):"; ws["A3"].font=Fnt(10,True,"C00000")
    inp=ws["B3"]; inp.value=0.20; inp.number_format=PCT; inp.font=Fnt(11,True,"C00000")
    inp.fill=fill("FFF2CC"); inp.border=Border(left=Side(style="medium",color="C00000"),right=Side(style="medium",color="C00000"),
                                               top=Side(style="medium",color="C00000"),bottom=Side(style="medium",color="C00000"))
    inp.alignment=Alignment(horizontal="center")
    ws["C3"]="applies to every month; override a single month in the 'Growth %' column ->"; ws["C3"].font=Fnt(9,False,"808080",italic=True)
    # ---- year bounds (hidden helpers) ----
    ws["N1"]=f'=IFERROR(YEAR(MIN({ODATE})),"")'; ws["N2"]=f'=IFERROR(YEAR(MAX({ODATE})),"")'
    ws.column_dimensions['N'].hidden=True
    FY="$N$1"; LY="$N$2"
    hr=5  # header row
    hc=ws.cell(hr,1,"Month"); hc.font=Fnt(10,True,"FFFFFF"); hc.fill=fill(BLUE); hc.alignment=Alignment(horizontal="center",vertical="center"); hc.border=BORDER
    for k in range(5):   # up to 5 year columns (B..F), each header a formula
        col=2+k; c=ws.cell(hr,col); c.value=f'=IF(AND({FY}<>"",{FY}+{k}<={LY}),{FY}+{k},"")'
        c.font=Fnt(10,True,"FFFFFF"); c.fill=fill(BLUE); c.alignment=Alignment(horizontal="center"); c.border=BORDER; c.number_format='0'
    ws.cell(hr,7,"Growth %"); ws.cell(hr,7).fill=fill("BF9000")            # G = per-month growth input
    ws.cell(hr,8).value=f'=IF({LY}="","Projection","Projection "&({LY}+1))'  # H = projection
    ws.cell(hr,8).fill=fill(TEAL)
    ws.cell(hr,9).value=f'=IF({LY}="","YoY %",({LY}-1)&" vs "&{LY}&" %")'    # I = YoY
    ws.cell(hr,9).fill=fill(NAVY)
    for cc in (7,8,9):
        c=ws.cell(hr,cc); c.font=Fnt(10,True,"FFFFFF"); c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=BORDER
    months=["January","February","March","April","May","June","July","August","September","October","November","December"]
    start=6
    for i,mnm in enumerate(months):
        r=start+i; m=i+1
        ws.cell(r,1,mnm).font=Fnt(10,True); ws.cell(r,1).border=BORDER
        for k in range(5):
            col=2+k; yh=f"{get_column_letter(col)}${hr}"
            c=ws.cell(r,col); c.value=f'=IF({yh}="","",SUMIFS({COR},{YR},{yh},{MN},{m}))'
            c.number_format=CUR; c.font=Fnt(10); c.border=BORDER
        gcell=ws.cell(r,7); gcell.value="=$B$3"; gcell.number_format=PCT; gcell.font=Fnt(10,True,"C00000")   # per-month growth (editable; defaults to master)
        gcell.fill=fill("FFF2CC"); gcell.border=BORDER; gcell.alignment=Alignment(horizontal="center")
        pc=ws.cell(r,8); pc.value=f'=IF({LY}="","",SUMIFS({COR},{YR},{LY},{MN},{m})*(1+G{r}))'                # projection uses this month's G
        pc.number_format=CUR; pc.font=Fnt(10); pc.border=BORDER; pc.fill=fill("E2EFDA")
        yv=ws.cell(r,9); yv.value=(f'=IFERROR((SUMIFS({COR},{YR},{LY},{MN},{m})-SUMIFS({COR},{YR},{LY}-1,{MN},{m}))'
                                   f'/SUMIFS({COR},{YR},{LY}-1,{MN},{m}),"")')
        yv.number_format=PCT; yv.font=Fnt(10); yv.border=BORDER
    tr=start+12
    ws.cell(tr,1,"TOTAL").font=Fnt(10,True,"FFFFFF"); ws.cell(tr,1).fill=fill(NAVY); ws.cell(tr,1).border=BORDER
    for col in range(2,6+1):   # year totals (blank when the year column is empty)
        L=get_column_letter(col)
        c=ws.cell(tr,col,f'=IF({L}${hr}="","",SUM({L}{start}:{L}{tr-1}))')
        c.number_format=CUR; c.font=Fnt(10,True,"FFFFFF"); c.fill=fill(NAVY); c.border=BORDER
    # G total = effective blended growth (projection total / last-year total - 1)
    gt=ws.cell(tr,7,f'=IFERROR(H{tr}/SUMIFS({COR},{YR},{LY})-1,"")'); gt.number_format=PCT; gt.font=Fnt(10,True,"FFFFFF"); gt.fill=fill(NAVY); gt.border=BORDER
    pt=ws.cell(tr,8,f"=SUM(H{start}:H{tr-1})"); pt.number_format=CUR; pt.font=Fnt(10,True,"FFFFFF"); pt.fill=fill(NAVY); pt.border=BORDER
    yt=ws.cell(tr,9,f'=IFERROR((SUMIFS({COR},{YR},{LY})-SUMIFS({COR},{YR},{LY}-1))/SUMIFS({COR},{YR},{LY}-1),"")')
    yt.number_format=PCT; yt.font=Fnt(10,True,"FFFFFF"); yt.fill=fill(NAVY); yt.border=BORDER
    ws.freeze_panes="B6"

# =====================================================================
# 7.  DATA AUDIT
# =====================================================================
def build_audit(wb, dims, cur, cancelled, meta):
    K=meta['K']; seg_row=meta['seg_row']; CT=cur or "amount"
    P="tblProducts"
    ISFx=f"{O}[IsFirstLine]"; IIOx=f"{O}[Items_In_Order]"; SKU=f"{O}[Line_SKU]"; LNx=f"{O}[Line_Name]"
    LPx=f"{O}[Line_Price]"; SCITY=f"{O}[Ship_City_F]"; SCTRY=f"{O}[Ship_Country_F]"; EMAIL=f"{O}[Email_K]"
    SIZEx=f"{O}[Size]"; PCATx=f"{O}[Prod_Category]"; ODATEx=f"{O}[Order_Date]"; CORx=f"{O}[Conf_Order_Rev]"
    OTOTx=f"{O}[Order_Total_F]"; PH=f"{P}[Handle_K]"; PT=f"{P}[Title_F]"; PSKU=f"{P}[SKU_K]"
    PPRICE=f"{P}[Price_K]"; PTYPE=f"{P}[Type_K]"
    ws=wb.create_sheet("Data_Audit")
    title(ws,"Data Validation & Audit","Automated formula-based checks on both source files. Confirmed = 'Cancelled at' blank.")
    ws.sheet_view.showGridLines=False; widths(ws,[5,50,12,11,62]); headers(ws,4,["#","Check","Result","Status","Notes / interpretation"])
    r=[5]
    def band(t):
        ws.cell(r[0],2,t).font=Fnt(11,True,"FFFFFF")
        for i in range(1,6): ws.cell(r[0],i).fill=fill(TEAL)
        ws.cell(r[0],2).font=Fnt(11,True,"FFFFFF"); r[0]+=1
    def chk(num,label,formula,status_tpl,note,nf='#,##0'):
        cr=r[0]
        ws.cell(cr,1,num).font=Fnt(10); ws.cell(cr,1).border=BORDER; ws.cell(cr,1).alignment=Alignment(horizontal="center")
        ws.cell(cr,2,label).font=Fnt(10); ws.cell(cr,2).border=BORDER
        c=ws.cell(cr,3,formula); c.font=Fnt(10,True); c.border=BORDER; c.alignment=Alignment(horizontal="center"); c.number_format=nf
        st="" if status_tpl is None else status_tpl.format(c=f"C{cr}",cp=f"C{cr-1}")
        s=ws.cell(cr,4,st); s.font=Fnt(10,True); s.border=BORDER; s.alignment=Alignment(horizontal="center")
        nc=ws.cell(cr,5,note); nc.font=Fnt(9,False,"606060"); nc.border=BORDER; nc.alignment=Alignment(wrap_text=True,vertical="top")
        r[0]+=1
    ZO='=IF({c}=0,"OK","Review")'; ZI='=IF({c}=0,"OK","Info")'; DASH='="-"'
    band("ORDERS FILE")
    chk(1,"Order line-item rows (records)",f"=COUNTA({NAME})",DASH,"Total rows in the orders export (one per line item).")
    chk(2,"Distinct order IDs",f"=SUMPRODUCT(1/COUNTIF({NAME},{NAME}))",DASH,"Unique order numbers.")
    chk(3,"Confirmed orders",f"={K['conf_orders']}",DASH,"Included in all analytics.")
    chk(4,"Cancelled orders (reference only)",f"={K['canc_orders']}",DASH,"Excluded from every KPI/chart; listed below.")
    chk(5,"Multi-item orders (>1 unit, info)",f"=SUMPRODUCT(({ISFx}=1)*({IIOx}>1))",DASH,"Not an error.")
    chk(6,"Order lines with MISSING SKU",f'=SUMPRODUCT(--({SKU}=""))',ZI,"Mapping uses product Title, so blank SKUs are non-blocking.")
    chk(7,"Order lines missing Lineitem name",f'=SUMPRODUCT(--({LNx}=""))',ZO,"Required for mapping.")
    chk(8,"Order lines with zero/blank price",f'=SUMPRODUCT(--(N({LPx})=0))',ZO,"Line item price missing or zero.")
    chk(9,"Orders missing Shipping City",f'=SUMPRODUCT(({ISFx}=1)*({SCITY}=""))',ZO,"City blank on the order header row.")
    chk(10,"Orders missing Shipping Country",f'=SUMPRODUCT(({ISFx}=1)*({SCTRY}=""))',ZO,"Country blank -> 'Unknown' region.")
    chk(11,"Orders missing Email (guest)",f'=SUMPRODUCT(({ISFx}=1)*({EMAIL}=""))',ZI,"Grouped as '(guest)', excluded from customer counts.")
    chk(12,"Order lines missing parsed Size",f'=SUMPRODUCT(--({SIZEx}="(No Size)"))',ZI,"Lineitem name had no ' - Size' suffix.")
    chk(13,"Order lines not matched to a product",f'=SUMPRODUCT(--({PCATx}="Unmapped"))',ZO,"Product Title not found in Products export.")
    chk(14,"Orders with invalid/blank date",f'=SUMPRODUCT(--({ODATEx}=""))',ZO,"Created-at could not be parsed.")
    band("PRODUCTS FILE")
    chk(15,"Product variant rows",f"=COUNTA({PH})",DASH,"One row per variant.")
    chk(16,"Distinct products (Handle)",f"=SUMPRODUCT(1/COUNTIF({PH},{PH}))",DASH,"Unique catalog products.")
    chk(17,"Distinct product Titles",f"=SUMPRODUCT(1/COUNTIF({PT},{PT}))",'=IF({c}<={cp},"OK","Info")',"If < Handles, some products share a title.")
    chk(18,"Products missing Title",f'=SUMPRODUCT(--({PT}=""))',ZO,"Filled-down title blank.")
    chk(19,"Products with 'Type' populated",f'=SUMPRODUCT(--({PTYPE}<>""))','=IF({c}>0,"OK","Info")',"If empty, category derived from Google Product Category.")
    chk(20,"Product rows missing Variant SKU",f'=SUMPRODUCT(--({PSKU}=""))',ZI,"Blank SKUs in catalog.")
    chk(21,"Duplicate Variant SKUs (non-blank)",f'=SUMPRODUCT(({PSKU}<>"")*(COUNTIF({PSKU},{PSKU})>1))',ZO,"Non-blank SKU rows sharing a value.")
    chk(22,"Products with zero/blank price",f'=SUMPRODUCT(--(N({PPRICE})=0))',ZI,"Variant price missing or zero.")
    chk(23,"Catalog products never sold (est.)",f"=Calc_Products!E{seg_row+3}",DASH,"Distinct catalog titles minus distinct products sold.")
    band("RECONCILIATION")
    chk(24,"Confirmed revenue = KPI total",f"=IF(ROUND(SUM({CORx}),2)=ROUND({K['total_rev']},2),1,0)",'=IF({c}=1,"OK","Review")',"Revenue reconciles across the workbook.")
    chk(25,"Confirmed + Cancelled = Distinct orders",f"=IF(({K['conf_orders']}+{K['canc_orders']})=SUMPRODUCT(1/COUNTIF({NAME},{NAME})),1,0)",'=IF({c}=1,"OK","Review")',"No order double-counted or missed.")
    chk(26,"Units reconcile",f"=IF(SUMIFS({QTY},{CONF},1)={K['units']},1,0)",'=IF({c}=1,"OK","Review")',"Total confirmed units tie out.")
    last=r[0]-1
    green=PatternFill("solid",fgColor="C6EFCE"); amber=PatternFill("solid",fgColor="FFEB9C")
    ws.conditional_formatting.add(f"D5:D{last}",FormulaRule(formula=['$D5="OK"'],fill=green,font=Fnt(10,True,"006100")))
    ws.conditional_formatting.add(f"D5:D{last}",FormulaRule(formula=['OR($D5="Review",$D5="Info")'],fill=amber,font=Fnt(10,True,"9C6500")))
    cr=last+3; section(ws,cr,"Cancelled Orders — reference only (EXCLUDED from all analytics)",span=5)
    headers(ws,cr+1,["Order ID","Order Date","Country",f"Order Total ({CT})","Financial Status"])
    SL_CANC=200; cst=cr+2
    for i in range(SL_CANC):
        rr=cst+i; mc=f"A{rr}"; guard=f'=IF($A{rr}="","",'
        ws.cell(rr,1,uniq_member(NAME,CANCSEQ,i+1)).font=Fnt(10); ws.cell(rr,1).border=BORDER
        ws.cell(rr,2,f'{guard}IFERROR(_xlfn.MAXIFS({ODATEx},{NAME},{mc},{ISFx},1),""))').number_format="yyyy-mm-dd"
        ws.cell(rr,3,f'{guard}IFERROR(INDEX({SCTRY},MATCH({mc},{NAME},0)),""))')
        ws.cell(rr,4,f'{guard}IFERROR(INDEX({OTOTx},MATCH({mc},{NAME},0)),""))').number_format='#,##0'
        ws.cell(rr,5,f'{guard}IFERROR(INDEX({FSF},MATCH({mc},{NAME},0)),""))')
        for c in range(2,6): ws.cell(rr,c).font=Fnt(10); ws.cell(rr,c).border=BORDER
    tot=cst+SL_CANC
    ws.cell(tot,1,"TOTAL").font=Fnt(10,True); ws.cell(tot,1).fill=fill(LIGHT); ws.cell(tot,1).border=BORDER
    lc=ws.cell(tot,2,f'="("&{K["canc_orders"]}&" orders)"'); lc.font=Fnt(9,italic=True); lc.fill=fill(LIGHT)
    ws.cell(tot,4,f"=SUM(D{cst}:D{tot-1})").number_format='#,##0'
    ws.cell(tot,4).font=Fnt(10,True); ws.cell(tot,4).fill=fill(LIGHT); ws.cell(tot,4).border=BORDER

# =====================================================================
# 8.  DASHBOARD + CHART_DATA + COVER
# =====================================================================
def build_dashboard(wb, dims, cur, meta):
    K=meta['K']; MR=meta['month_range']; top20=meta['top20_rev_row']; CT=cur or "amount"
    def find_row(ws,value,col=1,lo=1,hi=1400):
        for rr in range(lo,hi):
            if ws.cell(rr,col).value==value: return rr
        return None
    wpc=wb['Calc_Products']; wg=wb['Calc_Geography']; wa=wb['Calc_Attributes']; wt=wb['Calc_Trend']; wm=wb['Calc_Monthly']
    dp=meta['dpos']
    # dynamic tables: known data-first rows + slot counts (member labels are formula-extracted)
    cat_first,cat_slots,cat_seq=dp['cat']; cat_last=cat_first+cat_slots-1
    ctry_first,ctry_slots,ctry_seq=dp['ctry']; ctry_last=ctry_first+ctry_slots-1
    city_first,city_slots,city_seq=dp['city']; city_last=city_first+city_slots-1
    q_first,q_slots,q_seq=dp['qtr']; q_last=q_first+q_slots-1
    # static enumerations still located by label
    size_first=find_row(wa,'Extra Small'); size_last=size_first+len(meta['sizes'])-1
    pb_first=find_row(wa,'Under 2,000'); pb_last=pb_first+len(meta['buckets'])-1
    # charts reference a modest fixed window of the dynamic tables; unfilled rows are blank
    # (bar/pie render blank rows invisibly) and populate automatically as raw data grows.
    CAT_CHART=15; CTRY_CHART=12; QTR_CHART=16
    cat_last=cat_first+CAT_CHART-1; ctry_last=ctry_first+CTRY_CHART-1; q_last=q_first+QTR_CHART-1
    mm=dims['months']; miny,minm=map(int,mm[0].split('-')); maxy,maxm=map(int,mm[-1].split('-'))
    span=(maxy-miny)*12+(maxm-minm)+1; m_start=MR[0]; m_end=m_start+span-1

    cd=wb.create_sheet("Chart_Data"); cd.sheet_state='hidden'
    cd["A1"]="City"; cd["B1"]="Rev"; cd["C1"]="Orders"; cd["D1"]="eps"
    ncity=city_slots
    for i in range(ncity):
        rr=2+i; gr=city_first+i
        cd.cell(rr,1,f"=Calc_Geography!A{gr}")
        cd.cell(rr,2,f'=IF(Calc_Geography!A{gr}="","",Calc_Geography!C{gr})')
        cd.cell(rr,3,f'=IF(Calc_Geography!A{gr}="","",Calc_Geography!B{gr})')
        cd.cell(rr,4,f'=IF(Calc_Geography!A{gr}="","",Calc_Geography!C{gr}+ROW()/1000000)')
    DR=f"$D$2:$D${1+ncity}"; AR=f"$A$2:$A${1+ncity}"; BR=f"$B$2:$B${1+ncity}"; CRg=f"$C$2:$C${1+ncity}"
    topn=10
    cd["F1"]="Top City"; cd["G1"]="Revenue"; cd["H1"]="Orders"
    for i in range(topn):
        rr=2+i
        cd.cell(rr,6,f'=IFERROR(INDEX({AR},MATCH(LARGE({DR},{i+1}),{DR},0)),"")')
        cd.cell(rr,7,f'=IFERROR(INDEX({BR},MATCH(LARGE({DR},{i+1}),{DR},0)),"")')
        cd.cell(rr,8,f'=IFERROR(INDEX({CRg},MATCH(LARGE({DR},{i+1}),{DR},0)),"")')
    cd["J1"]="Segment"; cd["K1"]="Count"; cd["J2"]="New (1 order)"; cd["K2"]=f"={K['new_cust']}"; cd["J3"]="Returning (2+)"; cd["K3"]=f"={K['repeat_cust']}"
    cd["J5"]="Region"; cd["K5"]="Revenue"; cd["J6"]="Local (PK)"; cd["K6"]=f"={K['local_rev']}"; cd["J7"]="International"; cd["K7"]=f"={K['intl_rev']}"

    SER1="305496"; SER2="1F6F54"; SER3="BF9000"; SER4="9E480E"
    PIE=["305496","1F6F54","BF9000","9E480E","7030A0","C55A11","548235","2E75B6"]
    def R(ws,col,r1,r2): return Reference(ws,min_col=col,min_row=r1,max_row=r2)
    def dlabels(numfmt='#,##0',pos='outEnd',show_val=True,percent=False,catname=False,leader=False):
        # value/percent labels on the chart, in a small bold font so they stay readable and don't overlap
        dl=DataLabelList(); dl.showVal=show_val; dl.showPercent=percent; dl.showCatName=catname
        dl.showSerName=False; dl.showLegendKey=False; dl.showBubbleSize=False
        if numfmt: dl.numFmt=numfmt
        if pos: dl.dLblPos=pos
        if leader: dl.showLeaderLines=True
        cp=CharacterProperties(sz=850,b=True,solidFill="404040")
        dl.txPr=RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp),endParaRPr=cp)])
        return dl
    def bar(title_,cat_ref,val_ref,color=SER1,horizontal=False,numfmt='#,##0'):
        ch=BarChart(); ch.type="bar" if horizontal else "col"; ch.legend=None
        ch.add_data(val_ref,titles_from_data=False); ch.set_categories(cat_ref)
        ch.title=title_; ch.height=7.2; ch.width=11.5; ch.style=2; ch.y_axis.numFmt=numfmt; ch.y_axis.majorGridlines=None
        ch.dataLabels=dlabels(numfmt,'outEnd')
        for s in ch.series:
            s.graphicalProperties.solidFill=color; s.graphicalProperties.line.noFill=True
        return ch
    def line(title_,cat_ref,val_ref,color=SER1,numfmt='#,##0'):
        ch=LineChart(); ch.legend=None; ch.add_data(val_ref,titles_from_data=False); ch.set_categories(cat_ref)
        ch.title=title_; ch.height=7.2; ch.width=11.5; ch.style=2; ch.y_axis.numFmt=numfmt
        ch.dataLabels=dlabels(numfmt,'t')
        for s in ch.series:
            s.graphicalProperties.line.solidFill=color; s.graphicalProperties.line.width=28000; s.smooth=False; s.marker=Marker(symbol='circle',size=4)
        return ch
    def pie(title_,cat_ref,val_ref,doughnut=False):
        ch=DoughnutChart() if doughnut else PieChart(); ch.legend=None; ch.add_data(val_ref,titles_from_data=False); ch.set_categories(cat_ref)
        ch.title=title_; ch.height=7.2; ch.width=11.5
        ch.dataLabels=dlabels(None,'bestFit',show_val=False,percent=True,catname=True,leader=True)
        s=ch.series[0]
        for i,c in enumerate(PIE):
            dp=DataPoint(idx=i); dp.graphicalProperties.solidFill=c; s.data_points.append(dp)
        return ch
    dash=wb.create_sheet("Dashboard"); dash.sheet_view.showGridLines=False; widths(dash,[3]+[13]*17)
    dash.merge_cells("B2:R2"); dash["B2"]="Shopify Orders & Products — Analytics Dashboard"
    dash["B2"].font=Fnt(20,True,NAVY); dash["B2"].alignment=Alignment(vertical="center"); dash.row_dimensions[2].height=30
    dash.merge_cells("B3:R3")
    dash["B3"]=f"Confirmed orders only (cancelled excluded) • Currency: {CT} • Data window: {mm[0]} to {mm[-1]} • Auto-recalculates from Raw_Orders / Raw_Products"
    dash["B3"].font=Fnt(10,False,"808080",italic=True)
    CARDS=[("Confirmed Orders",K['conf_orders'],INT,SER1),(f"Revenue incl. Shipping ({CT})",K['total_rev'],CUR,SER2),
     ("Avg Order Value",K['aov'],CUR,SER1),("Total Units Sold",K['units'],INT,SER2),("Total Customers",K['customers'],INT,SER1),
     ("Cancelled (reference)",K['canc_orders'],INT,"C55A11"),("Repeat Customers",K['repeat_cust'],INT,SER2),
     ("New Customers",K['new_cust'],INT,SER1),("Avg Units / Order",K['units_per_order'],DEC1,SER2),("Revenue / Customer",K['rev_per_cust'],CUR,SER1),
     (f"Net Revenue Without Shipping ({CT})",K['net_rev_ex_ship'],CUR,SER2)]
    def card(top,left,label,kpi,nf,color):
        dash.merge_cells(start_row=top,start_column=left,end_row=top,end_column=left+2)
        hc=dash.cell(top,left,label); hc.fill=fill(color); hc.font=Fnt(9,True,"FFFFFF"); hc.alignment=Alignment(horizontal="center",vertical="center")
        dash.merge_cells(start_row=top+1,start_column=left,end_row=top+2,end_column=left+2)
        vc=dash.cell(top+1,left,f"={kpi}"); vc.fill=fill("F2F2F2"); vc.font=Fnt(20,True,color); vc.alignment=Alignment(horizontal="center",vertical="center"); vc.number_format=nf
        b=Side(style="thin",color="D9D9D9")
        for rr in range(top,top+3):
            for cc in range(left,left+3): dash.cell(rr,cc).border=Border(left=b,right=b,top=b,bottom=b)
    for i,(lab,kpi,nf,color) in enumerate(CARDS):
        card(5+(i//5)*4, 2+(i%5)*3, lab, kpi, nf, color)
    cr0=17; r2=cr0+15; r3=r2+15; r4=r3+15; r5=r4+15
    dash.add_chart(line(f"Monthly Revenue ({CT})",R(wm,2,m_start,m_end),R(wm,4,m_start,m_end),SER1),f"B{cr0}")
    dash.add_chart(bar("Monthly Orders",R(wm,2,m_start,m_end),R(wm,3,m_start,m_end),SER2),f"H{cr0}")
    dash.add_chart(line(f"Cumulative Revenue (Running Total, {CT})",R(wm,2,m_start,m_end),R(wm,9,m_start,m_end),SER4),f"N{cr0}")
    dash.add_chart(pie("Local vs International Revenue",R(cd,10,6,7),R(cd,11,6,7)),f"B{r2}")
    dash.add_chart(bar(f"Revenue by Country ({CT})",R(wg,1,ctry_first,ctry_last),R(wg,3,ctry_first,ctry_last),SER1,horizontal=True),f"H{r2}")
    dash.add_chart(pie("Revenue by Product Category",R(wpc,1,cat_first,cat_last),R(wpc,4,cat_first,cat_last)),f"N{r2}")
    dash.add_chart(bar(f"Top Cities by Revenue ({CT})",R(cd,6,2,11),R(cd,7,2,11),SER2,horizontal=True),f"B{r3}")
    dash.add_chart(bar("Top Cities by Orders",R(cd,6,2,11),R(cd,8,2,11),SER1,horizontal=True),f"H{r3}")
    dash.add_chart(bar(f"Top 10 Products by Revenue ({CT})",R(wpc,1,top20+1,top20+10),R(wpc,2,top20+1,top20+10),SER3,horizontal=True),f"N{r3}")
    dash.add_chart(bar(f"Revenue by Price Bucket ({CT})",R(wa,1,pb_first,pb_last),R(wa,3,pb_first,pb_last),SER1),f"B{r4}")
    dash.add_chart(bar("Units by Size",R(wa,1,size_first,size_last),R(wa,3,size_first,size_last),SER2),f"H{r4}")
    dash.add_chart(pie("New vs Returning Customers",R(cd,10,2,3),R(cd,11,2,3),doughnut=True),f"N{r4}")
    dash.add_chart(bar(f"Quarterly Revenue ({CT})",R(wt,1,q_first,q_last),R(wt,3,q_first,q_last),SER2),f"B{r5}")
    dash.add_chart(bar("Units Sold by Month",R(wm,2,m_start,m_end),R(wm,5,m_start,m_end),SER1),f"H{r5}")

    cov=wb.create_sheet("Cover"); cov.sheet_view.showGridLines=False; widths(cov,[3,42,60,3])
    cov.merge_cells("B2:C2"); cov["B2"]="Shopify Orders & Products — Analytics Dashboard"; cov["B2"].font=Fnt(22,True,NAVY)
    cov.merge_cells("B3:C3"); cov["B3"]="Formula-driven • Cancelled orders excluded • Generated locally"; cov["B3"].font=Fnt(11,False,"808080",italic=True)
    cov["B5"]="Navigation"; cov["B5"].font=Fnt(14,True,TEAL)
    nav=[("Dashboard","KPI cards + charts (executive view)"),("Data_Audit","Data validation & cancelled-orders reference"),
         ("Calc_KPI","All headline KPIs (single source of truth)"),("Calc_Monthly","Monthly performance, growth, forecast"),
         ("Calc_Trend","Daily / weekly / quarterly / yearly trend"),("Calc_Geography","Local vs international, country & city"),
         ("Calc_Products","Products, category, vendor, contribution, rankings"),("Calc_Attributes","Size, colour, variant, price bucket, basket"),
         ("Calc_Customers","Customer analytics & top customers"),("Calc_Business","Business KPIs, discount, shipping, time, outliers"),
         ("Raw_Orders","Orders source + helper columns (tblOrders)"),("Raw_Products","Products source + helper columns (tblProducts)")]
    r=6
    for sh,desc in nav:
        c=cov.cell(r,2,sh); c.font=Fnt(11,True,"0563C1"); c.hyperlink=f"#'{sh}'!A1"
        cov.cell(r,3,desc).font=Fnt(10,False,"404040"); r+=1
    r+=1; cov.cell(r,2,"Key assumptions & data notes").font=Fnt(14,True,TEAL); r+=1
    for a in [
     "Confirmed order = 'Cancelled at' is blank AND Financial Status is not 'refunded' or 'voided'. Cancelled/refunded/voided orders are excluded from every KPI/table/chart and listed on Data_Audit.",
     "Revenue incl. shipping = order Total (net of discounts); Net Revenue Without Shipping = Revenue - Shipping. Product/category/size revenue = line merchandise value (price x qty).",
     "Columns are matched by HEADER NAME, not position, so the app works across brands even when column order differs.",
     "Product category = 'Type' if present, else the last segment of the Google Product Category taxonomy.",
     "Products are matched to orders by Title (SKUs are often blank on order lines). Unmatched lines appear as 'Unmapped'.",
     "Size is parsed from the 'Product - Size' line-item name; colour is best-effort from the product colour metafield.",
     "Customer = lowercased email; orders without email are grouped as '(guest)' and excluded from customer counts.",
     "Local = Shipping Country 'PK'; International = all other countries.",
    ]:
        cell=cov.cell(r,2,"•  "+a); cov.merge_cells(start_row=r,start_column=2,end_row=r,end_column=3)
        cell.font=Fnt(10,False,"404040"); cell.alignment=Alignment(wrap_text=True,vertical="top"); cov.row_dimensions[r].height=30; r+=1
    r+=1; cov.cell(r,2,"How to refresh with new data").font=Fnt(14,True,TEAL); r+=1
    for a in [
     "Re-run the app on the new Orders + Products exports — it regenerates the whole workbook. No cloud upload, no code changes.",
     "Or, inside this file: replace the rows under the header in Raw_Orders / Raw_Products; the Tables auto-expand and every KPI/chart recalculates.",
     "The workbook recalculates automatically when opened in Excel (formula-driven; no macros).",
    ]:
        cell=cov.cell(r,2,a); cov.merge_cells(start_row=r,start_column=2,end_row=r,end_column=3)
        cell.font=Fnt(10,False,"404040"); cell.alignment=Alignment(wrap_text=True,vertical="top"); cov.row_dimensions[r].height=26; r+=1

    order=["Cover","Dashboard","Data_Audit","Calc_KPI","Calc_GMV","Calc_Monthly","Calc_Trend","Calc_Geography",
           "Calc_Products","Calc_Attributes","Calc_Customers","Calc_Business","Chart_Data","Raw_Orders","Raw_Products"]
    wb._sheets.sort(key=lambda s: order.index(s.title) if s.title in order else 99)

# =====================================================================
# 9.  POLISH + OPTIONAL RECALC
# =====================================================================
def polish(wb):
    pres=["Cover","Dashboard","Data_Audit","Calc_KPI","Calc_GMV","Calc_Monthly","Calc_Trend","Calc_Geography",
          "Calc_Products","Calc_Attributes","Calc_Customers","Calc_Business"]
    for name in pres:
        if name not in wb.sheetnames: continue
        ws=wb[name]; ws.page_setup.orientation="landscape"; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
        ws.sheet_properties.pageSetUpPr=PageSetupProperties(fitToPage=True); ws.print_options.horizontalCentered=True
        ws.page_margins.left=ws.page_margins.right=0.3; ws.page_margins.top=ws.page_margins.bottom=0.4
    for name in ("Raw_Orders","Raw_Products"):
        if name in wb.sheetnames:
            wb[name].print_title_rows="1:1"; wb[name].page_setup.orientation="landscape"
    if "Dashboard" in wb.sheetnames: wb["Dashboard"].print_area="A1:R100"
    wb.calculation.calcMode="auto"; wb.calculation.fullCalcOnLoad=True
    if "Cover" in wb.sheetnames:
        wb.active=wb.sheetnames.index("Cover")
        for ws in wb.worksheets: ws.sheet_view.tabSelected=(ws.title=="Cover")
    wb.properties.title="Shopify Orders & Products Analytics Dashboard"

def find_soffice():
    for p in [r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice",
              shutil.which("soffice") or "", shutil.which("libreoffice") or ""]:
        if p and os.path.exists(p): return p
    return None

def try_recalc(path):
    soffice=find_soffice()
    if not soffice: return False
    prof=tempfile.mkdtemp(prefix="lo_prof_"); outdir=tempfile.mkdtemp(prefix="lo_out_")
    try:
        os.makedirs(os.path.join(prof,"user"),exist_ok=True)
        with open(os.path.join(prof,"user","registrymodifications.xcu"),"w",encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<oor:items xmlns:oor="http://openoffice.org/2001/registry">\n'
                    ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
                    ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n</oor:items>\n')
        prof_uri=pathlib.Path(prof).as_uri()
        r=subprocess.run([soffice,"--headless","--norestore",f"-env:UserInstallation={prof_uri}",
                          "--convert-to","xlsx:Calc MS Excel 2007 XML","--outdir",outdir,os.path.abspath(path)],
                         capture_output=True,timeout=300)
        produced=os.path.join(outdir,os.path.basename(path))
        if os.path.exists(produced): shutil.move(produced,path); return True
    except Exception:
        return False
    finally:
        shutil.rmtree(prof,ignore_errors=True); shutil.rmtree(outdir,ignore_errors=True)
    return False

# =====================================================================
# 10.  ORCHESTRATION
# =====================================================================
def generate(orders_csv, products_csv, output_xlsx, verbose=True):
    orders_df=read_csv(orders_csv); products_df=read_csv(products_csv)
    OC,orep=resolve(list(orders_df.columns), ORDER_ALIASES)
    PC,prep=resolve(list(products_df.columns), PRODUCT_ALIASES)
    if verbose:
        print("\nORDERS column mapping:")
        for st,fld,hdr in orep: print(f"  [{st}] {fld:18s} -> {hdr}")
        print("PRODUCTS column mapping:")
        for st,fld,hdr in prep: print(f"  [{st}] {fld:18s} -> {hdr}")
    required=["name","lineitem_name","lineitem_qty","lineitem_price","total","created_at"]
    missing=[f for f in required if not OC.get(f)]
    if missing:
        print(f"\nWARNING: required order columns not found: {missing}. Output may be incomplete.")
    dims,ctrl,cur=enrich(orders_df, products_df, OC, PC)
    wb=openpyxl.Workbook(); wb.remove(wb.active)
    build_raw_products(wb, products_df, PC)
    build_raw_orders(wb, orders_df, OC)
    meta=build_calcs(wb, dims, cur)
    build_gmv(wb, cur)
    build_audit(wb, dims, cur, ctrl["cancelled"], meta)
    build_dashboard(wb, dims, cur, meta)
    polish(wb)
    wb.save(output_xlsx)
    # Optional LibreOffice pre-compute so values show even in non-calculating viewers. The workbook
    # stays 100% formula-driven (fullCalcOnLoad) so Excel recalculates every sheet/KPI/chart — and
    # grows/shrinks every dynamic member list — automatically on open and after any raw-data edit.
    recalced=try_recalc(output_xlsx)
    if verbose:
        print(f"\nControls (from source): orders={ctrl['conf_orders']}, revenue={ctrl['total_rev']:,}, "
              f"units={ctrl['units']}, customers={ctrl['customers']}, cancelled={ctrl['canc_orders']}")
        print("Fully formula-driven; values pre-computed via LibreOffice." if recalced else
              "Fully formula-driven — Excel recalculates every value/chart automatically on open and after any edit.")
        print(f"\nDone -> {output_xlsx}")
    return output_xlsx, ctrl

def pick_files_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        return None
    root=tk.Tk(); root.withdraw()
    messagebox.showinfo("Shopify Analytics","Select your Shopify ORDERS export CSV.")
    o=filedialog.askopenfilename(title="Select ORDERS export CSV",filetypes=[("CSV","*.csv"),("All","*.*")])
    if not o: return None
    messagebox.showinfo("Shopify Analytics","Now select your Shopify PRODUCTS export CSV.")
    p=filedialog.askopenfilename(title="Select PRODUCTS export CSV",filetypes=[("CSV","*.csv"),("All","*.*")])
    if not p: return None
    out=filedialog.asksaveasfilename(title="Save analytics workbook as",defaultextension=".xlsx",
        initialfile="Shopify_Analytics_Dashboard.xlsx",filetypes=[("Excel","*.xlsx")])
    if not out: return None
    root.destroy(); return o,p,out

def main():
    ap=argparse.ArgumentParser(description="Generate a Shopify analytics Excel workbook from two CSV exports.")
    ap.add_argument("orders", nargs="?", help="Shopify ORDERS export CSV")
    ap.add_argument("products", nargs="?", help="Shopify PRODUCTS export CSV")
    ap.add_argument("-o","--output", help="Output .xlsx path")
    ap.add_argument("--open", action="store_true", help="Open the workbook when done (Windows/Mac)")
    args=ap.parse_args()
    if not args.orders or not args.products:
        picked=pick_files_gui()
        if not picked:
            print("Usage: python shopify_analytics_app.py ORDERS.csv PRODUCTS.csv [-o OUTPUT.xlsx]")
            sys.exit(1)
        orders,products,output=picked
    else:
        orders,products=args.orders,args.products
        output=args.output or os.path.join(os.path.dirname(os.path.abspath(orders)),"Shopify_Analytics_Dashboard.xlsx")
    out,_=generate(orders,products,output)
    if args.open:
        try:
            if sys.platform.startswith("win"): os.startfile(out)
            elif sys.platform=="darwin": subprocess.run(["open",out])
            else: subprocess.run(["xdg-open",out])
        except Exception: pass

if __name__=="__main__":
    main()
