/* Field-level evidence, not reconstructed model reasoning. */
const inspection=document.createElement('details');
inspection.id='inspection';
inspection.innerHTML=`<summary>失败原因检查 · 展开逐步输入 / 返回 / 执行 / 结果</summary>
<p class="trace-warning">这里展示已保存的模型可见回答和遥测。完整 HTTP 输入输出、完整规划文本及模型内部推理未保存；空缺不会补造。仿真真值只用于解释执行结果。</p>
<div class="trace-controls"><button id="trace-prev">上一步</button><label>调用 / 决策 <select id="trace-select"></select></label><button id="trace-next">下一步</button><button id="trace-seek">定位回放参考帧</button></div>
<p id="trace-coverage"></p><p id="trace-finding" class="note"></p>
<div class="trace-grid"><article><h3>① 输入证据</h3><p id="trace-input"></p><pre id="trace-context"></pre></article>
<article><h3>② 模型返回</h3><p id="trace-output-note"></p><pre id="trace-output"></pre></article>
<article><h3>③ 动作 / 工具执行</h3><p id="trace-action"></p><pre id="trace-execution"></pre></article>
<article><h3>④ 执行后的结果</h3><p>下列 TCP、物体位置和原生评分属于执行 / 评估日志，不能当成该步模型输入。</p><pre id="trace-result"></pre></article></div>
<h3>与作者方法的不同</h3><p id="trace-diff"></p><p>上述差异可能影响表现，但尚未逐项完成对照实验，不能直接认定为该步失败原因。<a href="evidence/AUTHOR_FEATURE_AUDIT.md">查看作者源码审计</a></p>
<details><summary>查看本次保存的请求遥测字段、阶段事件与证据出处</summary><pre id="trace-raw"></pre></details>`;
document.querySelector('#budget').before(inspection);
document.querySelector('#budget').nextElementSibling.textContent='视频菜单覆盖打包时已保存的失败录像，具体任务见名称与证据。P7 完整矩阵及 P9 早期 metrics-only 运行没有视频；新增录像不能替代那些 episode 的原始记录。';
let traceRun=null, traceIndex=0;
const choose=document.querySelector('#trace-select');
const print=(id,value)=>document.querySelector(id).textContent=value==null?'未记录':JSON.stringify(value,null,2);
const pick=(obj,keys)=>Object.fromEntries(keys.filter(k=>obj&&Object.hasOwn(obj,k)).map(k=>[k,obj[k]]));
function renderTrace(){
 const entries=traceRun.trace.entries;const entry=entries[traceIndex];
 if(!entry)return;
 choose.value=String(traceIndex);
 const r=entry.request||{},s=entry.step||{},planner=r.role==='planner';
 document.querySelector('#trace-coverage').textContent=`已保存 ${traceRun.trace.request_rows} 条请求记录、${traceRun.trace.step_rows} 条动作记录。当前 ${traceIndex+1}/${entries.length}；日志步号从 0 开始。`;
 document.querySelector('#trace-input').textContent=planner?'Planner 调用。源码约定输入任务文字和当前图像；该次完整提示词、图像请求体与完整计划未留存。':'Actor 输入包括任务、图像、子目标与动作历史（源码约定）。下面仅列任务 / 当前阶段日志字段；完整子目标、历史字符串和序列化输入未保存。回放帧为压缩合成图，不是原始图片请求体。';
 print('#trace-context',{task:traceRun.trace.task||'完整任务文字未记录',task_id:traceRun.task,...pick(s,['i','stage','stage_id','target','sg','n_sg'])});
 document.querySelector('#trace-output-note').textContent=planner?'只保存规划阶段、数量、解析路径等遥测，未保存完整规划输出。':'visual_assessment 是模型返回的简短观察与判断，不是内部思维链；仅展示保存字段，非完整原始返回。';
 print('#trace-output',Object.keys(r).length?pick(r,['token','visual_assessment','subgoal_count','planner_route','model','output_protocol_id','duration_s','telemetry','error_class']):{status:'此早期日志没有 requests.jsonl；仅有动作词元',act:s.act});
 if(planner)document.querySelector('#trace-output-note').textContent+=' 注意：model.max_tokens 是 profile 字段，可能与 planner 实际请求 override 不同，不能据此判断截断。';
 const token=r.token||s.act;
 const explanation=planner?'该调用产生计划，不直接驱动机器人。':token==='DONE'?'DONE 表示模型认为阶段完成，不等于原生任务成功。':token==='HOLD'?'HOLD 是保持动作；检查 action_source 确认是错误处理还是保护拦截。':token==='GRASP'?'GRASP 映射到闭合夹爪代码。发出指令不证明已经抓住。':token==='RELEASE'?'RELEASE 映射到张开夹爪代码。':token?.startsWith('MV_')?'MV_* 是动作词元，由控制代码映射到相对 IK 移动。日志没有独立的模型 tool-call 记录。':'没有记录动作词元或工具调用。';
 document.querySelector('#trace-action').textContent=explanation;
 print('#trace-execution',Object.keys(s).length?pick(s,['i','act','event','executed','action_source','secondary_action_source','auto_release','gripper_command','grip','replan_count']):null);
 print('#trace-result',Object.keys(s).length?pick(s,['tcp_before','tcp_after','tcp_delta_m','eef','gripper_width_m','w','native_success','env_done','native_subtask','evaluator_truth','new_stage_progress_events','timing','vlm_ms']):null);
 const inverse={MV_LEFT:'MV_RIGHT',MV_RIGHT:'MV_LEFT',MV_FWD:'MV_BACK',MV_BACK:'MV_FWD',MV_UP:'MV_DOWN',MV_DOWN:'MV_UP'};
 const previous=entries.slice(0,traceIndex).reverse().find(e=>e.step?.executed===true)?.step;
 const findings=[];
 if(r.error_class)findings.push('已记录：本次逻辑请求失败。');
 if(previous&&s.executed===true&&inverse[previous.act]===s.act)findings.push('已记录：与前一已执行动作方向相反。可能是纠偏或振荡，单次反向不足以判定错误。');
 if(s.auto_release)findings.push('已记录：自动松爪触发，需结合夹爪宽度和画面复查空抓。');
 if(s.native_success===false)findings.push('该步结束时原生任务尚未成功。');
 document.querySelector('#trace-finding').textContent=(findings.join(' ')||'当前日志不足以给出该步的独立失败归因。')+` 整个 episode 终止：${reasons[traceRun.end_reason]||traceRun.end_reason}。`;
 document.querySelector('#trace-diff').textContent=traceRun.trace.visual_protocol?'适用于本条 P8/P9 visual-assessment 路径：作者输出 decision + 简短视觉理由；本地增加可见性、对准、接触风险字段。作者使用本体反馈、粗细步长和选择性分块；本地 staged 路径未完整接入，使用固定约 2 cm 步长。动作历史与恢复/阶段预算也有差异。':'当前录像属于早期流程；不能把后来的 P8/P9 差异直接套用。精确历史提示词和插件状态需结合该次版本核查。作者默认模型、试验次数与这里的 Astra/Luna 设置不同。';
 print('#trace-raw',{request_record:entry.request,stage_events:traceRun.trace.stage_events,source_folder:traceRun.source.replace('/rollout_failure.mp4',''),source_line:{requests:r.line??null,steps:s.line??null},source_hashes:traceRun.trace.artifacts});
 document.querySelector('#trace-prev').disabled=traceIndex===0;document.querySelector('#trace-next').disabled=traceIndex===entries.length-1;
 document.querySelector('#trace-seek').disabled=!entry.step;
}
function resetTrace(){traceRun=data.videos[Number(document.querySelector('#episodes').value)];traceIndex=0;choose.replaceChildren();traceRun.trace.entries.forEach((e,i)=>{const option=document.createElement('option');option.value=i;option.textContent=e.request?`${e.request.role} · ${e.request.phase||'步 '+e.request.step} · ${e.request.token||'计划 / 无词元'}`:`旧日志 · 步 ${e.step.i} · ${e.step.act}`;choose.append(option);});renderTrace();}
choose.onchange=()=>{traceIndex=Number(choose.value);renderTrace();};
document.querySelector('#trace-prev').onclick=()=>{traceIndex=Math.max(0,traceIndex-1);renderTrace();};
document.querySelector('#trace-next').onclick=()=>{traceIndex=Math.min(traceRun.trace.entries.length-1,traceIndex+1);renderTrace();};
document.querySelector('#trace-seek').onclick=()=>{const step=traceRun.trace.entries[traceIndex].step;const ordered=traceRun.trace.entries.filter(e=>e.step);const ordinal=ordered.findIndex(e=>e.step===step);const parts=traceRun.fps.split('/').map(Number);player.pause();player.currentTime=Math.min(ordinal/(parts[0]/parts[1]),Math.max(0,player.duration-0.05));document.querySelector('#trace-coverage').textContent+=' 已按录像顺序定位参考帧；不是请求时间戳级对齐，早期录像可能有初始化帧。';};
document.querySelector('#episodes').addEventListener('change',resetTrace);
if(data)resetTrace();
