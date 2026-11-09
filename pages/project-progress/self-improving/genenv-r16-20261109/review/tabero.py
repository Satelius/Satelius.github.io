"""Compile one lineage-preserving Tabero initial state and replay it on the stock driver."""
import argparse, hashlib, json, math, os, subprocess, time
from pathlib import Path
import h5py, numpy as np

root=Path('/workspace/TacHarness-exp')
area=Path(__file__).resolve().parents[1]
runtime=Path('/runtime/TacHarness')
audit=json.loads((root/'outputs/research/learning-pilot-20261109/stage0-audit-v2.json').read_text())
parser=argparse.ArgumentParser()
parser.add_argument('case')
parser.add_argument('--bowl-x',type=int,choices=[-3,0,3],required=True)
parser.add_argument('--target-y',type=int,choices=[-3,0,3],required=True)
parser.add_argument('--yaw',type=int,choices=[-15,0,15],required=True)
parser.add_argument('--task',choices=['stove','drawer'],default='stove')
parser.add_argument('--reference', type=Path, help='optional single image interpretation alongside the explicit stove task')
parser.add_argument('--demo',type=int,default=4)
args=parser.parse_args()
if args.reference:
    interpretation=json.loads(args.reference.read_text())
    if args.task!='stove' or interpretation.get('family')!='stove_bowl':
        raise ValueError('reference does not match the declared stove task family')
out=area/'runs'/args.case
out.mkdir()
task=audit['runs'][0 if args.task=='stove' else 1]
origin=Path(task['source']['path']);target=out/origin.name
def sha(p):
    with p.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
assert sha(origin)==task['source']['sha256']
changes={}
with h5py.File(origin) as src,h5py.File(target,'x') as dst:
    g=dst.create_group('data')
    for k,v in src.attrs.items(): dst.attrs[k]=v
    for k,v in src['data'].attrs.items(): g.attrs[k]=v
    key=f'demo_{args.demo}'
    src.copy(src['data'][key],g,name=key)
    state=g[key]['initial_state']
    for name,entity,dx,dy,yaw in [('rigid_object','akita_black_bowl_1',args.bowl_x,0,args.yaw),('articulation','flat_stove_1' if args.task=='stove' else 'white_cabinet_1',0,args.target_y,0)]:
        v=state[name+'/'+entity+'/root_pose']
        p=v[0].astype(float); before=p.tolist()
        p[:2]+=[dx/100,dy/100]
        w,x,y,z=p[3:];a=math.radians(yaw)/2;c,s=math.cos(a),math.sin(a)
        p[3:]=[c*w-s*z,c*x-s*y,c*y+s*x,c*z+s*w]
        v[0]=p; changes[entity]={'original':before,'requested':v[0].tolist()}
record=dict(source=str(origin),source_sha256=sha(origin),source_demo=args.demo,derived_sha256=sha(target),changes_wxyz=changes,task=task['task_key'])
if args.reference:
    record['reference']=dict(image_sha256=sha(area/'assets/bowl-scene.png'),answer_sha256=sha(args.reference),
                             declared_goal=task['task_key'],unknown=interpretation['unknown'])
(out/'request.json').write_text(json.dumps(record,indent=2))
provider=root/'src/providers/LIBERO'
env={**os.environ,**audit['runtime']['environment'],'TACHARNESS_BOWL_TRACE_DIR':str(out),'TACHARNESS_PROBE_HIDE_OPTICAL_GEL':'1','HDF5_TRAJ_SOURCE_DIR':str(out),'LIBERO_CONFIG_DIR':str(provider/'benchmarks/datasets/libero/config'),'LIBERO_ASSETS_DATA_DIR':str(runtime/'inputs/assets/vendor/tacbenchhub/external/tabero/datasets/Isaaclab_Libero/USD'),'OMNI_KIT_ACCEPT_EULA':'Y','HF_HUB_OFFLINE':'1','ISAAC_FAST_EXIT':'0','PYTHONUNBUFFERED':'1','XDG_RUNTIME_DIR':'/tmp','VK_ICD_FILENAMES':'/etc/vulkan/icd.d/nvidia_icd.json'}
ref=root/'outputs/research/learning-pilot-20261109/optical-reference-dev1.npz'
env.update(TACHARNESS_BOWL_OPTICAL_REFERENCE=str(ref),TACHARNESS_BOWL_OPTICAL_SHA256=sha(ref))
suite,tid=task['task_key'].split(':')
cmd=[str(runtime/'.venv-isaacsim62/bin/python'),str(provider/'scripts/tools/replay_demos_with_camera.py'),'--task','Isaac-Libero-Franka-Replay-Camera-Tactile-v0','--task_suite',suite,'--task_id',tid,'--demo_id',str(args.demo),'--num_envs','1','--dump_data','--recorder_type','7dpf','--output_file',str(out/'teacher.hdf5'),'--output_failure_record_file',str(out/'failures.jsonl'),'--camera_view_list','agentview','eye_in_hand','--tactile_sensor_list','gsmini_left','gsmini_right','--tactile_output_type','tactile_rgb','--device','cuda:0','--headless']
t=time.monotonic()
with (out/'native.log').open('w') as log:
    rc=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420).returncode
receipt=dict(command=cmd,elapsed_s=time.monotonic()-t,rc=rc)
reset=out/'teacher.reset.json'
if reset.exists():
    r=json.loads(reset.read_text())
    receipt['loaded_derived_source']=Path(r['source_file']).resolve()==target.resolve()
    errors={}
    for k,v in changes.items():
        actual=np.array(r['initial_world_poses'][k]); target_pose=np.array(v['requested'])
        errors[k]=dict(xyz_error_m=float(np.linalg.norm(actual[:3]-target_pose[:3])),orientation_error_rad=float(2*math.acos(np.clip(abs(np.dot(actual[[6,3,4,5]],target_pose[3:]))/(np.linalg.norm(actual[3:])*np.linalg.norm(target_pose[3:])),0,1))))
    receipt['reset_errors']=errors
    receipt['realized']=receipt['loaded_derived_source'] and all(e['xyz_error_m']<0.001 and e['orientation_error_rad']<0.005 for e in errors.values())
(out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(receipt)
