"use strict";
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
const cardTpl = $("#cardTpl");
const chipsEl = $("#chips");

/* browse state: genre slug + format slug, and the list the server sends */
let catalog = {genres: [], formats: []};
const browsing = {tag: "", cat: ""};

function esc(s){return (s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function humanSize(n){if(!n)return"";const u=["B","KB","MB","GB","TB"];let i=0;
  while(n>=1024&&i<u.length-1){n/=1024;i++;}return n.toFixed(1)+" "+u[i];}
function kind(title){
  const t=(title||"").toLowerCase();
  if(/\b(korean|kdrama|drama)\b/.test(t))return"Drama";
  if(/\banime\b|\bs\d+\b|season/.test(t))return"Series";
  if(/\bmovie\b|\b\(\d{4}\b/.test(t))return"Movie";
  return"";
}
function subFor(item){
  const bits=[];
  const k=kind(item.title); if(k)bits.push(k);
  if(item.date)bits.push(item.date.slice(0,4));
  return bits.join(" / ");
}

function cardEl(item){
  const node=cardTpl.content.firstElementChild.cloneNode(true);
  node.href="#/p/"+item.id;
  node.querySelector(".title").textContent=item.title;
  node.querySelector(".sub").textContent=subFor(item);
  const img=node.querySelector("img");
  const ph=node.querySelector(".ph");
  if(item.poster){
    img.loading="lazy"; img.decoding="async"; img.alt=item.title;
    // handlers first: a cached poster can fire load before src is assigned
    img.onload=()=>{img.classList.add("on");ph.style.display="none";};
    img.onerror=()=>{
      // one retry, then fall back to the placeholder
      if(!img.dataset.retried){img.dataset.retried="1";
        setTimeout(()=>{img.src=item.poster+(item.poster.includes("?")?"&":"?")+"r=1";},1200);}
      else{img.remove();}
    };
    img.src=item.poster;
    if(img.complete&&img.naturalWidth){img.onload();}
  }else{
    img.remove();
  }
  return node;
}

function grid(items,emptyMsg){
  const g=document.createElement("div"); g.className="grid";
  if(!items.length){g.remove();}
  items.forEach(it=>g.appendChild(cardEl(it)));
  return g;
}
function section(title,items,emptyMsg){
  const wrap=document.createElement("div");
  const h=document.createElement("div"); h.className="sec-title"; h.textContent=title;
  wrap.appendChild(h);
  if(items&&items.length) wrap.appendChild(grid(items));
  else{const e=document.createElement("div");e.className="state";e.textContent=emptyMsg||"Nothing here yet.";wrap.appendChild(e);}
  return wrap;
}
function spinner(txt){const d=document.createElement("div");d.className="state";
  d.innerHTML='<div class="spinner"></div>'+esc(txt||"Loading...");return d;}

async function getJSON(url){
  const r=await fetch(url); if(!r.ok)throw new Error((await r.json()).error||r.status);
  return r.json();
}

/* Every view bumps the token; a view that finishes after a newer one started
   throws its result away instead of appending a second copy into #view. */
let renderToken=0;
const beginRender=()=>++renderToken;
const stale=t=>t!==renderToken;


/* ---------------- pagination ---------------- */
function pageHref(base,page){
  return page<=1?base:base+"/"+page;
}
function pager(res,base){
  const pages=res.total_pages||0;
  if(pages<=1)return null;
  const bar=document.createElement("div");bar.className="pager";

  const prev=document.createElement("button");prev.className="btn btn-ghost btn-nav";
  prev.textContent="Prev";prev.disabled=res.page<=1;
  prev.onclick=()=>{location.hash=pageHref(base,res.page-1);};

  const info=document.createElement("div");info.className="pager-info";
  info.textContent=`Page ${res.page} of ${pages}`+
                   (res.total?` (${res.total} results)`:"");

  const next=document.createElement("button");next.className="btn btn-ghost btn-nav";
  next.textContent="Next";next.disabled=res.page>=pages;
  next.onclick=()=>{location.hash=pageHref(base,res.page+1);};

  bar.appendChild(prev);bar.appendChild(info);bar.appendChild(next);
  return bar;
}

/* ---------------- genre chips ---------------- */
function chipEl(label,on,onclick,extra){
  const b=document.createElement("button");
  b.type="button";b.className="chip"+(on?" on":"")+(extra?" "+extra:"");
  b.textContent=label;b.onclick=onclick;
  return b;
}

function renderChips(){
  if(!catalog.genres.length)return;      // the row keeps its height meanwhile
  chipsEl.replaceChildren();
  chipsEl.appendChild(chipEl("All",!browsing.tag,()=>{location.hash="#/latest";}));
  catalog.genres.forEach(g=>{
    chipsEl.appendChild(chipEl(g.name,browsing.tag===g.slug,
      ()=>{location.hash="#/g/"+encodeURIComponent(g.slug);}));
  });
  const fmt=catalog.formats.find(f=>f.slug===browsing.cat);
  chipsEl.appendChild(chipEl(fmt?fmt.name:"Format",!!fmt,openFormatSheet,"chip-end"));
  const on=chipsEl.querySelector(".chip.on");
  if(on)on.scrollIntoView({inline:"center",block:"nearest"});
}

function openFormatSheet(){
  closeSheet();
  const wrap=document.createElement("div");wrap.className="sheet-wrap";wrap.id="sheet";
  wrap.onclick=e=>{if(e.target===wrap)closeSheet();};
  const panel=document.createElement("div");panel.className="sheet";

  const head=document.createElement("div");head.className="sec-title";head.textContent="Format";
  panel.appendChild(head);

  const list=document.createElement("div");list.className="sheet-list";
  const pick=slug=>{browsing.cat=slug;closeSheet();renderChips();reloadBrowse();};
  list.appendChild(chipEl("All formats",!browsing.cat,()=>pick("")));
  catalog.formats.forEach(f=>{
    list.appendChild(chipEl(f.name,browsing.cat===f.slug,()=>pick(f.slug)));
  });
  panel.appendChild(list);

  const close=document.createElement("button");
  close.type="button";close.className="btn btn-ghost";close.textContent="Close";
  close.onclick=closeSheet;
  panel.appendChild(close);

  wrap.appendChild(panel);document.body.appendChild(wrap);
}
function closeSheet(){const s=$("#sheet");if(s)s.remove();}

function reloadBrowse(){
  const h=location.hash||"#/";
  const m=h.match(/^#\/g\/([^/]+)(?:\/(\d+))?$/);
  if(m)browse(decodeURIComponent(m[1]),1);
  else if(/^#\/(latest)?(\/?$|\/\d+$)/.test(h)||h==="#/")browse("",1);
}

/* ---------------- home / genre browse ---------------- */
function browseTitle(){
  const g=catalog.genres.find(x=>x.slug===browsing.tag);
  const f=catalog.formats.find(x=>x.slug===browsing.cat);
  if(g&&f)return`${g.name} / ${f.name}`;
  if(g)return g.name;
  if(f)return`New in ${f.name}`;
  return"New uploads";
}

async function home(page=1){
  return browse("",page);
}

async function browse(tag,page=1){
  const t=beginRender();
  browsing.tag=tag||"";
  chipsEl.hidden=false;
  renderChips();
  view.innerHTML="";
  view.appendChild(spinner());
  try{
    const res=await getJSON("/api/browse?tag="+encodeURIComponent(browsing.tag)
                           +"&cat="+encodeURIComponent(browsing.cat)
                           +"&limit=30&page="+page);
    if(stale(t))return;
    view.innerHTML="";
    view.appendChild(section(browseTitle(),res.items,"Nothing here yet."));
    const base=browsing.tag?"#/g/"+encodeURIComponent(browsing.tag):"#/latest";
    const p=pager(res,base);
    if(p)view.appendChild(p);
  }catch(e){
    if(stale(t))return;
    view.innerHTML="";
    view.appendChild(section(browseTitle(),[],"Couldn't load: "+e.message));
  }
}

/* ---------------- search ---------------- */
async function search(q,page=1){
  const t=beginRender();
  view.innerHTML=""; view.appendChild(spinner("Searching..."));
  try{
    const res=await getJSON("/api/search?q="+encodeURIComponent(q)
                           +"&limit=30&page="+page);
    if(stale(t))return;
    view.innerHTML="";
    if(res.items.length){
      // one page: show the count in the header so a short list reads as
      // "that is all of it", not "the pager is broken"
      const head=(res.total_pages||1)<=1
        ?`Results for "${q}" (${res.items.length})`
        :`Results for "${q}"`;
      view.appendChild(section(head,res.items));
      const p=pager(res,"#/s/"+encodeURIComponent(q));
      if(p)view.appendChild(p);
    }else{
      const e=document.createElement("div");e.className="state";
      e.textContent=page>1?`No more results for "${q}".`:`No results for "${q}".`;
      view.appendChild(e);
      const back=document.createElement("a");back.className="back";back.textContent="back to page 1";
      back.href="#/s/"+encodeURIComponent(q);
      if(page>1)view.appendChild(back);
    }
  }catch(e){
    if(stale(t))return;
    view.innerHTML="";
    const d=document.createElement("div");d.className="state";d.textContent="Search failed: "+e.message;
    view.appendChild(d);
  }
}

/* ---------------- detail ---------------- */
function toast(msg,cls){
  let t=$(".toast");
  if(!t){t=document.createElement("div");t.className="toast";document.body.appendChild(t);}
  t.textContent=msg; t.className="toast on "+(cls||"");
  clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove("on"),3500);
}

async function detail(id){
  const t=beginRender();
  view.innerHTML=""; view.appendChild(spinner("Loading..."));
  let p;
  try{p=await getJSON("/api/post?id="+encodeURIComponent(id));}
  catch(e){if(stale(t))return;
    view.innerHTML="";const d=document.createElement("div");d.className="state";
    d.textContent="Couldn't load: "+e.message;view.appendChild(d);return;}
  if(stale(t))return;

  const wrap=document.createElement("div");
  const back=document.createElement("a");back.className="back";back.textContent="back";
  back.onclick=()=>history.back();
  wrap.appendChild(back);

  const d=document.createElement("div");d.className="detail";
  // poster
  const poster=document.createElement("div");poster.className="poster";
  const ph=document.createElement("span");ph.className="ph";ph.textContent="rink";
  poster.appendChild(ph);
  if(p.poster){
    const img=document.createElement("img");img.alt=p.title;
    img.onload=()=>{img.classList.add("on");ph.style.display="none";};
    img.onerror=()=>{img.remove();};
    img.src=p.poster;
    poster.appendChild(img);
  }
  d.appendChild(poster);

  // right column
  const col=document.createElement("div");
  const h1=document.createElement("h1");h1.className="d-title";h1.textContent=p.title;
  col.appendChild(h1);
  const sub=document.createElement("div");sub.className="d-sub";
  const bits=[];const k=kind(p.title);if(k)bits.push(k);if(p.date)bits.push(p.date);
  sub.textContent=bits.join(" / ");col.appendChild(sub);
  if(p.synopsis){const s=document.createElement("p");s.className="syn";s.textContent=p.synopsis;
    col.appendChild(s);}

  // one file needs no heading; several are episodes or just files
  if(p.links.length>1){
    const epOnly=p.links.every(lk=>/^episode\b/i.test(lk.label||""));
    const dlh=document.createElement("div");dlh.className="dl-head";
    dlh.textContent=epOnly?"Episodes":"Files";
    col.appendChild(dlh);
  }

  const list=document.createElement("div");list.className="dl-list";
  const status=document.createElement("div");status.className="prog-txt";

  let activeBtn=null;

  p.links.forEach((lk,i)=>{
    const row=document.createElement("div");row.className="dl-row";
    const info=document.createElement("div");info.className="dl-ep";
    const l=document.createElement("div");l.className="l";
    l.textContent=lk.label||lk.text||"File";
    info.appendChild(l);
    const btn=document.createElement("button");btn.className="btn btn-dl";btn.textContent="Download";
    btn.onclick=()=>startDl(lk,btn,status);
    row.appendChild(info);row.appendChild(btn);list.appendChild(row);
  });

  col.appendChild(list);
  col.appendChild(status);
  d.appendChild(col);
  wrap.appendChild(d);
  view.innerHTML="";view.appendChild(wrap);

  async function startDl(lk,btn,txt){
    if(activeBtn)activeBtn.disabled=false;
    activeBtn=btn;btn.disabled=true;btn.textContent="Resolving...";
    txt.classList.add("on");
    try{
      // 1) ask the server to resolve the 2-step redirect to a direct URL
      const r=await fetch("/api/resolve?url="+encodeURIComponent(lk.url)
                         +"&referer="+encodeURIComponent(p.url));
      const j=await r.json();
      if(!r.ok)throw new Error(j.error||"resolve failed");

      // 2) hand the resolved file to the browser's own download manager.
      //    The request stays same-origin (our /api/file proxy) so the browser
      //    saves it as an attachment and streams straight to disk: no blob,
      //    no memory copy, no in-page progress loop.
      handToBrowser("/api/file?url="+encodeURIComponent(j.direct)
                    +"&name="+encodeURIComponent(j.name),j.name);

      btn.textContent="Downloading...";
      txt.textContent=(j.size?humanSize(j.size)+" - ":"")+"saving to your device";
      toast("Download started","ok");
      setTimeout(()=>{btn.textContent="Download again";btn.disabled=false;},2000);
    }catch(e){
      btn.textContent="Retry";
      txt.textContent="Error: "+e.message;
      toast("Download failed","err");
      btn.disabled=false;
    }
  }
}

/* Send a URL to the browser's native download manager without leaving the
   page: a same-origin click on an anchor. The server answers with
   Content-Disposition: attachment, so the browser saves instead of navigating. */
function handToBrowser(url,name){
  const a=document.createElement("a");
  a.href=url;
  if(name)a.download=name;
  a.rel="noopener";
  a.style.display="none";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* ---------------- router ---------------- */
async function loadCatalog(){
  try{
    const [g,f]=await Promise.all([getJSON("/api/genres"),getJSON("/api/formats")]);
    catalog={genres:g.genres||[],formats:f.formats||[]};
  }catch(e){
    catalog={genres:[],formats:[]};
    chipsEl.hidden=true;          // no catalog: hide the empty row entirely
  }
  renderChips();
}

function route(){
  const h=location.hash||"#/";
  let m;
  closeSheet();
  if((m=h.match(/^#\/p\/(.+)$/))){
    chipsEl.hidden=true;
    detail(decodeURIComponent(m[1]));
  }else if((m=h.match(/^#\/s\/([^/]+)(?:\/(\d+))?$/))){
    chipsEl.hidden=true;
    search(decodeURIComponent(m[1]),+(m[2]||1));
  }else if((m=h.match(/^#\/g\/([^/]+)(?:\/(\d+))?$/))){
    browse(decodeURIComponent(m[1]),+(m[2]||1));
  }else if((m=h.match(/^#\/latest(?:\/(\d+))?$/))){
    home(+(m[1]||1));
  }else{
    home(1);
  }
  window.scrollTo(0,0);
}
window.addEventListener("hashchange",route);


$("#searchForm").addEventListener("submit",e=>{
  e.preventDefault();
  const q=$("#searchInput").value.trim();
  if(!q)return;
  location.hash="#/s/"+encodeURIComponent(q);
});
/* chips before first paint: the genre row must not pop in late */
loadCatalog().then(route);
