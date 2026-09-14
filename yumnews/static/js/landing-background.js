// [Sol] Fondu discret, pause accessible, arrêt hors onglet et mode sans animation.
const host = document.getElementById('landingBackdrops');
const caption = document.getElementById('landingVisualCaption');
const title = document.getElementById('landingVisualTitle');
const label = document.getElementById('landingVisualLabel');
const next = document.getElementById('landingVisualNext');
const pause = document.getElementById('landingVisualPause');
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
let slides = [], index = -1, timer, paused = reduced.matches, loading = false;
const validImage = url => /^https:\/\/image\.tmdb\.org\/t\/p\/w1280\/[a-zA-Z0-9._-]+$/.test(url || '');
const validSource = url => /^https:\/\/www\.themoviedb\.org\/(movie|tv)\/\d+$/.test(url || '');

function schedule() {
  clearTimeout(timer);
  if (!paused && !document.hidden && slides.length > 1) timer = setTimeout(advance, 12000);
}
function state() {
  pause.textContent = paused ? 'Reprendre' : 'Pause';
  pause.setAttribute('aria-pressed', String(paused));
}
async function advance() {
  if (loading || !slides.length) return;
  loading = true;
  let failed = false;
  const target = (index + 1) % slides.length;
  const slide = slides[target];
  const image = new Image();
  image.alt = '';
  image.className = 'landing-backdrop';
  image.src = slide.backdrop;
  try {
    await image.decode();
    host.append(image);
    // Conserver seulement l'image précédente pendant le fondu.
    while (host.children.length > 2) host.firstElementChild.remove();
    requestAnimationFrame(() => requestAnimationFrame(() => {
      for (const el of host.children) el.classList.toggle('is-visible', el === image);
    }));
    index = target;
    title.textContent = slide.title;
    title.href = slide.source_url;
    label.textContent = slide.label;
    caption.hidden = false;
  } catch {
    failed = true;
    slides.splice(target, 1);
    index = Math.min(index, slides.length - 1);
  } finally {
    loading = false;
    next.disabled = pause.disabled = slides.length < 2;
    if (failed && slides.length) advance();
    else schedule();
  }
}
pause?.addEventListener('click', () => { paused = !paused; state(); schedule(); });
next?.addEventListener('click', () => { clearTimeout(timer); advance(); });
document.addEventListener('visibilitychange', schedule);
reduced.addEventListener('change', () => { paused = reduced.matches; state(); schedule(); });

if (host) {
  state();
  fetch('/api/landing/visuals', { headers: { Accept: 'application/json' } })
    .then(res => { if (!res.ok) throw new Error('Visuels indisponibles'); return res.json(); })
    .then(data => {
      slides = (data.results || []).filter(s => validImage(s.backdrop) && validSource(s.source_url)).slice(0, 8);
      next.disabled = pause.disabled = slides.length < 2;
      return advance();
    }).catch(() => { /* Le fond et tous les contenus existants restent visibles. */ });
}
