"""TacSim's small camera interface backed by native USD/RTX annotators in Isaac6."""
from __future__ import annotations

import numpy as np


class RtxCamera:
    def __init__(self, prim_path: str, resolution: tuple[int, int], name: str = ''):
        import omni.usd
        from pxr import UsdGeom

        self.path = prim_path
        self.resolution = resolution
        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        self.camera = UsdGeom.Camera(prim) if prim.IsValid() else UsdGeom.Camera.Define(stage, prim_path)
        self.annotators = {}
        self.render_product = None

    def initialize(self):
        import omni.replicator.core as rep

        self.render_product = rep.create.render_product(self.path, self.resolution)
        self._attach('rgb')

    def _attach(self, name):
        import omni.replicator.core as rep

        annotator = rep.AnnotatorRegistry.get_annotator(name, device='cpu')
        annotator.attach([self.render_product.path])
        self.annotators[name] = annotator

    def set_clipping_range(self, near_distance: float, far_distance: float):
        from pxr import Gf

        self.camera.CreateClippingRangeAttr(Gf.Vec2f(near_distance, far_distance))

    def add_distance_to_image_plane_to_frame(self):
        self._attach('distance_to_image_plane')

    def get_depth(self):
        return np.asarray(self.annotators['distance_to_image_plane'].get_data())

    def get_rgba(self):
        return np.asarray(self.annotators['rgb'].get_data())

    def get_rgb(self):
        return self.get_rgba()[..., :3]

    def get_current_frame(self, clone=False):
        return {'distance_to_image_plane': self.get_depth()}
