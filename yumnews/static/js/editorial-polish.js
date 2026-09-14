// [Sol] Lecture stable : pas d’animation de blocs ni d’interception des liens.
const body = document.body;
const article = document.querySelector('.reader-body');
let frame = 0;
if (article) body.classList.add('has-reading-progress');

function updateScroll() {
  frame = 0;
  body.classList.toggle('is-scrolled', window.scrollY > 16);
  if (article) {
    const end = article.getBoundingClientRect().bottom + window.scrollY - window.innerHeight;
    const progress = end <= 0 ? 1 : Math.min(1, Math.max(0, window.scrollY / end));
    body.style.setProperty('--reading-progress', progress.toFixed(4));
  }
}
function scheduleScroll() {
  if (!frame) frame = requestAnimationFrame(updateScroll);
}
window.addEventListener('scroll', scheduleScroll, { passive: true });
window.addEventListener('resize', scheduleScroll, { passive: true });
window.addEventListener('pageshow', scheduleScroll);
if (article && 'ResizeObserver' in window) new ResizeObserver(scheduleScroll).observe(article);
updateScroll();

// [Sol] Le catalogue de suggestions ne bloque pas la lecture du document.
import './reader-suggestions.js';

// [Sol] Mode livre accessible sur les deux lecteurs.
import './reading-room.js';
