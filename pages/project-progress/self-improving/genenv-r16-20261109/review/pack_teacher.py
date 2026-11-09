import json,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
site=Path(__file__).resolve().parents[1]
episodes=sorted((site/'runs/native1/robolab/AuditBananaFixedTask').glob('episode_*'))
def pack(ep):
    paths=sorted((ep/'frames').glob('*.npz'))
    assert (ep/'summary.json').is_file()
    meta=json.loads((ep/'meta/info.json').read_text())
    dst=site/'assets'/('teacher-'+ep.name+'.mp4')
    cmd=['ffmpeg','-v','error','-f','rawvideo','-s','960x360','-r',str(meta['fps']),'-pix_fmt','rgb24','-i','pipe:0','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as writer:
        for i,p in enumerate(paths):
            with np.load(p) as f:
                frame=Image.new('RGB',(960,360))
                frame.paste(Image.fromarray(f['observation.images.agentview']).resize((640,360)),(0,0))
                frame.paste(Image.fromarray(f['observation.images.cam_left_wrist']).resize((320,180)),(640,0))
                frame.paste(Image.fromarray(f['observation.images.tacumi_tactile_composite']).resize((320,180)),(640,180))
                writer.stdin.write(frame.tobytes())
                if i in (0,len(paths)-1):frame.save(site/'assets'/f'{ep.name}-{i}.jpg',quality=88)
        writer.stdin.close();assert writer.wait()==0
    n=int(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames','-of','csv=p=0',str(dst)]))
    assert n==len(paths)
    print(ep.name,n,flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(pack,episodes))
