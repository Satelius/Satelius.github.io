"""Decode each distinct video and extract the browser's poster from its own frames."""
import concurrent.futures
import json
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'review/catalog.json').read_text())
media=sorted(set(p for p in root.rglob('*.mp4') if p.is_file()))
primary={x['media'] for x in catalog}
def check(path):
    rel=path.relative_to(root).as_posix()
    cmd=['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=height,width,nb_frames:format=duration','-of','json',str(path)]
    info=json.loads(subprocess.check_output(cmd))
    if not info['streams']:
        return dict(path=rel,video=False,bytes=path.stat().st_size)
    first=info['streams'][0]
    frames=int(first.get('nb_frames',0))
    dur=float(info['format']['duration'])
    assert frames>0 and dur>0,(rel,info)
    decode=subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','2','-i',str(path),'-map','0:v:0','-f','null','-'],check=True,capture_output=True)
    if rel in primary:
        poster=root/'assets/posters'/(rel.replace('/','_')+'.jpg')
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-ss',str(min(dur*.45,0.32)),'-i',str(path),'-frames:v','1','-threads','1',str(poster)],check=True)
        assert poster.exists() and poster.stat().st_size>0,rel
    return dict(path=rel,video=True,frames=frames,seconds=dur,width=first['width'],height=first['height'])
with concurrent.futures.ThreadPoolExecutor(4) as pool: results=list(pool.map(check,media))
(root/'review/media-check.json').write_text(json.dumps(results,indent=2))
print('Decoded',sum(x['video'] for x in results),'/',len(results))
