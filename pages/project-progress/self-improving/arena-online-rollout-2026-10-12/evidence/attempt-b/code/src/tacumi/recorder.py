from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .embodiment import (
    TACUMI_EMBODIMENT_ID,
    TACUMI_END_EFFECTOR_PROFILE_SCHEMA,
    TACUMI_ROBOT_TYPE,
    TACUMI_WRIST_CAMERA_CONTRACT,
    tacumi_end_effector_profile,
)
from .visualization import render_tactile_composite


TACTILE_SCALE = 1_000_000.0
TACTILE_OFFSET = 30000.0
DEPTH_SCALE = 1_000_000.0
DEPTH_INVALID = 0
TACTILE_ZERO_CONTACT_CONTRACT = "zero-all-fields-on-no-contact-v2"
TACTILE_COORDINATE_CONTRACT = "depth-camera-aligned-v4"
TACUMI_EPISODE_SCHEMA = "tacharness.tacumi.episode.v1"
# Retained for RoboLab replay compatibility.  This names the serialized v4
# dataset contract, not the current Python package or repository layout.
LEGACY_CODEBASE_VERSION = "tacumi_unified_v4"


def encode_tactile_float(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32)
    return np.clip(np.rint(array * TACTILE_SCALE + TACTILE_OFFSET), 0, 65535).astype(np.uint16)


def encode_tactile_depth(value: Any) -> np.ndarray:
    """Encode positive metric depth at micrometer resolution; zero means no return."""
    array = np.asarray(value, dtype=np.float32)
    valid = np.isfinite(array) & (array > 0.0)
    encoded = np.zeros(array.shape, dtype=np.uint16)
    encoded[valid] = np.clip(
        np.rint(array[valid] * DEPTH_SCALE), 1, 65535
    ).astype(np.uint16)
    return encoded


def canonicalize_tactile_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Return finite, masked fields with an exact all-zero no-contact state."""
    depth = np.asarray(sample["depth"], dtype=np.float32)
    indent = np.asarray(sample["indent"], dtype=np.float32)
    deformation = np.asarray(sample["deformation"], dtype=np.float32)
    mask = np.asarray(sample["mask"], dtype=bool)
    if depth.shape != indent.shape or mask.shape != indent.shape:
        raise ValueError(
            "Tactile depth, indent, and mask shapes must match: "
            f"depth={depth.shape}, indent={indent.shape}, mask={mask.shape}"
        )
    if deformation.shape != (*indent.shape, 2):
        raise ValueError(
            f"Tactile deformation must have shape {(*indent.shape, 2)}, "
            f"got {deformation.shape}"
        )
    shear = np.asarray(sample.get("shear", ()), dtype=np.float32)
    if shear.shape != deformation.shape:
        shear = np.zeros_like(deformation)

    stats_value = sample.get("stats", {})
    stats = dict(stats_value) if isinstance(stats_value, dict) else {}
    declared_contact = stats.get("has_contact")
    if isinstance(declared_contact, (bool, np.bool_)):
        has_contact = bool(declared_contact)
    else:
        has_contact = bool(
            np.any(mask)
            and np.any(
                mask
                & np.isfinite(indent)
                & (indent > 0.0)
            )
        )

    if has_contact:
        depth = np.where(
            np.isfinite(depth) & (depth > 0.0),
            depth,
            0.0,
        )
        scalar_valid = mask & np.isfinite(indent)
        indent = np.where(
            scalar_valid,
            np.maximum(indent, 0.0),
            0.0,
        )
        vector_valid = mask & np.all(np.isfinite(deformation), axis=-1)
        deformation = np.where(
            vector_valid[..., None],
            deformation,
            0.0,
        )
        shear_valid = mask & np.all(np.isfinite(shear), axis=-1)
        shear = np.where(
            shear_valid[..., None],
            shear,
            0.0,
        )
    else:
        depth = np.zeros_like(depth)
        indent = np.zeros_like(indent)
        deformation = np.zeros_like(deformation)
        shear = np.zeros_like(shear)
        mask = np.zeros_like(mask)

    stats["has_contact"] = has_contact
    stats["zero_contact_enforced"] = not has_contact
    normalized = dict(sample)
    normalized.update(
        {
            "depth": np.ascontiguousarray(depth, dtype=np.float32),
            "indent": np.ascontiguousarray(indent, dtype=np.float32),
            "deformation": np.ascontiguousarray(
                deformation, dtype=np.float32
            ),
            "shear": np.ascontiguousarray(shear, dtype=np.float32),
            "mask": np.ascontiguousarray(mask, dtype=np.uint8),
            "stats": stats,
        }
    )
    return normalized


class UnifiedEpisodeRecorder:
    """Write source-policy rollouts into the shared Tacumi viewer format."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        source: str,
        task_id: str,
        instruction: str,
        policy_contract: str,
        state_layout: list[str],
        action_layout: list[str],
        fps: float,
        record_scene_rgb: bool = False,
        record_rgb_dual_view: bool = False,
        tactile_arms: tuple[str, ...] = ("left",),
        rgb_dual_view_wrist_arm: str = "left",
        robot_type: str = TACUMI_ROBOT_TYPE,
        end_effector_profile: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.frames_dir = self.output_dir / "frames"
        if self.frames_dir.is_dir() and any(self.frames_dir.glob("frame_*.npz")) and not overwrite:
            raise FileExistsError(f"Episode already contains frames: {self.frames_dir}")
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        if overwrite:
            for path in self.frames_dir.glob("frame_*.npz"):
                path.unlink()
            for name in ("summary.json", "summary.npz"):
                (self.output_dir / name).unlink(missing_ok=True)
        self.meta_dir = self.output_dir / "meta"
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.source = source
        self.task_id = task_id
        self.instruction = instruction
        self.policy_contract = policy_contract
        self.state_layout = list(state_layout)
        self.action_layout = list(action_layout)
        self.fps = float(fps)
        self.record_scene_rgb = bool(record_scene_rgb)
        self.record_rgb_dual_view = bool(record_rgb_dual_view)
        self.tactile_arms = tuple(str(value) for value in tactile_arms)
        if self.tactile_arms not in {("left",), ("left", "right")}:
            raise ValueError(
                "tactile_arms must be ('left',) or ('left', 'right'), got "
                f"{self.tactile_arms}"
            )
        self.robot_type = str(robot_type)
        self.end_effector_profile = copy.deepcopy(
            end_effector_profile
            if end_effector_profile is not None
            else tacumi_end_effector_profile(robot_type=self.robot_type)
        )
        if (
            self.end_effector_profile.get("schema")
            != TACUMI_END_EFFECTOR_PROFILE_SCHEMA
            or self.end_effector_profile.get("robot_type")
            != self.robot_type
        ):
            raise ValueError(
                "end_effector_profile must be a TacUMI profile matching "
                f"robot_type {self.robot_type!r}"
            )
        self.rgb_dual_view_wrist_arm = str(rgb_dual_view_wrist_arm)
        if self.rgb_dual_view_wrist_arm not in self.tactile_arms:
            raise ValueError(
                "rgb_dual_view_wrist_arm must name a recorded arm, got "
                f"{self.rgb_dual_view_wrist_arm!r} for {self.tactile_arms}"
            )
        if self.record_rgb_dual_view and not self.record_scene_rgb:
            raise ValueError("record_rgb_dual_view requires record_scene_rgb")
        self.frame_count = 0
        self.last_tactile_composite: np.ndarray | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._depth_range_written = False
        self._write_metadata()

    def _write_metadata(self) -> None:
        features: dict[str, Any] = {
            "observation.state": {"dtype": "float32", "shape": [len(self.state_layout)], "names": self.state_layout},
            "action": {"dtype": "float32", "shape": [len(self.action_layout)], "names": self.action_layout},
            "observation.images.tacumi_tactile_composite": {
                "dtype": "image",
                "shape": ["height", "width", "channels"],
                "layout": (
                    "arm blocks=left,right; each block rows=finger-left,finger-right; "
                    "columns=indent,deformation,shear,hsv"
                    if len(self.tactile_arms) == 2
                    else "rows=left,right; columns=indent,deformation,shear,hsv"
                ),
            },
        }
        for arm in self.tactile_arms:
            features[f"observation.images.cam_{arm}_wrist"] = {
                "dtype": "image",
                "shape": ["height", "width", "channels"],
            }
        if self.record_scene_rgb:
            features["observation.images.agentview"] = {
                "dtype": "image",
                "shape": ["height", "width", "channels"],
            }
        if self.record_rgb_dual_view:
            features["observation.images.rgb_dual_view"] = {
                "dtype": "image",
                "shape": ["height", "width", "channels"],
                "layout": (
                    "left=agentview; right=left_wrist_fisheye+right_wrist_fisheye"
                    if len(self.tactile_arms) > 1
                    else (
                        "left=agentview; right="
                        f"{self.rgb_dual_view_wrist_arm}_wrist_fisheye"
                    )
                ),
            }
        for arm in self.tactile_arms:
            for index in (0, 1):
                prefix = f"observation.tactile.cam_{arm}_finger{index}"
                features[f"{prefix}.depth_uint16"] = {"dtype": "uint16", "shape": ["height", "width"]}
                features[f"{prefix}.indent_uint16"] = {"dtype": "uint16", "shape": ["height", "width"]}
                features[f"{prefix}.deformation_uint16"] = {"dtype": "uint16", "shape": ["height", "width", 2]}
                features[f"{prefix}.shear_uint16"] = {"dtype": "uint16", "shape": ["height", "width", 2]}
                features[f"{prefix}.mask"] = {"dtype": "uint8", "shape": ["height", "width"]}
        self.info = {
            "schema": TACUMI_EPISODE_SCHEMA,
            "producer": "TacUMI",
            "codebase_version": LEGACY_CODEBASE_VERSION,
            "source": self.source,
            "task_id": self.task_id,
            "policy_contract": self.policy_contract,
            "robot_type": self.robot_type,
            "wrist_camera_contract": TACUMI_WRIST_CAMERA_CONTRACT,
            "end_effector_profile": self.end_effector_profile,
            "tactile_arms": list(self.tactile_arms),
            "tactile_sensor_roots_per_arm": 2,
            "tactile_sensor_root_count": 2 * len(self.tactile_arms),
            "rgb_dual_view_wrist_arm": self.rgb_dual_view_wrist_arm,
            "tactile_coordinate_contract": TACTILE_COORDINATE_CONTRACT,
            "tactile_zero_contact_contract": TACTILE_ZERO_CONTACT_CONTRACT,
            "fps": self.fps,
            "created_at": self.created_at,
            "tactile_uint16_encoding": {
                "float_to_uint16": "round(x * 1000000 + 30000)",
                "uint16_to_float": "(x - 30000) / 1000000",
                "scale": TACTILE_SCALE,
                "offset": TACTILE_OFFSET,
                "unit": "meter",
            },
            "depth_uint16_encoding": {
                "float_to_uint16": "round(depth_m * 1000000); 0 means no return",
                "uint16_to_float": "x / 1000000 meters; 0 means no return",
                "scale": DEPTH_SCALE,
                "invalid": DEPTH_INVALID,
                "unit": "meter",
                "display_min_m": 0.005,
                "display_max_m": 0.020,
            },
            "features": features,
        }
        self._flush_info()
        (self.meta_dir / "tasks.jsonl").write_text(
            json.dumps({"task_index": 0, "task": self.instruction}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _flush_info(self) -> None:
        (self.meta_dir / "info.json").write_text(
            json.dumps(self.info, indent=2), encoding="utf-8"
        )

    def _write_depth_display_range(
        self,
        tactile_by_arm: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        if self._depth_range_written:
            return
        near_values: list[float] = []
        far_values: list[float] = []
        for tactile in tactile_by_arm.values():
            for side in ("left", "right"):
                stats = tactile.get(side, {}).get("stats", {})
                raw_stats = (
                    stats.get("raw_depth", {})
                    if isinstance(stats, dict)
                    else {}
                )
                if not isinstance(raw_stats, dict):
                    continue
                try:
                    near = float(raw_stats["clip_near_m"])
                    far = float(raw_stats["clip_far_m"])
                except (KeyError, TypeError, ValueError):
                    continue
                if np.isfinite(near) and np.isfinite(far) and 0.0 <= near < far:
                    near_values.append(near)
                    far_values.append(far)
        if not near_values:
            return
        encoding = self.info["depth_uint16_encoding"]
        encoding["display_min_m"] = min(near_values)
        encoding["display_max_m"] = max(far_values)
        self._flush_info()
        self._depth_range_written = True

    def add_frame(
        self,
        *,
        state: Any,
        action: Any,
        wrist_rgb: Any,
        secondary_wrist_rgb: Any | None = None,
        scene_rgb: Any | None = None,
        tactile: dict[str, dict[str, Any]],
        secondary_tactile: dict[str, dict[str, Any]] | None = None,
        tactile_composite: Any | None = None,
        reward: float = 0.0,
        success: bool = False,
    ) -> Path:
        tactile_by_arm = {
            "left": {
                side: canonicalize_tactile_sample(tactile[side])
                for side in ("left", "right")
            }
        }
        secondary_wrist_array: np.ndarray | None = None
        if len(self.tactile_arms) == 2:
            if secondary_tactile is None:
                raise ValueError(
                    "secondary_tactile is required for dual-arm recording"
                )
            tactile_by_arm["right"] = {
                side: canonicalize_tactile_sample(secondary_tactile[side])
                for side in ("left", "right")
            }
        self._write_depth_display_range(tactile_by_arm)
        state_array = np.asarray(state, dtype=np.float32).reshape(-1)
        action_array = np.asarray(action, dtype=np.float32).reshape(-1)
        if state_array.size != len(self.state_layout):
            raise ValueError(f"State has {state_array.size} values, expected {len(self.state_layout)}")
        if action_array.size != len(self.action_layout):
            raise ValueError(f"Action has {action_array.size} values, expected {len(self.action_layout)}")

        if tactile_composite is None:
            multi_arm = len(self.tactile_arms) > 1
            arm_composites = [
                render_tactile_composite(
                    tactile_by_arm[arm],
                    labels=(
                        {
                            "left": f"{arm} arm / left pad",
                            "right": f"{arm} arm / right pad",
                        }
                        if multi_arm
                        else None
                    ),
                )
                for arm in self.tactile_arms
            ]
            if len(arm_composites) == 1:
                composite = arm_composites[0]
            else:
                # Arms sit side by side. Stacking them made a dual-arm clip
                # twice as tall as a single-arm one, which reads as a tall
                # video with dead bands whenever one arm is out of contact.
                gap = np.zeros(
                    (arm_composites[0].shape[0], 2, 3), dtype=np.uint8
                )
                composite = np.ascontiguousarray(
                    np.concatenate((arm_composites[0], gap, arm_composites[1]), axis=1)
                )
        else:
            composite = np.ascontiguousarray(
                np.asarray(tactile_composite, dtype=np.uint8)
            )
        self.last_tactile_composite = composite
        wrist_array = np.ascontiguousarray(np.asarray(wrist_rgb, dtype=np.uint8))
        payload: dict[str, np.ndarray] = {
            "observation.state": state_array,
            "action": action_array,
            "observation.images.cam_left_wrist": wrist_array,
            "observation.images.tacumi_tactile_composite": composite,
            "timestamp": np.asarray([self.frame_count / self.fps], dtype=np.float32),
            "frame_index": np.asarray([self.frame_count], dtype=np.int64),
            "episode_index": np.asarray([0], dtype=np.int64),
            "task_index": np.asarray([0], dtype=np.int64),
            "reward": np.asarray([reward], dtype=np.float32),
            "success": np.asarray([success], dtype=np.bool_),
        }
        if len(self.tactile_arms) == 2:
            if secondary_wrist_rgb is None:
                raise ValueError(
                    "secondary_wrist_rgb is required for dual-arm recording"
                )
            secondary_wrist_array = np.ascontiguousarray(
                np.asarray(secondary_wrist_rgb, dtype=np.uint8)
            )
            payload["observation.images.cam_right_wrist"] = secondary_wrist_array
        if self.record_scene_rgb:
            if scene_rgb is None:
                raise ValueError("scene_rgb is required when record_scene_rgb is enabled")
            scene_array = np.ascontiguousarray(np.asarray(scene_rgb, dtype=np.uint8))
            payload["observation.images.agentview"] = scene_array
            if self.record_rgb_dual_view:
                if secondary_wrist_array is not None:
                    # Dual-arm rig: both wrist fisheyes ride beside the scene.
                    wrist_panels = [wrist_array, secondary_wrist_array]
                else:
                    wrist_panels = [
                        secondary_wrist_array
                        if self.rgb_dual_view_wrist_arm == "right"
                        else wrist_array
                    ]
                panels = [scene_array]
                for panel in wrist_panels:
                    if panel.shape[0] != scene_array.shape[0]:
                        import cv2

                        target_height = scene_array.shape[0]
                        target_width = max(
                            1,
                            round(panel.shape[1] * target_height / panel.shape[0]),
                        )
                        panel = cv2.resize(
                            panel,
                            (target_width, target_height),
                            interpolation=cv2.INTER_AREA,
                        )
                    panels.append(panel)
                payload["observation.images.rgb_dual_view"] = np.ascontiguousarray(
                    np.concatenate(panels, axis=1)
                )
        for arm in self.tactile_arms:
            for index, side in enumerate(("left", "right")):
                sample = tactile_by_arm[arm][side]
                prefix = f"observation.tactile.cam_{arm}_finger{index}"
                payload[f"{prefix}.depth_uint16"] = encode_tactile_depth(sample["depth"])
                payload[f"{prefix}.indent_uint16"] = encode_tactile_float(sample["indent"])
                deformation = np.asarray(sample["deformation"], dtype=np.float32)
                payload[f"{prefix}.deformation_uint16"] = encode_tactile_float(deformation)
                shear = np.asarray(sample.get("shear", ()), dtype=np.float32)
                if shear.shape != deformation.shape:
                    shear = np.zeros_like(deformation)
                payload[f"{prefix}.shear_uint16"] = encode_tactile_float(shear)
                payload[f"{prefix}.mask"] = np.ascontiguousarray(np.asarray(sample["mask"], dtype=np.uint8))

        path = self.frames_dir / f"frame_{self.frame_count:06d}.npz"
        np.savez_compressed(path, **payload)
        self.frame_count += 1
        return path

    def close(self, *, success: bool, total_reward: float, extra: dict[str, Any] | None = None) -> Path:
        summary = {
            "source": self.source,
            "task_id": self.task_id,
            "task": self.instruction,
            "policy_contract": self.policy_contract,
            "embodiment": TACUMI_EMBODIMENT_ID,
            "tactile_zero_contact_contract": (
                TACTILE_ZERO_CONTACT_CONTRACT
            ),
            "frame_count": self.frame_count,
            "fps": self.fps,
            "success": bool(success),
            "total_reward": float(total_reward),
            "created_at": self.created_at,
        }
        summary.update(extra or {})
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
