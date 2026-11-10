"use strict";
const $ = (s, r = document) => r.querySelector(s);

/* Where the API lives. Same origin when the page is served by this process;
   set window.RINK_API in config.js (or ?api=https://...) when the UI is hosted
   separately, e.g. static hosting in front of a remote server. */
const API_BASE = (window.RINK_API
  || new URLSearchParams(location.search).get("api") || "").replace(/\/+$/, "");
const apiUrl = p => p.startsWith("/api/") ? API_BASE + p : p;
const view = $("#view");
const cardTpl = $("#cardTpl");
const chipsEl = $("#chips");
const sourcesEl = $("#sources");

/* ---------------- sources ----------------
   Two sites behind one UI. The choice lives in the URL ("#/9ja/s/avatar") so
   a shared link keeps it, and in localStorage so the next visit opens on the
   one that was picked. Every API call carries ?src= because post ids collide
   between the two sites. */
const SOURCES = [{id: "nkiri", label: "Nkiri"}, {id: "9ja", label: "9jarocks"}];
const DEFAULT_SOURCE = "nkiri";
/* both sites can answer, but 9jarocks answers per file (one GET per episode
   row), so it is the slower of the two on a long season */
const CAN_SIZE = {nkiri: true, "9ja": true};
const SOURCE_KEY = "rink.src";
let source = DEFAULT_SOURCE;

function storedSource(){
  try{
    const s = localStorage.getItem(SOURCE_KEY);
    return SOURCES.some(x => x.id === s) ? s : DEFAULT_SOURCE;
  }catch(e){ return DEFAULT_SOURCE; }
}
function sourceLabel(id){
  const s = SOURCES.find(x => x.id === id);
  return s ? s.label : "";
}
/* "#/9ja/s/avatar" -> {src:"9ja", rest:"/s/avatar"}; a bare "#/p/1" keeps the
   remembered source, so every link written before this toggle still works */
function hashRoute(){
  const h = location.hash || "#/";
  const m = h.match(/^#\/([a-z0-9]+)(?=\/|$)(.*)$/);
  if(m && SOURCES.some(x => x.id === m[1])) return {src: m[1], rest: m[2] || "/"};
  return {src: storedSource(), rest: h.slice(1) || "/"};
}
/* links always name the source, so what the toggle shows is what is loaded */
function href(rest){ return "#/" + source + rest; }

function setSource(id){
  const next = SOURCES.some(x => x.id === id) ? id : DEFAULT_SOURCE;
  if(next === source) return false;
  source = next;
  try{ localStorage.setItem(SOURCE_KEY, source); }catch(e){}
  paintSource();
  loadMenu();           // each site brings its own menu, not a sliced one
  return true;
}
function paintSource(){
  sourcesEl.querySelectorAll("button").forEach(b => {
    const on = b.dataset.src === source;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}
/* switching re-runs whatever is on screen against the other site: same view,
   same search, same page, different source */
function switchSource(id){
  if(id === source) return;
  let rest = hashRoute().rest;
  if(/^\/p\//.test(rest)){
    // post ids are per-site: the same number is a different title on the
    // other one, so carry the name across and search it there instead
    const el = $(".d-title");
    const title = el ? el.textContent.trim() : "";
    rest = title ? "/s/" + encodeURIComponent(title) : "/";
  }
  setSource(id);
  const h = "#/" + source + rest;
  if(location.hash === h) route();
  else location.hash = h;
}
sourcesEl.addEventListener("click", e => {
  const b = e.target.closest("button[data-src]");
  if(b) switchSource(b.dataset.src);
});

/* browse state: the slug of the selected chip, and the format filter */
let catalog = {chips: [], formats: [], kind: "genre"};
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

/* ---------------- watchlist ----------------
   No accounts and no server state: the list is this browser's localStorage.
   Storage can be unavailable (private mode, blocked site data), so every
   access is guarded and a failure just means an empty list. */
const WATCH_KEY="rink.watch";

function watchMap(){
  try{return JSON.parse(localStorage.getItem(WATCH_KEY)||"{}")||{};}
  catch(e){return{};}
}
function watchSave(m){
  try{localStorage.setItem(WATCH_KEY,JSON.stringify(m));}catch(e){}
}
/* ids collide between the two sites, so a saved item is keyed by source+id */
function watchKey(item){ return (item.src||source)+":"+item.id; }

function toggleWatch(item){
  const m=watchMap();
  const key=watchKey(item);
  if(m[key]) delete m[key];
  else m[key]={id:item.id,src:item.src||source,title:item.title,
               date:item.date||"",poster:item.poster||""};
  watchSave(m);
  return !!m[key];
}

function starEl(item){
  const on=!!watchMap()[watchKey(item)];
  const s=document.createElement("span");
  s.className="star"+(on?" on":"");
  s.textContent=on?"★":"☆";   // filled / hollow star
  s.setAttribute("role","button");
  s.setAttribute("tabindex","0");
  s.setAttribute("aria-label",on?"remove from watchlist":"add to watchlist");
  const flip=e=>{
    e.preventDefault(); e.stopPropagation();
    const now=toggleWatch(item);
    s.className="star"+(now?" on":"");
    s.textContent=now?"★":"☆";
    s.setAttribute("aria-label",now?"remove from watchlist":"add to watchlist");
    // the watchlist view is built from the map, so it has to rebuild itself
    if(hashRoute().rest.startsWith("/watchlist")) route();
  };
  s.onclick=flip;
  s.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){flip(e);}};
  return s;
}

function cardEl(item){
  const node=cardTpl.content.firstElementChild.cloneNode(true);
  // a card remembers which site it came from, so the detail view opens the
  // right one even from the watchlist, where both sites are mixed
  const src=item.src||source;
  node.href="#/"+src+"/p/"+item.id;
  // the source only picks the ratio the box wears before its picture lands
  node.classList.add("src-"+src);
  node.querySelector(".title").textContent=item.title;
  node.querySelector(".sub").textContent=subFor(item);
  const img=node.querySelector("img");
  const ph=node.querySelector(".ph");
  const thumb=node.querySelector(".thumb");
  if(item.poster){
    img.loading="lazy"; img.decoding="async"; img.alt=item.title;
    // handlers first: a cached poster can fire load before src is assigned
    img.onload=()=>{
      img.classList.add("on");ph.style.display="none";
      /* the box takes the picture's own shape. The ratio cannot be fixed per
         site: 9jarocks serves 390x220 stills when browsing a category and
         portrait posters on newest-uploads, so any one ratio crops the other
         case. Matching the image means cover has nothing left to cut. */
      if(img.naturalWidth&&img.naturalHeight){
        thumb.style.aspectRatio=img.naturalWidth+"/"+img.naturalHeight;
      }
    };
    img.onerror=()=>{
      // one retry, then fall back to the placeholder
      if(!img.dataset.retried){img.dataset.retried="1";
        setTimeout(()=>{img.src=apiUrl(item.poster)+(item.poster.includes("?")?"&":"?")+"r=1";},1200);}
      else{img.remove();}
    };
    img.src=apiUrl(item.poster);
    if(img.complete&&img.naturalWidth){img.onload();}
  }else{
    img.remove();
  }
  thumb.appendChild(starEl({...item, src}));
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
  const r=await fetch(apiUrl(url)); if(!r.ok)throw new Error((await r.json()).error||r.status);
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
  if(!catalog.chips.length)return;      // the row keeps its height meanwhile
  chipsEl.replaceChildren();
  chipsEl.appendChild(chipEl("All",!browsing.tag,()=>{location.hash=href("/");}));
  // second slot, not last: the row scrolls, and 22 genre chips before it
  // would leave the watchlist permanently off-screen
  chipsEl.appendChild(chipEl("Watchlist",
    (location.hash||"").includes("/watchlist"),
    ()=>{location.hash=href("/watchlist");}));
  catalog.chips.forEach(g=>{
    chipsEl.appendChild(chipEl(g.name,browsing.tag===g.slug,
      ()=>{location.hash=href("/c/"+encodeURIComponent(g.slug));}));
  });
  // the format filter is thenkiri-only: 9jarocks has one axis and no formats
  if(catalog.formats.length){
    const fmt=catalog.formats.find(f=>f.slug===browsing.cat);
    chipsEl.appendChild(chipEl(fmt?fmt.name:"Format",!!fmt,openFormatSheet,"chip-end"));
  }
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
  const {rest}=hashRoute();
  const m=rest.match(/^\/[cg]\/([^/]+)/);
  if(m)browse(decodeURIComponent(m[1]),1);
  else browse("",1);
}

/* ---------------- home / category browse ---------------- */
function browseTitle(){
  const g=catalog.chips.find(x=>x.slug===browsing.tag);
  const f=catalog.formats.find(x=>x.slug===browsing.cat);
  if(g&&f)return`${g.name} / ${f.name}`;
  if(g)return g.name;
  if(f)return`New in ${f.name}`;
  // the two sites do not call their front page the same thing
  return source===DEFAULT_SOURCE?"New uploads":"Latest videos";
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
    const res=await getJSON("/api/browse?src="+encodeURIComponent(source)
                           +"&tag="+encodeURIComponent(browsing.tag)
                           +"&cat="+encodeURIComponent(browsing.cat)
                           +"&limit=30&page="+page);
    if(stale(t))return;
    view.innerHTML="";
    view.appendChild(section(browseTitle(),res.items,"Nothing here yet."));
    const base=browsing.tag?href("/c/"+encodeURIComponent(browsing.tag)):href("/latest");
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
    const res=await getJSON("/api/search?src="+encodeURIComponent(source)
                           +"&q="+encodeURIComponent(q)
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
      const p=pager(res,href("/s/"+encodeURIComponent(q)));
      if(p)view.appendChild(p);
    }else{
      const e=document.createElement("div");e.className="state";
      e.textContent=page>1?`No more results for "${q}" on ${sourceLabel(source)}.`
                           :`No results for "${q}" on ${sourceLabel(source)}.`;
      view.appendChild(e);
      const back=document.createElement("a");back.className="back";back.textContent="back to page 1";
      back.href=href("/s/"+encodeURIComponent(q));
      if(page>1)view.appendChild(back);
      // the other site may well have it: offer the switch instead of a dead end
      const other=SOURCES.find(s=>s.id!==source);
      if(other&&page===1){
        const b=document.createElement("button");
        b.type="button";b.className="btn btn-ghost";b.id="otherSource";
        b.textContent="Search "+other.label+" instead";
        b.onclick=()=>{setSource(other.id);
          location.hash="#/"+other.id+"/s/"+encodeURIComponent(q);};
        view.appendChild(b);
      }
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

/* Release year from the title: "The Odyssey (2026)" -> "2026". The post date
   is when it was uploaded, which is a different fact and shown separately. */
function yearOf(title){
  const m=(title||"").match(/\((\d{4})\)/);
  return m?m[1]:"";
}

/* Release quality lives in the file name, not in any API field. */
function qualityOf(lk){
  let u="";
  try{u=decodeURIComponent((lk&&lk.url)||"");}catch(e){u=(lk&&lk.url)||"";}
  const m=u.match(/\b(2160p|1440p|1080p|720p|576p|540p|480p|360p|240p|4K|WEB[-_]?Rip|WEB[-_]?DL|BluRay|BRRip|HDRip|HDTV|DVDRip)\b/i);
  return m?m[1]:"";
}

/* Group an episode list by season when every link carries SxxExx. Returns
   null for a film or a flat file list, so the caller keeps the old layout. */
function seasonGroups(links){
  const parsed=links.map(lk=>{
    let u="";
    try{u=decodeURIComponent(lk.url||"");}catch(e){u=lk.url||"";}
    const m=u.match(/S(\d{1,2})E(\d{1,3})/i);
    return m?{season:+m[1],episode:+m[2]}:null;
  });
  if(!parsed.length||parsed.some(x=>!x))return null;
  const bySeason=new Map();
  links.forEach((lk,i)=>{
    const s=parsed[i].season;
    if(!bySeason.has(s))bySeason.set(s,[]);
    bySeason.get(s).push(lk);
  });
  return [...bySeason.entries()]
    .sort((a,b)=>a[0]-b[0])
    .map(([season,ls])=>({season,links:ls}));
}

async function detail(id){
  const t=beginRender();
  view.innerHTML=""; view.appendChild(spinner("Loading..."));
  let p;
  try{p=await getJSON("/api/post?src="+encodeURIComponent(source)
                     +"&id="+encodeURIComponent(id));}
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
  /* the source rides along as a class: thenkiri's detail posters are 700 tall
     at anything from 600 to 1000 wide, 9jarocks' are a steady 2:3, so one
     fixed box for both would crop one of them */
  const poster=document.createElement("div");
  poster.className="poster src-"+source;
  const ph=document.createElement("span");ph.className="ph";ph.textContent="rink";
  poster.appendChild(ph);
  if(p.poster){
    const img=document.createElement("img");img.alt=p.title;
    img.onload=()=>{img.classList.add("on");ph.style.display="none";};
    img.onerror=()=>{img.remove();};
    img.src=apiUrl(p.poster);
    poster.appendChild(img);
  }
  d.appendChild(poster);

  // right column
  const col=document.createElement("div");

  const hrow=document.createElement("div");hrow.className="d-hrow";
  const h1=document.createElement("h1");h1.className="d-title";h1.textContent=p.title;
  hrow.appendChild(h1);hrow.appendChild(starEl(p));
  col.appendChild(hrow);

  // type, release year, origin format, release quality: four different facts,
  // each from a different place (catalog, title, categories, filename)
  const sub=document.createElement("div");sub.className="d-sub";
  const bits=[];const k=kind(p.title);if(k)bits.push(k);
  const yr=yearOf(p.title);if(yr)bits.push(yr);
  (p.formats||[]).forEach(f=>bits.push(f.name));
  const qual=qualityOf(p.links[0]);if(qual)bits.push(qual);
  sub.textContent=bits.join(" / ");col.appendChild(sub);

  if(p.date){const added=document.createElement("div");added.className="d-added";
    added.textContent="added "+p.date;col.appendChild(added);}

  if((p.genres||[]).length){
    const gc=document.createElement("div");gc.className="d-genres";
    p.genres.forEach(g=>{
      const a=document.createElement("a");a.className="chip";a.textContent=g.name;
      a.href=href("/c/"+encodeURIComponent(g.slug));
      gc.appendChild(a);
    });
    col.appendChild(gc);
  }

  if(p.synopsis){const s=document.createElement("p");s.className="syn";s.textContent=p.synopsis;
    col.appendChild(s);}

  const sizeEls=new Map();
  const status=document.createElement("div");status.className="prog-txt";
  let activeBtn=null,activeLab=null;

  function linkList(links){
    const list=document.createElement("div");list.className="dl-list";
    links.forEach(lk=>{
      const row=document.createElement("div");row.className="dl-row";
      const info=document.createElement("div");info.className="dl-ep";
      const l=document.createElement("div");l.className="l";
      l.textContent=lk.label||lk.text||"File";
      info.appendChild(l);
      // label and size live in separate spans: the label changes during the
      // download, the size must survive it
      const btn=document.createElement("button");btn.className="btn btn-dl";
      const lab=document.createElement("span");lab.className="dl-lbl";lab.textContent="Download";
      const sz=document.createElement("span");sz.className="dl-size";
      btn.appendChild(lab);btn.appendChild(sz);
      // a size the post page already printed costs no request
      if(lk.size)sz.textContent=lk.size;
      else sizeEls.set(lk.url,sz);
      btn.onclick=()=>startDl(lk,btn,lab,status);
      row.appendChild(info);row.appendChild(btn);list.appendChild(row);
    });
    return list;
  }

  const groups=seasonGroups(p.links);
  if(groups){
    groups.forEach((grp,i)=>{
      // each season is its own block, so the heading reads as a header for
      // the rows under it rather than a caption for the rows above
      const g=document.createElement("div");g.className="dl-group";
      const h=document.createElement("button");
      h.type="button";h.className="dl-head";
      const caret=document.createElement("span");
      caret.className="dl-caret";caret.textContent="▾";
      const name=document.createElement("span");
      name.textContent="Season "+grp.season;
      const count=document.createElement("span");
      count.className="dl-count";
      count.textContent=grp.links.length+(grp.links.length===1?" episode":" episodes");
      h.appendChild(caret);h.appendChild(name);h.appendChild(count);
      const body=document.createElement("div");body.className="dl-body";
      body.appendChild(linkList(grp.links));
      // first season open, the rest folded: a six-season page should not
      // open as a wall of rows
      const open=i===0;
      g.classList.toggle("is-open",open);
      h.setAttribute("aria-expanded",open?"true":"false");
      body.hidden=!open;
      h.onclick=()=>{
        const now=!g.classList.contains("is-open");
        g.classList.toggle("is-open",now);
        h.setAttribute("aria-expanded",now?"true":"false");
        body.hidden=!now;
      };
      g.appendChild(h);g.appendChild(body);
      col.appendChild(g);
    });
  }else{
    // one file needs no heading; several are episodes or just files
    if(p.links.length>1){
      const epOnly=p.links.every(lk=>/^episode\b/i.test(lk.label||""));
      const dlh=document.createElement("div");dlh.className="dl-head";
      dlh.textContent=epOnly?"Episodes":"Files";
      col.appendChild(dlh);
    }
    col.appendChild(linkList(p.links));
  }
  col.appendChild(status);
  d.appendChild(col);
  wrap.appendChild(d);
  view.innerHTML="";view.appendChild(wrap);

  // sizes arrive after the page is usable, three at a time: each one is a
  // round trip to the file host, and a 12-episode series must not block paint
  fillSizes(t,p.links);

  async function fillSizes(token,links){
    // only thenkiri prints a size on a page that is cheap to read; for the
    // other source this would be one wasted round trip per episode
    if(!CAN_SIZE[source])return;
    links=links.filter(lk=>!lk.size);
    if(!links.length)return;
    const LIMIT=3;
    let i=0;
    async function worker(){
      while(i<links.length){
        if(stale(token))return;
        const lk=links[i++];
        const el=sizeEls.get(lk.url);
        if(!el)continue;
        try{
          /* the source has to travel with this one: the endpoint reads the
             size differently per site, and without ?src it answers for the
             default (thenkiri), which knows nothing about a 9jarocks file */
          const r=await fetch(apiUrl("/api/size?src="+encodeURIComponent(source)
                                     +"&url="+encodeURIComponent(lk.url)));
          const j=await r.json();
          if(stale(token))return;
          if(j.size)el.textContent=j.size;
        }catch(e){/* no size is fine: the button still works */}
      }
    }
    await Promise.all(Array.from({length:Math.min(LIMIT,links.length)},worker));
  }

  async function startDl(lk,btn,lab,txt){
    if(activeBtn){activeBtn.disabled=false;if(activeLab)activeLab.textContent="Download";}
    activeBtn=btn;activeLab=lab;btn.disabled=true;lab.textContent="Resolving...";
    txt.classList.add("on");
    try{
      // 1) ask the server to resolve the 2-step redirect to a direct URL
      const r=await fetch(apiUrl("/api/resolve?url="+encodeURIComponent(lk.url))
                         +"&referer="+encodeURIComponent(p.url));
      const j=await r.json();
      if(!r.ok)throw new Error(j.error||"resolve failed");

      // 2) hand the resolved file to the browser's own download manager.
      //    The request stays same-origin (our /api/file proxy) so the browser
      //    saves it as an attachment and streams straight to disk: no blob,
      //    no memory copy, no in-page progress loop.
      handToBrowser(apiUrl("/api/file?url="+encodeURIComponent(j.direct)
                          +"&name="+encodeURIComponent(j.name)),j.name);

      lab.textContent="Downloading...";
      txt.textContent=(j.size?humanSize(j.size)+" - ":"")+"saving to your device";
      toast("Download started","ok");
      setTimeout(()=>{lab.textContent="Download again";btn.disabled=false;},2000);
    }catch(e){
      lab.textContent="Retry";
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
/* One request, because the menu is per source: thenkiri sends genres plus
   formats, 9jarocks sends its categories and no formats. */
async function loadMenu(){
  const wanted=source;
  try{
    const m=await getJSON("/api/menu?src="+encodeURIComponent(wanted));
    if(wanted!==source)return;    // the toggle moved while this was in flight
    catalog={chips:m.chips||[],formats:m.formats||[],kind:m.kind||"genre"};
  }catch(e){
    if(wanted!==source)return;
    catalog={chips:[],formats:[],kind:"genre"};
    chipsEl.hidden=true;          // no menu: hide the empty row entirely
  }
  renderChips();
}

/* ---------------- watchlist view ---------------- */
function watchlist(){
  beginRender();
  chipsEl.hidden=false;
  const items=Object.values(watchMap())
    .sort((a,b)=>(b.date||"").localeCompare(a.date||""));
  view.innerHTML="";
  view.appendChild(section(`Watchlist (${items.length})`,items,
    "Nothing saved yet. Tap the star on a card."));
  renderChips();
}

function route(){
  const {src,rest}=hashRoute();
  // the URL is the source of truth: a link with a prefix wins over the one
  // that was remembered, and switching here reloads the menu if it changed
  setSource(src);
  let m;
  closeSheet();
  if((m=rest.match(/^\/p\/(.+)$/))){
    chipsEl.hidden=true;
    detail(decodeURIComponent(m[1]));
  }else if((m=rest.match(/^\/s\/([^/]+)(?:\/(\d+))?$/))){
    chipsEl.hidden=true;
    const q=decodeURIComponent(m[1]);
    // keep the box in step with the URL, so a shared link shows its query
    const box=$("#searchInput");
    if(box.value!==q)box.value=q;
    search(q,+(m[2]||1));
  }else if(/^\/watchlist\/?$/.test(rest)){
    watchlist();
  }else if((m=rest.match(/^\/[cg]\/([^/]+)(?:\/(\d+))?$/))){
    // /g/ is the old genre route, /c/ the current one; both mean "chip"
    browse(decodeURIComponent(m[1]),+(m[2]||1));
  }else if((m=rest.match(/^\/latest(?:\/(\d+))?$/))){
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
  location.hash=href("/s/"+encodeURIComponent(q));
});

/* Search as you type. 250ms after the last keystroke, so nine letters cost one
   request, not nine. Once inside a search the entry is replaced rather than
   pushed, otherwise every pause becomes a back-button step. */
const searchBox=$("#searchInput");
let searchTimer=0;
searchBox.addEventListener("input",()=>{
  clearTimeout(searchTimer);
  const q=searchBox.value.trim();
  searchTimer=setTimeout(()=>{
    if(!q)return;
    const h=href("/s/"+encodeURIComponent(q));
    if(location.hash===h)return;
    // inside a search for this source the entry is replaced; coming from
    // anywhere else it is pushed, so back returns to where the user was
    if(hashRoute().rest.startsWith("/s/")){
      history.replaceState(null,"",h);
      route();
    }else{
      location.hash=h;
    }
  },250);
});
/* Paint the list first, fill the chip row when the menu lands. Awaiting the
   menu here serialised two round trips in front of the first card.
   renderChips() is a no-op on an empty catalog and runs again on arrival. */
paintSource();
route();
loadMenu();
