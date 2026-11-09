from pathlib import Path
from pxr import Usd,UsdGeom
import json,numpy as np
site=Path(__file__).resolve().parents[1]
rows=[]
for name,z in [('Shelf',.001),('BottleLift',.01)]:
    p=Path('/runtime/UniVTAC/assets/objects')/(name+'.usd');st=Usd.Stage.Open(str(p))
    meshes=[q for q in st.Traverse() if q.IsA(UsdGeom.Mesh)]
    for q in meshes[:1]:
        mesh=UsdGeom.Mesh(q)
        v=np.asarray(mesh.GetPointsAttr().Get(),dtype=float)
        mat=np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(q))
        pos=(np.c_[v,np.ones(len(v))]@mat)[:,:3]
        rows.append(dict(asset=name,mesh=str(q.GetPath()),n=len(v),xyz_range=[pos.min(axis=0).tolist(),pos.max(axis=0).tolist()],
                         identity_bottom=z+pos[:,2].min(),x180_bottom=z-pos[:,2].max()))
(site/'review/uni-floor.json').write_text(json.dumps(rows,indent=2));print(rows)
