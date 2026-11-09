import json,sys
from pathlib import Path
from pxr import Usd,UsdGeom,UsdShade,UsdPhysics,Sdf
from tacharness.agenticsim.generation.scene_gen.scene_mutator import SceneMutator, SceneMutation
s=Path(__file__).resolve().parents[1];folder=s/'runs'/sys.argv[1];folder.mkdir()
base=folder/'base.usda'; st=Usd.Stage.CreateNew(str(base))
cube=UsdGeom.Cube.Define(st,'/Body');UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim());UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
mat=UsdShade.Material.Define(st,'/Surface');UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(mat,materialPurpose='physics')
shader=UsdShade.Shader.Define(st,'/Surface/Texture');shader.CreateIdAttr('UsdUVTexture')
st.GetRootLayer().Save()
geo=folder/'object.usda'; extra=Usd.Stage.CreateNew(str(geo));extra.SetDefaultPrim(UsdGeom.Sphere.Define(extra,'/Sphere').GetPrim());extra.GetRootLayer().Save()
engine=SceneMutator(folder)
r=engine.mutate(base,[
    SceneMutation('add_object','/New',{'asset':'object.usda'}),
    SceneMutation('set_mass','/Body',{'mass_kg':.18}),
    SceneMutation('set_friction','/Surface',{'static':.6,'dynamic':.4}),
    SceneMutation('swap_texture','/Surface/Texture',{'file':str(s/'assets/bowl-scene.png')}),
],folder/'changed.usda')
assert r.is_valid,r.validation_errors
dst=Usd.Stage.Open(str(r.mutated_usd))
record=dict(added=dst.GetPrimAtPath('/New').GetTypeName(),mass=UsdPhysics.MassAPI(dst.GetPrimAtPath('/Body')).GetMassAttr().Get(),
 static_friction=dst.GetPrimAtPath('/Surface').GetAttribute('physics:staticFriction').Get(),dynamic_friction=dst.GetPrimAtPath('/Surface').GetAttribute('physics:dynamicFriction').Get(),texture=dst.GetPrimAtPath('/Surface/Texture').GetAttribute('inputs:file').Get().resolvedPath)
assert record['added']=='Sphere' and abs(record['mass']-.18)<1e-4 and Path(record['texture']).is_file()
(folder/'review.json').write_text(json.dumps(record,indent=2));print(record)
