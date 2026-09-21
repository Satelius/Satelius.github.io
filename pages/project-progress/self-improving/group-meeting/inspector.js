/* Compact reader for saved model input/output. */
const inspection=document.createElement('details');
inspection.id='inspection';
inspection.innerHTML=`<summary>Provider 输入与返回</summary>
<div class="trace-controls"><button id="trace-prev">上一条</button><label>调用 <select id="trace-select"></select></label><button id="trace-next">下一条</button></div>
<p id="io-source" class="footnote"></p>
<div class="io-grid"><label>输入<textarea id="io-input" readonly spellcheck="false"></textarea></label>
<label>返回<textarea id="io-output" readonly spellcheck="false"></textarea></label></div>
<div id="io-images" class="recovered-images"></div><p id="io-downloads" class="player-tools"></p>`;
document.querySelector('#budget').before(inspection);
document.querySelector('#budget').nextElementSibling.textContent='视频菜单覆盖打包时已保存的失败录像，具体任务见名称与证据。P7 完整矩阵及 P9 早期 metrics-only 运行没有视频。';
let ioEntries=[],ioIndex=0;
const ioSelect=document.querySelector('#trace-select');
function readable(value){
 if(value==null)return '未记录';
 if(typeof value!=='string')return JSON.stringify(value,null,2);
 try{return JSON.stringify(JSON.parse(value),null,2);}catch{return value;}
}
function renderIO(){
 const e=ioEntries[ioIndex];if(!e)return;
 ioSelect.value=String(ioIndex);
 document.querySelector('#io-source').textContent=e.source;
 document.querySelector('#io-input').value=e.input;
 document.querySelector('#io-output').value=e.output;
 const images=document.querySelector('#io-images');images.replaceChildren();
 for(const src of e.images||[]){const img=document.createElement('img');img.src=src;img.alt='请求图片';images.append(img);}
 const downloads=document.querySelector('#io-downloads');downloads.replaceChildren();
 for(const [href,text] of e.downloads||[]){if(href){const a=document.createElement('a');a.href=href;a.textContent=text;a.download='';downloads.append(a);}}
 document.querySelector('#trace-prev').disabled=ioIndex===0;
 document.querySelector('#trace-next').disabled=ioIndex===ioEntries.length-1;
}
function populateIO(){ioSelect.replaceChildren();ioEntries.forEach((e,i)=>{const o=document.createElement('option');o.value=i;o.textContent=e.label;ioSelect.append(o);});renderIO();}
function resetIO(){
 const run=data.videos[Number(document.querySelector('#episodes').value)];
 ioEntries=run.trace.entries.map(e=>{
  const r=e.request||{},s=e.step||{},a=r.visual_assessment||s.visual_assessment;
  const input=[`任务：${run.trace.task||run.task}`,s.stage_id?`阶段：${s.stage_id}`:null,s.target?`目标：${s.target}`:null,'完整请求：未记录'].filter(Boolean).join('\n\n');
  const output=[r.token||s.act?`动作：${r.token||s.act}`:null,a?.observation?`观察：${a.observation}`:null,
   a?Object.entries(a).filter(([k])=>k!=='observation').map(([k,v])=>`${k}：${v}`).join('\n'):null,
   r.subgoal_count!=null?`子目标数：${r.subgoal_count}`:null,r.error_class?`调用错误：${r.error_class}`:null].filter(Boolean).join('\n\n')||'未记录';
  return {label:r.role==='planner'?`Planner · ${r.phase||'规划'}`:`Actor · 步 ${r.step??s.i} · ${r.token||s.act||''}`,source:'历史记录 · 保存字段',input,output};
 });
 ioIndex=0;if(window.appendReplayEntries)window.appendReplayEntries();populateIO();
}
ioSelect.onchange=()=>{ioIndex=Number(ioSelect.value);renderIO();};
document.querySelector('#trace-prev').onclick=()=>{ioIndex=Math.max(0,ioIndex-1);renderIO();};
document.querySelector('#trace-next').onclick=()=>{ioIndex=Math.min(ioEntries.length-1,ioIndex+1);renderIO();};
document.querySelector('#episodes').addEventListener('change',resetIO);
if(data)resetIO();
