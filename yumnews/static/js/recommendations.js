// [Sol] Fil explicable, avis réversibles ; aucun suivi passif des lectures.
import { api } from './api.js';
import { esc, mediaCard, empty, toast } from './ui.js';

export function recommendationsPanel(host) {
  let generation = 0, data, busy = false, savedSettings;
  const grid = host.querySelector('[data-rec-grid]');
  const mode = host.querySelector('[data-rec-mode]');
  const settings = host.querySelector('[data-rec-settings]');
  // [Sol] Un chargement propre aux réglages, indépendant des appels au catalogue.
  function renderSettings(result) {
    savedSettings = result;
    const prefs = result.settings, count = Object.keys(prefs.feedback).length;
    settings.innerHTML = `<div class="rec-settings-intro"><p class="eyebrow">Vous gardez la main</p><h3>Un fil à votre mesure.</h3><p>Vos stars suivies passent en premier. Vos avis affinent les sujets ; une petite place reste à la découverte.</p></div>
      <label class="rec-personal-toggle"><span><strong>Personnaliser mon fil</strong><small>${prefs.enabled ? 'Actif · vos suivis et vos avis guident les suggestions.' : 'Désactivé · les contenus sont rangés par date.'}</small></span><input type="checkbox" role="switch" data-rec-enabled ${prefs.enabled?'checked':''}><span class="rec-switch-track" aria-hidden="true"></span></label>
      <div class="rec-settings-columns"><fieldset class="rec-topics"><legend>Ce que vous préférez éviter</legend><p>Choisissez les sujets à masquer. Un second clic les réaffiche.</p><div class="rec-topic-list">${Object.entries(result.topics).map(([key,label])=>`<label class="rec-topic"><input type="checkbox" data-rec-topic="${key}" ${prefs.muted.includes(key)?'checked':''}><span><b aria-hidden="true">${prefs.muted.includes(key)?'−':'+'}</b>${esc(label)}<small>${prefs.muted.includes(key)?'Masqué':'Visible'}</small></span></label>`).join('')}</div></fieldset>
      <section class="rec-feedback"><div class="rec-feedback-heading"><h4>Vos avis</h4><span class="rec-count">${count}</span></div>${count ? `<ul>${Object.entries(prefs.feedback).map(([id,entry])=>`<li><div><span class="rec-feedback-badge">${esc({more:'Plus comme ça',less:'Moins comme ça',hide:'Contenu masqué'}[entry.action])}</span><p>${esc(entry.title)}</p></div><button type="button" class="link-btn" data-rec-remove="${esc(id)}" aria-label="Annuler l’avis sur ${esc(entry.title)}">Annuler</button></li>`).join('')}</ul>` : `<div class="rec-feedback-empty"><span aria-hidden="true">♡</span><strong>Votre fil apprend de vos choix</strong><p>Sur une suggestion, utilisez « Plus comme ça » ou « Moins comme ça ». Vous pourrez retrouver et annuler vos avis ici.</p></div>`}</section></div>
      <div class="rec-settings-footer"><p><strong>Vous pouvez changer d’avis.</strong><br>Aucun suivi automatique de vos lectures. Réinitialiser conserve vos stars suivies et votre liste.</p><button type="button" class="btn btn-ghost btn-sm" data-rec-reset>Réinitialiser mon fil</button></div>`;
  }
  async function loadSettings() {
    try { renderSettings(await api.get('/api/me/recommendations/settings')); }
    catch (error) {
      if (!savedSettings) settings.innerHTML = `<div class="rec-settings-loading"><p>Vos réglages n’ont pas pu être chargés.</p><button type="button" class="btn btn-ghost" data-rec-retry>Réessayer</button></div>`;
      throw error;
    }
  }
  loadSettings().catch(()=>{});
  const disclosure = settings.closest('details');
  let disclosureAnimation;
  disclosure.querySelector('summary').addEventListener('click', event => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    event.preventDefault();
    if (disclosureAnimation) return;
    const closing = disclosure.open;
    if (!closing) disclosure.open = true;
    const height = settings.getBoundingClientRect().height;
    settings.style.overflow = 'hidden';
    disclosureAnimation = settings.animate({height: closing ? [`${height}px`, '0px'] : ['0px', `${height}px`]}, {duration:420,easing:'cubic-bezier(.4,0,.2,1)'});
    disclosureAnimation.onfinish = () => {
      if (closing) disclosure.open = false;
      settings.style.overflow = '';
      disclosureAnimation = null;
    };
  });
  async function refresh() {
    const request = ++generation;
    host.setAttribute('aria-busy', 'true');
    try {
      const result = await api.get('/api/me/recommendations?mode=' + mode.value);
      if (request !== generation) return;
      data = result;
      host.querySelector('[data-rec-hint]').textContent = !data.settings.enabled ? 'Personnalisation désactivée : ordre par date.' : data.items.some(i => i.people.length)
        ? 'Priorité à vos stars suivies. Une petite part de découverte, quand le contenu le permet.'
        : 'Sélection éditoriale : aucun projet ou article récent lié à vos suivis dans les contenus disponibles.';
      host.querySelector('[data-rec-lock]').textContent = data.locked ? 'Projets des stars : aperçu Découverte. Le fil complet est inclus dans Premium.' : '';
      grid.innerHTML = data.items.map((item, index) => {
        const content = item.kind === 'project' ? mediaCard(item.media, {showDate:true, inWatchlist:item.in_watchlist}) : `<h3><a href="${esc(item.link)}">${esc(item.title)}</a></h3><p>${esc(item.description)}</p><a class="landing-text-link" href="${esc(item.link)}">Lire la brève →</a>`;
        return `<article class="recommendation-item"><p class="recommendation-reason">${esc(item.reason)}</p>${content}<p class="muted small">${esc(item.source)} · ${esc(item.status)}</p><div class="recommendation-actions" aria-label="Votre avis sur ${esc(item.title)}">${[['more','Plus comme ça'],['less','Moins comme ça'],['hide','Masquer']].map(([action,label])=>`<button class="btn btn-ghost btn-sm" type="button" data-rec-action="${action}" data-index="${index}" aria-pressed="${item.feedback===action}">${label}</button>`).join('')}</div></article>`;
      }).join('') || empty('Aucun contenu correspondant pour le moment. Vos réglages restent disponibles ci-dessous.');

    } catch (error) {
      if (request === generation) {
        grid.innerHTML = empty('Fil momentanément indisponible.');
        toast(error.message, 'error');
      }
    } finally { if (request === generation) host.removeAttribute('aria-busy'); }
  }
  async function save(action) {
    if (busy) return;
    const active = document.activeElement;
    const focusKey = active?.hasAttribute('data-rec-enabled') ? '[data-rec-enabled]' : active?.hasAttribute('data-rec-topic') ? `[data-rec-topic="${CSS.escape(active.dataset.recTopic)}"]` : active?.hasAttribute('data-rec-reset') ? '[data-rec-reset]' : null;
    busy = true;
    const status = host.querySelector('[data-rec-status]');
    status.textContent = 'Enregistrement de votre choix…';
    settings.setAttribute('aria-busy','true');
    host.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
    try {
      await action(); await loadSettings();
      status.textContent = 'Choix enregistré. Votre fil se met à jour.';
      refresh();
    } catch (error) {
      if (savedSettings) renderSettings(savedSettings);
      status.textContent = 'Enregistrement non confirmé. Réessayez ou rechargez vos réglages.';
      toast(error.message, 'error');
    } finally {
      busy=false; settings.removeAttribute('aria-busy');
      host.querySelectorAll('button,input,select').forEach(el=>el.disabled=false);
      if (focusKey) settings.querySelector(focusKey)?.focus({preventScroll:true});
    }
  }
  mode.addEventListener('change',refresh);
  host.addEventListener('click',event=>{
    const button = event.target.closest('button');
    if (!button || busy) return;
    if (button.dataset.recAction) {
      const item = data.items[Number(button.dataset.index)];
      save(()=>api.post('/api/me/recommendations/feedback',{token:item.token,action:button.dataset.recAction}));
    } else if (button.hasAttribute('data-rec-remove')) {
      save(()=>api.saveRecommendationSettings({remove:button.dataset.recRemove}));
    } else if (button.hasAttribute('data-rec-reset')) {
      save(()=>api.saveRecommendationSettings({reset:true}));
    } else if (button.hasAttribute('data-rec-retry')) { loadSettings().catch(()=>{});
    } else if (button.hasAttribute('data-rec-refresh')) { refresh(); }
  });
  settings.addEventListener('change',event=>{
    if (event.target.hasAttribute('data-rec-enabled')) save(()=>api.saveRecommendationSettings({enabled:event.target.checked}));
    if (event.target.hasAttribute('data-rec-topic')) {
      const muted=[...settings.querySelectorAll('[data-rec-topic]:checked')].map(el=>el.dataset.recTopic);
      save(()=>api.saveRecommendationSettings({muted}));
    }
  });
  return {refresh};
}
