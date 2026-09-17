"""The viewer: `outloud --view` (with or without files) opens the app in the browser.

A small local server (standard library only) serves one page: drop or choose
PDFs, and for each the rendered pages with every finding's location outlined,
the findings list that jumps to its box when clicked, the criteria view, the
logical structure tree, and a preview of the page in the order a screen
reader would read it. Files dropped into the page are written to a temporary
folder that is removed on exit. Nothing leaves the machine; the server binds
to localhost and stops when the process does.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .findings import Result
from .model import Document
from .registry import load_catalogue
from .rules._common import element_box, element_text

ZOOM = 2.0   # render scale; the page is shown at its point size, so this is a retina-quality image


def structure_tree(doc: Document, max_nodes: int = 6000) -> list[dict]:
    """The structure tree as nested dicts with type, page, text snippet and box."""
    count = 0

    def node(el):
        nonlocal count
        count += 1
        if count > max_nodes:
            return None
        text = element_text(doc, el, include_children=False)
        d = {"type": el.type_raw, "std": el.type if el.type != el.type_raw else None, "page": None, "text": " ".join(text.split())[:80],
             "alt": (el.alt or "")[:80] or None, "actual": (el.actual_text or "")[:80] or None, "box": element_box(doc, el), "kids": []}
        if d["box"]:
            d["page"] = d["box"]["page"]
        for c in el.children:
            k = node(c)
            if k:
                d["kids"].append(k)
        return d

    return [n for n in (node(el) for el in doc.elements if el.parent is None) if n]


def reading_order(doc: Document) -> dict[int, list[dict]]:
    """Per page: what a reader following the structure tree gets, in order, plus what artifacts hide."""
    per: dict[int, list[dict]] = {}
    for el in doc.elements:
        own = " ".join(element_text(doc, el, include_children=False).split())
        pieces = []
        if el.alt and el.type in ("Figure", "Formula", "Link"):
            pieces.append(f"[{el.type} alt: {el.alt}]")
        elif el.actual_text:
            pieces.append(el.actual_text)
        if own and not el.actual_text:
            pieces.append(own)
        if not pieces:
            continue
        b = element_box(doc, el)
        page = b["page"] if b else (el.page + 1 if el.page is not None else None)
        if page is None:
            continue
        per.setdefault(page, []).append({"type": el.type_raw, "text": " ".join(pieces)[:400], "box": b})
    for page in doc.pages:
        arts = [ln.text for ln in doc.content(page.index).lines if ln.artifact_share >= 0.8 and ln.text.strip()]
        if arts:
            per.setdefault(page.number, []).append({"type": "Artifact", "text": " / ".join(arts)[:400], "box": None})
    return per


def payload(result: Result, doc: Document) -> dict:
    cat = load_catalogue()
    pages = []
    for p in doc.pages:
        pages.append({"number": p.number, "width": round(p.width, 2), "height": round(p.height, 2)})
    findings = []
    for i, f in enumerate(result.sorted_findings()):
        meta = cat.get(f.rule)
        d = f.to_dict()
        d["id"] = i
        d["title"] = meta.title if meta else f.rule
        d["layer"] = meta.layer if meta else "?"
        d["clause"] = meta.clause if meta else None
        d["claim"] = meta.claim if meta else ""
        d["wcag"] = list(meta.wcag) if meta else []
        d["fix"] = meta.fix if meta else None
        findings.append(d)
    return {"result": {"path": result.path, "verdict": result.verdict, "counts": {"error": result.errors, "warning": result.warnings, "info": result.infos},
                       "seconds": round(result.seconds, 2), "stats": result.stats},
            "pages": pages, "findings": findings, "tree": structure_tree(doc), "reading": reading_order(doc),
            "criteria": result.criteria, "rules": [{"id": x.rule, "status": x.status, "outcome": x.outcome, "reason": x.reason} for x in result.runs]}


def render_page(doc: Document, number: int) -> bytes:
    fz = doc.fitz()
    page = fz[number - 1]
    try:
        import pymupdf as fitz  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        import fitz  # noqa: PLC0415
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    return pix.tobytes("png")


def page_transform(doc: Document, number: int) -> list[float]:
    """The matrix that maps PDF user space to the rendered image's pixels (fitz page space times zoom)."""
    fz = doc.fitz()
    m = fz[number - 1].transformation_matrix
    return [m.a * ZOOM, m.b * ZOOM, m.c * ZOOM, m.d * ZOOM, m.e * ZOOM, m.f * ZOOM]


HTML = r"""<!doctype html><meta charset="utf-8"><title>outloud</title>
<style>
:root{--ink:#1a1a1a;--muted:#5b5852;--rule:#d9d5ce;--bg:#f6f4ef;--panel:#fff;--err:#b3261e;--warn:#9a6a00;--info:#3a5a8c;--pass:#2c6e49;--accent:#c25c29}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:1rem;padding:.6rem 1rem;background:#1a1a1a;color:#f5f2ed}
header b{font-size:1rem}header .sub{color:#bbb;font-size:.85rem}
.verdict{padding:.1rem .5rem;border-radius:.2rem;font-weight:700;letter-spacing:.04em;color:#fff;font-size:.8rem}
.v-pass{background:var(--pass)}.v-review{background:var(--warn)}.v-fail{background:var(--err)}.v-unreadable{background:#555}
main[hidden],.drop[hidden]{display:none!important}
main{flex:1;display:grid;grid-template-columns:380px 1fr 360px;min-height:0}
@media (max-width:1100px){main{grid-template-columns:320px 1fr}aside.right{display:none}}
@media (max-width:760px){main{grid-template-columns:1fr;grid-template-rows:40vh 1fr}aside{border-right:0;border-bottom:1px solid var(--rule)}}
header{flex-wrap:wrap}
aside{background:var(--panel);border-right:1px solid var(--rule);overflow:auto;display:flex;flex-direction:column}
aside.right{border-right:0;border-left:1px solid var(--rule)}
.tabs{display:flex;border-bottom:1px solid var(--rule);position:sticky;top:0;background:var(--panel);z-index:2}
.tabs button{flex:1;padding:.55rem;border:0;background:none;cursor:pointer;color:var(--muted);font:inherit;border-bottom:2px solid transparent}
.tabs button.on{color:var(--ink);border-bottom-color:var(--accent);font-weight:600}
.filters{display:flex;gap:.4rem;padding:.5rem .75rem;border-bottom:1px solid var(--rule);flex-wrap:wrap}
.filters label{font-size:.8rem;color:var(--muted)}
.list{flex:1;overflow:auto}
.f{padding:.55rem .75rem;border-bottom:1px solid var(--rule);cursor:pointer}.f:hover{background:#faf8f3}.f.on{background:#fbf1ea;border-left:3px solid var(--accent)}
.f .top{display:flex;gap:.5rem;align-items:baseline}.sev{font-weight:700;text-transform:uppercase;font-size:.72rem}.sev-error{color:var(--err)}.sev-warning{color:var(--warn)}.sev-info{color:var(--info)}
.rule{font-family:ui-monospace,Menlo,monospace;font-size:.78rem;color:var(--muted)}.pg{margin-left:auto;color:var(--muted);font-size:.78rem}
.f .msg{margin-top:.15rem}.f .ev{color:var(--muted);font-size:.8rem;font-family:ui-monospace,Menlo,monospace;white-space:pre-wrap;margin-top:.15rem}
.f .claim{display:none;margin-top:.35rem;color:var(--muted);font-size:.8rem}.f.on .claim{display:block}
#pages{overflow:auto;padding:1rem;display:flex;flex-direction:column;align-items:center;gap:1rem;background:#e9e6df}
.page{position:relative;box-shadow:0 1px 4px rgba(0,0,0,.2);background:#fff}.page img{display:block}
.page .num{position:absolute;top:-1.1rem;left:0;font-size:.75rem;color:var(--muted)}
.box{position:absolute;border:2px solid var(--err);background:rgba(179,38,30,.10);pointer-events:none;border-radius:2px}
.box.warning{border-color:var(--warn);background:rgba(154,106,0,.10)}.box.info{border-color:var(--info);background:rgba(58,90,140,.10)}
.box.on{border-width:3px;box-shadow:0 0 0 3px rgba(194,92,41,.35);background:rgba(194,92,41,.15);border-color:var(--accent)}
.box.tree{border-color:var(--accent);background:rgba(194,92,41,.12);border-style:dashed}
.tree{padding:.5rem .75rem;font-size:.82rem}.tree ul{list-style:none;margin:0;padding-left:1rem}.tree li{margin:.1rem 0}
.tree .n{cursor:pointer;display:inline-block;padding:.05rem .3rem;border-radius:.2rem}.tree .n:hover{background:#faf8f3}.tree .n.on{background:#fbf1ea}
.tree .t{font-family:ui-monospace,Menlo,monospace;color:var(--accent)}.tree .s{color:var(--muted)}
details>summary{cursor:pointer}
.read{padding:.5rem .75rem;font-size:.85rem}.read h4{margin:.8rem 0 .3rem;font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.read p{margin:.2rem 0;padding:.2rem .3rem;border-radius:.2rem;cursor:pointer}.read p:hover{background:#faf8f3}.read p .t{color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:.75rem;margin-right:.3rem}
.read p.art{color:var(--muted);font-style:italic}
.empty{padding:1rem .75rem;color:var(--muted)}
header .grow{flex:1}.hbtn{font:inherit;font-size:.8rem;padding:.3rem .7rem;border:1px solid #666;background:#2a2a2a;color:#f5f2ed;border-radius:.2rem;cursor:pointer}.hbtn:hover{border-color:#ccc}
#docsel{font:inherit;font-size:.85rem;max-width:22rem;background:#2a2a2a;color:#f5f2ed;border:1px solid #666;border-radius:.2rem;padding:.2rem .4rem}
.drop{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1.5rem;padding:2rem;overflow:auto}
.dz{width:min(640px,100%);border:2px dashed #b9b4aa;border-radius:.4rem;padding:2.5rem 2rem;text-align:center;background:var(--panel);transition:border-color .15s,background .15s}
.dz.over{border-color:var(--accent);background:#fbf1ea}.dz .big{font-size:1.4rem;margin:0 0 .5rem}.dz .sub{color:var(--muted);margin:.35rem 0}
.dz .link{font:inherit;color:var(--accent);background:none;border:0;padding:0;cursor:pointer;text-decoration:underline}
.dz input[type=text]{font:inherit;font-size:.85rem;padding:.3rem .5rem;border:1px solid var(--rule);border-radius:.2rem}
.dz .hbtn{background:var(--accent);border-color:var(--accent);color:#fff}
.dz .err{color:var(--err)}
.doclist{width:min(640px,100%)}.doclist .d{display:flex;gap:.8rem;align-items:center;padding:.5rem .75rem;background:var(--panel);border:1px solid var(--rule);border-radius:.3rem;margin-bottom:.4rem;cursor:pointer}
.doclist .d:hover{border-color:var(--accent)}.doclist .d .n{flex:1}.doclist .d .s{color:var(--muted);font-size:.8rem}
.f .fix{display:none;margin-top:.3rem;font-size:.8rem;color:var(--ink)}.f.on .fix{display:block}
.crit{font-size:.82rem}.crit .sw{display:flex;gap:.4rem;padding:.5rem .75rem;border-bottom:1px solid var(--rule);align-items:center;flex-wrap:wrap}
.crit .sw button{border:1px solid var(--rule);background:none;padding:.2rem .5rem;border-radius:.2rem;cursor:pointer;font:inherit;font-size:.78rem;color:var(--muted)}
.crit .sw button.on{color:var(--ink);border-color:var(--accent);font-weight:600}
.crit .tally{padding:.4rem .75rem;color:var(--muted);font-size:.78rem;border-bottom:1px solid var(--rule)}
.crit .row{display:grid;grid-template-columns:4.4rem 1fr;gap:.5rem;padding:.4rem .75rem;border-bottom:1px solid var(--rule);cursor:pointer;align-items:start}
.crit .row:hover{background:#faf8f3}.crit .row.on{background:#fbf1ea;border-left:3px solid var(--accent)}
.st{display:inline-block;text-align:center;padding:.05rem .3rem;border-radius:.2rem;font-size:.66rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#fff;min-width:3.8rem}
.st-fail{background:var(--err)}.st-warning{background:var(--warn)}.st-pass{background:var(--pass)}.st-not-applicable{background:#8a877f}.st-manual{background:var(--info)}.st-not-tested{background:#bbb;color:#333}
.crit .nm{font-weight:600}.crit .lv{color:var(--muted);font-weight:400}.crit .rl{color:var(--muted);font-family:ui-monospace,Menlo,monospace;font-size:.74rem;margin-top:.15rem}
.crit .note{color:var(--muted);font-size:.76rem;margin-top:.15rem}
.crit .beyond{color:var(--warn);font-size:.74rem;margin-top:.15rem}
#critfilter{display:none;padding:.4rem .75rem;background:#fbf1ea;border-bottom:1px solid var(--rule);font-size:.8rem}
#critfilter button{margin-left:.5rem;font:inherit;font-size:.75rem;cursor:pointer}
</style>
<header><b>outloud</b><select id="docsel" hidden aria-label="Checked files"></select><span id="file" class="sub"></span><span id="verdict" class="verdict"></span><span id="counts" class="sub"></span>
  <span class="grow"></span><button id="openbtn" class="hbtn">Open PDF…</button><input type="file" id="filein" accept="application/pdf,.pdf" multiple hidden></header>
<div id="drop" class="drop" hidden>
  <div class="dz" id="dz">
    <p class="big">Drop a PDF here</p>
    <p class="sub">or <button class="link" id="pickbtn">choose one from your computer</button>. Several at once is fine.</p>
    <p class="sub">Or a path on this machine: <input id="pathin" type="text" placeholder="/Users/you/report.pdf" size="40"> <button id="pathbtn" class="hbtn">Check</button></p>
    <p id="busy" class="sub" hidden>Checking…</p>
    <p id="derr" class="err" hidden></p>
  </div>
  <div id="doclist" class="doclist"></div>
</div>
<main id="main" hidden>
<aside>
  <div class="tabs"><button class="on" data-tab="findings">Findings</button><button data-tab="crit">Criteria</button><button data-tab="tree">Structure</button></div>
  <div id="findings">
    <div id="critfilter"><span id="critlabel"></span><button onclick="clearCrit()">show all</button></div>
    <div class="filters"><label><input type="checkbox" checked data-sev="error"> errors</label><label><input type="checkbox" checked data-sev="warning"> warnings</label><label><input type="checkbox" checked data-sev="info"> info</label><label><input type="checkbox" id="onlyboxed"> only with a location</label></div>
    <div class="list" id="flist"></div>
  </div>
  <div id="crit" class="crit" hidden>
    <div class="sw"><button class="on" data-fw="pdfua1">PDF/UA-1</button><button data-fw="wcag22">WCAG 2.2</button><span style="margin-left:auto"><label style="font-size:.78rem;color:var(--muted)"><input type="checkbox" id="crithide" checked> hide not applicable</label></span></div>
    <div class="tally" id="crittally"></div>
    <div class="list" id="critlist"></div>
  </div>
  <div id="tree" class="tree" hidden></div>
</aside>
<section id="pages"></section>
<aside class="right"><div class="tabs"><button class="on">Read as a screen reader would</button></div><div id="read" class="read"></div></aside>
</main>
<script>
const $=s=>document.querySelector(s);
let DATA=null, TF={}, CRIT=null, FW='pdfua1';
const STL={fail:'fail',warning:'warn',pass:'pass','not-applicable':'n/a',manual:'person','not-tested':'not tested'};
const OUT={fail:'fail',warning:'warning',pass:'pass',info:'info','not-applicable':'n/a','not-run':'not run'};
function esc(s){return (s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
let ID=null;
function q(u){ return u+(u.includes('?')?'&':'?')+'id='+encodeURIComponent(ID); }
async function load(id){
  const url = id ? '/api/data?id='+encodeURIComponent(id) : '/api/data';
  const d=await (await fetch(url)).json();
  if(d.empty){ showDrop([]); return; }
  DATA=d; ID=d.id; TF={}; CRIT=null; $('#critfilter').style.display='none';
  $('#drop').hidden=true; $('#main').hidden=false;
  const r=DATA.result; $('#file').textContent=DATA.pages.length+' page(s) · '+r.seconds+'s';
  $('#verdict').textContent=r.verdict.toUpperCase(); $('#verdict').className='verdict v-'+r.verdict;
  $('#counts').textContent=r.counts.error+' error(s), '+r.counts.warning+' warning(s), '+r.counts.info+' info';
  renderDocsel(d.docs||[]);
  for(const p of DATA.pages){ TF[p.number]=await (await fetch(q('/api/transform/'+p.number))).json(); }
  renderPages(); renderFindings(); renderTree(); renderRead(); renderCriteria();
}
function renderDocsel(docs){ const sel=$('#docsel'); sel.innerHTML=''; for(const d of docs){ const o=document.createElement('option'); o.value=d.id; o.textContent=d.name+' — '+d.verdict.toUpperCase()+' ('+d.errors+'e/'+d.warnings+'w)'; if(d.id===ID) o.selected=true; sel.appendChild(o);} sel.hidden=docs.length<2; }
function showDrop(docs){ $('#main').hidden=true; $('#drop').hidden=false; $('#file').textContent=''; $('#verdict').textContent=''; $('#verdict').className='verdict'; $('#counts').textContent=''; $('#docsel').hidden=true;
  const host=$('#doclist'); host.innerHTML=''; if(docs.length){ const h=document.createElement('p'); h.className='sub'; h.textContent='Already checked in this session:'; host.appendChild(h); }
  for(const d of docs){ const el=document.createElement('div'); el.className='d'; el.innerHTML='<span class="verdict v-'+d.verdict+'">'+d.verdict.toUpperCase()+'</span><span class="n">'+esc(d.name)+'</span><span class="s">'+d.pages+' p · '+d.errors+' error(s), '+d.warnings+' warning(s)</span>'; el.onclick=()=>load(d.id); host.appendChild(el);} }
async function upload(files){
  const busy=$('#busy'), err=$('#derr'); err.hidden=true; busy.hidden=false; let last=null;
  for(const f of files){ busy.textContent='Checking '+f.name+'…';
    const r=await fetch('/api/upload?name='+encodeURIComponent(f.name),{method:'POST',body:f}); const j=await r.json();
    if(j.error){ err.textContent=f.name+': '+j.error; err.hidden=false; } else last=j.id; }
  busy.hidden=true; if(last) load(last); else showDrop((await (await fetch('/api/docs')).json()));
}
async function openPath(p){ const busy=$('#busy'), err=$('#derr'); err.hidden=true; busy.hidden=false; busy.textContent='Checking '+p+'…';
  const r=await fetch('/api/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})}); const j=await r.json(); busy.hidden=true;
  if(j.error){ err.textContent=j.error; err.hidden=false; } else load(j.id); }
$('#openbtn').onclick=()=>$('#filein').click(); $('#pickbtn').onclick=()=>$('#filein').click();
$('#filein').onchange=e=>{ if(e.target.files.length) upload([...e.target.files]); e.target.value=''; };
$('#pathbtn').onclick=()=>{ const p=$('#pathin').value.trim(); if(p) openPath(p); }; $('#pathin').onkeydown=e=>{ if(e.key==='Enter') $('#pathbtn').click(); };
$('#docsel').onchange=e=>load(e.target.value);
for(const ev of ['dragenter','dragover']) document.addEventListener(ev,e=>{ e.preventDefault(); $('#dz').classList.add('over'); });
for(const ev of ['dragleave','drop']) document.addEventListener(ev,e=>{ e.preventDefault(); $('#dz').classList.remove('over'); });
document.addEventListener('drop',e=>{ const fs=[...e.dataTransfer.files].filter(f=>f.name.toLowerCase().endsWith('.pdf')); if(fs.length){ if($('#drop').hidden){ $('#drop').hidden=false; $('#main').hidden=true; } upload(fs); } });
function px(box){ const m=TF[box.page]; if(!m) return null;
  const pts=[[box.x0,box.y0],[box.x1,box.y0],[box.x0,box.y1],[box.x1,box.y1]].map(([x,y])=>[m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5]]);
  const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]); const z=2;
  return {l:Math.min(...xs)/z, t:Math.min(...ys)/z, w:(Math.max(...xs)-Math.min(...xs))/z, h:(Math.max(...ys)-Math.min(...ys))/z}; }
function renderPages(){
  const host=$('#pages'); host.innerHTML='';
  for(const p of DATA.pages){
    const d=document.createElement('div'); d.className='page'; d.id='page-'+p.number; d.style.width=p.width+'px'; d.style.height=p.height+'px';
    d.innerHTML='<span class="num">page '+p.number+'</span><img loading="lazy" width="'+p.width+'" height="'+p.height+'" src="'+q('/page/'+p.number+'.png')+'">';
    host.appendChild(d);
  }
  for(const f of DATA.findings){ for(const b of (f.boxes||[])){ const r=px(b); if(!r) continue; const el=document.createElement('div'); el.className='box '+f.severity; el.dataset.f=f.id;
    el.style.left=r.l+'px'; el.style.top=r.t+'px'; el.style.width=Math.max(r.w,3)+'px'; el.style.height=Math.max(r.h,3)+'px'; el.title=f.rule+': '+f.message; $('#page-'+b.page)?.appendChild(el);} }
}
function renderFindings(){
  const on=[...document.querySelectorAll('[data-sev]')].filter(c=>c.checked).map(c=>c.dataset.sev); const onlyBoxed=$('#onlyboxed').checked;
  const host=$('#flist'); host.innerHTML='';
  const fs=DATA.findings.filter(f=>on.includes(f.severity)&&(!onlyBoxed||(f.boxes&&f.boxes.length))&&(!CRIT||CRIT.rules.includes(f.rule)));
  if(!fs.length){host.innerHTML='<div class="empty">'+(CRIT?'No findings for this criterion: the rules behind it passed or did not apply.':'No findings to show.')+'</div>';return;}
  for(const f of fs){ const d=document.createElement('div'); d.className='f'; d.dataset.f=f.id;
    d.innerHTML='<div class="top"><span class="sev sev-'+f.severity+'">'+f.severity+'</span><span class="rule">'+f.rule+'</span><span class="pg">'+(f.page?'p.'+f.page:'document')+(f.boxes&&f.boxes.length?' · '+f.boxes.length+' box'+(f.boxes.length>1?'es':''):'')+'</span></div>'
      +'<div class="msg">'+esc(f.message)+'</div>'+(f.evidence?'<div class="ev">'+esc(f.evidence)+'</div>':'')
      +'<div class="claim"><b>'+esc(f.title)+'</b>'+(f.clause?' · ISO 14289-1 '+esc(f.clause):' · semantic check')+(f.wcag&&f.wcag.length?' · WCAG '+esc(f.wcag.join(', ')):'')+'<br>'+esc(f.claim)+'</div>'
      +(f.fix?'<div class="fix"><b>Fix:</b> '+esc(f.fix)+'</div>':'');
    d.onclick=()=>select(f); host.appendChild(d);} }
function select(f){
  document.querySelectorAll('.f.on,.box.on').forEach(e=>e.classList.remove('on'));
  document.querySelectorAll('.f[data-f="'+f.id+'"]').forEach(e=>e.classList.add('on'));
  const boxes=document.querySelectorAll('.box[data-f="'+f.id+'"]'); boxes.forEach(e=>e.classList.add('on'));
  const target=boxes[0]||(f.page?$('#page-'+f.page):null); if(target) target.scrollIntoView({behavior:'smooth',block:'center'});
}
function renderTree(){
  const host=$('#tree'); host.innerHTML='';
  if(!DATA.tree.length){host.innerHTML='<div class="empty">No structure tree.</div>';return;}
  const build=(n,depth)=>{ const li=document.createElement('li'); const kids=n.kids||[];
    const label='<span class="n"><span class="t">'+esc(n.type)+'</span>'+(n.std?' <span class="s">→'+esc(n.std)+'</span>':'')+(n.page?' <span class="s">p.'+n.page+'</span>':'')+(n.alt?' <span class="s">alt: '+esc(n.alt)+'</span>':'')+(n.text?' '+esc(n.text):'')+'</span>';
    if(kids.length){ const det=document.createElement('details'); det.open=depth<2; det.innerHTML='<summary>'+label+'</summary>'; const ul=document.createElement('ul'); for(const k of kids) ul.appendChild(build(k,depth+1)); det.appendChild(ul); li.appendChild(det); det.querySelector('.n').onclick=(e)=>{e.preventDefault();showBox(n,det.querySelector('.n'));}; }
    else { li.innerHTML=label; li.querySelector('.n').onclick=()=>showBox(n,li.querySelector('.n')); }
    return li; };
  const ul=document.createElement('ul'); for(const n of DATA.tree) ul.appendChild(build(n,0)); host.appendChild(ul);
}
function showBox(n,el){
  document.querySelectorAll('.tree .n.on').forEach(e=>e.classList.remove('on')); el.classList.add('on');
  document.querySelectorAll('.box.tree').forEach(e=>e.remove());
  if(!n.box) return; const r=px(n.box); if(!r) return; const d=document.createElement('div'); d.className='box tree';
  d.style.left=r.l+'px'; d.style.top=r.t+'px'; d.style.width=Math.max(r.w,3)+'px'; d.style.height=Math.max(r.h,3)+'px';
  const pg=$('#page-'+n.box.page); pg.appendChild(d); d.scrollIntoView({behavior:'smooth',block:'center'});
}
function renderRead(){
  const host=$('#read'); host.innerHTML='';
  const pages=Object.keys(DATA.reading).map(Number).sort((a,b)=>a-b);
  if(!pages.length){host.innerHTML='<div class="empty">Nothing is tagged, so a screen reader following the structure gets nothing.</div>';return;}
  for(const p of pages){ const h=document.createElement('h4'); h.textContent='page '+p; host.appendChild(h);
    for(const item of DATA.reading[p]){ const d=document.createElement('p'); d.className=item.type==='Artifact'?'art':''; d.innerHTML='<span class="t">'+esc(item.type)+'</span>'+esc(item.text);
      if(item.box) d.onclick=()=>showBox({box:item.box},d); host.appendChild(d);} }
}
function tallyLine(rows){ const t={}; for(const r of rows) t[r.status]=(t[r.status]||0)+1;
  const lab={fail:'fail',warning:'warning',pass:'pass','not-applicable':'not applicable',manual:'need a person','not-tested':'not tested'};
  return ['fail','warning','pass','not-applicable','manual','not-tested'].filter(s=>t[s]).map(s=>t[s]+' '+lab[s]).join(' · '); }
function renderCriteria(){
  const host=$('#critlist'); host.innerHTML=''; if(!DATA.criteria||!DATA.criteria[FW]){host.innerHTML='<div class="empty">No criteria evaluated.</div>';return;}
  const rows=DATA.criteria[FW]; $('#crittally').textContent=tallyLine(rows);
  const hide=$('#crithide').checked;
  for(const r of rows){ if(hide&&r.status==='not-applicable') continue;
    const d=document.createElement('div'); d.className='row'+(CRIT&&CRIT.id===r.id&&CRIT.fw===FW?' on':'');
    const rules=(r.rules||[]).map(x=>x.id+' '+OUT[x.outcome]).join(' · ');
    const beyond=(r.semantic||[]).filter(x=>x.outcome==='fail'||x.outcome==='warning').map(x=>x.id+' '+OUT[x.outcome]).join(' · ');
    d.innerHTML='<span class="st st-'+r.status+'">'+STL[r.status]+'</span><div><div class="nm">'+esc(r.id)+' '+esc(r.name)+(r.level?' <span class="lv">('+r.level+')</span>':'')+'</div>'
      +(rules?'<div class="rl">'+esc(rules)+'</div>':'')+(beyond?'<div class="beyond">beyond the protocol: '+esc(beyond)+'</div>':'')+(r.note?'<div class="note">'+esc(r.note)+'</div>':'')+'</div>';
    d.onclick=()=>{ const ids=[...(r.rules||[]),...(r.semantic||[])].map(x=>x.id); if(!ids.length) return;
      CRIT={id:r.id,fw:FW,rules:ids,label:r.id+' '+r.name}; $('#critfilter').style.display='block'; $('#critlabel').textContent='Findings for '+CRIT.label;
      renderCriteria(); document.querySelector('.tabs button[data-tab="findings"]').click(); renderFindings(); };
    host.appendChild(d); }
}
function clearCrit(){ CRIT=null; $('#critfilter').style.display='none'; renderFindings(); renderCriteria(); }
document.querySelectorAll('.tabs button[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button[data-tab]').forEach(x=>x.classList.toggle('on',x===b)); $('#findings').hidden=b.dataset.tab!=='findings'; $('#tree').hidden=b.dataset.tab!=='tree'; $('#crit').hidden=b.dataset.tab!=='crit';});
document.querySelectorAll('.crit .sw button[data-fw]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.crit .sw button[data-fw]').forEach(x=>x.classList.toggle('on',x===b)); FW=b.dataset.fw; renderCriteria();});
$('#crithide').onchange=renderCriteria;
document.querySelectorAll('[data-sev],#onlyboxed').forEach(c=>c.onchange=renderFindings);
load(null);
</script>"""


class Store:
    """The documents the viewer holds: each checked once, kept open for page renders, closed on exit."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.order: list[str] = []
        self.tmpdir: Optional[str] = None
        self.lock = threading.Lock()

    def add_path(self, path: str, source: Optional[str] = None, result: Optional[Result] = None) -> str:
        from . import check  # noqa: PLC0415

        if result is None:
            result = check(path, source=source)
        doc = Document(path, source=source) if result.error is None else None
        did = hashlib.sha1(f"{path}:{time.time_ns()}".encode()).hexdigest()[:10]
        entry = {"id": did, "path": path, "name": os.path.basename(path), "result": result, "doc": doc,
                 "data": payload(result, doc) if doc is not None else {"result": {"path": path, "verdict": "unreadable", "error": result.error,
                                                                                    "counts": {"error": 0, "warning": 0, "info": 0}, "seconds": 0, "stats": {}},
                                                                         "pages": [], "findings": [], "tree": [], "reading": {}, "criteria": {}, "rules": []}}
        with self.lock:
            self.docs[did] = entry
            self.order.append(did)
        return did

    def add_bytes(self, name: str, body: bytes) -> str:
        if self.tmpdir is None:
            self.tmpdir = tempfile.mkdtemp(prefix="outloud-")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(name) or "upload.pdf")
        if not safe.lower().endswith(".pdf"):
            safe += ".pdf"
        path = os.path.join(self.tmpdir, f"{len(self.order) + 1:03d}-{safe}")
        with open(path, "wb") as fh:
            fh.write(body)
        return self.add_path(path)

    def listing(self) -> list[dict]:
        out = []
        for did in self.order:
            e = self.docs[did]
            r = e["result"]
            out.append({"id": did, "name": e["name"], "verdict": r.verdict, "errors": r.errors, "warnings": r.warnings,
                        "pages": r.stats.get("pages", 0)})
        return out

    def close(self):
        for e in self.docs.values():
            if e["doc"] is not None:
                try:
                    e["doc"].close()
                except Exception:  # noqa: BLE001
                    pass
        if self.tmpdir:
            shutil.rmtree(self.tmpdir, ignore_errors=True)


class _Handler(BaseHTTPRequestHandler):
    store: Store = None

    def log_message(self, *args):  # quiet
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200):
        self._send(json.dumps(obj).encode("utf-8"), "application/json", status)

    def _entry(self, query: dict) -> Optional[dict]:
        did = (query.get("id") or [None])[0]
        if did is None and self.store.order:
            did = self.store.order[-1]
        return self.store.docs.get(did) if did else None

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        path = u.path
        query = parse_qs(u.query)
        try:
            if path == "/" or path == "/index.html":
                self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/docs":
                self._json(self.store.listing())
            elif path == "/api/data":
                e = self._entry(query)
                if e is None:
                    self._json({"empty": True})
                else:
                    self._json(dict(e["data"], id=e["id"], docs=self.store.listing()))
            elif path.startswith("/api/transform/"):
                e = self._entry(query)
                n = int(path.rsplit("/", 1)[1])
                self._json(page_transform(e["doc"], n))
            elif path.startswith("/page/") and path.endswith(".png"):
                e = self._entry(query)
                n = int(path[len("/page/"):-4])
                self._send(render_page(e["doc"], n), "image/png")
            else:
                self._send(b"not found", "text/plain", 404)
        except Exception as exc:  # noqa: BLE001
            self._send(f"error: {exc}".encode("utf-8"), "text/plain", 500)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        query = parse_qs(u.query)
        try:
            if u.path == "/api/upload":
                # The body is the PDF itself; the name travels in the query string. No multipart
                # parsing, no size limit beyond what the machine holds.
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                if not body.startswith(b"%PDF"):
                    self._json({"error": "not a PDF file"}, 400)
                    return
                name = (query.get("name") or ["upload.pdf"])[0]
                did = self.store.add_bytes(name, body)
                self._json({"id": did, "docs": self.store.listing()})
            elif u.path == "/api/open":
                # A path on this machine, typed or pasted into the page; the server is local.
                length = int(self.headers.get("Content-Length") or 0)
                p = json.loads(self.rfile.read(length) or b"{}").get("path", "").strip()
                if not p or not os.path.isfile(p):
                    self._json({"error": "no such file"}, 400)
                    return
                did = self.store.add_path(p)
                self._json({"id": did, "docs": self.store.listing()})
            else:
                self._send(b"not found", "text/plain", 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 500)


def serve(results: list = (), docs: list = (), port: int = 0, open_browser: bool = True, block: bool = True):
    """Serve the viewer until interrupted. `results` and `docs` are parallel lists of what the CLI
    already checked; both may be empty, in which case the page opens with a drop zone. Returns
    the URL (and the server, when `block` is False, for tests)."""
    store = Store()
    for r, d in zip(results, docs):
        store.add_path(r.path, result=r)
        entry = store.docs[store.order[-1]]
        if entry["doc"] is not None and d is not None:
            entry["doc"].close()
            entry["doc"] = d
            entry["data"] = payload(r, d)
    handler = type("Handler", (_Handler,), {"store": store})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    if not block:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return url, httpd, store
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    else:
        print(url, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        store.close()
    return url
