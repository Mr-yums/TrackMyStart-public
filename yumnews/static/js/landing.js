import './editorial-polish.js';
import './landing-background.js';
import { api } from './api.js';
import { mediaCard, empty } from './ui.js';
const box = document.getElementById('landingTrending');
api.get('/api/movies/trending').then((d) => { box.innerHTML = d.results.slice(0, 16).map((i) => mediaCard(i)).join('') || empty(); })
  .catch(() => { box.innerHTML = empty('Catalogue indisponible pour le moment.'); });
box.addEventListener('click', (e) => { if (e.target.closest('.card')) location.href = '/inscription'; });
