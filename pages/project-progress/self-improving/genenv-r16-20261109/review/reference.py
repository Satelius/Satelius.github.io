from pathlib import Path
import io, json, subprocess, hashlib
import h5py, numpy as np
from PIL import Image,ImageDraw
site=Path(__file__).resolve().parents[1]; assets=site/'assets'
f=site.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/bottle.h5'
with f.open('rb') as stream: sha=hashlib.file_digest(stream,'sha256').hexdigest()
assert sha=='c245c706749361037152199a8a8c03bc7d73ed67bea859f083a62c90124d0a44'
with h5py.File(f) as h:
    data=h['observation/head/rgb']; n=len(data)
    def rgb(i):return Image.open(io.BytesIO(data[i])).convert('RGB')
    width,height=rgb(0).size
    command=['ffmpeg','-v','error','-threads','2','-f','rawvideo','-pix_fmt','rgb24','-s',f'{width}x{height}','-r','60','-i','pipe:0','-vf','scale=480:-2','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(assets/'bottle-reference.mp4')]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as proc:
        for i in range(n):proc.stdin.write(rgb(i).tobytes())
        proc.stdin.close();assert proc.wait()==0
    indices=np.linspace(0,n-1,8,dtype=int).tolist()
    strip=Image.new('RGB',(4*320,2*206),'#152320'); draw=ImageDraw.Draw(strip)
    for j,i in enumerate(indices):
        img=rgb(i);img.thumbnail((320,180));x=(j%4)*320;y=(j//4)*206
        strip.paste(img,(x,y));draw.text((x+5,y+181),f'{i}/523  {i/60:.2f}s',fill='white')
    strip.save(assets/'bottle-evidence.jpg',quality=94)
    tags=h['atom/tag'][:]; groups=np.split(np.arange(n),np.where(tags[1:]!=tags[:-1])[0]+1)
    stages=[dict(tag=tags[g[0]].decode(),first=int(g[0]),last=int(g[-1])) for g in groups]
    record=dict(source='byml2024/UniVTAC / isaac51/put_bottle_in_shelf/hdf5/0.hdf5',revision='a08f69b26ebcc87ac14a11e85ba911aee5af72dc',sha256=sha,frames=n,steps=h['step'][:].tolist(),frame_rate_display=60,actor_start={k:d[0].tolist() for k,d in h['actor'].items()},stages=stages,montage_indices=indices)
    (site/'review/bottle-source.json').write_text(json.dumps(record,indent=2))
subprocess.run(['ffmpeg','-v','error','-i',str(site.parent/'learning-pilot-20261109-stage-1/media/source-4.mp4'),'-vf','crop=224:224:0:0','-frames:v','1',str(assets/'bowl-reference.png')],check=True)
