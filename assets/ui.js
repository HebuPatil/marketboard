// Shared helpers for every dashboard page: formatting, sparklines, charts, key panel, sub-tabs.
// Each page defines before loading this file:  D (data), PAGE (name), KEY {tab: [[id, text, watch]]}
// and optionally NAMES {id: label} and T(id) -> tile, used to title key entries.

const $ = s => document.querySelector(s);
const fmtV = t => t.kind==="yield" ? t.last.toFixed(2)+"%" : t.last>=1000 ? t.last.toLocaleString(undefined,{maximumFractionDigits:0}) : t.last>=10 ? t.last.toFixed(2) : t.last.toFixed(t.last<2?4:3);
const unit = k => k==="yield" ? "bp" : k==="level" ? "" : "%";
const sgn = x => x==null ? "–" : (x>0?"+":"")+x;
const cls = x => x==null||x===0 ? "" : x>0 ? "up" : "dn";
const esc = s => String(s??"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const store = {get:(k,d)=>{try{const v=localStorage.getItem(PAGE+":"+k);return v==null?d:v}catch(e){return d}},
               set:(k,v)=>{try{localStorage.setItem(PAGE+":"+k,v)}catch(e){}}};

function spark(v, w=146, h=28){
  if(!v||v.length<2) return "";
  const mn=Math.min(...v), mx=Math.max(...v), r=mx-mn||1;
  const p=v.map((y,i)=>`${(i/(v.length-1)*w).toFixed(1)},${(h-2-(y-mn)/r*(h-4)).toFixed(1)}`).join(" ");
  const c = v[v.length-1]>=v[0] ? "var(--up)" : "var(--dn)";
  return `<svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="height:${h}px;display:block;margin-top:4px"><polyline fill="none" stroke="${c}" stroke-width="1.4" points="${p}"/></svg>`;
}

// Line/bar chart. Each series scaled to its own range (dual axis).
// opts: dual (right axis labels), invert (flip 2nd series), bars (1st series as bars), zero (dashed zero line)
function chart(series, opts={}){
  const W=520,H=170,L=44,R=opts.dual?44:10,Tp=8,B=20;
  const cols=["var(--acc)","var(--warn)"];
  let out=`<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block">`;
  const s0=series.find(s=>s&&s.v&&s.v.length); if(!s0) return '<p class="sub">No data</p>';
  series.forEach((s,k)=>{
    if(!s||!s.v||s.v.length<2) return;
    let mn=Math.min(...s.v), mx=Math.max(...s.v); const r=mx-mn||1;
    const inv = k===1 && opts.invert;
    const y = v => Tp + (inv ? (v-mn)/r : (mx-v)/r)*(H-Tp-B);
    const x = i => L + i/(s.v.length-1)*(W-L-R);
    if(opts.bars&&k===0){ const z=y(Math.max(mn,Math.min(mx,0))), bw=Math.max(1,(W-L-R)/s.v.length-1);
      s.v.forEach((v,i)=>{const yy=y(v); out+=`<rect x="${(x(i)-bw/2).toFixed(1)}" y="${Math.min(yy,z).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.5,Math.abs(z-yy)).toFixed(1)}" fill="${v>=0?cols[0]:"var(--dn)"}" opacity="0.8"/>`}); }
    else out+=`<polyline fill="none" stroke="${cols[k]}" stroke-width="1.6" points="${s.v.map((v,i)=>x(i).toFixed(1)+","+y(v).toFixed(1)).join(" ")}"/>`;
    const f = v => Math.abs(v)>=1000 ? v.toFixed(0) : Math.abs(v)>=10 ? v.toFixed(1) : Math.abs(v)>=0.1||v===0 ? v.toFixed(2) : v.toPrecision(3);
    const ax = k===0 ? 4 : W-4, anc = k===0 ? "start" : "end";
    const top = inv ? mn : mx, bot = inv ? mx : mn;
    out+=`<text x="${ax}" y="${Tp+9}" font-size="10" fill="${cols[k]}" text-anchor="${anc}">${f(top)}</text><text x="${ax}" y="${H-B}" font-size="10" fill="${cols[k]}" text-anchor="${anc}">${f(bot)}</text>`;
  });
  if(opts.zero||opts.bars){const s=series[0];const mn=Math.min(...s.v),mx=Math.max(...s.v);if(mn<0&&mx>0){const yy=Tp+(mx/(mx-mn))*(H-Tp-B);out+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="var(--faint)" stroke-dasharray="3 3"/>`;}}
  out+=`<text x="${L}" y="${H-4}" font-size="10" fill="var(--faint)">${s0.d[0]}</text><text x="${W-R}" y="${H-4}" font-size="10" fill="var(--faint)" text-anchor="end">${s0.d[s0.d.length-1]}</text></svg>`;
  return out;
}

// ---------------------------------------------------------------- key panel
let tab=null;
function keyName(id){ const t = typeof T==="function" ? T(id) : null; return t ? t.label : ((typeof NAMES!=="undefined" && NAMES[id]) || id); }
function renderKey(hl){
  const items = (KEY[tab]||[]);
  $("#key").innerHTML=`<h2>Key <button class="btn" style="padding:2px 8px" onclick="toggleKey(false)">Close</button></h2><p class="hint">Click anything on the page to jump to its entry.</p>`+
   items.map(([id,a,b])=>`<div class="kitem${id===hl?" hl":""}" id="k-${CSS.escape(id)}"><b>${keyName(id)}</b><p>${a}</p>${b?`<p class="w">Watch: ${b}</p>`:""}</div>`).join("");
  if(hl){const el=document.getElementById("k-"+CSS.escape(hl)); if(el) el.scrollIntoView({block:"center",behavior:"smooth"});}
}
function toggleKey(open){ $("#wrap").classList.toggle("nokey",!open); store.set("keyOpen",open?"1":"0"); }
function explain(id){ if($("#wrap").classList.contains("nokey")) toggleKey(true); renderKey(id); }

// ---------------------------------------------------------------- page boot
// tabs: [[id, label, renderFn], ...]. A single tab hides the sub-tab bar.
function initPage(tabs, first){
  const go = t => { tab=t; const nav=$("#tabs");
    nav.innerHTML = tabs.length>1 ? tabs.map(([id,n])=>`<button class="${id===t?"on":""}" data-t="${id}">${n}</button>`).join("") : "";
    nav.querySelectorAll("button").forEach(b=>b.onclick=()=>go(b.dataset.t));
    $("#main").innerHTML = tabs.find(x=>x[0]===t)[2](); renderKey(); store.set("tab",t); window.scrollTo(0,0); };
  window.go = go;
  $("#gen").textContent = "Updated " + D.generated;
  if(D.demo) $("#demo").style.display="";
  $("#keybtn").onclick=()=>toggleKey($("#wrap").classList.contains("nokey"));
  toggleKey(store.get("keyOpen","1")!=="0");
  const saved = store.get("tab", first);
  go(tabs.some(x=>x[0]===saved) ? saved : first);
}
