/* Offline presentation: all data and media are local. */
const data = window.MEETING_DATA;
const sections = [...document.querySelectorAll('main section')];
let current = 0;
function show(index) {
  current = Math.max(0, Math.min(sections.length - 1, index));
  sections.forEach((s, i) => s.classList.toggle('current', i === current));
  document.querySelectorAll('nav a').forEach((a, i) => a.classList.toggle('active', i === current));
  document.querySelector('#page').textContent = `0${current + 1} / 05`;
  if (!document.body.classList.contains('presentation')) sections[current].scrollIntoView();
  else window.scrollTo(0, 0);
  if (current !== 2) document.querySelector('#player').pause();
}
document.querySelectorAll('nav a').forEach((a, i) => a.onclick = e => {e.preventDefault(); show(i);});
document.querySelector('#prev').onclick = () => show(current - 1);
document.querySelector('#next-page').onclick = () => show(current + 1);
document.querySelector('#present').onclick = () => {document.body.classList.toggle('presentation'); document.querySelector('#present').textContent=document.body.classList.contains('presentation')?'长页模式':'演示模式';show(current);};
document.querySelector('#full').onclick = async () => {try {if(document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen();} catch {document.querySelector('#full').textContent='可按 F11 全屏';}};
document.addEventListener('keydown',e=>{if(['SELECT','INPUT','VIDEO','BUTTON'].includes(document.activeElement.tagName))return;if(e.key==='ArrowRight'){e.preventDefault();show(current+1);}if(e.key==='ArrowLeft'){e.preventDefault();show(current-1);}if(e.key==='Escape'){document.body.classList.remove('presentation');document.querySelector('#present').textContent='演示模式';}});
const observer = new IntersectionObserver(entries=>{if(document.body.classList.contains('presentation'))return;for(const entry of entries){if(entry.isIntersecting){current=sections.indexOf(entry.target);document.querySelector('#page').textContent=`0${current+1} / 05`;document.querySelectorAll('nav a').forEach((a,i)=>a.classList.toggle('active',i===current));}}},{threshold:0.4});
sections.forEach(s=>observer.observe(s));
const player=document.querySelector('#player');
const reasons={action_oscillation_replan_exhausted:'动作振荡，重规划耗尽',stage_budget_replan_exhausted:'阶段预算及重规划耗尽',max_steps_exceeded:'决策步数上限',env_truncated:'环境时间到期'};
const fmt=(n,unit='')=>typeof n==='number'?`${n.toFixed(1)}${unit}`:'未记录';
function selectVideo(index){const r=data.videos[index];player.pause();player.poster=r.poster;player.src=r.video;player.playbackRate=Number(document.querySelector('#speed').value);document.querySelector('#video-title').textContent=r.title;document.querySelector('#video-note').textContent=r.note;document.querySelector('#group').textContent=r.group;document.querySelector('#download').href=r.video;document.querySelector('#record').href=`assets/${r.id}/evidence.json`;const metrics=[['原生成功',r.native_success===false?'否':r.native_success===true?'是':'未知'],['实际决策',`${r.steps} 步`],['结束原因',reasons[r.end_reason]||r.end_reason],['真实耗时',fmt(r.wall_s,' 秒')],['Actor p95',fmt(r.actor_p95_s,' 秒')],['视频时长',fmt(r.duration_s,' 秒')],['视频帧率',r.fps+' fps']];document.querySelector('#metrics').replaceChildren(...metrics.flatMap(([k,v])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=v;return[dt,dd];}));document.querySelector('#media-error').textContent='';}
player.onerror=()=>document.querySelector('#media-error').textContent='视频加载失败：请确认已复制整个文件夹，或使用 README 中的本地服务器命令。';
document.querySelector('#speed').onchange=e=>player.playbackRate=Number(e.target.value);
if(data){document.querySelector('#partial').textContent=`P9 v2 快照：${data.p9_v2.terminal_ledger_rows}/33 条正式终态记录，另有 ${data.p9_v2.summary_files} 份 episode summary（含未被父进程登记的产物）。该运行已中断，不能作为完整基线；HTTP 400 是历史阻塞记录，不代表 provider 当前状态。`;const select=document.querySelector('#episodes');data.videos.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.title} · ${r.steps}步`;select.append(o);});select.onchange=()=>selectVideo(Number(select.value));selectVideo(0);data.videos.filter(r=>r.group==='预算实验').forEach(r=>{const a=document.createElement('article'),b=document.createElement('b'),n=document.createElement('strong'),p=document.createElement('p');b.textContent=r.title;n.textContent=`${r.steps} / 160 步`;p.textContent=r.note;a.append(b,n,p);document.querySelector('#budget').append(a);});}else document.querySelector('#video-title').textContent='请先运行 build_assets.py 生成本地素材。';
sections[0].classList.add('current');
