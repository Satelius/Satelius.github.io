"""Nine-token control for one Arena Franka relative-pose IK environment.

This is an uncalibrated interpreter, not a teacher. It reads only the control
TCP and its observation counterpart; no object state determines the target.
The caller executes and records the returned actions with ``env.step``.
"""
from __future__ import annotations

import hashlib
import json
import math
from numbers import Integral
from typing import Any, Callable

import torch


TOKEN_DIRECTIONS_BASE = {
    "MV_FWD": (1.0, 0.0, 0.0),
    "MV_BACK": (-1.0, 0.0, 0.0),
    "MV_LEFT": (0.0, 1.0, 0.0),
    "MV_RIGHT": (0.0, -1.0, 0.0),
    "MV_UP": (0.0, 0.0, 1.0),
    "MV_DOWN": (0.0, 0.0, -1.0),
}
TOKENS = (*TOKEN_DIRECTIONS_BASE, "GRASP", "RELEASE", "DONE")
DOWN_QUATERNION_XYZW = (1.0, 0.0, 0.0, 0.0)
PoseError = Callable[
    [torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
    tuple[torch.Tensor, torch.Tensor],
]


class ArenaMetaActionInterpreter:
    """Freeze one token target, then emit bounded relative-IK servo actions.

    ``begin`` returns JSON-compatible decision metadata. ``action`` emits at
    most ``hold_frames`` actions for that decision, or ``None`` for DONE.
    Emitting an action does not certify physical execution: the caller must
    retain the actual executed frame interval separately.
    """

    def __init__(
        self,
        env: Any,
        *,
        translation_step: float = 0.025,
        hold_frames: int = 5,
        translation_clamp: float = 0.025,
        rotation_clamp: float = 0.08,
        version: str = "arena-meta-actions-v1",
        pose_error_fn: PoseError | None = None,
    ) -> None:
        self.env = env.unwrapped
        if self.env.num_envs != 1:
            raise ValueError("Arena meta actions require exactly one environment")
        self.translation_step = self._positive(translation_step, "translation_step")
        self.translation_clamp = self._positive(translation_clamp, "translation_clamp")
        self.rotation_clamp = self._positive(rotation_clamp, "rotation_clamp")
        if isinstance(hold_frames, bool) or not isinstance(hold_frames, Integral) or hold_frames < 1:
            raise ValueError("hold_frames must be a positive integer")
        self.hold_frames = int(hold_frames)
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version must be a nonempty string")
        self.version = version
        self.device = torch.device(self.env.device)
        manager = self.env.action_manager
        if (
            manager.total_action_dim != 7
            or list(manager.active_terms) != ["arm_action", "gripper_action"]
            or list(manager.action_term_dim) != [6, 1]
        ):
            raise ValueError("Expected ordered 7D arm_action(6), gripper_action(1)")
        self.arm = manager.get_term("arm_action")
        for controller in (self.arm.cfg.controller, self.arm._ik_controller.cfg):
            if controller.command_type != "pose" or controller.use_relative_mode is not True:
                raise ValueError("Arm controller must use relative pose IK")
        if self.arm.action_dim != 6 or not callable(getattr(self.arm, "_compute_frame_pose", None)):
            raise ValueError("Arm must expose the six-dimensional control TCP")
        config_scale = self._tensor(self.arm.cfg.scale)
        self._scale = self._tensor(self.arm._scale).clone()
        if (
            config_scale.numel() not in (1, 6)
            or self._scale.shape != (1, 6)
            or not torch.allclose(config_scale, torch.full_like(config_scale, 0.5), atol=1e-7, rtol=0)
            or not torch.allclose(self._scale, torch.full_like(self._scale, 0.5), atol=1e-7, rtol=0)
        ):
            raise ValueError("Actual Arena relative-pose IK scale must be 0.5 in all six axes")
        if pose_error_fn is None:
            from isaaclab.utils.math import compute_pose_error

            pose_error_fn = compute_pose_error
        self._pose_error = pose_error_fn
        self._assert_xyzw_math()
        self._read_tcp()
        self._gripper = 1.0
        self._token: str | None = None
        self._done = False
        self._actions_emitted = 0
        self._decision_index = -1
        self._target_position: torch.Tensor | None = None
        self._down = self._tensor([DOWN_QUATERNION_XYZW])
        self._config = {
            "version": self.version,
            "calibration_status": "uncalibrated",
            "coordinate_frame": "robot_base",
            "quaternion_order": "xyzw",
            "down_quaternion_xyzw": list(DOWN_QUATERNION_XYZW),
            "token_directions_base": {key: list(value) for key, value in TOKEN_DIRECTIONS_BASE.items()},
            "translation_step_m": self.translation_step,
            "hold_frames": self.hold_frames,
            "translation_clamp_m": self.translation_clamp,
            "rotation_clamp_rad": self.rotation_clamp,
            "arm_scale": self._scale[0].cpu().tolist(),
            "initial_gripper_target": 1.0,
            "tcp_position_tolerance_m": 1e-5,
            "tcp_quaternion_tolerance": 1e-4,
        }
        self.config_sha256 = hashlib.sha256(
            json.dumps(self._config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

    @staticmethod
    def _positive(value: float, name: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be finite and positive")
        result = float(value)
        if not math.isfinite(result) or result <= 0:
            raise ValueError(f"{name} must be finite and positive")
        return result

    def _tensor(self, value: Any) -> torch.Tensor:
        if hasattr(value, "torch"):
            value = value.torch
        return torch.as_tensor(value, dtype=torch.float32, device=self.device).detach()

    def _assert_xyzw_math(self) -> None:
        zero = torch.zeros((1, 3), device=self.device)
        identity = self._tensor([[0.0, 0.0, 0.0, 1.0]])
        quarter_x = self._tensor([[math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)]])
        position_error, rotation_error = self._pose_error(zero, identity, zero, quarter_x)
        if (
            position_error.shape != (1, 3)
            or rotation_error.shape != (1, 3)
            or not torch.allclose(position_error, zero, atol=1e-5, rtol=0)
            or not torch.allclose(rotation_error, self._tensor([[math.pi / 2, 0.0, 0.0]]), atol=1e-5, rtol=0)
        ):
            raise ValueError("Pose-error mathematics must use XYZW quaternion order")

    def _read_tcp(self) -> tuple[torch.Tensor, torch.Tensor]:
        position, quaternion = (self._tensor(value) for value in self.arm._compute_frame_pose())
        if position.shape != (1, 3) or quaternion.shape != (1, 4):
            raise ValueError("Expected one control TCP position(3) and XYZW quaternion(4)")
        if not torch.isfinite(position).all() or not torch.isfinite(quaternion).all():
            raise ValueError("Control TCP must be finite")
        if not torch.allclose(quaternion.norm(dim=-1), torch.ones(1, device=self.device), atol=1e-4, rtol=0):
            raise ValueError("Control TCP quaternion must have unit norm")
        frames = self.env.scene["ee_frame"].data
        if list(frames.target_frame_names) != ["end_effector"]:
            raise ValueError("TCP observation must identify only end_effector")
        observed_position = self._tensor(frames.target_pos_source)[:, 0]
        observed_quaternion = self._tensor(frames.target_quat_source)[:, 0]
        if observed_position.shape != position.shape or observed_quaternion.shape != quaternion.shape:
            raise ValueError("TCP observation shape differs from controller")
        quaternion_delta = torch.minimum(
            (observed_quaternion - quaternion).norm(dim=-1),
            (observed_quaternion + quaternion).norm(dim=-1),
        )
        if (
            not torch.allclose(observed_position, position, atol=1e-5, rtol=0)
            or not torch.isfinite(quaternion_delta).all()
            or bool(torch.any(quaternion_delta > 1e-4))
        ):
            raise ValueError("Controller TCP and end_effector observation disagree")
        return position, quaternion

    @property
    def done(self) -> bool:
        return self._done

    @property
    def remaining_frames(self) -> int:
        if self._token is None or self._done:
            return 0
        return self.hold_frames - self._actions_emitted

    def configuration(self) -> dict[str, Any]:
        """Return a detached JSON-compatible configuration receipt."""
        return json.loads(json.dumps(self._config))

    def begin(self, token: str) -> dict[str, Any]:
        if not isinstance(token, str) or token not in TOKENS:
            raise ValueError("Expected exactly one legal meta-action token")
        if self._done:
            raise RuntimeError("DONE ended this interpreter; create one for the next attempt")
        if self.remaining_frames:
            raise RuntimeError("The current token still has unissued control frames")
        position, _ = self._read_tcp()
        target = position.clone()
        if token in TOKEN_DIRECTIONS_BASE:
            target += self._tensor([TOKEN_DIRECTIONS_BASE[token]]) * self.translation_step
        gripper = -1.0 if token == "GRASP" else 1.0 if token == "RELEASE" else self._gripper
        self._token = token
        self._done = token == "DONE"
        self._actions_emitted = 0
        self._decision_index += 1
        self._target_position = target
        self._gripper = gripper
        return {
            "decision_index": self._decision_index,
            "token": token,
            "execute": not self._done,
            "done": self._done,
            "hold_frames": 0 if self._done else self.hold_frames,
            "initial_tcp_position_base_m": position[0].cpu().tolist(),
            "target_position_base_m": None if self._done else target[0].cpu().tolist(),
            "target_quaternion_xyzw": None if self._done else self._down[0].cpu().tolist(),
            "gripper_target": self._gripper,
            "interpreter_version": self.version,
            "interpreter_config_sha256": self.config_sha256,
            "calibration_status": "uncalibrated",
        }

    def action(self) -> torch.Tensor | None:
        if self._token is None:
            raise RuntimeError("Call begin(token) before requesting an action")
        if self._done:
            return None
        if self.remaining_frames == 0:
            raise RuntimeError("All control frames for this token have been issued")
        position, quaternion = self._read_tcp()
        position_error, rotation_error = self._pose_error(position, quaternion, self._target_position, self._down)
        if (
            position_error.shape != (1, 3)
            or rotation_error.shape != (1, 3)
            or not torch.isfinite(position_error).all()
            or not torch.isfinite(rotation_error).all()
        ):
            raise ValueError("Pose-error mathematics returned invalid servo errors")
        servo = torch.cat(
            (
                position_error.clamp(-self.translation_clamp, self.translation_clamp),
                rotation_error.clamp(-self.rotation_clamp, self.rotation_clamp),
            ),
            dim=1,
        ) / self._scale
        action = torch.cat((servo, self._tensor([[self._gripper]])), dim=1)
        self._actions_emitted += 1
        return action
