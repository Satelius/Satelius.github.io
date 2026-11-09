from pathlib import Path
import json, hashlib
from tacharness.cvpr_protocol.derive import derive_act7d
from tacbenchhub.data.act_dataset import ACTHDF5Dataset
root=Path(__file__).resolve().parents[1]
raw=root.parents[1]/'TacHarness-genenv/outputs/genenv-audit-20261109/raw'
sources=[raw/p/'teacher.hdf5' for p in ('stove-origin','stove-east','stove-west')]
target=raw/'conditions.act7d.hdf5'
report=derive_act7d(sources,target,exclusive=True)
ds=ACTHDF5Dataset(target,chunk_size=20)
row=ds[0]
meta=dict(derivation=report,source_lineage='one original demonstration (#4), three reset conditions',samples=len(ds),
          tensors={k:list(v.shape) for k,v in row.items()},sha256=hashlib.sha256(target.read_bytes()).hexdigest())
(root/'review/student-readback.json').write_text(json.dumps(meta,indent=2))
