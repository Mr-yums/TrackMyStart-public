// [Sol] Liseuse paginée : texte existant intégralement conservé, sans récupération externe.
const original = document.querySelector('.reader-body');
const header = document.querySelector('.reader-header');
if (original && header && typeof HTMLDialogElement !== 'undefined') {
  const open = document.createElement('button');
  open.type='button';open.className='reading-room-open';open.textContent='Ouvrir la liseuse · lecture par pages';
  open.setAttribute('aria-haspopup','dialog');header.append(open);
  const room=document.createElement('dialog');room.className='reading-room';room.setAttribute('aria-labelledby','readingRoomTitle');
  room.innerHTML=`<header class="reading-room-head"><div><p class="eyebrow">Le temps de lire</p><h2 id="readingRoomTitle"></h2><p class="reading-room-kind"></p></div><button type="button" class="reading-room-close" aria-label="Fermer la liseuse">✕</button></header>
    <div class="reading-room-tools"><div class="reading-room-type" role="group" aria-label="Taille du texte"><button type="button" data-type="-1" aria-label="Réduire le texte">A−</button><button type="button" data-type="1" aria-label="Agrandir le texte">A+</button></div><a class="reading-room-source" target="_blank" rel="noopener noreferrer">Vérifier la source ↗</a></div>
    <div class="reading-room-paper" tabindex="0" role="region" aria-label="Texte de la lecture"><article class="reading-room-text"></article></div>
    <footer class="reading-room-footer"><div class="reading-room-progress" aria-hidden="true"><span></span></div><nav aria-label="Pages de la lecture"><button type="button" data-page="-1" aria-label="Page précédente">← <span>Précédente</span></button><span class="reading-room-position" role="status" aria-live="polite"></span><button type="button" data-page="1" aria-label="Page suivante"><span>Suivante</span> →</button></nav><button type="button" class="reading-room-discover">Choisir un autre article</button></footer>`;
  room.querySelector('h2').textContent=header.querySelector('h1').textContent;
  room.querySelector('.reading-room-kind').textContent=header.querySelector('.reader-status')?.textContent || '';
  const source=document.querySelector('.reader-source a');
  const sourceLink=room.querySelector('.reading-room-source');
  if(source) sourceLink.href=source.href;else sourceLink.hidden=true;
  const paper=room.querySelector('.reading-room-paper'), text=room.querySelector('.reading-room-text');
  // DOM déjà échappé par les templates ; pas d'injection d'HTML de média.
  for(const child of original.childNodes)text.append(child.cloneNode(true));
  text.querySelectorAll('[id]').forEach(node=>node.removeAttribute('id'));
  document.body.append(room);
  let index=0, pages=1, size=20, frame=0;
  const previous=room.querySelector('[data-page="-1"]'),next=room.querySelector('[data-page="1"]');
  function render() {
    paper.scrollLeft=index*(paper.clientWidth+64);
    previous.disabled=index===0;next.disabled=index>=pages-1;
    room.querySelector('.reading-room-position').textContent=`Page ${index+1} sur ${pages}`;
    room.querySelector('.reading-room-progress span').style.width=`${(index+1)/pages*100}%`;
    room.querySelector('[data-type="-1"]').disabled=size<=16;
    room.querySelector('[data-type="1"]').disabled=size>=26;
  }
  function layout() {
    if(!room.open)return;
    const progress=pages>1?index/pages:0;
    text.style.fontSize=`${size}px`;
    paper.scrollLeft=0;
    pages=Math.max(1,Math.round((text.scrollWidth+64)/(paper.clientWidth+64)));
    index=Math.min(pages-1,Math.floor(progress*pages));render();
  }
  function turn(direction) {
    index=Math.min(pages-1,Math.max(0,index+direction));render();
    if(!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      text.getAnimations().forEach(animation=>animation.cancel());
      text.animate([{opacity:.45},{opacity:1}],{duration:320,easing:'ease-out'});
    }
  }
  open.addEventListener('click',()=>{room.showModal();document.body.classList.add('reading-room-active');layout();room.querySelector('.reading-room-close').focus();});
  room.querySelector('.reading-room-close').addEventListener('click',()=>room.close());
  room.addEventListener('close',()=>{document.body.classList.remove('reading-room-active');open.focus({preventScroll:true});});
  room.querySelectorAll('[data-page]').forEach(button=>button.addEventListener('click',()=>turn(Number(button.dataset.page))));
  room.querySelectorAll('[data-type]').forEach(button=>button.addEventListener('click',()=>{size=Math.min(26,Math.max(16,size+Number(button.dataset.type)*2));layout();}));
  room.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey)return;
    if(['ArrowRight','PageDown','ArrowLeft','PageUp'].includes(event.key)){event.preventDefault();turn(['ArrowRight','PageDown'].includes(event.key)?1:-1);}
  });
  let touch=null;
  paper.addEventListener('pointerdown',event=>{if(event.pointerType==='touch')touch={x:event.clientX,y:event.clientY};});
  paper.addEventListener('pointerup',event=>{if(!touch)return;const dx=event.clientX-touch.x,dy=event.clientY-touch.y;touch=null;if(Math.abs(dx)>50&&Math.abs(dx)>Math.abs(dy)*1.5)turn(dx<0?1:-1);});
  paper.addEventListener('pointercancel',()=>touch=null);
  room.querySelector('.reading-room-discover').addEventListener('click',()=>{room.close();const target=document.querySelector('[data-reader-suggestions]');if(target){target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});target.querySelector('[data-reader-track]')?.focus({preventScroll:true});}});
  new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(layout);}).observe(paper);
  document.fonts.ready.then(()=>{if(room.open)layout();});
}
