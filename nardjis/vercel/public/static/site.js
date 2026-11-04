(function(){const P=location.pathname.replace(/\/$/,"")||"/",N=[["/","Accueil"],["/#tarifs","Tarifs"],["/about","À propos"],["/contact","Contact"],["/privacy","Confidentialité"]];
const h=document.getElementById("hdr"),f=document.getElementById("ftr");
const BURGER='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',CLOSE='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
if(h){h.outerHTML=`<header class="hdr"><button class="menu-btn" id="mb" aria-label="Menu" aria-expanded="false" aria-controls="dr">${BURGER}</button><a class="brand" href="/"><img src="/static/emblem.png" alt="" onerror="this.remove()"><b>Nardjis</b></a></header>
<div class="scrim" id="sc"></div><aside class="drawer" id="dr" aria-hidden="true"><div class="drawer-top"><a class="brand" href="/"><img src="/static/emblem.png" alt="" onerror="this.remove()"><b>Nardjis</b></a><button class="menu-btn" id="mx" aria-label="Fermer">${CLOSE}</button></div><nav>${N.map(([u,l])=>`<a href="${u}" class="${P===u?"on":""}">${l}</a>`).join("")}</nav><small>© ${new Date().getFullYear()} Nardjis Solutions</small></aside>`;
const dr=document.getElementById("dr"),sc=document.getElementById("sc"),mb=document.getElementById("mb");
const set=o=>{dr.classList.toggle("open",o);sc.classList.toggle("open",o);mb.setAttribute("aria-expanded",o);dr.setAttribute("aria-hidden",!o);document.body.style.overflow=o?"hidden":""};
mb.onclick=()=>set(true);document.getElementById("mx").onclick=sc.onclick=()=>set(false);
dr.querySelectorAll("nav a").forEach(a=>a.addEventListener("click",()=>set(false)));
addEventListener("keydown",e=>{if(e.key==="Escape")set(false)})}
if(f)f.outerHTML=`<footer class="ft"><div class="ft-in"><div class="ft-brand"><a class="brand" href="/"><img src="/static/emblem.png" alt="" onerror="this.remove()"><b>Nardjis</b></a><p>Suivi de salle par caméra pour restaurants, cafés et cafétérias.</p><a class="ft-mail" href="mailto:support@nardjis.com">support@nardjis.com</a></div>
<nav class="ft-col" aria-label="Plateforme"><h3>Plateforme</h3><a href="/">Accueil</a><a href="/#tarifs">Tarifs</a><a href="/#signup">Créer un compte</a></nav>
<nav class="ft-col" aria-label="Société"><h3>Société</h3><a href="/about">À propos</a><a href="/contact">Contact</a></nav>
<nav class="ft-col" aria-label="Légal"><h3>Légal</h3><a href="/privacy">Confidentialité</a></nav></div>
<div class="ft-bar"><span>© ${new Date().getFullYear()} Nardjis Solutions</span><span>Visages floutés · aucune donnée vendue</span></div></footer>`})();
