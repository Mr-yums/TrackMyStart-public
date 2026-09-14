// [Sol] Administration authentifiée, révision et CSRF ; aucun HTML publicitaire libre.
import {api} from './api.js';
const form=document.querySelector('#advertisingForm'),status=document.querySelector('#advertisingStatus');
let revision,config;
async function load(){
 try{
  const data=await api.get('/api/admin/advertising');({revision,config}=data);
  for(const field of ['enabled','interstitial'])form.elements[field].checked=config[field];
  for(const field of ['title','description','sponsor','image_url','target_url'])form.elements[field].value=config.campaign[field]||'';
  for(const field of ['starts_at','ends_at'])form.elements[field].value=config.campaign[field]?new Date(config.campaign[field]).toISOString().slice(0,16):'';
  form.querySelectorAll('[name=placement]').forEach(i=>i.checked=(config.campaign.placements||[]).includes(i.value));
  form.hidden=false;status.textContent='Campagne directe : les statistiques de facturation sont gérées avec votre annonceur.';
 }catch(error){status.textContent=error.message;}
}
async function save(values){
 form.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='Enregistrement…';
 try{const data=await api.put('/api/admin/advertising',{config:values,revision});({revision,config}=data);status.textContent=config.enabled?'Campagne enregistrée. Diffusion selon ses dates et ses emplacements.':'Toute diffusion est désactivée.';form.elements.enabled.checked=config.enabled;}
 catch(error){status.textContent=error.message;}
 finally{form.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
form.addEventListener('submit',event=>{
 event.preventDefault();const campaign={};for(const field of ['title','description','sponsor','image_url','target_url'])campaign[field]=form.elements[field].value.trim();
 for(const field of ['starts_at','ends_at'])campaign[field]=form.elements[field].value+':00Z';
 campaign.placements=[...form.querySelectorAll('[name=placement]:checked')].map(i=>i.value);
 save({enabled:form.elements.enabled.checked,interstitial:form.elements.interstitial.checked,campaign});
});
document.querySelector('#advertisingOff').addEventListener('click',()=>save({...config,enabled:false}));
load();
