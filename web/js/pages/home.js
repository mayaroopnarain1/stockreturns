// Market Pulse: macro tiles, sector heat map, watchlist snapshot, movers, navigation.
import { api } from '../api.js';
import { getWatchlist } from '../store.js';
import { analysisUrl } from '../router.js';
import { h, tile, banner, b, section, into, num, money, pct, signed, tone, DASH, table } from '../ui.js';

// Same colour ramp as the Streamlit tiles: pale -> strong, saturating at +/-3%.
function tileColors(p) {
  if (p === null || p === undefined) return { bg: 'var(--card-2)', fg: 'var(--muted)' };
  const c = Math.max(-3, Math.min(3, p));
  const k = Math.min(1, Math.abs(c) / 3);
  const [r, g, bl] = c >= 0
    ? [230 - (230 - 22) * k, 244 - (244 - 163) * k, 234 - (234 - 74) * k]
    : [253 - (253 - 220) * k, 226 - (226 - 38) * k, 226 - (226 - 38) * k];
  return { bg: `rgb(${Math.round(r)},${Math.round(g)},${Math.round(bl)})`, fg: Math.abs(p) < 1.5 ? '#111827' : '#ffffff' };
}

export function targetStatus(price, target) {
  if (price === null || price === undefined) return { vs: null, status: 'no_data' };
  if (!target || target <= 0) return { vs: null, status: 'none' };
  const vs = (price - target) / target * 100;
  return { vs, status: price >= target ? 'hit' : vs >= -5 ? 'near' : 'below' };
}
export const STATUS_LABEL = { hit: 'Target hit', near: 'Near target', below: 'Below target', none: DASH, no_data: 'No data' };

export async function render({ el, alive }) {
  el.append(h('div', { class: 'page-head' }, h('h1', null, 'Market Pulse')));
  const body = h('div', { class: 'stack' });
  el.append(body);
  await into(body, async () => {
    const wl = getWatchlist();
    const [home, quotes] = await Promise.all([
      api('/home'),
      wl.length ? api('/quotes', { method: 'POST', body: { tickers: wl.map((i) => i.ticker) } }) : Promise.resolve({ quotes: [] }),
    ]);
    if (!alive()) return null;
    return build(home, quotes.quotes, wl);
  }, 'Loading market data…');
}

function build(home, quotes, wl) {
  const out = [];
  const d = new Date(`${home.date}T12:00:00`);
  out.push(h('p', { class: 'sub' }, `${home.weekday}, ${d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}`,
    home.is_weekend ? ' · Markets closed (weekend)' : ' · Live quotes from Yahoo Finance'));

  // macro strip
  const m = Object.fromEntries(home.macro.map((x) => [x.symbol, x]));
  const spy = m.SPY, vix = m['^VIX'], tnx = m['^TNX'];
  out.push(h('div', { class: 'grid g4' },
    tile({ label: spy.label, value: money(spy.current), sub: signed(spy.change_pct, 2, '%'), subTone: tone(spy.change_pct) }),
    tile({ label: vix.label, value: num(vix.current), sub: signed(vix.change_pct, 2, '%'), subTone: tone(-vix.change_pct) }),
    tile({ label: tnx.label, value: tnx.current === null ? DASH : `${num(tnx.current)}%`, sub: signed(tnx.change_pct, 2, '%'), subTone: tone(tnx.change_pct) }),
    h('div', { class: 'tile' }, h('div', { class: 'label' }, 'Regime'),
      h('div', { class: 'value', style: { color: home.regime.tone } }, home.regime.label),
      h('div', { class: 'note' }, 'From the VIX level'))));

  // sectors
  const tiles = home.sectors.tiles.map((t) => {
    const c = tileColors(t.change_pct);
    return h('a', { class: 'sector', href: analysisUrl(t.etf), style: { background: c.bg, color: c.fg } },
      h('div', { class: 'e' }, t.etf), h('div', { class: 'n' }, t.sector),
      h('div', { class: 'p mono' }, t.change_pct === null ? DASH : pct(t.change_pct, 2, true)),
      h('div', { class: 'n mono' }, t.price === null ? '' : money(t.price)));
  });
  const row = (r) => h('p', { class: 'small' }, h('b', null, `${r.sector} (${r.etf})`), ' · ',
    h('b', { class: tone(r.change_pct) }, pct(r.change_pct, 2, true)), ` · ${money(r.price)}`);
  out.push(section('Sector heat map', '1-day move in each SPDR sector ETF. Tap a tile to analyze it.',
    h('div', { class: 'grid g3' }, tiles),
    h('div', { class: 'grid g2', style: { marginTop: '10px' } },
      h('div', { class: 'card flat' }, h('h4', null, '▲ Leading'), home.sectors.leaders.map(row)),
      h('div', { class: 'card flat' }, h('h4', null, '▼ Lagging'), home.sectors.laggards.map(row)))));

  // watchlist
  if (!wl.length) {
    out.push(section('Your watchlist', null, banner('info', 'You\'re not tracking anything yet. Research a name in ', h('a', { href: '#/analysis' }, 'Analyze'), ' and add it, or open ', h('a', { href: '#/watchlist' }, 'Watch'), '.')));
  } else {
    const q = Object.fromEntries(quotes.map((x) => [x.ticker, x]));
    const rows = wl.map((i) => {
      const x = q[i.ticker]; const price = x ? x.price : null;
      const { vs, status } = targetStatus(price, i.target_price);
      return { ticker: i.ticker, price, change: x ? x.change_pct : null, target: i.target_price, vs, status };
    });
    const hit = rows.filter((r) => r.status === 'hit').map((r) => r.ticker);
    const near = rows.filter((r) => r.status === 'near').map((r) => r.ticker);
    out.push(section('Your watchlist', null,
      table({ rows, sortKey: null, onRow: (r) => { location.hash = analysisUrl(r.ticker); }, cols: [
        { key: 'ticker', label: 'Ticker', sort: false },
        { key: 'price', label: 'Price', fmt: (v) => money(v), sort: false },
        { key: 'change', label: 'Change', fmt: (v) => pct(v, 2, true), cls: (v) => tone(v), sort: false },
        { key: 'target', label: 'Target', fmt: (v) => (v ? money(v) : DASH), sort: false },
        { key: 'vs', label: 'vs Target', fmt: (v) => pct(v, 1, true), sort: false },
        { key: 'status', label: 'Status', fmt: (v) => STATUS_LABEL[v], sort: false },
      ] }),
      hit.length ? h('div', { style: { marginTop: '8px' } }, banner('success', b('Price target hit: '), hit.join(', '))) : null,
      !hit.length && near.length ? h('div', { style: { marginTop: '8px' } }, banner('warning', b('Approaching target: '), near.join(', '))) : null));
  }

  // movers
  const mv = (r) => h('a', { href: analysisUrl(r.ticker), style: { display: 'block', color: 'inherit', padding: '5px 0' } },
    h('div', { class: 'row between', style: { flexWrap: 'nowrap' } }, h('b', null, r.ticker),
      h('b', { class: `mono ${tone(r.change_pct)}` }, pct(r.change_pct, 2, true))),
    h('div', { class: 'small muted mono' }, money(r.price)));
  out.push(section('Today\'s movers', 'Largest 1-day moves among 40 mega-cap names.',
    h('div', { class: 'grid g2' },
      h('div', { class: 'card flat' }, h('h4', null, '▲ Top gainers'), home.movers.gainers.map(mv)),
      h('div', { class: 'card flat' }, h('h4', null, '▼ Top losers'), home.movers.losers.map(mv)))));

  // navigation
  const nav = [['#/analysis', 'Stock Analysis', 'Buy / Hold / Avoid verdict with a transparent rubric'],
    ['#/screener', 'Screener', 'Find names across the S&P 500'],
    ['#/compare', 'Compare', 'Side-by-side metrics and correlation'],
    ['#/portfolio', 'Portfolio', 'Weighted return, volatility and risk contributions'],
    ['#/watchlist', 'Watchlist', 'Track tickers, set price targets, get alerts']];
  out.push(section('Where to next', null, h('div', { class: 'grid g2' }, nav.map(([href, t, c]) =>
    h('a', { href, class: 'card flat', style: { color: 'inherit' } }, h('b', null, t), h('div', { class: 'small muted' }, c))))));
  out.push(h('p', { class: 'tiny muted' }, 'Data is for research and education, not investment advice. Quotes are cached for up to 30 minutes.'));
  return out;
}
