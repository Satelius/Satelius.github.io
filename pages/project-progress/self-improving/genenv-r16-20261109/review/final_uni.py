"""Pack every captured native attempt and retain native outcome separately from tool exit status."""
from pathlib import Path
import json, subprocess, shutil, re, hashlib
import numpy as np
from PIL import Image
s=Path(__file__).resolve().parents[1];u=s.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/uni60'
records=[]
for folder in sorted((s/'runs').glob('*-startup')):
    name=folder.name.removesuffix('-startup');phase=folder/'frames.jsonl'
    if not (folder/'startup.json').exists(): continue
    attempts=sorted((u/name).glob('*/demo/metadata.json'))
    j=json.loads(attempts[0].read_text()).get('1') if attempts else None
    if j is not None:(folder/'native-result.json').write_text(json.dumps(j,indent=2))
    framefiles=sorted(folder.glob('f*.jpg'))
    if framefiles and not (folder/'sampled.mp4').exists():
        with subprocess.Popen(['ffmpeg','-v','error','-f','image2pipe','-c:v','mjpeg','-framerate','20','-i','pipe:0','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'sampled.mp4')],stdin=subprocess.PIPE) as proc:
            for f in framefiles:proc.stdin.write(f.read_bytes())
            proc.stdin.close(); assert proc.wait()==0
    original=None
    for video in sorted((u/name).glob('*/demo/video/*.mp4')):
        result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',video],capture_output=True,text=True)
        if 'video' in result.stdout:
            dst=folder/('native-'+video.name);shutil.copy2(video,dst);original=str(dst.relative_to(s))
    hist=list(map(json.loads,phase.read_text().splitlines())) if phase.exists() else []
    telemetry={}
    if hist:
        telemetry['physics_equal_uipc']=sum(f['step']==f['uipc_advances'] for f in hist)
        telemetry['n']=len(hist)
        telemetry['positions']={key:dict(first=hist[0]['actor_positions'][key],final=hist[-1]['actor_positions'][key],
            max_z=max(f['actor_positions'][key][2] for f in hist),min_z=min(f['actor_positions'][key][2] for f in hist)) for key in hist[0]['actor_positions']}
        telemetry['initial_pressure']=hist[0]['pressure_mm']
    records.append(dict(name=name,metadata=j,telemetry=telemetry,frames=len(framefiles),source_video=original))
(s/'review/uni-outcomes.json').write_text(json.dumps(records,indent=2))
attempts=[]
for log in (s/'review').glob('*.log'):
 if not re.fullmatch(r'(uni-native-\d+|can-(?:v2-)?[456]|bottle-(?:air|near|far)|near-fixed|far-fixed|near-video-r[23]|air-isolated)',log.stem):continue
 lines=log.read_text(errors='replace').splitlines()
 errors=[l.strip()[:360] for l in lines if re.match(r'^(?:\w*(?:Error|Exception):|Geometry\([0-9]+\) in Object|.*\[error\] .*Assertion )',l)]
 attempts.append(dict(name=log.stem,log=log.name,errors=errors[:6],last_measurements=[l[:240] for l in lines if 'Complete collection' in l or re.search(r'Seed 1 (failed|success)',l)][:3]))
(s/'review/uni-attempts.json').write_text(json.dumps(sorted(attempts,key=lambda a:a['name']),ensure_ascii=False,indent=2))
print('records',len(records))
