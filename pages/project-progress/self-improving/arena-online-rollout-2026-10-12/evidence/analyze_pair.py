"""Read immutable attempts; write new pair/error receipts, without a simulator."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
from collections import Counter

import numpy as np

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts/agentic'))
from tacharness.isaaclab.arena_online_records import read_online_decision_records
from preflight_tacjev_arena import verify_video
from tools.audit_p0_tactile_episode import audit

DIRECTIONS = {'MV_FWD':[1,0,0], 'MV_BACK':[-1,0,0], 'MV_LEFT':[0,1,0],
              'MV_RIGHT':[0,-1,0], 'MV_UP':[0,0,1], 'MV_DOWN':[0,0,-1]}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')

def read(path):
    return json.loads(path.read_text())

def stats(values):
    if not values:
        return {'count':0, 'median_m':None}
    return {'count':len(values),'median_m':float(np.median(values)),
            'mean_m':float(np.mean(values)),'min_m':min(values),'max_m':max(values),
            'reversed_count':sum(value < -1e-6 for value in values)}

def world_point(point, root_pose):
    q = np.asarray(root_pose[3:7]); v = np.asarray(point)
    return np.asarray(root_pose[:3]) + v + 2*np.cross(q[:3], np.cross(q[:3],v) + q[3]*v)

def inspect(name):
    run = STAGE/name
    report, rows = read(run/'report.json'), read(run/'native/trajectory.json')
    records = read_online_decision_records(run/'decisions', native_frame_count=len(rows))
    motions, waits, returned_models = [], [], set()
    for record in records:
        directory = run/'decisions'/record['decision_id']
        metadata = read(directory/'interpreter.json')
        finish = record['execution']
        inference = read(directory/'inference/inference.json')
        waits.append(inference['elapsed_s']); returned_models.add(inference['response_model'])
        start = np.asarray(metadata['initial_tcp_position_base_m'])
        assert start.shape == (3,)
        if record['token'] in DIRECTIONS and finish['actual_control_frame_count'] == 5:
            delta = np.asarray(rows[finish['frame_end_exclusive']-1]['control_tcp_pose_base_xyzw'][:3])-start
            direction = np.asarray(DIRECTIONS[record['token']])
            projection = float(delta@direction)
            motions.append({'token':record['token'],'projection_m':projection,
                            'cross_m':float(np.linalg.norm(delta-projection*direction)),
                            'decision_id':record['decision_id'],'frame_start':finish['frame_start']})
    for index,path in enumerate(sorted((run/'native/frames').glob('frame_*.npz'))):
        with np.load(path,allow_pickle=False) as frame:
            assert int(frame['frame_index'][0]) == index
            assert np.isfinite(frame['action']).all() and frame['action'].size == 7
            assert np.allclose(frame['action'],rows[index]['target_action'],atol=1e-6,rtol=0)
    first = records[0]
    prefix = []
    for motion in motions:
        if motion['token'] != 'MV_FWD': break
        prefix.append(motion)
    tactile = audit(run/'native')
    video = verify_video(run/'rollout_h264.mp4')
    result = {'native_frames':len(rows),'native_success':report['native_success'],
        'outcome':report['outcome'],'native_accounting_valid':report['execution_accounting_valid'],
        'causal_valid':report['decisions_validation']['valid'],
        'all_actions_match_native_rows':True,'video':video,'tactile':tactile,
        'teacher_requests':report['teacher_inference_requests'],'decision_count':len(records),
        'token_counts':dict(Counter(r['token'] for r in records)),
        'response_models':sorted(returned_models),'max_decision_wait_s':max(waits),
        'http_attempt_count':sum(len(read(run/'decisions'/r['decision_id']/'inference/inference.json')['attempts']) for r in records),
        'direction_metrics':{token:{'axis_projection':stats([m['projection_m'] for m in motions if m['token']==token]),
            'cross_axis':stats([m['cross_m'] for m in motions if m['token']==token])} for token in DIRECTIONS},
        'first_tcp_base_xyz_m':read(run/'decisions'/first['decision_id']/'interpreter.json')['initial_tcp_position_base_m'],
        'last_tcp_base_xyz_m':rows[-1]['control_tcp_pose_base_xyzw'][:3],
        'contact_frames':sum(any(row['physical_contact'].values()) for row in rows),
        'report_sha256':sha(run/'report.json'),'interpreter_config':read(run/'interpreter.json')}
    return result, prefix, records, rows

a, prefix_a, records_a, rows_a = inspect('attempt-a')
b, prefix_b, records_b, rows_b = inspect('attempt-b')
diagnosis = read(STAGE/'diagnosis_before_b_v2.json')
initial = read(STAGE/'initial_pair_check.json')
assert diagnosis['baseline_report_sha256'] == a['report_sha256']
assert datetime.fromisoformat(diagnosis['created_at']) < datetime.fromisoformat(read(STAGE/'attempt-b/report.json')['started_at'])
configs = a['interpreter_config'], b['interpreter_config']
changed = [key for key in configs[0] if configs[0][key]!=configs[1][key]]
assert set(changed)=={'version','translation_step_m','translation_clamp_m'}
assert a['response_models']==b['response_models']==['gpt-6.1-sol']
n = min(len(prefix_a),len(prefix_b))
prefix_metrics = {name:{'axis':stats([m['projection_m'] for m in prefix[:n]]),
                       'cross_axis':stats([m['cross_m'] for m in prefix[:n]])}
                  for name,prefix in [('A',prefix_a),('B',prefix_b)]}
threshold = diagnosis['expected_response']['same_direction_full_hold5_axis_projection_median_at_least_m']
pair = {'schema':'tacharness.arena.online-agent-comparison.v1','created_at':datetime.now(timezone.utc).isoformat(),
    'diagnosis_before_b_sha256':sha(STAGE/'diagnosis_before_b_v2.json'),'initial_pair_check':initial,
    'configuration_changes':changed,'A':a,'B':b,'common_forward_prefix':prefix_metrics,
    'common_forward_prefix_count':n,'predeclared_full_forward_projection_threshold_m':threshold,
    'full_forward_projection_threshold_passed':b['direction_metrics']['MV_FWD']['axis_projection']['median_m']>=threshold,
    'comparable':initial['actual_initial_state']['unchanged'] and initial['control_source_files_unchanged'] and initial['native_run_function_identical'],
    'formal_online_diagnosis_pair_complete':True,
    'candidate_adopted':False,'positive_demonstrations':0,
    'decision':'Reject the candidate as an overall control improvement: forward displacement rises but cross-axis response worsens and DOWN reverses. Neither episode succeeds or contacts the cube.',
    'limits':['single development opening','step and clamp co-change','closed-loop token/context distribution changes','no extra unchanged rerun within two-start cap','no statistical/general-calibration/learning claim']}
write(STAGE/'comparison.json',pair)

# Exact observed empty closure; audit may read state, the teacher never receives it.
grasp = next(record for record in records_b if record['token']=='GRASP')
decision = STAGE/'attempt-b/decisions'/grasp['decision_id']
with np.load(decision/'http_state_before.npz',allow_pickle=False) as state:
    root_pose = state['scene.articulation.robot.root_pose'][0]
    cube_world = state['scene.rigid_object.dex_cube.root_pose'][0,:3]
tcp = np.asarray(read(decision/'interpreter.json')['initial_tcp_position_base_m'])
tcp_world = world_point(tcp,root_pose)
finish = grasp['execution']; interval=rows_b[finish['frame_start']:finish['frame_end_exclusive']]
assert np.linalg.norm(tcp_world-cube_world) > .25
assert not any(any(row['physical_contact'].values()) for row in interval)
error_audit={'schema':'tacharness.arena.empty-close-audit.v1','decision_id':grasp['decision_id'],
    'control_frame_start':finish['frame_start'],'control_frame_end_exclusive':finish['frame_end_exclusive'],
    'tcp_before_base_xyz_m':tcp.tolist(),'tcp_before_world_xyz_m':tcp_world.tolist(),
    'cube_before_world_xyz_m':cube_world.tolist(),'tcp_cube_distance_m':float(np.linalg.norm(tcp_world-cube_world)),
    'vertical_gap_m':float(tcp_world[2]-cube_world[2]),'physical_contact_in_interval':False,
    'max_contact_force_n':max(v for row in interval for v in row['contact_force_n'].values()),
    'interpretation':'Premature empty finger closure during cube-grasp task; teacher internal intent is not inferred.'}
write(STAGE/'empty_close_audit.json',error_audit)
evidence_paths=[STAGE/'empty_close_audit.json',decision/'interpreter.json',decision/'http_state_before.npz',STAGE/'attempt-b/native/trajectory.json']
error={'schema':'tacharness.tacjev-known-error.v1','episode_id':'attempt-b','decision_id':grasp['decision_id'],
    'token':'GRASP','finish_sha256':sha(decision/'finish.json'),
    'reason':'Premature empty closure: TCP was over0.67m from cube, with zero contact and force; preserve actual action and exclude its positive label.',
    'evidence':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in evidence_paths]}
write(STAGE/'known_error_receipt.json',error)
print(json.dumps({'pair_comparable':pair['comparable'],'full_forward_threshold_passed':pair['full_forward_projection_threshold_passed'],
    'common_prefix':prefix_metrics,'down_B':b['direction_metrics']['MV_DOWN'],
    'native_successes':[a['native_success'],b['native_success']],'known_error':error_audit},ensure_ascii=False))
