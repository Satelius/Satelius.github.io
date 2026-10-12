"""Isaac Lab 3 Arena state receipts without advancing physics or commands.

These checks cover physical/task state, not RNG restoration or image visibility.
The module has no Isaac imports, so its invariants can be tested on the CPU.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np


_REQUIRED = (
    "env.episode_length_buf", "env.common_step_counter", "env._sim_step_counter",
    "sim.physics_step_count", "sim.physics_time_s",
    "object_pose.command", "object_pose.pose_command_b", "object_pose.pose_command_w",
    "object_pose.time_left", "object_pose.command_counter",
)
_PHYSICAL_FIELDS = {
    "articulation": ("root_pose", "root_velocity", "joint_position", "joint_velocity"),
    "rigid_object": ("root_pose", "root_velocity"),
    "deformable_object": ("nodal_position", "nodal_velocity"),
}


class ArenaStateError(RuntimeError):
    """Required state was unavailable; a freeze claim cannot be made."""


class ArenaStateChangedError(ArenaStateError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__("Arena state changed: " + ", ".join(report["changed_fields"]))


def _array(value: Any, field: str) -> np.ndarray:
    if hasattr(value, "torch"):
        value = value.torch
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    try:
        result = np.array(value, copy=True)
    except (TypeError, ValueError) as exc:
        raise ArenaStateError(f"Cannot read Arena state field: {field}") from exc
    if result.dtype.kind not in "biuf" or result.size == 0 or not np.isfinite(result).all():
        raise ArenaStateError(f"Invalid Arena state field: {field}")
    return result


def _required_attr(obj: Any, name: str, field: str) -> Any:
    try:
        value = getattr(obj, name)
    except AttributeError as exc:
        raise ArenaStateError(f"Missing Arena state field: {field}") from exc
    if value is None:
        raise ArenaStateError(f"Missing Arena state field: {field}")
    return value


def _goal_term(env: Any) -> Any:
    manager = _required_attr(env, "command_manager", "command_manager")
    try:
        return manager.get_term("object_pose")
    except (AttributeError, KeyError, ValueError) as exc:
        raise ArenaStateError("Missing Arena object_pose command term") from exc


def snapshot_arena_state(env: Any) -> dict[str, np.ndarray]:
    """Copy all registered scene bodies and the native goal, clocks and counters.

    Isaac Lab 3's physics-manager clock is sampled independently of env counters.
    Missing bodies, velocities or clock/command fields fail closed.
    """
    env = getattr(env, "unwrapped", env)
    scene = _required_attr(env, "scene", "scene")
    try:
        physical = scene.get_state(is_relative=False)
    except AttributeError as exc:
        raise ArenaStateError("Missing Arena scene.get_state") from exc
    if not isinstance(physical, Mapping):
        raise ArenaStateError("Invalid Arena scene state")
    result: dict[str, np.ndarray] = {}
    for kind, fields in _PHYSICAL_FIELDS.items():
        entities = physical.get(kind)
        if not isinstance(entities, Mapping):
            raise ArenaStateError(f"Missing Arena scene group: {kind}")
        # Verify get_state did not omit a registered body.
        registry_name = {"articulation": "articulations", "rigid_object": "rigid_objects",
                         "deformable_object": "deformable_objects"}[kind]
        registry = _required_attr(scene, registry_name, f"scene.{registry_name}")
        if set(entities) != set(registry):
            raise ArenaStateError(f"Incomplete Arena scene group: {kind}")
        for name, values in entities.items():
            if not isinstance(values, Mapping):
                raise ArenaStateError(f"Invalid Arena scene entity: {kind}.{name}")
            for field in fields:
                key = f"scene.{kind}.{name}.{field}"
                if field not in values:
                    raise ArenaStateError(f"Missing Arena state field: {key}")
                result[key] = _array(values[field], key)
    if "robot" not in physical["articulation"] or not physical["rigid_object"]:
        raise ArenaStateError("Arena collection requires robot and rigid-object state")
    # InteractiveScene.get_state currently omits rigid-object collections.
    if getattr(scene, "rigid_object_collections", {}):
        raise ArenaStateError("Arena rigid-object collections are not covered by scene.get_state")
    for name, value in physical.get("gripper", {}).items():
        key = f"scene.gripper.{name}"
        result[key] = _array(value, key)
    for field in ("episode_length_buf", "common_step_counter", "_sim_step_counter"):
        key = f"env.{field}"
        result[key] = _array(_required_attr(env, field, key), key)
    sim = _required_attr(env, "sim", "sim")
    count_fn = _required_attr(sim, "get_physics_step_count", "sim.get_physics_step_count")
    manager = _required_attr(sim, "physics_manager", "sim.physics_manager")
    time_fn = _required_attr(manager, "get_simulation_time", "sim.physics_manager.get_simulation_time")
    result["sim.physics_step_count"] = _array(count_fn(), "sim.physics_step_count")
    result["sim.physics_time_s"] = _array(time_fn(), "sim.physics_time_s")
    term = _goal_term(env)
    for field in ("command", "pose_command_b", "pose_command_w", "time_left", "command_counter"):
        key = f"object_pose.{field}"
        result[key] = _array(_required_attr(term, field, key), key)
    if hasattr(term, "_succeeded"):
        result["object_pose._succeeded"] = _array(term._succeeded, "object_pose._succeeded")
    return result


def assert_arena_state_unchanged(
    before: Mapping[str, np.ndarray], after: Mapping[str, np.ndarray], tolerance: float = 1e-7,
) -> dict[str, Any]:
    """Return a JSON receipt or raise with a receipt when any field changes.

    Integers/booleans (especially counters) must be identical. Floating-point
    comparison uses absolute tolerance only; non-finite values never pass.
    """
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Arena state tolerance must be finite and nonnegative")
    for state in (before, after):
        missing = set(_REQUIRED) - set(state)
        if missing:
            raise ArenaStateError("Incomplete Arena snapshot: " + ", ".join(sorted(missing)))
        if not any(key.startswith("scene.articulation.robot.") for key in state):
            raise ArenaStateError("Incomplete Arena snapshot: robot")
        if not any(key.startswith("scene.rigid_object.") for key in state):
            raise ArenaStateError("Incomplete Arena snapshot: rigid objects")
        for kind, fields in _PHYSICAL_FIELDS.items():
            prefix = f"scene.{kind}."
            entities = {key[len(prefix):].rsplit(".", 1)[0] for key in state if key.startswith(prefix)}
            for entity in entities:
                missing_fields = {f"{prefix}{entity}.{field}" for field in fields} - set(state)
                if missing_fields:
                    raise ArenaStateError("Incomplete Arena snapshot: " + ", ".join(sorted(missing_fields)))
    changed = sorted(set(before) ^ set(after))
    deltas: dict[str, float | None] = {key: None for key in changed}
    for key in sorted(set(before) & set(after)):
        left, right = _array(before[key], key), _array(after[key], key)
        if left.shape != right.shape or left.dtype != right.dtype:
            changed.append(key)
            deltas[key] = None
            continue
        delta = float(np.max(np.abs(left.astype(np.float64) - right.astype(np.float64))))
        deltas[key] = delta
        equal = np.array_equal(left, right) if left.dtype.kind in "biu" else delta <= tolerance
        if not equal:
            changed.append(key)
    report = {"schema": "tacharness.arena_state_freeze.v1", "unchanged": not changed,
              "checked_fields": len(set(before) | set(after)), "tolerance": float(tolerance),
              "max_abs_delta": max((value for value in deltas.values() if value is not None), default=0.0),
              "changed_fields": sorted(changed), "field_max_abs_delta": deltas}
    if changed:
        raise ArenaStateChangedError(report)
    return report


def _world_pose_xyzw(root_position: np.ndarray, root_quaternion: np.ndarray, command: np.ndarray) -> np.ndarray:
    """Same XYZW composition as Isaac Lab 3 combine_frame_transforms."""
    if root_position.shape != command[:, :3].shape or root_quaternion.shape != command[:, 3:].shape:
        raise ArenaStateError("Arena goal/root pose shape mismatch")
    for quaternion in (root_quaternion, command[:, 3:]):
        if not np.allclose(np.linalg.norm(quaternion, axis=-1), 1, atol=1e-5, rtol=0):
            raise ArenaStateError("Arena goal requires unit XYZW quaternions")
    xyz, scalar = root_quaternion[:, :3], root_quaternion[:, 3:4]
    target_xyz, target_scalar = command[:, 3:6], command[:, 6:7]
    cross = 2 * np.cross(xyz, command[:, :3])
    position = root_position + command[:, :3] + scalar * cross + np.cross(xyz, cross)
    quaternion = np.concatenate((scalar * target_xyz + target_scalar * xyz + np.cross(xyz, target_xyz),
                                 scalar * target_scalar - np.sum(xyz * target_xyz, axis=-1, keepdims=True)), axis=-1)
    return np.concatenate((position, quaternion), axis=-1)


def _write_pose(target: Any, value: np.ndarray) -> Any:
    if hasattr(target, "torch"):
        target = target.torch
    if isinstance(target, np.ndarray):
        target[...] = value
    elif hasattr(target, "copy_"):
        import torch
        target.copy_(torch.as_tensor(value, dtype=target.dtype, device=target.device))
    else:
        raise ArenaStateError("Unsupported Arena pose_command_w buffer")
    return target


def refresh_object_goal(env: Any) -> dict[str, Any]:
    """Refresh the sampled native goal cache and existing marker without compute.

    Reset samples pose_command_b before updating pose_command_w. Calling compute
    to fix that cache would decrement the timer and could resample the goal.
    This function changes only the cached world pose and marker presentation.
    A successful receipt proves marker submission, not RGB visibility.
    """
    env = getattr(env, "unwrapped", env)
    before = snapshot_arena_state(env)
    term = _goal_term(env)
    robot = _required_attr(term, "robot", "object_pose.robot")
    data = _required_attr(robot, "data", "object_pose.robot.data")
    root_position = _array(_required_attr(data, "root_pos_w", "robot.root_pos_w"), "robot.root_pos_w")
    root_quaternion = _array(_required_attr(data, "root_quat_w", "robot.root_quat_w"), "robot.root_quat_w")
    command = before["object_pose.command"]
    if command.ndim != 2 or command.shape[1] != 7:
        raise ArenaStateError("Arena object_pose command must have shape (num_envs, 7)")
    if not np.array_equal(command, before["object_pose.pose_command_b"]):
        raise ArenaStateError("Arena object_pose command differs from pose_command_b")
    if before["object_pose.pose_command_w"].shape != command.shape:
        raise ArenaStateError("Arena object_pose world cache shape mismatch")
    marker = _required_attr(term, "goal_pose_visualizer", "object_pose.goal_pose_visualizer")
    visualize = _required_attr(marker, "visualize", "object_pose.goal_pose_visualizer.visualize")
    world_pose = _world_pose_xyzw(root_position, root_quaternion, command)
    world_buffer = _write_pose(term.pose_command_w, world_pose)
    expected = dict(before)
    expected["object_pose.pose_command_w"] = _array(world_buffer, "object_pose.pose_command_w")
    visualize(world_buffer[:, :3], world_buffer[:, 3:])
    after = snapshot_arena_state(env)
    guard = assert_arena_state_unchanged(expected, after)
    return {"schema": "tacharness.arena_object_goal.v1", "quaternion_order": "xyzw",
            "command_frame": "robot_root", "command_pose_b": command.tolist(),
            "robot_root_position_w": root_position.tolist(), "robot_root_quaternion_w_xyzw": root_quaternion.tolist(),
            "goal_pose_w_xyzw": after["object_pose.pose_command_w"].tolist(),
            "previous_goal_pose_w_xyzw": before["object_pose.pose_command_w"].tolist(),
            "time_left_s": after["object_pose.time_left"].tolist(),
            "command_counter": after["object_pose.command_counter"].tolist(),
            "physics_time_s": after["sim.physics_time_s"].tolist(),
            "physics_step_count": after["sim.physics_step_count"].tolist(),
            "marker_updated": True, "marker_rgb_visibility": "not_verified", "state_guard": guard}
