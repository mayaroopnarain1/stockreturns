// Minimal hash router: "#/analysis/AAPL?tab=risk" -> page module render().
const routes = [
  { name: 'home', re: /^\/?$/ },
  { name: 'analysis', re: /^\/analysis(?:\/([^/?#]+))?\/?$/ },
  { name: 'screener', re: /^\/screener\/?$/ },
  { name: 'compare', re: /^\/compare\/?$/ },
  { name: 'portfolio', re: /^\/portfolio\/?$/ },
  { name: 'watchlist', re: /^\/watchlist\/?$/ },
];

export function parseHash(hash = window.location.hash) {
  const raw = hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  for (const r of routes) {
    const m = path.match(r.re);
    if (m) return { name: r.name, params: m.slice(1).map((x) => (x ? decodeURIComponent(x) : x)), query: new URLSearchParams(query), path };
  }
  return { name: 'home', params: [], query: new URLSearchParams(), path: '/' };
}

export function navigate(path) { window.location.hash = path; }
export const analysisUrl = (t, tab) => `#/analysis/${encodeURIComponent(t)}${tab ? `?tab=${tab}` : ''}`;

export function startRouter({ view, load, onRoute }) {
  let token = 0;
  async function run() {
    const route = parseHash();
    const mine = ++token;
    onRoute && onRoute(route);
    view.replaceChildren();
    window.scrollTo(0, 0);
    try {
      const mod = await load(route.name);
      if (mine !== token) return;
      await mod.render({ el: view, params: route.params, query: route.query, alive: () => mine === token });
    } catch (e) {
      if (mine !== token) return;
      console.error(e);
      const box = document.createElement('div');
      box.className = 'banner error';
      box.textContent = `Something went wrong loading this page: ${e.message || e}`;
      view.replaceChildren(box);
    }
  }
  window.addEventListener('hashchange', run);
  run();
  return run;
}
