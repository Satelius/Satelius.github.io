from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from tacharness.paths import CONFIGS_ROOT

DEFAULT_CONFIG = CONFIGS_ROOT / "tacumi" / "tacsim_group_sample_scene.yaml"


class TacumiTactileRuntime:
    """Attach TacSim solvers to Tacumi sensor prims in an existing Isaac stage."""

    def __init__(
        self,
        *,
        config_path: str | Path = DEFAULT_CONFIG,
        stage: Any | None = None,
        root_prefix: str | None = None,
        expected_sensors: int = 2,
        camera_class: Any | None = None,
        headless: bool = True,
        robot: Any | None = None,
        camera_namespace: str = "/World/TacumiTactileRuntime",
        particle_surface_radius_m: float = 0.005,
        logger: logging.Logger | None = None,
    ) -> None:
        from .camera_runtime import load_cfg
        from .sensor_usd import (
            discover_existing_sensor_roots,
        )
        from .tactile_sensor import TactileSensor

        if stage is None:
            import omni.usd

            stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No active USD stage is available for TacSim")

        self.stage = stage
        self.logger = logger or logging.getLogger("tacumi.tactile_runtime")
        self.camera_namespace = camera_namespace.rstrip("/")
        if not self.camera_namespace.startswith("/World/"):
            raise ValueError(
                "Tacumi camera namespace must be rooted below /World: "
                f"{camera_namespace}"
            )
        self.particle_surface_radius_m = float(particle_surface_radius_m)
        if self.particle_surface_radius_m <= 0.0:
            raise ValueError("Particle tactile projection radius must be positive")
        self.depth_source_counts: dict[str, dict[str, int]] = {}
        self.config_path = Path(config_path).expanduser().resolve()
        if not self.config_path.is_file():
            raise FileNotFoundError(f"TacSim config does not exist: {self.config_path}")
        self.cfg = load_cfg(self.config_path)

        targets = sorted(discover_existing_sensor_roots(stage), key=lambda row: str(row[0]))
        if root_prefix:
            prefix = root_prefix.rstrip("/")
            targets = [row for row in targets if str(row[0]) == prefix or str(row[0]).startswith(prefix + "/")]
        if len(targets) != int(expected_sensors):
            raise RuntimeError(
                f"Expected {expected_sensors} Tacumi tactile sensor roots"
                f"{f' under {root_prefix}' if root_prefix else ''}, found {targets}"
            )

        tagged_targets = [
            (_target_side(model_root, model_key), model_root, model_key)
            for model_root, model_key in targets
        ]
        tagged_sides = {side for side, _, _ in tagged_targets}
        if tagged_sides == {"left", "right"} and len(tagged_targets) == 2:
            tagged_targets.sort(key=lambda row: ("left", "right").index(row[0]))
        else:
            tagged_targets = [
                (side, model_root, model_key)
                for side, (model_root, model_key) in zip(
                    ("left", "right"), targets, strict=True
                )
            ]

        self.sensor_sides = [side for side, _, _ in tagged_targets]
        self.depth_source_counts = {
            side: {"rtx": 0, "particle_projection": 0}
            for side in self.sensor_sides
        }
        self._depth_diagnostics_logged: set[str] = set()
        self._hidden_geometry_logged = False

        self.sensors = [
            TactileSensor(
                session_idx=index,
                camera_class=camera_class,
                session_count=len(tagged_targets),
                model_root=str(model_root),
                model_key=model_key,
                cfg=self.cfg,
                stage=stage,
                ui=None,
                logger=self.logger,
                headless=headless,
                camera_prim_override=(
                    f"{self.camera_namespace}/{side}"
                    if robot is not None
                    else None
                ),
            )
            for index, (side, model_root, model_key) in enumerate(tagged_targets)
        ]
        render_near_override = os.environ.get("TACUMI_DEPTH_RENDER_NEAR_M")
        render_far_override = os.environ.get("TACUMI_DEPTH_RENDER_FAR_M")
        if render_near_override or render_far_override:
            for sensor in self.sensors:
                render_near = float(
                    render_near_override
                    if render_near_override is not None
                    else sensor.render_depth_near
                )
                render_far = float(
                    render_far_override
                    if render_far_override is not None
                    else sensor.render_depth_far
                )
                if render_near <= 0.0 or render_far <= render_near:
                    raise ValueError(
                        "Tacumi render clipping requires 0 < near < far, got "
                        f"near={render_near}, far={render_far}"
                    )
                sensor.render_depth_near = render_near
                sensor.render_depth_far = render_far
                sensor.camera.set_clipping_range(
                    near_distance=render_near,
                    far_distance=render_far,
                )

        self.robot = robot
        self._camera_mounts: dict[str, dict[str, Any]] = {}
        self._camera_sync_count = 0
        if robot is not None:
            from pxr import Gf, Usd, UsdGeom

            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            body_by_side = {"left": "Link5", "right": "Link4"}
            for side, sensor in zip(
                self.sensor_sides, self.sensors, strict=True
            ):
                body_name = body_by_side[side]
                body_index = list(robot.body_names).index(body_name)
                body_prim = stage.GetPrimAtPath(
                    f"{root_prefix.rstrip('/')}/{body_name}"
                )
                contact_prim = sensor.layout["contact_prim"]
                collider_prim = stage.GetPrimAtPath(
                    f"{contact_prim.GetPath()}/Cube"
                )
                if not collider_prim.IsValid():
                    raise RuntimeError(
                        f"Tacumi contact collider is missing for {side}: "
                        f"{contact_prim.GetPath()}/Cube"
                    )
                relative = (
                    xform_cache.GetLocalToWorldTransform(collider_prim)
                    * xform_cache.GetLocalToWorldTransform(body_prim).GetInverse()
                )
                origin = np.asarray(
                    relative.Transform(Gf.Vec3d(0.0, 0.0, 0.0)),
                    dtype=np.float64,
                )
                basis = []
                lengths = []
                for axis in (
                    Gf.Vec3d(1.0, 0.0, 0.0),
                    Gf.Vec3d(0.0, 1.0, 0.0),
                    Gf.Vec3d(0.0, 0.0, 1.0),
                ):
                    vector = (
                        np.asarray(relative.Transform(axis), dtype=np.float64)
                        - origin
                    )
                    length = float(np.linalg.norm(vector))
                    basis.append(vector / max(length, 1.0e-12))
                    lengths.append(length)
                up_axis = basis[int(np.argmax(lengths))]
                normal_axis = basis[int(np.argmin(lengths))]
                self._camera_mounts[side] = {
                    "body_index": body_index,
                    "pad_position": origin,
                    "pad_up_axis": np.asarray(up_axis, dtype=np.float64),
                    "pad_normal_axis": np.asarray(
                        normal_axis, dtype=np.float64
                    ),
                    "camera_depth": 0.5
                    * (
                        float(sensor.depth_near)
                        + float(sensor.depth_far)
                    ),
                }
                if os.environ.get("TACUMI_CAMERA_DEBUG_DIR"):
                    self.logger.warning(
                        "Tacumi camera mount namespace=%s side=%s model=%s "
                        "body=%s contact=%s local_pad=%s basis_lengths=%s",
                        self.camera_namespace,
                        side,
                        sensor.model_root,
                        body_prim.GetPath(),
                        collider_prim.GetPath(),
                        np.array2string(origin, precision=6),
                        np.array2string(np.asarray(lengths), precision=6),
                    )
                camera_view = getattr(sensor.camera, "_view", None)
                if camera_view is not None and hasattr(camera_view, "_use_fabric"):
                    camera_view._use_fabric = False

    @contextmanager
    def hide_sensor_geometry_for_depth(self, *, target_prim_paths: tuple[str, ...] = ()):
        """Hide sensor meshes for one depth render, then restore RGB appearance."""
        from pxr import UsdGeom

        visibility_states = []
        hidden_paths: list[str] = []
        try:
            for sensor in self.sensors:
                model_root = self.stage.GetPrimAtPath(sensor.model_root)
                if model_root is None or not model_root.IsValid():
                    raise RuntimeError(
                        f"Invalid tactile model root during depth render: "
                        f"{sensor.model_root}"
                    )
                cel_prim = sensor.layout["cel_prim"]
                occluder_paths = (
                    f"{cel_prim.GetPath()}/Mesh",
                    f"{cel_prim.GetParent().GetPath()}/foundation",
                )
                for occluder_path in occluder_paths:
                    occluder = self.stage.GetPrimAtPath(occluder_path)
                    if occluder is None or not occluder.IsValid():
                        raise RuntimeError(
                            "Tacumi tactile self-occluder is missing: "
                            f"{occluder_path}"
                        )
                    visibility = UsdGeom.Imageable(
                        occluder
                    ).GetVisibilityAttr()
                    previous = visibility.Get()
                    visibility_states.append((visibility, previous))
                    visibility.Set(UsdGeom.Tokens.invisible)
                    hidden_paths.append(str(occluder.GetPath()))
            if target_prim_paths:
                # Match depth contributors to the object-filtered PhysX contact
                # channel. Visibility affects rendering only, not collisions.
                from pxr import Usd

                for prim in Usd.PrimRange(self.stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
                    path = str(prim.GetPath())
                    if not prim.IsA(UsdGeom.Gprim) or any(
                        path == target or path.startswith(target.rstrip("/") + "/")
                        for target in target_prim_paths
                    ):
                        continue
                    visibility = UsdGeom.Imageable(prim).GetVisibilityAttr()
                    previous = visibility.Get()
                    if previous != UsdGeom.Tokens.invisible and not prim.IsInstanceProxy():
                        visibility_states.append((visibility, previous))
                        visibility.Set(UsdGeom.Tokens.invisible)
                        hidden_paths.append(path)
            if not self._hidden_geometry_logged:
                self.logger.warning(
                    "Tacumi tactile-only render hides %d self-occluders; "
                    "RGB cameras are refreshed after visibility is restored",
                    len(hidden_paths),
                )
                self._hidden_geometry_logged = True
            yield
        finally:
            for visibility, previous in reversed(visibility_states):
                visibility.Set(
                    UsdGeom.Tokens.inherited
                    if previous is None
                    else previous
                )

    def sync_camera_poses(self) -> None:
        """Move authored tactile cameras with their PhysX finger bodies."""
        if self.robot is None or not self._camera_mounts:
            return
        states: dict[str, dict[str, np.ndarray]] = {}
        for side, sensor in zip(
            self.sensor_sides, self.sensors, strict=True
        ):
            mount = self._camera_mounts[side]
            body_index = int(mount["body_index"])
            body_position = _to_numpy(
                self.robot.data.body_pos_w[0, body_index]
            ).astype(np.float64, copy=False)
            body_quaternion = _normalize_quaternion(
                _to_numpy(self.robot.data.body_quat_w[0, body_index])
            )
            states[side] = {
                "pad_position": body_position
                + _rotate_vector(
                    body_quaternion, mount["pad_position"]
                ),
                "pad_up_axis": _normalize_vector(
                    _rotate_vector(
                        body_quaternion, mount["pad_up_axis"]
                    )
                ),
                "pad_normal_axis": _normalize_vector(
                    _rotate_vector(
                        body_quaternion, mount["pad_normal_axis"]
                    )
                ),
            }

        left_up = states["left"]["pad_up_axis"]
        right_up = states["right"]["pad_up_axis"]
        if float(np.dot(left_up, right_up)) < 0.0:
            right_up = -right_up
        common_up = _normalize_vector(left_up + right_up)

        for side, sensor in zip(
            self.sensor_sides, self.sensors, strict=True
        ):
            other_side = "right" if side == "left" else "left"
            pad_position = states[side]["pad_position"]
            toward_other = (
                states[other_side]["pad_position"] - pad_position
            )
            toward_other_unit = _normalize_vector(toward_other)
            forward = states[side]["pad_normal_axis"]
            if float(np.dot(forward, toward_other)) < 0.0:
                forward = -forward
            up = common_up - float(np.dot(common_up, forward)) * forward
            up = _normalize_vector(up)
            camera_retreat = float(
                os.environ.get(
                    f"TACUMI_CAMERA_RETREAT_{side.upper()}_M",
                    os.environ.get(
                        "TACUMI_CAMERA_RETREAT_M",
                        "-0.0025" if side == "left" else "-0.0010",
                    ),
                )
            )
            camera_position = pad_position - forward * (
                float(self._camera_mounts[side]["camera_depth"])
                + camera_retreat
            )
            view_forward = (
                -forward
                if os.environ.get("TACUMI_CAMERA_FLIP_VIEW", "").strip().lower()
                in {"1", "true", "yes"}
                else forward
            )
            back = -view_forward
            right = _normalize_vector(np.cross(up, back))
            up = _normalize_vector(np.cross(back, right))
            camera_rotation = np.column_stack((right, up, back))
            camera_quaternion = _matrix_to_quaternion(camera_rotation)
            sensor.camera.set_world_pose(
                position=camera_position,
                orientation=camera_quaternion,
                camera_axes="usd",
            )
            debug_dir = os.environ.get("TACUMI_CAMERA_DEBUG_DIR")
            if debug_dir and self._camera_sync_count in {0, 55, 65, 70, 82, 98}:
                self.logger.warning(
                    "Tacumi camera geometry frame=%d side=%s pad=%s other=%s "
                    "toward_other=%s pad_normal=%s alignment=%.9f camera=%s "
                    "view_forward=%s",
                    self._camera_sync_count,
                    side,
                    np.array2string(pad_position, precision=6),
                    np.array2string(states[other_side]["pad_position"], precision=6),
                    np.array2string(toward_other_unit, precision=6),
                    np.array2string(states[side]["pad_normal_axis"], precision=6),
                    float(np.dot(forward, toward_other_unit)),
                    np.array2string(camera_position, precision=6),
                    np.array2string(view_forward, precision=6),
                )
            if self._camera_sync_count == 0:
                from pxr import Gf, UsdGeom

                actual_position, actual_quaternion = (
                    sensor.camera.get_world_pose(camera_axes="usd")
                )
                actual_position = _to_numpy(actual_position).astype(
                    np.float64, copy=False
                )
                actual_quaternion = _normalize_quaternion(
                    _to_numpy(actual_quaternion)
                )
                actual_forward = _normalize_vector(
                    _rotate_vector(
                        actual_quaternion,
                        np.asarray([0.0, 0.0, -1.0]),
                    )
                )
                camera_world = UsdGeom.XformCache().GetLocalToWorldTransform(
                    self.stage.GetPrimAtPath(sensor.camera_prim)
                )
                usd_origin = np.asarray(
                    camera_world.Transform(Gf.Vec3d(0.0, 0.0, 0.0)),
                    dtype=np.float64,
                )
                usd_forward = _normalize_vector(
                    np.asarray(
                        camera_world.Transform(Gf.Vec3d(0.0, 0.0, -1.0)),
                        dtype=np.float64,
                    )
                    - usd_origin
                )
                self.logger.warning(
                    "Tacumi camera pose side=%s position_error_mm=%.6f "
                    "forward_alignment=%.9f usd_forward_alignment=%.9f "
                    "target_forward=%s usd_forward=%s",
                    side,
                    1000.0
                    * float(np.linalg.norm(actual_position - camera_position)),
                    float(np.dot(actual_forward, view_forward)),
                    float(np.dot(usd_forward, view_forward)),
                    np.array2string(view_forward, precision=6),
                    np.array2string(usd_forward, precision=6),
                )
        self._camera_sync_count += 1

    def step(
        self,
        *,
        contact_by_side: dict[str, bool] | None = None,
        particle_points_world: Any | None = None,
    ) -> dict[str, dict[str, np.ndarray | dict[str, Any]]]:
        outputs: dict[str, dict[str, np.ndarray | dict[str, Any]]] = {}
        for side, sensor in zip(
            self.sensor_sides, self.sensors, strict=True
        ):
            contact_active = (
                None
                if contact_by_side is None
                else bool(contact_by_side.get(side, False))
            )
            particle_depth = None
            particle_projection: dict[str, Any] = {
                "ready": False,
                "reason": "not_requested",
            }
            if particle_points_world is not None and contact_active is True:
                particle_depth, particle_projection = _rasterize_particle_depth(
                    sensor.camera,
                    particle_points_world,
                    resolution=sensor.camera_resolution,
                    render_near_m=float(sensor.render_depth_near),
                    render_far_m=float(sensor.render_depth_far),
                    particle_radius_m=self.particle_surface_radius_m,
                )
                if particle_projection.get("active_pixels", 0) <= 0:
                    particle_depth = None
            depth_source = (
                "particle_projection"
                if particle_depth is not None
                else "rtx"
            )
            sensor.step(
                depth=particle_depth,
                contact_active=contact_active,
            )
            self.depth_source_counts[side][depth_source] += 1
            debug_dir = os.environ.get("TACUMI_CAMERA_DEBUG_DIR")
            debug_frame = self._camera_sync_count - 1
            if debug_dir and debug_frame in {0, 55, 65, 70, 82, 98}:
                output_dir = Path(debug_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                namespace = self.camera_namespace.rsplit("/", 1)[-1]
                np.save(
                    output_dir
                    / f"{namespace}_{side}_{debug_frame:04d}_rgb.npy",
                    np.asarray(sensor.camera.get_rgb()),
                )
            depth = _copy_or_empty(_sensor_last_depth(sensor), dtype=np.float32)
            depth_stats = _depth_stats(depth)
            depth_stats.update(_depth_window_stats(sensor))
            if depth.size and side not in self._depth_diagnostics_logged:
                self.logger.warning(
                    "Tacumi raw depth side=%s camera=%s valid=%.2f%% "
                    "min=%.9g p50=%.9g p99=%.9g max=%.9g "
                    "mapping=[%.9g, %.9g] render=[%.9g, %.9g]",
                    side,
                    getattr(sensor, "camera_prim", "unknown"),
                    100.0 * depth_stats["valid_ratio"],
                    depth_stats["min"],
                    depth_stats["p50"],
                    depth_stats["p99"],
                    depth_stats["max"],
                    float(getattr(sensor, "depth_near", float("nan"))),
                    float(getattr(sensor, "depth_far", float("nan"))),
                    float(
                        getattr(sensor, "render_depth_near", float("nan"))
                    ),
                    float(
                        getattr(sensor, "render_depth_far", float("nan"))
                    ),
                )
                self._depth_diagnostics_logged.add(side)
            stats = sensor.get_stats()
            stats["raw_depth"] = depth_stats
            stats["depth_source"] = depth_source
            stats["particle_projection"] = particle_projection
            stats.update(
                {
                    "indent_max_m": float(getattr(sensor, "indent_max_m", 0.0015)),
                    "deformation_stride": int(getattr(sensor, "deformation_stride", 16)),
                    "deformation_scale": float(getattr(sensor, "deformation_scale", 2500.0)),
                    "deformation_min_mag": float(
                        getattr(sensor, "deformation_min_mag", 5.0e-5)
                    ),
                    "deformation_mode": str(getattr(sensor, "deformation_mode", "screen")),
                    "deformation_hsv_max_mag": float(
                        getattr(sensor, "deformation_hsv_max_mag", 8.0)
                    ),
                }
            )
            deformation = _copy_or_empty(
                sensor.get_deformation(), dtype=np.float32, vector=True
            )
            shear = _copy_or_empty(
                _sensor_shear(sensor), dtype=np.float32, vector=True
            )
            indent = _copy_or_empty(
                sensor.get_indent(), dtype=np.float32
            )
            mask = _copy_or_empty(
                sensor.get_mask(), dtype=np.uint8
            )
            has_contact = bool(stats.get("has_contact", False))
            if not has_contact:
                # Raw depth is useful for diagnostics, but it is not a tactile
                # signal until both PhysX and the depth mapper agree on contact.
                # Never leak proximity, stale FEM state, or renderer background
                # into a no-contact observation.
                depth = np.zeros_like(depth, dtype=np.float32)
                indent = np.zeros_like(indent, dtype=np.float32)
                deformation = np.zeros_like(deformation, dtype=np.float32)
                shear = np.zeros_like(shear, dtype=np.float32)
                mask = np.zeros_like(mask, dtype=np.uint8)
            stats["zero_contact_enforced"] = not has_contact
            stats["shear_max_magnitude"] = float(
                np.max(np.linalg.norm(shear, axis=-1))
            ) if shear.size else 0.0
            outputs[side] = {
                "depth": depth,
                "indent": indent,
                "deformation": deformation,
                "shear": shear,
                "mask": mask,
                "stats": stats,
            }
        return outputs


def _target_side(model_root: Any, model_key: Any) -> str | None:
    # Arm prims also contain "Left_Robot" or "Right_Robot". Only the sensor
    # leaf/model key identifies the physical pad side.
    sensor_leaf = str(model_root).rstrip("/").rsplit("/", 1)[-1]
    text = f"{sensor_leaf} {model_key or ''}".lower()
    if "left" in text:
        return "left"
    if "right" in text:
        return "right"
    return None


def _sensor_last_depth(sensor: Any) -> Any:
    """Read the frame consumed by ``step`` across bundled TacSim versions."""
    getter = getattr(sensor, "get_last_depth", None)
    if callable(getter):
        return getter()
    return getattr(sensor, "_last_depth", None)


def _sensor_shear(sensor: Any) -> Any:
    getter = getattr(sensor, "get_shear", None)
    if not callable(getter):
        return None
    return getter()


def _depth_window_stats(sensor: Any) -> dict[str, float]:
    mapping_near = float(getattr(sensor, "depth_near", float("nan")))
    mapping_far = float(getattr(sensor, "depth_far", float("nan")))
    render_near = float(
        getattr(sensor, "render_depth_near", float("nan"))
    )
    render_far = float(
        getattr(sensor, "render_depth_far", float("nan"))
    )
    return {
        "clip_near_m": render_near,
        "clip_far_m": render_far,
        "mapping_near_m": mapping_near,
        "mapping_far_m": mapping_far,
        "render_near_m": render_near,
        "render_far_m": render_far,
    }


def _rasterize_particle_depth(
    camera: Any,
    points_world: Any,
    *,
    resolution: tuple[int, int],
    render_near_m: float,
    render_far_m: float,
    particle_radius_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Rasterize physical particle spheres into a tactile camera depth image."""
    width, height = (int(resolution[0]), int(resolution[1]))
    depth_image = np.zeros((height, width), dtype=np.float32)
    points = _to_numpy(points_world).astype(np.float64, copy=False).reshape(-1, 3)
    project = getattr(camera, "get_image_coords_from_world_points", None)
    if not callable(project) or not points.size:
        return depth_image, {
            "ready": False,
            "reason": "camera_projection_or_particles_unavailable",
            "particle_count": int(points.shape[0]),
            "active_pixels": 0,
        }
    try:
        projected = project(points)
    except (TypeError, AttributeError):
        import torch

        camera_device = getattr(camera, "device", None) or getattr(
            camera, "_device", "cpu"
        )
        projected = project(
            torch.as_tensor(
                points,
                dtype=torch.float32,
                device=camera_device,
            )
        )
    uv = _to_numpy(projected).astype(np.float64, copy=False)
    if uv.ndim != 2 or uv.shape[0] != points.shape[0] or uv.shape[1] < 2:
        return depth_image, {
            "ready": False,
            "reason": "invalid_camera_projection_shape",
            "particle_count": int(points.shape[0]),
            "projection_shape": list(uv.shape),
            "active_pixels": 0,
        }
    camera_position, camera_orientation = camera.get_world_pose(camera_axes="usd")
    camera_position = _to_numpy(camera_position).astype(np.float64, copy=False).reshape(3)
    camera_orientation = _normalize_quaternion(_to_numpy(camera_orientation))
    camera_forward = _normalize_vector(
        _rotate_vector(camera_orientation, np.asarray([0.0, 0.0, -1.0]))
    )
    center_depth = (points - camera_position.reshape(1, 3)) @ camera_forward
    surface_depth = center_depth - float(particle_radius_m)
    valid = (
        np.all(np.isfinite(uv[:, :2]), axis=1)
        & np.isfinite(center_depth)
        & (center_depth > 0.0)
        & (surface_depth <= float(render_far_m))
        & (uv[:, 0] >= 0.0)
        & (uv[:, 0] <= float(width - 1))
        & (uv[:, 1] >= 0.0)
        & (uv[:, 1] <= float(height - 1))
    )
    valid_indices = np.flatnonzero(valid)
    if not valid_indices.size:
        return depth_image, {
            "ready": True,
            "reason": "no_particle_surface_in_tactile_frustum",
            "particle_count": int(points.shape[0]),
            "projected_particle_count": 0,
            "active_pixels": 0,
        }
    get_intrinsics = getattr(camera, "get_intrinsics_matrix", None)
    focal_pixels = 1.0
    if callable(get_intrinsics):
        intrinsics = _to_numpy(get_intrinsics()).astype(np.float64, copy=False)
        if intrinsics.shape == (3, 3):
            focal_pixels = max(float(abs(intrinsics[0, 0])), float(abs(intrinsics[1, 1])))
    for index in valid_indices:
        u, v = uv[index, :2]
        sphere_depth = float(
            np.clip(surface_depth[index], render_near_m, render_far_m)
        )
        radius_pixels = int(
            np.clip(
                np.ceil(
                    focal_pixels
                    * float(particle_radius_m)
                    / max(float(center_depth[index]), float(render_near_m))
                ),
                1.0,
                64.0,
            )
        )
        center_x = int(round(float(u)))
        center_y = int(round(float(v)))
        x0 = max(center_x - radius_pixels, 0)
        x1 = min(center_x + radius_pixels, width - 1)
        y0 = max(center_y - radius_pixels, 0)
        y1 = min(center_y + radius_pixels, height - 1)
        yy, xx = np.ogrid[y0 : y1 + 1, x0 : x1 + 1]
        disk = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius_pixels**2
        patch = depth_image[y0 : y1 + 1, x0 : x1 + 1]
        patch[disk] = np.where(
            (patch[disk] <= 0.0) | (sphere_depth < patch[disk]),
            sphere_depth,
            patch[disk],
        )
    active = depth_image > 0.0
    return depth_image, {
        "ready": True,
        "reason": "physx_particle_surface_projection",
        "particle_count": int(points.shape[0]),
        "projected_particle_count": int(valid_indices.size),
        "active_pixels": int(np.count_nonzero(active)),
        "active_ratio": float(np.mean(active)),
        "minimum_surface_depth_m": float(np.min(depth_image[active])),
        "maximum_surface_depth_m": float(np.max(depth_image[active])),
        "particle_radius_m": float(particle_radius_m),
    }


def _to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _normalize_quaternion(value: Any) -> np.ndarray:
    quaternion = np.asarray(value, dtype=np.float64).reshape(4)
    norm = float(np.linalg.norm(quaternion))
    if norm <= 1.0e-12:
        raise RuntimeError("Tacumi camera pose has a zero quaternion")
    return quaternion / norm


def _normalize_vector(value: Any) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-12:
        raise RuntimeError("Tacumi camera pose has a zero direction vector")
    return vector / norm


def _matrix_to_quaternion(value: Any) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = 2.0 * np.sqrt(trace + 1.0)
        quaternion = np.asarray(
            [
                0.25 * scale,
                (matrix[2, 1] - matrix[1, 2]) / scale,
                (matrix[0, 2] - matrix[2, 0]) / scale,
                (matrix[1, 0] - matrix[0, 1]) / scale,
            ]
        )
    else:
        index = int(np.argmax(np.diag(matrix)))
        next_index = (index + 1) % 3
        last_index = (index + 2) % 3
        scale = 2.0 * np.sqrt(
            max(
                1.0
                + matrix[index, index]
                - matrix[next_index, next_index]
                - matrix[last_index, last_index],
                0.0,
            )
        )
        xyz = np.zeros(3, dtype=np.float64)
        xyz[index] = 0.25 * scale
        xyz[next_index] = (
            matrix[next_index, index] + matrix[index, next_index]
        ) / scale
        xyz[last_index] = (
            matrix[last_index, index] + matrix[index, last_index]
        ) / scale
        quaternion = np.asarray(
            [
                (
                    matrix[last_index, next_index]
                    - matrix[next_index, last_index]
                )
                / scale,
                xyz[0],
                xyz[1],
                xyz[2],
            ]
        )
    return _normalize_quaternion(quaternion)


def _rotate_vector(quaternion: Any, vector: Any) -> np.ndarray:
    quaternion = _normalize_quaternion(quaternion)
    vector = np.asarray(vector, dtype=np.float64).reshape(3)
    imaginary = quaternion[1:]
    return vector + 2.0 * np.cross(
        imaginary,
        np.cross(imaginary, vector) + quaternion[0] * vector,
    )


def _copy_or_empty(value: Any, *, dtype: Any, vector: bool = False) -> np.ndarray:
    if value is None:
        shape = (0, 0, 2) if vector else (0, 0)
        return np.empty(shape, dtype=dtype)
    return np.ascontiguousarray(np.asarray(value, dtype=dtype))


def _depth_stats(depth: Any) -> dict[str, float]:
    array = np.asarray(depth, dtype=np.float32)
    valid = np.isfinite(array) & (array > 0.0)
    values = array[valid]
    if not values.size:
        return {
            "valid_ratio": 0.0,
            "min": float("nan"),
            "p50": float("nan"),
            "p99": float("nan"),
            "max": float("nan"),
        }
    return {
        "valid_ratio": float(np.mean(valid)),
        "min": float(np.min(values)),
        "p50": float(np.percentile(values, 50.0)),
        "p99": float(np.percentile(values, 99.0)),
        "max": float(np.max(values)),
    }
