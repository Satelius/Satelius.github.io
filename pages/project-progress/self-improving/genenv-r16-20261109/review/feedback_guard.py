import json, sys
from pathlib import Path
from tacharness.agenticsim.generation.genenv.feedback import apply_data_requirement
site=Path(__file__).resolve().parents[1]
root=site/'runs'/sys.argv[1];root.mkdir()
cases={'nan':dict(x=float('nan'),y=.1),'outside':dict(x=1.5,y=.1),'partial':dict(x=.5,y=.1)}
rows=[]
for name,layout in cases.items():
    data=dict(kind='collect_targeted',target_layouts=[layout])
    if name=='partial':data['target_layouts'].append(dict(x=.5))
    try:
        result=apply_data_requirement(site/'runs/block','audit_block',data,out_dir=root/name,round_index=1)
        rows.append(dict(case=name,result='emitted',position=list(result.centroids.values())))
    except ValueError as exc:rows.append(dict(case=name,result='rejected',error=str(exc)))
(root/'review.json').write_text(json.dumps(rows,indent=2).replace('NaN','"NaN"'))
print(rows)
