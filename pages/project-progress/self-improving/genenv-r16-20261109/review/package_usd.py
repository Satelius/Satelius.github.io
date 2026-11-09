import json
from pathlib import Path
from pxr import Usd,UsdUtils,Sdf
site=Path(__file__).resolve().parents[1]
rows=[]
for source in [site/'runs/banana_0_1/audit_banana_0_1.usda',site/'runs/feedback/audit_feedback.usda']:
    package=site/'assets'/(source.stem+'.usdz')
    ok=UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(source)),str(package))
    stage=Usd.Stage.Open(str(package)); prims=[str(p.GetPath()) for p in stage.Traverse() if p.IsA(__import__('pxr.UsdGeom',fromlist=['Mesh']).Mesh)] if stage else []
    rows.append(dict(scene=source.name,package=package.name,success=ok,composed_mesh_count=len(prims),size=package.stat().st_size))
(site/'review/usdz.json').write_text(json.dumps(rows,indent=2));print(rows)
