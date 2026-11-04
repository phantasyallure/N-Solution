(function(){const P=location.pathname.replace(/\/$/,"")||"/",N=[["/","Accueil"],["/about","À propos"],["/contact","Contact"],["/privacy","Confidentialité"]];
const h=document.getElementById("hdr"),f=document.getElementById("ftr");
if(h)h.outerHTML=`<header class="hdr"><a class="brand" href="/"><img src="/static/emblem.png" alt="" onerror="this.remove()"><b>Nardjis</b></a><nav>${N.map(([u,l])=>`<a href="${u}" class="${P===u?"on":""}">${l}</a>`).join("")}</nav></header>`;
if(f)f.outerHTML=`<footer><span>© ${new Date().getFullYear()} Nardjis Solutions</span><span class="sp"></span><a href="/about">À propos</a><a href="/contact">Contact</a><a href="/privacy">Confidentialité</a></footer>`})();
