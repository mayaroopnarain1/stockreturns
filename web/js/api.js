// Thin fetch wrapper: JSON in/out, friendly errors, short GET cache, slow-server signal.
export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const cache = new Map();

export function qs(params) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === null || v === undefined || v === '') continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : '';
}

function detailMessage(data) {
  const d = data && data.detail;
  if (!d) return null;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return JSON.stringify(d);
}

export async function api(path, { method = 'GET', body, ttl = 0 } = {}) {
  const key = `${method} ${path} ${body ? JSON.stringify(body) : ''}`;
  if (ttl) {
    const hit = cache.get(key);
    if (hit && Date.now() - hit.t < ttl) return hit.v;
  }
  // Free hosts sleep when idle; tell the UI if a request is taking a while.
  const slow = setTimeout(() => window.dispatchEvent(new CustomEvent('api-slow')), 3500);
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    clearTimeout(slow);
    window.dispatchEvent(new CustomEvent('api-ok'));
    throw new ApiError('Network problem — check your connection and try again.', 0);
  }
  clearTimeout(slow);
  window.dispatchEvent(new CustomEvent('api-ok'));
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
  if (!res.ok) {
    const fallback = res.status === 429 ? 'Too many requests — wait a moment.' : `Request failed (${res.status}).`;
    throw new ApiError(detailMessage(data) || fallback, res.status);
  }
  if (ttl) cache.set(key, { t: Date.now(), v: data });
  return data;
}

export function clearApiCache() { cache.clear(); }

let metaPromise = null;
export function getMeta() {
  if (!metaPromise) metaPromise = api('/meta', { ttl: 3600e3 }).catch((e) => { metaPromise = null; throw e; });
  return metaPromise;
}
