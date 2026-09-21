/* The replay is selectable alongside historical saved records. */
if(window.RECOVERED_EXCHANGE){
 window.appendReplayEntries=()=>{
  for(const r of window.RECOVERED_EXCHANGE.records){
   const messages=r.request.messages||[];
   const texts=messages.map(m=>{
    const body=typeof m.content==='string'?m.content:(m.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('\n\n');
    return `${m.role}\n\n${body}`;
   });
   const answers=(r.response?.choices||[]).map(c=>readable(c.message?.content));
   const images=messages.flatMap(m=>Array.isArray(m.content)?m.content.filter(p=>p.image_url?.saved_file).map(p=>p.image_url.saved_file):[]);
   ioEntries.push({label:`完整重放 · ${r.role==='planner'?'Planner':'Actor'}`,
    source:`新重放 · ${r.role} · ${r.request.model} · HTTP ${r.http_status} · ${r.duration_s} 秒`,
    input:texts.join('\n\n────────\n\n'),output:answers.length?answers.join('\n\n'):readable(r.response),images,
    downloads:[[r.request_file,'请求原文'],[r.response_file,'返回原文']]});
  }
 };
 window.appendReplayEntries();ioIndex=ioEntries.length-window.RECOVERED_EXCHANGE.records.length;populateIO();
}
