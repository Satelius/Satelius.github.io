"""Read native task scores, synchronized images and the sampled heights in the four controlled trials."""
import hashlib
import json
from pathlib import Path

import h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

site = Path(__file__).resolve().parents[1]
raw = site.parents[1] / "TacHarness-genenv/outputs/genenv-audit-20261109/uni60"
colors = ["#197449", "#a64935", "#477ea0", "#8a8073"]
fig, ax = plt.subplots(figsize=(8.4, 3.6), layout="constrained")
cases = []
for case,color in zip(["near-fixed","near-video-r2","near-video-r3","far-fixed"],colors):
    folder = site / "runs" / (case + "-startup")
    score = json.loads((folder/"native-result.json").read_text())
    pre = json.loads((folder/"pregrasp.json").read_text())
    trace = [json.loads(line) for line in (folder/"frames.jsonl").read_text().splitlines()]
    steps = np.array([frame["step"] for frame in trace])
    z = np.array([frame["actor_positions"]["prism"][2] for frame in trace])
    ax.plot(steps/120, z*100, color=color, label=case+" / "+score["result"])
    record = dict(case=case, seed=1, request=pre["condition"], shelf_actual=pre["shelf_actual"],
        bottle_actual=pre["bottle_actual"], physics_steps=score["cost_physics_step"],
        result=score["result"], final_native_relative_xyz_m=score["bottle_pose"][:3],
        sampled_peak_z_m=float(z.max()), final_sampled_z_m=float(z[-1]),
        initial_pressure_mm=trace[0]["pressure_mm"], captures=len(trace),
        task_pair_support_force=None, released_stable_support_qualification="unverified")
    # The actual native pose predicate checks relative XYZ and local bottle Z.
    x,y,zz = score["bottle_pose"][:3]
    _,qx,qy,_ = score["bottle_pose"][3:]
    alignment=1-2*(qx*qx+qy*qy)
    predicate=abs(x)<.02 and abs(y)<.1 and abs(zz)<.02 and alignment>.965
    assert predicate==(score["result"]=="success")
    record.update(final_axis_dot=float(alignment),recomputed_native_success=bool(predicate))
    hdf = raw / case / "put_bottle_in_shelf/demo/hdf5/1.hdf5"
    if hdf.is_file():
        with h5py.File(hdf) as h:
            t=h["step"][:]
            assert np.all(np.diff(t)>0)
            streams={}
            for key in ["observation/head/rgb","observation/wrist/rgb","tactile/left_tactile/rgb","tactile/right_tactile/rgb"]:
                images=h[key][:]
                streams[key]=dict(frames=len(images),distinct_encoded_frames=len(set(bytes(x) for x in images)))
                assert len(images)==len(t)
            record["demonstration"] = dict(path=str(hdf),sha256=hashlib.file_digest(hdf.open("rb"),"sha256").hexdigest(),
                frames=len(t),step_range=[int(t[0]),int(t[-1])],step_spacing=np.unique(np.diff(t)).tolist(),streams=streams,
                tactile_shape=list(h["tactile/left_tactile/press_depth"].shape), joint_shape=list(h["embodiment/joint"].shape))
    cases.append(record)
ax.set(xlabel="Simulation time (s)", ylabel="Bottle center height (cm)")
ax.spines[['right','top']].set_visible(False)
ax.legend(ncols=2,fontsize=8)
fig.savefig(site/"assets/bottle-height.png",dpi=145)
(site/"review/bottle-qualification.json").write_text(json.dumps(cases, indent=2))
