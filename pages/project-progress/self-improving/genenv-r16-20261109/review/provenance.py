from pathlib import Path
import subprocess,json,hashlib,difflib,sys
s=Path(__file__).resolve().parents[1];proj=s.parents[1]/'TacHarness-genenv'
audit=proj/'outputs/genenv-audit-20261109';u=audit/'uni60';src=Path('/runtime/UniVTAC')
native=proj/'thirdparty/robot-harness-gen-env'
def git(dir,*args):
 return subprocess.run(['git','-C',str(dir),*args],capture_output=True,text=True).stdout
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
changed=['scripts/agentic/genenv_robolab_example.py','src/tacharness/agenticsim/generation/genenv/feedback.py','src/tacharness/agenticsim/generation/genenv/robolab_import.py','src/tacharness/agenticsim/generation/genenv/robolab_catalog.py','src/tacharness/agenticsim/generation/scene_gen/scene_mutator.py','tests/agentic/test_genenv_robolab.py','repo-docs/modules/agentic-runtime.md','repo-docs/change-log.md']
fresh=['scripts/agentic/probe_generated_layout.py','tests/agentic/test_scene_mutator_readback.py']
patch=git(proj,'diff','--',*changed)
for p in fresh:patch+=git(proj,'diff','--no-index','/dev/null',p)
(s/'review/bridge.patch').write_text(patch)
(s/'review/parser.patch').write_text(git(native,'diff','--','scene_gen','tests/scene_gen','repo-docs/modules/scene-contract.md','repo-docs/change-log.md'))
(s/'review/robotwin-import.patch').write_text(git(audit/'RoboTwin','diff','--','envs/utils/rand_create_cluttered_actor.py'))
parts=[]
for prefix,orig,copy in [('work',src,u/'work'),('overlay/tacex_uipc',src/'third_party/TacEx/source/tacex_uipc/tacex_uipc',u/'overlay/tacex_uipc'),('overlay/tacex',src/'third_party/TacEx/source/tacex/tacex',u/'overlay/tacex')]:
 for p in sorted(copy.rglob('*.py')):
  a=orig/p.relative_to(copy)
  if a.is_file() and p.read_bytes()!=a.read_bytes():
   f=str(Path(prefix)/p.relative_to(copy))
   parts.extend(difflib.unified_diff(a.read_text().splitlines(True),p.read_text().splitlines(True),'a/'+f,'b/'+f))
(s/'review/uni60.patch').write_text(''.join(parts))
record={'roots':{str(p):git(p,'rev-parse','HEAD').strip() for p in [proj,native,s.parents[1]/'TacHarness-exp',src,audit/'RoboTwin',Path('/runtime/TacHarness-genenv')]},'sha256':{p:sha(proj/p) for p in changed+fresh},'runtime':{'RoboLab/Tabero':'/runtime/TacHarness/.venv-isaacsim62/bin/python','UniVTAC':'/runtime/gujie/TacHarness/.venv-isaacsim60/bin/python','SAPIEN / USD':str(audit/'cpu/bin/python')},'raw_directory':str(audit/'raw'),'source_notes':['开发探针，无盲测身份','三组炉台轨迹共用源示教 #4','RoboLab 原教师使用默认机器人资产与原始相机尺寸；接触探针使用 gujie 的摩擦垫材质和 640×360 相机','程序化滑轨来自此次专项诊断脚本','部署选项、源数据与试次 ID 各自独立']}
(s/'review/sources.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
