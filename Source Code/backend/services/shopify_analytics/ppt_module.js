// =====================================================================
//  Executive PowerPoint generator  (native, fully editable)
//  Consumes the SAME analytics model `A` that builds the Excel workbook,
//  and mirrors the workbook's number formats (#,##0 / 0.0% / #,##0.0),
//  so every value in the deck matches the Excel cell-for-cell.
//  No images: native PptxGenJS charts, tables, shapes and text only.
// =====================================================================
(function (root) {
  'use strict';

  // ---- palette (matches the dashboard app) ----
  const NAVY = '2D4A86', BLUE = '3A63B8', TEAL = '0F7A63', AMBER = 'B07D12',
        CORAL = 'B64328', VIOLET = '5A49A8', GREEN = '1C7A52';
  const INK = '191C22', MID = '565D6B', SOFT = '878E9C',
        RULE = 'D8DCE4', PANEL = 'F4F6F9', PANEL2 = 'EAEEF5', WHITE = 'FFFFFF';
  const SERIES = [NAVY, TEAL, AMBER, VIOLET, CORAL, BLUE, GREEN, SOFT];
  const FONT = 'Calibri', FONT_LT = 'Calibri Light';

  // slide geometry (16:9 wide = 13.333 x 7.5 in)
  const PW = 13.333, PH = 7.5, MX = 0.55, CW = PW - MX * 2;
  const BODY_TOP = 1.62, BODY_BOT = 7.02, BODY_H = BODY_BOT - BODY_TOP;

  function buildPPTX(A, opts) {
    opts = opts || {};
    const K = A.kpi, INV = A.inventory || {}, CUR = A.currency || '';
    const company = (opts.company || '').trim() || deriveCompany(A);
    const R = v => Math.round(Number(v) || 0);

    // ---- formatters that mirror the Excel number formats exactly ----
    const num = v => R(v).toLocaleString('en-US');                       // #,##0
    const money = v => (CUR ? CUR + ' ' : '') + R(v).toLocaleString('en-US');
    const pct = v => ((Number(v) || 0) * 100).toFixed(1) + '%';          // 0.0%
    const dec1 = v => (Math.round((Number(v) || 0) * 10) / 10).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const curLbl = CUR ? ' (' + CUR + ')' : '';
    const MONA = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const monLbl = k => { if (!k || k.indexOf('-') < 0) return k || ''; const [y, m] = k.split('-'); return (MONA[(+m) - 1] || m) + ' ' + String(y).slice(2); };
    const monDay = iso => { if (!iso || iso.length < 10) return iso || ''; const p = iso.split('-'); return (MONA[(+p[1]) - 1] || p[1]) + ' ' + (+p[2]); };

    // ---- derived, mathematically-true figures (from the model / Excel series) ----
    const months = A.months || [];
    const mf = A.monthlyFull || [];
    const firstM = months[0] || '', lastM = months[months.length - 1] || '';
    const yrs = (A.yearly || []).filter(y => y.key);
    const yoy = (yrs.length >= 2 && yrs[yrs.length - 2].rev)
      ? (yrs[yrs.length - 1].rev - yrs[yrs.length - 2].rev) / yrs[yrs.length - 2].rev : null;
    const latestMoM = mf.length ? mf[mf.length - 1].momRev : null;
    const periodGrowth = (mf.length >= 2 && mf[0].rev)
      ? (mf[mf.length - 1].rev - mf[0].rev) / mf[0].rev : null;
    const cats = A.category || [], prods = A.products || [], vends = A.vendor || [];
    const topCatShare = (cats[0] && K.merch_rev) ? cats[0].rev / K.merch_rev : 0;
    const top10 = prods.slice(0, 10);
    const top10Share = K.merch_rev ? top10.reduce((s, p) => s + (p.rev || 0), 0) / K.merch_rev : 0;
    const custs = A.customers || [];
    const custRevTot = custs.reduce((s, c) => s + (c.rev || 0), 0);
    const retRev = custs.filter(c => c.type === 'Returning').reduce((s, c) => s + (c.rev || 0), 0);
    const retRevShare = custRevTot ? retRev / custRevTot : 0;
    const wdOrders = {}; (A.weekday || []).forEach(w => wdOrders[w.key] = w.orders || 0);
    const WD = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    let peakDay = '', peakN = -1; WD.forEach(w => { if ((wdOrders[w] || 0) > peakN) { peakN = wdOrders[w] || 0; peakDay = w; } });
    const WEEKEND = (wdOrders['Sat'] || 0) + (wdOrders['Sun'] || 0);
    const weekendShare = K.conf_orders ? WEEKEND / K.conf_orders : 0;
    const growthTxt = g => (g == null ? 'n/a' : (g >= 0 ? '+' : '') + pct(g));

    // ---- pptx doc ----
    const pptx = new root.PptxGenJS();
    pptx.defineLayout({ name: 'WIDE', width: PW, height: PH });
    pptx.layout = 'WIDE';
    pptx.author = 'Shopify Analytics'; pptx.company = company;
    pptx.title = company + ' - Commerce Analytics';
    pptx.theme = { headFontFace: FONT_LT, bodyFontFace: FONT };

    let PAGE = 0;
    const CONF = company + '  |  Commerce Analytics  |  Confidential';

    // ---------- slide scaffold ----------
    function chrome(kicker) {
      const s = pptx.addSlide();
      s.background = { color: WHITE };
      PAGE++;
      // footer
      s.addText(CONF, { x: MX, y: PH - 0.36, w: CW - 0.6, h: 0.26, fontFace: FONT, fontSize: 8, color: SOFT, align: 'left', valign: 'middle' });
      s.addText(String(PAGE).padStart(2, '0'), { x: PW - MX - 0.6, y: PH - 0.36, w: 0.6, h: 0.26, fontFace: FONT, fontSize: 8, color: SOFT, align: 'right', valign: 'middle' });
      return s;
    }
    // content slide with title + action-title (the McKinsey takeaway)
    function slide(kicker, title, action) {
      const s = chrome(kicker);
      s.addText((kicker || '').toUpperCase(), { x: MX, y: 0.34, w: CW, h: 0.24, fontFace: FONT, fontSize: 9.5, color: TEAL, charSpacing: 2, bold: true });
      s.addText(title, { x: MX, y: 0.58, w: CW, h: 0.5, fontFace: FONT_LT, fontSize: 23, color: NAVY, bold: true });
      if (action) s.addText(action, { x: MX, y: 1.12, w: CW, h: 0.42, fontFace: FONT, fontSize: 12.5, color: INK, italic: true });
      s.addShape(pptx.ShapeType.line, { x: MX, y: BODY_TOP - 0.12, w: CW, h: 0, line: { color: RULE, width: 1 } });
      return s;
    }

    // ---------- reusable pieces ----------
    function tile(s, x, y, w, h, label, value, sub, accent) {
      accent = accent || NAVY;
      s.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: PANEL }, line: { color: RULE, width: 1 } });
      s.addShape(pptx.ShapeType.rect, { x, y, w: 0.06, h, fill: { color: accent }, line: { type: 'none' } });
      s.addText(label.toUpperCase(), { x: x + 0.16, y: y + 0.1, w: w - 0.26, h: 0.26, fontFace: FONT, fontSize: 9, color: MID, bold: true, charSpacing: 1 });
      s.addText(String(value), { x: x + 0.16, y: y + 0.32, w: w - 0.26, h: h - 0.62, fontFace: FONT_LT, fontSize: 21, color: accent, bold: true, valign: 'middle' });
      if (sub) s.addText(sub, { x: x + 0.16, y: y + h - 0.32, w: w - 0.26, h: 0.28, fontFace: FONT, fontSize: 8.5, color: SOFT });
    }

    function baseChartOpts(o) {
      return Object.assign({
        chartColors: SERIES,
        showTitle: false,
        showLegend: false,
        showValue: true,
        dataLabelFontFace: FONT, dataLabelFontSize: 8, dataLabelColor: INK, dataLabelPosition: 'outEnd',
        catAxisLabelFontFace: FONT, catAxisLabelFontSize: 8.5, catAxisLabelColor: MID,
        valAxisLabelFontFace: FONT, valAxisLabelFontSize: 8, valAxisLabelColor: MID,
        catAxisLineColor: RULE, valAxisLineColor: RULE,
        valGridLine: { style: 'solid', color: 'EDEFF3', size: 1 },
        catGridLine: { style: 'none' },
        catAxisTitleColor: MID, catAxisTitleFontSize: 9, catAxisTitleFontFace: FONT,
        valAxisTitleColor: MID, valAxisTitleFontSize: 9, valAxisTitleFontFace: FONT,
        border: { pt: 0, color: WHITE },
      }, o || {});
    }
    function panelTitle(s, x, y, w, txt, sub) {
      s.addText(txt, { x, y, w, h: 0.28, fontFace: FONT, fontSize: 12, color: NAVY, bold: true });
      if (sub) s.addText(sub, { x, y: y + 0.26, w, h: 0.22, fontFace: FONT, fontSize: 8.5, color: SOFT });
    }
    function dataTable(s, x, y, w, headers, rows, colW, opts) {
      opts = opts || {};
      const head = headers.map((hd, i) => ({ text: String(hd), options: { fill: { color: NAVY }, color: WHITE, bold: true, fontSize: opts.fs || 9, align: i === 0 ? 'left' : 'right', valign: 'middle', fontFace: FONT } }));
      const body = rows.map((r, ri) => r.map((c, ci) => ({
        text: String(c), options: {
          fill: { color: ri % 2 ? WHITE : PANEL }, color: INK, fontSize: opts.fs || 9,
          align: ci === 0 ? 'left' : 'right', valign: 'middle', fontFace: FONT,
          bold: !!(opts.boldLast && ri === rows.length - 1),
        }
      })));
      s.addTable([head].concat(body), {
        x, y, w, colW, fontFace: FONT, border: { type: 'solid', pt: 0.5, color: RULE },
        rowH: opts.rowH || 0.24, valign: 'middle', autoPage: false,
      });
      return y + (opts.rowH || 0.24) * (rows.length + 1);
    }
    function bulletBox(s, x, y, w, h, items, accent) {
      accent = accent || NAVY;
      const runs = [];
      items.forEach((it, i) => {
        const head = typeof it === 'string' ? it : it.h;
        const body = typeof it === 'string' ? '' : it.b;
        runs.push({ text: head, options: { fontFace: FONT, fontSize: 12.5, color: NAVY, bold: true, bullet: { code: '25AA', indent: 18 }, paraSpaceBefore: i ? 12 : 0, paraSpaceAfter: body ? 3 : 7, breakLine: true } });
        if (body) runs.push({ text: body, options: { fontFace: FONT, fontSize: 11, color: MID, bullet: false, indentLevel: 1, paraSpaceAfter: 7, breakLine: true } });
      });
      s.addText(runs, { x, y, w, h, valign: 'top' });
    }

    // =================================================================
    // 1) COVER
    // =================================================================
    (function cover() {
      const s = chrome();
      s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: PW, h: PH, fill: { color: WHITE }, line: { type: 'none' } });
      s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 4.7, h: PH, fill: { color: NAVY }, line: { type: 'none' } });
      s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.16, h: PH, fill: { color: TEAL }, line: { type: 'none' } });
      s.addText(company.toUpperCase(), { x: 0.6, y: 2.35, w: 3.7, h: 1.2, fontFace: FONT_LT, fontSize: 30, color: WHITE, bold: true, valign: 'middle' });
      s.addText('COMMERCE ANALYTICS', { x: 0.62, y: 3.5, w: 3.7, h: 0.3, fontFace: FONT, fontSize: 12, color: '9DB0DA', charSpacing: 3 });
      // right column
      s.addText('Executive Analytics Report', { x: 5.2, y: 2.05, w: 7.4, h: 0.5, fontFace: FONT_LT, fontSize: 26, color: NAVY, bold: true });
      s.addText('Formula-driven diagnostic of orders, revenue, customers and product performance — derived directly from Shopify Orders & Products exports. Confirmed orders only.',
        { x: 5.22, y: 2.66, w: 7.2, h: 0.8, fontFace: FONT, fontSize: 12, color: MID });
      const meta = [
        ['Report period', (firstM && lastM) ? (monLbl(firstM) + '  –  ' + monLbl(lastM) + '  (' + months.length + ' months)') : 'n/a'],
        ['Currency', CUR || 'n/a'],
        ['Confirmed orders', num(K.conf_orders) + '   (' + num(K.canc_orders) + ' cancelled, excluded)'],
        ['Generated', new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })],
      ];
      let yy = 3.95;
      meta.forEach(m => {
        s.addText(m[0].toUpperCase(), { x: 5.22, y: yy, w: 2.3, h: 0.3, fontFace: FONT, fontSize: 9.5, color: SOFT, bold: true, charSpacing: 1, valign: 'middle' });
        s.addText(m[1], { x: 7.5, y: yy, w: 5.0, h: 0.3, fontFace: FONT, fontSize: 11.5, color: INK, valign: 'middle' });
        s.addShape(pptx.ShapeType.line, { x: 5.22, y: yy + 0.34, w: 7.2, h: 0, line: { color: RULE, width: 0.75 } });
        yy += 0.5;
      });
      s.addText('CONFIDENTIAL', { x: 5.22, y: 6.5, w: 4, h: 0.3, fontFace: FONT, fontSize: 9, color: SOFT, charSpacing: 2 });
    })();

    // =================================================================
    // 2) EXECUTIVE SUMMARY
    // =================================================================
    (function execSummary() {
      const action = 'Across ' + months.length + ' months, ' + company + ' generated ' + money(K.total_rev) +
        ' from ' + num(K.conf_orders) + ' confirmed orders and ' + num(K.customers) + ' identified customers' +
        (yoy != null ? '; revenue ' + (yoy >= 0 ? 'grew' : 'declined') + ' ' + growthTxt(yoy) + ' year-over-year.' : '.');
      const s = slide('Executive summary', 'The business at a glance', action);
      const tiles = [
        ['Total Revenue' + curLbl, money(K.total_rev), 'Incl. shipping · Net excl. ship ' + money(K.net_rev_ex_ship), NAVY],
        ['Confirmed Orders', num(K.conf_orders), num(K.canc_orders) + ' cancelled excluded', TEAL],
        ['Total Customers', num(K.customers), num(K.new_cust) + ' new · ' + num(K.repeat_cust) + ' returning', BLUE],
        ['Avg Order Value' + curLbl, money(K.aov), 'Median ' + money(K.median_order), AMBER],
        ['Units Sold', num(K.units), dec1(K.units_per_order) + ' per order', VIOLET],
        ['Repeat Purchase Rate', pct(K.repeat_rate), num(K.repeat_cust) + ' of ' + num(K.customers) + ' customers', TEAL],
        ['Returning-Rev Share', pct(retRevShare), 'of identified-customer revenue', GREEN],
        ['Local Revenue Share', pct(K.local_rev_pct), num(K.local_orders) + ' local · ' + num(K.intl_orders) + ' intl', CORAL],
      ];
      const cols = 4, tw = (CW - 0.3 * (cols - 1)) / cols, th = 1.12;
      tiles.forEach((t, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        tile(s, MX + c * (tw + 0.3), BODY_TOP + 0.05 + r * (th + 0.24), tw, th, t[0], t[1], t[2], t[3]);
      });
      // highlights strip
      const hi = topInsights(3);
      s.addText('KEY HIGHLIGHTS', { x: MX, y: BODY_TOP + 0.05 + 2 * (th + 0.24) + 0.05, w: CW, h: 0.26, fontFace: FONT, fontSize: 9.5, color: MID, bold: true, charSpacing: 1 });
      s.addText(hi.map((t, i) => ({ text: t, options: { fontFace: FONT, fontSize: 10.5, color: INK, bullet: { code: '25AA', indent: 16 }, paraSpaceAfter: 3 } })),
        { x: MX, y: BODY_TOP + 0.05 + 2 * (th + 0.24) + 0.32, w: CW, h: 0.9, valign: 'top' });
    })();

    // =================================================================
    // 3) REVENUE OVERVIEW  (combo: monthly revenue columns + orders line)
    // =================================================================
    (function revenueOverview() {
      const action = 'Revenue ' + (periodGrowth != null ? (periodGrowth >= 0 ? 'rose' : 'fell') + ' ' + growthTxt(periodGrowth) + ' from first to last month' : 'trend shown below') +
        '; latest month posted ' + growthTxt(latestMoM) + ' MoM.';
      const s = slide('Revenue', 'Revenue & order trajectory', action);
      const labels = mf.map(m => monLbl(m.key));
      const rev = mf.map(m => R(m.rev)), ord = mf.map(m => m.orders);
      panelTitle(s, MX, BODY_TOP, 8.4, 'Monthly revenue vs. orders', 'Columns = revenue' + curLbl + '  ·  line = confirmed orders');
      s.addChart([
        { type: pptx.ChartType.bar, data: [{ name: 'Revenue' + curLbl, labels, values: rev }], options: { chartColors: [NAVY], barGrouping: 'clustered', showValue: true, dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd', dataLabelColor: NAVY, dataLabelFontSize: 7, dataLabelFontFace: FONT } },
        { type: pptx.ChartType.line, data: [{ name: 'Orders', labels, values: ord }], options: { chartColors: [AMBER], secondaryValAxis: true, secondaryCatAxis: true, lineSize: 2.25, lineDataSymbol: 'circle', lineDataSymbolSize: 5, showValue: true, dataLabelFormatCode: '#,##0', dataLabelPosition: 't', dataLabelColor: AMBER, dataLabelFontSize: 7, dataLabelFontFace: FONT } },
      ], baseChartOpts({
        x: MX, y: BODY_TOP + 0.5, w: 8.4, h: BODY_H - 0.5,
        showValue: false, showLegend: true, legendPos: 'b', legendFontSize: 9, legendColor: MID, legendFontFace: FONT,
        valAxes: [
          { showValAxisTitle: false, valAxisLabelFormatCode: '#,##0', valGridLine: { style: 'solid', color: 'EDEFF3', size: 1 }, valAxisLabelColor: MID, valAxisLabelFontSize: 8 },
          { showValAxisTitle: false, valAxisLabelFormatCode: '#,##0', valGridLine: { style: 'none' }, valAxisLabelColor: AMBER, valAxisLabelFontSize: 8 },
        ],
        catAxes: [{ catAxisLabelColor: MID, catAxisLabelFontSize: 8 }, { catAxisHidden: true }],
      }));
      // right: growth tiles
      const gx = MX + 8.7, gw = CW - 8.7;
      panelTitle(s, gx, BODY_TOP, gw, 'Growth signals');
      const g = [
        ['Total Revenue' + curLbl, money(K.total_rev), NAVY, 'Net excl. ship ' + money(K.net_rev_ex_ship)],
        ['Year-over-Year', growthTxt(yoy), yoy != null && yoy < 0 ? CORAL : GREEN],
        ['Latest month MoM', growthTxt(latestMoM), latestMoM != null && latestMoM < 0 ? CORAL : GREEN],
        ['Best month' + curLbl, bestMonth(), TEAL],
      ];
      let gy = BODY_TOP + 0.42;
      g.forEach(t => { tile(s, gx, gy, gw, 1.05, t[0], t[1], t[3] || '', t[2]); gy += 1.22; });
    })();

    // =================================================================
    // 4) REVENUE BY QUARTER & YEAR
    // =================================================================
    (function revByPeriod() {
      const s = slide('Revenue', 'Revenue by quarter & year', 'Seasonality and annual trajectory, confirmed orders only.');
      const q = (A.quarterly || []).filter(x => x.key);
      const yy = (A.yearly || []).filter(x => x.key);
      panelTitle(s, MX, BODY_TOP, CW / 2 - 0.2, 'Quarterly revenue' + curLbl);
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: q.map(x => x.key), values: q.map(x => R(x.rev)) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: CW / 2 - 0.3, h: BODY_H - 0.5, chartColors: [NAVY], dataLabelFormatCode: '#,##0', valAxisLabelFormatCode: '#,##0' }));
      panelTitle(s, MX + CW / 2 + 0.1, BODY_TOP, CW / 2 - 0.2, 'Yearly revenue' + curLbl);
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: yy.map(x => x.key), values: yy.map(x => R(x.rev)) }],
        baseChartOpts({ x: MX + CW / 2 + 0.1, y: BODY_TOP + 0.5, w: CW / 2 - 0.3, h: BODY_H - 0.5, chartColors: [TEAL], dataLabelFormatCode: '#,##0', valAxisLabelFormatCode: '#,##0' }));
    })();

    // =================================================================
    // 5) ORDERS ANALYSIS
    // =================================================================
    (function orders() {
      const action = num(K.conf_orders) + ' confirmed orders; ' + peakDay + ' is the peak day (' + num(peakN) + ' orders) and weekends drive ' + pct(weekendShare) + ' of volume.';
      const s = slide('Orders', 'Order volume & cadence', action);
      const labels = mf.map(m => monLbl(m.key));
      panelTitle(s, MX, BODY_TOP, 8.4, 'Monthly orders', 'Confirmed orders per month');
      s.addChart(pptx.ChartType.bar, [{ name: 'Orders', labels, values: mf.map(m => m.orders) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: 8.4, h: BODY_H - 0.5, chartColors: [BLUE], dataLabelFormatCode: '#,##0' }));
      const gx = MX + 8.7, gw = CW - 8.7;
      panelTitle(s, gx, BODY_TOP, gw, 'Orders by weekday');
      s.addChart(pptx.ChartType.bar, [{ name: 'Orders', labels: WD.filter(w => wdOrders[w] != null), values: WD.filter(w => wdOrders[w] != null).map(w => wdOrders[w]) }],
        baseChartOpts({ x: gx, y: BODY_TOP + 0.5, w: gw, h: BODY_H - 0.5, chartColors: [NAVY], barDir: 'bar', dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd' }));
    })();

    // =================================================================
    // 6) CUSTOMER ANALYSIS
    // =================================================================
    (function customers() {
      const action = num(K.customers) + ' identified customers — ' + pct(K.repeat_rate) + ' returning, generating ' + pct(retRevShare) + ' of customer revenue.';
      const s = slide('Customers', 'Customer base & retention', action);
      // donut new vs returning
      panelTitle(s, MX, BODY_TOP, 3.9, 'New vs. returning', 'Share of identified customers');
      s.addChart(pptx.ChartType.doughnut, [{ name: 'Customers', labels: ['New', 'Returning'], values: [K.new_cust, K.repeat_cust] }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: 3.9, h: BODY_H - 0.5, chartColors: [BLUE, TEAL], showValue: false, showPercent: true, showLegend: true, legendPos: 'b', legendFontSize: 9, legendColor: MID, dataLabelFontSize: 10, dataLabelColor: WHITE, holeSize: 58 }));
      // tiles
      const tx = MX + 4.15, tw = 2.6;
      const T = [['New Customers', num(K.new_cust), BLUE], ['Returning Customers', num(K.repeat_cust), TEAL], ['Repeat Purchase Rate', pct(K.repeat_rate), NAVY], ['Revenue / Customer' + curLbl, money(K.rev_per_cust), AMBER]];
      T.forEach((t, i) => tile(s, tx, BODY_TOP + 0.05 + i * 1.28, tw, 1.12, t[0], t[1], '', t[2]));
      // top customers table
      const cx = tx + tw + 0.3, cw = PW - MX - cx;
      panelTitle(s, cx, BODY_TOP, cw, 'Top customers by revenue');
      const rows = custs.slice(0, 8).map(c => [truncate(c.key, 26), num(c.orders), money(c.rev), c.type]);
      dataTable(s, cx, BODY_TOP + 0.45, cw, ['Customer', 'Orders', 'Revenue' + curLbl, 'Type'], rows, [cw * 0.42, cw * 0.14, cw * 0.26, cw * 0.18], { rowH: 0.3, fs: 8.5 });
    })();

    // =================================================================
    // 7) REVENUE BREAKDOWN  (category + vendor)
    // =================================================================
    (function breakdown() {
      const action = (cats[0] ? cats[0].key + ' leads at ' + pct(topCatShare) + ' of merchandise revenue' : 'Category mix shown below') +
        (vends.length > 1 ? '; ' + vends.length + ' brands contribute.' : '.');
      const s = slide('Revenue breakdown', 'Where revenue comes from', action);
      const tc = cats.slice(0, 8);
      panelTitle(s, MX, BODY_TOP, CW / 2 - 0.2, 'Revenue by category' + curLbl);
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: tc.map(c => truncate(c.key, 18)), values: tc.map(c => R(c.rev)) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: CW / 2 - 0.3, h: BODY_H - 0.5, chartColors: [NAVY], barDir: 'bar', dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd' }));
      // vendor / brand contribution (table with %)
      const vx = MX + CW / 2 + 0.1, vw = CW / 2 - 0.2;
      const useVendor = vends.length > 1 && vends[0].key && vends[0].key !== 'Unmapped';
      panelTitle(s, vx, BODY_TOP, vw, useVendor ? 'Brand / vendor contribution' : 'Category contribution');
      const src = useVendor ? vends : cats;
      const rows = src.slice(0, 9).map(c => [truncate(c.key, 24), money(c.rev), pct(K.merch_rev ? (c.rev || 0) / K.merch_rev : 0)]);
      dataTable(s, vx, BODY_TOP + 0.45, vw, [useVendor ? 'Brand' : 'Category', 'Revenue' + curLbl, '% of Merch Rev'], rows, [vw * 0.5, vw * 0.28, vw * 0.22], { rowH: 0.3, fs: 9 });
    })();

    // =================================================================
    // 8) PRODUCT PERFORMANCE
    // =================================================================
    (function products() {
      const action = 'Top 10 products drive ' + pct(top10Share) + ' of merchandise revenue' + (A.zeroSales ? '; ' + num(A.zeroSales) + ' catalog products recorded zero sales.' : '.');
      const s = slide('Products', 'Product performance', action);
      const tp = prods.slice(0, 10);
      panelTitle(s, MX, BODY_TOP, 6.4, 'Top 10 products by revenue' + curLbl);
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: tp.map(p => truncate(p.key, 22)), values: tp.map(p => R(p.rev)) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: 6.4, h: BODY_H - 0.5, chartColors: [NAVY], barDir: 'bar', dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd', catAxisLabelFontSize: 8 }));
      // by units table
      const ux = MX + 6.7, uw = PW - MX - ux;
      const byUnits = (A.products || []).slice().sort((a, b) => (b.units || 0) - (a.units || 0)).slice(0, 10);
      panelTitle(s, ux, BODY_TOP, uw, 'Top 10 by units sold');
      const rows = byUnits.map(p => [truncate(p.key, 28), num(p.units), money(p.rev)]);
      dataTable(s, ux, BODY_TOP + 0.45, uw, ['Product', 'Units', 'Revenue' + curLbl], rows, [uw * 0.56, uw * 0.16, uw * 0.28], { rowH: 0.3, fs: 8.5 });
    })();

    // =================================================================
    // 9) GEOGRAPHIC ANALYSIS
    // =================================================================
    (function geography() {
      const action = pct(K.local_rev_pct) + ' of revenue is local (PK)' + ((A.country || []).length > 1 ? '; international spans ' + ((A.country || []).filter(c => c.key && c.key !== 'PK').length) + ' countries.' : '.');
      const s = slide('Geography', 'Where customers order from', action);
      const co = (A.country || []).slice(0, 8);
      panelTitle(s, MX, BODY_TOP, 5.2, 'Revenue by country' + curLbl);
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: co.map(c => c.key || '(blank)'), values: co.map(c => R(c.rev)) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: 5.2, h: BODY_H - 0.5, chartColors: [NAVY], barDir: 'bar', dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd' }));
      // local vs intl donut
      const dx = MX + 5.5;
      panelTitle(s, dx, BODY_TOP, 3.0, 'Local vs. international');
      s.addChart(pptx.ChartType.doughnut, [{ name: 'Revenue', labels: ['Local (PK)', 'International'], values: [R(K.local_rev), R(K.intl_rev)] }],
        baseChartOpts({ x: dx, y: BODY_TOP + 0.5, w: 3.0, h: BODY_H - 0.5, chartColors: [NAVY, AMBER], showValue: false, showPercent: true, showLegend: true, legendPos: 'b', legendColor: MID, legendFontSize: 9, dataLabelColor: WHITE, dataLabelFontSize: 10, holeSize: 55 }));
      // top cities
      const cx = dx + 3.2, cw = PW - MX - cx;
      panelTitle(s, cx, BODY_TOP, cw, 'Top local cities');
      const rows = (A.city || []).slice(0, 8).map(c => [truncate(c.key, 18), num(c.orders), money(c.rev)]);
      if (rows.length) dataTable(s, cx, BODY_TOP + 0.45, cw, ['City', 'Orders', 'Revenue' + curLbl], rows, [cw * 0.44, cw * 0.2, cw * 0.36], { rowH: 0.3, fs: 8.5 });
      else s.addText('No local city data available.', { x: cx, y: BODY_TOP + 0.5, w: cw, h: 0.4, fontFace: FONT, fontSize: 10, color: SOFT, italic: true });
    })();

    // =================================================================
    // 10) SALES TREND (cumulative area + monthly line)
    // =================================================================
    (function trend() {
      const s = slide('Sales trend', 'Momentum & cumulative build', 'Cumulative revenue and monthly rhythm across the reporting window.');
      const labels = mf.map(m => monLbl(m.key));
      panelTitle(s, MX, BODY_TOP, CW / 2 - 0.2, 'Cumulative revenue' + curLbl);
      s.addChart(pptx.ChartType.area, [{ name: 'Cumulative', labels, values: mf.map(m => R(m.runRev)) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: CW / 2 - 0.3, h: BODY_H - 0.5, chartColors: [TEAL], chartColorsOpacity: [40], showValue: true, dataLabelFormatCode: '#,##0', dataLabelPosition: 't', dataLabelFontSize: 7, valAxisLabelFormatCode: '#,##0', lineSize: 2 }));
      panelTitle(s, MX + CW / 2 + 0.1, BODY_TOP, CW / 2 - 0.2, 'Monthly revenue' + curLbl);
      s.addChart(pptx.ChartType.line, [{ name: 'Revenue', labels, values: mf.map(m => R(m.rev)) }],
        baseChartOpts({ x: MX + CW / 2 + 0.1, y: BODY_TOP + 0.5, w: CW / 2 - 0.3, h: BODY_H - 0.5, chartColors: [NAVY], showValue: true, dataLabelFormatCode: '#,##0', dataLabelPosition: 't', dataLabelFontSize: 7, valAxisLabelFormatCode: '#,##0', lineSize: 2.25, lineDataSymbol: 'circle', lineDataSymbolSize: 5 }));
    })();

    // =================================================================
    // 10b) SEASONALITY & EVENT IMPACT (data-driven)
    // =================================================================
    const SEA = A.seasonality || { events: [], monthlyHeat: null, calendarHeat: null, eventMonths: [] };
    const HEAT = ['F2F6FC', 'D9E1F2', 'B4C7E7', '7BA0D6', '305496'];
    function heatCell(v, max) { if (!(v > 0)) return { bg: HEAT[0], fg: SOFT }; const r = v / max, i = r >= 0.8 ? 4 : r >= 0.6 ? 3 : r >= 0.4 ? 2 : r >= 0.2 ? 1 : 0; return { bg: HEAT[i], fg: i >= 3 ? WHITE : INK }; }
    function heatTable(s, x, y, w, corner, colLabels, rowLabels, matrix) {
      const max = Math.max(1, ...matrix.map(r => Math.max(...r)));
      const hopt = { fill: { color: NAVY }, color: WHITE, bold: true, fontSize: 8, valign: 'middle', fontFace: FONT };
      const head = [{ text: corner, options: Object.assign({ align: 'left' }, hopt) }].concat(colLabels.map(c => ({ text: String(c), options: Object.assign({ align: 'center' }, hopt) })));
      const body = rowLabels.map((rl, ri) => [{ text: String(rl), options: { fill: { color: PANEL }, color: INK, bold: true, fontSize: 8, align: 'left', valign: 'middle', fontFace: FONT } }]
        .concat(matrix[ri].map(v => { const hc = heatCell(v, max); return { text: v > 0 ? num(v) : '—', options: { fill: { color: hc.bg }, color: hc.fg, fontSize: 7.5, align: 'center', valign: 'middle', fontFace: FONT } }; })));
      const colW = [w * 0.13].concat(colLabels.map(() => (w * 0.87) / colLabels.length));
      s.addTable([head].concat(body), { x, y, w, colW, rowH: 0.26, valign: 'middle', fontFace: FONT, border: { type: 'solid', pt: 0.5, color: WHITE }, autoPage: false });
    }
    function eventInsights() {
      const out = [], ev = SEA.events.filter(e => e.revChangePct != null);
      if (!ev.length) return out;
      const up = ev.filter(e => e.revChangePct > 0).sort((a, b) => b.revChangePct - a.revChangePct);
      const daily = ev.slice().sort((a, b) => b.during.perDayRev - a.during.perDayRev);
      const acq = ev.map(e => ({ e, nc: Math.max(0, e.during.custs - e.during.ret) })).sort((a, b) => b.nc - a.nc);
      const down = ev.filter(e => e.classification === 'Decline' || e.classification === 'No noticeable change').sort((a, b) => a.revChangePct - b.revChangePct);
      if (up[0]) out.push(up[0].name + ' drove the biggest uplift — revenue per day rose ' + pct(up[0].revChangePct) + ' vs its ' + SEA.radius + '-day baseline.');
      if (daily[0]) out.push(daily[0].name + ' generated the highest daily revenue at ' + money(daily[0].during.perDayRev) + ' per day.');
      if (acq[0] && acq[0].nc > 0) out.push(acq[0].e.name + ' showed the strongest customer acquisition — ' + num(acq[0].nc) + ' new customers during the window.');
      if (down[0]) out.push('No uplift around ' + down[0].name + ' — revenue per day ' + pct(down[0].revChangePct) + ' vs baseline (' + down[0].classification.toLowerCase() + ').');
      return out;
    }
    const verdictColor = c => c && c.indexOf('increase') >= 0 ? GREEN : c === 'Decline' ? CORAL : MID;

    if (SEA.events && SEA.events.length) (function seasonalityImpact() {
      const top = SEA.events.filter(e => e.revChangePct != null)[0];
      const action = top ? (top.name + ' had the strongest measured impact: revenue per day ' + (top.revChangePct >= 0 ? 'up ' : 'down ') + pct(Math.abs(top.revChangePct)) + ' vs baseline — auto-classified “' + top.classification + '”.') : 'Measured impact of calendar events on daily sales.';
      const s = slide('Seasonality', 'Event impact on sales', action);
      // left: event impact table (with colored verdict)
      const tw = 6.9;
      panelTitle(s, MX, BODY_TOP, tw, 'Auto-detected events in the data window', 'Per-day metrics vs a ' + SEA.radius + '-day baseline');
      const hopt = { fill: { color: NAVY }, color: WHITE, bold: true, fontSize: 8.5, fontFace: FONT, valign: 'middle' };
      const heads = ['Event', 'Dates', 'During Rev/day' + curLbl, 'Rev Δ%/day', 'Verdict'];
      const aligns = ['left', 'left', 'right', 'right', 'left'];
      const head = heads.map((hd, i) => ({ text: hd, options: Object.assign({ align: aligns[i] }, hopt) }));
      const body = SEA.events.slice(0, 8).map((e, ri) => {
        const dates = e.start === e.end ? monDay(e.start) : monDay(e.start) + '–' + monDay(e.end);
        const chg = e.revChangePct == null ? 'n/a' : (e.revChangePct >= 0 ? '+' : '') + pct(e.revChangePct);
        const base = { fontSize: 8.5, fontFace: FONT, valign: 'middle', fill: { color: ri % 2 ? WHITE : PANEL } };
        return [
          { text: e.name, options: Object.assign({ align: 'left', color: INK, bold: true }, base) },
          { text: dates, options: Object.assign({ align: 'left', color: MID }, base) },
          { text: money(e.during.perDayRev), options: Object.assign({ align: 'right', color: INK }, base) },
          { text: chg, options: Object.assign({ align: 'right', color: e.revChangePct >= 0 ? GREEN : CORAL, bold: true }, base) },
          { text: e.classification, options: Object.assign({ align: 'left', color: verdictColor(e.classification), bold: true, fontSize: 8 }, base) },
        ];
      });
      s.addTable([head].concat(body), { x: MX, y: BODY_TOP + 0.5, w: tw, colW: [tw * 0.26, tw * 0.2, tw * 0.2, tw * 0.14, tw * 0.2], rowH: 0.3, valign: 'middle', fontFace: FONT, border: { type: 'solid', pt: 0.5, color: RULE }, autoPage: false });
      // right: bar chart of revenue per day during each event (absolute — matches the Excel chart)
      const cx = MX + tw + 0.35, cw = PW - MX - cx;
      panelTitle(s, cx, BODY_TOP, cw, 'Revenue per day during each event' + curLbl);
      const evc = SEA.events.slice(0, 8);
      s.addChart(pptx.ChartType.bar, [{ name: 'During Rev/day', labels: evc.map(e => e.name), values: evc.map(e => R(e.during.perDayRev)) }],
        baseChartOpts({ x: cx, y: BODY_TOP + 0.5, w: cw, h: BODY_H - 0.5, chartColors: [NAVY], barDir: 'bar', dataLabelFormatCode: '#,##0', valAxisLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd', catAxisLabelFontSize: 8 }));
    })();

    (function seasonalityPatterns() {
      const ins = eventInsights();
      const s = slide('Seasonality', 'Seasonal revenue patterns', ins[0] || 'Revenue distribution across months and weekdays.');
      // monthly heatmap (year x month)
      if (SEA.monthlyHeat && SEA.monthlyHeat.years.length) {
        const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        panelTitle(s, MX, BODY_TOP, CW, 'Monthly seasonality heatmap — revenue by year × month' + curLbl);
        heatTable(s, MX, BODY_TOP + 0.5, CW, 'Year', MO, SEA.monthlyHeat.years.map(String), SEA.monthlyHeat.matrix);
      }
      // monthly revenue with event months highlighted
      const yTrend = BODY_TOP + 0.5 + 0.26 * (1 + (SEA.monthlyHeat ? SEA.monthlyHeat.years.length : 0)) + 0.35;
      const evSet = new Set(SEA.eventMonths || []);
      const labels = mf.map(m => monLbl(m.key));
      panelTitle(s, MX, yTrend, CW * 0.62, 'Monthly revenue — event periods highlighted (amber = month contains a major event)');
      s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels, values: mf.map(m => R(m.rev)) }],
        baseChartOpts({ x: MX, y: yTrend + 0.42, w: CW * 0.62, h: BODY_BOT - (yTrend + 0.42), chartColors: mf.map(m => evSet.has(m.key) ? AMBER : NAVY), dataLabelFormatCode: '#,##0', dataLabelFontSize: 7 }));
      // event insight bullets
      const bx = MX + CW * 0.62 + 0.3, bw = PW - MX - bx;
      panelTitle(s, bx, yTrend, bw, 'Event findings');
      if (ins.length) s.addText(ins.map(t => ({ text: t, options: { fontFace: FONT, fontSize: 9.5, color: INK, bullet: { code: '25AA', indent: 14 }, paraSpaceAfter: 6, breakLine: true } })), { x: bx, y: yTrend + 0.42, w: bw, h: BODY_BOT - (yTrend + 0.42), valign: 'top' });
      else s.addText('No calendar events fell within the data window.', { x: bx, y: yTrend + 0.42, w: bw, h: 0.6, fontFace: FONT, fontSize: 10, color: SOFT, italic: true });
    })();

    // =================================================================
    // 11) ORDER VALUE ANALYSIS
    // =================================================================
    (function orderValue() {
      const s = slide('Order value', 'How much customers spend', 'AOV of ' + money(K.aov) + ' with a median of ' + money(K.median_order) + '; distribution by price band below.');
      const BUCK = ['Under 2,000', '2,000-4,999', '5,000-7,999', '8,000-9,999', '10,000-14,999', '15,000-24,999', '25,000+'];
      const bm = {}; (A.bucket || []).forEach(b => bm[b.key] = b);
      const bk = BUCK.filter(b => bm[b]);
      panelTitle(s, MX, BODY_TOP, 8.4, 'Orders by price band', 'Order total distribution');
      s.addChart(pptx.ChartType.bar, [{ name: 'Orders', labels: bk, values: bk.map(b => bm[b].orders || 0) }],
        baseChartOpts({ x: MX, y: BODY_TOP + 0.5, w: 8.4, h: BODY_H - 0.5, chartColors: [NAVY], dataLabelFormatCode: '#,##0', catAxisLabelFontSize: 8 }));
      const gx = MX + 8.7, gw = CW - 8.7;
      const T = [['Average Order Value' + curLbl, money(K.aov), NAVY], ['Median Order Value' + curLbl, money(K.median_order), TEAL], ['Highest Order' + curLbl, money(K.max_order), AMBER], ['Lowest Order' + curLbl, money(K.min_order), MID]];
      T.forEach((t, i) => tile(s, gx, BODY_TOP + 0.05 + i * 1.3, gw, 1.12, t[0], t[1], '', t[2]));
    })();

    // =================================================================
    // 12) INVENTORY & PRODUCT STATUS
    // =================================================================
    (function inventory() {
      const s = slide('Inventory', 'Catalog & product status', 'Catalog composition from the Products export' + (INV.statusKnown ? '; ' + num(INV.active) + ' active, ' + num(INV.draft) + ' draft, ' + num(INV.archived) + ' archived.' : '.'));
      const tiles = [
        ['Distinct Products', num(INV.products), 'unique titles', NAVY],
        ['Catalog Rows / Variants', num(INV.variants), 'from Products file', TEAL],
        ['Vendors / Brands', num(INV.vendors), 'distinct', BLUE],
        ['Product Types', num(INV.productTypes), 'distinct', VIOLET],
        ['Products Sold', num(Math.max(0, (INV.products || 0) - (INV.zeroSales || 0))), 'with ≥1 confirmed sale', GREEN],
        ['Zero-Sales Products', num(INV.zeroSales), 'no confirmed sales', CORAL],
      ];
      const cols = 3, tw = (7.6 - 0.3 * (cols - 1)) / cols;
      tiles.forEach((t, i) => { const r = Math.floor(i / cols), c = i % cols; tile(s, MX + c * (tw + 0.3), BODY_TOP + 0.1 + r * 1.5, tw, 1.32, t[0], t[1], t[2], t[3]); });
      // status donut
      const dx = MX + 8.1, dw = PW - MX - dx;
      panelTitle(s, dx, BODY_TOP, dw, 'Product status');
      if (INV.statusKnown && (INV.active + INV.draft + INV.archived + INV.other) > 0) {
        const labels = [], values = [], colors = [];
        if (INV.active) { labels.push('Active'); values.push(INV.active); colors.push(TEAL); }
        if (INV.draft) { labels.push('Draft'); values.push(INV.draft); colors.push(AMBER); }
        if (INV.archived) { labels.push('Archived'); values.push(INV.archived); colors.push(MID); }
        if (INV.other) { labels.push('Other'); values.push(INV.other); colors.push(SOFT); }
        s.addChart(pptx.ChartType.doughnut, [{ name: 'Status', labels, values }],
          baseChartOpts({ x: dx, y: BODY_TOP + 0.5, w: dw, h: BODY_H - 0.7, chartColors: colors, showValue: false, showPercent: true, showLegend: true, legendPos: 'b', legendColor: MID, legendFontSize: 9, dataLabelColor: WHITE, dataLabelFontSize: 10, holeSize: 55 }));
      } else {
        s.addText('No product Status column in the Products export — status breakdown omitted.', { x: dx, y: BODY_TOP + 0.6, w: dw, h: 1.0, fontFace: FONT, fontSize: 10, color: SOFT, italic: true });
      }
    })();

    // =================================================================
    // 12b) MARKETING / ROAS (optional — only if an ad export was provided)
    // =================================================================
    const MK = A.marketing;
    if (MK) {
      const adCur = MK.currency || '';
      const admoney = v => (adCur ? adCur + ' ' : '') + R(v).toLocaleString('en-US');
      const roasFmt = v => v == null ? 'n/a' : (Math.round(v * 10) / 10).toFixed(1) + '×';
      const marketingInsights = () => {
        const out = [];
        if (MK.roas != null) out.push('Overall ROAS is ' + roasFmt(MK.roas) + ' on ' + admoney(MK.totalSpend) + ' of ad spend, returning ' + admoney(MK.totalRev) + ' in attributed revenue.');
        const bestChan = MK.channels.filter(c => c.roas != null).sort((a, b) => b.roas - a.roas)[0];
        if (bestChan) out.push(bestChan.key + ' delivered the highest ROAS at ' + roasFmt(bestChan.roas) + '.');
        else if (MK.channels[0]) out.push(MK.channels[0].key + ' generated the most attributed revenue (' + admoney(MK.channels[0].rev) + ').');
        if (MK.best && MK.best.roas != null) out.push('Best campaign: “' + MK.best.key + '” at ' + roasFmt(MK.best.roas) + ' ROAS.');
        if (MK.months.length >= 2 && MK.months[0].roas != null && MK.months[MK.months.length - 1].roas != null) {
          const a = MK.months[0].roas, b = MK.months[MK.months.length - 1].roas;
          out.push('ROAS ' + (b >= a ? 'improved' : 'declined') + ' from ' + roasFmt(a) + ' to ' + roasFmt(b) + ' over the period.');
        }
        if (MK.worst && MK.worst.roas != null && MK.worst.key !== (MK.best && MK.best.key)) out.push('Lowest-returning campaign: “' + MK.worst.key + '” at ' + roasFmt(MK.worst.roas) + '.');
        return out;
      };

      (function marketingOverview() {
        const action = MK.roas != null
          ? ('Advertising returned ' + roasFmt(MK.roas) + ' on ' + admoney(MK.totalSpend) + ' spend (' + admoney(MK.totalRev) + ' attributed revenue), sourced from ' + MK.platform + '.')
          : ('Marketing performance from ' + MK.platform + ' — ' + admoney(MK.totalRev) + ' attributed revenue' + (MK.hasSpend ? '' : ' (spend not in export, ROAS omitted)') + '.');
        const s = slide('Marketing', 'Advertising performance & ROAS', action);
        const tiles = [];
        if (MK.hasSpend) tiles.push(['Total Ad Spend' + (adCur ? ' (' + adCur + ')' : ''), admoney(MK.totalSpend), MK.platform, CORAL]);
        if (MK.hasRev) tiles.push(['Attributed Revenue' + (adCur ? ' (' + adCur + ')' : ''), admoney(MK.totalRev), 'from ad export', TEAL]);
        if (MK.roas != null) tiles.push(['ROAS', roasFmt(MK.roas), 'return on ad spend', NAVY]);
        if (MK.cpp != null) tiles.push(['Cost / Purchase' + (adCur ? ' (' + adCur + ')' : ''), admoney(MK.cpp), num(MK.totalPur) + ' purchases', AMBER]);
        else if (MK.hasPur) tiles.push(['Purchases / Conv.', num(MK.totalPur), 'from ad export', AMBER]);
        const n2 = Math.min(4, tiles.length), tw = (CW - 0.3 * (n2 - 1)) / Math.max(1, n2);
        tiles.slice(0, 4).forEach((t, i) => tile(s, MX + i * (tw + 0.3), BODY_TOP + 0.05, tw, 1.15, t[0], t[1], t[2], t[3]));
        const yc = BODY_TOP + 1.45;
        if (MK.months.length) {
          panelTitle(s, MX, yc, CW, 'Monthly ad spend, attributed revenue & ROAS', 'Bars = ' + (adCur || 'spend/revenue') + '  ·  line = ROAS (right axis)');
          const labels = MK.months.map(m => monLbl(m.key));
          const charts = [{ type: pptx.ChartType.bar, data: [{ name: 'Ad Spend', labels, values: MK.months.map(m => R(m.spend)) }, { name: 'Attributed Revenue', labels, values: MK.months.map(m => R(m.rev)) }], options: { chartColors: [CORAL, TEAL], barGrouping: 'clustered', showValue: true, dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd', dataLabelColor: INK, dataLabelFontSize: 7, dataLabelFontFace: FONT } }];
          if (MK.roas != null) charts.push({ type: pptx.ChartType.line, data: [{ name: 'ROAS', labels, values: MK.months.map(m => m.roas) }], options: { chartColors: [NAVY], secondaryValAxis: true, secondaryCatAxis: true, lineSize: 2.25, lineDataSymbol: 'circle', lineDataSymbolSize: 5, showValue: true, dataLabelFormatCode: '0.0', dataLabelPosition: 't', dataLabelColor: NAVY, dataLabelFontSize: 7, dataLabelFontFace: FONT } });
          s.addChart(charts, baseChartOpts({ x: MX, y: yc + 0.5, w: CW, h: BODY_BOT - (yc + 0.5), showValue: false, showLegend: true, legendPos: 'b', legendFontSize: 9, legendColor: MID, legendFontFace: FONT, valAxes: [{ valAxisLabelFormatCode: '#,##0', valGridLine: { style: 'solid', color: 'EDEFF3', size: 1 }, valAxisLabelColor: MID, valAxisLabelFontSize: 8 }, { valAxisLabelFormatCode: '0.0', valGridLine: { style: 'none' }, valAxisLabelColor: NAVY, valAxisLabelFontSize: 8 }], catAxes: [{ catAxisLabelColor: MID, catAxisLabelFontSize: 8 }, { catAxisHidden: true }] }));
        } else {
          // no dates: show channel revenue bar instead
          panelTitle(s, MX, yc, CW, 'Attributed revenue by channel' + (adCur ? ' (' + adCur + ')' : ''));
          const ch = MK.channels.slice(0, 8);
          s.addChart(pptx.ChartType.bar, [{ name: 'Revenue', labels: ch.map(c => c.key), values: ch.map(c => R(c.rev)) }],
            baseChartOpts({ x: MX, y: yc + 0.5, w: CW, h: BODY_BOT - (yc + 0.5), chartColors: [TEAL], barDir: 'bar', dataLabelFormatCode: '#,##0', dataLabelPosition: 'outEnd' }));
        }
      })();

      (function marketingCampaigns() {
        const s = slide('Marketing', 'Campaigns & channels', 'Where ad budget worked hardest — ranked by attributed revenue and ROAS.');
        const realCamps = MK.campaigns.filter(c => c.key !== '(unattributed)');
        const leftW = 7.4;
        if (realCamps.length) {
          panelTitle(s, MX, BODY_TOP, leftW, 'Campaign performance');
          const hopt = { fill: { color: NAVY }, color: WHITE, bold: true, fontSize: 8.5, fontFace: FONT, valign: 'middle' };
          const heads = ['Campaign', 'Spend', 'Revenue', 'ROAS'], al = ['left', 'right', 'right', 'right'];
          const head = heads.map((hd, i) => ({ text: hd + (i && i < 3 && adCur ? ' (' + adCur + ')' : ''), options: Object.assign({ align: al[i] }, hopt) }));
          const body = realCamps.slice(0, 9).map((c, ri) => {
            const base = { fontSize: 8.5, fontFace: FONT, valign: 'middle', fill: { color: ri % 2 ? WHITE : PANEL } };
            return [
              { text: truncate(c.key, 26), options: Object.assign({ align: 'left', color: INK, bold: true }, base) },
              { text: admoney(c.spend), options: Object.assign({ align: 'right', color: MID }, base) },
              { text: admoney(c.rev), options: Object.assign({ align: 'right', color: INK }, base) },
              { text: c.roas == null ? 'n/a' : roasFmt(c.roas), options: Object.assign({ align: 'right', color: c.roas != null && c.roas >= 1 ? GREEN : c.roas != null ? CORAL : MID, bold: true }, base) },
            ];
          });
          s.addTable([head].concat(body), { x: MX, y: BODY_TOP + 0.45, w: leftW, colW: [leftW * 0.4, leftW * 0.2, leftW * 0.22, leftW * 0.18], rowH: 0.3, valign: 'middle', fontFace: FONT, border: { type: 'solid', pt: 0.5, color: RULE }, autoPage: false });
        } else {
          panelTitle(s, MX, BODY_TOP, leftW, 'Channel performance');
          const rows = MK.channels.slice(0, 10).map(c => [truncate(c.key, 24), admoney(c.rev), c.roas == null ? 'n/a' : roasFmt(c.roas)]);
          dataTable(s, MX, BODY_TOP + 0.45, leftW, ['Channel', 'Revenue' + (adCur ? ' (' + adCur + ')' : ''), 'ROAS'], rows, [leftW * 0.5, leftW * 0.3, leftW * 0.2], { rowH: 0.3, fs: 9 });
        }
        // right: channel revenue donut
        const dx = MX + leftW + 0.35, dw = PW - MX - dx;
        panelTitle(s, dx, BODY_TOP, dw, 'Revenue share by channel');
        const ch = MK.channels.slice(0, 6);
        s.addChart(pptx.ChartType.doughnut, [{ name: 'Revenue', labels: ch.map(c => c.key), values: ch.map(c => R(c.rev)) }],
          baseChartOpts({ x: dx, y: BODY_TOP + 0.5, w: dw, h: 2.7, chartColors: SERIES, showValue: false, showPercent: true, showLegend: true, legendPos: 'b', legendColor: MID, legendFontSize: 8, dataLabelColor: WHITE, dataLabelFontSize: 9, holeSize: 55 }));
        // marketing insight bullets under the donut
        const ins = marketingInsights();
        if (ins.length) {
          panelTitle(s, dx, BODY_TOP + 3.35, dw, 'Marketing findings');
          s.addText(ins.slice(0, 4).map(t => ({ text: t, options: { fontFace: FONT, fontSize: 9, color: INK, bullet: { code: '25AA', indent: 12 }, paraSpaceAfter: 5, breakLine: true } })), { x: dx, y: BODY_TOP + 3.7, w: dw, h: BODY_BOT - (BODY_TOP + 3.7), valign: 'top' });
        }
      })();
    }

    // =================================================================
    // 13) TOP INSIGHTS
    // =================================================================
    (function insights() {
      const s = slide('Insights', 'What the numbers are telling us', 'Automatically derived — every statement is computed from the figures above.');
      bulletBox(s, MX, BODY_TOP + 0.05, CW, BODY_H, topInsights(7).map(t => ({ h: t, b: '' })), NAVY);
    })();

    // =================================================================
    // 14) RECOMMENDATIONS
    // =================================================================
    (function recommendations() {
      const s = slide('Recommendations', 'Where to focus next', 'Rule-based actions triggered by the calculated metrics.');
      const recs = buildRecs();
      bulletBox(s, MX, BODY_TOP + 0.05, CW, BODY_H, recs, TEAL);
    })();

    // =================================================================
    // 15) APPENDIX  (supporting tables)
    // =================================================================
    (function appendix() {
      const s = slide('Appendix', 'Supporting detail', 'Source figures behind the charts — matches the Excel workbook.');
      panelTitle(s, MX, BODY_TOP, CW / 2 - 0.2, 'Monthly performance');
      const mrows = mf.slice(-12).map(m => [monLbl(m.key), num(m.orders), money(m.rev), num(m.units), growthTxt(m.momRev)]);
      const w1 = CW / 2 - 0.2;
      dataTable(s, MX, BODY_TOP + 0.4, w1, ['Month', 'Orders', 'Revenue' + curLbl, 'Units', 'MoM'], mrows, [w1 * 0.24, w1 * 0.16, w1 * 0.3, w1 * 0.14, w1 * 0.16], { rowH: 0.26, fs: 8 });
      const vx = MX + CW / 2 + 0.1, w2 = CW / 2 - 0.2;
      panelTitle(s, vx, BODY_TOP, w2, 'Category performance');
      const crows = cats.slice(0, 12).map(c => [truncate(c.key, 22), num(c.units), money(c.rev), pct(K.merch_rev ? (c.rev || 0) / K.merch_rev : 0)]);
      dataTable(s, vx, BODY_TOP + 0.4, w2, ['Category', 'Units', 'Revenue' + curLbl, '% Rev'], crows, [w2 * 0.4, w2 * 0.16, w2 * 0.28, w2 * 0.16], { rowH: 0.26, fs: 8 });
    })();

    // ---- helpers that need model scope ----
    function bestMonth() {
      let bm = null; mf.forEach(m => { if (!bm || m.rev > bm.rev) bm = m; });
      return bm ? money(bm.rev) + '  (' + monLbl(bm.key) + ')' : 'n/a';
    }
    function topInsights(n) {
      const out = [];
      if (yoy != null) out.push('Revenue ' + (yoy >= 0 ? 'grew' : 'declined') + ' ' + growthTxt(yoy) + ' year-over-year (' + yrs[yrs.length - 2].key + ' → ' + yrs[yrs.length - 1].key + ').');
      if (cats[0]) out.push(cats[0].key + ' is the top category, contributing ' + pct(topCatShare) + ' of merchandise revenue.');
      out.push('The top 10 products account for ' + pct(top10Share) + ' of merchandise revenue.');
      out.push('Returning customers generate ' + pct(retRevShare) + ' of identified-customer revenue at a ' + pct(K.repeat_rate) + ' repeat rate.');
      out.push('Local (PK) orders make up ' + pct(K.local_rev_pct) + ' of revenue; international contributes ' + pct(1 - K.local_rev_pct) + '.');
      out.push(peakDay + ' is the strongest order day, and weekends account for ' + pct(weekendShare) + ' of order volume.');
      out.push('Average order value is ' + money(K.aov) + ' (median ' + money(K.median_order) + '), with ' + dec1(K.units_per_order) + ' units per order.');
      if (A.zeroSales) out.push(num(A.zeroSales) + ' catalog products recorded zero confirmed sales — a long-tail opportunity.');
      return out.slice(0, n);
    }
    function buildRecs() {
      const r = [];
      if (K.repeat_rate < 0.25) r.push({ h: 'Strengthen retention', b: 'Repeat purchase rate is only ' + pct(K.repeat_rate) + '. Launch post-purchase flows, loyalty rewards and win-back campaigns to lift returning-customer share.' });
      else r.push({ h: 'Protect a healthy repeat base', b: 'A ' + pct(K.repeat_rate) + ' repeat rate is a strength — formalize loyalty tiers to defend and extend it.' });
      if (topCatShare > 0.5 && cats[0]) r.push({ h: 'Diversify category concentration', b: cats[0].key + ' represents ' + pct(topCatShare) + ' of revenue. Broaden the assortment to reduce single-category dependence.' });
      if (top10Share > 0.5) r.push({ h: 'Reduce hero-SKU dependence', b: 'The top 10 products drive ' + pct(top10Share) + ' of revenue. Develop the next tier of products and cross-sell around the heroes.' });
      if (weekendShare > 0.34) r.push({ h: 'Lean into weekend demand', b: 'Weekends deliver ' + pct(weekendShare) + ' of orders. Concentrate promotions, ad spend and drops around ' + peakDay + '.' });
      if (K.local_rev_pct > 0.8) r.push({ h: 'Unlock international growth', b: 'Only ' + pct(1 - K.local_rev_pct) + ' of revenue is international. Test targeted shipping offers and localized marketing in top non-PK countries.' });
      if (A.zeroSales > 0) r.push({ h: 'Activate the long tail', b: num(A.zeroSales) + ' products have zero confirmed sales. Review merchandising, imagery and pricing, or retire dead stock.' });
      if (K.aov && K.median_order && K.aov > K.median_order * 1.3) r.push({ h: 'Lift the typical basket', b: 'Mean AOV (' + money(K.aov) + ') sits well above the median (' + money(K.median_order) + '), signalling a few large orders. Use bundles and thresholds to raise the typical order.' });
      return r.slice(0, 6);
    }

    return pptx.write({ outputType: 'blob' });
  }

  // ---- module-level helpers ----
  function truncate(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function deriveCompany(A) {
    const v = (A.vendor || []).filter(x => x.key && x.key !== 'Unmapped');
    if (v.length === 1) return v[0].key;
    if (v.length > 1 && A.kpi.merch_rev && v[0].rev / A.kpi.merch_rev > 0.6) return v[0].key;
    return 'Commerce Analytics';
  }

  root.ReportPPTX = { buildPPTX };
})(typeof window !== 'undefined' ? window : globalThis);
