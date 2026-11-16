// Compare 2–5 tickers side by side: verdicts, performance, risk, fundamentals, correlation.
import { api, getMeta } from '../api.js';
import { addWatch, getPrefs, setPrefs } from '../store.js';
import { analysisUrl } from '../router.js';
import { draw, line, heat, scatter } from '../charts.js';
import { h, tile, banner, b, section, into, tabs, table, details, select, field, toast, num, pct, tone, DASH, metricDescriptions } from '../ui.js';

const HORIZONS = [['1mo', '1 Month'], ['3mo', '3 Months'], ['6mo', '6 Months'], ['1y', '1 Year'], ['2y', '2 Years'], ['5y', '5 Years']];
const VERDICT = { Buy: ['#16a34a', 'rgba(22,163,74,.12)'], Hold: ['#d97706', 'rgba(217,119,6,.13)'], Avoid: ['#dc2626', 'rgba(220,38,38,.10)'] };

export function parseTickers(text) {
  const out = [];
  for (const t of String(text).split(/[\s,;]+/)) {
    const v = t.trim().toUpperCase();
    if (v && !out.includes(v)) out.push(v);
  }
  return out;
}

export async function render({ el, query }) {
  const meta = await getMeta().catch(() => ({ metric_desc: {}, fundamental_desc: {} }));
  const prefs = getPrefs('compare');
  const fromUrl = query.get('tickers');
  const st = { ...prefs, tickers: fromUrl || prefs.tickers };

  const tickers = h('input', { type: 'text', value: st.tickers, autocapitalize: 'characters', 'aria-label': 'Tickers', placeholder: 'AAPL, MSFT, GOOGL',
    onkeydown: (e) => { if (e.key === 'Enter') run(); } });
  const out = h('div', { class: 'stack' });
  const bench = h('input', { type: 'checkbox', checked: !!st.benchmark });
  const rf = h('input', { type: 'number', step: '0.01', min: '0', max: '0.2', value: st.rf });
  const hor = select(HORIZONS.map(([v, l]) => ({ value: v, label: l })), st.horizon);
  const prof = select(['Balanced', 'Value', 'Growth', 'Income'], st.profile);

  el.append(h('div', { class: 'page-head' }, h('h1', null, 'Compare Stocks')),
    h('p', { class: 'sub' }, 'Pick 2–5 tickers. SPY is overlaid as a benchmark.'),
    h('div', { class: 'card stack' },
      field('Tickers (comma-separated, max 5)', tickers),
      h('div', { class: 'grid g2' }, field('Time horizon', hor), field('Investor profile', prof), field('Risk-free rate', rf),
        h('label', { class: 'check', style: { alignSelf: 'end' } }, bench, h('span', null, 'Include SPY benchmark'))),
      h('button', { class: 'btn primary block', onclick: () => run() }, 'Compare')), out);

  async function run() {
    const list = parseTickers(tickers.value).slice(0, 5);
    if (list.length < 2) { out.replaceChildren(banner('warning', 'Enter at least 2 tickers.')); return; }
    const body = { tickers: list, horizon: hor.value, rf: Number(rf.value), benchmark: bench.checked, profile: prof.value };
    setPrefs('compare', { ...body, tickers: list.join(', ') });
    tickers.value = list.join(', ');
    await into(out, async () => view(await api('/compare', { method: 'POST', body }), meta), 'Comparing…');
  }
  run();
}

function view(d, meta) {
  const parts = [];
  if (d.errors.length) parts.push(banner('warning', `Could not fetch data for: ${d.errors.join(', ')}`));
  parts.push(h('h2', null, 'Verdicts (quick read)'));
  parts.push(h('div', { class: 'grid g2' }, d.tickers.map((t) => {
    const v = d.verdicts[t], [border, bg] = VERDICT[v.verdict] || VERDICT.Hold;
    return h('a', { href: analysisUrl(t), style: { border: `2px solid ${border}`, background: bg, borderRadius: '12px', padding: '12px', color: 'inherit', display: 'block' } },
      h('div', { style: { fontWeight: 800, fontSize: '1.1rem' } }, t),
      h('div', { style: { fontWeight: 800, color: border } }, v.verdict),
      h('div', { class: 'small muted' }, `Score: ${num(v.composite_score, 0)} / 100`),
      h('div', { class: 'tiny muted', style: { marginTop: '6px', lineHeight: 1.3 } }, v.thesis));
  })));
  parts.push(h('p', { class: 'tiny muted' }, `Verdicts use the ${d.profile} profile.`));

  const chart = (spec, height) => { const c = h('div', { class: 'chart' }); setTimeout(() => draw(c, spec, { height }), 0); return c; };
  parts.push(tabs([
    { id: 'perf', label: 'Performance', load: (p) => {
      const names = Object.keys(d.performance.series);
      p.append(h('p', { class: 'sub' }, 'Cumulative performance regardless of share price — 1.2 means up 20% from the start. SPY is dashed.'),
        chart(line({ dates: d.performance.dates, yTitle: 'Normalized price', series: names.map((n) => ({ name: n, values: d.performance.series[n], dash: n === 'SPY' ? [6, 3] : [1, 0], color: n === 'SPY' ? '#64748b' : undefined })) }), 300),
        section('Total return', null, h('div', { class: 'grid g2' }, d.performance.total_return.map((r) => tile({
          label: r.ticker, value: pct(r.value, 2), valueTone: tone(r.value),
          sub: r.ticker === 'SPY' ? 'Benchmark' : (r.vs_spy === null ? null : `vs SPY: ${num(r.vs_spy, 2)}pp`), subTone: r.vs_spy === null ? '' : tone(r.vs_spy) })))));
    } },
    { id: 'risk', label: 'Risk metrics', load: (p) => {
      const rows = d.risk.labels.map((label) => ({ label, ...Object.fromEntries(d.risk.tickers.map((t) => [t, d.risk.rows[t][label]])) }));
      p.append(h('p', { class: 'sub' }, 'Risk & return comparison'),
        table({ rows, cols: [{ key: 'label', label: 'Metric', sort: false }, ...d.risk.tickers.map((t) => ({ key: t, label: t, sort: false, fmt: (v) => num(v, 2) }))] }),
        section('Risk vs. return', 'The ideal position is upper-left: high return, low volatility.',
          chart(scatter({ points: d.risk.scatter.map((s) => ({ ticker: s.ticker, x: s.ann_vol, y: s.total_return })), xTitle: 'Annualized volatility (%)', yTitle: 'Total return (%)' }), 280)),
        details('What do these metrics mean?', metricDescriptions(meta.metric_desc)));
    } },
    { id: 'fund', label: 'Fundamentals', load: (p) => {
      const rows = d.fundamentals;
      p.append(h('p', { class: 'sub' }, 'Best value in each row is highlighted green.'),
        table({ rows, bestCell: (c, r) => c.key !== 'label' && r.values[c.key] && r.values[c.key].best,
          cols: [{ key: 'label', label: 'Metric', sort: false }, ...d.tickers.map((t) => ({ key: t, label: t, sort: false, get: (r) => r.values[t].display }))] }),
        details('What do these metrics mean?', metricDescriptions(meta.fundamental_desc)));
    } },
    { id: 'corr', label: 'Correlation', load: (p) => {
      const c = d.correlation;
      p.append(h('p', { class: 'sub' }, 'How closely the stocks move together: near 1 = in sync, near 0 = independent, negative = opposite.'),
        chart(heat({ xs: c.tickers, ys: c.tickers, values: c.matrix, fmt: '.2f' }), Math.max(220, 46 * c.tickers.length)));
      if (c.avg_pairwise !== null) {
        const kind = { warning: 'warning', info: 'info', success: 'success' }[c.level];
        const text = { warning: 'these stocks move very similarly. Diversification benefit is limited.', info: 'moderately correlated. Some diversification benefit.', success: 'a well-diversified cohort.' }[c.level];
        p.append(banner(kind, 'Average pairwise correlation is ', b(num(c.avg_pairwise, 2)), ` — ${text}`));
      }
    } },
  ], { active: 'perf' }));

  parts.push(section('Next steps', null, h('div', { class: 'row' },
    h('button', { class: 'btn', onclick: () => { const added = d.tickers.filter((t) => addWatch(t)); toast(added.length ? `Added: ${added.join(', ')}` : 'All already on your watchlist'); } }, '＋ Add all to watchlist'),
    h('a', { class: 'btn', href: '#/portfolio' }, 'Build a portfolio'),
    h('a', { class: 'btn', href: analysisUrl(d.tickers[0]) }, 'Drill into a name'))));
  return parts;
}
