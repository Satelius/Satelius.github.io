from pathlib import Path
import json,subprocess,sys,time
site=Path(__file__).resolve().parents[1]
repo=site.parents[1]/'TacHarness-genenv'
catalog='/runtime/TacHarness/inputs/datasets/vendor/robolab/assets'
specs=[('stack','A block on top of a plate.','block_1','plate_1','on_top_of'),
('already_inside','A block inside a bowl.','block_1','bowl_1','inside'),
('missing_asset','A drawer to the left of a bottle.','drawer_1','bottle_1','inside'),
('wrong_binding','A banana to the left of a bowl.','can_1','bowl_1','inside'),
('cn','在碗的左侧放一根香蕉。','banana_1','bowl_1','inside'),
('front','A can in front of a bowl.','can_1','bowl_1','inside'),
('same','A banana to the left of a bowl.','banana_1','banana_1','inside')]
rows=[]
for name,prompt,obj,target,relation in specs:
    dest=site/'runs'/name
    cmd=[sys.executable,str(repo/'scripts/agentic/genenv_robolab_example.py'),'--asset-root',catalog,'--seed','7','--prompt',prompt,'--object',obj,'--target',target,'--relation',relation,'--scene-name','audit_'+name,'--out',str(dest)]
    t=time.monotonic();r=subprocess.run(cmd,cwd=repo,capture_output=True,text=True)
    dest.mkdir(exist_ok=True);(dest/'process.log').write_text(r.stdout+r.stderr)
    errors=list(dest.rglob('failure_report.json'));error=json.loads(errors[0].read_text())['code'] if errors else r.stderr.strip().splitlines()[-1] if r.stderr else None
    rows.append(dict(case=name,prompt=prompt,cmd=cmd,rc=r.returncode,error=error,seconds=time.monotonic()-t))
(site/'review/compiler-matrix.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
