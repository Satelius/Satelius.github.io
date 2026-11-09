from pathlib import Path
import json,sys,subprocess
import numpy as np
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'width':640,'height':360})
import omni.usd, omni.timeline, omni.replicator.core as rep
import carb
from pxr import Usd,UsdGeom,UsdPhysics,PhysxSchema,Gf
site=Path(__file__).resolve().parents[1]
out=site/'runs'/sys.argv[1];out.mkdir()
stage=omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z);UsdGeom.SetStageMetersPerUnit(stage,1.)
scene=UsdPhysics.Scene.Define(stage,'/World/Physics')
scene.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));scene.CreateGravityMagnitudeAttr(9.81)
def box(path,pos,size,color,collision=True):
    cube=UsdGeom.Cube.Define(stage,path);cube.CreateSizeAttr(1.)
    cube.AddTranslateOp().Set(Gf.Vec3d(*pos));cube.AddScaleOp().Set(Gf.Vec3f(*size))
    cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if collision:UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    return cube
box('/World/Table',(0,0,-.06),(1.,.78,.1),(.25,.33,.33))
box('/World/Back',(-.19,0,.13),(.05,.43,.24),(.35,.28,.18))
for y in (-.205,.205):box('/World/Rail'+('L' if y>0 else 'R'),(0,y,.12),(.42,.025,.21),(.52,.35,.18))
drawer=UsdGeom.Xform.Define(stage,'/World/Drawer')
drawer.AddTranslateOp().Set(Gf.Vec3d(0,0,.15))
box('/World/Drawer/Base',(0,0,-.07),(.32,.36,.025),(.72,.48,.23))
box('/World/Drawer/Face',(.15,0,0),(.026,.36,.15),(.68,.42,.18))
box('/World/Drawer/Handle',(.176,0,.015),(.036,.10,.022),(.12,.17,.16))
UsdPhysics.RigidBodyAPI.Apply(drawer.GetPrim());UsdPhysics.MassAPI.Apply(drawer.GetPrim()).CreateMassAttr(.4)
joint=UsdPhysics.PrismaticJoint.Define(stage,'/World/Slide')
joint.CreateAxisAttr('X');joint.CreateLowerLimitAttr(0);joint.CreateUpperLimitAttr(.14)
joint.CreateBody1Rel().SetTargets([drawer.GetPath()]);joint.CreateLocalPos0Attr(Gf.Vec3f(0,0,.15))
drive=UsdPhysics.DriveAPI.Apply(joint.GetPrim(),'linear')
drive.CreateStiffnessAttr(900);drive.CreateDampingAttr(65);drive.CreateMaxForceAttr(150);drive.CreateTargetPositionAttr(0.)
from pxr import UsdLux
light=UsdLux.DomeLight.Define(stage,'/World/Light');light.CreateIntensityAttr(1400.)
cam=rep.create.camera(position=(.85,-.77,.59),look_at=(.07,0,.10))
rp=rep.create.render_product(cam,(640,360))
ann=rep.AnnotatorRegistry.get_annotator('rgb');ann.attach([rp])
stage.GetRootLayer().Export(str(out/'drawer.usda'))
carb.settings.get_settings().set_bool('/physics/updateToUsd',True)
carb.settings.get_settings().set_bool('/physics/updateToFabric',False)
timeline=omni.timeline.get_timeline_interface();timeline.play()
for _ in range(30):app.update()
writer=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-s','640x360','-r','30','-pix_fmt','rgb24','-i','pipe:0','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(out/'motion.mp4')],stdin=subprocess.PIPE)
rows=[]
try:
    for i in range(160):
        goal=0.12 if 25<=i<95 else 0.
        drive.GetTargetPositionAttr().Set(goal)
        app.update()
        pos=UsdGeom.XformCache().GetLocalToWorldTransform(drawer.GetPrim()).ExtractTranslation()
        rgb=np.asarray(ann.get_data())
        if rgb.shape==(360,640,4): writer.stdin.write(np.ascontiguousarray(rgb[:,:,:3]).tobytes())
        rows.append(dict(frame=i,command=goal,xyz=list(pos),clock=timeline.get_current_time(),rgb_shape=list(rgb.shape)))
finally:
    writer.stdin.close(); rc=writer.wait()
    timeline.stop()
    report=dict(axis='X',limit_m=[0,.14],steps=rows,peak=max(r['xyz'][0] for r in rows),end=rows[-1]['xyz'],
        passed=rc==0 and all(r['rgb_shape']==[360,640,4] for r in rows) and max(r['xyz'][0] for r in rows)>.11 and abs(rows[-1]['xyz'][0])<.01 and max(abs(r['xyz'][1]) for r in rows)<.003)
    (out/'readback.json').write_text(json.dumps(report,indent=2))
    app.close()
