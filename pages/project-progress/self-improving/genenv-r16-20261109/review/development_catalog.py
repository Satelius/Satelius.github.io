"""Build a reviewable catalogue of frozen development instances from the actual receipts."""
import hashlib
import json
from pathlib import Path

site=Path(__file__).resolve().parents[1]
sources=json.loads((site/'review/sources.json').read_text())
def read(p):return json.loads(p.read_text())
def ref(p):return p.relative_to(site).as_posix()
def sha(p):
    with p.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
rows=[]
for instance in ('stove-origin','stove-east','stove-west','drawer-east-v2'):
    attempts=sorted(p.parent for p in (site/'runs').glob(instance+'*/review.json'))
    assert len(attempts)==3
    scores=[read(p/'review.json') for p in attempts]
    requests=[read(p/'request.json') for p in attempts]
    assert len({json.dumps(j['changes_wxyz'],sort_keys=True) for j in requests})==1
    teacher=Path(read(attempts[0]/'receipt.json')['command'][1])
    rows.append(dict(instance=instance,task=requests[0]['task'],backend='Tabero / Sim 6.2',teacher=teacher.name,
        teacher_sha256=sha(teacher),teacher_access='source demonstration replay',lineage=[requests[0]['source_sha256'],requests[0]['source_demo']],
        requested_pose_wxyz=requests[0]['changes_wxyz'],observed_resets=[ref(p/'teacher.reset.json') for p in attempts],
        native_success=sum(j['native_success_seen'] for j in scores),qualified=sum(j['collection_qualified'] for j in scores),
        attempts=len(attempts),rule='native + grasp/release + stable support for ten consecutive 50 ms frames',
        measurements=[ref(p/'review.json') for p in attempts],media=[ref(p/'teacher.mp4') for p in attempts]))
for instance in ['confirmed-banana','confirmed-block']:
    records=sorted((site/'runs'/instance).glob('trial-*/result.json'))
    trials=[read(p) for p in records]; assert len(trials)==3 and len({j['scene_sha256'] for j in trials})==1
    rule='upward-support-retreat-v2';assert all(j['rule']==rule for j in trials)
    rows.append(dict(instance=instance,task=trials[0]['task_sha256'],backend='RoboLab / Sim 6.2',teacher='Cartesian IK',
        teacher_sha256=sources['sha256']['scripts/agentic/probe_generated_layout.py'],teacher_access='privileged object and gripper state',
        scene_sha256=trials[0]['scene_sha256'], requested_task=ref(Path(trials[0]['task'])),
        seed=trials[0]['seed'],observed_resets=[j['initial_base_xyz'] for j in trials],
        native_success=sum(j['native'] for j in trials),qualified=sum(j['qualified'] for j in trials),attempts=3,
        rule=rule,measurements=[ref(p) for p in records],media=[ref(p.parent/'scene.mp4') for p in records]))
b=read(site/'review/bottle-qualification.json')
for instance,cases in [('near-bottle',b[:3]),('far-bottle',b[3:])]:
    assert all(j['request']==cases[0]['request'] for j in cases)
    task=site.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/uni60/work/envs/put_bottle_in_shelf.py'
    rows.append(dict(instance=instance,task='put_bottle_in_shelf',backend='UniVTAC / Sim 6.0.0.1',teacher='native pre-grasp',teacher_sha256=sha(task),
        teacher_access='privileged bottle and shelf poses',requested=cases[0]['request'],seed=1,observed_resets=[j['bottle_actual'] for j in cases],
        native_success=sum(j['recomputed_native_success'] for j in cases),qualified=None,attempts=len(cases),
        rule='support pair and empty tactile calibration unverified',measurements=['review/bottle-qualification.json'],
        media=[f"runs/{j['case']}-startup/sampled.mp4" for j in cases]))
for row in rows:
    row["eligible_development_condition"]=row["attempts"]>=3 and row["qualified"] is not None and row["qualified"]>=2
assert sum(r["eligible_development_condition"] for r in rows)==5
(site/'review/development-instances.json').write_text(json.dumps(dict(schema='tacharness.review.development_instances.v1',split='development',instances=rows),indent=2))
