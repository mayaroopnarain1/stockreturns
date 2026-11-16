// Screener: picklist filters run in the browser against the full S&P 500 table.
import { api, getMeta } from '../api.js';
import { addWatch, getPrefs, setPrefs } from '../store.js';
import { analysisUrl, navigate } from '../router.js';
import { h, tile, banner, b, section, into, table, details, select, field, toast, num, pct, pctR, money, DASH, loading, metricDescriptions } from '../ui.js';

const FIELDS = [
  ['Market cap & valuation', [['marketCap', 'Market cap tier'], ['trailingPE', 'Trailing P/E'], ['priceToBook', 'Price / Book'], ['enterpriseToEbitda', 'EV / EBITDA'], ['pegRatio', 'PEG ratio']]],
  ['Quality', [['returnOnEquity', 'Return on equity'], ['profitMargins', 'Profit margin'], ['debtToEquity', 'Debt / equity']]],
  ['Growth & income', [['revenueGrowth', 'Revenue growth'], ['dividendYield', 'Dividend yield']]],
];
const PAGE = 100;

export function applyFilters(rows, presets, chosen, sectors) {
  return rows.filter((r) => {
    for (const [key, label] of Object.entries(chosen)) {
      const opt = (presets[key] || []).find((o) => o.label === label);
      if (!opt || (opt.min === null && opt.max === null)) continue;
      const v = r[key];
      if (v === null || v === undefined || !Number.isFinite(v)) return false;     // missing data fails an active bound
      if (opt.min !== null && v < opt.min) return false;
      if (opt.max !== null && v > opt.max) return false;
    }
    return !(sectors.length && !sectors.includes(r.sector));
  });
}

export async function render({ el, alive }) {
  const meta = await getMeta();
  el.append(h('div', { class: 'page-head' }, h('h1', null, 'Stock Screener')),
    h('p', { class: 'sub' }, 'Screen the S&P 500 with labeled ranges. Filters apply instantly once the data is loaded.'));
  const box = h('div', { class: 'stack' });
  el.append(box);

  async function load() {
    box.replaceChildren(loading('Loading screener…'));
    let snap = await api('/screener');
    while (alive() && snap.status === 'building') {
      const pctDone = snap.total ? (snap.done / snap.total) * 100 : 0;
      box.replaceChildren(banner('info', b('Building the S&P 500 universe… '), `${snap.done}/${snap.total} companies.`,
        h('div', { class: 'bar', style: { marginTop: '8px' } }, h('i', { style: { width: `${pctDone}%` } })),
        h('p', { class: 'small muted', style: { margin: '8px 0 0' } }, 'The first build takes a few minutes; afterwards results are cached for 12 hours. You can leave this page — it keeps building.')));
      await new Promise((r) => setTimeout(r, 2500));
      if (!alive()) return;
      snap = await api('/screener/status');
      if (snap.status === 'ready') snap = await api('/screener');
    }
    if (!alive()) return;
    if (snap.status === 'error') {
      box.replaceChildren(banner('error', snap.error || 'Could not fetch fundamentals.'), h('button', { class: 'btn', onclick: load }, 'Try again'));
      return;
    }
    box.replaceChildren(...view(snap, meta));
  }
  try { await load(); } catch (e) { box.replaceChildren(banner('error', e.message), h('button', { class: 'btn', onclick: load }, 'Try again')); }
}

function view(snap, meta) {
  const presets = meta.filter_presets;
  const prefs = getPrefs('screener');
  const chosen = { ...prefs.filters };
  let sectors = [...(prefs.sectors || [])];
  let limit = PAGE;
  const results = h('div', { class: 'stack' });

  const selects = {};
  const filterGrid = FIELDS.map(([group, items]) => h('div', null, h('h4', { style: { margin: '8px 0 6px' } }, group),
    h('div', { class: 'grid g2' }, items.map(([key, label]) => {
      const s = select(presets[key].map((o) => o.label), chosen[key] || 'Any', (v) => { chosen[key] = v; limit = PAGE; save(); draw(); },
        { 'aria-label': label });
      selects[key] = s;
      return field(label, s);
    }))));

  const sectorBox = h('div', { class: 'chips' });
  function drawSectors() {
    sectorBox.replaceChildren(...snap.sectors.map((s) => h('button', { type: 'button', class: `chip ${sectors.includes(s) ? 'pill-good' : ''}`,
      onclick: () => { sectors = sectors.includes(s) ? sectors.filter((x) => x !== s) : [...sectors, s]; limit = PAGE; save(); drawSectors(); draw(); } }, s)));
  }
  const save = () => setPrefs('screener', { filters: chosen, sectors });

  function reset() {
    Object.keys(chosen).forEach((k) => delete chosen[k]);
    Object.values(selects).forEach((s) => { s.value = 'Any'; });
    sectors = []; limit = PAGE; save(); drawSectors(); draw();
  }

  const nActive = () => Object.values(chosen).filter((v) => v && v !== 'Any').length + (sectors.length ? 1 : 0);

  function draw() {
    const rows = applyFilters(snap.rows, presets, chosen, sectors).sort((a, b2) => (b2.marketCap ?? -1) - (a.marketCap ?? -1));
    const parts = [h('div', { class: 'grid g3' },
      tile({ label: 'Universe', value: String(snap.rows.length) }), tile({ label: 'Pass filters', value: String(rows.length) }),
      tile({ label: 'Active filters', value: String(nActive()) }))];
    if (!rows.length) {
      parts.push(banner('warning', 'No stocks match the current filters. Loosen the criteria or tap ', b('Reset filters'), '.'));
      results.replaceChildren(...parts);
      return;
    }
    const shown = rows.slice(0, limit);
    parts.push(h('h2', null, `Results — ${rows.length} of ${snap.rows.length}`),
      table({
        rows: shown, sortKey: 'marketCap', onRow: (r) => navigate(`/analysis/${encodeURIComponent(r.ticker)}`),
        cols: [
          { key: 'ticker', label: 'Ticker' },
          { key: 'shortName', label: 'Company' },
          { key: 'sector', label: 'Sector' },
          { key: 'marketCapB', label: 'Mkt cap ($B)', fmt: (v) => num(v, 1) },
          { key: 'currentPrice', label: 'Price', fmt: (v) => money(v) },
          { key: 'trailingPE', label: 'P/E', fmt: (v) => num(v, 1) },
          { key: 'forwardPE', label: 'Fwd P/E', fmt: (v) => num(v, 1) },
          { key: 'priceToBook', label: 'P/B', fmt: (v) => num(v, 1) },
          { key: 'enterpriseToEbitda', label: 'EV/EBITDA', fmt: (v) => num(v, 1) },
          { key: 'pegRatio', label: 'PEG', fmt: (v) => num(v, 2) },
          { key: 'dividendYieldPct', label: 'Div yld %', fmt: (v) => num(v, 2) },
          { key: 'returnOnEquity', label: 'ROE', fmt: (v) => pctR(v, 1) },
          { key: 'profitMargins', label: 'Margin', fmt: (v) => pctR(v, 1) },
          { key: 'revenueGrowth', label: 'Rev growth', fmt: (v) => pctR(v, 1) },
          { key: 'debtToEquity', label: 'D/E', fmt: (v) => num(v, 0) },
          { key: 'beta', label: 'Beta', fmt: (v) => num(v, 2) },
          { key: 'pct_below_52w_high', label: '% below 52w hi', fmt: (v) => num(v, 1) },
        ],
      }));
    if (rows.length > limit) parts.push(h('button', { class: 'btn block', onclick: () => { limit += PAGE; draw(); } }, `Show more (${rows.length - limit} left)`));
    const topN = Math.min(10, rows.length);
    const n = h('input', { type: 'number', min: '1', max: String(topN), value: Math.min(5, topN), 'aria-label': 'How many' });
    parts.push(section('Quick actions', 'Adds the largest companies in the current results to your watchlist.',
      h('div', { class: 'row' }, h('div', { style: { width: '90px' } }, n),
        h('button', { class: 'btn primary', onclick: () => {
          const k = Math.max(1, Math.min(topN, Number(n.value) || 1));
          const added = [], skipped = [];
          rows.slice(0, k).forEach((r) => (addWatch(r.ticker) ? added : skipped).push(r.ticker));
          toast(added.length ? `Added: ${added.join(', ')}${skipped.length ? ` (already had ${skipped.length})` : ''}` : 'Already on your watchlist');
        } }, 'Add top N by market cap'),
        h('a', { class: 'btn', href: '#/watchlist' }, 'Open Watchlist'))));
    parts.push(details('What do these metrics mean?', metricDescriptions(meta.fundamental_desc)));
    results.replaceChildren(...parts);
  }

  const updated = snap.updated ? new Date(snap.updated * 1000).toLocaleString() : null;
  drawSectors(); draw();
  return [
    details(`Filters${nActive() ? ` (${nActive()} active)` : ''}`, h('div', { class: 'stack' }, ...filterGrid,
      h('div', null, h('h4', { style: { margin: '8px 0 6px' } }, 'Sector'), sectorBox,
        h('p', { class: 'tiny muted' }, 'Tap sectors to include them; none selected = all.')),
      h('button', { class: 'btn block', onclick: reset }, 'Reset filters')), { open: nActive() === 0 }),
    results,
    h('div', { class: 'row between' }, h('span', { class: 'tiny muted' }, updated ? `Data built ${updated}` : ''),
      h('button', { class: 'btn small', onclick: async () => {
        const r = await api('/screener/refresh', { method: 'POST' }).catch((e) => ({ error: e.message }));
        toast(r.error || (r.started ? 'Refreshing in the background…' : 'Data is already fresh (refresh allowed once an hour).'));
      } }, 'Refresh data')),
  ];
}
