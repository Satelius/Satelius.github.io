"""Put the four synchronously sampled, recorded image streams on the same native clock."""
import io, json, subprocess
from pathlib import Path
import h5py
import numpy as np
from PIL import Image, ImageDraw

site=Path(__file__).resolve().parents[1]
keys=['observation/head/rgb','observation/wrist/rgb','tactile/left_tactile/rgb','tactile/right_tactile/rgb']
for case in json.loads((site/'review/bottle-qualification.json').read_text()):
    record=case.get('demonstration')
    if record is None: continue
    dest=site/'runs'/(case['case']+'-startup')/'synchronized.mp4'
    with h5py.File(record['path']) as h:
        steps=h['step'][:];assert np.all(np.diff(steps)==2)
        streams=[h[k][:] for k in keys]
        cmd=['ffmpeg','-nostdin','-y','-v','error','-f','rawvideo','-s','960x566','-pix_fmt','rgb24','-framerate','60','-i','pipe:0','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)]
        with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
            for i,step in enumerate(steps):
                canvas=Image.new('RGB',(960,566),'#182e27');draw=ImageDraw.Draw(canvas)
                for n,seq in enumerate(streams):
                    frame=Image.open(io.BytesIO(bytes(seq[i]))).convert('RGB')
                    frame.thumbnail((480,270));cx=(n%2)*480;cy=(n//2)*283
                    canvas.paste(frame,(cx+(480-frame.width)//2,cy))
                    draw.text((cx+8,cy+267),f'{keys[n]}  |  step {step}',fill='white')
                proc.stdin.write(canvas.tobytes())
            proc.stdin.close()
            assert proc.wait()==0
    print(dest, len(steps))
