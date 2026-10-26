import { pages, sources, outline, questions } from './content.js';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const pdfScroll = $('#pdf-scroll');
const notesScroll = $('#notes-scroll');
const pageRoot = $('#pdf-pages');
const count = pages.length;
let current = 0;
let pdf = null;
let zoom = 1;
let renderEpoch = 0;
let rendererBusy = false;
let activeRender = null;
let queue = [];
let pageObserver = null;
let visiblePages = new Set();
let jumpTarget = null;
let pendingNavigation = null;
let expanded = false;
const pageNodes = [];
const rendered = new Map();
const kindNames = { paper:'论文事实', code:'代码核验', proposal:'接入方案', caution:'阅读边界' };

function hashState() {
  const h = new URLSearchParams(location.hash.slice(1));
  const n = Number(h.get('page'));
  return { page: Number.isInteger(n) && n >= 1 && n <= count ? n : 1, card: h.get('note') };
}

function sourceLinks(refs) {
  return `<div class="source-row">${refs.map(key => sources[key]).filter(Boolean).map(([name,url])=>`<a href="${url}" target="_blank" rel="noopener">${name} ↗</a>`).join('')}</div>`;
}

function setCurrent(n, cardId=null) {
  n = Math.max(1, Math.min(count, n));
  const pg = pages[n-1];
  if (n !== current) {
    current = n;
    expanded = false;
    $('#expand-all').textContent = '展开全部';
    $('#page-input').value = n;
    $('#note-page').textContent = String(n).padStart(2,'0');
    $('#mobile-page').textContent = `P.${String(n).padStart(2,'0')}`;
    $('#note-section').textContent = pg.section;
    $('#reading-label').textContent = pg.section;
    $('#previous').disabled = n === 1;
    $('#next').disabled = n === count;
    $('#commentary').innerHTML = `<span class="eyebrow">PAGE ${String(n).padStart(2,'0')} / 24 · READING COMPANION</span><h1 class="article-heading">${pg.title}</h1><p class="article-lede">${pg.lede}</p><div class="meta-tags">${pg.tags.map(tag=>`<span>${tag}</span>`).join('')}</div><div class="takeaway">${pg.takeaway}</div>${pg.cards.map((c,i)=>`<details class="note-card" id="note-${c.id}" ${i<2?'open':''}><summary><span class="kind ${c.kind}">${kindNames[c.kind]}</span><h3>${c.title}</h3></summary><div class="card-body">${c.body}${sourceLinks(c.refs)}</div></details>`).join('')}<div class="jump-links">${n>1?`<button data-jump="${n-1}">← 上一页讲解</button>`:''}${n<count?`<button data-jump="${n+1}">下一页讲解 →</button>`:''}<button data-jump="21" data-note="distillation">TacJev 蒸馏方案 · p.21</button></div>`;
    notesScroll.scrollTop = 0;
    $$('#outline button').forEach(b=>b.classList.toggle('active',Number(b.dataset.page)===n));
    $$('#commentary [data-jump]').forEach(b=>b.addEventListener('click',()=>navigate(Number(b.dataset.jump),b.dataset.note)));
    setupSelectionLab();
    setupRealFrames();
    queueVisible();
  }
  const hash = new URLSearchParams({page:String(n)});
  if (cardId) hash.set('note',cardId);
  history.replaceState(null,'',`#${hash}`);
  if (cardId) {
    const target = document.getElementById(`note-${cardId}`);
    if (target) {
      target.open = true;
      requestAnimationFrame(()=>{
        notesScroll.scrollTop = target.getBoundingClientRect().top - notesScroll.getBoundingClientRect().top + notesScroll.scrollTop - 16;
        target.classList.add('highlight-card');
        setTimeout(()=>target.classList.remove('highlight-card'),2000);
      });
    }
  }
}

function navigate(n, cardId=null, showNotes=false) {
  if (!Number.isFinite(n)) return;
  n = Math.max(1,Math.min(count,Math.round(n)));
  jumpTarget = n;
  if (pageNodes[n-1]) {
    pdfScroll.scrollTo({top:pageNodes[n-1].offsetTop - pageRoot.offsetTop,behavior:'instant'});
    enqueue(n);
    setTimeout(()=>{ jumpTarget = null; },200);
  } else pendingNavigation = n;
  setCurrent(n,cardId);
  if (showNotes && matchMedia('(max-width:760px)').matches) setPane('notes');
}

function setupSelectionLab() {
  const lab = $('#selection-lab');
  if (!lab) return;
  let scores = [0,0.22,0.48,0.33,1.65,0.41,0.65,0.18];
  lab.className = 'lab';
  lab.innerHTML = '<span class="lab-label">教学用归一化变化分数 · 不是原始测量</span><div class="lab-bars" aria-label="八个采样时刻的相邻变化分数"></div><label class="lab-control">阈值 <input type="range" id="threshold" min="0.5" max="2" step="0.05" value="1" aria-label="选帧阈值"><output id="threshold-value">1.00</output></label><button type="button" class="lab-toggle" id="tie-toggle">试试两个并列峰</button><p class="lab-output" id="selected-output" aria-live="polite"></p><span class="lab-label" id="lab-explanation"></span>';
  function update() {
    const threshold = Number($('#threshold').value);
    const maximum = Math.max(...scores.slice(1));
    const peak = scores.indexOf(maximum,1);
    const kept = [...new Set(maximum >= threshold ? [0,peak-1,peak,7] : [0,7])].sort((a,b)=>a-b);
    $('#threshold-value').textContent = threshold.toFixed(2);
    $('#selected-output').textContent = `保留索引 S = { ${kept.join(', ')} } · 每指 ${kept.length} 帧`;
    $('#lab-explanation').textContent = maximum >= threshold ? `最大变化 ${maximum.toFixed(2)} ≥ ${threshold.toFixed(2)}：加入第 ${peak-1} / ${peak} 帧。${scores[6]===maximum?'并列时取时间上第一个峰。':''}` : `最大变化 ${maximum.toFixed(2)} < ${threshold.toFixed(2)}：只保留起点与终点。`;
    $('.lab-bars').innerHTML = scores.map((s,i)=>`<div class="lab-column ${i===peak?'peak':''} ${kept.includes(i)?'selected':''}" data-step="${i}" style="--score:${s}" title="索引 ${i}，分数 ${s}，${kept.includes(i)?'保留':'不保留'}"><i></i><b>${s.toFixed(2)}</b></div>`).join('');
  }
  $('#threshold').addEventListener('input',update);
  $('#tie-toggle').addEventListener('click',()=>{
    scores[6] = scores[6]===1.65 ? 0.65 : 1.65;
    $('#tie-toggle').textContent = scores[6]===1.65 ? '恢复单峰' : '试试两个并列峰';
    update();
  });
  update();
}

function setupRealFrames() {
  const viewer = $('#real-frame-viewer');
  if (!viewer) return;
  const steps=[598,728,730,778],labels=['动作起点','最大变化前','最大变化后','动作终点'];
  viewer.innerHTML = '<div class="demo-media"><label>左指<img id="demo-left" alt=""></label><label>右指<img id="demo-right" alt=""></label></div><div class="demo-actions">'+steps.map((s,i)=>`<button type="button" data-frame="${i}">${labels[i]} · ${s}</button>`).join('')+'</div><p class="note-caption" id="demo-caption"></p>';
  function select(i) {
    for (const side of ['left','right']) {
      const img=$(`#demo-${side}`);
      img.src=`assets/demonstrations/insert_tube/e0_s4_${side}_frames/frame-${i}.png`;
      img.alt=`官方示范 ${side==='left'?'左':'右'}指，${labels[i]}，step ${steps[i]}`;
    }
    $$('.demo-actions button').forEach(b=>b.classList.toggle('active',Number(b.dataset.frame)===i));
    $('#demo-caption').textContent=`${labels[i]} · 记录 step ${steps[i]}。这是已公开的选帧结果；原始 HDF5 未发布在该代码包中，本页未重算原始峰值。`;
  }
  $$('.demo-actions button').forEach(b=>b.addEventListener('click',()=>select(Number(b.dataset.frame))));
  select(0);
}

function setPane(pane) {
  document.body.dataset.pane=pane;
  $$('.mobile-tabs button').forEach(b=>b.classList.toggle('selected',b.dataset.pane===pane));
  if (pane==='paper') {
    requestAnimationFrame(()=>{
      resizePages();
      if(pageNodes[current-1]) pdfScroll.scrollTop=pageNodes[current-1].offsetTop-pageRoot.offsetTop;
    });
  }
}

function setupQuestions() {
  const dialog=$('#question-dialog');
  function render(filter='') {
    const q=filter.trim().toLocaleLowerCase();
    const hits=questions.filter(x=>[x.question,pages[x.page-1].cards.find(c=>c.id===x.card).body.replace(/<[^>]+>/g,'')].join(' ').toLocaleLowerCase().includes(q));
    $('#question-list').innerHTML=hits.map(x=>`<button class="question-result" data-page="${x.page}" data-note="${x.card}"><span>P.${String(x.page).padStart(2,'0')}</span>${x.question}</button>`).join('')||'<p class="empty-results">没有匹配问题。可以试试“模型”“选帧”“蒸馏”“输入”。</p>';
    $$('#question-list button').forEach(b=>b.addEventListener('click',()=>{dialog.close();navigate(Number(b.dataset.page),b.dataset.note,true);}));
  }
  $('#questions-button').addEventListener('click',()=>{render();dialog.showModal();$('#question-search').value='';$('#question-search').focus();});
  $('#close-questions').addEventListener('click',()=>dialog.close());
  $('#question-search').addEventListener('input',e=>render(e.target.value));
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
}

function pageWidth() {
  const computed=getComputedStyle(pdfScroll);
  return Math.max(180,pdfScroll.clientWidth-parseFloat(computed.paddingLeft)-parseFloat(computed.paddingRight))*zoom;
}

function resizePages() {
  if (!pageNodes.length || pdfScroll.clientWidth===0) return;
  renderEpoch++;
  if(activeRender) activeRender.cancel();
  queue=[];
  rendered.clear();
  const width=pageWidth();
  pageNodes.forEach(node=>{
    node.style.width=`${width}px`;
    node.style.height=`${width*Number(node.dataset.ratio)}px`;
    node.classList.remove('rendered');
    node.querySelectorAll('canvas,.textLayer').forEach(x=>{if(x.tagName==='CANVAS'){x.width=0;x.height=0;}x.remove();});
  });
  queueVisible();
}

function enqueue(n) {
  if (!pdf || !pageNodes[n-1] || rendered.get(n)===renderEpoch || queue.includes(n)) return;
  queue.push(n);
  queue.sort((a,b)=>Math.abs(a-current)-Math.abs(b-current));
  processQueue();
}

function queueVisible() {
  if (!pdf) return;
  for (const n of [current,...visiblePages,current-1,current+1]) if(n>=1&&n<=count) enqueue(n);
  // Keep layout placeholders, release canvases far away from the reading position.
  for (const [n] of rendered) {
    if (Math.abs(n-current)>5&&!visiblePages.has(n)) {
      const node=pageNodes[n-1];
      node.querySelectorAll('canvas,.textLayer').forEach(x=>{if(x.tagName==='CANVAS'){x.width=0;x.height=0;}x.remove();});
      node.classList.remove('rendered');
      rendered.delete(n);
    }
  }
}

async function processQueue() {
  if(rendererBusy) return;
  rendererBusy=true;
  while(queue.length) {
    const n=queue.shift(),epoch=renderEpoch;
    if(rendered.get(n)===epoch) continue;
    const node=pageNodes[n-1];
    if(!node || node.offsetWidth===0) continue;
    try {
      const pg=await pdf.getPage(n);
      if(epoch!==renderEpoch) continue;
      const base=pg.getViewport({scale:1});
      const scale=node.offsetWidth/base.width;
      const viewport=pg.getViewport({scale});
      const ratio=Math.min(devicePixelRatio||1,2);
      node.style.height=`${viewport.height}px`;
      node.dataset.ratio=String(base.height/base.width);
      node.querySelectorAll('canvas,.textLayer').forEach(x=>x.remove());
      const canvas=document.createElement('canvas');
      canvas.width=Math.ceil(viewport.width*ratio);
      canvas.height=Math.ceil(viewport.height*ratio);
      canvas.setAttribute('aria-label',`论文第 ${n} 页`);
      node.prepend(canvas);
      activeRender=pg.render({canvasContext:canvas.getContext('2d'),viewport,transform:ratio===1?null:[ratio,0,0,ratio,0,0]});
      await activeRender.promise;
      activeRender=null;
      if(epoch!==renderEpoch) continue;
      node.classList.add('rendered');
      rendered.set(n,epoch);
      const text=await pg.getTextContent();
      if(epoch!==renderEpoch) continue;
      const layer=document.createElement('div');
      layer.className='textLayer';
      layer.style.setProperty('--scale-factor',scale);
      node.style.setProperty('--scale-factor',scale);
      node.append(layer);
      try { await new window.pdfjsLib.TextLayer({textContentSource:text,container:layer,viewport}).render(); }
      catch(error) { layer.remove(); console.warn('Selectable text layer:',n,error.message); }
    } catch(error) {
      if(error.name!=='RenderingCancelledException') {
        console.error('PDF page',n,error);
        node.querySelector('.page-loading').textContent='本页渲染失败，请打开原始 PDF';
      }
    }
  }
  rendererBusy=false;
}

async function loadPdf() {
  try {
    const pdfjs=await import('./assets/vendor/pdf.mjs');
    window.pdfjsLib=pdfjs;
    pdfjs.GlobalWorkerOptions.workerSrc=new URL('./assets/vendor/pdf.worker.mjs',import.meta.url).href;
    pdf=await pdfjs.getDocument({url:new URL('./assets/tactile-eta-v1.pdf',import.meta.url).href,isEvalSupported:false}).promise;
    if(pdf.numPages!==count) throw new Error(`PDF版本不匹配：预期24页，实际${pdf.numPages}`);
    const first=await pdf.getPage(1),viewport=first.getViewport({scale:1});
    for(let n=1;n<=count;n++) {
      const node=document.createElement('div');
      node.className='pdf-page';
      node.dataset.page=n;
      node.dataset.ratio=String(viewport.height/viewport.width);
      node.style.minHeight='0';
      node.innerHTML=`<span class="page-loading">第 ${n} 页</span><span class="page-marker" aria-hidden="true">${n} / 24</span>`;
      pageNodes.push(node);pageRoot.append(node);
    }
    $('#pdf-status').hidden=true;
    resizePages();
    pageObserver=new IntersectionObserver(entries=>{
      entries.forEach(entry=>{const n=Number(entry.target.dataset.page);if(entry.isIntersecting){visiblePages.add(n);enqueue(n);}else visiblePages.delete(n);});
    },{root:pdfScroll,rootMargin:'650px 0px',threshold:0});
    pageNodes.forEach(node=>pageObserver.observe(node));
    navigate(pendingNavigation||current||1,hashState().card);
    document.documentElement.dataset.ready='true';
  } catch(error) {
    console.error(error);
    $('#pdf-status').innerHTML='原文阅读器未能加载。请刷新，或<a href="assets/tactile-eta-v1.pdf" target="_blank" rel="noopener">打开原始 PDF</a>。右侧讲解与页码仍可独立使用。';
    document.documentElement.dataset.ready='error';
  }
}

$('#outline').innerHTML='<strong>论文目录 · 24 页</strong>'+outline.map(x=>`<button data-page="${x.page}"><span>${String(x.page).padStart(2,'0')}</span>${x.label}</button>`).join('');
$$('#outline button').forEach(b=>b.addEventListener('click',()=>{navigate(Number(b.dataset.page));$('#outline').hidden=true;$('#outline-button').setAttribute('aria-expanded','false');}));
$('#outline-button').addEventListener('click',()=>{const nav=$('#outline');nav.hidden=!nav.hidden;$('#outline-button').setAttribute('aria-expanded',String(!nav.hidden));});
$('#previous').addEventListener('click',()=>navigate(current-1));
$('#next').addEventListener('click',()=>navigate(current+1));
$('#page-input').addEventListener('change',e=>navigate(Number(e.target.value)));
$('#page-input').addEventListener('keydown',e=>{if(e.key==='Enter'){navigate(Number(e.target.value));e.target.blur();}});
$('#zoom-in').addEventListener('click',()=>{zoom=Math.min(1.8,zoom+0.2);resizePages();navigate(current);});
$('#zoom-out').addEventListener('click',()=>{zoom=Math.max(0.6,zoom-0.2);resizePages();navigate(current);});
$('#zoom-reset').addEventListener('click',()=>{zoom=1;resizePages();navigate(current);});
$('#expand-all').addEventListener('click',()=>{expanded=!expanded;$$('#commentary .note-card').forEach(d=>d.open=expanded);$('#expand-all').textContent=expanded?'收起全部':'展开全部';});
$$('.mobile-tabs button').forEach(b=>b.addEventListener('click',()=>setPane(b.dataset.pane)));
let scrollFrame=0;
pdfScroll.addEventListener('scroll',()=>{
  if(scrollFrame) return;
  scrollFrame=requestAnimationFrame(()=>{
    scrollFrame=0;
    if(jumpTarget||pdfScroll.clientHeight===0) return;
    const line=pdfScroll.getBoundingClientRect().top+pdfScroll.clientHeight*0.38;
    const node=pageNodes.find(x=>{const r=x.getBoundingClientRect();return r.top<=line&&r.bottom>line;});
    if(node) setCurrent(Number(node.dataset.page));
  });
},{passive:true});
pdfScroll.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();navigate(current+(e.key==='ArrowRight'?1:-1));}
});
let resizeTimer;
new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(pdfScroll.clientWidth>0){resizePages();navigate(current);}},160);}).observe(pdfScroll);
window.addEventListener('hashchange',()=>{const h=hashState();navigate(h.page,h.card);});
setupQuestions();
const initial=hashState();
setCurrent(initial.page,initial.card);
loadPdf();
