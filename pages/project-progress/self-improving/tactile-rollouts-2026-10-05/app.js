'use strict';
(() => {
  const data = window.ROLLOUT_DATA;
  const slides = [...document.querySelectorAll('.slide')];
  const nav = document.querySelector('#chapters');
  const notes = document.querySelector('#speaker-notes');
  let current = 0;
  let toastTimer;
  let syncRaf;
  let syncPlaying = false;
  const syncRange = document.querySelector('#sync-range');
  const syncSpeed = document.querySelector('#sync-speed');
  const pad = n => String(n).padStart(2, '0');
  const escape = s => String(s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function toast(message) {
    const box = document.querySelector('#toast');
    box.textContent = message;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 4200);
  }
  slides.forEach((slide, i) => {
    const link = document.createElement('a');
    link.href = '#' + slide.id;
    link.innerHTML = `<span>${pad(i + 1)}</span>${escape(slide.dataset.nav)}`;
    nav.append(link);
  });

  function contactTrack(frames, total, side) {
    const segments = [];
    for (const frame of frames) {
      const last = segments[segments.length - 1];
      if (last && frame === last[1] + 1) last[1] = frame;
      else segments.push([frame, frame]);
    }
    return `<div class="contact-track"><span>${side}</span><div class="track" role="img" aria-label="${side}物理接触 ${frames.length} 帧">${segments.map(([a,b]) => `<span class="segment" style="left:${a / total * 100}%;width:${(b-a+1) / total * 100}%"></span>`).join('')}</div><span>${frames.length} 帧</span></div>`;
  }

  document.querySelectorAll('.media-slot').forEach(slot => {
    const key = slot.dataset.run;
    const d = data[key];
    slot.innerHTML = `<div class="media-card"><div class="video-wrap"><video controls playsinline preload="metadata" poster="${d.poster}" aria-label="${key} 原生 rollout 合成视频"><source src="${d.video}" type="video/mp4"></video><span class="video-badge">RUN ${key} · ${d.fps} Hz</span><p class="media-error" hidden>视频未加载。请将 assets 文件夹与网页一起保留，或打开下方视频文件。</p></div><div class="video-tools"><button data-action="play" aria-label="播放或暂停 ${key}">播放</button><button data-action="back" aria-label="${key} 上一帧">−1 帧</button><button data-action="forward" aria-label="${key} 下一帧">+1 帧</button><select aria-label="${key} 播放速度"><option value="0.25" selected>0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option></select><output>0 / ${d.frames - 1}</output></div><div class="video-seek"><input type="range" min="0" max="${d.frames-1}" value="0" aria-label="${key} 视频帧位置"></div><p class="contact-caption">物理接触时间线 · 绿色表示传感器门控为接触</p><div class="contact-tracks">${contactTrack(d.contacts.left,d.frames,'左')}${contactTrack(d.contacts.right,d.frames,'右')}</div><div class="media-caption">上：场景与腕部 RGB　下：双侧触觉 · ${d.frames} 帧 / ${d.duration.toFixed(2)} 秒模拟时间 · <a href="${d.video}" target="_blank" rel="noopener">打开视频 ↗</a></div></div>`;
    const video = slot.querySelector('video');
    const range = slot.querySelector('input');
    const output = slot.querySelector('output');
    const play = slot.querySelector('[data-action=play]');
    video.playbackRate = .25;
    function update() {
      const frame = Math.min(d.frames - 1, Math.max(0, Math.floor(video.currentTime * d.fps + .001)));
      range.value = frame;
      output.textContent = `${frame} / ${d.frames-1}`;
    }
    function seek(frame) {
      video.pause();
      video.currentTime = Math.max(0, Math.min(d.frames-1, frame)) / d.fps;
      update();
    }
    play.addEventListener('click', () => toggleVideo(video));
    slot.querySelector('[data-action=back]').addEventListener('click', () => seek(Math.floor(video.currentTime*d.fps+.001)-1));
    slot.querySelector('[data-action=forward]').addEventListener('click', () => seek(Math.floor(video.currentTime*d.fps+.001)+1));
    range.addEventListener('input', () => seek(Number(range.value)));
    slot.querySelector('select').addEventListener('change', e => { video.playbackRate = Number(e.target.value); });
    video.addEventListener('timeupdate', update);
    video.addEventListener('seeked', update);
    video.addEventListener('play', () => { play.textContent = '暂停'; });
    video.addEventListener('pause', () => { play.textContent = '播放'; });
    video.addEventListener('ended', () => { play.textContent = '重播'; });
    video.addEventListener('error', () => { slot.querySelector('.media-error').hidden = false; });
  });
  function toggleVideo(video) {
    if (!video) return;
    if (video.paused) {
      if (video.ended) video.currentTime = 0;
      video.play().catch(() => toast('请点击视频原生播放按钮；也可直接打开视频文件。'));
    } else video.pause();
  }

  document.querySelectorAll('.evidence-slot').forEach(slot => {
    const d = data[slot.dataset.run];
    slot.innerHTML = `<details><summary>查看本次运行的公开证据摘要</summary><p class="run-id">${escape(d.id)}</p><div class="evidence-links">${d.evidence.map(e => `<a href="${e.url}" target="_blank" rel="noopener">${escape(e.label)} ↗</a>`).join('')}</div></details>`;
  });

  const compareKeys = ['115502','120900','133133'];
  const compareLabels = ['示范动作回放','BC 残差目标','BC 绝对目标'];
  const compareRoot = document.querySelector('#comparison-videos');
  compareKeys.forEach((key,i) => {
    const d=data[key];
    const div=document.createElement('article');
    div.className='compare-card';
    div.innerHTML=`<header><b>${key} · ${compareLabels[i]}</b><span class="pill ${i===0?'success':'danger'}">${i===0?'任务成功':'任务失败'}</span></header><video muted playsinline preload="metadata" poster="${d.poster}" aria-label="同步对照 ${key}"><source src="${d.video}" type="video/mp4"></video><p>最大相邻目标跳变 <b>${d.maxStep.toFixed(4)} rad</b></p>`;
    compareRoot.append(div);
  });
  const compareVideos=[...compareRoot.querySelectorAll('video')];
  compareVideos.forEach(v=>v.addEventListener('loadeddata',()=>{v.currentTime=0.000001;},{once:true}));
  const W=900,H=155,left=37,right=13,top=12,bottom=26,maxY=4;
  const x=i=>left+i/169*(W-left-right);
  const y=v=>H-bottom-v/maxY*(H-top-bottom);
  const path=values=>values.map((v,i)=>(i?'L':'M')+x(i).toFixed(2)+','+y(v).toFixed(2)).join(' ');
  document.querySelector('#deviation-chart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="关节目标偏离对照。残差模型最大偏差 3.689 rad，绝对目标模型最大偏差 0.206 rad。"><title>相对示范的逐帧最大关节目标偏差</title>${[0,1,2,3,4].map(v=>`<line x1="${left}" y1="${y(v)}" x2="${W-right}" y2="${y(v)}" stroke="#e3e7dc"/><text x="${left-9}" y="${y(v)+4}" font-size="9" text-anchor="end" fill="#7d8775">${v}</text>`).join('')}${[0,20,50,100,169].map(i=>`<text x="${x(i)}" y="${H-7}" text-anchor="middle" font-size="9" fill="#7d8775">${i}</text>`).join('')}<path d="${path(data['120900'].deviation)}" fill="none" stroke="#c85c49" stroke-width="2"/><path d="${path(data['133133'].deviation)}" fill="none" stroke="#b88939" stroke-width="2"/><line id="chart-cursor" x1="${x(0)}" x2="${x(0)}" y1="${top}" y2="${H-bottom}" stroke="#255c51" stroke-dasharray="3 3"/></svg>`;
  function setSyncFrame(frame, seekVideos=true) {
    frame=Math.max(0,Math.min(169,Math.round(frame)));
    syncRange.value=frame;
    document.querySelector('#sync-frame').textContent=`第 ${frame} / 169 帧`;
    const cursor=document.querySelector('#chart-cursor');
    cursor.setAttribute('x1',x(frame));cursor.setAttribute('x2',x(frame));
    if (seekVideos) compareVideos.forEach(v=>{v.currentTime=frame/60;});
  }
  function stopSync() {
    syncPlaying=false;
    cancelAnimationFrame(syncRaf);
    compareVideos.forEach(v=>v.pause());
    document.querySelector('#sync-play').textContent='同步播放';
  }
  async function playSync() {
    if(syncPlaying){stopSync();return;}
    if(Number(syncRange.value)>=169)setSyncFrame(0);
    compareVideos.forEach(v=>{v.playbackRate=Number(syncSpeed.value);v.currentTime=Number(syncRange.value)/60;});
    const results=await Promise.allSettled(compareVideos.map(v=>v.play()));
    if(results.some(r=>r.status==='rejected')){stopSync();toast('视频播放未就绪，请重试或使用逐帧滑块。');return;}
    syncPlaying=true;
    document.querySelector('#sync-play').textContent='暂停对照';
    function tick(){
      if(!syncPlaying)return;
      const frame=Math.min(169,Math.floor(compareVideos[0].currentTime*60+.001));
      setSyncFrame(frame,false);
      compareVideos.slice(1).forEach(v=>{if(Math.abs(v.currentTime-compareVideos[0].currentTime)>1/30)v.currentTime=compareVideos[0].currentTime;});
      if(compareVideos[0].ended){stopSync();setSyncFrame(169);return;}
      syncRaf=requestAnimationFrame(tick);
    }
    tick();
  }
  document.querySelector('#sync-play').addEventListener('click',playSync);
  syncRange.addEventListener('input',()=>{stopSync();setSyncFrame(Number(syncRange.value));});
  document.querySelector('#sync-prev').addEventListener('click',()=>{stopSync();setSyncFrame(Number(syncRange.value)-1);});
  document.querySelector('#sync-next').addEventListener('click',()=>{stopSync();setSyncFrame(Number(syncRange.value)+1);});
  syncSpeed.addEventListener('change',()=>{compareVideos.forEach(v=>{v.playbackRate=Number(syncSpeed.value);});});

  const ledger=[
    ['115502','示范动作物理回放','成功','success','通过','success','源示范 + 重定向'],
    ['120900','BC 残差模型','失败','danger','通过','success','169 次决策复算通过'],
    ['133133','BC 绝对目标模型','失败','danger','未通过','danger','169 次决策复算通过'],
    ['130903','几何反馈教师','成功','success','通过','success','教师源码 / 哈希留证'],
    ['131910','Door 示范脚手架','未完成','warn','未完整验收','warn','范围变更停止收据']
  ];
  document.querySelector('#result-ledger').innerHTML='<div class="ledger-row ledger-head"><span>运行 / 动作来源</span><span>原生任务结果</span><span>触觉审计</span><span>来源与决策证据</span></div>'+ledger.map(r=>`<div class="ledger-row"><div><b>${r[0]}</b><small>${r[1]}</small></div><span class="pill ${r[3]}">${r[2]}</span><span class="pill ${r[5]}">${r[4]}</span><span>${r[6]}</span></div>`).join('');

  function show(index,updateHash=true){
    current=Math.max(0,Math.min(slides.length-1,index));
    stopSync();document.querySelectorAll('video').forEach(v=>v.pause());
    slides.forEach((s,i)=>{s.classList.toggle('active',i===current);s.setAttribute('aria-hidden',String(i!==current));});
    [...nav.children].forEach((a,i)=>{a.classList.toggle('active',i===current);if(i===current)a.setAttribute('aria-current','step');else a.removeAttribute('aria-current');});
    document.querySelector('#section-label').textContent=slides[current].dataset.label;
    document.querySelector('#page-count').textContent=`${pad(current+1)} / ${pad(slides.length)}`;
    document.querySelector('#progress').style.width=`${(current+1)/slides.length*100}%`;
    document.querySelector('#prev').disabled=current===0;
    document.querySelector('#next-page').disabled=current===slides.length-1;
    document.querySelector('#note-text').textContent=slides[current].dataset.note;
    document.title=`${slides[current].dataset.nav} · TacHarness 组会报告`;
    if(updateHash){try{history.replaceState(null,'','#'+slides[current].id);}catch{location.hash=slides[current].id;}}
    window.scrollTo({top:0,behavior:'instant'});
  }
  function fromHash(){const index=slides.findIndex(s=>'#'+s.id===location.hash);show(index<0?0:index,false);}
  document.querySelector('#prev').addEventListener('click',()=>show(current-1));
  document.querySelector('#next-page').addEventListener('click',()=>show(current+1));
  document.querySelectorAll('[data-next]').forEach(b=>b.addEventListener('click',()=>show(current+1)));
  nav.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;e.preventDefault();show(slides.findIndex(s=>'#'+s.id===a.hash));});
  window.addEventListener('hashchange',fromHash);
  function toggleNotes(){notes.hidden=!notes.hidden;document.querySelector('#notes-toggle').setAttribute('aria-pressed',String(!notes.hidden));}
  document.querySelector('#notes-toggle').addEventListener('click',toggleNotes);
  document.querySelector('#notes-close').addEventListener('click',toggleNotes);
  async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else toast('此浏览器不支持网页全屏，请使用浏览器全屏功能。');}catch{toast('无法进入网页全屏，请使用浏览器全屏功能。');}}
  document.querySelector('#fullscreen').addEventListener('click',fullscreen);
  document.addEventListener('keydown',e=>{
    if(e.altKey||e.ctrlKey||e.metaKey||/INPUT|SELECT|TEXTAREA|BUTTON|VIDEO/.test(e.target.tagName)||e.target.isContentEditable)return;
    if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();show(current+1);}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();show(current-1);}
    else if(e.key==='Home'){e.preventDefault();show(0);}
    else if(e.key==='End'){e.preventDefault();show(slides.length-1);}
    else if(e.key.toLowerCase()==='n'){toggleNotes();}
    else if(e.key.toLowerCase()==='f'){fullscreen();}
    else if(e.key===' '){e.preventDefault();if(slides[current].id==='comparison')playSync();else toggleVideo(slides[current].querySelector('video'));}
    else if(e.key==='Escape'&&!notes.hidden){toggleNotes();}
  });
  fromHash();
})();
