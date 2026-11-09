from pathlib import Path
import hashlib, json, subprocess, sys, os
from self_improving.harness.x2env.contracts import X2EnvRequest, InputMedia
from self_improving.harness.x2env.store import Store
from self_improving.harness.x2env.input import ingest,InputIngestError
site=Path(__file__).resolve().parents[1]
store=Store(site/'runs/ingest')
cases={'text':dict(text='A banana to the left of a bowl.'),'image':dict(images=(InputMedia(path=str(site/'assets/bowl-scene.png')),)),'video':dict(video=InputMedia(path=str(site/'assets/bottle-reference.mp4')))}
exe=next(Path('/usr/local/lib/node_modules/@openai/codex/node_modules').rglob('bin/codex'))
deploy=site/'review/x2env-deployment.json'
deploy.write_text(json.dumps(dict(state_dir=str(site/'runs/x2state'),timeout_seconds=110,codex=dict(executable=str(exe),sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),model='gpt-6-astra'),schema_version='x2env.deployment.v1'),indent=2))
for key,fields in cases.items():
    if (site/'review'/f'x2-{key}.json').exists(): continue
    req=X2EnvRequest(**fields,seed=7,idempotency_key='r16-'+key,output_dir=str(site/'runs'/('x2-'+key)))
    bundle=ingest(req,store)
    (site/'review'/f'ingest-{key}.json').write_text(bundle.model_dump_json(indent=2))
    command=[sys.executable,'-m','self_improving.harness.x2env.cli','submit','--deployment',str(deploy),'--seed','7','--idempotency-key',req.idempotency_key,'--output',req.output_dir]
    if key=='text':command+=['--text',req.text]
    elif key=='image':command+=['--image',req.images[0].path]
    else:command+=['--video',req.video.path]
    r=subprocess.run(command,capture_output=True,text=True,timeout=130)
    (site/'review'/f'x2-{key}.json').write_text(r.stdout)
    print(key,r.returncode,r.stderr[:200],flush=True)
