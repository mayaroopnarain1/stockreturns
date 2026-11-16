// App shell: routing, navigation state, cold-start banner, service worker.
import { startRouter } from './router.js';

const pages = {
  home: () => import('./pages/home.js'),
  analysis: () => import('./pages/analysis.js'),
  screener: () => import('./pages/screener.js'),
  compare: () => import('./pages/compare.js'),
  portfolio: () => import('./pages/portfolio.js'),
  watchlist: () => import('./pages/watchlist.js'),
};

const wake = document.getElementById('wake');
window.addEventListener('api-slow', () => {
  wake.textContent = 'Waking the server — free hosting sleeps when idle, so the first request can take up to a minute.';
  wake.hidden = false;
});
window.addEventListener('api-ok', () => { wake.hidden = true; });

startRouter({
  view: document.getElementById('app'),
  load: (name) => pages[name](),
  onRoute: (route) => {
    document.querySelectorAll('nav.bottom a').forEach((a) => a.classList.toggle('on', a.dataset.route === route.name));
  },
});

if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
