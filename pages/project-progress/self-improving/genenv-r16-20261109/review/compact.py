"""Retain large research inputs in the experiment output directory; keep portable evidence on the site."""
from pathlib import Path
import json, shutil, hashlib, sys, importlib.util
import h5py
site=Path(__file__).resolve().parents[1]
exp=site.parents[1]/'TacHarness-exp'
archive=site.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/raw'
archive.mkdir(exist_ok=True)
sys.path.insert(0,str(exp/'src'))
from tacharness.cvpr_protocol.pilot_qualification import score_bowl_replay
spec=importlib.util.spec_from_file_location('assess',exp/'.scratch/learning-pilot-20261109/assess_teacher.py')
assess=importlib.util.module_from_spec(spec);spec.loader.exec_module(assess)
for run in sorted((site/'runs').iterdir()):
    if not (run/'receipt.json').is_file() or not (run/'teacher.trace.jsonl').is_file():continue
    if (run/'review.json').is_file():continue
    request=json.loads((run/'request.json').read_text()); score=score_bowl_replay(list(map(json.loads,(run/'teacher.trace.jsonl').open())),request['task'])
    dest=archive/run.name;dest.mkdir(exist_ok=True)
    with h5py.File(run/'teacher.hdf5') as f:
        keys=list(f['data'])
        if keys:
            score['decoded_video_frames']=assess.video(run,f['data'][keys[0]]['obs'])
    (run/'review.json').write_text(json.dumps(score,indent=2))
    for name in ['teacher.hdf5','depth_m.npz']:
        path=run/name
        if path.is_file():shutil.move(path,dest/name)
    print(run.name,score['native_window_passed'],score['collection_qualified'],score.get('decoded_video_frames'))
# The original compact videos cover every recorded frame. Archive only after validation.
from subprocess import check_output
for ep in sorted((site/'runs/native1/robolab/AuditBananaFixedTask').glob('episode_*')):
    frames=ep/'frames';video=site/'assets'/('teacher-'+ep.name+'.mp4')
    if frames.is_dir():
        n=int(check_output(['ffprobe','-v','error','-count_frames','-show_entries','stream=nb_read_frames','-of','csv=p=0',video]))
        assert n==len(list(frames.glob('*.npz')))
        dest=archive/'native1'/ep.name;dest.mkdir(parents=True,exist_ok=True)
        shutil.move(frames,dest/'frames')
for path in (site/'runs/native1/robolab/AuditBananaFixedTask/robolab_native').glob('*.hdf5'):
    dest=archive/'native1';dest.mkdir(exist_ok=True)
    shutil.move(path,dest/path.name)
