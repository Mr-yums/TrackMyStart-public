// Dashboard TrackMyStart — un état, des vues par onglet, chargement paresseux.
import { api, ApiError } from './api.js';
import { CatalogComfort } from './catalog-comfort.js'; // [Sol]
import { afterActor } from './advertising.js'; // [Sol]
import { recommendationsPanel } from './recommendations.js'; // [Sol]
import { PreferencePanel } from './preferences.js'; // [Sol]
import { $, $$, esc, el, toast, skeletons, empty, mediaCard, mangaCard, personCard, newsCard, animeRow, pill, initCarousels, fmtDate } from './ui.js';

const CFG = window.TRACKMYSTART || { policy: { plan: 'free', features: [], limits: {} } };
const state = {
  meta: null, me: null, loaded: new Set(),
  watch: new Map(), follows: new Map(),
  movies: { key: 'trending', sort: 'popularity' }, series: { key: 'trending', sort: 'popularity', platform: null },
  mangas: { key: 'popular', sort: 'popular', offset: 0, items: [] },
  people: { page: 0, items: [] }, news: { cat: null, source: null }, upcoming: { kind: 'all', data: null },
  heroTimer: null,
};
const personalFeed = recommendationsPanel(document.getElementById('recommendationsSection')); // [Sol]
const isPremium = () => state.me?.policy?.plan === 'premium' || CFG.policy.plan === 'premium';
const can = (f) => (state.me?.policy?.features || CFG.policy.features || []).includes(f);
const watchKey = (t, id) => `${t}:${id}`;
const comfort = new CatalogComfort(()=>can('advanced_filters'),()=>{
  for(const tab of ['home','movies','series','upcoming'])state.loaded.delete(tab);
  const active=document.querySelector('.panel.active')?.id;
  if(active==='tab-movies')loadMovies();else if(active==='tab-series')loadSeries();
});
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-status]');if(!button)return;
  event.stopPropagation();comfort.mark(button.closest('[data-title-status]'),button.dataset.status);
},true);
let movieRequest=0,seriesRequest=0; // [Sol] Une réponse ancienne ne remplace pas les nouveaux filtres.


// ---------- erreurs & upsell ----------
function handleError(err, ctx = '') {
  if (!(err instanceof ApiError)) { console.error(err); toast('Une erreur est survenue.', 'error'); return; }
  if (err.loginRequired) { location.href = err.payload?.login_url || '/connexion'; return; }
  if (err.premiumRequired) { toast(err.message, 'gold', 5000); return; }
  toast(err.message || ctx, 'error');
}
const upsell = (text) => `<div class="upsell"><span>🔒 ${esc(text)}</span><a class="btn btn-primary btn-sm" href="${CFG.checkoutUrl}">${CFG.paymentsEnabled ? "Passer Premium · " + esc(CFG.price) : "Préinscription gratuite"}</a></div>`;

// ---------- onglets ----------
function showTab(name) {
  $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  $$('.panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${name}`));
  // [Sol] Éviter une navigation identique qui interrompt le fondu de retour au fil.
  if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
  const loaders = { home: loadHome, movies: loadMovies, series: loadSeries, mangas: loadMangas, people: loadPeople, news: loadNews, upcoming: loadUpcoming, me: loadMe };
  if (name === 'me' || name === 'home') loaders[name]();
  else if (!state.loaded.has(name)) { state.loaded.add(name); loaders[name](); }
}
$('#tabs').addEventListener('click', (e) => { const t = e.target.closest('.tab'); if (t) showTab(t.dataset.tab); });
document.addEventListener('click', (e) => { const b = e.target.closest('[data-goto]'); if (b) showTab(b.dataset.goto); });

// [Sol] Personnaliser seulement l'accueil ; les catalogues restent consultables.
function applyPreferences(prefs) {
  if (!prefs) return;
  document.body.classList.toggle('compact-cards', prefs.compact_cards);
  const sections = new Set(prefs.sections);
  for (const [id, type] of Object.entries({carouselMovies:'movies', carouselNowPlaying:'movies', carouselSeries:'series', carouselMangas:'mangas', carouselPeople:'people', homeNews:'news'})) {
    document.getElementById(id).closest('.section').hidden = !sections.has(type);
  }
}
new PreferencePanel(document.getElementById('preferencesForm'), (prefs) => {
  if (state.me) state.me.preferences = prefs;
  state.loaded.delete('home');
  applyPreferences(prefs);
});
document.getElementById('preferencesShortcut').addEventListener('click', (event) => {
  event.preventDefault(); document.getElementById('preferencesForm').scrollIntoView({behavior:'smooth', block:'center'});
});

// ---------- accueil ----------
async function loadHome() {
  personalFeed.refresh(); // [Sol] Indépendant des autres catalogues.
  if (state.loaded.has('home')) return; state.loaded.add('home');
  ['carouselMovies', 'carouselNowPlaying', 'carouselSeries', 'carouselMangas', 'carouselPeople'].forEach((id) => ($(`#${id}`).innerHTML = skeletons(8)));
  try {
    const d = await api.home();
    renderHero(d.hero);
    $('#carouselMovies').innerHTML = d.movies_trending.map((i) => mediaCard(i, { inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty();
    $('#carouselNowPlaying').innerHTML = d.now_playing.map((i) => mediaCard(i, { inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty();
    $('#carouselSeries').innerHTML = d.series_trending.map((i) => mediaCard(i, { large: true, inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty();
    $('#carouselMangas').innerHTML = d.mangas_new.map((i) => mangaCard(i, { inWatchlist: state.watch.has(watchKey('manga', i.id)) })).join('') || empty();
    $('#carouselPeople').innerHTML = d.people.map((p) => personCard(p, { followed: state.follows.has(p.id) })).join('') || empty();
    $('#homeNews').innerHTML = d.headlines.map(newsCard).join('') || empty('Presse indisponible.');
  } catch (err) { handleError(err); }
  loadFeed();
}

function renderHero(items) {
  const slides = $('#heroSlides'), dots = $('#heroDots');
  if (!items?.length) { $('#hero').hidden = true; return; }
  slides.innerHTML = items.map((i, n) => `<div class="hero-slide ${n === 0 ? 'active' : ''}" data-type="${esc(i.media_type)}" data-id="${esc(i.id)}">
    <div class="hero-bg" style="background-image:url('${esc(i.backdrop)}')"></div><div class="hero-grad"></div>
    <div class="hero-content"><span class="hero-badge">${i.media_type === 'tv' ? 'Série' : 'Film'} · tendance</span><h2 class="hero-title">${esc(i.title)}</h2>
    <div class="hero-meta"><span>${esc(i.year)}</span><span class="hero-rating">★ ${esc(i.rating)}</span></div><p class="hero-overview">${esc(i.overview)}</p></div></div>`).join('');
  dots.innerHTML = items.map((_, n) => `<span class="hero-dot ${n === 0 ? 'active' : ''}" data-n="${n}"></span>`).join('');
  let cur = 0;
  const go = (n) => { cur = (n + items.length) % items.length; $$('.hero-slide').forEach((s, i) => s.classList.toggle('active', i === cur)); $$('.hero-dot').forEach((d, i) => d.classList.toggle('active', i === cur)); };
  dots.onclick = (e) => { const d = e.target.closest('.hero-dot'); if (d) { go(+d.dataset.n); restart(); } };
  const restart = () => { clearInterval(state.heroTimer); state.heroTimer = setInterval(() => go(cur + 1), 6000); };
  restart();
}

async function loadFeed() {
  const section = $('#feedSection');
  if (!state.follows.size) { section.hidden = true; return; }
  section.hidden = false; $('#carouselFeed').innerHTML = skeletons(6);
  try {
    const f = await api.feed();
    const items = f.upcoming.length ? f.upcoming : f.recent;
    $('#feedHint').textContent = f.locked ? `aperçu limité — Premium pour le fil complet` : `${f.upcoming.length} à venir · ${f.recent.length} récents`;
    $('#carouselFeed').innerHTML = items.map((i) => mediaCard(i, { showDate: true, tag: { text: i.person.name.split(' ')[0] }, inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty('Rien de prévu pour vos acteurs.');
  } catch (err) { handleError(err); }
}

// ---------- films ----------
function renderMoviePills() {
  const lists = [['trending', 'Tendances'], ['now_playing', "À l'affiche"], ['popular', 'Populaires'], ['top_rated', 'Mieux notés'], ['upcoming', 'Prochainement']];
  const genres = state.meta.genres.movie.map((g) => [g.key, g.label]);
  $('#moviePills').innerHTML = [...lists, ...genres].map(([v, l]) => pill(l, v, { active: v === state.movies.key, locked: v === 'upcoming' && !can('upcoming') })).join('');
}
async function loadMovies() {
  const request=++movieRequest;
  renderMoviePills();
  const grid = $('#movieGrid'); grid.innerHTML = skeletons(18);
  try { const d = await api.movies(state.movies.key, state.movies.sort); if(request!==movieRequest)return; const hint=document.querySelector('[data-catalog-filters=movie] [data-filter-count]'); if(hint)hint.textContent=`${d.results.length} titres sur ${d.scanned} dans cette sélection`; grid.innerHTML = d.results.map((i) => mediaCard(i, { inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty(); }
  catch (err) { if(request!==movieRequest)return; grid.innerHTML = err.premiumRequired ? upsell(err.message) : empty(err.message); }
}
$('#moviePills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.movies.key = p.dataset.value; loadMovies(); });
$('#movieSort').addEventListener('click', (e) => { state.movies.sort = state.movies.sort === 'rating' ? 'popularity' : 'rating'; e.currentTarget.classList.toggle('active', state.movies.sort === 'rating'); loadMovies(); });

// ---------- séries ----------
function renderSeriesPills() {
  const lists = [['trending', 'Tendances'], ['airing', 'En diffusion'], ['top_rated', 'Mieux notées'], ['upcoming', 'Prochainement']];
  const genres = state.meta.genres.tv.map((g) => [g.key, g.label]);
  $('#seriesPills').innerHTML = [...lists, ...genres].map(([v, l]) => pill(l, v, { active: !state.series.platform && v === state.series.key, locked: v === 'upcoming' && !can('upcoming') })).join('');
  $('#platformPills').innerHTML = state.meta.platforms.filter((p) => p.filterable).map((p) => pill(p.name, `platform:${p.key}`, { active: state.series.platform === `platform:${p.key}`, color: p.color })).join('');
}
async function loadSeries() {
  const request=++seriesRequest;
  renderSeriesPills();
  const grid = $('#seriesGrid'); grid.innerHTML = skeletons(12);
  const key = state.series.platform || state.series.key;
  try { const d = await api.series(key, state.series.sort); if(request!==seriesRequest)return; const hint=document.querySelector('[data-catalog-filters=tv] [data-filter-count]'); if(hint)hint.textContent=`${d.results.length} titres sur ${d.scanned} dans cette sélection`; grid.innerHTML = d.results.map((i) => mediaCard(i, { large: true, inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty(); }
  catch (err) { if(request!==seriesRequest)return; grid.innerHTML = err.premiumRequired ? upsell(err.message) : empty(err.message); }
}
$('#seriesPills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.series.key = p.dataset.value; state.series.platform = null; loadSeries(); });
$('#platformPills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.series.platform = state.series.platform === p.dataset.value ? null : p.dataset.value; loadSeries(); });
$('#seriesSort').addEventListener('click', (e) => { state.series.sort = state.series.sort === 'rating' ? 'popularity' : 'rating'; e.currentTarget.classList.toggle('active', state.series.sort === 'rating'); loadSeries(); });

// ---------- mangas ----------
async function loadMangas(append = false) {
  if (!append) {
    $('#mangaPills').innerHTML = [['popular', 'Populaires'], ['new', 'Nouveautés'], ...state.meta.manga_genres.map((g) => [g.key, g.label])].map(([v, l]) => pill(l, v, { active: v === state.mangas.key })).join('');
    state.mangas.offset = 0; state.mangas.items = []; $('#mangaGrid').innerHTML = skeletons(18);
    if (!state.loaded.has('anime')) { state.loaded.add('anime'); loadAnime(); }
  }
  try {
    const d = await api.mangas(state.mangas.key, state.mangas.sort, state.mangas.offset);
    state.mangas.items.push(...d.results); state.mangas.offset += d.results.length;
    $('#mangaGrid').innerHTML = state.mangas.items.map((i) => mangaCard(i, { inWatchlist: state.watch.has(watchKey('manga', i.id)) })).join('') || empty();
    $('#mangaMore').hidden = !d.has_more || state.mangas.key === 'new';
  } catch (err) { $('#mangaGrid').innerHTML = empty(err.message); }
}
async function loadAnime() {
  try { const d = await api.anime(); $('#animeSchedule').innerHTML = d.results.map(animeRow).join('') || empty('Planning indisponible.'); $('#animeHint').textContent = can('anime_schedule') ? `${d.results.length} épisodes cette semaine` : 'aperçu — Premium pour la semaine complète'; }
  catch (err) { $('#animeSchedule').innerHTML = empty(err.message); }
}
$('#mangaPills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.mangas.key = p.dataset.value; loadMangas(); });
$('#mangaSort').addEventListener('change', (e) => { state.mangas.sort = e.target.value; loadMangas(); });
$('#mangaMore').addEventListener('click', () => loadMangas(true));

// ---------- acteurs ----------
async function loadPeople() {
  const grid = $('#peopleGrid'); if (state.people.page === 0) grid.innerHTML = skeletons(18);
  try {
    const d = await api.people(state.people.page + 1); state.people.page = d.page; state.people.items.push(...d.results);
    renderPeople(); $('#peopleMore').hidden = d.page >= d.total_pages;
  } catch (err) { grid.innerHTML = empty(err.message); }
}
function renderPeople() {
  const q = $('#peopleFilter').value.trim().toLowerCase();
  const items = state.people.items.filter((p) => !q || p.name.toLowerCase().includes(q));
  $('#peopleGrid').innerHTML = items.map((p) => personCard(p, { followed: state.follows.has(p.id) })).join('') || empty('Aucun résultat.');
}
$('#peopleMore').addEventListener('click', loadPeople);
$('#peopleFilter').addEventListener('input', renderPeople);

// ---------- presse ----------
async function loadNews() {
  const cats = state.meta.news_categories;
  if (!state.news.cat) state.news.cat = (cats.find((c) => !c.locked) || cats[0]).key;
  $('#newsCatPills').innerHTML = cats.map((c) => pill(c.label, c.key, { active: c.key === state.news.cat, locked: c.locked })).join('');
  const sources = state.meta.sources.filter((s) => s.category === state.news.cat);
  $('#newsSourcePills').innerHTML = [pill('Toutes', '', { active: !state.news.source }), ...sources.map((s) => pill(s.name, s.key, { active: s.key === state.news.source, color: s.color }))].join('');
  const grid = $('#newsGrid'); grid.innerHTML = skeletons(6);
  try { const d = await api.news(state.news.cat, state.news.source); grid.innerHTML = d.articles.map(newsCard).join('') || empty('Aucun article récupéré.'); }
  catch (err) { grid.innerHTML = err.premiumRequired ? upsell(err.message) : empty(err.message); }
}
$('#newsCatPills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.news.cat = p.dataset.value; state.news.source = null; loadNews(); });
$('#newsSourcePills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; state.news.source = p.dataset.value || null; loadNews(); });

// ---------- prochainement ----------
async function loadUpcoming() {
  const grid = $('#upcomingGrid'); grid.innerHTML = skeletons(18);
  try { state.upcoming.data = await api.upcoming(); renderUpcoming(); }
  catch (err) { grid.innerHTML = err.premiumRequired ? upsell(err.message) : empty(err.message); }
}
function renderUpcoming() {
  const d = state.upcoming.data; if (!d) return;
  let items = state.upcoming.kind === 'movie' ? d.movies : state.upcoming.kind === 'tv' ? d.series : [...d.movies, ...d.series].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  $('#upcomingGrid').innerHTML = items.map((i) => mediaCard(i, { showDate: true, tag: { text: fmtDate(i.date), gold: true }, inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty();
}
$('#upcomingPills').addEventListener('click', (e) => { const p = e.target.closest('.pill'); if (!p) return; $$('#upcomingPills .pill').forEach((x) => x.classList.toggle('active', x === p)); state.upcoming.kind = p.dataset.kind; renderUpcoming(); });

// ---------- mon espace ----------
async function loadMe() {
  try {
    const d = await api.me(); state.me = d; applyPreferences(d.preferences);
    state.follows = new Map(d.follows.map((f) => [f.id, f])); state.watch = new Map(d.watchlist.map((w) => [watchKey(w.media_type, w.id), w]));
    document.body.classList.toggle('is-premium', d.policy.plan === 'premium');
    const sub = d.subscription, lim = d.policy.limits;
    $('#meHead').innerHTML = `<div><h2>${esc(d.user.display_name)}</h2><span class="muted small">${esc(d.user.email)}</span></div>
      <div class="me-stats"><div class="me-stat"><b>${d.follows.length}${lim.follows ? `<small class="muted">/${lim.follows}</small>` : ''}</b><span>acteurs suivis</span></div><div class="me-stat"><b>${d.watchlist.length}${lim.watchlist ? `<small class="muted">/${lim.watchlist}</small>` : ''}</b><span>dans ma liste</span></div><div class="me-stat"><b>${sub.active ? sub.days_left + ' j' : '—'}</b><span>${sub.active ? 'Premium restant' : 'plan Découverte'}</span></div></div>
      <a class="btn ${sub.active ? 'btn-ghost' : 'btn-primary'} btn-sm" href="${CFG.checkoutUrl}">${!CFG.paymentsEnabled ? 'Préinscription gratuite' : sub.active ? 'Prolonger' : 'Passer Premium · ' + esc(CFG.price)}</a>`;
    $('#followsHint').textContent = lim.follows ? `${d.follows.length} / ${lim.follows} (Premium : illimité)` : 'illimité';
    $('#watchlistHint').textContent = lim.watchlist ? `${d.watchlist.length} / ${lim.watchlist} (Premium : illimité)` : 'illimité';
    $('#followsGrid').innerHTML = d.follows.map((f) => personCard({ ...f, department: 'retirer ✕' }, { followed: true })).join('') || empty("Suivez des acteurs depuis l'onglet Acteurs ou une fiche.");
    $('#watchlistGrid').innerHTML = d.watchlist.map((w) => w.media_type === 'manga' ? mangaCard({ ...w, cover: w.poster }, { inWatchlist: true }) : mediaCard({ ...w, media_type: w.media_type }, { inWatchlist: true })).join('') || empty('Ajoutez des titres avec le bouton + sur une carte.');
    if (d.follows.length) { $('#carouselFeedRecent').innerHTML = skeletons(6); const f = await api.feed(); $('#carouselFeedRecent').innerHTML = f.recent.map((i) => mediaCard(i, { showDate: true, tag: { text: i.person.name.split(' ')[0] }, inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty('Pas de sortie récente.'); }
    else $('#carouselFeedRecent').innerHTML = empty('Suivez un acteur pour voir ses sorties ici.');
  } catch (err) { handleError(err); }
}

// ---------- ma liste / suivis (actions) ----------
async function toggleWatch(card) {
  const type = card.dataset.type, id = card.dataset.id, key = watchKey(type, id);
  const btn = $('[data-action="watch"]', card);
  try {
    if (state.watch.has(key)) { await api.removeWatch(type, id); state.watch.delete(key); btn.classList.remove('on'); btn.textContent = '+'; toast('Retiré de ma liste.'); if ($('#tab-me').classList.contains('active')) loadMe(); }
    else {
      const title = $('.card-title', card)?.textContent || '', poster = $('.card-poster', card)?.src || null, year = ($('.card-meta span', card)?.textContent || '').match(/\d{4}/)?.[0] || null;
      const r = await api.addWatch({ media_type: type, id, title, poster, year }); state.watch.set(key, r.result); btn.classList.add('on'); btn.textContent = '✓'; toast('Ajouté à ma liste.', 'success');
    }
    personalFeed.refresh(); // [Sol]
  } catch (err) { handleError(err); }
}
async function toggleFollow(p) {
  try {
    if (state.follows.has(p.id)) { await api.unfollow(p.id); state.follows.delete(p.id); toast(`${p.name} retiré de vos suivis.`); }
    else { const r = await api.follow({ id: p.id, name: p.name, profile: p.profile, department: p.department }); state.follows.set(p.id, r.result); toast(`Vous suivez ${p.name}.`, 'success'); }
    if ($('#tab-me').classList.contains('active')) loadMe();
    if ($('#tab-people').classList.contains('active')) renderPeople();
    state.loaded.delete('home');
    personalFeed.refresh(); // [Sol] Le retrait d’une star est pris en compte immédiatement.
  } catch (err) { handleError(err); }
}

// ---------- détail ----------
const detail = $('#detail'), detailInner = $('#detailInner');
function openDetail(type, id) {
  // [Sol] Dimensions propres aux acteurs et retour en haut à chaque fiche.
  detail.classList.toggle('detail-person', type === 'person');
  detail.scrollTop = 0;
  detailInner.scrollTop = 0;
  detail.classList.add('open'); detail.setAttribute('aria-hidden', 'false'); document.body.style.overflow = 'hidden';
  detailInner.innerHTML = `<div class="detail-backdrop skeleton"></div><div class="detail-body"><div class="skeleton" style="height:200px"></div></div>`;
  const loader = type === 'person' ? renderPerson : type === 'manga' ? renderManga : renderMedia;
  loader(type, id).catch((err) => { detailInner.innerHTML = `<div class="detail-body" style="margin-top:80px">${empty(err.message)}</div>`; });
}
function closeDetail() { const actor=detail.classList.contains('open') && detail.classList.contains('detail-person') && !!detail.querySelector('[data-follow-toggle]'); detail.classList.remove('open'); detail.setAttribute('aria-hidden', 'true'); document.body.style.overflow = ''; if(actor)afterActor(); }
$('#detailClose').addEventListener('click', closeDetail);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeDetail(); closeSearch(); } });

async function renderMedia(type, id) {
  const { result: m } = await api.detail(type, id);
  const key = watchKey(m.media_type, m.id), inList = state.watch.has(key);
  const offers = m.watch.offers.map((o) => `<a class="offer ${o.official ? 'offer-official' : ''}" style="--offer-color:${esc(o.color)}" href="${esc(o.url)}" target="_blank" rel="noopener">${o.logo ? `<img src="${esc(o.logo)}" alt="">` : ''}${esc(o.name)} <small>${esc(o.kind_label)}</small></a>`).join('');
  const network = m.network_platform ? `<a class="offer offer-official" style="--offer-color:${esc(m.network_platform.color)}" href="${esc(m.network_platform.url)}" target="_blank" rel="noopener">${esc(m.network_platform.name)} <small>diffuseur</small></a>` : '';
  const justwatch = m.watch.justwatch ? `<a class="offer" href="${esc(m.watch.justwatch)}" target="_blank" rel="noopener">Toutes les offres (JustWatch) →</a>` : '';
  const lock = m.watch.locked ? `<p class="lock-note">Connectez-vous pour voir toutes les plateformes.</p>` : '';
  detailInner.innerHTML = `<div class="detail-backdrop" style="background-image:url('${esc(m.backdrop || m.poster || '')}')"></div>
    <div class="detail-body">
      <div class="detail-top">${m.poster ? `<img class="detail-poster" src="${esc(m.poster)}" alt="">` : ''}
        <div><h2 class="detail-title">${esc(m.title)}</h2>${m.tagline ? `<p class="detail-tagline">${esc(m.tagline)}</p>` : ''}
        <div class="detail-meta"><span class="card-rating">★ ${esc(m.rating)}</span><span>${esc(m.year)}</span>${m.runtime ? `<span>${esc(m.runtime)} min</span>` : ''}${m.nb_seasons ? `<span>${esc(m.nb_seasons)} saison(s) · ${esc(m.nb_episodes)} ép.</span>` : ''}<span>${m.genres.map(esc).join(' · ')}</span></div></div></div>
      <div class="detail-actions"><button class="btn btn-sm ${inList ? 'btn-ghost' : 'btn-primary'}" data-watch-toggle data-type="${esc(m.media_type)}" data-id="${esc(m.id)}">${inList ? '✓ Dans ma liste' : '+ Ma liste'}</button>${m.homepage ? `<a class="btn btn-ghost btn-sm" href="${esc(m.homepage)}" target="_blank" rel="noopener">Site officiel</a>` : ''}</div>
      ${comfort.buttons(m)}
      <p>${esc(m.overview)}</p>
      <h3>📺 Où regarder (France)</h3>${lock}<div class="offers">${network}${offers}${justwatch}${!offers && !network ? '<span class="muted">Aucune offre de streaming référencée pour le moment.</span>' : ''}</div>
      ${m.trailer_url ? `<h3>🎬 Bande-annonce</h3><iframe class="trailer" src="${esc(m.trailer_url)}" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe>` : ''}
      ${m.directors.length ? `<h3>${m.media_type === 'tv' ? 'Créé par' : 'Réalisation'}</h3><div class="cast">${m.directors.map((p) => personCard({ ...p, department: 'suivre / voir' }, { followed: state.follows.has(p.id) })).join('')}</div>` : ''}
      ${m.cast.length ? `<h3>🎭 Casting</h3><div class="cast">${m.cast.map((p) => personCard({ ...p, department: p.character }, { followed: state.follows.has(p.id) })).join('')}</div>` : ''}
      ${m.media_type === 'tv' ? `<h3>📚 Saisons</h3><div class="seasons" id="seasons">${can('seasons') ? '<div class="skeleton" style="height:60px"></div>' : upsell('Le détail des saisons et épisodes est réservé aux membres Premium.')}</div>` : ''}
    </div>`;
  if (m.media_type === 'tv' && can('seasons')) {
    try { const { seasons } = await api.seasons(m.id); $('#seasons').innerHTML = seasons.map((s) => `<details><summary>${esc(s.name)} · ${s.episodes.length} épisodes${s.air_date ? ` · ${esc(s.air_date.slice(0, 4))}` : ''}</summary>${s.episodes.map((e) => `<div class="episode">${e.still ? `<img loading="lazy" src="${esc(e.still)}" alt="">` : ''}<div><b>${esc(e.episode_number)}. ${esc(e.name)}</b><span class="muted small">${esc(fmtDate(e.air_date))}${e.rating ? ` · ★ ${esc(e.rating)}` : ''}</span><div class="muted small">${esc(e.overview)}</div></div></div>`).join('')}</details>`).join('') || empty(); }
    catch (err) { $('#seasons').innerHTML = empty(err.message); }
  }
}
async function renderPerson(_type, id) {
  const { result: p } = await api.person(id);
  const followed = state.follows.has(p.id);
  const bio = p.biography ? esc(p.biography.slice(0, 900)) + (p.biography.length > 900 ? '…' : '') + (p.biography_lang === 'en' ? ' <span class="muted small">(biographie en anglais)</span>' : '') : '<span class="muted">Pas de biographie disponible.</span>';
  detailInner.innerHTML = `<div class="detail-backdrop" style="background-image:url('${esc(p.credits.find((c) => c.backdrop)?.backdrop || p.portrait || '')}')"></div>
    <div class="detail-body"><div class="detail-top">${p.portrait ? `<img class="detail-poster" src="${esc(p.portrait)}" alt="">` : ''}<div><h2 class="detail-title">${esc(p.name)}</h2>
      <div class="detail-meta"><span>${esc(p.department || '')}</span>${p.birthday ? `<span>né(e) le ${esc(fmtDate(p.birthday))}</span>` : ''}${p.birthplace ? `<span>${esc(p.birthplace)}</span>` : ''}</div></div></div>
      <div class="detail-actions"><button class="btn btn-sm ${followed ? 'btn-ghost' : 'btn-primary'}" data-follow-toggle data-person='${esc(JSON.stringify({ id: p.id, name: p.name, profile: p.portrait, department: p.department }))}'>${followed ? '★ Suivi · retirer' : '☆ Suivre'}</button>${p.homepage ? `<a class="btn btn-ghost btn-sm" href="${esc(p.homepage)}" target="_blank" rel="noopener">Site</a>` : ''}</div>
      <p>${bio}</p><h3>🎞 Filmographie</h3><div class="credits-grid">${p.credits.map((c) => mediaCard(c, { showDate: (c.date || '') >= new Date().toISOString().slice(0, 10), tag: (c.date || '') >= new Date().toISOString().slice(0, 10) ? { text: 'à venir', gold: true } : null, inWatchlist: state.watch.has(watchKey(c.media_type, c.id)) })).join('') || empty()}</div></div>`;
}
async function renderManga(_type, id) {
  const { result: m } = await api.manga(id);
  const key = watchKey('manga', m.id), inList = state.watch.has(key);
  detailInner.innerHTML = `<div class="detail-backdrop" style="background-image:url('${esc(m.cover || '')}');background-position:center 20%"></div>
    <div class="detail-body"><div class="detail-top">${m.cover ? `<img class="detail-poster" src="${esc(m.cover)}" alt="">` : ''}<div><h2 class="detail-title">${esc(m.title)}</h2>
      <div class="detail-meta">${m.rating ? `<span class="card-rating">★ ${esc(m.rating)}</span>` : ''}<span>${esc(m.author || '')}</span><span>${esc(m.year)}</span><span>${esc(m.status || '')}</span>${m.follows ? `<span>${Number(m.follows).toLocaleString('fr-FR')} lecteurs MangaDex</span>` : ''}</div>
      <div class="chips">${m.genres.map((g) => `<span class="chip chip-alt">${esc(g)}</span>`).join('')}</div></div></div>
      <div class="detail-actions"><button class="btn btn-sm ${inList ? 'btn-ghost' : 'btn-primary'}" data-watch-toggle data-type="manga" data-id="${esc(m.id)}" data-title="${esc(m.title)}" data-poster="${esc(m.cover || '')}" data-year="${esc(m.year)}">${inList ? '✓ Dans ma liste' : '+ Ma liste'}</button></div>
      ${comfort.buttons(m)}
      <p>${esc(m.overview)}</p>
      <h3>📖 Où lire légalement</h3><div class="offers"><a class="offer offer-official" style="--offer-color:#FF6740" href="${esc(m.read_urls.mangadex)}" target="_blank" rel="noopener">MangaDex <small>scantrad / officiel</small></a><a class="offer offer-official" style="--offer-color:#e60012" href="${esc(m.read_urls.mangaplus)}" target="_blank" rel="noopener">MANGA Plus <small>Shueisha</small></a></div>
      <h3>🆕 Derniers chapitres</h3><ul class="chapters">${m.chapters.map((c) => `<li><span>Ch. ${esc(c.chapter || '?')}${c.title ? ` — ${esc(c.title)}` : ''} <span class="muted small">${esc(c.lang)}${c.group ? ` · ${esc(c.group)}` : ''}</span></span><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(fmtDate(c.date))} →</a></li>`).join('') || '<li class="muted">Aucun chapitre référencé.</li>'}</ul></div>`;
}

// ---------- délégation globale ----------
document.addEventListener('click', async (e) => {
  const watchBtn = e.target.closest('[data-action="watch"]');
  if (watchBtn) { e.stopPropagation(); return toggleWatch(watchBtn.closest('.card')); }
  const wt = e.target.closest('[data-watch-toggle]');
  if (wt) { const d = wt.dataset, key = watchKey(d.type, d.id); try { if (state.watch.has(key)) { await api.removeWatch(d.type, d.id); state.watch.delete(key); wt.textContent = '+ Ma liste'; wt.className = 'btn btn-sm btn-primary'; } else { const title = d.title || $('.detail-title')?.textContent || '', poster = d.poster || $('.detail-poster')?.src || null, year = d.year || ($('.detail-meta')?.textContent || '').match(/\d{4}/)?.[0] || null; const r = await api.addWatch({ media_type: d.type, id: d.id, title, poster, year }); state.watch.set(key, r.result); wt.textContent = '✓ Dans ma liste'; wt.className = 'btn btn-sm btn-ghost'; toast('Ajouté à ma liste.', 'success'); } } catch (err) { handleError(err); } return; }
  const ft = e.target.closest('[data-follow-toggle]');
  if (ft) { const p = JSON.parse(ft.dataset.person); await toggleFollow(p); const f = state.follows.has(p.id); ft.textContent = f ? '★ Suivi · retirer' : '☆ Suivre'; ft.className = `btn btn-sm ${f ? 'btn-ghost' : 'btn-primary'}`; return; }
  const person = e.target.closest('.person-card');
  if (person) { if (person.closest('#followsGrid')) return toggleFollow({ id: +person.dataset.id, name: $('.person-name', person).textContent }); return openDetail('person', person.dataset.id); }
  const card = e.target.closest('.card, .hero-slide');
  if (card && card.dataset.type) return openDetail(card.dataset.type, card.dataset.id);
});

// ---------- recherche ----------
const overlay = $('#searchOverlay'); let searchTimer;
function closeSearch() { overlay.hidden = true; }
$('#searchClose').addEventListener('click', closeSearch);
overlay.addEventListener('click', (e) => { if (e.target === overlay) closeSearch(); });
$('#searchInput').addEventListener('input', (e) => { clearTimeout(searchTimer); const q = e.target.value.trim(); if (q.length < 2) return closeSearch(); searchTimer = setTimeout(() => runSearch(q), 450); });
async function runSearch(q) {
  overlay.hidden = false; $('#searchTitle').textContent = `Recherche « ${q} »`; $('#searchGrid').innerHTML = skeletons(6); $('#searchMangaGrid').innerHTML = '';
  try {
    const d = await api.search(q);
    $('#searchGrid').innerHTML = d.results.map((i) => i.media_type === 'person' ? personCard(i, { followed: state.follows.has(i.id) }) : mediaCard(i, { inWatchlist: state.watch.has(watchKey(i.media_type, i.id)) })).join('') || empty('Aucun film, série ou acteur.');
    $('#searchMangaGrid').innerHTML = d.mangas.map((m) => mangaCard(m, { inWatchlist: state.watch.has(watchKey('manga', m.id)) })).join('');
  } catch (err) { $('#searchGrid').innerHTML = empty(err.message); }
}

// ---------- démarrage ----------
(async function init() {
  initCarousels();
  try { const [meta, me] = await Promise.all([api.meta(), api.me().catch(() => null)]); state.meta = { ...meta, sources: (await api.newsCategories()).sources }; if (me) { state.me = me; state.follows = new Map(me.follows.map((f) => [f.id, f])); state.watch = new Map(me.watchlist.map((w) => [watchKey(w.media_type, w.id), w])); document.body.classList.toggle('is-premium', me.policy.plan === 'premium'); } }
  catch (err) { handleError(err); return; }
  await comfort.init();
  applyPreferences(state.me?.preferences);
  const initial = location.hash.replace('#', '') || state.me?.preferences?.start_tab || 'home';
  showTab(['home', 'movies', 'series', 'mangas', 'people', 'news', 'upcoming', 'me'].includes(initial) ? initial : 'home');
})();
