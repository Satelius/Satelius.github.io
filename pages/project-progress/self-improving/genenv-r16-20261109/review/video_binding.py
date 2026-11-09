"""Bind a time-stamped video interpretation to one registered native task under a declared goal."""
from pathlib import Path
import json,hashlib,subprocess,sys,os,time
s=Path(__file__).resolve().parents[1]
name=sys.argv[1]
if name not in ('near-video-r2','near-video-r3'):raise ValueError("unregistered instance request")
case=s/'runs'/('binding-'+name);case.mkdir()
interpret=json.loads((s/'review/video-answer.txt').read_text());media=json.loads((s/'review/ingest-video.json').read_text())['video']
movie=s/'assets/bottle-reference.mp4'
assert hashlib.sha256(movie.read_bytes()).hexdigest()==media['source']['sha256']
if interpret['family']!='bottle_shelf':raise ValueError('reference family conflicts with supplied target')
duration=media['frame_count']*media['fps_den']/media['fps_num']
for interval in interpret['intervals']:
    if not (0<=interval['start']<=interval['end']<=duration+.01):raise ValueError('interval not supported by decoded frames')
params=[-.04,.025,.114,-7.]
request=dict(goal='put_bottle_in_shelf',reference=media['source']['sha256'],sequence=media['sequence']['sha256'],
    intervals=interpret['intervals'],unknown=interpret['unknown'],condition=params,condition_origin='frozen native development instance; not inferred metric geometry')
(case/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
env={**os.environ,'GENENV_BOTTLE_CONDITION':json.dumps(params,separators=(',',':'))}
cmd=['bash',str(s/'review/uni-native.sh'),request['goal'],name]
t=time.monotonic()
with (s/'review'/f'{name}.log').open('x') as log:
    r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=600)
(case/'execution.json').write_text(json.dumps(dict(command=cmd,exit=r.returncode,elapsed_s=time.monotonic()-t),indent=2))
