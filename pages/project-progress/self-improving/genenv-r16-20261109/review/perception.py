"""Read-only model inference over captured reference images. No tools or file access required."""
from pathlib import Path
import json, subprocess, sys, time
site=Path(__file__).resolve().parents[1]
case=sys.argv[1]
img=site/'assets'/('bowl-scene.png' if case=='image' else 'bottle-evidence.jpg')
prompt="""仅根据附图回答。返回 JSON 对象，字段 observed（可直接观察的物体和相对关系）、inferred（推断）、unknown（遮挡、尺寸、接触等无法测量项）、family（从 stove_bowl, drawer_bowl, bottle_shelf, unknown 选择）、intervals（如有多个时刻，列出有画面支持的动作区间及时间；单帧为空）、confidence（是否足以唯一确定任务）。不可使用工具。"""
cmd=['codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','read-only','-m','gpt-6.1-sol','-c','features.shell_tool=false','-c','features.multi_agent=false','-c','mcp_servers={}','-i',str(img),'--output-last-message',str(site/'review'/f'{case}-answer.txt'),prompt]
t=time.monotonic()
r=subprocess.run(cmd,cwd=site,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=160)
# Keep the answer and compact error; avoid archiving unrelated CLI/user config content.
(site/'review'/f'{case}-inference.json').write_text(json.dumps(dict(requested_model='gpt-6.1-sol',input=img.name,prompt=prompt,exit=r.returncode,elapsed_s=time.monotonic()-t,errors=[line[:400] for line in r.stderr.splitlines() if 'error:' in line.lower() or 'ERROR' in line][:6]),ensure_ascii=False,indent=2))
