from pathlib import Path
import json, sys
from pxr import Usd, UsdGeom, UsdLux, Gf
from tacharness.agenticsim.generation.scene_gen.scene_mutator import SceneMutator, SceneMutation
out=Path(sys.argv[1]);out.mkdir()
base=out/'base.usda'; stage=Usd.Stage.CreateNew(str(base))
cube=UsdGeom.Cube.Define(stage,'/Cube'); cube.AddTranslateOp().Set(Gf.Vec3d(1,2,3))
light=UsdLux.DistantLight.Define(stage,'/Light');light.CreateIntensityAttr(100)
stage.GetRootLayer().Save()
rows=[]
for name,op,path,params in [
 ('move','move_object','/Cube',{'delta_position':[.03,0,0]}),
 ('remove','remove_object','/Cube',{}),('light','change_lighting','',{'intensity_multiplier':1.5}),
 ('missing','move_object','/Missing',{}),('unknown','fake','/Cube',{}),
 ('add','add_object','/New',{}),('texture','swap_texture','/Cube',{}),('friction','friction','/Cube',{})]:
 result=SceneMutator().mutate(base,[SceneMutation(op,path,params)],out/(name+'.usda'))
 dst=Usd.Stage.Open(str(result.mutated_usd)) if result.mutated_usd else None
 cube=dst.GetPrimAtPath('/Cube') if dst else None
 pos=list(cube.GetAttribute('xformOp:translate').Get()) if cube and cube.IsActive() else None
 intensity=dst.GetPrimAtPath('/Light').GetAttribute('inputs:intensity').Get() if dst else None
 verified={'move':pos==[1.03,2,3],'remove':cube and not cube.IsActive(),'light':intensity==150}.get(name,False)
 rows.append(dict(case=name,accepted=result.is_valid,readback=bool(verified),position=pos,intensity=intensity,errors=result.validation_errors))
(out/'review.json').write_text(json.dumps(rows,indent=2))
print(rows)
