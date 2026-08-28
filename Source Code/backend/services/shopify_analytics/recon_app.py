# -*- coding: utf-8 -*-
"""
Studio By SY - Reconciliation & Dashboard Generator
====================================================
Pick a REFERENCE file/sheet and a FINAL CSV file/sheet, click Generate, and the
app produces:
  1) <name> - Reconciliation & Dashboard.xlsx   (formula-driven, auditable)
  2) <name> - Product Dashboard.pptx            (detailed deck, no mismatch info)

Inputs may be .xlsx or .csv. If an .xlsx has several sheets you choose which one.
No internet required. Excel formulas recalculate automatically when opened in
Excel; if LibreOffice is installed the app also pre-computes them.

Run:  double-click "Run Reconciliation App.bat"  (or:  python recon_app.py)
"""

import os, sys, csv, re, glob, tempfile, shutil, subprocess, threading, traceback, html as _html
from collections import OrderedDict, Counter

# ----------------------------------------------------------------------------- deps
def _need(mod, pip_name=None):
    try:
        return __import__(mod)
    except Exception:
        return None

import openpyxl
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.worksheet.properties import PageSetupProperties

def _fit_wide(ws):
    """Scale a sheet to one page wide for clean printing / PDF export."""
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

# python-pptx (for the deck)
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.oxml.ns import qn

# =============================================================================
#  DATA LOADING
# =============================================================================
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")

def _coerce(v):
    """Coerce CSV/text values to number or bool where sensible."""
    if v is None:
        return None
    if isinstance(v, (int, float, bool)):
        return v
    s = str(v)
    st = s.strip()
    if st == "":
        return None
    low = st.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if _NUM_RE.match(st):
        try:
            f = float(st)
            return int(f) if f.is_integer() else f
        except Exception:
            return s
    return s

def list_sheets(path):
    if path.lower().endswith((".xlsx", ".xlsm", ".xltx")):
        wb = load_workbook(path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
        return names
    return []  # csv

def _decode_bytes(raw):
    """Decode CSV/TSV bytes, guessing the encoding (fixes Windows-1252 / mojibake)."""
    if raw[:3] == b"\xef\xbb\xbf":
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    tries = []
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best and best.encoding:
            tries.append(best.encoding)
    except Exception:
        pass
    for enc in tries + ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")

def _read_xls(path, sheet=None):
    """Read a legacy .xls (or .xlsb) workbook via pandas; auto-install the engine."""
    import importlib.util
    engine = None
    if path.lower().endswith(".xlsb"):
        need, engine = "pyxlsb", "pyxlsb"
    else:
        need = "xlrd"
    if importlib.util.find_spec(need) is None:
        if getattr(sys, "frozen", False):
            # In the packaged .exe there is no pip; the engine should have been bundled.
            raise ValueError(f"This build cannot read {os.path.splitext(path)[1]} files. "
                             f"Please save the file as CSV or .xlsx and try again.")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                            "--disable-pip-version-check", need],
                           check=True, capture_output=True)
        except Exception:
            raise ValueError(f"Reading {os.path.splitext(path)[1]} files needs the '{need}' package. "
                             f"Please run:  pip install {need}")
    import pandas as pd
    kw = {"engine": engine} if engine else {}
    df = pd.read_excel(path, sheet_name=(sheet if sheet else 0), header=None, dtype=object, **kw)
    out = []
    for row in df.itertuples(index=False, name=None):
        out.append([None if (isinstance(c, float) and c != c) else c for c in row])  # NaN -> None
    return out

def read_table(path, sheet=None):
    """Return (header list, list-of-row-lists) from CSV/TSV or Excel (.xlsx/.xlsm/.xltx/.xls/.xlsb)."""
    ext = os.path.splitext(path)[1].lower()
    is_excel = ext in (".xlsx", ".xlsm", ".xltx", ".xls", ".xlsb")
    if ext in (".xlsx", ".xlsm", ".xltx"):
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    elif ext in (".xls", ".xlsb"):
        rows = _read_xls(path, sheet)
    else:  # csv / tsv / txt
        import io
        delim = "\t" if ext == ".tsv" else ","
        with open(path, "rb") as f:
            text = _decode_bytes(f.read()).lstrip("﻿")
        # StringIO (not splitlines) so multi-line quoted fields (e.g. Body HTML) parse correctly
        rows = [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
        rows = [[_coerce(c) for c in r] for r in rows]
    # trim trailing blank rows
    while rows and all(c is None or (isinstance(c, str) and c.strip() == "") for c in rows[-1]):
        rows.pop()
    if not rows:
        raise ValueError(f"No data found in {os.path.basename(path)}"
                         + (f" / sheet '{sheet}'" if sheet else ""))
    header = list(rows[0])
    ncol = len(header)
    data = [(r + [None] * (ncol - len(r)))[:ncol] for r in rows[1:]]
    # coerce booleans in Excel text too (Published stored as text, etc.)
    if is_excel:
        for r in data:
            for j, c in enumerate(r):
                if isinstance(c, str):
                    lc = c.strip().lower()
                    if lc in ("true", "false"):
                        r[j] = (lc == "true")
    return header, data

# ---- Body (HTML) -> plain comparison text ----------------------------------
# Product descriptions are compared on their WORDS only, so HTML tags, entities,
# punctuation, case and corrupted special characters (e.g. an apostrophe that a
# non-UTF-8 export turned into U+FFFD) do not create false mismatches. The
# original 'Body (HTML)' column is preserved untouched; this only feeds a helper
# 'Body (text)' column that the reconciliation formula compares.
_RE_SCRIPT = re.compile(r"(?is)<(script|style).*?</\1>")
_RE_TAG = re.compile(r"(?s)<[^>]+>")
_RE_KEEP = re.compile(r"[^0-9a-zÀ-ɏ ]+")  # keep letters (incl. accented), digits, space

def body_text_key(s):
    if s is None:
        return ""
    t = _RE_SCRIPT.sub(" ", str(s))
    t = _RE_TAG.sub(" ", t)
    t = _html.unescape(t).lower()
    t = _RE_KEEP.sub(" ", t)              # drop punctuation, entities, U+FFFD, quotes, dashes, etc.
    return re.sub(r"\s+", " ", t).strip()

def add_body_text_col(header, data):
    """Append a 'Body (text)' helper column (words-only form of 'Body (HTML)')."""
    if "Body (HTML)" not in header or "Body (text)" in header:
        return header, data
    bi = header.index("Body (HTML)")
    new_header = list(header) + ["Body (text)"]
    out = []
    for row in data:
        row = list(row)
        if len(row) < len(header):
            row += [None] * (len(header) - len(row))
        out.append(row + [body_text_key(row[bi] if bi < len(row) else "")])
    return new_header, out

# =============================================================================
#  ANALYSIS
# =============================================================================
def first_rows(header, data):
    idx = {h: i for i, h in enumerate(header) if h is not None}
    if "Handle" not in idx:
        raise ValueError("A 'Handle' column is required (Shopify product export). "
                         "None found in one of the inputs.")
    hi = idx["Handle"]
    seen = OrderedDict()
    for r in data:
        h = r[hi]
        if h in (None, ""):
            continue
        if h not in seen:
            seen[h] = r
    return idx, seen

# dashboard dimension candidates (first present + non-blank wins)
DIM_SPECS = [
    ("status",   "By Status",                          ["Status"]),
    # Category/Collection breakdown is driven by the 'Type' column (F), NOT the
    # Google 'Product Category' taxonomy (E). Type IS the category for this catalog.
    ("type",     "By Category (Type)",                 ["Type"]),
    ("subcat",   "By Item / Sub-Category",             ["Sub Category  (product.metafields.custom.sub_category)",
                                                        "Sub Category (product.metafields.custom.sub_category)",
                                                        "Sub Category", "Subcategory"]),
    ("vendor",   "By Vendor / Edit",                   ["Vendor"]),
    ("style",    "By Style / Fit",                     ["Style (product.metafields.custom.style)", "Style"]),
    ("color",    "By Colour",                          ["Color (product.metafields.custom.color)",
                                                        "Colour (product.metafields.custom.color)",
                                                        "Color (product.metafields.shopify.color-pattern)",
                                                        "Color", "Colour"]),
    ("material", "By Fabric / Material",               ["Material (product.metafields.custom.material)",
                                                        "Fabric (product.metafields.shopify.fabric)",
                                                        "Material", "Fabric"]),
]

def analyze(fin_hdr, fin_data, ref_hdr, ref_data):
    fi, fin_first = first_rows(fin_hdr, fin_data)
    ri, ref_first = first_rows(ref_hdr, ref_data)
    handles = list(fin_first.keys())
    for h in ref_first:
        if h not in fin_first:
            handles.append(h)
    handles = sorted(handles)
    common_fields = [h for h in fin_hdr if h in ri and h != "Handle"]
    # If the words-only 'Body (text)' helper exists, reconcile that instead of the
    # raw 'Body (HTML)' so markup / entities / special characters don't count as diffs.
    if "Body (text)" in common_fields and "Body (HTML)" in common_fields:
        common_fields = [h for h in common_fields if h != "Body (HTML)"]
    prod = list(fin_first.values())
    N = len(fin_first)

    def dist(colname):
        # Group case-INSENSITIVELY: the dashboard counts each label with a
        # case-insensitive COUNTIF, so listing "LIRA" and "Lira" as separate labels
        # would count the same rows twice (and push "(Not specified)" negative).
        # Merge case variants under the first-seen spelling.
        i = fi[colname]; blank = 0
        firstcase = {}; counts = {}
        for r in prod:
            v = r[i]
            if v is None or (isinstance(v, str) and v.strip() == ""):
                blank += 1
            else:
                s = str(v).strip(); k = s.lower()
                if k not in firstcase:
                    firstcase[k] = s
                counts[k] = counts.get(k, 0) + 1
        items = [(firstcase[k], counts[k]) for k in counts]
        items.sort(key=lambda kv: (-kv[1], kv[0].lower()))
        return items, blank

    def pick(cands):
        for name in cands:
            if name in fi:
                items, blank = dist(name)
                if items:  # has at least some data
                    return name, items, blank
        return None, None, None

    D = {"total": N, "brand": "Studio By SY"}
    dims = []  # (key, title, colname)
    for key, title, cands in DIM_SPECS:
        name, items, blank = pick(cands)
        if name is None:
            continue
        D[key] = {"col": name, "items": items, "blank": blank, "distinct": len(items)}
        dims.append((key, title, name))

    # KPIs
    if "Status" in fi:
        sc = Counter(str(r[fi["Status"]]).strip().lower() for r in prod if r[fi["Status"]] not in (None, ""))
        D["active"] = sc.get("active", 0); D["draft"] = sc.get("draft", 0); D["archived"] = sc.get("archived", 0)
    if "Published" in fi:
        pc = Counter(r[fi["Published"]] for r in prod)
        D["published"] = int(pc.get(True, 0)); D["not_published"] = int(pc.get(False, 0))
    if "Variant Price" in fi:
        pr = [r[fi["Variant Price"]] for r in prod if isinstance(r[fi["Variant Price"]], (int, float)) and not isinstance(r[fi["Variant Price"]], bool)]
        if pr:
            D["price_min"] = min(pr); D["price_max"] = max(pr)
            D["price_avg"] = round(sum(pr) / len(pr)); D["price_count"] = len(pr)

    return dict(handles=handles, common_fields=common_fields, fi=fi, ri=ri, D=D, dims=dims)

# =============================================================================
#  EXCEL WORKBOOK
# =============================================================================
ARIAL = "Arial"
def _F(sz=10, b=False, color="000000", it=False):
    return Font(name=ARIAL, size=sz, bold=b, color=color, italic=it)
_thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
CEN = Alignment(horizontal="center", vertical="center")
CENW = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")
LEFTT = Alignment(horizontal="left", vertical="top", wrap_text=True)
NAVY="1F3864"; BLUE="2E5496"; LBLUE="D9E1F2"; LBLUE2="EAF0FA"; GREY="F2F2F2"
GREEN_F="C6EFCE"; GREEN_T="006100"; RED_F="FFC7CE"; RED_T="9C0006"
AMBER_F="FFEB9C"; AMBER_T="9C6500"; GREYFILL="D9D9D9"; LINEC="E4D8DD"
def _fill(c): return PatternFill("solid", fgColor=c)

def build_workbook(a, out_path):
    fin_hdr, fin_data = a["_fin_hdr"], a["_fin_data"]
    ref_hdr, ref_data = a["_ref_hdr"], a["_ref_data"]
    handles = a["handles"]; common_fields = a["common_fields"]; D = a["D"]; dims = a["dims"]

    FIN_N=len(fin_data); REF_N=len(ref_data)
    FIN_LR=FIN_N+1; REF_LR=REF_N+1
    FIN_LC=get_column_letter(len(fin_hdr)); REF_LC=get_column_letter(len(ref_hdr))
    fin_idx={h:i for i,h in enumerate(fin_hdr) if h is not None}
    NH=len(handles); NF=len(common_fields)

    wb=Workbook(); wb.remove(wb.active)

    def hcell(ws,r,c,t,fillc=BLUE,fontc="FFFFFF",wrap=True,sz=9):
        cell=ws.cell(r,c,t); cell.font=_F(sz,True,fontc); cell.fill=_fill(fillc)
        cell.alignment=CENW if wrap else CEN; cell.border=BORDER; return cell
    def title_bar(ws,text,sub,ncols):
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=ncols)
        c=ws.cell(1,1,text); c.font=_F(15,True,"FFFFFF"); c.fill=_fill(NAVY)
        c.alignment=Alignment(horizontal="left",vertical="center",indent=1); ws.row_dimensions[1].height=30
        ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=ncols)
        c=ws.cell(2,1,sub); c.font=_F(9,False,"FFFFFF",it=True); c.fill=_fill(BLUE)
        c.alignment=Alignment(horizontal="left",vertical="center",indent=1); ws.row_dimensions[2].height=16

    # ---- data copies
    def write_copy(name,header,data):
        ws=wb.create_sheet(name)
        for j,h in enumerate(header,1):
            c=ws.cell(1,j,h); c.font=_F(9,True,"FFFFFF"); c.fill=_fill(NAVY); c.alignment=CENW; c.border=BORDER
        for i,row in enumerate(data,2):
            for j,v in enumerate(row,1):
                if isinstance(v,str) and v[:1] in ("=","+","-","@"):
                    cc=ws.cell(i,j); cc.value=v; cc.data_type="s"
                else:
                    ws.cell(i,j,v)
        ws.freeze_panes="B2"; ws.row_dimensions[1].height=28
        for j in range(1,len(header)+1): ws.column_dimensions[get_column_letter(j)].width=16
        ws.column_dimensions["A"].width=22; ws.column_dimensions["B"].width=26
        ws.sheet_properties.tabColor="808080"
    write_copy("Final CSV",fin_hdr,fin_data)
    write_copy("Reference File",ref_hdr,ref_data)

    FIN_ALL=f"'Final CSV'!$A$1:${FIN_LC}${FIN_LR}"
    FIN_H_ALL=f"'Final CSV'!$A$2:$A${FIN_LR}"; FIN_H1=f"'Final CSV'!$A$1:$A${FIN_LR}"
    FIN_HDR=f"'Final CSV'!$A$1:${FIN_LC}$1"; FIN_TITLE=f"'Final CSV'!$B$2:$B${FIN_LR}"
    REF_ALL=f"'Reference File'!$A$1:${REF_LC}${REF_LR}"
    REF_H_ALL=f"'Reference File'!$A$2:$A${REF_LR}"; REF_H1=f"'Reference File'!$A$1:$A${REF_LR}"
    REF_HDR=f"'Reference File'!$A$1:${REF_LC}$1"
    def FINcol(name):
        L=get_column_letter(fin_idx[name]+1); return f"'Final CSV'!${L}$2:${L}${FIN_LR}"

    # ================= Reconciliation
    recon=wb.create_sheet("Reconciliation"); recon.sheet_properties.tabColor=NAVY
    title_bar(recon,"RECONCILIATION REPORT  \u2014  'Final CSV'  vs  'Reference File'",
              "One row per product (Handle). Presence, duplicate check, and field-by-field match status. Green = match, Red = differs, \"-\" = not comparable.",20)
    DATA0=15; DATA1=DATA0+NH-1; TOTROW=DATA1+1
    Gc=f"$G${DATA0}:$G${DATA1}"; Hc=f"$H${DATA0}:$H${DATA1}"; Lc=f"$L${DATA0}:$L${DATA1}"; Kc=f"$K${DATA0}:$K${DATA1}"; Ac=f"$A${DATA0}:$A${DATA1}"
    def kpi(r,cl,label,cv,formula):
        lc=recon.cell(r,cl,label); lc.font=_F(10); lc.alignment=LEFT
        vc=recon.cell(r,cv); vc.value=formula; vc.font=_F(11,True,NAVY); vc.alignment=CEN; vc.fill=_fill(LBLUE); vc.border=BORDER
    h=recon.cell(4,1,"RECONCILIATION SUMMARY"); h.font=_F(11,True,"FFFFFF"); h.fill=_fill(BLUE)
    recon.merge_cells("A4:H4"); h.alignment=Alignment(horizontal="left",vertical="center",indent=1)
    kpi(5,1,"Total products (handles, both files)",3,f"=COUNTA({Ac})")
    kpi(6,1,"Matched in both files",3,f'=COUNTIF({Gc},"Matched")')
    kpi(7,1,"Missing in Final CSV",3,f'=COUNTIF({Gc},"Missing in Final CSV")')
    kpi(8,1,"Missing in Reference File",3,f'=COUNTIF({Gc},"Missing in Reference File")')
    kpi(9,1,"Duplicate products in Final CSV",3,f'=COUNTIF({Hc},"Yes")')
    kpi(10,1,"Products fully matching (all fields)",3,f'=COUNTIF({Lc},"Full Match")')
    kpi(11,1,"Products with >=1 field mismatch",3,f'=COUNTIF({Lc},"Field Mismatch*")')
    kpi(5,5,"Fields compared per product",7,f"=MAX($I${DATA0}:$I${DATA1})")
    kpi(6,5,"Total field-mismatch instances",7,f"=SUM({Kc})")
    kpi(7,5,"Final CSV total rows",7,f"=COUNTA({FIN_H_ALL})")
    kpi(8,5,"Reference File total rows",7,f"=COUNTA({REF_H_ALL})")
    kpi(9,5,"Final CSV products (Title rows)",7,f'=COUNTIF({FIN_TITLE},"?*")')
    kpi(10,5,"Handles only in Reference",7,f'=COUNTIF({Gc},"Missing in Final CSV")')
    kpi(11,5,"Handles only in Final",7,f'=COUNTIF({Gc},"Missing in Reference File")')

    idhdrs=["Handle","Title (Final)","Final Rows","Ref Rows","In Final?","In Ref?","Presence Status",
            "Dup Product? (Final)","Fields Compared","Fields Matched","Fields Mismatched","Match Status",
            "Mismatched Field(s)","_finRow","_refRow"]
    HROW=14
    for j,hh in enumerate(idhdrs,1): hcell(recon,HROW,j,hh,fillc=NAVY)
    FLAG_FIRST=16; FLAG_LAST=16+NF-1
    FLAG_F_L=get_column_letter(FLAG_FIRST); FLAG_L_L=get_column_letter(FLAG_LAST)
    for k,fld in enumerate(common_fields):
        col=FLAG_FIRST+k; hcell(recon,HROW,col,fld,fillc=BLUE,sz=8)
        cl=get_column_letter(col)
        ci=recon.cell(12,col); ci.value=f'=IFERROR(MATCH({cl}${HROW},{FIN_HDR},0),"")'; ci.font=_F(7,color="BFBFBF")
        rj=recon.cell(13,col); rj.value=f'=IFERROR(MATCH({cl}${HROW},{REF_HDR},0),"")'; rj.font=_F(7,color="BFBFBF")
    recon.row_dimensions[HROW].height=46

    for i,hnd in enumerate(handles):
        r=DATA0+i
        A=recon.cell(r,1,hnd); A.font=_F(9,True); A.alignment=LEFT
        recon.cell(r,14).value=f'=IFERROR(MATCH($A{r},{FIN_H1},0),"")'; recon.cell(r,14).font=_F(7,color="BFBFBF")
        recon.cell(r,15).value=f'=IFERROR(MATCH($A{r},{REF_H1},0),"")'; recon.cell(r,15).font=_F(7,color="BFBFBF")
        recon.cell(r,2).value=f'=IFERROR(INDEX({FIN_ALL},$N{r},MATCH("Title",{FIN_HDR},0)),"(only in Reference)")'
        recon.cell(r,3).value=f"=COUNTIF({FIN_H_ALL},$A{r})"
        recon.cell(r,4).value=f"=COUNTIF({REF_H_ALL},$A{r})"
        recon.cell(r,5).value=f'=IF($C{r}>0,"Yes","No")'
        recon.cell(r,6).value=f'=IF($D{r}>0,"Yes","No")'
        recon.cell(r,7).value=(f'=IF(AND($E{r}="Yes",$F{r}="Yes"),"Matched",'
                               f'IF($E{r}="Yes","Missing in Reference File",'
                               f'IF($F{r}="Yes","Missing in Final CSV","Not found")))')
        recon.cell(r,8).value=f'=IF(COUNTIFS({FIN_H_ALL},$A{r},{FIN_TITLE},"?*")>1,"Yes","No")'
        recon.cell(r,9).value=f'=COUNT(${FLAG_F_L}{r}:${FLAG_L_L}{r})'
        recon.cell(r,10).value=f'=COUNTIF(${FLAG_F_L}{r}:${FLAG_L_L}{r},1)'
        recon.cell(r,11).value=f'=COUNTIF(${FLAG_F_L}{r}:${FLAG_L_L}{r},0)'
        recon.cell(r,12).value=(f'=IF($G{r}<>"Matched",$G{r},IF($K{r}=0,"Full Match","Field Mismatch ("&$K{r}&")"))')
        recon.cell(r,13).value=ArrayFormula(f"M{r}",
            f'=_xlfn.TEXTJOIN(", ",TRUE,IF(${FLAG_F_L}{r}:${FLAG_L_L}{r}=0,${FLAG_F_L}${HROW}:${FLAG_L_L}${HROW},""))')
        for k in range(NF):
            col=FLAG_FIRST+k; cl=get_column_letter(col)
            f=(f'=IFERROR(IF(TRIM(INDEX({FIN_ALL},$N{r},{cl}$12)&"")='
               f'TRIM(INDEX({REF_ALL},$O{r},{cl}$13)&""),1,0),"-")')
            cc=recon.cell(r,col); cc.value=f; cc.alignment=CEN; cc.font=_F(8); cc.border=BORDER
        for j in range(1,14):
            cell=recon.cell(r,j); cell.border=BORDER
            if cell.alignment is None or cell.alignment.horizontal is None:
                cell.alignment=LEFT if j in (1,2,7,12,13) else CEN
            if cell.font is None: cell.font=_F(9)
        recon.cell(r,13).alignment=LEFTT; recon.cell(r,2).alignment=LEFT
        if i%2==1:
            for j in range(1,14):
                fg=recon.cell(r,j).fill.fgColor.rgb
                if fg in (None,"00000000"): recon.cell(r,j).fill=_fill(GREY)

    tc=recon.cell(TOTROW,1,"Products where field differs  \u2192"); tc.font=_F(9,True,"FFFFFF"); tc.fill=_fill(NAVY)
    tc.alignment=Alignment(horizontal="right",vertical="center")
    recon.merge_cells(start_row=TOTROW,start_column=1,end_row=TOTROW,end_column=15)
    for k in range(NF):
        col=FLAG_FIRST+k; cl=get_column_letter(col)
        cc=recon.cell(TOTROW,col); cc.value=f'=COUNTIF({cl}{DATA0}:{cl}{DATA1},0)'
        cc.font=_F(8,True,NAVY); cc.alignment=CEN; cc.fill=_fill(LBLUE); cc.border=BORDER

    flag_range=f"{FLAG_F_L}{DATA0}:{FLAG_L_L}{DATA1}"
    recon.conditional_formatting.add(flag_range,CellIsRule(operator="equal",formula=["1"],fill=_fill(GREEN_F),font=_F(8,color=GREEN_T)))
    recon.conditional_formatting.add(flag_range,CellIsRule(operator="equal",formula=["0"],fill=_fill(RED_F),font=_F(8,True,RED_T)))
    recon.conditional_formatting.add(flag_range,CellIsRule(operator="equal",formula=['"-"'],fill=_fill(GREYFILL)))
    msr=f"$L${DATA0}:$L${DATA1}"
    recon.conditional_formatting.add(msr,FormulaRule(formula=[f'ISNUMBER(SEARCH("Full Match",L{DATA0}))'],fill=_fill(GREEN_F),font=_F(9,True,GREEN_T)))
    recon.conditional_formatting.add(msr,FormulaRule(formula=[f'ISNUMBER(SEARCH("Field Mismatch",L{DATA0}))'],fill=_fill(AMBER_F),font=_F(9,True,AMBER_T)))
    recon.conditional_formatting.add(msr,FormulaRule(formula=[f'ISNUMBER(SEARCH("Missing",L{DATA0}))'],fill=_fill(RED_F),font=_F(9,True,RED_T)))
    psr=f"$G${DATA0}:$G${DATA1}"
    recon.conditional_formatting.add(psr,FormulaRule(formula=[f'ISNUMBER(SEARCH("Missing",G{DATA0}))'],fill=_fill(RED_F),font=_F(9,True,RED_T)))
    recon.conditional_formatting.add(psr,FormulaRule(formula=[f'EXACT(G{DATA0},"Matched")'],fill=_fill(GREEN_F),font=_F(9,GREEN_T)))
    for c,w in {"A":22,"B":30,"C":9,"D":9,"E":8,"F":8,"G":20,"H":16,"I":10,"J":9,"K":9,"L":18,"M":40}.items():
        recon.column_dimensions[c].width=w
    recon.column_dimensions["N"].hidden=True; recon.column_dimensions["O"].hidden=True
    for k in range(NF): recon.column_dimensions[get_column_letter(FLAG_FIRST+k)].width=4.2
    recon.row_dimensions[12].hidden=True; recon.row_dimensions[13].hidden=True
    recon.freeze_panes=recon.cell(DATA0,3)
    recon.auto_filter.ref=f"A{HROW}:{get_column_letter(15+NF)}{DATA1}"

    # ================= Mismatch Detail
    detail_fields=[f for f in [
        "Vendor","Type","Product Category","Status","Published","Title","Body (text)","Tags",
        "Image Src","SEO Title","SEO Description","Option1 Value","Option2 Value","Option3 Value",
        "Variant SKU","Variant Price","Variant Compare At Price",
        "Color (product.metafields.custom.color)","Material (product.metafields.custom.material)",
        "Fabric (product.metafields.shopify.fabric)",
        "Length of Bottom (product.metafields.custom.length_of_bottom)","Variant Image",
    ] if f in fin_idx and f in a["ri"]]
    if not detail_fields:
        detail_fields=common_fields[:min(20,len(common_fields))]
    md=wb.create_sheet("Mismatch Detail"); md.sheet_properties.tabColor="C55A11"
    title_bar(md,"FIELD MISMATCH DETAIL  (side-by-side values)",
              "Product-level values from each file. Filter 'Match?' = DIFF to see only differences. Comparison is trimmed & case-insensitive.",5)
    for j,hh in enumerate(["Handle","Field","Final CSV Value","Reference File Value","Match?"],1):
        hcell(md,4,j,hh,fillc=NAVY,wrap=False)
    row=5
    for hnd in handles:
        for fld in detail_fields:
            md.cell(row,1,hnd).font=_F(9); md.cell(row,2,fld).font=_F(9)
            fval=(f'=IFERROR(IF(INDEX({FIN_ALL},MATCH($A{row},{FIN_H1},0),MATCH($B{row},{FIN_HDR},0))&""="","(blank)",'
                  f'INDEX({FIN_ALL},MATCH($A{row},{FIN_H1},0),MATCH($B{row},{FIN_HDR},0))),"(missing)")')
            rval=(f'=IFERROR(IF(INDEX({REF_ALL},MATCH($A{row},{REF_H1},0),MATCH($B{row},{REF_HDR},0))&""="","(blank)",'
                  f'INDEX({REF_ALL},MATCH($A{row},{REF_H1},0),MATCH($B{row},{REF_HDR},0))),"(missing)")')
            md.cell(row,3).value=fval; md.cell(row,4).value=rval
            md.cell(row,5).value=f'=IF(TRIM($C{row}&"")=TRIM($D{row}&""),"OK","DIFF")'
            for j in range(1,6):
                c=md.cell(row,j); c.border=BORDER
                c.alignment=LEFTT if j in (3,4) else (LEFT if j<=2 else CEN)
                if c.font is None: c.font=_F(9)
            row+=1
    MD_LAST=row-1
    md.conditional_formatting.add(f"$E$5:$E${MD_LAST}",CellIsRule(operator="equal",formula=['"DIFF"'],fill=_fill(RED_F),font=_F(9,True,RED_T)))
    md.conditional_formatting.add(f"$E$5:$E${MD_LAST}",CellIsRule(operator="equal",formula=['"OK"'],fill=_fill(GREEN_F),font=_F(9,color=GREEN_T)))
    for c,w in {"A":22,"B":30,"C":60,"D":60,"E":9}.items(): md.column_dimensions[c].width=w
    md.freeze_panes="A5"; md.auto_filter.ref=f"A4:E{MD_LAST}"

    # ---- helpers shared by the reconciliation sheets below
    ref_idx = a["ri"]
    def _colrange(sheet, colname, idxmap, lastrow):
        if colname not in idxmap: return None
        L = get_column_letter(idxmap[colname] + 1)
        return f"'{sheet}'!${L}$2:${L}${lastrow}"
    def _first_vals(data, idxmap, colname):
        # product-level distinct values: value -> product count (first row per Handle)
        if colname not in idxmap or "Handle" not in idxmap: return OrderedDict()
        hi = idxmap["Handle"]; ci = idxmap[colname]; out = OrderedDict(); seen = set()
        for row in data:
            h = row[hi] if hi < len(row) else None
            if h is None or (isinstance(h, str) and h.strip() == "") or h in seen: continue
            seen.add(h)
            v = row[ci] if ci < len(row) else ""
            v = ("" if v is None else str(v)).strip()
            out[v] = out.get(v, 0) + 1
        return out
    def _xlq(s):  # escape a literal for a COUNTIF/COUNTIFS text criterion
        return str(s).replace("~", "~~").replace("*", "~*").replace("?", "~?").replace('"', '""')
    REF_TITLE = f"'Reference File'!$B$2:$B${REF_LR}"

    # ================= Type Reconciliation  (Reference vs Final, field: Type)
    if "Type" in fin_idx and "Type" in ref_idx:
        FIN_TYPE = _colrange("Final CSV", "Type", fin_idx, FIN_LR)
        REF_TYPE = _colrange("Reference File", "Type", ref_idx, REF_LR)
        rtypes = _first_vals(ref_data, ref_idx, "Type")
        ftypes = _first_vals(fin_data, fin_idx, "Type")
        allt = set(rtypes) | set(ftypes)
        nb = sorted([t for t in allt if t != ""], key=lambda t: (-(rtypes.get(t, 0) + ftypes.get(t, 0)), t.lower()))
        ordered = nb + ([""] if "" in allt else [])

        tr = wb.create_sheet("Type Reconciliation"); tr.sheet_properties.tabColor = "7030A0"
        title_bar(tr, "TYPE RECONCILIATION  —  Reference vs Final   (field: Type)",
                  "Category = the Type column ONLY (not Product Category or any mapping). One count per product (Handle). Every number is a live formula.", 5)
        sh = tr.cell(4, 1, "SUMMARY"); sh.font = _F(11, True, "FFFFFF"); sh.fill = _fill(BLUE)
        tr.merge_cells("A4:E4"); sh.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        HR = 8
        for j, hh in enumerate(["Type", "Reference Count", "Final Count", "Difference (Final-Ref)", "Status"], 1):
            hcell(tr, HR, j, hh, fillc=NAVY, wrap=True, sz=10)
        r0 = HR + 1
        for i, t in enumerate(ordered):
            r = r0 + i
            lab = "(blank / no Type)" if t == "" else t
            lc = tr.cell(r, 1, lab); lc.font = _F(9, it=(t == "")); lc.alignment = LEFT; lc.border = BORDER
            if t == "":
                rf = f'=COUNTIF({REF_TITLE},"?*")-COUNTIFS({REF_TITLE},"?*",{REF_TYPE},"?*")'
                ff = f'=COUNTIF({FIN_TITLE},"?*")-COUNTIFS({FIN_TITLE},"?*",{FIN_TYPE},"?*")'
            else:
                q = _xlq(t)
                rf = f'=COUNTIFS({REF_TITLE},"?*",{REF_TYPE},"{q}")'
                ff = f'=COUNTIFS({FIN_TITLE},"?*",{FIN_TYPE},"{q}")'
            bc = tr.cell(r, 2); bc.value = rf; bc.font = _F(9); bc.alignment = CEN; bc.border = BORDER
            cc = tr.cell(r, 3); cc.value = ff; cc.font = _F(9); cc.alignment = CEN; cc.border = BORDER
            dc = tr.cell(r, 4); dc.value = f"=C{r}-B{r}"; dc.font = _F(9); dc.alignment = CEN; dc.border = BORDER
            sc = tr.cell(r, 5)
            sc.value = f'=IF(B{r}=C{r},"Match",IF(B{r}=0,"Only in Final",IF(C{r}=0,"Only in Reference","Count differs")))'
            sc.font = _F(9); sc.alignment = CEN; sc.border = BORDER
        rlast = r0 + len(ordered) - 1
        trow = rlast + 1
        tc = tr.cell(trow, 1, "TOTAL"); tc.font = _F(9, True); tc.fill = _fill(LBLUE); tc.alignment = LEFT; tc.border = BORDER
        for col in (2, 3, 4):
            cc = tr.cell(trow, col); cc.value = f"=SUM({get_column_letter(col)}{r0}:{get_column_letter(col)}{rlast})"
            cc.font = _F(9, True); cc.fill = _fill(LBLUE); cc.alignment = CEN; cc.border = BORDER
        tr.cell(trow, 5).fill = _fill(LBLUE); tr.cell(trow, 5).border = BORDER
        STAT_RNG = f"$E${r0}:$E${rlast}"
        def trk(r, c, label, cv, formula):
            lc = tr.cell(r, c, label); lc.font = _F(10); lc.alignment = LEFT
            vc = tr.cell(r, cv); vc.value = formula; vc.number_format = "#,##0"; vc.font = _F(11, True, NAVY)
            vc.alignment = CEN; vc.fill = _fill(LBLUE); vc.border = BORDER
        trk(5, 1, "Total Reference products", 3, f'=COUNTIF({REF_TITLE},"?*")')
        trk(6, 1, "Total Final products", 3, f'=COUNTIF({FIN_TITLE},"?*")')
        trk(5, 4, "Types matching (count equal)", 5, f'=COUNTIF({STAT_RNG},"Match")')
        trk(6, 4, "Type values with a difference", 5,
            f'=COUNTIF({STAT_RNG},"Count differs")+COUNTIF({STAT_RNG},"Only in Reference")+COUNTIF({STAT_RNG},"Only in Final")')
        if "Type" in common_fields:
            tf = get_column_letter(FLAG_FIRST + common_fields.index("Type"))
            tflag = f"Reconciliation!${tf}${DATA0}:${tf}${DATA1}"
            trk(7, 1, "Products whose Type changed", 3, f'=COUNTIF({tflag},0)')
            trk(7, 4, "Products with matching Type", 5, f'=COUNTIF({tflag},1)')
        tr.conditional_formatting.add(STAT_RNG, CellIsRule(operator="equal", formula=['"Match"'], fill=_fill(GREEN_F), font=_F(9, color=GREEN_T)))
        tr.conditional_formatting.add(STAT_RNG, FormulaRule(formula=[f'E{r0}<>"Match"'], fill=_fill(AMBER_F), font=_F(9, True, AMBER_T)))
        for c, w in {"A": 30, "B": 16, "C": 14, "D": 20, "E": 18}.items(): tr.column_dimensions[c].width = w
        tr.freeze_panes = tr.cell(r0, 1); tr.auto_filter.ref = f"A{HR}:E{rlast}"; _fit_wide(tr)

    # ================= SKU Reconciliation (variant-level, field: Variant SKU)
    if "Variant SKU" in fin_idx and "Variant SKU" in ref_idx:
        FIN_SKU = _colrange("Final CSV", "Variant SKU", fin_idx, FIN_LR)
        REF_SKU = _colrange("Reference File", "Variant SKU", ref_idx, REF_LR)
        FIN_HND = f"'Final CSV'!$A$2:$A${FIN_LR}"; REF_HND = f"'Reference File'!$A$2:$A${REF_LR}"
        DREF = f'SUMPRODUCT(({REF_SKU}<>"")/COUNTIF({REF_SKU},{REF_SKU}&""))'
        DFIN = f'SUMPRODUCT(({FIN_SKU}<>"")/COUNTIF({FIN_SKU},{FIN_SKU}&""))'
        rows = [
            ("Reference SKU rows (non-blank)", f'=COUNTIF({REF_SKU},"?*")', "Variant rows in Reference that carry a SKU."),
            ("Final SKU rows (non-blank)", f'=COUNTIF({FIN_SKU},"?*")', "Variant rows in Final that carry a SKU."),
            ("Distinct Reference SKUs", f'={DREF}', "Unique SKU values in Reference (blanks ignored)."),
            ("Distinct Final SKUs", f'={DFIN}', "Unique SKU values in Final (blanks ignored)."),
            ("SKUs in both files (matched)", f'=SUMPRODUCT(({REF_SKU}<>"")*(COUNTIF({FIN_SKU},{REF_SKU})>0)/COUNTIF({REF_SKU},{REF_SKU}&""))', "Distinct SKUs present in Reference AND Final."),
            ("SKUs only in Reference (missing in Final)", f'=SUMPRODUCT(({REF_SKU}<>"")*(COUNTIF({FIN_SKU},{REF_SKU})=0)/COUNTIF({REF_SKU},{REF_SKU}&""))', "Distinct SKUs in Reference not found in Final."),
            ("SKUs only in Final (extra)", f'=SUMPRODUCT(({FIN_SKU}<>"")*(COUNTIF({REF_SKU},{FIN_SKU})=0)/COUNTIF({FIN_SKU},{FIN_SKU}&""))', "Distinct SKUs in Final not found in Reference."),
            ("Duplicate SKU rows in Reference", f'=COUNTIF({REF_SKU},"?*")-{DREF}', "Non-blank SKU rows minus distinct SKUs (0 = no duplicates)."),
            ("Duplicate SKU rows in Final", f'=COUNTIF({FIN_SKU},"?*")-{DFIN}', "Non-blank SKU rows minus distinct SKUs (0 = no duplicates)."),
            ("Blank SKU rows in Reference", f'=({REF_LR}-1)-COUNTIF({REF_SKU},"?*")', "Variant rows in Reference with no SKU."),
            ("Blank SKU rows in Final", f'=({FIN_LR}-1)-COUNTIF({FIN_SKU},"?*")', "Variant rows in Final with no SKU."),
            ("SKUs mapped to a DIFFERENT product", f'=SUMPRODUCT(({FIN_SKU}<>"")*(COUNTIFS({REF_SKU},{FIN_SKU},{REF_HND},"<>"&{FIN_HND})>0))', "Final SKU rows whose SKU exists in Reference under a different Handle."),
        ]
        sk = wb.create_sheet("SKU Reconciliation"); sk.sheet_properties.tabColor = "1F6F54"
        title_bar(sk, "SKU RECONCILIATION  —  Reference vs Final   (field: Variant SKU)",
                  "Variant-level SKU presence, duplicate, blank and SKU→product consistency checks. Distinct counts ignore blanks. Every number is a live formula.", 3)
        hcell(sk, 4, 1, "Check", fillc=NAVY, wrap=False); hcell(sk, 4, 2, "Value", fillc=NAVY, wrap=False)
        hcell(sk, 4, 3, "What it means", fillc=NAVY, wrap=False)
        r = 5
        for label, formula, note in rows:
            lc = sk.cell(r, 1, label); lc.font = _F(10); lc.alignment = LEFT; lc.border = BORDER
            vc = sk.cell(r, 2); vc.value = formula; vc.number_format = "#,##0"; vc.font = _F(11, True, NAVY)
            vc.alignment = CEN; vc.fill = _fill(LBLUE); vc.border = BORDER
            nc = sk.cell(r, 3, note); nc.font = _F(9, it=True, color="606060"); nc.alignment = LEFTT; nc.border = BORDER
            r += 1
        for c, w in {"A": 42, "B": 14, "C": 62}.items(): sk.column_dimensions[c].width = w
        sk.freeze_panes = "A5"; _fit_wide(sk)

    # ================= Field Summary  (per shared field: how many products differ)
    fs = wb.create_sheet("Field Summary"); fs.sheet_properties.tabColor = "C55A11"
    title_bar(fs, "FIELD-LEVEL MISMATCH SUMMARY  —  where the two files differ",
              "For each shared field: how many products differ (product-level, first row per Handle). A high % usually means a store-level difference (image URLs, market pricing), not a data error.", 5)
    for j, hh in enumerate(["Field", "Products Differ", "Products Compared", "% Differ", "Assessment"], 1):
        hcell(fs, 4, j, hh, fillc=NAVY, wrap=True, sz=10)
    r = 5
    for k, fld in enumerate(common_fields):
        fl = get_column_letter(FLAG_FIRST + k)
        flagRange = f"Reconciliation!${fl}${DATA0}:${fl}${DATA1}"
        lc = fs.cell(r, 1, fld); lc.font = _F(9); lc.alignment = LEFT; lc.border = BORDER
        dc = fs.cell(r, 2); dc.value = f'=COUNTIF({flagRange},0)'; dc.font = _F(9); dc.alignment = CEN; dc.border = BORDER
        cc = fs.cell(r, 3); cc.value = f'=COUNT({flagRange})'; cc.font = _F(9); cc.alignment = CEN; cc.border = BORDER
        pc = fs.cell(r, 4); pc.value = f'=IFERROR(B{r}/C{r},0)'; pc.number_format = "0.0%"; pc.font = _F(9); pc.alignment = CEN; pc.border = BORDER
        ac = fs.cell(r, 5)
        ac.value = f'=IF(B{r}=0,"All match",IF(D{r}>=0.5,"Bulk difference — likely store-level (review)","Review "&B{r}&" product(s)"))'
        ac.font = _F(9); ac.alignment = LEFT; ac.border = BORDER
        r += 1
    fs_last = r - 1
    fs.conditional_formatting.add(f"$B$5:$B${fs_last}", CellIsRule(operator="greaterThan", formula=["0"], fill=_fill(AMBER_F), font=_F(9, True, AMBER_T)))
    fs.conditional_formatting.add(f"$B$5:$B${fs_last}", CellIsRule(operator="equal", formula=["0"], fill=_fill(GREEN_F), font=_F(9, color=GREEN_T)))
    for c, w in {"A": 50, "B": 14, "C": 16, "D": 10, "E": 46}.items(): fs.column_dimensions[c].width = w
    fs.freeze_panes = "A5"; fs.auto_filter.ref = f"A4:E{fs_last}"; _fit_wide(fs)

    # ================= Dashboard (Final CSV only)
    dash=wb.create_sheet("Dashboard"); dash.sheet_properties.tabColor="2E7D32"
    title_bar(dash,f"PRODUCT DASHBOARD  \u2014  {D.get('brand','Product')}",
              "All figures computed with live formulas from the 'Final CSV' sheet ONLY (one count per product / Handle).",9)
    TOTAL_CELL="$C$5"
    has_status="Status" in fin_idx; has_pub="Published" in fin_idx; has_price="Variant Price" in fin_idx
    STAT=FINcol("Status") if has_status else None
    PUB=FINcol("Published") if has_pub else None
    TITLE=FINcol("Title") if "Title" in fin_idx else FINcol("Handle")
    def kpi_card(r,label,formula,fmt="0",note=""):
        lc=dash.cell(r,1,label); lc.font=_F(10); lc.alignment=LEFT; lc.border=BORDER
        vc=dash.cell(r,3); vc.value=formula; vc.number_format=fmt; vc.font=_F(12,True,NAVY); vc.alignment=CEN; vc.fill=_fill(LBLUE); vc.border=BORDER
        dash.cell(r,2).border=BORDER
        if note:
            nc=dash.cell(r,4,note); nc.font=_F(8,it=True,color="808080"); nc.alignment=LEFT
    h=dash.cell(4,1,"KEY METRICS"); h.font=_F(11,True,"FFFFFF"); h.fill=_fill(BLUE); dash.merge_cells("A4:D4")
    h.alignment=Alignment(horizontal="left",vertical="center",indent=1)
    kpi_card(5,"Total Products",f'=COUNTIF({TITLE},"?*")')
    rr=6
    if has_status:
        kpi_card(6,"Active Products",f'=COUNTIF({STAT},"active")'); kpi_card(7,"Draft Products",f'=COUNTIF({STAT},"draft")')
        kpi_card(8,"Archived Products",f'=COUNTIF({STAT},"archived")',note="(0 if no 'archived' status present)"); rr=9
    if has_pub:
        kpi_card(rr,"Published (online)",f"=COUNTIF({PUB},TRUE)"); kpi_card(rr+1,"Not Published",f"=COUNTIF({PUB},FALSE)"); rr+=2
    if has_status:
        kpi_card(rr,"Check: Active+Draft+Archived",f"=$C$6+$C$7+$C$8",note="should equal Total Products"); rr+=1

    price_last=rr
    if has_price:
        PRICE=FINcol("Variant Price")
        hh=dash.cell(rr+1,1,"PRICING (first variant / product)"); hh.font=_F(11,True,"FFFFFF"); hh.fill=_fill(BLUE)
        dash.merge_cells(start_row=rr+1,start_column=1,end_row=rr+1,end_column=4); hh.alignment=Alignment(horizontal="left",vertical="center",indent=1)
        kpi_card(rr+2,"Min Price",f'=_xlfn.MINIFS({PRICE},{TITLE},"?*")',fmt="#,##0")
        kpi_card(rr+3,"Max Price",f'=_xlfn.MAXIFS({PRICE},{TITLE},"?*")',fmt="#,##0")
        kpi_card(rr+4,"Average Price",f'=IFERROR(AVERAGEIFS({PRICE},{TITLE},"?*"),0)',fmt="#,##0")
        price_last=rr+4

    def dim_table(start_row,c0,title,colname):
        d=D[[k for k,_,cn in dims if cn==colname][0]] if any(cn==colname for _,_,cn in dims) else None
        labels=[it[0] for it in d["items"]]
        col=get_column_letter(fin_idx[colname]+1); rng=f"'Final CSV'!${col}$2:${col}${FIN_LR}"
        dash.merge_cells(start_row=start_row,start_column=c0,end_row=start_row,end_column=c0+2)
        tc=dash.cell(start_row,c0,title); tc.font=_F(11,True,"FFFFFF"); tc.fill=_fill(BLUE)
        tc.alignment=Alignment(horizontal="left",vertical="center",indent=1)
        hr=start_row+1
        hcell(dash,hr,c0,"Category",fillc=NAVY,wrap=False); hcell(dash,hr,c0+1,"Products",fillc=NAVY,wrap=False); hcell(dash,hr,c0+2,"% of Total",fillc=NAVY,wrap=False)
        r=hr+1
        for lab in labels:
            lc=dash.cell(r,c0,lab); lc.font=_F(9); lc.alignment=LEFT; lc.border=BORDER
            vc=dash.cell(r,c0+1); safe=str(lab).replace('"','""'); vc.value=f'=COUNTIF({rng},"{safe}")'
            vc.font=_F(9); vc.alignment=CEN; vc.border=BORDER
            pc=dash.cell(r,c0+2); pc.value=f"={get_column_letter(c0+1)}{r}/{TOTAL_CELL}"; pc.number_format="0.0%"; pc.font=_F(9); pc.alignment=CEN; pc.border=BORDER
            r+=1
        lc=dash.cell(r,c0,"(Not specified)"); lc.font=_F(9,it=True); lc.alignment=LEFT; lc.border=BORDER
        vc=dash.cell(r,c0+1); vc.value=f"={TOTAL_CELL}-SUM({get_column_letter(c0+1)}{hr+1}:{get_column_letter(c0+1)}{r-1})"; vc.font=_F(9,it=True); vc.alignment=CEN; vc.border=BORDER
        pc=dash.cell(r,c0+2); pc.value=f"={get_column_letter(c0+1)}{r}/{TOTAL_CELL}"; pc.number_format="0.0%"; pc.font=_F(9,it=True); pc.alignment=CEN; pc.border=BORDER
        r+=1
        lc=dash.cell(r,c0,"TOTAL"); lc.font=_F(9,True); lc.fill=_fill(LBLUE); lc.alignment=LEFT; lc.border=BORDER
        vc=dash.cell(r,c0+1); vc.value=f"=SUM({get_column_letter(c0+1)}{hr+1}:{get_column_letter(c0+1)}{r-1})"; vc.font=_F(9,True); vc.fill=_fill(LBLUE); vc.alignment=CEN; vc.border=BORDER
        pc=dash.cell(r,c0+2); pc.value=f"={get_column_letter(c0+1)}{r}/{TOTAL_CELL}"; pc.number_format="0.0%"; pc.font=_F(9,True); pc.fill=_fill(LBLUE); pc.alignment=CEN; pc.border=BORDER
        return r

    left=[(k,t,cn) for k,t,cn in dims if D[k]["distinct"]<=15]
    right=[(k,t,cn) for k,t,cn in dims if D[k]["distinct"]>15]
    rL=max(price_last+2,18)
    for k,t,cn in left:
        rL=dim_table(rL,1,t.upper()+f"  (field: {cn.split(' (')[0]})",cn)+2
    rR=18
    for k,t,cn in right:
        rR=dim_table(rR,6,t.upper()+f"  ({cn.split('(')[-1].rstrip(')') if '(' in cn else cn})",cn)+2
    for c,w in {"A":34,"B":11,"C":11,"D":30,"E":3,"F":42,"G":11,"H":11}.items(): dash.column_dimensions[c].width=w
    dash.freeze_panes="A4"

    # ================= Read Me
    readme=wb.create_sheet("Read Me",0); readme.sheet_properties.tabColor="7030A0"
    readme.column_dimensions["A"].width=3; readme.column_dimensions["B"].width=40; readme.column_dimensions["C"].width=100
    title_bar(readme,f"READ ME  \u2014  {D.get('brand','')} Reconciliation & Dashboard","How this workbook is built, what each sheet shows, and the assumptions used.",3)
    lines=[
        ("Purpose","Reconcile the 'Final CSV' sheet against the 'Reference File' sheet and provide a product dashboard driven entirely by the Final CSV."),
        ("Source",f"Copied (as values) from the uploaded files. Final CSV = {FIN_N} rows; Reference File = {REF_N} rows. Shopify product exports keyed by Handle."),
        ("Granularity","Reconciliation is at PRODUCT level (one row per Handle). Product attributes are taken from each product's first (Title) row."),
        ("Lookup method","Formula-driven with INDEX + MATCH (not XLOOKUP, which does not recalculate in LibreOffice). Counts use COUNTIF / COUNTIFS / MINIFS / MAXIFS / AVERAGEIFS."),
        ("Match logic","Field match = trimmed, case-insensitive string equality. Formatting/order differences count as a mismatch, so nothing is hidden."),
        ("Body description","The product description is reconciled on its WORDS only: a 'Body (text)' helper strips HTML tags, entities, punctuation, case and corrupted special characters (e.g. an apostrophe an export turned into a replacement char), so only real wording differences are flagged. The original 'Body (HTML)' is preserved in the data sheets."),
        ("Sheet: Reconciliation","Presence, duplicate check, per-field match flags (1=match, 0=differ, '-' n/a), matched/mismatched counts, a Match Status, and the list of mismatched fields. Bottom row totals how many products differ on each field."),
        ("Sheet: Type Reconciliation","Reference vs Final product counts for every value in the 'Type' column (Type = category, taken directly from the Type column - NOT Product Category or any mapping): Type, Reference Count, Final Count, Difference and Status. Includes blank / Reference-only / Final-only types and how many products changed Type."),
        ("Sheet: SKU Reconciliation","Variant-level checks on 'Variant SKU': non-blank rows, distinct SKUs, matched / missing / extra, duplicates, blanks, and SKUs whose product (Handle) differs between the two files."),
        ("Sheet: Field Summary","For every shared field, how many products differ. A high % (e.g. Image Src, Variant Price) usually means a store-level difference, not a data error - use it to tell data differences from reconciliation issues."),
        ("Sheet: Dashboard","All counts computed with formulas from 'Final CSV' ONLY. Category labels are fixed keys; every number is a live formula."),
        ("Sheet: Mismatch Detail","Side-by-side Final vs Reference values. AutoFilter 'Match?' = DIFF for differences only."),
        ("Sheet: Final CSV / Reference File","Verbatim value copies of the inputs, so the workbook is self-contained."),
        ("Note","If both files contain the same Handles, 'Missing' counts are 0 - the logic is still live and populates if data changes."),
        ("Generated by",f"{D.get('brand','')} Reconciliation & Dashboard Generator."),
    ]
    r=4
    for aa,bb in lines:
        bc=readme.cell(r,2); bc.value=aa; bc.font=_F(10,True,NAVY); bc.alignment=LEFTT
        cc=readme.cell(r,3);
        if isinstance(bb,str) and bb[:1] in ("=","+","-","@"): cc.value=bb; cc.data_type="s"
        else: cc.value=bb
        cc.font=_F(10); cc.alignment=LEFTT
        readme.row_dimensions[r].height=30 if len(bb)>90 else 16
        if len(bb)>180: readme.row_dimensions[r].height=46
        r+=1
    readme.sheet_view.showGridLines=False

    order=["Read Me","Dashboard","Reconciliation","Type Reconciliation","SKU Reconciliation",
           "Field Summary","Mismatch Detail","Final CSV","Reference File"]
    wb._sheets.sort(key=lambda s: order.index(s.title) if s.title in order else 99)
    wb.save(out_path)
    return dict(recon_rows=(DATA0,DATA1),flags=(FLAG_F_L,FLAG_L_L),md_last=MD_LAST)

# =============================================================================
#  RECALC (LibreOffice, optional)
# =============================================================================
def find_soffice():
    for p in [r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]:
        if os.path.exists(p):
            return p
    w = shutil.which("soffice")
    return w

_REG = '''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>'''

def recalc_excel(path, log=print, timeout=300):
    soffice = find_soffice()
    if not soffice:
        log("LibreOffice not found - skipping pre-compute (Excel will recalc on open).")
        return False
    try:
        profile = tempfile.mkdtemp(prefix="lo_p_")
        user = os.path.join(profile, "user"); os.makedirs(user, exist_ok=True)
        with open(os.path.join(user, "registrymodifications.xcu"), "w", encoding="utf-8") as f:
            f.write(_REG)
        outdir = tempfile.mkdtemp(prefix="lo_o_")
        url = "file:///" + profile.replace("\\", "/")
        cmd = [soffice, "--headless", "--nologo", "--norestore", f"-env:UserInstallation={url}",
               "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", outdir, os.path.abspath(path)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        outs = glob.glob(os.path.join(outdir, "*.xlsx"))
        if outs:
            shutil.copy(outs[0], path); log("Formulas pre-computed with LibreOffice.")
            ok = True
        else:
            log("LibreOffice recalc produced no file - Excel will recalc on open."); ok = False
        shutil.rmtree(profile, ignore_errors=True); shutil.rmtree(outdir, ignore_errors=True)
        return ok
    except Exception as e:
        log(f"Recalc skipped ({e}). Excel will recalc on open.")
        return False

# =============================================================================
#  POWERPOINT (python-pptx)
# =============================================================================
INK="2E1F2E"; INK2="3B2A3A"; INK3="352438"; PLUM="6D2E46"; ROSE="B5838D"; GOLD="B08D57"
TAUPE="9C8B7A"; SAGE="8AA399"; SLATE="5B7B8A"; MAUVE="A26769"; SAND="D8C3A5"
CARD="F5EFF1"; CARD2="FAF6F2"; WHITE="FFFFFF"; TX="2E1F2E"; MUTED="8A7A84"
SERIF="Century Schoolbook"; SANS="Calibri"; GREEN="2C7A4B"
def _rgb(h): return RGBColor.from_string(h)

def _shadow(shape):
    spPr=shape._element.spPr
    old=spPr.find(qn('a:effectLst'))
    if old is not None: spPr.remove(old)
    eff=spPr.makeelement(qn('a:effectLst'),{})
    o=eff.makeelement(qn('a:outerShdw'),{'blurRad':'55000','dist':'28000','dir':'5400000','rotWithShape':'0'})
    c=o.makeelement(qn('a:srgbClr'),{'val':'C9B7BF'}); al=c.makeelement(qn('a:alpha'),{'val':'42000'})
    c.append(al); o.append(c); eff.append(o); spPr.append(eff)

class Deck:
    def __init__(self):
        self.p=Presentation(); self.p.slide_width=Inches(13.333); self.p.slide_height=Inches(7.5)
        self.blank=self.p.slide_layouts[6]; self.PW=13.333; self.PH=7.5; self.M=0.6; self.page=0
    def slide(self,bg=WHITE):
        s=self.p.slides.add_slide(self.blank)
        r=s.background.fill; r.solid(); r.fore_color.rgb=_rgb(bg); return s
    def txt(self,s,x,y,w,h,text,size=14,color=TX,bold=False,italic=False,face=SANS,
            align=PP_ALIGN.LEFT,anchor=MSO_ANCHOR.TOP,spacing=None,line=None,wrap=True):
        tb=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=tb.text_frame
        tf.word_wrap=wrap
        for m in ("margin_left","margin_right","margin_top","margin_bottom"): setattr(tf,m,0)
        tf.vertical_anchor=anchor
        runs=text if isinstance(text,list) else [(text,{})]
        p=tf.paragraphs[0]; p.alignment=align
        if line is not None: p.line_spacing=line
        for i,(t,o) in enumerate(runs):
            run=p.add_run(); run.text=t; fnt=run.font
            fnt.size=Pt(o.get("size",size)); fnt.bold=o.get("bold",bold); fnt.italic=o.get("italic",italic)
            fnt.name=o.get("face",face); fnt.color.rgb=_rgb(o.get("color",color))
            if spacing is not None:
                _set_spacing(run,o.get("spacing",spacing))
        return tb
    def rect(self,s,x,y,w,h,fill=CARD,line=None,radius=0.08,shadow=False):
        shp=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                               Inches(x),Inches(y),Inches(w),Inches(h))
        try: shp.adjustments[0]=radius
        except Exception: pass
        shp.fill.solid(); shp.fill.fore_color.rgb=_rgb(fill)
        if line: shp.line.color.rgb=_rgb(line); shp.line.width=Pt(0.75)
        else: shp.line.fill.background()
        if shadow: _shadow(shape=shp)
        else: shp.shadow.inherit=False
        return shp
    def ellipse(self,s,x,y,w,h,fill):
        shp=s.shapes.add_shape(MSO_SHAPE.OVAL,Inches(x),Inches(y),Inches(w),Inches(h))
        shp.fill.solid(); shp.fill.fore_color.rgb=_rgb(fill); shp.line.fill.background(); shp.shadow.inherit=False
        return shp

def _set_spacing(run,val):
    rPr=run._r.get_or_add_rPr(); rPr.set('spc',str(int(val*100)))

def _chart_common(chart):
    chart.has_title=False
    try:
        chart.font.name=SANS; chart.font.size=Pt(11)
    except Exception: pass

def _style_donut(gf, colors, values):
    chart=gf.chart; _chart_common(chart)
    plot=chart.plots[0]; plot.has_data_labels=True
    dl=plot.data_labels; dl.number_format='0'; dl.number_format_is_linked=False
    dl.font.size=Pt(13); dl.font.bold=True; dl.font.name=SANS; dl.font.color.rgb=_rgb(WHITE)
    try: dl.position=XL_LABEL_POSITION.CENTER
    except Exception: pass
    ser=plot.series[0]
    for i,pt in enumerate(ser.points):
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb=_rgb(colors[i%len(colors)])
    chart.has_legend=True; chart.legend.position=XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout=False; chart.legend.font.size=Pt(12); chart.legend.font.name=SANS
    chart.legend.font.color.rgb=_rgb(TX)

def _style_bar(gf, colors):
    chart=gf.chart; _chart_common(chart)
    plot=chart.plots[0]; plot.gap_width=60; plot.has_data_labels=True
    dl=plot.data_labels; dl.number_format='General'; dl.number_format_is_linked=False
    dl.font.size=Pt(11); dl.font.bold=True; dl.font.name=SANS; dl.font.color.rgb=_rgb(TX)
    try: dl.position=XL_LABEL_POSITION.OUTSIDE_END
    except Exception: pass
    ser=plot.series[0]
    for i,pt in enumerate(ser.points):
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb=_rgb(colors[i%len(colors)])
    chart.has_legend=False
    va=chart.value_axis; va.visible=False; va.has_major_gridlines=False
    try: va.maximum_scale=None
    except Exception: pass
    ca=chart.category_axis; ca.has_major_gridlines=False
    ca.tick_labels.font.size=Pt(10); ca.tick_labels.font.name=SANS; ca.tick_labels.font.color.rgb=_rgb(TX)
    ca.format.line.color.rgb=_rgb("D8C7CE")

def nf(n):
    try: return f"{int(round(float(n))):,}"
    except Exception: return str(n)

def build_ppt(a, out_path, currency="PKR", brand="Studio By SY", date_str=""):
    D=a["D"]; dims=a["dims"]; total=D["total"]
    def pct(n): return round(n/total*1000)/10 if total else 0
    dk=Deck(); PW,PH,M=dk.PW,dk.PH,dk.M

    def chrome(s,kicker,title,dark=False):
        dk.page+=1
        dk.txt(s,M,0.42,PW-2*M,0.3,kicker.upper(),size=11,color=GOLD,bold=True,spacing=3)
        dk.txt(s,M,0.7,PW-2*M,0.7,title,size=30,color=(WHITE if dark else PLUM),bold=True,face=SERIF)
        dk.txt(s,M,PH-0.42,8,0.3,f"Source: Final CSV \u00b7 one count per product (Handle) \u00b7 {total} products",
               size=8.5,color=("9A8A94" if dark else MUTED))
        dk.txt(s,PW-M-0.6,PH-0.42,0.6,0.3,str(dk.page),size=9,color=("9A8A94" if dark else MUTED),align=PP_ALIGN.RIGHT)

    def stat_card(s,x,y,w,h,value,label,vcolor=PLUM,vsize=34,fill=CARD):
        dk.rect(s,x,y,w,h,fill=fill,line="E4D8DD",radius=0.06,shadow=True)
        dk.txt(s,x+0.12,y+h*0.14,w-0.24,h*0.5,str(value),size=vsize,color=vcolor,bold=True,face=SERIF,
               align=PP_ALIGN.CENTER,anchor=MSO_ANCHOR.MIDDLE)
        dk.txt(s,x+0.1,y+h*0.62,w-0.2,h*0.34,label,size=11,color=MUTED,align=PP_ALIGN.CENTER)

    def bar_chart(s,x,y,w,h,items,colors_hint=None,topN=None,unit="categories"):
        it=items[:]
        if topN and len(it)>topN:
            top=it[:topN]; rest=it[topN:]; rs=sum(v for _,v in rest)
            it=top+[(f"Other ({len(rest)} {unit})",rs)]
        labels=[str(l) for l,_ in it][::-1]; values=[v for _,v in it][::-1]
        colors=[PLUM]*len(values); colors[-1]=GOLD  # max on top
        cd=CategoryChartData(); cd.categories=labels; cd.add_series("v",values)
        gf=s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED,Inches(x),Inches(y),Inches(w),Inches(h),cd)
        _style_bar(gf,colors); return gf

    def donut(s,x,y,w,h,items,colors):
        labels=[str(l) for l,_ in items]; values=[v for _,v in items]
        cd=CategoryChartData(); cd.categories=labels; cd.add_series("v",values)
        gf=s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT,Inches(x),Inches(y),Inches(w),Inches(h),cd)
        _style_donut(gf,colors,values); return gf

    def statrow(s,x,y,w,label,val,p,numc):
        dk.txt(s,x,y,w*0.62,0.3,label,size=13,color=TX,bold=True)
        dk.txt(s,x+w*0.62,y,w*0.38,0.3,f"{val}  \u00b7  {p}%",size=12,color=MUTED,align=PP_ALIGN.RIGHT)
        dk.rect(s,x,y+0.36,w,0.2,fill="EDE3E7",radius=0.5)
        dk.rect(s,x,y+0.36,max(0.12,w*(p/100)),0.2,fill=numc,radius=0.5)

    def highlights(s,items,note):
        px=9.7; pw=PW-M-px
        dk.rect(s,px,1.75,pw,4.35,fill=CARD,line="E4D8DD",radius=0.05,shadow=True)
        dk.txt(s,px+0.25,1.95,pw-0.5,0.3,"HIGHLIGHTS",size=11,color=GOLD,bold=True,spacing=2)
        yy=2.42
        for lab,val in items[:3]:
            dk.txt(s,px+0.25,yy-0.05,1.0,0.6,str(val),size=24,color=PLUM,bold=True,face=SERIF)
            dk.txt(s,px+1.15,yy,pw-1.35,0.65,[(str(lab),{"bold":True,"size":11}),
                   (f"\n{pct(val)}% of catalog",{"size":10,"color":MUTED})],size=11,color=TX,line=1.0)
            yy+=0.8
        dk.txt(s,px+0.25,yy+0.05,pw-0.5,1.4,note,size=11,italic=True,color=MUTED,line=1.12)

    # ---------- Slide 1 : title
    s=dk.slide(INK)
    dk.ellipse(s,9.6,-1.4,5.4,5.4,INK2); dk.ellipse(s,10.8,3.7,3.6,3.6,INK3)
    dk.txt(s,M,1.5,10,0.5,brand.upper(),size=15,color=GOLD,bold=True,spacing=6)
    dk.txt(s,M,2.05,11.5,1.5,"Product Catalog Dashboard",size=50,color=WHITE,bold=True,face=SERIF)
    dk.txt(s,M,3.55,8.6,0.9,"A detailed overview of the product portfolio \u2014 status, assortment mix, colour & fabric story, and pricing.",
           size=15,color="D9CBD2",line=1.15)
    teasers=[(str(total),"Products")]
    if "color" in D: teasers.append((str(D["color"]["distinct"]),"Colours"))
    if "material" in D: teasers.append((str(D["material"]["distinct"]),"Fabrics"))
    for i,(v,l) in enumerate(teasers):
        x=M+i*2.55
        dk.txt(s,x,4.75,2.3,0.7,v,size=40,color=GOLD,bold=True,face=SERIF)
        dk.txt(s,x,5.5,2.3,0.35,l.upper(),size=11,color="C9B7BF",spacing=2)
    foot=("Figures computed from the Final CSV, one count per product." if not date_str
          else f"Prepared {date_str}   \u00b7   Figures computed from the Final CSV, one count per product.")
    dk.txt(s,M,PH-0.55,11.5,0.3,foot,size=10,color="9A8A94")

    # ---------- Slide 2 : exec summary
    s=dk.slide(); chrome(s,"Overview","Portfolio at a Glance")
    dk.txt(s,M,1.55,PW-2*M,0.55,f"The catalog holds {total} products, spanning a varied colour and fabric range across the assortment.",
           size=13.5,color=TX,line=1.1)
    y1,h1,gap=2.35,1.75,0.28; w1=(PW-2*M-4*gap)/5
    k1=[(str(total),"Total Products",PLUM)]
    if "active" in D: k1.append((str(D["active"]),"Active",GREEN)); k1.append((str(D["draft"]),"Draft",GOLD))
    if "published" in D: k1.append((str(D["published"]),"Published",PLUM)); k1.append((str(D["not_published"]),"Not Published",ROSE))
    for i,(v,l,c) in enumerate(k1[:5]): stat_card(s,M+i*(w1+gap),y1,w1,h1,v,l,vcolor=c,vsize=38)
    y2,h2=y1+h1+0.35,1.65
    k2=[]
    for key,label in [("type","Categories (Type)"),("vendor","Vendors / Edits"),("subcat","Item Categories"),
                      ("color","Distinct Colours"),("material","Distinct Fabrics")]:
        if key in D: k2.append((str(D[key]["distinct"]),label))
    for i,(v,l) in enumerate(k2[:5]): stat_card(s,M+i*(w1+gap),y2,w1,h2,v,l,vcolor=GOLD,vsize=34,fill=CARD2)
    if "price_min" in D:
        dk.txt(s,M,y2+h2+0.18,PW-2*M,0.4,[("Price range  ",{"color":MUTED,"size":13}),
               (f"{currency} {nf(D['price_min'])} \u2013 {nf(D['price_max'])}",{"face":SERIF,"size":15,"color":PLUM,"bold":True}),
               (f"     Average  {currency} {nf(D['price_avg'])}",{"color":MUTED,"size":13})])

    # ---------- Slide 3 : status & availability
    if "active" in D or "published" in D:
        s=dk.slide(); chrome(s,"Catalog Health","Status & Availability")
        if "active" in D:
            dk.txt(s,M,1.7,5.6,0.35,"By publishing status",size=13,bold=True,color=PLUM)
            donut(s,M,2.0,5.4,4.2,[("Active",D["active"]),("Draft",D["draft"])],[GREEN,GOLD])
            dk.txt(s,M+1.5,3.35,2.4,0.7,f"{pct(D['active'])}%",size=26,bold=True,color=GREEN,face=SERIF,align=PP_ALIGN.CENTER)
        if "published" in D:
            dk.txt(s,7.1,1.7,5.6,0.35,"Online availability",size=13,bold=True,color=PLUM)
            donut(s,7.1,2.0,5.4,4.2,[("Published",D["published"]),("Not Published",D["not_published"])],[PLUM,ROSE])
            dk.txt(s,7.1+1.5,3.35,2.4,0.7,f"{pct(D['published'])}%",size=26,bold=True,color=PLUM,face=SERIF,align=PP_ALIGN.CENTER)

    # ---------- per-dimension slides
    donut_cols=[PLUM,ROSE,GOLD,SLATE,SAGE,MAUVE]
    for key,title,cn in dims:
        if key=="status": continue  # covered above
        d=D[key]; items=d["items"]
        if d["distinct"]<=4:
            s=dk.slide(); chrome(s,"Assortment",title.replace("By ",""))
            labels=items+([("Not specified",d["blank"])] if d["blank"]>0 else [])
            donut(s,M,1.9,6.1,4.4,labels,donut_cols)
            lead=items[0][0]
            dk.txt(s,7.1,1.95,PW-M-7.1,0.5,f"{lead} leads",size=20,bold=True,color=PLUM,face=SERIF)
            yy=2.75
            for i,(lab,val) in enumerate(items):
                statrow(s,7.1,yy,PW-M-7.1,lab,val,pct(val),donut_cols[i%len(donut_cols)]); yy+=1.0
        else:
            s=dk.slide(); chrome(s,("Palette" if key=="color" else "Materials" if key=="material" else "Assortment"),title.replace("By ",""))
            topN=12 if d["distinct"]>14 else None
            unit={"color":"colours","material":"fabrics"}.get(key,"categories")
            bar_chart(s,M,1.75,8.7,max(3.6,min(5.0,(min(len(items),(topN or len(items))+1))*0.33+0.6)),items,topN=topN,unit=unit)
            note=f"{d['distinct']} distinct values across the catalog." if d["distinct"]>14 else \
                 f"{d['distinct']} categories; {items[0][0]} leads."
            highlights(s,items,note)

    # ---------- Pricing
    if "price_min" in D:
        s=dk.slide(); chrome(s,"Commercials","Pricing Overview")
        dk.txt(s,M,1.6,PW-2*M,0.4,f"Product pricing based on each product's Variant Price ({currency}).",size=13.5,color=TX)
        y1,h1,gap=2.3,2.1,0.4; w1=(PW-2*M-2*gap)/3
        stat_card(s,M,y1,w1,h1,f"{currency} {nf(D['price_min'])}","Lowest price",vcolor=SAGE,vsize=28,fill=CARD2)
        stat_card(s,M+w1+gap,y1,w1,h1,f"{currency} {nf(D['price_avg'])}","Average price",vcolor=PLUM,vsize=28,fill=CARD)
        stat_card(s,M+2*(w1+gap),y1,w1,h1,f"{currency} {nf(D['price_max'])}","Highest price",vcolor=GOLD,vsize=28,fill=CARD2)
        dk.txt(s,M,y1+h1+0.45,6,0.35,f"Price span ({currency})",size=13,bold=True,color=PLUM)
        cd=CategoryChartData(); cd.categories=["Highest","Average","Lowest"]
        cd.add_series("v",[D["price_max"],D["price_avg"],D["price_min"]])
        gf=s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED,Inches(M),Inches(y1+h1+0.8),Inches(PW-2*M),Inches(1.7),cd)
        _style_bar(gf,[GOLD,PLUM,SAGE])  # data order Highest,Average,Lowest -> match cards

    # ---------- Closing
    s=dk.slide(INK)
    dk.ellipse(s,-1.6,4.4,5,5,INK2)
    dk.txt(s,M,1.2,10,0.4,"SUMMARY",size=12,color=GOLD,bold=True,spacing=4)
    dk.txt(s,M,1.65,11.8,1.0,"A compact, well-structured catalog",size=36,color=WHITE,bold=True,face=SERIF)
    facts=[(str(total),"products in the catalog")]
    if "active" in D: facts.append((f"{D['active']} / {D['draft']}","active / draft"))
    if "type" in D: facts.append((str(D["type"]["distinct"]),"categories (Type)"))
    if "vendor" in D: facts.append((str(D["vendor"]["distinct"]),"vendors / edits"))
    if "color" in D: facts.append((str(D["color"]["distinct"]),"distinct colours"))
    if "material" in D: facts.append((str(D["material"]["distinct"]),"distinct fabrics"))
    gx,gy,gw,gh=M,2.95,(PW-2*M-2*0.4)/3,1.25
    for i,(v,l) in enumerate(facts[:6]):
        x=gx+(i%3)*(gw+0.4); y=gy+(i//3)*(gh+0.3)
        dk.txt(s,x,y,gw,0.7,v,size=34,color=GOLD,bold=True,face=SERIF)
        dk.txt(s,x,y+0.72,gw,0.35,l.upper(),size=11,color="C9B7BF",spacing=1.5)
    dk.txt(s,M,PH-0.95,11.8,0.6,"All figures are computed with live formulas from the Final CSV master \u2014 one count per product (Handle).",
           size=11,color="9A8A94",line=1.1)

    dk.p.save(out_path)
    return dk.page

# =============================================================================
#  PIPELINE
# =============================================================================
def run_pipeline(final_path, final_sheet, ref_path, ref_sheet, outdir, base_name,
                 make_excel=True, make_ppt=True, currency="PKR", brand="Studio By SY",
                 date_str="", log=print, recalc=True):
    log("Reading inputs...")
    fin_hdr, fin_data = read_table(final_path, final_sheet)
    ref_hdr, ref_data = read_table(ref_path, ref_sheet)
    # Compare product descriptions on words only (ignore HTML markup / special chars)
    fin_hdr, fin_data = add_body_text_col(fin_hdr, fin_data)
    ref_hdr, ref_data = add_body_text_col(ref_hdr, ref_data)
    log(f"  Final CSV: {len(fin_data)} rows x {len(fin_hdr)} cols")
    log(f"  Reference: {len(ref_data)} rows x {len(ref_hdr)} cols")
    log("Analyzing...")
    a = analyze(fin_hdr, fin_data, ref_hdr, ref_data)
    a["_fin_hdr"], a["_fin_data"] = fin_hdr, fin_data
    a["_ref_hdr"], a["_ref_data"] = ref_hdr, ref_data
    a["D"]["brand"] = brand
    log(f"  {len(a['handles'])} unique handles, {len(a['common_fields'])} common fields, "
        f"{len(a['dims'])} dashboard dimensions.")
    os.makedirs(outdir, exist_ok=True)
    xlsx_path = pptx_path = None
    if make_excel:
        xlsx_path = os.path.join(outdir, f"{base_name} - Reconciliation & Dashboard.xlsx")
        log("Building reconciliation workbook...")
        build_workbook(a, xlsx_path)
        if recalc:
            log("Recalculating...")
            recalc_excel(xlsx_path, log=log)
        else:
            # Web/helper flow: skip the (blocking) LibreOffice pre-compute so the
            # request can never hang on a stuck soffice. The workbook is written with
            # fullCalcOnLoad=1, so Excel recalculates every formula the moment it opens.
            log("Skipping LibreOffice pre-compute (Excel recalculates on open).")
        log(f"  Saved: {xlsx_path}")
    if make_ppt:
        pptx_path = os.path.join(outdir, f"{base_name} - Product Dashboard.pptx")
        log("Building dashboard presentation...")
        n = build_ppt(a, pptx_path, currency=currency, brand=brand, date_str=date_str)
        log(f"  Saved {n} slides: {pptx_path}")
    log("Done.")
    return xlsx_path, pptx_path

# =============================================================================
#  GUI
# =============================================================================
def launch_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import datetime

    root = tk.Tk()
    root.title("Reconciliation & Dashboard Generator")
    root.geometry("820x640"); root.minsize(760, 600)
    try: root.iconbitmap(default="")
    except Exception: pass

    state = {"final": tk.StringVar(), "ref": tk.StringVar(), "out": tk.StringVar(),
             "brand": tk.StringVar(value="Studio By SY"), "cur": tk.StringVar(value="PKR"),
             "xlsx": tk.BooleanVar(value=True), "ppt": tk.BooleanVar(value=True),
             "final_sheet": tk.StringVar(), "ref_sheet": tk.StringVar()}
    results = {"paths": []}

    PADX=14
    hdr = tk.Frame(root, bg="#2E1F2E"); hdr.pack(fill="x")
    tk.Label(hdr, text="Reconciliation & Dashboard Generator", bg="#2E1F2E", fg="white",
             font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=PADX, pady=(12,2))
    tk.Label(hdr, text="Pick a Reference file/sheet and a Final CSV file/sheet, then Generate.",
             bg="#2E1F2E", fg="#D9CBD2", font=("Segoe UI", 9)).pack(anchor="w", padx=PADX, pady=(0,12))

    body = tk.Frame(root); body.pack(fill="both", expand=True, padx=PADX, pady=10)

    def file_row(parent, label, var, sheetvar, r):
        tk.Label(parent, text=label, font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(8,0))
        ent = tk.Entry(parent, textvariable=var, width=64); ent.grid(row=r+1, column=0, sticky="we", padx=(0,6))
        cb = ttk.Combobox(parent, textvariable=sheetvar, width=20, state="disabled")
        cb.grid(row=r+1, column=2, sticky="w", padx=(6,0))
        def browse():
            p = filedialog.askopenfilename(title=label,
                    filetypes=[("Excel/CSV","*.xlsx *.xlsm *.csv *.tsv"),("All files","*.*")])
            if not p: return
            var.set(p)
            sheets = list_sheets(p)
            if sheets:
                cb["values"] = sheets; cb["state"]="readonly"
                pre = next((x for x in sheets if label.split()[0].lower() in x.lower()), sheets[0])
                # smarter preselect
                key = "final" if "Final" in label else "refer"
                pre = next((x for x in sheets if key in x.lower()), pre)
                sheetvar.set(pre)
            else:
                cb["values"]=[]; cb["state"]="disabled"; sheetvar.set("")
            if not state["out"].get():
                state["out"].set(os.path.dirname(p))
        tk.Button(parent, text="Browse…", command=browse, width=10).grid(row=r+1, column=1, padx=(0,6))
        return cb

    body.columnconfigure(0, weight=1)
    file_row(body, "Final CSV  (file / sheet)", state["final"], state["final_sheet"], 0)
    file_row(body, "Reference File  (file / sheet)", state["ref"], state["ref_sheet"], 3)

    # output + options
    opt = tk.Frame(body); opt.grid(row=7, column=0, columnspan=3, sticky="we", pady=(14,0))
    opt.columnconfigure(1, weight=1)
    tk.Label(opt, text="Output folder", font=("Segoe UI",10,"bold")).grid(row=0,column=0,sticky="w")
    tk.Entry(opt, textvariable=state["out"]).grid(row=0,column=1,sticky="we",padx=6)
    tk.Button(opt, text="Browse…", width=10,
              command=lambda: state["out"].set(filedialog.askdirectory() or state["out"].get())).grid(row=0,column=2)

    optrow = tk.Frame(body); optrow.grid(row=8, column=0, columnspan=3, sticky="we", pady=(10,0))
    tk.Checkbutton(optrow, text="Reconciliation Excel", variable=state["xlsx"]).pack(side="left")
    tk.Checkbutton(optrow, text="Dashboard PowerPoint", variable=state["ppt"]).pack(side="left", padx=(12,0))
    tk.Label(optrow, text="Brand:").pack(side="left", padx=(18,2))
    tk.Entry(optrow, textvariable=state["brand"], width=18).pack(side="left")
    tk.Label(optrow, text="Currency:").pack(side="left", padx=(12,2))
    tk.Entry(optrow, textvariable=state["cur"], width=6).pack(side="left")

    # log
    logf = tk.LabelFrame(body, text="Log"); logf.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(12,0))
    body.rowconfigure(9, weight=1)
    logbox = tk.Text(logf, height=12, wrap="word", font=("Consolas", 9)); logbox.pack(fill="both", expand=True, side="left")
    sb = tk.Scrollbar(logf, command=logbox.yview); sb.pack(side="right", fill="y"); logbox.config(yscrollcommand=sb.set)
    def log(msg):
        logbox.insert("end", str(msg)+"\n"); logbox.see("end"); logbox.update_idletasks()

    btns = tk.Frame(root); btns.pack(fill="x", padx=PADX, pady=10)
    open_btn = tk.Button(btns, text="Open Output Folder", state="disabled",
                         command=lambda: os.startfile(state["out"].get()) if state["out"].get() else None)
    open_btn.pack(side="right")
    gen_btn = tk.Button(btns, text="Generate", bg="#6D2E46", fg="white", font=("Segoe UI",11,"bold"),
                        padx=18, pady=6)
    gen_btn.pack(side="right", padx=8)

    def worker():
        try:
            fp=state["final"].get().strip(); rp=state["ref"].get().strip()
            if not fp or not rp:
                messagebox.showwarning("Missing files","Please choose both a Final CSV and a Reference file."); return
            outdir=state["out"].get().strip() or os.path.dirname(fp)
            base=state["brand"].get().strip() or "Reconciliation"
            date_str=datetime.date.today().strftime("%d %B %Y")
            log("="*54)
            x,p=run_pipeline(fp, state["final_sheet"].get() or None, rp, state["ref_sheet"].get() or None,
                             outdir, base, make_excel=state["xlsx"].get(), make_ppt=state["ppt"].get(),
                             currency=state["cur"].get().strip() or "PKR", brand=base,
                             date_str=date_str, log=log)
            results["paths"]=[q for q in (x,p) if q]
            open_btn.config(state="normal")
            messagebox.showinfo("Success","Generated:\n\n"+"\n".join(os.path.basename(q) for q in results["paths"])
                                +f"\n\nin\n{outdir}")
        except Exception as e:
            log("ERROR: "+str(e)); log(traceback.format_exc())
            messagebox.showerror("Error", str(e))
        finally:
            gen_btn.config(state="normal", text="Generate")

    def on_generate():
        gen_btn.config(state="disabled", text="Working…")
        threading.Thread(target=worker, daemon=True).start()
    gen_btn.config(command=on_generate)

    log("Ready. Choose your Final CSV and Reference file above, then click Generate.")
    lo = find_soffice()
    log("LibreOffice detected \u2713 (formulas will be pre-computed)." if lo
        else "LibreOffice not found - Excel will still recalc formulas when you open the file.")
    root.mainloop()

# =============================================================================
if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--cli":
        # --cli final.xlsx[:Sheet] ref.xlsx[:Sheet] [outdir]
        def split(a):
            if a.lower().endswith((".xlsx",".xlsm")) and a.count(":")>=2:  # keep drive colon
                pass
            return a
        run_pipeline(sys.argv[2], None, sys.argv[3], None,
                     sys.argv[4] if len(sys.argv)>4 else os.path.dirname(sys.argv[2]),
                     "Reconciliation", log=print)
    else:
        launch_gui()
