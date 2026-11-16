// Stock Analysis: verdict first, then lazily-loaded tabs (same content/order as the Streamlit page).
import { api, qs, getMeta } from '../api.js';
import { addWatch, getPrefs, setPrefs, getWatchlist } from '../store.js';
import { analysisUrl, navigate } from '../router.js';
import { draw, line, area, bars, heat, histogram, priceEvents, macd as macdSpec, COLORS } from '../charts.js';
import {
  h, tile, banner, b, section, into, tabs, table, frameTable, details, openSheet, toast, select, field, seg,
  num, pct, pctR, money, big, signed, tone, DASH, loading, metricDescriptions,
} from '../ui.js';

const MONEY_AXIS = "datum.value >= 1e9 || datum.value <= -1e9 ? '$' + format(datum.value / 1e9, '.1f') + 'B' : (datum.value >= 1e6 || datum.value <= -1e6 ? '$' + format(datum.value / 1e6, '.0f') + 'M' : '$' + format(datum.value, ',.0f'))";
const POPULAR = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'JPM', 'KO', 'SPY'];
const HORIZONS = [['3mo', '3 Months'], ['6mo', '6 Months'], ['1y', '1 Year'], ['2y', '2 Years'], ['5y', '5 Years'], ['10y', '10 Years'], ['custom', 'Custom range']];
const TABS = [['overview', 'Overview'], ['fundamentals', 'Fundamentals'], ['financials', 'Financials'], ['technicals', 'Technicals'], ['risk', 'Risk'], ['events', 'Price & Events']];

export async function render({ el, params, query, alive }) {
  const ticker = (params[0] || '').toUpperCase();
  if (!ticker) return renderSearch(el);

  const prefs = getPrefs('analysis');
  const meta = await getMeta().catch(() => ({ metric_desc: {}, fundamental_desc: {}, technical_desc: {}, profiles: {} }));
  const P = {
    horizon: prefs.horizon, profile: prefs.profile, rf: prefs.rf, outlier_z: prefs.outlier_z, rolling: prefs.rolling,
    ...(prefs.horizon === 'custom' ? { start: prefs.start, end: prefs.end } : {}),
  };
  const url = (ep, extra) => `/analysis/${encodeURIComponent(ticker)}/${ep}${qs({ ...P, ...extra })}`;

  el.append(headBar(ticker, prefs));
  const top = h('div', { class: 'stack' });
  el.append(top);

  let overview;
  try {
    top.append(loading(`Loading ${ticker}…`));
    overview = await api(url('overview'), { ttl: 60e3 });
  } catch (e) {
    top.replaceChildren(banner('error', e.message), h('p', null, h('a', { href: '#/analysis' }, '← Try another ticker')));
    return;
  }
  if (!alive()) return;
  top.replaceChildren(...heroAndVerdict(overview, ticker, prefs, meta));

  const ctx = { ticker, P, url, meta, overview };
  const active = TABS.some(([id]) => id === query.get('tab')) ? query.get('tab') : 'overview';
  const tabEl = tabs(TABS.map(([id, label]) => ({ id, label, load: (panel) => loaders[id](panel, ctx) })), {
    active,
    onSelect: (id) => history.replaceState(null, '', analysisUrl(ticker, id)),
  });
  el.append(tabEl);
  el.append(h('p', { class: 'tiny muted', style: { marginTop: '18px' } },
    'Keep going: ', h('a', { href: '#/screener' }, 'Screener'), ' · ', h('a', { href: `#/compare?tickers=${ticker}` }, 'Compare'),
    ' · ', h('a', { href: '#/portfolio' }, 'Portfolio'), '. Research and education only — not investment advice.'));
}

// ---------------------------------------------------------------- header + search
function renderSearch(el) {
  const go = (t) => { const v = t.trim().toUpperCase(); if (v) navigate(`/analysis/${encodeURIComponent(v)}`); };
  const input = h('input', { type: 'search', placeholder: 'Ticker, e.g. AAPL', autocapitalize: 'characters', autocomplete: 'off', enterkeyhint: 'go',
    onkeydown: (e) => { if (e.key === 'Enter') go(input.value); } });
  const wl = getWatchlist().map((i) => i.ticker);
  el.append(
    h('div', { class: 'page-head' }, h('h1', null, 'Stock Analysis')),
    h('p', { class: 'sub' }, 'Deep-dive research for a single ticker — verdict, fundamentals, technicals, risk and price context.'),
    h('div', { class: 'row' }, h('div', { class: 'grow' }, input), h('button', { class: 'btn primary', onclick: () => go(input.value) }, 'Analyze')),
    wl.length ? section('Your watchlist', null, h('div', { class: 'chips' }, wl.map((t) => h('a', { class: 'chip', href: analysisUrl(t) }, t)))) : null,
    section('Popular', null, h('div', { class: 'chips' }, POPULAR.map((t) => h('a', { class: 'chip', href: analysisUrl(t) }, t)))));
  setTimeout(() => input.focus(), 50);
}

function headBar(ticker, prefs) {
  const input = h('input', { type: 'search', value: ticker, autocapitalize: 'characters', 'aria-label': 'Ticker', enterkeyhint: 'go',
    onkeydown: (e) => { if (e.key === 'Enter' && input.value.trim()) navigate(`/analysis/${encodeURIComponent(input.value.trim().toUpperCase())}`); } });
  return h('div', { class: 'row', style: { marginBottom: '12px' } },
    h('div', { class: 'grow' }, input),
    h('button', { class: 'btn', onclick: () => settingsSheet(prefs) }, '⚙ Settings'));
}

function settingsSheet(prefs) {
  let cur = { ...prefs };
  const dates = h('div', { class: 'grid g2' },
    field('Start', h('input', { type: 'date', value: cur.start, onchange: (e) => { cur.start = e.target.value; } })),
    field('End', h('input', { type: 'date', value: cur.end, onchange: (e) => { cur.end = e.target.value; } })));
  dates.hidden = cur.horizon !== 'custom';
  const z = h('span', null, num(cur.outlier_z, 1));
  const body = h('div', { class: 'stack' },
    field('Time horizon', select(HORIZONS.map(([v, l]) => ({ value: v, label: l })), cur.horizon, (v) => { cur.horizon = v; dates.hidden = v !== 'custom'; })),
    dates,
    field('Investor profile', select(['Balanced', 'Value', 'Growth', 'Income'], cur.profile, (v) => { cur.profile = v; })),
    field('Annual risk-free rate (0–0.20)', h('input', { type: 'number', step: '0.01', min: '0', max: '0.2', value: cur.rf, onchange: (e) => { cur.rf = Number(e.target.value); } })),
    field('Rolling volatility window (days)', select(['21', '30', '60'], String(cur.rolling), (v) => { cur.rolling = Number(v); })),
    field(h('span', null, 'Outlier-day threshold (|z|): ', z), h('input', { type: 'range', min: '2', max: '4', step: '0.5', value: cur.outlier_z, oninput: (e) => { cur.outlier_z = Number(e.target.value); z.textContent = num(cur.outlier_z, 1); } })),
    h('button', { class: 'btn primary block', onclick: () => {
      if (cur.horizon === 'custom' && (!cur.start || !cur.end || cur.start >= cur.end)) { toast('Pick a start date before the end date.'); return; }
      if (!(cur.rf >= 0 && cur.rf <= 0.2)) { toast('Risk-free rate must be between 0 and 0.20.'); return; }
      setPrefs('analysis', cur); close();
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    } }, 'Apply'));
  const close = openSheet('Analysis settings', body);
}

// ---------------------------------------------------------------- hero + verdict
const VERDICT = { Buy: ['#1e8449', '🟢'], Hold: ['#b9770e', '🟡'], Avoid: ['#a93226', '🔴'] };

function heroAndVerdict(o, ticker, prefs, meta) {
  const hero = o.hero, pres = o.prescription;
  const [vc, vi] = VERDICT[pres.verdict] || VERDICT.Hold;
  const range = hero.week_low && hero.week_high ? h('div', { class: 'range' },
    h('div', { class: 'small muted' }, `52-week range: ${money(hero.week_low)} – ${money(hero.week_high)}`,
      hero.pct_of_range !== null ? `  ·  ${num(hero.pct_of_range, 0)}% of range` : ''),
    hero.pct_of_range !== null ? h('div', { class: 'bar', style: { marginTop: '4px' } }, h('i', { style: { width: `${Math.max(0, Math.min(100, hero.pct_of_range))}%` } })) : null) : null;
  const w = pres.weights || {};
  const rows = [['Valuation', 'valuation'], ['Quality', 'quality'], ['Momentum', 'momentum'], ['Macro', 'macro']].map(([label, k]) =>
    h('div', { class: 'row between', style: { alignItems: 'flex-start', padding: '6px 0', borderBottom: '1px solid var(--border)' } },
      h('div', null, h('b', null, `${label} `), h('span', { class: 'muted small' }, `weight ${num((w[k] || 0) * 100, 0)}%`),
        h('div', { class: 'small muted' }, (pres[`${k}_rationale`] || []).join('  ·  ') || DASH)),
      h('b', { class: 'mono' }, `${num(pres[`${k}_score`], 0)}/100`)));
  return [
    h('div', { class: 'card' },
      h('h2', { style: { margin: 0 } }, `${hero.ticker} · ${hero.name}`),
      h('div', { class: 'small muted' }, `${hero.sector} · ${hero.industry}`),
      h('div', { class: 'row', style: { marginTop: '8px', alignItems: 'baseline' } },
        h('span', { class: 'mono', style: { fontSize: '2rem', fontWeight: 800 } }, money(hero.price)),
        h('span', { class: `mono ${tone(hero.day_change_abs)}`, style: { fontWeight: 700 } }, `${signed(hero.day_change_abs, 2)} (${pct(hero.day_change_pct, 2, true)})`)),
      range,
      h('div', { class: 'row', style: { marginTop: '10px' } },
        h('button', { class: 'btn small', onclick: () => toast(addWatch(ticker) ? `${ticker} added to watchlist` : `${ticker} already on watchlist`) }, '＋ Watchlist'),
        h('a', { class: 'btn small', href: `#/compare?tickers=${ticker}` }, 'Compare'))),
    h('div', { class: 'split' },
      h('div', { class: 'verdict', style: { '--vc': vc } },
        h('div', { class: 'k' }, `Verdict · ${pres.profile} investor`),
        h('div', { class: 'big' }, `${vi} ${pres.verdict}`),
        h('div', { class: 'small muted' }, 'Confidence: ', h('b', null, pres.confidence), '  ·  Composite: ', h('b', null, `${num(pres.composite_score, 0)}/100`))),
      h('div', { class: 'thesis' }, h('div', { class: 'k' }, 'Thesis'), h('div', { class: 't' }, pres.thesis))),
    details('How was this verdict calculated?', h('div', null,
      h('p', { class: 'small muted' }, `Weights reflect the ${pres.profile} profile. ${o.profile_description || ''} Each component is scored 0–100; the composite is their weighted average.`),
      rows,
      h('p', { class: 'small muted', style: { marginTop: '8px' } }, 'Thresholds: Buy ≥ 60 · Hold 48–59 · Avoid < 48. The engine is rule-based — change the profile in Settings to see the verdict adapt.'))),
  ];
}

// ---------------------------------------------------------------------- tabs
const loaders = {
  async overview(panel, c) {
    const o = c.overview;
    const bandCls = { Strong: 'pill-good', Solid: 'pill-good', Fair: 'pill-warn', Weak: 'pill-bad', Poor: 'pill-bad' };
    const m = o.macro, vix = m['^VIX'], tnx = m['^TNX'], spy = m.SPY, k = o.key_stats;
    panel.append(h('div', { class: 'stack' },
      section('Dimension scores', 'Open the matching tab to go deeper.',
        h('div', { class: 'grid g2' }, o.dimensions.map((d) => h('div', { class: 'tile' },
          h('div', { class: 'label' }, d.name), h('div', { class: 'value' }, d.band),
          h('div', { class: 'delta mono' }, `${num(d.score, 0)}/100`),
          h('div', { class: 'note' }, d.rationale.join(' · ') || DASH))))),
      section('Macro regime', 'The backdrop against which any single-stock thesis plays out.',
        h('div', { class: 'grid g3' },
          tile({ label: `VIX${vix.label ? ` — ${vix.label}` : ''}`, value: num(vix.current, 1), sub: signed(vix.change_pct, 1, '% 1d'), subTone: tone(-vix.change_pct), note: 'Fear gauge. Low = risk-on.' }),
          tile({ label: `10Y Treasury${tnx.label ? ` — ${tnx.label}` : ''}`, value: tnx.current === null ? DASH : `${num(tnx.current)}%`, sub: signed(tnx.change_pct, 2, '% 1d'), subTone: tone(tnx.change_pct), note: 'Rising yields = headwind for growth.' }),
          tile({ label: 'SPY', value: money(spy.current), sub: signed(spy.change_pct, 2, '% 1d'), subTone: tone(spy.change_pct), note: 'Broad market reference.' }))),
      section('Key stats', null, h('div', { class: 'grid g4' },
        tile({ label: 'Market cap', value: big(k.market_cap) }),
        tile({ label: 'Beta', value: num(k.beta) }),
        tile({ label: 'Dividend yield', value: k.dividend_yield ? pctR(k.dividend_yield, 2) : '0.00%' }),
        tile({ label: 'Forward P/E', value: num(k.forward_pe, 1) }),
        tile({ label: 'P/E (TTM)', value: num(k.trailing_pe, 1) }),
        tile({ label: 'ROE', value: pctR(k.roe, 1) }),
        tile({ label: 'Revenue growth', value: pctR(k.revenue_growth, 1) }),
        tile({ label: 'Total return (period)', value: pct(k.total_return, 2, true), valueTone: tone(k.total_return) })))));
  },

  async fundamentals(panel, c) {
    const box = h('div', { class: 'stack' });
    let withCtx = false, timer = null;
    const toggle = h('label', { class: 'check' }, h('input', { type: 'checkbox', onchange: (e) => { withCtx = e.target.checked; draw_(); } }),
      h('span', null, 'Show sector & universe percentile context'));
    panel.append(toggle, h('p', { class: 'tiny muted' }, 'Builds the S&P 500 universe in the background the first time (a few minutes), then it is cached.'), box);

    async function draw_() {
      clearTimeout(timer);
      await into(box, async () => {
        const f = await api(c.url('fundamentals', { context: withCtx ? 'true' : null }), { ttl: withCtx ? 0 : 60e3 });
        const out = fundamentalsView(f, c, withCtx);
        if (withCtx && !f.context.available && f.context.universe && f.context.universe.status === 'building') {
          timer = setTimeout(() => { if (box.isConnected && withCtx) draw_(); }, 4000);
        }
        return out;
      });
    }
    await draw_();
  },

  async financials(panel, c) {
    let freq = 'annual';
    const box = h('div', { class: 'stack' });
    panel.append(h('div', { class: 'row between' }, h('span', { class: 'muted small' }, 'Source: SEC filings (XBRL), Yahoo as fallback'),
      seg([{ value: 'annual', label: 'Annual' }, { value: 'quarterly', label: 'Quarterly' }], freq, (v) => { freq = v; load(); })), box);
    const load = () => into(box, async () => financialsView(await api(c.url('financials', { freq }), { ttl: 60e3 }), c), 'Loading statements…');
    await load();
  },

  async technicals(panel, c) {
    await into(panel, async () => technicalsView(await api(c.url('technicals'), { ttl: 60e3 }), c));
  },

  async risk(panel, c) {
    await into(panel, async () => riskView(await api(c.url('risk'), { ttl: 60e3 }), c));
  },

  async events(panel, c) {
    await eventsTab(panel, c);
  },
};

// ------------------------------------------------------------- fundamentals view
function fundamentalsView(f, c, withCtx) {
  const desc = c.meta.fundamental_desc || {};
  const deltaTile = (m, fmtVal) => {
    let sub = null, st = '';
    if (m.delta !== null && m.delta !== undefined) {
      sub = `${signed(m.delta, 1, m.delta_unit)} vs sector${m.delta_unit === '%' ? ` (median ${num(m.sector_median)})` : ''}`;
      const good = m.direction === 'lower' ? -m.delta : m.delta;
      st = tone(good);
    }
    return tile({ label: m.label, value: m.value === null ? DASH : fmtVal(m.value), sub, subTone: st, note: desc[m.key] });
  };
  const out = [];
  out.push(section('Valuation', 'Is the stock cheap, fair or expensive — by peer comparison and by its own history?',
    h('div', { class: 'grid g2' }, f.valuation.map((m) => deltaTile(m, (v) => num(v, 2))))));
  out.push(section('Quality', 'Is this a fundamentally healthy business?',
    h('div', { class: 'grid g2' }, f.quality.map((m) => deltaTile(m, (v) => (m.is_pct ? pctR(v, 1) : num(v, 2)))))));
  out.push(section('Growth', null, h('div', { class: 'grid g2' }, f.growth.map((m) =>
    m.key === 'freeCashflow'
      ? tile({ label: m.label, value: big(m.value), note: 'Cash left after operating costs and capex — fuel for dividends, buybacks and investment.' })
      : tile({ label: m.label, value: m.value === null ? DASH : pctR(m.value, 1, true), note: desc[m.key] })))));

  if (f.dividends) out.push(dividendsView(f.dividends));

  const ctxInfo = f.context;
  if (withCtx) {
    if (ctxInfo.available) {
      if (ctxInfo.percentiles.length) {
        out.push(section('Sector percentile ranking', `Where ${c.ticker} sits within ${f.sector} (100 = best in sector).`,
          h('div', { class: 'chart', ref: 'pct' })));
        const holder = out[out.length - 1].querySelector('.chart');
        setTimeout(() => draw(holder, {
          data: { values: ctxInfo.percentiles },
          mark: { type: 'bar', cornerRadiusEnd: 3 },
          encoding: {
            y: { field: 'metric', type: 'nominal', sort: '-x', axis: { title: null } },
            x: { field: 'percentile', type: 'quantitative', scale: { domain: [0, 100] }, axis: { title: 'Sector percentile' } },
            color: { field: 'percentile', type: 'quantitative', scale: { scheme: 'redyellowgreen', domain: [0, 100] }, legend: null },
            tooltip: [{ field: 'metric' }, { field: 'percentile', format: '.0f' }],
          },
        }, { height: Math.max(160, 38 * ctxInfo.percentiles.length) }), 0);
      }
      if (ctxInfo.peers.length) {
        out.push(banner('info', b('Compare head-to-head → '), 'open ', h('a', { href: `#/compare?tickers=${[c.ticker, ...ctxInfo.peers].join(',')}` }, 'Compare'),
          ` with ${[c.ticker, ...ctxInfo.peers].join(', ')}.`));
      }
    } else if (ctxInfo.universe && ctxInfo.universe.status === 'building') {
      const u = ctxInfo.universe;
      out.push(banner('info', b('Building the S&P 500 universe… '), `${u.done}/${u.total} companies. This page refreshes automatically.`,
        h('div', { class: 'bar', style: { marginTop: '8px' } }, h('i', { style: { width: `${u.total ? (u.done / u.total) * 100 : 0}%` } }))));
    } else {
      out.push(banner('warning', 'Sector context is not available right now (the data provider may be rate-limiting). Try again shortly.'));
    }
  } else {
    out.push(banner('info', 'Turn on ', b('sector & universe percentile context'), ' above to see how this stock ranks against its sector.'));
  }
  return out;
}

function dividendsView(d) {
  const y = d.yield;
  const chartBars = h('div', { class: 'chart' }), chartPayout = h('div', { class: 'chart' });
  const vs = y.current_yield !== null && y.avg_yield ? (y.current_yield - y.avg_yield) / y.avg_yield * 100 : null;
  const hist = d.history.map((r) => ({ year: String(r.year), dps: r.dps, yoy: r.yoy, payout: r.payout_ratio }));
  setTimeout(() => {
    draw(chartBars, {
      data: { values: hist },
      layer: [
        { mark: { type: 'bar', color: COLORS.good, cornerRadiusEnd: 2 } },
        { transform: [{ filter: 'datum.yoy != null' }], mark: { type: 'text', dy: -8, fontSize: 10 },
          encoding: { text: { field: 'yoy', type: 'quantitative', format: '+.0%' }, color: { value: 'var(--text)' } } },
      ],
      encoding: { x: { field: 'year', type: 'ordinal', axis: { title: null, labelAngle: 0 } },
                  y: { field: 'dps', type: 'quantitative', axis: { title: 'Dividend per share ($)', format: '$.2f' } },
                  tooltip: [{ field: 'year' }, { field: 'dps', format: '$.2f' }, { field: 'yoy', format: '+.1%' }] },
    }, { height: 210 });
    const withPayout = hist.filter((r) => r.payout !== null);
    if (withPayout.length >= 2) {
      draw(chartPayout, {
        layer: [
          { data: { values: withPayout }, mark: { type: 'line', point: true, color: '#34495e' },
            encoding: { x: { field: 'year', type: 'ordinal', axis: { title: null, labelAngle: 0 } }, y: { field: 'payout', type: 'quantitative', axis: { title: 'Payout ratio', format: '%' } },
              tooltip: [{ field: 'year' }, { field: 'payout', format: '.0%' }] } },
          { data: { values: [{ y: 0.6 }] }, mark: { type: 'rule', color: '#f39c12', strokeDash: [4, 4] }, encoding: { y: { field: 'y', type: 'quantitative' } } },
          { data: { values: [{ y: 0.8 }] }, mark: { type: 'rule', color: '#e74c3c', strokeDash: [4, 4] }, encoding: { y: { field: 'y', type: 'quantitative' } } },
        ],
      }, { height: 170 });
    } else chartPayout.remove();
  }, 0);
  const pay = d.latest_payout;
  return section('Dividends', 'Per-share dividend track record and payout sustainability (declared DPS from 10-K filings).',
    h('div', { class: 'grid g2' },
      tile({ label: 'Current yield', value: pctR(y.current_yield, 2), note: y.avg_yield !== null ? `${y.n_years}y avg: ${pctR(y.avg_yield, 2)}` : null }),
      tile({ label: 'Rich / cheap vs history', value: vs === null ? DASH : signed(vs, 0, `% vs ${y.n_years}y avg`), note: 'Above the trailing-avg yield = cheaper; below = richer.' }),
      tile({ label: '5y DPS CAGR', value: pctR(d.cagr_5y, 1), note: d.cagr_3y !== null ? `3y: ${pctR(d.cagr_3y, 1)}` : null }),
      tile({ label: 'Growth streak', value: d.streak ? `${d.streak}y` : DASH, note: 'Consecutive years with non-decreasing DPS.' }),
      tile({ label: 'Payout ratio', value: pay === null ? DASH : pctR(pay, 0), note: pay > 0.8 ? '⚠ High payout — limited cushion.' : pay > 0.6 ? 'Elevated payout — watch EPS.' : 'DPS ÷ diluted EPS.' })),
    chartBars, chartPayout,
    h('p', { class: 'tiny muted' }, 'Dashed lines mark the 60% (watch) and 80% (stress) payout thresholds.'));
}

// ------------------------------------------------------------- financials view
const F = {
  ratio: (v) => pctR(v, 1), mult: (v) => num(v, 2), money: (v) => big(v), none: (v) => num(v, 2),
};
function periodLabels(periods, freq) { return periods.map((p) => (freq === 'annual' ? p.slice(0, 4) : p.slice(0, 7))); }

function financialsView(f, c) {
  if (!f.available) return banner('warning', 'No financial statements available for this ticker. Coverage is spotty for ETFs, non-US stocks and some small caps.');
  const out = [];
  const pills = { Strong: 'pill-good', Solid: 'pill-good', Fair: 'pill-warn', Weak: 'pill-bad' };
  const sc = f.scorecard;
  out.push(h('div', { class: 'grid g3' }, [['Profitability', sc.profitability], ['Earnings Quality', sc.earnings_quality], ['Balance Sheet', sc.balance_sheet]].map(([n, s]) =>
    h('div', { class: `tile ${pills[s.label] || ''}` }, h('div', { class: 'label' }, n), h('div', { class: 'value' }, s.label),
      h('div', { class: 'delta mono' }, s.score === null ? DASH : `${num(s.score, 0)}/100`)))));
  const sub = (title, caption, ...kids) => h('div', { class: 'section' }, h('h3', null, title), h('p', { class: 'sub' }, caption), ...kids);
  const tbl = (part, fmts) => (part ? h('div', null, frameTable(part.table, fmts)) : banner('info', 'Not available for this ticker.'));
  const years = periodLabels(f.periods, f.freq);

  out.push(h('h2', { style: { marginTop: '14px' } }, 'Profitability architecture'));
  if (f.dupont) out.push(sub('1. DuPont ROE decomposition', 'ROE = Net Margin × Asset Turnover × Equity Multiplier.', tbl(f.dupont, { 'Net Margin': F.ratio, ROE: F.ratio, 'Asset Turnover': F.mult, 'Equity Multiplier': F.mult }),
    f.dupont.latest_roe !== null ? h('p', { class: 'small' }, 'Latest ROE ', b(pctR(f.dupont.latest_roe, 1)), ' — primary driver: ', b(f.dupont.driver), '.') : null));
  if (f.margins) {
    const chart = h('div', { class: 'chart' });
    const t = f.margins.table;
    setTimeout(() => draw(chart, line({ dates: f.periods, yFormat: '%', xFormat: f.freq === 'annual' ? '%Y' : '%b %Y',
      series: t.index.map((name, i) => ({ name, values: t.data[i] })) }), { height: 230 }), 0);
    out.push(sub('2. Margin decomposition', 'Where profit leaks as revenue moves from top line to bottom line.',
      tbl(f.margins, Object.fromEntries(f.margins.table.index.map((k) => [k, F.ratio]))), chart,
      f.margins.biggest_leak !== '—' ? h('p', { class: 'small' }, 'Biggest margin drop in the latest period: ', b(f.margins.biggest_leak), '.') : null));
  }
  if (f.roic) out.push(sub('3. ROIC (indirect NOPAT)', 'NOPAT = (NI + Tax + Interest − Non-op income) × (1 − tax rate). ROIC = NOPAT ÷ avg (Debt + Equity − Cash).',
    tbl(f.roic, { NOPAT: F.money, 'Invested Capital': F.money, 'Effective tax rate': F.ratio, ROIC: F.ratio }),
    f.roic.latest_roic !== null ? banner(f.roic.creates_value ? 'success' : 'warning', 'Latest ROIC ', b(pctR(f.roic.latest_roic, 1)), ` vs WACC proxy ${pctR(f.roic.wacc_proxy, 0)} — `, b(f.roic.creates_value ? 'creates value' : 'destroys value'), '.') : null));

  out.push(h('h2', { style: { marginTop: '14px' } }, 'Earnings quality'));
  if (f.revenue_quality) {
    const r = f.revenue_quality, bits = [];
    if (r.cagr_3y !== null) bits.push(['3y revenue CAGR ', b(pctR(r.cagr_3y, 1))]);
    if (r.latest_yoy !== null) bits.push(['latest YoY ', b(pctR(r.latest_yoy, 1))]);
    out.push(sub('4. Revenue quality', 'Growth pace and whether rising revenue is collected as cash.',
      tbl(r, { Revenue: F.money, 'Revenue YoY': F.ratio, 'AR / Revenue': F.ratio, 'AR YoY': F.ratio }),
      bits.length ? h('p', { class: 'small' }, bits.map((x, i) => [i ? ' · ' : null, ...x])) : null,
      r.ar_outpacing_revenue ? banner('warning', '⚠ Receivables are growing >10pp faster than revenue — watch collections.') : null));
  }
  if (f.earnings_quality) {
    const e = f.earnings_quality, chart = h('div', { class: 'chart' }), t = e.table;
    const row = (name) => t.data[t.index.indexOf(name)];
    setTimeout(() => draw(chart, line({ dates: f.periods, yLabelExpr: MONEY_AXIS, xFormat: f.freq === 'annual' ? '%Y' : '%b %Y',
      series: [{ name: 'Net Income', values: row('Net Income'), color: '#e67e22' }, { name: 'Operating Cash Flow', values: row('Operating Cash Flow'), color: '#2980b9' }] }), { height: 230 }), 0);
    out.push(sub('5. Earnings quality — NI vs OCF', 'Cash flow should track reported earnings; persistent gaps suggest aggressive accruals or working-capital drag.',
      tbl(e, { 'Net Income': F.money, 'Operating Cash Flow': F.money, '(OCF − NI) / |NI|': F.ratio, 'Effective tax rate': F.ratio }), chart,
      h('p', { class: 'small' }, e.latest_gap !== null ? ['Latest OCF−NI gap: ', b(pctR(e.latest_gap, 1))] : null),
      e.tax_unstable ? banner('warning', `Effective tax rate is volatile (σ = ${pctR(e.tax_std, 1)}).`) : null));
  }
  if (f.accruals) {
    const a = f.accruals, kind = { Clean: 'success', Watch: 'warning', 'Red flag': 'error' }[a.band];
    out.push(sub('6. Accruals (Sloan ratio)', '(NI − OCF) ÷ avg assets. Lower is better — high accruals historically predict weaker returns.',
      tbl(a, { 'Sloan accrual ratio': F.ratio }),
      a.latest !== null ? banner(kind || 'info', 'Latest: ', b(pctR(a.latest, 1)), ' · ', b(a.band), '  (< 5% clean · 5–10% watch · > 10% red flag)') : null));
  }
  if (f.fcf) {
    const chart = h('div', { class: 'chart' }), t = f.fcf.table, conv = t.data[t.index.indexOf('FCF / NI')];
    setTimeout(() => draw(chart, bars({ data: years.map((y, i) => ({ x: y, y: conv[i] })).filter((r) => r.y !== null), yFormat: '%', yTitle: 'FCF / NI' }), { height: 200 }), 0);
    out.push(sub('7. FCF conversion', 'Free cash flow ÷ net income. Above 100% every dollar of earnings becomes cash; below 70% sustained is a concern.',
      tbl(f.fcf, { 'Net Income': F.money, FCF: F.money, 'FCF / NI': F.ratio }), chart));
  }
  out.push(h('h2', { style: { marginTop: '14px' } }, 'Capital structure'));
  if (f.leverage) {
    const order = [['Debt / Equity', (v) => num(v, 2)], ['Debt / Assets', (v) => num(v, 2)], ['Net Debt / EBITDA', (v) => num(v, 2)],
      ['Interest Coverage', (v) => (v === null ? DASH : `${num(v, 1)}×`)], ['Current Ratio', (v) => num(v, 2)], ['Quick Ratio', (v) => num(v, 2)], ['Cash Ratio', (v) => num(v, 2)]];
    const cls = { good: 'pill-good', fair: 'pill-warn', poor: 'pill-bad' };
    out.push(sub('8. Leverage & liquidity (latest period)', 'How much debt is on the balance sheet, and how easily near-term obligations can be met.',
      h('div', { class: 'grid g2' }, order.map(([n, fm]) => h('div', { class: `tile ${cls[f.leverage.bands[n]] || ''}` },
        h('div', { class: 'label' }, n), h('div', { class: 'value mono' }, fm(f.leverage.metrics[n])), h('div', { class: 'note' }, (f.leverage.bands[n] || DASH).toUpperCase())))),
      h('p', { class: 'tiny muted' }, 'Bands are rough large-cap heuristics. Banks, utilities and REITs warrant sector-adjusted thresholds.')));
  }
  return out;
}

// --------------------------------------------------------------- technicals view
function technicalsView(t, c) {
  if (t.insufficient) return banner('warning', 'Not enough price history for reliable technical signals. Try a longer horizon.');
  const dirColor = { Bullish: ['success', '🟢'], Bearish: ['error', '🔴'], Neutral: ['warning', '🟡'] }[t.direction] || ['info', ''];
  const mk = (spec, height = 230) => { const d = h('div', { class: 'chart' }); setTimeout(() => draw(d, spec, { height }), 0); return d; };
  const s = t.series, dates = t.dates;
  const sigRows = t.signals.map(([name, direction, text]) => ({ name, direction, text }));
  return [
    banner(dirColor[0], h('div', { class: 'small muted' }, 'TECHNICAL READ'), h('div', { style: { fontSize: '1.4rem', fontWeight: 800 } }, `${dirColor[1]} ${t.direction} · strength ${num(t.strength, 0)}/100`)),
    table({ rows: sigRows, cols: [{ key: 'name', label: 'Signal', sort: false }, { key: 'direction', label: 'Direction', sort: false }, { key: 'text', label: 'Interpretation', wrap: true, sort: false }] }),
    section('Price with moving averages', `MA20 ${money(t.ma_values.ma20)} · MA50 ${money(t.ma_values.ma50)} · MA200 ${money(t.ma_values.ma200)}`,
      mk(line({ dates, yFormat: '$.2f', series: [{ name: 'Price', values: s.price, color: '#2c3e50', width: 1.8 }, { name: 'MA20', values: s.ma20, color: '#3498db', dash: [5, 3] },
        { name: 'MA50', values: s.ma50, color: '#e67e22', dash: [5, 3] }, { name: 'MA200', values: s.ma200, color: '#c0392b', dash: [5, 3] }] }), 280)),
    section('RSI (14)', 'Above 70 = overbought; below 30 = oversold.',
      mk(line({ dates, yFormat: '.0f', series: [{ name: 'RSI', values: s.rsi, color: '#8e44ad' }], rules: [{ y: 70, color: '#e74c3c' }, { y: 30, color: '#27ae60' }] }), 190)),
    section('MACD (12, 26, 9)', 'MACD above the signal line = bullish momentum; bars show the distance.',
      mk(macdSpec({ dates, macd: s.macd, signal: s.macd_signal, hist: s.macd_hist }), 210)),
    section('Bollinger Bands (20, 2σ)', t.bb_read ? `Current position: ${t.bb_read}.` : null,
      mk(line({ dates, yFormat: '$.2f', series: [{ name: 'Price', values: s.price, color: '#2c3e50' }, { name: 'Upper', values: s.bb_upper, color: '#e74c3c', dash: [4, 4] },
        { name: 'Middle', values: s.bb_middle, color: '#95a5a6', dash: [4, 4] }, { name: 'Lower', values: s.bb_lower, color: '#27ae60', dash: [4, 4] }] }), 250)),
    details('What do these indicators mean?', metricDescriptions(c.meta.technical_desc, (k) => k.toUpperCase().replace(/_/g, ' '))),
  ];
}

// --------------------------------------------------------------------- risk view
function riskView(r, c) {
  const m = r.metrics, d = c.meta.metric_desc || {};
  const T = (label, key, value, vt) => tile({ label, value, valueTone: vt, note: d[key] });
  const chartVol = h('div', { class: 'chart' }), chartHist = h('div', { class: 'chart' });
  setTimeout(() => {
    draw(chartVol, area({ dates: r.rolling_vol.x, values: r.rolling_vol.y, yFormat: '.2f', yTitle: 'Rolling std dev (%)' }), { height: 220 });
    draw(chartHist, histogram(r.histogram), { height: 250 });
  }, 0);
  return [
    h('div', { class: 'grid g2' },
      T('Trading days', 'trading_days', num(m.trading_days, 0)), T('Total return', 'total_return', pct(m.total_return, 2, true), tone(m.total_return)),
      T('Avg daily return', 'avg_daily', `${num(m.avg_daily, 4)}%`), T('Annualised vol', 'ann_vol', pct(m.ann_vol, 2)),
      T('Sharpe', 'sharpe', num(m.sharpe)), T('Sortino', 'sortino', num(m.sortino)),
      T('Max drawdown', 'max_drawdown', pct(m.max_drawdown, 2)), T('VaR (95%)', 'var_95', pct(m.var_95, 2)),
      T('Skewness', 'skewness', num(m.skewness)), T('Kurtosis', 'kurtosis', num(m.kurtosis)), T('Std (daily)', 'std_daily', `${num(m.std_daily, 4)}%`)),
    section(`Rolling ${r.rolling_window}-day volatility`, 'Spikes highlight regime changes — earnings surprises, macro shocks or market stress.', chartVol),
    section('Return distribution', 'If the bars extend further left than the orange normal curve, daily losses are fatter than theory predicts.', chartHist,
      h('p', { class: 'tiny muted' }, 'Orange dashed = normal distribution with the same mean and spread.')),
  ];
}

// -------------------------------------------------------------- price & events
async function eventsTab(panel, c) {
  let relative = false;
  const show = { earnings: true, dividend: true, outlier: true };
  const holder = h('div', { class: 'stack' });
  const toggles = h('div', { class: 'grid g2' },
    ...[['earnings', 'Earnings dates'], ['dividend', 'Dividends'], ['outlier', `Outlier days (|z| > ${c.P.outlier_z})`]].map(([k, label]) =>
      h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { show[k] = e.target.checked; redraw(); } }), h('span', null, label))),
    h('label', { class: 'check' }, h('input', { type: 'checkbox', onchange: (e) => { relative = e.target.checked; load(); } }), h('span', null, 'Relative to sector ETF')));
  panel.append(h('p', { class: 'sub' }, 'Why did it move? Overlay earnings dates, dividends and outlier days on the price chart.'), toggles, holder);

  let data = null;
  const chartBox = h('div', { class: 'chart' });
  function redraw() {
    if (!data) return;
    const ev = data.events.filter((e) => show[e.type]);
    draw(chartBox, priceEvents({ dates: data.price.x, values: data.price.y, label: data.label, events: ev, yFormat: data.relative ? '.3f' : ',.2f' }), { height: 330 });
  }
  async function load() {
    await into(holder, async () => {
      data = await api(c.url('events', { relative: relative ? 'true' : null }), { ttl: 60e3 });
      const parts = [];
      if (data.notice) parts.push(banner('info', data.notice));
      parts.push(chartBox);
      parts.push(h('div', { class: 'legend' }, h('span', null, '🔺 earnings'), h('span', null, '🟢 dividend'), h('span', null, '🔶 outlier day (green up / red down)')));
      if (data.next_earnings) {
        const d = new Date(`${data.next_earnings.date}T12:00:00`);
        parts.push(banner('info', b('Next earnings: '), `${d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} · ${data.next_earnings.days_until} days away.`));
      }
      parts.push(section('Top price-move days', 'The biggest one-day moves in the window — the moments most likely to have an explanation worth finding.',
        table({ rows: data.top_moves, cols: [{ key: 'date', label: 'Date', sort: false }, { key: 'price', label: 'Price', fmt: (v) => money(v), sort: false },
          { key: 'return_pct', label: 'Daily return', fmt: (v) => pct(v, 2, true), cls: tone, sort: false }] })));
      parts.push(seasonalityView(data.seasonality, c));
      setTimeout(redraw, 0);
      return parts;
    });
  }
  await load();
}

function seasonalityView(s, c) {
  const body = h('div', { class: 'stack' });
  const chart = h('div', { class: 'chart' });
  if (!s || !s.available) return details('Monthly seasonality (10y)', h('p', { class: 'muted' }, 'Not enough price history to compute seasonality (need at least 12 months).'));
  const vals = s.rows.flatMap((r) => r.months.map((m) => Math.abs(m.mean)).filter((v) => Number.isFinite(v))).sort((a, b2) => a - b2);
  const mag = Math.max(vals.length ? vals[Math.floor(vals.length * 0.95)] : 0.03, 0.01);
  const hl = s.headline;
  body.append(
    h('p', { class: 'small muted' }, 'Average calendar-month return for the ticker, its sector ETF and SPY. The last row isolates the ticker\'s excess seasonality over SPY. Treat ≤ 10 observations per month as suggestive, not predictive.'),
    chart,
    h('div', { class: 'grid g2' },
      tile({ label: 'Best month', value: hl.best_month, sub: signed(hl.best_mean * 100, 1, '% avg'), subTone: 'good' }),
      tile({ label: 'Worst month', value: hl.worst_month, sub: signed(hl.worst_mean * 100, 1, '% avg'), subTone: 'bad' }),
      tile({ label: 'Avg hit rate', value: pctR(hl.avg_hit_rate, 0), note: 'Share of months with a positive return.' }),
      tile({ label: 'Window', value: `${hl.years}y`, note: hl.start ? `${hl.start.slice(0, 7)} – ${hl.end.slice(0, 7)}` : null })),
    s.short_window ? banner('warning', `Only ~${hl.years} year(s) of data — too little to separate signal from noise.`) : null);
  return details('Monthly seasonality (10y)', body, { onOpen: () => draw(chart, heat({
    xs: s.months, ys: s.rows.map((r) => r.series), values: s.rows.map((r) => r.months.map((m) => m.mean)),
    domain: [-mag, 0, mag], range: ['#e74c3c', '#f5f5f5', '#2ecc71'], fmt: '+.1%', labelFlip: mag * 0.6, legendTitle: 'Avg return',
  }), { height: 56 + 34 * s.rows.length }) });
}
