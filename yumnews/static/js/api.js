// Client HTTP du dashboard : un seul point d'entrée, erreurs normalisées.
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

export class ApiError extends Error {
  constructor(message, code, status, payload) { super(message); this.code = code; this.status = status; this.payload = payload; }
  get premiumRequired() { return this.code === 'premium_required' || this.code === 'quota_exceeded'; }
  get loginRequired() { return this.code === 'login_required'; }
}

async function call(method, url, body) {
  const opts = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.headers['X-CSRFToken'] = CSRF; opts.body = JSON.stringify(body); }
  else if (method !== 'GET') { opts.headers['X-CSRFToken'] = CSRF; }
  let res, data;
  try { res = await fetch(url, opts); data = await res.json(); }
  catch (e) { throw new ApiError('Réseau indisponible.', 'network', 0, null); }
  if (!res.ok || data.ok === false) throw new ApiError(data.error || 'Erreur', data.code || 'error', res.status, data);
  return data;
}

export const api = {
  put: (url, body) => call('PUT', url, body), // [Sol]
  get: (url) => call('GET', url),
  post: (url, body) => call('POST', url, body),
  del: (url) => call('DELETE', url),
  meta: () => call('GET', '/api/meta'),
  home: () => call('GET', '/api/home'),
  movies: (key, sort) => call('GET', `/api/movies/${key}?sort=${sort}`),
  series: (key, sort) => call('GET', `/api/series/${key}?sort=${sort}`),
  upcoming: () => call('GET', '/api/upcoming'),
  detail: (type, id) => call('GET', `/api/detail/${type}/${id}`),
  seasons: (id) => call('GET', `/api/tv/${id}/seasons`),
  search: (q) => call('GET', `/api/search?q=${encodeURIComponent(q)}`),
  people: (page) => call('GET', `/api/people?page=${page}`),
  person: (id) => call('GET', `/api/person/${id}`),
  mangas: (key, sort, offset) => call('GET', `/api/mangas/${key}?sort=${sort}&offset=${offset}`),
  manga: (id) => call('GET', `/api/mangas/detail/${id}`),
  anime: () => call('GET', '/api/anime/schedule'),
  newsCategories: () => call('GET', '/api/news/categories'),
  news: (cat, source) => call('GET', `/api/news/${cat}${source ? `?source=${source}` : ''}`),
  savePreferences: (prefs) => call('PUT', '/api/me/preferences', prefs), // [Sol]
  saveRecommendationSettings: (values) => call('PUT', '/api/me/recommendations/settings', values), // [Sol]
  me: () => call('GET', '/api/me'),
  feed: () => call('GET', '/api/me/feed'),
  follow: (p) => call('POST', '/api/me/follows', p),
  unfollow: (id) => call('DELETE', `/api/me/follows/${id}`),
  addWatch: (item) => call('POST', '/api/me/watchlist', item),
  removeWatch: (type, id) => call('DELETE', `/api/me/watchlist/${type}/${id}`),
};
