"""Single-environment Arena TacClaw recording with physical contact gates."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np


def as_numpy(value):
    if hasattr(value, 'torch'):
        value = value.torch
    if hasattr(value, 'detach'):
        value = value.detach().cpu()
    return value.numpy() if hasattr(value, 'numpy') else np.asarray(value)


class ArenaTactileRecorder:
    def __init__(self, env, output: Path, task: str, steps: int, *,
                 camera_eye=(1.6, 1.3, 1.1), camera_lookat=(.5, 0, .1),
                 scene_focal_length_mm=None, verify_frozen=False):
        import omni.physx
        from isaacsim.core.rendering_manager import ViewportManager
        from .rtx_camera import RtxCamera as Camera
        from tacumi.recorder import UnifiedEpisodeRecorder
        from tacumi.tactile_runtime import TacumiTactileRuntime

        self.env = env.unwrapped
        if self.env.num_envs != 1:
            raise ValueError('P0 tactile recorder requires one environment')
        self.physx = omni.physx.get_physx_interface()
        self.runtime = TacumiTactileRuntime(
            root_prefix='/World/envs/env_0/Robot/Gripper/Tacumi', expected_sensors=2, camera_class=Camera)
        self.wrist = Camera(prim_path='/World/envs/env_0/Robot/Gripper/Tacumi/Link3/wrist_cam',
                            name='p0_wrist', resolution=(640, 360))
        self.scene = Camera(prim_path='/World/P0SceneCamera', name='p0_scene', resolution=(640, 360))
        if task == 'franka_put_and_close_door':
            # USD's 50 mm default crops the approach/cube out of the kitchen
            # view. Only widen the scene camera, never the tactile cameras.
            self.scene.camera.GetFocalLengthAttr().Set(24.0)
        if scene_focal_length_mm is not None:
            if not np.isfinite(scene_focal_length_mm) or scene_focal_length_mm <= 0:
                raise ValueError('Scene focal length must be finite and positive')
            self.scene.camera.GetFocalLengthAttr().Set(float(scene_focal_length_mm))
        for camera in (self.wrist, self.scene):
            camera.initialize()
        ViewportManager.set_camera_view('/World/P0SceneCamera', eye=list(camera_eye), target=list(camera_lookat))
        self.robot = self.env.scene['robot']
        self.control_arm = self.env.action_manager.get_term('arm_action')
        self.contact = self.env.scene['contact_gripper']
        self.body_ids = {side: list(self.contact.body_names).index(name)
                         for side, name in [('left', 'Link5'), ('right', 'Link4')]}
        self.output = output
        self.steps = steps
        self.rows = []
        self.source_actions_submitted = 0
        self.terminal = False
        self._pending = None
        self._captured_before_reset = False
        self.verify_frozen = bool(verify_frozen)
        self.last_observation = None
        self.success = False
        self.policy_mode = "zero_action_smoke"
        self.checkpoint_sha256 = None
        self.policy_source_sha256 = None
        self.total_reward = 0.0
        self.recorder = UnifiedEpisodeRecorder(
            output, source='isaaclab_arena_franka', task_id=task, instruction=self.env.get_language_instruction(),
            policy_contract='arena-tacclaw-native-recording-v1',
            state_layout=list(self.robot.joint_names),
            action_layout=[f'arena_action_{i}' for i in range(self.env.action_manager.total_action_dim)],
            fps=1.0 / self.env.step_dt, record_scene_rgb=True, record_rgb_dual_view=True)
        frames = self.env.scene['ee_frame'].data
        names = list(frames.target_frame_names)
        if names != ['end_effector']:
            raise ValueError(f'Arena TCP observation must not silently refer to a finger: {names}')
        setup = {'ee_frame_names': names,
                 'scene_camera': {'eye': list(camera_eye), 'lookat': list(camera_lookat),
                                  'focal_length_mm': self.scene.camera.GetFocalLengthAttr().Get(),
                                  'resolution': list(self.scene.resolution),
                                  'horizontal_aperture_mm': self.scene.camera.GetHorizontalApertureAttr().Get(),
                                  'vertical_aperture_mm': self.scene.camera.GetVerticalApertureAttr().Get()},
                 'finger_frame_names': list(self.env.scene['tacumi_finger_frames'].data.target_frame_names),
                 'robot_joint_names': list(self.robot.joint_names),
                 'default_joint_positions': as_numpy(self.robot.data.default_joint_pos)[0].tolist()}
        from pxr import UsdPhysics
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        setup['gripper_drive_type'] = {
            name: UsdPhysics.DriveAPI.Get(
                stage.GetPrimAtPath(f'/World/envs/env_0/Robot/Gripper/Tacumi/joints/{name}'),
                'angular').GetTypeAttr().Get()
            for name in ('Link4_joint', 'Link5_joint')}
        setup['actuator_parameters'] = {
            name: as_numpy(getattr(self.robot.data, name))[0].tolist()
            for name in ('joint_stiffness', 'joint_damping', 'joint_effort_limits')}
        setup['object_mass_kg'] = as_numpy(self.env.scene['dex_cube'].data.body_mass).tolist()
        arm_term = self.env.action_manager.get_term('arm_action')
        if hasattr(arm_term, '_compute_frame_pose'):
            position, _ = arm_term._compute_frame_pose()
            setup['controller_vs_observation_tcp_delta_m'] = float(np.max(np.abs(
                as_numpy(position) - as_numpy(frames.target_pos_source)[:, 0])))
        (self.output / 'embodiment_audit.json').write_text(json.dumps(setup, indent=2) + '\n')
        self._original_reset = self.env._reset_idx
        self.env._reset_idx = self._capture_before_reset

    def begin_step(self, action, teacher_observation=None):
        self.source_actions_submitted = getattr(self, 'source_actions_submitted', 0) + 1
        self._pending = (action, teacher_observation)
        self._captured_before_reset = False

    def _capture_before_reset(self, env_ids):
        # ManagerBasedRLEnv auto-resets before returning step(). Record the
        # actual terminal physical state, not the freshly reset scene.
        if self._pending is not None:
            action, observation = self._pending
            self.capture(action, self.env.reward_buf, observation, terminal=True)
            self._captured_before_reset = True
            self.terminal = True
        return self._original_reset(env_ids)

    def finish_step(self, reward):
        if not self._captured_before_reset:
            action, observation = self._pending
            self.capture(action, reward, observation)
        self._pending = None

    def _render(self):
        from isaaclab_physx.renderers.isaac_rtx_renderer_utils import ensure_isaac_rtx_render_update

        self.env.sim.render()
        ensure_isaac_rtx_render_update()

    def sample_observation(self):
        """Sample current images without adding an action frame or reward.

        A new snapshot runs the tactile solver once. A repeated decision must
        reuse this snapshot, rather than run the solver again during a retry.
        """
        verify_frozen = getattr(self, 'verify_frozen', False)
        if verify_frozen:
            from .arena_collection_state import snapshot_arena_state, assert_arena_state_unchanged

            before = snapshot_arena_state(self.env)

        self.physx.update_transformations(True, True, True, False)
        forces = as_numpy(self.contact.data.net_forces_w)[0]
        force_n = {side: float(np.linalg.norm(forces[index])) for side, index in self.body_ids.items()}
        contact = {side: force >= .01 for side, force in force_n.items()}
        state_before_render = as_numpy(self.robot.data.joint_pos).copy()
        with self.runtime.hide_sensor_geometry_for_depth():
            for _ in range(16):
                self._render()
            tactile = deepcopy(self.runtime.step(contact_by_side=contact))
        for _ in range(16):
            self._render()
        render_state_delta = float(np.max(np.abs(as_numpy(self.robot.data.joint_pos) - state_before_render)))
        if render_state_delta > 1e-7:
            raise RuntimeError(f'Rendering advanced robot state by {render_state_delta}')
        scene = np.array(self.scene.get_rgba(), copy=True)[..., :3]
        wrist = np.array(self.wrist.get_rgba(), copy=True)[..., :3]
        if scene.ndim != 3 or wrist.ndim != 3 or scene.shape[-1] != 3 or wrist.shape[-1] != 3:
            raise RuntimeError('Scene/wrist camera did not produce an RGB frame')
        frozen_check = None
        if verify_frozen:
            frozen_check = assert_arena_state_unchanged(before, snapshot_arena_state(self.env))
        snapshot = {
            'scene_rgb': scene,
            'wrist_rgb': wrist,
            'tactile': tactile,
            'state': as_numpy(self.robot.data.joint_pos)[0].copy(),
            'physical_contact': contact,
            'contact_force_n': force_n,
            'render_state_delta': render_state_delta,
            'frozen_check': frozen_check,
        }
        if getattr(self, 'control_arm', None) is not None:
            tcp_position, tcp_quaternion = self.control_arm._compute_frame_pose()
            snapshot['control_tcp_pose_base_xyzw'] = np.concatenate(
                (as_numpy(tcp_position)[0], as_numpy(tcp_quaternion)[0])).copy()
            snapshot['robot_joint_velocity'] = as_numpy(self.robot.data.joint_vel)[0].copy()
        self.last_observation = snapshot
        return snapshot

    def capture(self, action, reward, teacher_observation=None, terminal=False):
        snapshot = self.sample_observation()
        success = bool(as_numpy(self.env.termination_manager.get_term('success'))[0])
        self.success |= success
        step_reward = float(as_numpy(reward)[0])
        self.total_reward += step_reward
        target = as_numpy(action)[0]
        self.recorder.add_frame(state=snapshot['state'], action=target,
                                scene_rgb=snapshot['scene_rgb'], wrist_rgb=snapshot['wrist_rgb'],
                                tactile=snapshot['tactile'],
                                reward=step_reward, success=success)
        self.rows.append({'source_frame': len(self.rows), 'target_action': target.tolist(),
                          'physical_contact': snapshot['physical_contact'],
                          'contact_force_n': snapshot['contact_force_n'],
                          'joint_position_target': as_numpy(self.robot.data.joint_pos_target)[0].tolist(),
                          'rigid_object_poses_xyzw': {
                              name: np.concatenate((as_numpy(obj.data.root_pos_w)[0],
                                                    as_numpy(obj.data.root_quat_w)[0])).tolist()
                              for name, obj in self.env.scene.rigid_objects.items()},
                          'other_articulation_joints': {
                              name: as_numpy(obj.data.joint_pos)[0].tolist()
                              for name, obj in self.env.scene.articulations.items() if name != 'robot'},
                          'subtask_success_state': deepcopy(self.env.extras.get('subtask_success_state')),
                          'render_state_delta': snapshot['render_state_delta'],
                          'render_frozen_check': snapshot['frozen_check'], 'terminal_before_reset': terminal,
                          'teacher_observation': teacher_observation.tolist() if teacher_observation is not None else None,
                          'control_tcp_pose_base_xyzw': snapshot['control_tcp_pose_base_xyzw'].tolist()
                              if 'control_tcp_pose_base_xyzw' in snapshot else None,
                          'robot_joint_velocity': snapshot['robot_joint_velocity'].tolist()
                              if 'robot_joint_velocity' in snapshot else None,
                          'policy_checkpoint_sha256': self.checkpoint_sha256,
                          'policy_source_sha256': self.policy_source_sha256})
        (self.output / 'trajectory.json').write_text(json.dumps(self.rows, indent=2) + '\n')

    def close(self):
        self.env._reset_idx = self._original_reset
        self.recorder.close(success=self.success, total_reward=self.total_reward, extra={
            'policy_mode': self.policy_mode,
            'source_action_count': getattr(self, 'source_actions_submitted', len(self.rows)),
            'source_action_count_semantics': 'begin_step_submissions',
            'recorded_action_count': len(self.rows),
            'requested_step_budget': self.steps, 'terminal_captured_before_reset': self.terminal,
            'policy_checkpoint_sha256': self.checkpoint_sha256,
            'policy_source_sha256': self.policy_source_sha256,
            'contact_force_threshold_n': .01, 'tactile_render_passes': 16,
            'p0_complete': False, 'note': 'Native recording; task success, policy lineage and tactile quality require independent gates.'})
