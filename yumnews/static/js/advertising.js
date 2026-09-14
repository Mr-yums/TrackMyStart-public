// [Sol] Campagnes directes uniquement. Aucun SDK tiers, blocage ou revenu simulé.
import {api} from './api.js';
import {esc} from './ui.js';
const premium=()=>window.TRACKMYSTART?.policy?.features?.includes('ad_free');
const creative=c=>`<a class="sponsor-image" href="${esc(c.target_url)}" target="_blank" rel="sponsored noopener noreferrer"><img src="${esc(c.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></a><div class="sponsor-copy"><small>Publicité · ${esc(c.sponsor)}</small><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p><a href="${esc(c.target_url)}" target="_blank" rel="sponsored noopener noreferrer">Découvrir ↗</a></div>`;
async function fill(host) {
 if(premium())return;
 try {
  const {campaign}=await api.get(`/api/ads/${host.dataset.adPlacement}`);if(!campaign)return;
  host.innerHTML=`<div class="sponsor-creative">${creative(campaign)}</div><a class="sponsor-premium" href="/tarifs">Profiter de TrackMyStart sans publicité →</a>`;host.hidden=false;
  host.querySelector('img').addEventListener('error',()=>{host.hidden=true;host.replaceChildren();},{once:true});
 }catch{/* L'absence de campagne ou une panne ne gêne jamais le contenu. */}
}
// IntersectionObserver évite de charger les campagnes des onglets non consultés.
document.querySelectorAll('[data-ad-placement]').forEach(host=>{
 // L'ancre est observable, même lorsque son contenu publicitaire est masqué.
 const marker=document.createElement('span');marker.className='sponsor-marker';host.before(marker);
 const one=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){one.disconnect();fill(host);}});one.observe(marker);
});
let pending=false;
export async function afterActor() {
 if(premium()||pending||document.querySelector('dialog[open]'))return;
 let state;
 try {
  state=JSON.parse(sessionStorage.getItem('sol-ad-break')||'{"actors":0,"shown":0,"last":0}');
  state.actors+=1;sessionStorage.setItem('sol-ad-break',JSON.stringify(state));
  if(state.actors<6||state.shown>=2||Date.now()-state.last<600000)return;
  state.actors=0;sessionStorage.setItem('sol-ad-break',JSON.stringify(state));
 }catch{return;}
 pending=true;
 try {
  const {campaign}=await api.get('/api/ads/actor_break');
  if(!campaign||document.querySelector('#detail.open, dialog[open]')||document.hidden)return;
  const dialog=document.createElement('dialog');dialog.className='sponsor-break';dialog.setAttribute('aria-label','Publicité');
  dialog.innerHTML=`<button type="button" class="sponsor-close">Continuer maintenant ✕</button><div class="sponsor-creative">${creative(campaign)}</div><p class="muted small">Reprise automatique dans <span data-countdown>5</span> secondes</p><a href="/tarifs">Passer Premium pour naviguer sans publicité</a>`;
  document.body.append(dialog);dialog.showModal();dialog.querySelector('button').focus();
  // Comptage de confort dans cet onglet, pas un compteur de facturation publicitaire.
  state.actors=0;state.shown+=1;state.last=Date.now();sessionStorage.setItem('sol-ad-break',JSON.stringify(state));
  const started=Date.now();const timer=setInterval(()=>{const left=Math.max(0,5-Math.floor((Date.now()-started)/1000));dialog.querySelector('[data-countdown]').textContent=left;if(!left)dialog.close();},250);
  dialog.querySelector('button').onclick=()=>dialog.close();
  dialog.querySelector('img').onerror=()=>dialog.close();
  dialog.addEventListener('close',()=>{clearInterval(timer);dialog.remove();},{once:true});
 }catch{/* Ne jamais bloquer une fiche si l'annonce échoue. */}
 finally{pending=false;}
}
