// Portfolio risk: holdings editor + results (overview, risk contributions, sectors, holdings).
import { api, getMeta } from '../api.js';
import { getPortfolio, savePortfolio, getPrefs, setPrefs, watchTickers } from '../store.js';
import { draw, line, bars, heat } from '../charts.js';
import { h, tile, banner, b, section, into, tabs, table, details, select, field, toast, num, pct, signed, tone, DASH, metricDescriptions } from '../ui.js';

const HORIZONS = [['3mo', '3 Months'], ['6mo', '6 Months'], ['1y', '1 Year'], ['2y', '2 Years'], ['5y', '5 Years']];
const MAX = 15;
const DEFAULT = { tickers: ['AAPL', 'MSFT', 'GOOGL'], weights: [40, 35, 25] };

export const equalWeights = (n) => {
  const w = Array(n).fill(Math.round(1000 / n) / 10);
  w[n - 1] = Math.round((100 - w.slice(0, -1).reduce((a, x) => a + x, 0)) * 10) / 10;
  return w;
};
export const weightsValid = (w) => Math.abs(w.reduce((a, x) => a + (Number(x) || 0), 0) - 100) <= 0.5;

export async function render({ el }) {
  const meta = await getMeta().catch(() => ({ metric_desc: {} }));
  const prefs = getPrefs('portfolio');
  const st = getPortfolio();
  const out = h('div', { class: 'stack' });
  const list = h('div', { class: 'stack' });
  const status = h('div');
  const run = h('button', { class: 'btn primary block', onclick: () => analyze() }, 'Analyze portfolio');
  const hor = select(HORIZONS.map(([v, l]) => ({ value: v, label: l })), prefs.horizon);
  const rf = h('input', { type: 'number', step: '0.01', min: '0', max: '0.2', value: prefs.rf });

  function persist() { savePortfolio({ tickers: st.tickers, weights: st.weights }); }
  function total() { return st.weights.reduce((a, x) => a + (Number(x) || 0), 0); }
  function refreshStatus() {
    const t = total(), ok = weightsValid(st.weights) && st.tickers.filter(Boolean).length >= 2;
    status.replaceChildren(h('p', { class: `small ${Math.abs(t - 100) <= 0.5 ? 'good' : 'warn'}` }, `Total weight: ${num(t, 1)}%`,
      Math.abs(t - 100) > 0.5 ? ' — weights must sum to 100% (±0.5).' : ''));
    run.disabled = !ok;
  }
  function drawList() {
    list.replaceChildren(...st.tickers.map((t, i) => h('div', { class: 'row', style: { flexWrap: 'nowrap' } },
      h('div', { class: 'grow' }, h('input', { type: 'text', value: t, autocapitalize: 'characters', 'aria-label': `Ticker ${i + 1}`, placeholder: 'Ticker',
        onchange: (e) => { st.tickers[i] = e.target.value.trim().toUpperCase(); e.target.value = st.tickers[i]; persist(); refreshStatus(); } })),
      h('div', { style: { width: '96px' } }, h('input', { type: 'number', min: '0', max: '100', step: '1', value: st.weights[i], 'aria-label': `Weight ${i + 1} (%)`,
        oninput: (e) => { st.weights[i] = Number(e.target.value) || 0; persist(); refreshStatus(); } })),
      h('button', { class: 'btn small danger', 'aria-label': `Remove ${t}`, onclick: () => { if (st.tickers.length <= 2) return toast('Keep at least 2 holdings.'); st.tickers.splice(i, 1); st.weights.splice(i, 1); persist(); drawList(); refreshStatus(); } }, '✕'))));
    refreshStatus();
  }
  const setAll = (tickers, weights) => { st.tickers = tickers; st.weights = weights; persist(); drawList(); };

  el.append(h('div', { class: 'page-head' }, h('h1', null, 'Portfolio Risk')),
    h('p', { class: 'sub' }, 'Enter holdings and weights to see portfolio risk, return and diversification.'),
    h('div', { class: 'card stack' },
      h('div', { class: 'row' },
        h('button', { class: 'btn small', onclick: () => { const w = watchTickers().slice(0, 10); if (w.length < 2) return toast('Add at least 2 names to your watchlist first.'); setAll(w, equalWeights(w.length)); } }, 'Load from watchlist'),
        h('button', { class: 'btn small', onclick: () => setAll([...st.tickers], equalWeights(st.tickers.length)) }, 'Equal weight'),
        h('button', { class: 'btn small', onclick: () => setAll([...DEFAULT.tickers], [...DEFAULT.weights]) }, 'Reset')),
      list, status,
      h('button', { class: 'btn small', onclick: () => { if (st.tickers.length >= MAX) return toast(`At most ${MAX} holdings.`); st.tickers.push(''); st.weights.push(0); persist(); drawList(); } }, '＋ Add holding'),
      h('div', { class: 'grid g2' }, field('Time horizon', hor), field('Risk-free rate', rf)),
      run), out);
  drawList();

  async function analyze() {
    const tickers = st.tickers.map((t) => t.trim().toUpperCase()), weights = st.weights.map((w) => Number(w) || 0);
    if (tickers.some((t) => !t)) return toast('Fill in or remove empty holdings.');
    setPrefs('portfolio', { horizon: hor.value, rf: Number(rf.value) });
    await into(out, async () => view(await api('/portfolio', { method: 'POST', body: { tickers, weights, horizon: hor.value, rf: Number(rf.value) } }), meta), 'Crunching numbers…');
  }
  if (weightsValid(st.weights) && st.tickers.every(Boolean)) analyze();
}

function view(d, meta) {
  const s = d.summary, desc = meta.metric_desc || {};
  const chart = (spec, height) => { const c = h('div', { class: 'chart' }); setTimeout(() => draw(c, spec, { height }), 0); return c; };
  const bannerFor = { well: ['success', 'Well-diversified', `diversification removes ~${num(s.diversification_ratio * 100, 0)}% of the naive weighted volatility.`],
    moderate: ['info', 'Moderately diversified', `${num(s.diversification_ratio * 100, 0)}% volatility reduction vs a perfectly correlated baseline. Consider less-correlated sectors.`],
    concentrated: ['warning', 'Concentrated', `only ${num(s.diversification_ratio * 100, 0)}% volatility reduction; holdings move too similarly. Mix in other sectors or a defensive ETF.`] }[s.diversification_level];

  return tabs([
    { id: 'overview', label: 'Overview', load: (p) => {
      p.append(h('div', { class: 'stack' },
        h('div', { class: 'grid g2' },
          tile({ label: 'Portfolio return', value: pct(s.total_return, 2), valueTone: tone(s.total_return), note: desc.total_return }),
          tile({ label: 'Annualized vol', value: pct(s.ann_vol, 2), note: desc.ann_vol }),
          tile({ label: 'Sharpe', value: num(s.sharpe), note: desc.sharpe }),
          tile({ label: 'Max drawdown', value: pct(s.max_drawdown, 2), note: desc.max_drawdown }),
          tile({ label: 'Undiversified vol', value: pct(s.undiversified_vol, 2), note: 'Weighted sum of individual vols — what you\'d get at perfect correlation.' }),
          tile({ label: 'Diversification benefit', value: pct(s.diversification_benefit, 2), note: `≈ ${num(s.diversification_ratio * 100, 0)}% of the undiversified vol is saved.` }),
          tile({ label: 'Sortino', value: num(s.sortino), note: desc.sortino }),
          tile({ label: 'VaR (95%)', value: pct(s.var_95, 2), note: desc.var_95 })),
        banner(bannerFor[0], b(`${bannerFor[1]} — `), bannerFor[2]),
        d.benchmark ? section('vs. SPY benchmark', null, h('div', { class: 'grid g2' },
          tile({ label: 'Excess return', value: `${signed(d.benchmark.excess_return, 2)} pp`, valueTone: tone(d.benchmark.excess_return), note: 'Portfolio total return minus SPY over the same horizon.' }),
          tile({ label: 'Beta', value: num(d.benchmark.beta), note: '1.0 = moves with the market; >1 = more volatile.' }),
          tile({ label: 'Alpha (annualized)', value: d.benchmark.alpha_annualized === null ? DASH : `${signed(d.benchmark.alpha_annualized, 2)}%`, note: 'Return above what CAPM predicts given your beta.' }),
          tile({ label: 'Correlation to SPY', value: num(d.benchmark.correlation) }))) : null,
        section('Cumulative performance', 'Solid = portfolio, dashed = holdings, dotted = SPY. All series start from the same date.',
          chart(line({ dates: d.cumulative.dates, yTitle: 'Cumulative return',
            series: [{ name: 'Portfolio', values: d.cumulative.portfolio, width: 3.2, color: '#2563eb' },
              ...Object.entries(d.cumulative.holdings).map(([t, v]) => ({ name: t, values: v, dash: [6, 3], width: 1.4 })),
              ...(d.cumulative.spy ? [{ name: 'SPY', values: d.cumulative.spy, dash: [2, 2], width: 1.8, color: '#64748b' }] : [])] }), 340))));
    } },
    { id: 'risk', label: 'Risk contributions', load: (p) => {
      p.append(h('div', { class: 'stack' },
        h('p', { class: 'sub' }, 'How much of portfolio volatility each stock drives. A stock can contribute more risk than its weight if it is volatile or highly correlated with the rest.'),
        table({ rows: d.contributions, cols: [{ key: 'ticker', label: 'Ticker', sort: false }, { key: 'weight', label: 'Weight (%)', fmt: (v) => num(v, 2), sort: false },
          { key: 'ann_vol', label: 'Ann. vol (%)', fmt: (v) => num(v, 2), sort: false }, { key: 'risk_contribution', label: 'Risk contrib. (%)', fmt: (v) => num(v, 2), sort: false }] }),
        chart(bars({ data: d.contributions.flatMap((c) => [{ x: c.ticker, y: c.weight, c: 'Weight (%)' }, { x: c.ticker, y: c.risk_contribution, c: 'Risk contribution (%)' }]), color: true, yFormat: '.1f' }), 260),
        section('Alternative weight schemes', 'Equal-weight spreads risk by position count; inverse-vol gives each name a similar standalone risk.',
          table({ rows: d.alternatives, cols: [{ key: 'ticker', label: 'Ticker', sort: false }, { key: 'current', label: 'Current (%)', fmt: (v) => num(v, 1), sort: false },
            { key: 'equal', label: 'Equal (%)', fmt: (v) => num(v, 1), sort: false }, { key: 'inverse_vol', label: 'Inverse-vol (%)', fmt: (v) => num(v, 1), sort: false }] })),
        section('Correlation matrix', null, chart(heat({ xs: d.correlation.tickers, ys: d.correlation.tickers, values: d.correlation.matrix, fmt: '.2f' }), Math.max(220, 46 * d.correlation.tickers.length)))));
    } },
    { id: 'sectors', label: 'Sector allocation', load: (p) => {
      const rows = d.sectors.rows, c = d.sectors.concentration;
      const msg = { high: ['warning', ` alone is ${num(c.weight, 1)}% of the portfolio — highly concentrated; a sector shock will dominate returns.`],
        medium: ['info', ` is your largest sector at ${num(c.weight, 1)}% — meaningful concentration worth monitoring.`],
        low: ['success', ` — no single sector dominates; the largest is at ${num(c.weight, 1)}%.`] }[c.level];
      p.append(h('div', { class: 'stack' },
        chart(bars({ data: rows.map((r) => ({ x: r.sector, y: r.weight })), horizontal: true, yFormat: '.1f', sort: '-x', yTitle: 'Weight (%)' }), Math.max(160, 40 * rows.length)),
        table({ rows, cols: [{ key: 'sector', label: 'Sector', sort: false }, { key: 'weight', label: 'Weight (%)', fmt: (v) => num(v, 1), sort: false }] }),
        banner(msg[0], b(c.sector), msg[1])));
    } },
    { id: 'holdings', label: 'Holdings', load: (p) => {
      p.append(h('div', { class: 'stack' },
        table({ rows: d.holdings, cols: [{ key: 'ticker', label: 'Ticker', sort: false }, { key: 'weight', label: 'Weight (%)', fmt: (v) => num(v, 1) },
          { key: 'total_return', label: 'Return (%)', fmt: (v) => num(v, 2), cls: tone }, { key: 'ann_vol', label: 'Vol (%)', fmt: (v) => num(v, 2) },
          { key: 'sharpe', label: 'Sharpe', fmt: (v) => num(v, 2) }, { key: 'sortino', label: 'Sortino', fmt: (v) => num(v, 2) },
          { key: 'max_drawdown', label: 'Max DD (%)', fmt: (v) => num(v, 2) }, { key: 'var_95', label: 'VaR 95 (%)', fmt: (v) => num(v, 2) }] }),
        details('What do these metrics mean?', metricDescriptions(meta.metric_desc))));
    } },
  ], { active: 'overview' });
}
