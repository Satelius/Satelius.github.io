"""Exercise the published resolved-scene loader with a real RoboTwin actor factory."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys,subprocess
import numpy as np
import sapien
from scipy.spatial.transform import Rotation
from scene_gen.envs.generated_scene import load_resolved_scene
site=Path(__file__).resolve().parents[1];out=site/'runs'/sys.argv[1];out.mkdir()
case=sys.argv[2] if len(sys.argv)>2 else 'new-mesh'
folder=next(p.parent for p in (site/'runs'/case).glob('*/resolved_scene.json'))
resolved=json.loads((folder/'resolved_scene.json').read_text());item=resolved['objects'][0]
scene=sapien.Scene();scene.set_timestep(1/120)
table=scene.create_actor_builder();table.add_box_collision(half_size=[.40,.32,.025]);table.add_box_visual(half_size=[.40,.32,.025],material=[.34,.40,.36]);support=table.build_static('table');support.set_pose(sapien.Pose([0,0,.741-.025]))
holder=SimpleNamespace(scene=scene,table_z_bias=0.,prohibited_area=[])
actors=load_resolved_scene(holder,resolved,asset_roots={item['object_id']:Path(next(f for f in item['source_files'] if f.endswith('model_data0.json'))).parent})
obj=actors[item['object_id']];start=obj.get_pose().p.tolist()
scene.set_ambient_light([.6,.6,.6]);scene.add_directional_light([1,.3,-1],[1,1,1])
camera=scene.add_camera('audit',640,360,.85,.02,6.)
eye=np.array(start)+[.24,-.30,.20];forward=(np.array(start)-eye);forward/=np.linalg.norm(forward);left=np.cross([0,0,1],forward);left/=np.linalg.norm(left);up=np.cross(forward,left)
q=Rotation.from_matrix(np.stack((forward,left,up),axis=1)).as_quat();camera.set_pose(sapien.Pose(eye,q[[3,0,1,2]]))
writer=subprocess.Popen(['ffmpeg','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','640x360','-r','30','-i','pipe:0','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(out/'scene.mp4')],stdin=subprocess.PIPE)
rows=[]
for i in range(180):
    scene.step();contacts=[]
    for c in scene.get_contacts():
        names=[body.entity.name for body in c.bodies]
        if sorted(names)==sorted(['table',item['object_id']]):contacts.append(sum(float(np.linalg.norm(pt.impulse)) for pt in c.points))
    rows.append(dict(step=i+1,xyz=obj.get_pose().p.tolist(),contact_impulses=contacts))
    if i%4==0:
        scene.update_render();camera.take_picture();rgb=camera.get_picture('Color')[:,:,:3]
        writer.stdin.write(np.ascontiguousarray(np.clip(rgb*255,0,255).astype('uint8')).tobytes())
writer.stdin.close();assert writer.wait()==0
j=dict(loader='scene_gen.envs.generated_scene.load_resolved_scene + RoboTwin.envs.utils.create_actor',start=start,
       resolved_sha256=json.loads((folder/'package_manifest.json').read_text())['resolved_scene_sha256'],n=180,
       final_contact_steps=sum(any(v>0 for v in x['contact_impulses']) for x in rows[-30:]),steps=rows)
(out/'result.json').write_text(json.dumps(j,indent=2))
