// Composants de rendu (fonctions pures → HTML) + utilitaires DOM.
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const fmtDate = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }); };
export const relDate = (iso) => { if (!iso) return ''; const diff = (Date.now() - new Date(iso)) / 36e5; if (diff < 1) return "à l'instant"; if (diff < 24) return `il y a ${Math.floor(diff)} h`; if (diff < 48) return 'hier'; return fmtDate(iso); };
export const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };

export function toast(message, kind = 'info', ms = 3200) {
  const box = $('#toasts'); if (!box) return;
  const t = el(`<div class="toast toast-${kind}">${esc(message)}</div>`);
  box.appendChild(t); setTimeout(() => t.remove(), ms);
}

export function skeletons(n = 8) { return Array.from({ length: n }, () => '<div class="skeleton-card"></div>').join(''); }
export function empty(msg = 'Rien à afficher pour le moment.') { return `<p class="empty">${esc(msg)}</p>`; }

export function mediaCard(item, { large = false, tag = null, inWatchlist = false, showDate = false } = {}) {
  const img = large ? (item.backdrop || item.poster) : item.poster;
  const poster = img ? `<img class="card-poster" loading="lazy" src="${esc(img)}" alt="">` : `<div class="card-poster-empty">🎬</div>`;
  const kind = item.media_type === 'tv' ? 'Série' : 'Film';
  const tagHtml = tag ? `<span class="card-tag ${tag.gold ? 'gold' : ''}">${esc(tag.text)}</span>` : '';
  return `<div class="card ${large ? 'card-lg' : ''}" data-type="${esc(item.media_type)}" data-id="${esc(item.id)}">
    ${poster}${tagHtml}
    <button class="card-btn ${inWatchlist ? 'on' : ''}" data-action="watch" title="${inWatchlist ? 'Retirer de ma liste' : 'Ajouter à ma liste'}">${inWatchlist ? '✓' : '+'}</button>
    <div class="card-info"><div class="card-title" title="${esc(item.title)}">${esc(item.title)}</div>
    <div class="card-meta"><span>${showDate && item.date ? esc(fmtDate(item.date)) : esc(item.year || kind)}</span>${item.rating ? `<span class="card-rating">★ ${esc(item.rating)}</span>` : `<span>${kind}</span>`}</div></div>
  </div>`;
}

export function mangaCard(item, { inWatchlist = false } = {}) {
  const poster = item.cover ? `<img class="card-poster" loading="lazy" src="${esc(item.cover)}" alt="">` : `<div class="card-poster-empty">📚</div>`;
  return `<div class="card card-manga" data-type="manga" data-id="${esc(item.id)}">
    ${poster}${item.has_french ? '<span class="card-tag">FR</span>' : ''}
    <button class="card-btn ${inWatchlist ? 'on' : ''}" data-action="watch" title="Ma liste">${inWatchlist ? '✓' : '+'}</button>
    <div class="card-info"><div class="card-title" title="${esc(item.title)}">${esc(item.title)}</div>
    <div class="card-meta"><span>${esc(item.year || item.status || 'manga')}</span>${item.rating ? `<span class="card-rating">★ ${esc(item.rating)}</span>` : `<span>${esc(item.demographic || '')}</span>`}</div></div>
  </div>`;
}

export function personCard(p, { followed = false } = {}) {
  const img = p.profile ? `<img class="person-avatar" loading="lazy" src="${esc(p.profile)}" alt="">` : '<div class="person-avatar"></div>';
  return `<div class="person-card" data-type="person" data-id="${esc(p.id)}">${img}
    <div class="person-name">${esc(p.name)}</div><div class="person-dept">${followed ? '★ suivi · ' : ''}${esc(p.department || p.character || '')}</div></div>`;
}

export function newsCard(a) {
  const img = a.image ? `<img class="news-img" loading="lazy" src="${esc(a.image)}" alt="" onerror="this.remove()">` : '';
  return `<article class="news-card" style="--src-color:${esc(a.source.color)}">${img}
    <div class="news-body"><div class="news-src"><b>${esc(a.source.name)}</b><span>${esc(relDate(a.date))}</span></div>
    <div class="news-title">${a.reader_url ? `<a href="${esc(a.reader_url)}">${esc(a.title)}</a>` : esc(a.title)}</div><div class="news-desc">${esc(a.description)}</div>
    ${a.reader_url ? `<a class="news-link" href="${esc(a.reader_url)}">Lire sur TrackMyStart →</a>` : `<a class="news-link" href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">Lire sur ${esc(a.source.name)} →</a>`}</div></article>`;
}

export function animeRow(e) {
  const when = new Date(e.airing_at * 1000).toLocaleString('fr-FR', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  const links = e.streaming.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.site)}</a>`).join('');
  return `<div class="anime-row" style="--anime-color:${esc(e.color || '#a855f7')}"><img loading="lazy" src="${esc(e.cover)}" alt="">
    <div><div class="t">${esc(e.title)}</div><div class="m">Épisode ${esc(e.episode)} · ${esc(when)}</div><div class="links">${links || `<a href="${esc(e.url)}" target="_blank" rel="noopener">AniList</a>`}</div></div></div>`;
}

export function pill(label, value, { active = false, color = null, locked = false } = {}) {
  return `<span class="pill ${active ? 'active' : ''} ${locked ? 'locked' : ''}" data-value="${esc(value)}" ${color ? `style="--pill-color:${esc(color)}"` : ''}>${esc(label)}</span>`;
}

export function initCarousels(root = document) {
  $$('.carousel-wrap', root).forEach((wrap) => {
    const c = $('.carousel', wrap);
    $('.prev', wrap)?.addEventListener('click', () => c.scrollBy({ left: -c.clientWidth * 0.8 }));
    $('.next', wrap)?.addEventListener('click', () => c.scrollBy({ left: c.clientWidth * 0.8 }));
  });
}
