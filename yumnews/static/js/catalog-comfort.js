// [Sol] Filtres persistants, statuts réversibles et présentation du bénéfice Premium.
import {api} from './api.js';
import {esc,toast} from './ui.js';
export class CatalogComfort {
  constructor(premium,onChange) { this.premium=premium;this.onChange=onChange;this.data=null;this.countries={};this.historyLimit=30; }
  async init() {
    try { const response=await api.get('/api/me/catalog');this.data=response.catalog;this.countries=response.countries;this.render(); }
    catch(error) { document.querySelectorAll('[data-catalog-filters]').forEach(host=>{host.replaceChildren();const b=document.createElement('button');b.className='btn btn-ghost';b.textContent='Réessayer le chargement des filtres';b.onclick=()=>this.init();host.append(b);}); }
  }
  render() {
    document.querySelectorAll('[data-catalog-filters]').forEach(host=>{
      const kind=host.dataset.catalogFilters,f=this.data.filters[kind],premium=this.premium();
      host.innerHTML=`<details class="catalog-comfort"><summary><span>✦ Affiner mes découvertes</span><small>${premium?'Vos filtres sont mémorisés':'Filtres avancés · Premium'}</small></summary><form><p class="muted small">Pays de production, durée ${kind==='tv'?'d’un épisode':'du film'} et votes TMDB. Les filtres affinent la sélection de la rubrique actuelle.</p><fieldset ${premium?'':'disabled'}><div class="comfort-fields"><label>Pays de production<select name="country" class="select"><option value="">Tous les pays</option>${Object.entries(this.countries).map(([code,name])=>`<option value="${code}" ${f.country===code?'selected':''}>${esc(name)}</option>`).join('')}</select></label><label>Durée minimale (min)<input class="input" name="runtime_min" type="number" min="0" max="1000" value="${f.runtime_min??''}" placeholder="Libre"></label><label>Durée maximale (min)<input class="input" name="runtime_max" type="number" min="0" max="1000" value="${f.runtime_max??''}" placeholder="Libre"></label><label>Votes TMDB minimum<input class="input" name="votes_min" type="number" min="0" max="100000000" value="${f.votes_min??''}" placeholder="Aucun minimum"></label></div><div class="comfort-checks"><label><input type="checkbox" name="hide_seen" ${f.hide_seen?'checked':''}> Masquer les titres vus</label><label><input type="checkbox" name="hide_disliked" ${f.hide_disliked?'checked':''}> Masquer les titres qui ne m’intéressent pas</label></div></fieldset>${premium?'<div class="comfort-actions"><button type="submit" class="btn btn-primary btn-sm">Appliquer mes filtres</button><button type="button" data-clear class="btn btn-ghost btn-sm">Réinitialiser</button></div>':'<div class="comfort-upsell"><p>Trouvez votre prochaine découverte plus facilement : filtres mémorisés, catalogue épuré et navigation sans publicité.</p><a href="/tarifs" class="btn btn-primary btn-sm">Découvrir Premium</a></div>'}<p role="status" data-comfort-status></p></form></details><p class="muted small" data-filter-count></p>`;
      const form=host.querySelector('form');form.addEventListener('submit',event=>{event.preventDefault();this.save(kind,form);});
      form.querySelector('[data-clear]')?.addEventListener('click',()=>{form.querySelectorAll('input').forEach(i=>{i.value='';i.checked=false;});form.querySelector('select').value='';this.save(kind,form);});
    });this.history();
  }
  async save(kind,form) {
    const values={country:form.elements.country.value};
    for(const name of ['runtime_min','runtime_max','votes_min'])values[name]=form.elements[name].value===''?null:Number(form.elements[name].value);
    for(const name of ['hide_seen','hide_disliked'])values[name]=form.elements[name].checked;
    const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);form.querySelector('fieldset').disabled=true;
    const status=form.querySelector('[data-comfort-status]');status.textContent='Enregistrement…';
    try {this.data.filters[kind]=(await api.put(`/api/me/catalog/filters/${kind}`,values)).filters;status.textContent='Filtres enregistrés.';this.onChange();}
    catch(error) {status.textContent=error.message;}
    finally{buttons.forEach(b=>b.disabled=false);form.querySelector('fieldset').disabled=!this.premium();}
  }
  buttons(item) {
    if(!this.data)return '';
    const status=this.data.titles[`${item.media_type}:${item.id}`]||{};
    return `<div class="title-status-actions" data-title-status data-kind="${esc(item.media_type)}" data-id="${esc(item.id)}" data-title="${esc(item.title)}"><button type="button" class="btn btn-ghost btn-sm" data-status="seen" aria-pressed="${!!status.seen}">${status.seen?'✓ Vu':'Marquer comme vu'}</button><button type="button" class="btn btn-ghost btn-sm" data-status="disliked" aria-pressed="${!!status.disliked}">${status.disliked?'✓ Pas intéressé':'Pas intéressé'}</button><span role="status"></span></div>`;
  }
  async mark(host,field) {
    const key=`${host.dataset.kind}:${host.dataset.id}`,current=this.data.titles[key]||{};
    const values=field==='reset'?{seen:false,disliked:false}:{[field]:!current[field],title:host.dataset.title};
    host.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      const response=await api.put(`/api/me/catalog/titles/${host.dataset.kind}/${host.dataset.id}`,values);
      if(response.status.seen||response.status.disliked)this.data.titles[key]=response.status;else delete this.data.titles[key];
      if(field!=='reset')host.outerHTML=this.buttons({media_type:host.dataset.kind,id:host.dataset.id,title:host.dataset.title});
      this.history();this.onChange();toast('Votre choix est enregistré.');
    }catch(error){toast(error.message,'error');host.querySelectorAll('button').forEach(b=>b.disabled=false);}
  }
  history() {
    const host=document.querySelector('[data-title-history]');if(!host||!this.data)return;
    const expanded=host.querySelector('details')?.open;
    const entries=Object.entries(this.data.titles);
    host.innerHTML=`<details class="catalog-comfort"><summary>Mes titres vus et écartés <small>${entries.length} titre(s)</small></summary><div class="comfort-history">${entries.length?entries.slice(0,this.historyLimit).map(([key,s])=>{const [kind,id]=key.split(':');return `<div data-title-status data-kind="${kind}" data-id="${id}" data-title="${esc(s.title||'')}" class="comfort-history-row"><span>${esc(s.title||key)}<small>${[s.seen?'Vu':'',s.disliked?'Pas intéressé':''].filter(Boolean).join(' · ')}</small></span><button type="button" data-status="reset" class="btn btn-ghost btn-sm">Retirer les statuts</button></div>`}).join(''):'<p class="muted">Marquez un film ou une série depuis sa fiche. Vos choix resteront modifiables ici.</p>'}${entries.length>this.historyLimit?'<button type="button" class="btn btn-ghost" data-history-more>Afficher la suite</button>':''}</div></details>`;
    if(expanded)host.querySelector('details').open=true;
    host.querySelector('[data-history-more]')?.addEventListener('click',()=>{this.historyLimit+=30;this.history();host.querySelector('details').open=true;});
  }
}
