"""Install TacUMI/TacClaw Franka embodiments into IsaacLab-Arena.

Arena's upstream Franka classes intentionally use the stock Panda hand.  P0
rollouts must use the repository's TacUMI asset instead, so this adapter keeps
Arena's task/action classes and replaces only the robot asset, gripper joints,
and contact sensor at the embodiment boundary.
"""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from tacumi.embodiment import TACUMI_CLOSE_ANGLE_RAD, TACUMI_TCP_OFFSET_M

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TACUMI_USD = ROOT / "assets" / "robots" / "isaaclab_franka_tacumi_dm25pd04.usda"
TACTILE_ROOT = "{ENV_REGEX_NS}/Robot/Gripper/Tacumi"
CONTACT_PRIM = f"{TACTILE_ROOT}/Link[45]"


def tacumi_usd_path() -> str:
    path = Path(os.environ.get("TACUMI_FRANKA_USD_PATH", DEFAULT_TACUMI_USD)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"TacUMI Franka asset does not exist: {path}")
    return str(path)


def _tacumi_robot_cfg(base_cfg: Any) -> Any:
    from isaaclab.actuators import ImplicitActuatorCfg

    cfg = base_cfg.copy()
    cfg.spawn.usd_path = tacumi_usd_path()
    cfg.spawn.activate_contact_sensors = True
    cfg.actuators.pop("panda_hand", None)
    cfg.actuators["tacumi_gripper"] = ImplicitActuatorCfg(
        joint_names_expr=["Link4_joint", "Link5_joint"],
        effort_limit_sim=float(os.environ.get("TACUMI_ARENA_GRIPPER_EFFORT_LIMIT", "20.0")),
        velocity_limit_sim=float(os.environ.get("TACUMI_ARENA_GRIPPER_VELOCITY_LIMIT", "2.0")),
        stiffness=float(os.environ.get("TACUMI_ARENA_GRIPPER_STIFFNESS", "2000.0")),
        damping=float(os.environ.get("TACUMI_ARENA_GRIPPER_DAMPING", "100.0")),
        friction=0.0,
        armature=0.0,
    )
    cfg.init_state.joint_pos = {
        key: value for key, value in cfg.init_state.joint_pos.items()
        if not key.startswith("panda_finger")
    }
    cfg.init_state.joint_pos.update({"Link4_joint": 0.0, "Link5_joint": 0.0})
    return cfg


def _patch_gripper_action(action_config: Any) -> None:
    action = action_config.gripper_action
    action.joint_names = ["Link4_joint", "Link5_joint"]
    action.open_command_expr = {"Link4_joint": 0.0, "Link5_joint": 0.0}
    action.close_command_expr = {
        "Link4_joint": TACUMI_CLOSE_ANGLE_RAD,
        "Link5_joint": -TACUMI_CLOSE_ANGLE_RAD,
    }
    arm = action_config.arm_action
    if hasattr(arm, "body_name"):
        arm.body_name = "base_link"
        arm.body_offset.pos = TACUMI_TCP_OFFSET_M


def _patch_ee_frames(scene_config: Any) -> Any:
    for frame in getattr(scene_config.ee_frame, "target_frames", []):
        if getattr(frame, "name", "") == "end_effector":
            frame.prim_path = f"{TACTILE_ROOT}/base_link"
            frame.offset.pos = TACUMI_TCP_OFFSET_M
        elif frame.name in {"tool_rightfinger", "tool_leftfinger"}:
            side = "Link4" if frame.name == "tool_rightfinger" else "Link5"
            frame.prim_path = f"{TACTILE_ROOT}/{side}"
            frame.offset.pos = (0.0, 0.0, 0.0)
    # PhysX FrameTransformer sorts targets by prim path, not config order.
    # Link4/Link5 sort before base_link, while Arena's MDP assumes TCP at 0.
    fingers = deepcopy(scene_config.ee_frame)
    fingers.target_frames = [frame for frame in fingers.target_frames if frame.name != 'end_effector']
    scene_config.ee_frame.target_frames = [frame for frame in scene_config.ee_frame.target_frames
                                           if frame.name == 'end_effector']
    return fingers


def tacumi_initial_joint_pose(pose: list[float]) -> list[float]:
    """Preserve seven arm joints; Panda's 0.04 m opening is not a TacClaw angle."""
    return [*pose[:7], 0.0, 0.0]


def _patch_embodiment_instance(instance: Any, base_cfg: Any) -> None:
    from isaaclab.sensors import ContactSensorCfg
    from isaaclab_arena.utils.configclass import combine_configclass_instances, make_configclass

    instance.scene_config.robot = _tacumi_robot_cfg(base_cfg).replace(prim_path="{ENV_REGEX_NS}/Robot")
    contact_cfg = ContactSensorCfg(
        prim_path=CONTACT_PRIM,
        track_contact_points=False,
        track_friction_forces=False,
        filter_prim_paths_expr=[],
    )
    # Arena composes dataclass fields, so a dynamic instance attribute would
    # silently disappear before InteractiveScene creates its contact sensor.
    finger_frames = _patch_ee_frames(instance.scene_config)
    contact_scene = make_configclass('TacClawContactSceneCfg', [
        ('contact_gripper', ContactSensorCfg, contact_cfg),
        ('tacumi_finger_frames', type(finger_frames), finger_frames)])()
    instance.scene_config = combine_configclass_instances(
        'TacClawFrankaSceneCfg', instance.scene_config, contact_scene)
    pose = instance.event_config.init_franka_arm_pose.params['default_pose']
    instance.event_config.init_franka_arm_pose.params['default_pose'] = tacumi_initial_joint_pose(pose)
    _patch_gripper_action(instance.action_config)
    instance.tacumi_tactile_contract = {
        "asset": tacumi_usd_path(),
        "sensor_root": CONTACT_PRIM,
        "body_names": ["Link4", "Link5"],
        "contact_field": "scene.contact_gripper.data.net_forces_w",
    }


def install_tacumi_franka_embodiments() -> dict[str, Any]:
    """Patch registered Arena Franka classes once and return the contract."""
    from isaaclab_arena.embodiments.franka.franka import (
        FrankaEmbodimentBase,
        FrankaIKEmbodiment,
        FrankaJointPosEmbodiment,
        _FRANKA_IK_REL_CFG,
        _FRANKA_JOINT_POS_CFG,
    )

    marker = "_tacharness_tacumi_installed"
    if getattr(FrankaIKEmbodiment, marker, False):
        return {"installed": True, "asset": tacumi_usd_path(), "already_installed": True}

    original_set_pose = FrankaEmbodimentBase.set_initial_joint_pose

    def set_tacumi_pose(self: Any, initial_joint_pose: list[float]) -> None:
        original_set_pose(self, tacumi_initial_joint_pose(initial_joint_pose))

    FrankaEmbodimentBase.set_initial_joint_pose = set_tacumi_pose
    for cls, base_cfg in (
        (FrankaIKEmbodiment, _FRANKA_IK_REL_CFG),
        (FrankaJointPosEmbodiment, _FRANKA_JOINT_POS_CFG),
    ):
        original_init = cls.__init__

        def patched_init(self: Any, *args: Any, _original_init=original_init, _base_cfg=base_cfg, **kwargs: Any) -> None:
            _original_init(self, *args, **kwargs)
            _patch_embodiment_instance(self, _base_cfg)

        cls.__init__ = patched_init
        setattr(cls, marker, True)

    return {
        "installed": True,
        "asset": tacumi_usd_path(),
        "sensor_root": CONTACT_PRIM,
        "body_names": ["Link4", "Link5"],
    }
