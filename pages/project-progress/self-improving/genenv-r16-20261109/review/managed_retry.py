from pathlib import Path
import json,subprocess,sys,time,concurrent.futures,os
s=Path(__file__).resolve().parents[1];j=json.loads((s/'review/x2env-deployment.json').read_text())
j.update(timeout_seconds=600,state_dir=str(s/'runs/x2managed-retry'))
deploy=s/'review/x2env-long.json';deploy.write_text(json.dumps(j,indent=2))
cases={'text':['--text','A banana to the left of a bowl.'],'image':['--image',str(s/'assets/bowl-scene.png')],'video':['--video',str(s/'assets/bottle-reference.mp4')]}
def go(case):
 args=[sys.executable,'-m','self_improving.harness.x2env.cli','submit','--deployment',str(deploy),'--seed','7','--idempotency-key','rerun-'+case,'--output',str(s/'runs'/('managed-'+case))]+cases[case]
 r=subprocess.run(args,capture_output=True,text=True,timeout=630)
 (s/'review'/('managed-'+case+'.json')).write_text(r.stdout)
 print(case,r.returncode,flush=True)
with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(go,cases))
