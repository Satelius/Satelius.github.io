'use strict';

(() => {
  const D = window.ROLLOUT_DATA;
  const $ = id => document.getElementById(id);
  if (!D || !Array.isArray(D.runs) || D.runs.length !== 2) {
    $('load-status').textContent = '未能加载本地证据。请把整个文件夹放在一起，并确认data.js与index.html同目录。';
    $('load-status').className = 'error-note';
    return;
  }
  const names = {MV_FWD:'向前', MV_BACK:'向后', MV_LEFT:'向左', MV_RIGHT:'向右', MV_UP:'向上', MV_DOWN:'向下', GRASP:'闭合夹爪', RELEASE:'释放夹爪', DONE:'停止'};
  const abbreviations = {MV_FWD:'前',MV_BACK:'后',MV_LEFT:'左',MV_RIGHT:'右',MV_UP:'上',MV_DOWN:'下',GRASP:'合',RELEASE:'开',DONE:'停'};
  const directionNames = {MV_FWD:'+X',MV_BACK:'−X',MV_LEFT:'+Y',MV_RIGHT:'−Y',MV_UP:'+Z',MV_DOWN:'−Z'};
  const state = {run:0, decision:0, frame:0, stopAt:null};
  const video = $('decision-video');
  let frameCallback = null;
  let animationCallback = null;
  const fmt = (value, precision=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(precision);
  const vector = (values, precision=4) => Array.isArray(values) ? '['+values.map(value=>fmt(value,precision)).join(', ')+']' : '—';
  const json = value => JSON.stringify(value,null,2);
  const escape = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const kind = token => token === 'MV_FWD' ? 'forward' : token === 'MV_DOWN' ? 'down' : token === 'GRASP' ? 'grasp' : 'other';
  const run = () => D.runs[state.run];
  const decision = () => run().decisions[state.decision];
  const contactText = frame => frame.contact.left || frame.contact.right ? `左${frame.contact.left?'有':'无'} / 右${frame.contact.right?'有':'无'}` : '左0 / 右0';
  const seconds = value => `${fmt(value,1)}秒`;

  function link(id, path) {
    const element=$(id);
    if (path) { element.href=path; element.removeAttribute('aria-disabled'); }
    else { element.removeAttribute('href'); element.setAttribute('aria-disabled','true'); }
  }

  function seek(time) {
    if (video.readyState >= 1) video.currentTime=Math.max(0,Math.min(time,Math.max(0,video.duration-.002)));
    else video.addEventListener('loadedmetadata',()=>{video.currentTime=time;},{once:true});
  }

  function drawTimeline() {
    $('token-timeline').replaceChildren();
    for (const d of run().decisions) {
      const button=document.createElement('button');
      button.className=kind(d.token)+(d.index===state.decision?' selected':'');
      button.title=`${run().id} 决策#${String(d.index).padStart(2,'0')} · ${d.token} · ${fmt(d.physicalStartS,1)}–${fmt(d.physicalEndS,1)}秒`;
      button.setAttribute('aria-label',button.title);
      button.setAttribute('aria-pressed',String(d.index===state.decision));
      button.innerHTML=`<small>${String(d.index).padStart(2,'0')}</small><span>${abbreviations[d.token]}</span>`;
      button.addEventListener('click',()=>selectDecision(d.index));
      $('token-timeline').append(button);
    }
  }

  function renderHttp(d) {
    const box=$('http-attempts'); box.replaceChildren();
    for (const attempt of d.httpAttempts) {
      const row=document.createElement('div');
      row.className='http-attempt '+(attempt.status==='ok'?'ok':'failed');
      const frozen=attempt.freeze_before?.unchanged && attempt.freeze_after?.unchanged;
      const label=attempt.http_status===200 ? `HTTP200 → ${attempt.token}` : attempt.reason==='transport_timeout' || attempt.reason==='connection_timeout' ? '等待超时' : attempt.reason || attempt.status;
      row.innerHTML=`<span>第${attempt.attempt}次 · ${fmt(attempt.elapsed_s,2)}s</span><b>${escape(label)}</b><span>${frozen?'冻结核对通过':'详见收据'}</span>`;
      box.append(row);
    }
    if (d.httpAttempts.length>1) {
      const paragraph=document.createElement('p'); paragraph.className='caption';
      paragraph.textContent='重试使用相同请求字节与同一观测，场景/目标计时器/动作历史不推进；最后只执行一次返回的合法token。';
      box.append(paragraph);
    }
    const links=document.createElement('div'); links.className='raw-actions';
    for (let i=0;i<(d.rawLinks.responses||[]).length;i++) {
      const a=document.createElement('a');a.href=d.rawLinks.responses[i];a.download='';a.textContent=`响应${i+1}回执原件`;links.append(a);
    }
    box.append(links);
  }

  function renderMovement(d) {
    const before=d.interpreter.initial_tcp_position_base_m;
    const delta=d.actualDelta.map(value=>value*1000);
    const gripper=d.interpreter.gripper_target;
    const rows=[['起始TCP（基座，m）',vector(before)],['固定位置目标（基座，m）',vector(d.target)],['执行后TCP（基座，m）',vector(d.actualAfter)],['实际位移XYZ（mm）',vector(delta,2)],['夹爪持续目标',gripper<0?'−1 · 闭合':'+1 · 打开']];
    if (d.projectionMm!=null) rows.push(['沿请求方向位移',`${fmt(d.projectionMm,2)}mm${d.projectionMm<0?' · 实际反向':''}`],['跨轴偏移',`${fmt(d.crossMm,2)}mm`]);
    $('movement-detail').innerHTML=rows.map(([label,value])=>`<div><span>${escape(label)}</span><b>${escape(value)}</b></div>`).join('');
    $('execution-stats').innerHTML=`<div><strong>${d.frameEnd-d.frameStart}帧</strong><span>实际控制区间</span></div><div><strong>${fmt(d.physicalEndS-d.physicalStartS,2)}s</strong><span>物理执行时间</span></div><div><strong>${fmt(d.waitS,2)}s</strong><span>本决策请求流程等待</span></div>`;
  }

  function explanation(d) {
    if (d.knownWrong) return '独立审计标记：这是过早的空闭合。执行前TCP距方块675.9mm、高出方块671.4mm，零接触/零力。原始finish标签未改写，错误标记来自额外哈希收据。闭合仍执行位置保持与朝下姿态纠偏；随后移动继续保持夹爪闭合目标。';
    if (d.httpAttempts.length>1) return '本次第一次发送等待约35秒后超时，同一三图与请求原文重试成功。HTTP等待期间物理状态、目标计时器与移动历史冻结，返回的合法token只展开执行一次5帧。请求流程等待包含图像编码和收据开销；每次HTTP发送耗时列在右侧。';
    if (d.index===49) return '这是该次运行的最后5帧。末尾位置取自自动reset前的原生终态；源final_state.npz是超时后重置的新状态，不能当作本episode终点。250帧结束后，原生仍判定未成功。';
    if (d.token==='MV_DOWN' && d.projectionMm<0) return `教师选择向下，解释器也把目标放在当前TCP下方，但执行后的Z实际增加${fmt(d.actualDelta[2]*1000,2)}mm。沿请求方向投影${fmt(d.projectionMm,2)}mm为负，说明动作的实际效果反向。原因不能仅由这个token确定。`;
    if (d.index===0) return '这是reset后的第一次决策，模型没有移动历史。三张图在执行前采样；精确TCP只供解释器控制和本网页审计，未放入模型请求。实际发送仅有固定system和当次user两个message。';
    if (state.run===1 && d.index>11) return '这是B空闭合之后的决策。GRASP不属于移动词，因此不会占用最近五个移动历史名额；后续没有RELEASE，解释器继续沿用−1夹爪闭合目标。每次只看到本次三图与有限移动历史。';
    return '模型根据当前三图和有限移动历史选一个词。解释器在执行前固定目标，然后每帧用当前控制点纠偏。下方可以把设定目标、实际位移、原生动作与响应收据逐项对照。';
  }

  function renderFrame(index,{seekVideo=false}={}) {
    state.frame=Math.max(0,Math.min(index,run().frames.length-1));
    const f=run().frames[state.frame];
    $('frame-range').value=state.frame;
    $('frame-number').textContent=`#${String(f.index).padStart(3,'0')}`;
    $('prev-frame').disabled=state.frame===0;
    $('next-frame').disabled=state.frame===run().frames.length-1;
    $('frame-detail').innerHTML=`<div class="frame-facts"><div><span>视频 / 原记录时间</span><strong>${fmt(f.timeS,2)}s</strong></div><div><span>该帧执行后物理边界</span><strong>${fmt(f.afterTimeS,2)}s</strong></div><div><span>TCP · 基座XYZ(m)</span><strong>${escape(vector(f.tcp,4))}</strong></div><div><span>双指接触与力</span><strong>${escape(contactText(f))} · ${fmt(f.forceN.left,2)}/${fmt(f.forceN.right,2)}N</strong></div></div><div class="frame-action"><span class="caption">实际7维动作 · [dx,dy,dz,rx,ry,rz,gripper]</span><code>${escape(vector(f.action,5))}</code></div><p class="caption">${f.terminal?'原生超时终态已在自动reset前捕获。':'该帧是动作执行后的真实状态。'}视频PTS从0开始，帧末状态位于下一控制边界；全程触觉图为无接触归零的黑图，已实际发送。</p>`;
    if (seekVideo) seek(f.timeS+.0005);
  }

  function renderRows(d) {
    const frames=run().frames.filter(f=>f.index>=d.frameStart&&f.index<d.frameEnd);
    $('frame-rows').innerHTML=frames.map(f=>`<tr><td>${f.index}</td><td>${fmt(f.timeS,2)}</td><td>${escape(vector(f.action,6))}</td><td>${escape(vector(f.tcp,5))}</td><td>${escape(contactText(f))}</td></tr>`).join('');
  }

  function selectDecision(index,{seekVideo=true,frame=null}={}) {
    state.decision=Math.max(0,Math.min(Number(index),run().decisions.length-1));
    const d=decision();
    const changedVideo=video.dataset.run!==run().id;
    if (changedVideo) {video.pause();video.src=run().video;video.poster=run().decisions[0].images.scene;video.dataset.run=run().id;state.stopAt=null;}
    $('decision-range').max=run().decisions.length-1;
    $('decision-range').value=state.decision;
    $('decision-position').textContent='#'+String(d.index).padStart(2,'0');
    $('decision-id').textContent=`运行${run().id} · ${d.id} · 第${d.index+1}次决策`;
    $('decision-token').textContent=`${d.token} · ${names[d.token]}`;
    $('decision-meta').innerHTML=`<span>执行帧 [${d.frameStart}, ${d.frameEnd})</span><span>物理 ${fmt(d.physicalStartS,1)}–${fmt(d.physicalEndS,1)}s</span><span>教师温度0</span>`;
    $('decision-note').textContent=explanation(d);
    $('decision-note').className='decision-note'+(d.knownWrong||d.projectionMm<0?' warning':'');
    for (const [id,key] of [['image-scene','scene'],['image-wrist','wrist'],['image-tactile','tactile']]) {
      $(id).src=d.images[key];
      $(id).alt=`运行${run().id} ${d.id} 的真实${key==='scene'?'场景':key==='wrist'?'腕部':'双指触觉'}输入图`;
    }
    $('history-tokens').replaceChildren();
    if (!d.history.length) {const empty=document.createElement('span');empty.textContent='[] · 尚无已执行移动';empty.className='caption';$('history-tokens').append(empty);}
    for (const token of d.history) {const c=document.createElement('code');c.textContent=token;$('history-tokens').append(c);}
    $('user-text').textContent=d.userText;
    $('system-text').textContent=d.systemPrompt;
    $('request-text').textContent=d.requestText;
    $('response-text').textContent=d.responseText;
    $('interpreter-text').textContent=json(d.interpreter);
    $('finish-text').textContent=json(d.finish);
    $('selected-token').textContent=d.token;
    link('request-link',d.rawLinks.request);link('inference-link',d.rawLinks.inference);
    link('finish-link',d.rawLinks.finish);link('selected-link',d.rawLinks.selected);
    $('prev-decision').disabled=state.decision===0;
    $('next-decision').disabled=state.decision===run().decisions.length-1;
    renderHttp(d);renderMovement(d);renderRows(d);drawTimeline();
    renderFrame(frame??d.frameStart,{seekVideo:false});
    if (seekVideo) {video.pause();state.stopAt=null;seek(d.physicalStartS+.0005);}
  }

  function selectRun(id,index=0) {
    const selected=D.runs.findIndex(r=>r.id===id);
    if (selected<0) return;
    state.run=selected;
    for (const id of ['A','B']) {const button=$('choose-'+id.toLowerCase());button.classList.toggle('active',run().id===id);button.setAttribute('aria-pressed',String(run().id===id));}
    selectDecision(index);
  }

  function selectFrame(index) {
    const i=Math.max(0,Math.min(Number(index),run().frames.length-1));
    const owner=run().decisions.findIndex(d=>d.frameStart<=i&&i<d.frameEnd);
    if (owner!==state.decision&&owner>=0) selectDecision(owner,{seekVideo:false,frame:i});
    else renderFrame(i);
    video.pause();state.stopAt=null;seek(run().frames[i].timeS+.0005);
  }

  function renderSummary() {
    for (const r of D.runs) {
      const v=$('video-'+r.id.toLowerCase());v.src=r.video;v.poster=r.decisions[0].images.scene;
      const report=r.report;
      $(r.id.toLowerCase()+'-facts').innerHTML=`<div><b>${report.native_frame_count}帧</b><span>5秒物理过程</span></div><div><b>${r.decisions.length}次</b><span>教师决策</span></div><div><b>${report.teacher_inference_requests}次</b><span>HTTP推理请求</span></div><div><b>${Math.floor(report.elapsed_s/60)}分${Math.round(report.elapsed_s%60)}秒</b><span>实际运行墙钟</span></div>`;
    }
  }

  function renderMapping() {
    $('mapping-rows').innerHTML=D.mapping.tokens.map(token=>{
      const movement=!!D.mapping.directionMap[token];
      const direction=movement?`${directionNames[token]} · ${names[token]}`:names[token];
      const target=movement?'当前TCP + 方向 × 步长':token==='DONE'?'没有执行目标':'固定当前TCP位置';
      const extra=token==='GRASP'?'闭合−1，仍控制手臂5帧':token==='RELEASE'?'打开+1，仍控制手臂5帧':token==='DONE'?'0帧，停止本次尝试':'保持此前夹爪目标，执行5帧';
      const a=D.runs.find(r=>r.id==='A').tokenCounts[token]||0,b=D.runs.find(r=>r.id==='B').tokenCounts[token]||0;
      return `<tr><td>${token}</td><td>${direction}</td><td>${target}</td><td>${extra}</td><td>${a} / ${b}</td></tr>`;
    }).join('');
  }

  function renderMetrics() {
    const rows=[['全程前向投影中位','8.687mm','35.334mm'],['事前前向门槛','原基线','≥17.374mm · 达标'],['共同前10次前移：跨轴中位','0.927mm','10.311mm'],['下探实际反向次数','3 / 3','17 / 18'],['下探投影中位','−5.639mm','−38.678mm'],['原生成功 / 接触帧','否 / 0','否 / 0']];
    $('metric-comparison').innerHTML='<div class="metric-row header"><span>从实际轨迹测量</span><span>A</span><span>B</span></div>'+rows.map(([label,a,b])=>`<div class="metric-row"><span>${label}</span><span class="metric-a">${a}</span><span class="metric-b">${b}</span></div>`).join('');
  }

  function drawHeightChart() {
    const width=600,height=270,left=58,right=16,top=20,bottom=42;
    const values=D.runs.flatMap(r=>r.frames.map(f=>f.tcp[2]));
    let min=Math.floor(Math.min(...values)*10)/10-.01,max=Math.ceil(Math.max(...values)*10)/10+.01;
    const x=time=>left+(width-left-right)*time/5;
    const y=value=>height-bottom-(height-top-bottom)*(value-min)/(max-min);
    let content='';
    for(let i=0;i<=4;i++) {const value=min+(max-min)*i/4,py=y(value);content+=`<line x1="${left}" y1="${py}" x2="${width-right}" y2="${py}" stroke="#e1e7e9"/><text x="${left-9}" y="${py+4}" text-anchor="end" fill="#607080" font-size="11">${fmt(value,2)}</text>`;}
    for(let i=0;i<=5;i++) content+=`<text x="${x(i)}" y="${height-20}" text-anchor="middle" fill="#607080" font-size="11">${i}s</text>`;
    content+=`<text x="10" y="15" fill="#607080" font-size="11">Z(m)</text>`;
    for(const r of D.runs) {
      const before=r.decisions[0].interpreter.initial_tcp_position_base_m[2];
      const points=[[0,before],...r.frames.map(f=>[f.afterTimeS,f.tcp[2]])];
      const path=points.map((point,i)=>`${i?'L':'M'}${fmt(x(point[0]),2)},${fmt(y(point[1]),2)}`).join(' ');
      content+=`<path d="${path}" fill="none" stroke="${r.id==='A'?'#176b9a':'#b86621'}" stroke-width="2"/>`;
    }
    $('height-chart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="A和B的实际TCP基座高度随5秒物理时间变化，B末尾高度更高"><title>TCP基座高度，来自原生逐帧审计状态</title>${content}</svg>`;
  }

  function renderEvidence() {
    const extras=[{title:'完整中文解释',path:'analysis_notes.md'},{title:'副本与源文件哈希清单',path:'evidence_manifest.json'},{title:'本地展示数据',path:'data.js'},{title:'动作解释器归档源码',path:D.mapping.source},{title:'网页验证结果',path:'validation/web_checks.json'},{title:'全部数据核对脚本',path:'build_evidence.py'}];
    const all=[...D.evidence,...extras];
    $('evidence-links').replaceChildren();
    for(const item of all) {const a=document.createElement('a');a.href=item.path;a.download='';a.innerHTML=`${escape(item.title)}<span>↓ 原件 / 副本</span>`;$('evidence-links').append(a);}
  }

  $('choose-a').addEventListener('click',()=>selectRun('A'));
  $('choose-b').addEventListener('click',()=>selectRun('B'));
  $('prev-decision').addEventListener('click',()=>selectDecision(state.decision-1));
  $('next-decision').addEventListener('click',()=>selectDecision(state.decision+1));
  $('decision-range').addEventListener('input',event=>selectDecision(event.target.value));
  $('frame-range').addEventListener('input',event=>selectFrame(event.target.value));
  $('prev-frame').addEventListener('click',()=>selectFrame(state.frame-1));
  $('next-frame').addEventListener('click',()=>selectFrame(state.frame+1));
  for(const button of document.querySelectorAll('[data-jump]')) button.addEventListener('click',()=>{const [id,index]=button.dataset.jump.split(':');selectRun(id,Number(index));$('explorer').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});});
  $('play-decision').addEventListener('click',()=>{const d=decision();state.stopAt=d.physicalEndS;seek(d.physicalStartS+.0005);video.play().catch(()=>{$('load-status').textContent='浏览器未允许自动播放；可用视频本身的播放按钮。';});});
  function checkClipEnd(mediaTime) {
    if(state.stopAt==null || mediaTime < state.stopAt-1/50-.0001) return;
    const end=state.stopAt;
    state.stopAt=null;
    video.pause();
    // Keep the last included frame visible; the next decision starts at end.
    seek(end-.002);
  }
  function scheduleVideoFrame() {
    if(video.paused) return;
    if(typeof video.requestVideoFrameCallback==='function') {
      frameCallback=video.requestVideoFrameCallback((_,metadata)=>{
        frameCallback=null;checkClipEnd(metadata.mediaTime);scheduleVideoFrame();
      });
    } else {
      animationCallback=requestAnimationFrame(()=>{
        animationCallback=null;checkClipEnd(video.currentTime);scheduleVideoFrame();
      });
    }
  }
  video.addEventListener('play',scheduleVideoFrame);
  video.addEventListener('pause',()=>{
    if(frameCallback!=null) {video.cancelVideoFrameCallback(frameCallback);frameCallback=null;}
    if(animationCallback!=null) {cancelAnimationFrame(animationCallback);animationCallback=null;}
  });
  video.addEventListener('timeupdate',()=>{
    if(typeof video.requestVideoFrameCallback!=='function') checkClipEnd(video.currentTime);
    if(!$('follow-video').checked) return;
    const frame=Math.max(0,Math.min(Math.floor(video.currentTime*50),run().frames.length-1));
    const owner=run().decisions.findIndex(d=>d.frameStart<=frame&&frame<d.frameEnd);
    if(owner>=0&&owner!==state.decision) selectDecision(owner,{seekVideo:false,frame});
    else if(frame!==state.frame) renderFrame(frame);
  });
  for(const button of document.querySelectorAll('.image-open')) button.addEventListener('click',()=>{const img=button.querySelector('img');$('large-image').src=img.src;$('large-image').alt=img.alt;$('large-image-caption').textContent=img.alt+' · 实际请求PNG原字节';$('image-dialog').showModal();});
  $('close-image').addEventListener('click',()=>$('image-dialog').close());
  $('image-dialog').addEventListener('click',event=>{if(event.target===$('image-dialog')) $('image-dialog').close();});

  renderSummary();renderMapping();renderMetrics();drawHeightChart();renderEvidence();selectRun('A',0);
  $('load-status').textContent=`本地证据已加载：${D.runs.reduce((sum,r)=>sum+r.decisions.length,0)}次决策、300张实际输入图、500控制帧。页面仅读取同文件夹资产，没有教师请求或仿真启动。`;
  window.ROLLOUT_VIEWER_READY=true;
})();
