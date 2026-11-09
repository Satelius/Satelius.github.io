from pathlib import Path
import json,sys
import numpy as np
import uipc
from uipc import Engine, World, Scene, SceneIO, Matrix4x4,view
from uipc.geometry import SimplicialComplexIO,label_surface,label_triangle_orient,flip_inward_triangles,ground
from uipc.constitution import StableNeoHookean,ElasticModuli
out=Path(__file__).resolve().parents[1]/'runs'/sys.argv[1];out.mkdir()
source=Path('/runtime/UniVTAC/third_party/TacEx/source/tacex_uipc/libuipc/assets/sim_data/tetmesh/cube.msh')
for name,E in [('soft',1.e4),('firm',1.e6)]:
    work=out/name; work.mkdir()
    engine=Engine('cuda',str(work));world=World(engine)
    scene=Scene(Scene.default_config())
    snh=StableNeoHookean();scene.constitution_tabular().insert(snh)
    scene.contact_tabular().default_model(.5,1.e9)
    trans=Matrix4x4.Identity();trans[:3,:3]*=.11
    cube=SimplicialComplexIO(trans).read(str(source));label_surface(cube);label_triangle_orient(cube)
    cube=flip_inward_triangles(cube)
    snh.apply_to(cube,ElasticModuli.youngs_poisson(E,.45));scene.contact_tabular().default_element().apply_to(cube)
    vertices=view(cube.positions());vertices[:,1]+=.18-float(vertices[:,1].min())
    body=scene.objects().create('sample');body.geometries().create(cube)
    support=scene.objects().create('support');support.geometries().create(ground(0.))
    world.init(scene);io=SceneIO(scene); coords=[]
    for frame in range(80):
        world.advance();world.retrieve()
        surf=io.simplicial_surface();coords.append(np.array(surf.positions().view()).reshape(-1,3).copy())
    data=np.stack(coords);np.savez_compressed(work/'vertices.npz',xyz=data)
    (work/'result.json').write_text(json.dumps(dict(E=E,material='StableNeoHookean',n_frames=len(coords),surface_vertices=data.shape[1],y_min=data[:,:,1].min(axis=1).tolist(),thickness_m=np.ptp(data[:,:,1],axis=1).tolist()),indent=2))
