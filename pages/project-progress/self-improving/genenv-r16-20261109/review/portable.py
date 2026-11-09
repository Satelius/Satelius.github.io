"""A self-contained USD geometry preview with local materials and no network requests."""
from pathlib import Path
import json,shutil
from pxr import Usd,UsdGeom,UsdUtils,Sdf,Gf
site=Path(__file__).resolve().parents[1]; archive=site.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/raw/usdz-v1'
archive.mkdir(parents=True,exist_ok=True)
rows=[]
for case in ['banana_0_1','feedback']:
    source=site/'runs'/case/f'audit_{case}.usda'
    old=site/'assets'/f'audit_{case}.usdz'
    if old.exists():shutil.move(old,archive/old.name)
    stage=Usd.Stage.Open(str(source)); flat=Usd.Stage.Open(stage.Flatten())
    delete=[]
    for p in flat.Traverse():
        if p.GetTypeName() in ('Shader','NodeGraph'):delete.append(p.GetPath()); continue
        for prop in p.GetProperties():
            if prop.GetName().startswith('material:binding') and 'physics' not in prop.GetName():
                p.RemoveProperty(prop.GetName())
        if p.IsA(UsdGeom.Mesh):
            path=str(p.GetPath()).lower()
            color=Gf.Vec3f(.72,.54,.10) if 'banana' in path else Gf.Vec3f(.67,.28,.19) if 'bowl' in path else Gf.Vec3f(.16,.46,.72) if 'block' in path else Gf.Vec3f(.42,.39,.34)
            UsdGeom.Mesh(p).CreateDisplayColorAttr([color])
    for path in reversed(delete):flat.RemovePrim(path)
    UsdUtils.ModifyAssetPaths(flat.GetRootLayer(), lambda path: '')
    usdc=archive/(case+'-geometry.usdc');flat.GetRootLayer().Export(str(usdc))
    dst=site/'assets'/f'preview-{case}.usdz'
    if dst.exists(): shutil.move(dst,archive/dst.name)
    ok=UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(usdc)),str(dst))
    layers,assets,missing=UsdUtils.ComputeAllDependencies(Sdf.AssetPath(str(dst)))
    check=Usd.Stage.Open(str(dst)); rows.append(dict(case=case,packaged=ok,mesh_count=sum(p.IsA(UsdGeom.Mesh) for p in check.Traverse()),unresolved=list(missing),size=dst.stat().st_size))
(site/'review/portable.json').write_text(json.dumps(rows,indent=2));print(rows)
