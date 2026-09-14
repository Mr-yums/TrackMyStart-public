// [Sol] Carrousel de presse vivant : pagination, lecture interne et retours explicites.
import { api } from './api.js';
import { esc } from './ui.js';
const host = document.querySelector('[data-reader-suggestions]');
if (host) {
  const context = JSON.parse(host.dataset.context), track = host.querySelector('[data-reader-track]');
  const status = host.querySelector('[data-reader-status]'), more = host.querySelector('[data-reader-more]');
  const previous = host.querySelector('[data-reader-prev]'), next = host.querySelector('[data-reader-next]');
  const refresh = host.querySelector('[data-reader-refresh]');
  let cursor = null, loading = false, hasMore = true, changed = false;
  const seen = new Set(), tokens = new Map();
  const position = host.querySelector('[data-reader-position]');
  let pageSize = 4;
  const pageIndex = () => Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
  function arrange() {
    const cards = [...track.querySelectorAll('.reader-suggestion')];
    const anchor = pageIndex() * pageSize;
    pageSize = track.clientWidth >= 960 ? 4 : track.clientWidth >= 540 ? 2 : 1;
    const pages = document.createDocumentFragment();
    for (let i=0; i<cards.length; i+=pageSize) {
      const group=document.createElement('div');group.className='reader-discovery-page';
      group.style.setProperty('--reader-columns',pageSize);
      cards.slice(i,i+pageSize).forEach(card=>group.append(card));pages.append(group);
    }
    track.replaceChildren(pages);
    track.scrollTo({left:Math.floor(anchor/pageSize)*track.clientWidth,behavior:'instant'});
    controls();
  }
  function controls() {
    const index=pageIndex(), pages=track.children.length;
    previous.disabled = index===0;
    next.disabled = loading || (index>=pages-1 && (!hasMore || changed));
    more.disabled = next.disabled;
    more.textContent = loading ? 'Recherche en cours…' : next.disabled ? 'Fin de la sélection' : 'Découvrir la suite →';
    position.textContent = pages ? `${index*pageSize+1}–${Math.min((index+1)*pageSize,track.querySelectorAll('.reader-suggestion').length)} · articles` : '';
    [...track.children].forEach((group,i)=>{group.inert=i!==index;});
    refresh.disabled = loading;
  }
  async function load(reset=false) {
    if (loading || (!reset && (!hasMore || changed))) return;
    loading=true;controls();
    try {
      const response = await api.post('/api/reader/suggestions',{context,cursor:reset?null:cursor});
      if (response.changed) { changed=true;hasMore=false;status.textContent='Les sources ont évolué. Actualisez la sélection pour découvrir les nouveautés.';return; }
      if (reset) { track.replaceChildren();seen.clear();tokens.clear();track.scrollLeft=0;changed=false; }
      for (const item of response.items) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);if(item.feedback_token)tokens.set(item.id,item.feedback_token);
        const card=document.createElement('article');card.className='reader-suggestion';card.dataset.storyTheme=item.theme;card.dataset.articleId=item.id;
        card.innerHTML=`<a class="reader-suggestion-link" href="${esc(item.url)}"><div class="reader-suggestion-visual">${item.image?`<img src="${esc(item.image)}" loading="lazy" alt="" referrerpolicy="no-referrer">`:''}<span class="reader-suggestion-placeholder" ${item.image?'hidden':''}><b aria-hidden="true">✦</b><small>${esc(item.source)}</small></span></div><div class="reader-suggestion-copy"><span class="reader-suggestion-source">${esc(item.source)}</span><h3>${esc(item.title)}</h3><p>${esc(item.reason)}</p><span class="reader-suggestion-read">Lire l’article <span aria-hidden="true">→</span></span></div></a>${item.feedback_token?`<div class="reader-suggestion-feedback" aria-label="Votre avis"><button type="button" data-reader-feedback="more">Plus comme ça</button><button type="button" data-reader-feedback="less">Moins</button><button type="button" data-reader-feedback="hide">Masquer</button></div>`:''}`;
        card.querySelector('img')?.addEventListener('error',event=>{event.target.remove();card.querySelector('.reader-suggestion-placeholder').hidden=false;},{once:true});
        track.append(card);
      }
      cursor=response.next_cursor;hasMore=!!cursor;arrange();
      status.textContent=seen.size?'Une sélection pour vous · à parcourir à votre rythme':'Aucun article disponible avec vos choix actuels. Vous pouvez actualiser ou ajuster vos préférences dans le dashboard.';
    } catch(error) { status.textContent=`${error.message || 'Sources momentanément indisponibles.'} Vous pouvez réessayer.`; }
    finally {loading=false;controls();}
  }
  const movement = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth';
  async function move(direction) {
    let target=pageIndex()+direction;
    if(target>=track.children.length)await load();
    target=Math.max(0,Math.min(target,track.children.length-1));
    track.scrollTo({left:target*track.clientWidth,behavior:movement()});
    controls();
  }
  previous.addEventListener('click',()=>move(-1));
  next.addEventListener('click',()=>move(1));
  more.addEventListener('click',()=>move(1));refresh.addEventListener('click',()=>load(true));
  track.addEventListener('scroll',controls,{passive:true});
  track.addEventListener('keydown',event=>{if(event.target!==track)return;if(event.key==='ArrowRight'){event.preventDefault();next.click();}if(event.key==='ArrowLeft'){event.preventDefault();previous.click();}});
  track.addEventListener('click',async event=>{
    const button=event.target.closest('[data-reader-feedback]');if(!button)return;
    const card=button.closest('[data-article-id]'),token=tokens.get(card.dataset.articleId);
    card.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      await api.post('/api/me/recommendations/feedback',{token,action:button.dataset.readerFeedback});
      if(button.dataset.readerFeedback==='hide'){card.remove();arrange();track.focus({preventScroll:true});}
      else {card.querySelectorAll('[data-reader-feedback]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}
      // Préférences modifiées : garder la rangée stable, recalculer à la prochaine actualisation.
      changed=true;hasMore=false;status.textContent='Avis enregistré. Actualisez pour adapter les propositions.';
    } catch(error){status.textContent=error.message;}
    finally{card.querySelectorAll('button').forEach(b=>b.disabled=false);controls();}
  });
  let measuredWidth=0;
  if ('ResizeObserver' in window)new ResizeObserver(()=>{if(track.clientWidth!==measuredWidth){measuredWidth=track.clientWidth;arrange();}}).observe(track);
  load();
}
