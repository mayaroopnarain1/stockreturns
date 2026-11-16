// Vega-Lite chart helpers. Specs are plain objects; draw() applies the theme and embeds them.
const PALETTE = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];
export const COLORS = { good: '#16a34a', bad: '#dc2626', warn: '#d97706', purple: '#8e44ad', slate: '#64748b' };

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const isDark = () => window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;

function config() {
  return {
    background: 'transparent',
    font: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    view: { stroke: null },
    axis: { labelColor: css('--muted'), titleColor: css('--muted'), domainColor: css('--border'),
            gridColor: css('--border'), tickColor: css('--border'), labelFontSize: 11, titleFontSize: 11, labelLimit: 110 },
    legend: { labelColor: css('--text'), titleColor: css('--muted'), labelFontSize: 11, orient: 'bottom', symbolType: 'stroke' },
    range: { category: PALETTE },
  };
}

const registry = new Map(); // element -> {spec, opts}

function fullSpec(spec, height) {
  return {
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    width: 'container', height, autosize: { type: 'fit', contains: 'padding' },
    config: config(), ...spec,
  };
}

/** Render a Vega-Lite spec into `el`. Safe to call repeatedly. */
export async function draw(el, spec, { height = 240 } = {}) {
  if (!window.vegaEmbed) { el.textContent = 'Charts unavailable.'; return null; }
  el.classList.add('chart');
  registry.set(el, { spec, height });
  try {
    return await window.vegaEmbed(el, fullSpec(spec, height), {
      actions: false, renderer: 'canvas', tooltip: { theme: isDark() ? 'dark' : 'light' },
    });
  } catch (e) {
    console.error('chart failed', e);
    el.textContent = 'This chart could not be drawn.';
    return null;
  }
}

if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    for (const [el, { spec, height }] of registry) {
      if (el.isConnected) window.vegaEmbed(el, fullSpec(spec, height), { actions: false, renderer: 'canvas' });
      else registry.delete(el);
    }
  });
}

// ------------------------------------------------------------------ builders
const tipDate = { field: 'd', type: 'temporal', title: 'Date', format: '%b %d, %Y' };

/** series: [{name, values, dash?, width?, color?}] sharing `dates`. */
export function line({ dates, series, yFormat = '.2f', zero = false, rules = [], yTitle = null, xFormat = '%b %Y', yLabelExpr = null }) {
  const rows = [];
  series.forEach((s) => dates.forEach((d, i) => { if (s.values[i] !== null && s.values[i] !== undefined) rows.push({ d, s: s.name, v: s.values[i] }); }));
  const names = series.map((s) => s.name);
  const colors = series.map((s, i) => s.color || PALETTE[i % PALETTE.length]);
  const layers = [{
    data: { values: rows },
    mark: { type: 'line', clip: true },
    encoding: {
      x: { field: 'd', type: 'temporal', axis: { title: null, format: xFormat, labelOverlap: true, grid: false } },
      y: { field: 'v', type: 'quantitative', scale: { zero }, axis: { title: yTitle, format: yFormat, ...(yLabelExpr ? { labelExpr: yLabelExpr } : {}) } },
      color: { field: 's', type: 'nominal', scale: { domain: names, range: colors }, legend: names.length > 1 ? { title: null } : null },
      strokeDash: { field: 's', type: 'nominal', scale: { domain: names, range: series.map((s) => s.dash || [1, 0]) }, legend: null },
      strokeWidth: { field: 's', type: 'nominal', scale: { domain: names, range: series.map((s) => s.width || 1.8) }, legend: null },
      tooltip: [tipDate, { field: 's', title: 'Series' }, { field: 'v', type: 'quantitative', title: 'Value', format: yFormat }],
    },
  }];
  rules.forEach((r) => layers.push({
    data: { values: [{ y: r.y }] },
    mark: { type: 'rule', strokeDash: r.dash || [4, 4], color: r.color || COLORS.slate, strokeWidth: 1 },
    encoding: { y: { field: 'y', type: 'quantitative' } },
  }));
  return { layer: layers };
}

export function area({ dates, values, yFormat = '.2f', color = PALETTE[0], yTitle = null }) {
  const rows = dates.map((d, i) => ({ d, v: values[i] })).filter((r) => r.v !== null);
  return {
    data: { values: rows },
    layer: [
      { mark: { type: 'area', opacity: 0.22, color } },
      { mark: { type: 'line', color, strokeWidth: 1.5 } },
    ],
    encoding: {
      x: { field: 'd', type: 'temporal', axis: { title: null, format: '%b %Y', grid: false } },
      y: { field: 'v', type: 'quantitative', axis: { title: yTitle, format: yFormat } },
      tooltip: [tipDate, { field: 'v', type: 'quantitative', title: 'Value', format: yFormat }],
    },
  };
}

/** Vertical bars. data: [{x, y, c?}] ; grouped when `color` is given. */
export function bars({ data, xTitle = null, yTitle = null, yFormat = '.1f', color = false, colorDomain, colorRange,
                       horizontal = false, sort = null, barColor = PALETTE[0], height }) {
  const cat = { field: 'x', type: 'nominal', axis: { title: xTitle, labelAngle: horizontal ? 0 : -30, labelLimit: horizontal ? 150 : 80 }, sort };
  const val = { field: 'y', type: 'quantitative', axis: { title: yTitle, format: yFormat } };
  const enc = horizontal ? { y: cat, x: val } : { x: cat, y: val };
  if (color) {
    enc.color = { field: 'c', type: 'nominal', scale: colorDomain ? { domain: colorDomain, range: colorRange || PALETTE } : undefined, legend: { title: null } };
    enc[horizontal ? 'yOffset' : 'xOffset'] = { field: 'c' };
  }
  enc.tooltip = [{ field: 'x', title: 'Item' }, ...(color ? [{ field: 'c', title: 'Measure' }] : []), { field: 'y', type: 'quantitative', title: 'Value', format: yFormat }];
  return { data: { values: data }, mark: { type: 'bar', color: color ? undefined : barColor, cornerRadiusEnd: 2 }, encoding: enc, ...(height ? { height } : {}) };
}

/** Heatmap with centered diverging colors and cell labels. values[y][x]. */
export function heat({ xs, ys, values, domain = [-1, 0, 1], range = ['#2166ac', '#f7f7f7', '#b2182b'], fmt = '.2f',
                       labelFlip = 0.5, legendTitle = null, hideLegend = false }) {
  const rows = [];
  ys.forEach((y, iy) => xs.forEach((x, ix) => {
    const v = values[iy][ix];
    if (v !== null && v !== undefined) rows.push({ x, y, v });
  }));
  const enc = {
    x: { field: 'x', type: 'nominal', sort: xs, axis: { title: null, orient: 'top', labelAngle: 0 } },
    y: { field: 'y', type: 'nominal', sort: ys, axis: { title: null } },
  };
  return {
    data: { values: rows },
    layer: [
      { mark: { type: 'rect' }, encoding: { ...enc,
        color: { field: 'v', type: 'quantitative', scale: { domain, range, clamp: true }, legend: hideLegend ? null : { title: legendTitle, format: fmt } },
        tooltip: [{ field: 'y', title: 'Row' }, { field: 'x', title: 'Column' }, { field: 'v', type: 'quantitative', title: 'Value', format: fmt }] } },
      { mark: { type: 'text', fontSize: 11, fontWeight: 600 }, encoding: { ...enc,
        text: { field: 'v', type: 'quantitative', format: fmt },
        color: { condition: { test: `abs(datum.v) > ${labelFlip}`, value: '#ffffff' }, value: '#111111' } } },
    ],
  };
}

export function scatter({ points, xTitle, yTitle }) {
  return {
    data: { values: points },
    layer: [
      { mark: { type: 'circle', size: 180, opacity: 0.9 }, encoding: { color: { field: 'ticker', type: 'nominal', legend: null } } },
      { mark: { type: 'text', align: 'left', dx: 10, fontSize: 12, fontWeight: 600 }, encoding: { text: { field: 'ticker', type: 'nominal' }, color: { value: css('--text') } } },
    ],
    encoding: {
      x: { field: 'x', type: 'quantitative', scale: { zero: false }, axis: { title: xTitle } },
      y: { field: 'y', type: 'quantitative', scale: { zero: false }, axis: { title: yTitle } },
      tooltip: [{ field: 'ticker' }, { field: 'x', title: xTitle, format: '.2f' }, { field: 'y', title: yTitle, format: '.2f' }],
    },
  };
}

/** Return histogram with an optional normal-curve overlay. */
export function histogram({ edges, counts, normal }) {
  const rows = counts.map((c, i) => ({ a: edges[i], b: edges[i + 1], c }));
  const layers = [{
    data: { values: rows }, mark: { type: 'bar', opacity: 0.75, color: PALETTE[0] },
    encoding: {
      x: { field: 'a', type: 'quantitative', scale: { zero: false }, axis: { title: 'Daily return (%)' } },
      x2: { field: 'b' },
      y: { field: 'c', type: 'quantitative', axis: { title: 'Frequency' } },
      tooltip: [{ field: 'a', title: 'From %', format: '.2f' }, { field: 'b', title: 'To %', format: '.2f' }, { field: 'c', title: 'Days' }],
    },
  }];
  if (normal) {
    layers.push({
      data: { values: normal.x.map((x, i) => ({ x, y: normal.y[i] })) },
      mark: { type: 'line', color: '#f59e0b', strokeDash: [6, 3], strokeWidth: 2 },
      encoding: { x: { field: 'x', type: 'quantitative' }, y: { field: 'y', type: 'quantitative' } },
    });
  }
  return { layer: layers };
}

/** Price line with event markers: events [{type,date,price,label,return_pct?}]. */
export function priceEvents({ dates, values, label, events, yFormat = ',.2f' }) {
  const line = {
    data: { values: dates.map((d, i) => ({ d, v: values[i] })).filter((r) => r.v !== null) },
    mark: { type: 'line', color: css('--text'), strokeWidth: 1.6 },
    encoding: { x: { field: 'd', type: 'temporal', axis: { title: null, format: '%b %Y', grid: false } },
                y: { field: 'v', type: 'quantitative', scale: { zero: false }, axis: { title: label, format: yFormat } },
                tooltip: [tipDate, { field: 'v', type: 'quantitative', title: label, format: yFormat }] },
  };
  const kindOf = (e) => (e.type === 'outlier' ? (e.return_pct >= 0 ? 'outlier-up' : 'outlier-down') : e.type);
  const pts = events.map((e) => ({ d: e.date, v: e.price, k: kindOf(e), label: e.label }));
  const layers = [line];
  if (pts.length) {
    layers.push({
      data: { values: pts },
      mark: { type: 'point', filled: true, opacity: 0.9, size: 110 },
      encoding: {
        x: { field: 'd', type: 'temporal' }, y: { field: 'v', type: 'quantitative' },
        color: { field: 'k', type: 'nominal', legend: null, scale: { domain: ['earnings', 'dividend', 'outlier-up', 'outlier-down'],
                 range: [COLORS.purple, COLORS.good, '#2ecc71', '#e74c3c'] } },
        shape: { field: 'k', type: 'nominal', legend: null, scale: { domain: ['earnings', 'dividend', 'outlier-up', 'outlier-down'],
                 range: ['triangle-up', 'circle', 'diamond', 'diamond'] } },
        tooltip: [{ field: 'label', title: 'Event' }, tipDate, { field: 'v', type: 'quantitative', title: label, format: yFormat }],
      },
    });
  }
  return { layer: layers };
}

export function macd({ dates, macd: m, signal, hist }) {
  const hrows = dates.map((d, i) => ({ d, v: hist[i] })).filter((r) => r.v !== null);
  const bar = { data: { values: hrows }, mark: { type: 'bar', opacity: 0.45 },
    encoding: { x: { field: 'd', type: 'temporal', axis: { title: null, format: '%b %Y' } }, y: { field: 'v', type: 'quantitative', axis: { title: null } },
      color: { condition: { test: 'datum.v > 0', value: COLORS.good }, value: COLORS.bad },
      tooltip: [tipDate, { field: 'v', title: 'Histogram', format: '.3f' }] } };
  const lines = line({ dates, series: [{ name: 'MACD', values: m, color: '#2980b9' }, { name: 'Signal', values: signal, color: '#e67e22' }], yFormat: '.2f' }).layer[0];
  return { layer: [bar, lines] };
}
