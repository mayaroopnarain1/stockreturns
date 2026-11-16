// Device-local persistence (watchlist, portfolio, preferences). Falls back to memory when
// localStorage is unavailable (private mode, blocked storage).
const mem = {};
function read(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw !== null) return JSON.parse(raw);
  } catch (e) { /* ignore */ }
  return key in mem ? mem[key] : fallback;
}
function write(key, value) {
  mem[key] = value;
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* memory only */ }
}

const WL = 'stocklens.watchlist', PF = 'stocklens.portfolio', PR = 'stocklens.prefs';
export const MAX_WATCHLIST = 50;
export const today = () => new Date().toISOString().slice(0, 10);

// ---- watchlist: [{ticker, target_price, added_date, notes}]
export const getWatchlist = () => read(WL, []);
export const saveWatchlist = (items) => write(WL, items);
export function addWatch(ticker, target = null, notes = '') {
  const t = ticker.trim().toUpperCase();
  const items = getWatchlist();
  const existing = items.find((i) => i.ticker === t);
  if (existing) {
    if (target) { existing.target_price = Number(target); saveWatchlist(items); }
    return false;
  }
  if (items.length >= MAX_WATCHLIST) return false;
  items.push({ ticker: t, target_price: target ? Number(target) : null, added_date: today(), notes });
  saveWatchlist(items);
  return true;
}
export function removeWatch(ticker) { saveWatchlist(getWatchlist().filter((i) => i.ticker !== ticker)); }
export function updateWatch(ticker, patch) {
  saveWatchlist(getWatchlist().map((i) => (i.ticker === ticker ? { ...i, ...patch } : i)));
}
export const watchTickers = () => getWatchlist().map((i) => i.ticker);

// ---- portfolio holdings: {tickers: [], weights: []}
export const getPortfolio = () => read(PF, { tickers: ['AAPL', 'MSFT', 'GOOGL'], weights: [40, 35, 25] });
export const savePortfolio = (p) => write(PF, p);

// ---- preferences by area
const DEFAULTS = {
  analysis: { horizon: '1y', start: '', end: '', profile: 'Balanced', rf: 0.05, outlier_z: 3, rolling: 30 },
  compare: { tickers: 'AAPL, MSFT, GOOGL', horizon: '1y', rf: 0.05, benchmark: true, profile: 'Balanced' },
  portfolio: { horizon: '1y', rf: 0.05 },
  screener: { filters: {}, sectors: [] },
};
export function getPrefs(area) { return { ...DEFAULTS[area], ...(read(PR, {})[area] || {}) }; }
export function setPrefs(area, patch) {
  const all = read(PR, {});
  all[area] = { ...(all[area] || {}), ...patch };
  write(PR, all);
}

// ---- backup / restore
export function exportAll() {
  return JSON.stringify({ version: 1, watchlist: getWatchlist(), portfolio: getPortfolio(), prefs: read(PR, {}) }, null, 2);
}
export function importAll(text) {
  const d = JSON.parse(text);
  if (!d || typeof d !== 'object') throw new Error('Not a StockLens backup file.');
  if (Array.isArray(d.watchlist)) {
    saveWatchlist(d.watchlist
      .filter((i) => i && typeof i.ticker === 'string')
      .slice(0, MAX_WATCHLIST)
      .map((i) => ({ ticker: i.ticker.toUpperCase(), target_price: i.target_price ?? null,
                     added_date: i.added_date || today(), notes: String(i.notes || '').slice(0, 500) })));
  }
  if (d.portfolio && Array.isArray(d.portfolio.tickers) && Array.isArray(d.portfolio.weights)) savePortfolio(d.portfolio);
  if (d.prefs && typeof d.prefs === 'object') write(PR, d.prefs);
}
