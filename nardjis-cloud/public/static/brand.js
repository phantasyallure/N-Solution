/* Platform name: one source of truth (Administration > Général > Nom de la plateforme).
   Every page loads this file; it swaps the default name "Nardjis" for the saved one in all texts. */
(function(){
const SRC="Nardjis",KEY="nj_brand",RX=/Nardjis/g,SKIP={SCRIPT:1,STYLE:1,NOSCRIPT:1};
let name=SRC;try{name=localStorage.getItem(KEY)||SRC}catch(e){}
const B=window.BRAND={name,
  async save(n){
    const r=await fetch("/api?op=brand_set",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(j.error||"error");
    try{localStorage.setItem(KEY,j.name)}catch(e){}
    return j.name}};
const ATTRS=["title","alt","placeholder","aria-label"];
function fix(n){
  if(name===SRC)return;
  if(n.nodeType===3){if(n.nodeValue.indexOf(SRC)>-1&&!(n.parentNode&&SKIP[n.parentNode.nodeName]))n.nodeValue=n.nodeValue.replace(RX,name);return}
  if(n.nodeType!==1||SKIP[n.nodeName])return;
  for(const a of ATTRS){const v=n.getAttribute&&n.getAttribute(a);if(v&&v.indexOf(SRC)>-1)n.setAttribute(a,v.replace(RX,name))}
  for(let c=n.firstChild;c;c=c.nextSibling)fix(c)}
const mo=new MutationObserver(ms=>{mo.disconnect();for(const m of ms){if(m.type==="characterData")fix(m.target);else m.addedNodes.forEach(fix)}run()});
function run(){mo.observe(document.documentElement,{childList:true,subtree:true,characterData:true})}
function start(){if(name===SRC)return;fix(document.documentElement);mo.disconnect();run()}
start();
if(name!==SRC)document.addEventListener("DOMContentLoaded",()=>{mo.disconnect();fix(document.documentElement);run()});
fetch("/api?op=brand").then(r=>r.ok?r.json():null).then(j=>{
  if(!j||!j.name)return;
  try{localStorage.setItem(KEY,j.name)}catch(e){}
  B.name=j.name;
  if(j.name!==name){
    if(name!==SRC){try{if(sessionStorage.getItem("njr")!==j.name){sessionStorage.setItem("njr",j.name);location.reload()}}catch(e){}return}
    name=j.name;mo.disconnect();fix(document.documentElement);run()}
  window.dispatchEvent(new CustomEvent("brand",{detail:j.name}))}).catch(()=>{});
})();
