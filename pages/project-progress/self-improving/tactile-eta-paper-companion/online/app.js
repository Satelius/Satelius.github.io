const $=s=>document.querySelector(s);
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data,run,videoURL;
const video=$('#video');
function indexAt(t){let index=0;for(let i=0;i<run.video_times.length;i++){if(run.video_times[i]<=t+0.0002)index=i;else break;}return index;}
function seek(index){index=Math.max(0,Math.min(run.video_times.length-1,index));video.pause();video.currentTime=run.video_times[index]+0.0001;updateFrame();}
function updateFrame(){if(!run)return;const i=indexAt(video.currentTime);$('#frame-label').textContent=`${i+1} / ${run.samples} 帧 · 仿真 ${Number(run.simulation_times[i]||0).toFixed(3)} s`;}
function showRun(index){
  run=data.runs[index];video.pause();video.removeAttribute('src');video.load();
  if(videoURL){URL.revokeObjectURL(videoURL);videoURL=null;}
  const selected=run;
  video.dataset.run='';video.setAttribute('aria-busy','true');
  fetch(run.video).then(r=>{if(!r.ok)throw Error('video');return r.blob();}).then(blob=>{
    if(run!==selected)return;
    videoURL=URL.createObjectURL(blob);video.src=videoURL;video.dataset.run=selected.id;video.load();
  }).catch(()=>{if(run===selected)$('#result-note').textContent='视频未能载入，可刷新或使用下方下载链接。';}).finally(()=>{if(run===selected)video.setAttribute('aria-busy','false');});
  $('#run-name').textContent=run.label;
  $('#outcome').textContent=run.task_success?'原生任务成功':'原生任务未成功';
  $('#outcome').classList.toggle('success',run.task_success);
  $('#metrics').innerHTML=[[run.motion_requests,'实际动作段'],[run.control_steps,'控制步'],[run.samples,'真实采样帧'],[run.histories,'触觉历史回传']].map(([n,label])=>`<div><strong>${escape(n)}</strong><span>${label}</span></div>`).join('');
  $('#result-note').textContent=run.explanation;
  $('#download').href=run.video;
  const endReasons={arm_reached:'控制器报告到达',episode_ended:'原生回合结束'};
  $('#actions').innerHTML=run.actions.map((a,i)=>`<details class="action" ${i===0?'open':''}><summary><span class="action-label">ACTION ${String(i+1).padStart(2,'0')} · ${a.control_steps} 控制步</span><h4>${escape(a.label)}</h4></summary><div class="action-body"><p>模型指令：<code>${escape(JSON.stringify(a.arguments))}</code></p><p>该段${a.arm_reached?'到达请求目标':'未到达请求目标'}；${escape(endReasons[a.end_reason]||a.end_reason)}。动作执行状态与任务成功分别记录。</p><div class="selection">触觉保留 ${a.selected_ids.length} / ${a.candidate_count} 个时刻<br>共同样本编号：${escape(a.selected_ids.join(' → '))}<br>左右共用时间点，段末回传；无动作内触觉中断。</div><button class="seek-action" data-frame="${a.first_frame}">定位这一段 ↗</button></div></details>`).join('');
  document.querySelectorAll('.seek-action').forEach(button=>button.addEventListener('click',()=>seek(Number(button.dataset.frame))));
  updateFrame();
}
$('#prev-frame').addEventListener('click',()=>seek(indexAt(video.currentTime)-1));
$('#next-frame').addEventListener('click',()=>seek(indexAt(video.currentTime)+1));
$('#speed').addEventListener('change',()=>{video.playbackRate=Number($('#speed').value);});
video.addEventListener('loadedmetadata',()=>{video.playbackRate=Number($('#speed').value);updateFrame();});
video.addEventListener('timeupdate',updateFrame);
video.addEventListener('seeked',updateFrame);
$('#run-select').addEventListener('change',e=>showRun(Number(e.target.value)));
fetch('data.json').then(r=>{if(!r.ok)throw Error('data');return r.json();}).then(value=>{
  data=value;$('#run-select').innerHTML=data.runs.map((r,i)=>`<option value="${i}">${escape(r.label)}</option>`).join('');
  $('#attempts').innerHTML=data.attempts.map(a=>`<article class="attempt-row"><span>${escape(a.id)}</span><div><h3>${escape(a.title)}</h3><p>${escape(a.detail)}</p></div><b>${escape(a.status)}</b></article>`).join('');
  $('#load-status').hidden=true;$('#run-grid').hidden=false;showRun(0);document.documentElement.dataset.ready='true';
}).catch(()=>{$('#load-status').textContent='记录未能载入，请刷新或下载运行摘要。';document.documentElement.dataset.ready='error';});
