import hashlib,json
from pathlib import Path
from pxr import Usd
from tacharness.agenticsim.generation.genenv.feedback import apply_data_requirement
root=Path(__file__).resolve().parents[1]
native=Path('/runtime/TacHarness/inputs/datasets/vendor/robolab/assets/scenes/banana_bowl.usda')
stage=Usd.Stage.Open(str(native)); center={}
for name in ('banana','bowl'):
    prim=next(p for p in stage.Traverse() if p.GetName()==name and p.GetAttribute('xformOp:translate'))
    center[name]=list(prim.GetAttribute('xformOp:translate').Get())[:2]
rows=[]
for xi,dx in enumerate((-.03,0,.03)):
    for yi,dy in enumerate((-.03,.03)):
        label=f'banana_{xi}_{yi}'; out=root/'runs'/label;out.mkdir()
        xy=[center['banana'][0]+dx,center['banana'][1]+dy]
        req=dict(kind='collect_targeted',target_layouts=[{'object':'banana','xy':xy},{'object':'bowl','xy':center['bowl']}],reset_jitter_m=0,reset_yaw_jitter_rad=0)
        (out/'request.json').write_text(json.dumps(req,indent=2))
        r=apply_data_requirement(root/'runs/banana_parent','audit_banana_parent',req,out_dir=out,round_index=1,variant_name='audit_'+label)
        rows.append(dict(case=label,xy=xy,target=center['bowl'],dx=dx,dy=dy,task=r.task_path.name))
(root/'review/banana-grid.json').write_text(json.dumps(dict(native_scene=str(native),native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),native_xy=center,rows=rows),indent=2))
