// DOM helpers, number formatting and reusable UI components. No framework, no innerHTML with data.

const PROP_KEYS = new Set(['value', 'checked', 'disabled', 'selected', 'indeterminate']);

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv;   // custom props need setProperty
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (PROP_KEYS.has(k)) el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

export const clear = (el) => { el.replaceChildren(); return el; };

// ------------------------------------------------------------------ formatting
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
export const DASH = '—';

export function num(v, d = 2) {
  return isNum(v) ? v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) : DASH;
}
/** v is already a percent number (e.g. 12.3 -> "12.3%"). */
export function pct(v, d = 1, sign = false) {
  if (!isNum(v)) return DASH;
  return `${sign && v > 0 ? '+' : ''}${num(v, d)}%`;
}
/** v is a ratio (0.123 -> "12.3%"). */
export const pctR = (v, d = 1, sign = false) => (isNum(v) ? pct(v * 100, d, sign) : DASH);
export const money = (v, d = 2) => (isNum(v) ? `${v < 0 ? '-' : ''}$${num(Math.abs(v), d)}` : DASH);
export function big(v) {
  if (!isNum(v)) return DASH;
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e12) return `${s}$${num(a / 1e12, 2)}T`;
  if (a >= 1e9) return `${s}$${num(a / 1e9, 2)}B`;
  if (a >= 1e6) return `${s}$${num(a / 1e6, 1)}M`;
  return `${s}$${num(a, 0)}`;
}
export const signed = (v, d = 2, suffix = '') => (isNum(v) ? `${v > 0 ? '+' : ''}${num(v, d)}${suffix}` : DASH);
export const tone = (v) => (!isNum(v) || v === 0 ? '' : v > 0 ? 'good' : 'bad');
export const isNumber = isNum;

// ------------------------------------------------------------------ components
export function tile({ label, value, sub, subTone, note, valueTone }) {
  return h('div', { class: 'tile' },
    h('div', { class: 'label' }, label),
    h('div', { class: `value mono ${valueTone || ''}` }, value ?? DASH),
    sub ? h('div', { class: `delta mono ${subTone || ''}` }, sub) : null,
    note ? h('div', { class: 'note' }, note) : null);
}

export const banner = (kind, ...kids) => h('div', { class: `banner ${kind}` }, ...kids);
export const b = (...kids) => h('b', null, ...kids);

export function section(title, caption, ...kids) {
  return h('div', { class: 'section' }, title ? h('h2', null, title) : null,
    caption ? h('p', { class: 'sub' }, caption) : null, ...kids);
}

export function loading(msg = 'Loading…') {
  return h('div', { class: 'center muted' }, h('span', { class: 'spin' }), h('div', { style: { marginTop: '8px' } }, msg));
}

export function errorBox(err, retry) {
  return h('div', { class: 'banner error stack' },
    h('div', null, err && err.message ? err.message : String(err)),
    retry ? h('button', { class: 'btn small', onclick: retry }, 'Try again') : null);
}

/** Run an async loader into `container` with a spinner and an error box (with retry). */
export async function into(container, loader, msg) {
  const run = async () => {
    container.replaceChildren(loading(msg));
    try {
      const node = await loader();
      container.replaceChildren(...[].concat(node).filter(Boolean));
    } catch (e) {
      console.error(e);
      container.replaceChildren(errorBox(e, run));
    }
  };
  await run();
}

export function details(title, body, { open = false, onOpen } = {}) {
  const d = h('details', { class: 'exp' }, h('summary', null, title), h('div', { class: 'body' }, body));
  if (open) d.open = true;
  if (onOpen) {
    let done = false;
    d.addEventListener('toggle', () => { if (d.open && !done) { done = true; onOpen(); } });
    if (open) { done = true; queueMicrotask(onOpen); }
  }
  return d;
}

export function seg(options, value, onChange) {
  const wrap = h('div', { class: 'seg' });
  options.forEach((o) => {
    const opt = typeof o === 'string' ? { value: o, label: o } : o;
    wrap.append(h('button', {
      type: 'button', class: opt.value === value ? 'on' : '',
      onclick: () => {
        [...wrap.children].forEach((c) => c.classList.remove('on'));
        wrap.children[options.indexOf(o)].classList.add('on');
        onChange(opt.value);
      },
    }, opt.label));
  });
  return wrap;
}

export function select(options, value, onChange, attrs = {}) {
  const s = h('select', attrs, options.map((o) => {
    const opt = typeof o === 'string' ? { value: o, label: o } : o;
    return h('option', { value: opt.value, selected: String(opt.value) === String(value) }, opt.label);
  }));
  if (onChange) s.addEventListener('change', () => onChange(s.value));
  return s;
}

export const field = (label, control) => h('label', { class: 'field' }, label, control);

/** Tabs with lazily-loaded panels. defs: [{id,label,load:(panelEl)=>Promise|void}] */
export function tabs(defs, { active, onSelect } = {}) {
  const bar = h('div', { class: 'tabs', role: 'tablist' });
  const panels = h('div');
  const loaded = new Set();
  const els = {};
  function show(id) {
    defs.forEach((d) => {
      els[d.id].btn.classList.toggle('on', d.id === id);
      els[d.id].panel.hidden = d.id !== id;
    });
    if (!loaded.has(id)) {
      loaded.add(id);
      const d = defs.find((x) => x.id === id);
      Promise.resolve(d.load(els[id].panel)).catch((e) => { console.error(e); els[id].panel.replaceChildren(errorBox(e)); });
    }
    onSelect && onSelect(id);
  }
  defs.forEach((d) => {
    const btn = h('button', { type: 'button', role: 'tab', onclick: () => show(d.id) }, d.label);
    const panel = h('div', { role: 'tabpanel', hidden: true });
    els[d.id] = { btn, panel };
    bar.append(btn); panels.append(panel);
  });
  const root = h('div', null, bar, panels);
  root.show = show;
  root.reload = (id) => { loaded.delete(id); if (!els[id].panel.hidden) show(id); };
  queueMicrotask(() => show(defs.some((d) => d.id === active) ? active : defs[0].id));
  return root;
}

/** Sortable table. cols: [{key,label,get?(row),fmt?(v,row),cls?(v,row),sort?:bool,wrap?:bool}] */
export function table({ cols, rows, sortKey, sortDir = -1, onRow, className = '', bestCell }) {
  let key = sortKey, dir = sortDir;
  const wrap = h('div', { class: 'tbl-wrap' });
  function val(c, r) { return c.get ? c.get(r) : r[c.key]; }
  function draw() {
    const data = [...rows];
    if (key) {
      const c = cols.find((x) => x.key === key);
      if (c) {
        data.sort((a, b2) => {
          const x = val(c, a), y = val(c, b2);
          const nx = x === null || x === undefined || (typeof x === 'number' && !Number.isFinite(x));
          const ny = y === null || y === undefined || (typeof y === 'number' && !Number.isFinite(y));
          if (nx && ny) return 0; if (nx) return 1; if (ny) return -1;
          if (typeof x === 'string' || typeof y === 'string') return String(x).localeCompare(String(y)) * dir;
          return (x - y) * dir;
        });
      }
    }
    const head = h('tr', null, cols.map((c) => h('th', {
      class: c.sort === false ? '' : 'sortable',
      onclick: c.sort === false ? null : () => { if (key === c.key) dir = -dir; else { key = c.key; dir = -1; } draw(); },
    }, c.label, key === c.key ? (dir > 0 ? ' ▲' : ' ▼') : '')));
    const body = data.map((r) => h('tr', { onclick: onRow ? () => onRow(r) : null },
      cols.map((c) => {
        const v = val(c, r);
        const best = bestCell ? bestCell(c, r) : false;
        return h('td', { class: [c.cls ? c.cls(v, r) : '', c.wrap ? 'wrap' : '', best ? 'best' : ''].join(' ').trim() },
          c.fmt ? c.fmt(v, r) : (v ?? DASH));
      })));
    wrap.replaceChildren(h('table', { class: `tbl ${onRow ? 'clickable' : ''} ${className}` }, h('thead', null, head), h('tbody', null, body)));
  }
  draw();
  wrap.redraw = draw;
  return wrap;
}

/** Plain key/row table from an API DataFrame {index, columns, data}. */
export function frameTable(frame, fmts = {}, fallback = (v) => num(v, 2)) {
  if (!frame || !frame.index) return h('p', { class: 'muted small' }, DASH);
  const cols = [{ key: '_k', label: '', sort: false }].concat(frame.columns.map((c, i) => ({ key: `c${i}`, label: c, sort: false })));
  const rows = frame.index.map((name, r) => {
    const o = { _k: name };
    frame.columns.forEach((_, i) => { o[`c${i}`] = frame.data[r][i]; });
    return o;
  });
  const t = table({
    cols: cols.map((c) => (c.key === '_k' ? c : { ...c, fmt: (v, row) => (fmts[row._k] || fallback)(v) })),
    rows,
  });
  return t;
}

// -------------------------------------------------------------- sheet + toast
export function openSheet(title, body) {
  const scrim = h('div', { class: 'scrim', onclick: (e) => { if (e.target === scrim) close(); } });
  const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-label': title },
    h('div', { class: 'row between' }, h('h3', null, title), h('button', { class: 'btn small', onclick: () => close() }, 'Done')), body);
  scrim.append(sheet);
  document.body.append(scrim);
  function close() { scrim.remove(); }
  return close;
}

let toastTimer;
export function toast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

export function link(href, text, cls = '') { return h('a', { href, class: cls }, text); }

export function metricDescriptions(map, labelOf = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase())) {
  return h('div', { class: 'stack' }, Object.entries(map || {}).map(([k, d]) =>
    h('p', { class: 'small' }, h('b', null, `${labelOf(k)}: `), d)));
}

export function download(filename, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h('a', { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
