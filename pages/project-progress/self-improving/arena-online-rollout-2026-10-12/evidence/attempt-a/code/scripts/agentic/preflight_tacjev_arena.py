#!/usr/bin/env python3
"""Run a fixed-token native component probe, without calling a model service.

This deliberately cannot produce a positive teacher demonstration. It checks
pre-action recording and physical execution before an online collector exists.
The operator must accept the Isaac license in this launch process environment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src", ROOT / "scripts", Path(__file__).resolve().parent):
    sys.path.insert(0, str(path))

TASK = "Grasp the cube and move it to the displayed target position."
# Preparation also consumes physical steps and receives a pre-action record.
# All targets derive from the robot TCP. No object pose chooses these actions.
PLAN = ("RELEASE",) * 8 + (
    "MV_FWD", "MV_BACK", "MV_LEFT", "MV_RIGHT", "MV_UP", "MV_DOWN",
    "GRASP", "RELEASE", "DONE",
)


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def archive_code(output: Path) -> dict:
    files = [Path(__file__).relative_to(ROOT), Path("scripts/agentic/run_isaaclab_arena_smoke.py"),
             Path("scripts/run_p0_rollout.py")]
    files += [Path("src/tacharness/isaaclab") / name for name in (
        "arena_tactile.py", "arena_collection_state.py", "arena_meta_actions.py",
        "arena_decision_records.py", "tacumi_arena.py", "rtx_camera.py")]
    files += [Path("src/tacumi") / name for name in ("recorder.py", "tactile_runtime.py", "visualization.py")]
    hashes = {}
    for relative in files:
        source = ROOT / relative
        destination = output / "code" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        destination.write_bytes(data)
        hashes[str(relative)] = hashlib.sha256(data).hexdigest()
    patch = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    (output / "code" / "tracked.patch").write_bytes(patch)
    receipt = {"git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "source_sha256": hashes, "tracked_patch_sha256": hashlib.sha256(patch).hexdigest()}
    write_json(output / "code_receipt.json", receipt)
    return receipt


def verify_video(path: Path) -> dict:
    import cv2
    capture = cv2.VideoCapture(str(path))
    decoded = 0
    try:
        while True:
            okay, frame = capture.read()
            if not okay:
                break
            if frame is None or not frame.size:
                raise RuntimeError("decoded_video_frame_empty")
            decoded += 1
    finally:
        capture.release()
    if not decoded:
        raise RuntimeError("video_has_no_decodable_frames")
    return {"path": path.name, "decoded_frames": decoded,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def save_initial_images(output: Path, images: dict) -> None:
    import cv2
    for name, rgb in images.items():
        if not cv2.imwrite(str(output / f"initial_{name}.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise RuntimeError("initial_image_write_failed")


def close_after_persisting(output: Path, report: dict, started: float, resources: tuple) -> None:
    """Keep final evidence even when native shutdown exits the Python process."""
    report["elapsed_s"] = round(time.monotonic() - started, 3)
    write_json(output / "report.json", report)
    for label, resource in resources:
        if resource is not None:
            try:
                resource.close()
            except Exception as exc:
                report.setdefault("shutdown_errors", []).append({"resource": label, "error_type": type(exc).__name__})
    report["elapsed_s"] = round(time.monotonic() - started, 3)
    write_json(output / "report.json", report)


def require_process_acknowledgement() -> None:
    # The generic repository helper has an older accepting default. This new
    # probe requires an acknowledgement explicitly passed in its launch env.
    if os.environ.get("OMNI_KIT_ACCEPT_EULA", "").strip().upper() not in {"Y", "YES"}:
        raise RuntimeError("probe_requires_explicit_launch_eula_acknowledgement")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--hold-frames", type=int, choices=(5, 15), default=5)
    parser.add_argument("--camera-profile", choices=("v1", "v2", "v3"), default="v3")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    observation_version = f"arena-visible-component-{args.camera_profile}"
    camera_lookat, camera_focal = {
        "v1": ((.5, 0, .25), 24.0),
        "v2": ((.5, 0, .4), 18.0),
        "v3": ((.5, 0, .5), 14.0),
    }[args.camera_profile]
    from run_p0_rollout import _failure_video, _recorded_video
    _failure_video(output / "startup_diagnostic.mp4", "Fixed-token Arena component probe", "No physical frames yet")
    started = time.monotonic()
    report = {"schema": "tacharness.arena.component-probe.v1", "status": "starting",
              "started_at": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
              "seed_pool": "development", "environment": "lift_object", "object": "dex_cube",
              "control_source": "component_token_probe", "online_teacher": False,
              "positive_demonstration_count": 0, "student_policy_executed": False,
              "teacher_inference_requests": 0, "native_attempts_started": 0,
              "env_step_calls_submitted": 0, "env_step_calls_returned": 0,
              "physical_frame_budget": 250, "plan": list(PLAN), "task": TASK,
              "observation_version": observation_version, "marker_rgb_visibility": "not_verified",
              "camera_profile": args.camera_profile,
              "video": verify_video(output / "startup_diagnostic.mp4"), "video_kind": "diagnostic_only"}
    write_json(output / "report.json", report)
    archive_code(output)
    simulation_app = env = recorder = writer = None

    def checkpoint(status: str, **values) -> None:
        report.update(status=status, elapsed_s=round(time.monotonic() - started, 3), **values)
        write_json(output / "report.json", report)

    try:
        from tacharness.runtime_ready import require_isaac_eula_acknowledgement
        require_process_acknowledgement()
        require_isaac_eula_acknowledgement()
        os.environ["ENABLE_CAMERAS"] = "1"
        # Baseline effort is explicit; it must not silently change across comparisons.
        os.environ["TACUMI_ARENA_GRIPPER_EFFORT_LIMIT"] = "1"
        from run_isaaclab_arena_smoke import _add_pythonpaths, _launcher_args
        _add_pythonpaths(installed_isaaclab=True)
        launcher_args = _launcher_args(argparse.Namespace(
            headless=True, device=args.device, width=960, height=540, seed=args.seed,
            num_envs=1, arena_env="lift_object", object="dex_cube", embodiment="franka_ik"))
        checkpoint("launching_app", gripper_effort_limit_nm=1.0)
        from isaaclab.app import AppLauncher
        simulation_app = AppLauncher(launcher_args).app
        checkpoint("app_launched")
        import gymnasium as gym
        import numpy as np
        from tacharness.isaaclab.tacumi_arena import install_tacumi_franka_embodiments
        install_tacumi_franka_embodiments()
        from isaaclab_arena_environments.cli import get_arena_builder_from_cli
        builder = get_arena_builder_from_cli(launcher_args)
        builder.cfg.language_instruction = TASK
        name, cfg, kwargs = builder.build_registered()
        checkpoint("creating_environment", native_attempts_started=1)
        env = gym.make(name, cfg=cfg, **kwargs)
        env.reset(seed=args.seed)
        native = env.unwrapped
        from tacharness.isaaclab.arena_collection_state import (
            snapshot_arena_state, assert_arena_state_unchanged, refresh_object_goal)
        from tacharness.isaaclab.arena_meta_actions import ArenaMetaActionInterpreter
        from tacharness.isaaclab.arena_decision_records import (
            ArenaDecisionRecordWriter, tactile_mosaic, validate_decision_records)
        from tacharness.isaaclab.arena_tactile import ArenaTactileRecorder
        goal = refresh_object_goal(native)
        write_json(output / "goal_receipt.json", goal)
        np.savez_compressed(output / "reset_state.npz", **snapshot_arena_state(native))
        reset_state = snapshot_arena_state(native)
        report["physics_steps_at_reset"] = int(reset_state["sim.physics_step_count"])
        report["physics_time_at_reset_s"] = float(reset_state["sim.physics_time_s"])
        interpreter = ArenaMetaActionInterpreter(env, hold_frames=args.hold_frames,
                                               version=f"arena-meta-actions-hold{args.hold_frames}-component-v1")
        write_json(output / "interpreter.json", interpreter.configuration())
        recorder = ArenaTactileRecorder(env, output / "native", "lift_object", 250,
                                       camera_eye=(1.6, 1.3, 1.1), camera_lookat=camera_lookat,
                                       scene_focal_length_mm=camera_focal, verify_frozen=True)
        recorder.policy_mode = "component_token_probe"
        writer = ArenaDecisionRecordWriter(output / "decisions", task=TASK,
                                           observation_version=observation_version,
                                           interpreter_version=interpreter.version)
        snapshot = recorder.sample_observation()

        def visible_images(observation):
            return {"scene_rgb": observation["scene_rgb"], "wrist_rgb": observation["wrist_rgb"],
                    "tactile_mosaic_rgb": tactile_mosaic(observation["tactile"])}

        save_initial_images(output, visible_images(snapshot))
        # A short passive wait exercises the service-wait boundary without a service.
        before = snapshot_arena_state(native)
        time.sleep(.05)
        freeze = assert_arena_state_unchanged(before, snapshot_arena_state(native))
        write_json(output / "passive_wait_freeze.json", {"wait_s": .05, "model_called": False, **freeze})
        checkpoint("initial_observation_ready", initial_render_freeze=snapshot["frozen_check"],
                   interpreter_config_sha256=interpreter.config_sha256)
        receipts = []
        for index, token in enumerate(PLAN):
            if len(recorder.rows) >= 250 or recorder.terminal:
                break
            metadata = interpreter.begin(token)
            decision_id = writer.begin(visible_images(snapshot), token, len(recorder.rows))
            write_json(output / "decisions" / decision_id / "interpreter.json", metadata)
            tcp_before = interpreter.arm._compute_frame_pose()[0].detach().cpu().numpy().copy()
            while (interpreter.remaining_frames and not recorder.terminal
                   and report["env_step_calls_returned"] < 250):
                action = interpreter.action()
                recorder.begin_step(action)
                report["env_step_calls_submitted"] += 1
                _, reward, _, _, _ = env.step(action)
                report["env_step_calls_returned"] += 1
                recorder.finish_step(reward)
            execution = writer.finish(len(recorder.rows), native_success=recorder.success)
            tcp_after = (None if recorder.terminal else
                         interpreter.arm._compute_frame_pose()[0].detach().cpu().numpy().copy())
            receipts.append({"decision_id": decision_id, "token": token, "preparation": index < 8,
                             "interpreter": metadata, "execution": execution,
                             "tcp_position_base_before": tcp_before.tolist(),
                             "requested_control_frames": metadata["hold_frames"],
                             "unissued_control_frames": interpreter.remaining_frames,
                             "stop_reason": "native_terminal_before_reset" if recorder.terminal else "token_interval_complete",
                             "tcp_position_base_after": None if tcp_after is None else tcp_after.tolist(),
                             "tcp_delta_base_m": None if tcp_after is None else (tcp_after - tcp_before).tolist()})
            write_json(output / "token_receipts.json", {"records": receipts})
            snapshot = recorder.last_observation
            checkpoint("executing_fixed_tokens", actual_control_frames=len(recorder.rows),
                       decision_count=len(receipts), last_token=token)
            if interpreter.done:
                break
        writer.close()
        validation = validate_decision_records(output / "decisions", native_frame_count=len(recorder.rows))
        if not validation["valid"]:
            raise RuntimeError("decision_record_validation_failed")
        checkpoint("component_execution_complete", decisions_validation=validation,
            actual_control_frames=len(recorder.rows), native_success=recorder.success,
            native_task_verdict=("success" if recorder.success else "partial_budget_non_success"),
            simulated_time_s=len(recorder.rows) * float(native.step_dt),
            contact_frames=sum(any(row["physical_contact"].values()) for row in recorder.rows))
    except Exception as exc:
        traceback.print_exc()
        freeze_report = getattr(exc, "report", None)
        checkpoint("component_failed", error_type=type(exc).__name__, error=str(exc),
                   state_guard_failure=freeze_report)
        if writer is not None and writer.pending_decision_id is not None:
            writer.finish(report["env_step_calls_returned"], status="interrupted",
                          failure_reason="component_execution_interrupted_unrecorded_steps_possible")
        if writer is not None and not (output / "decisions" / "closed.json").exists():
            writer.close()
    finally:
        try:
            if env is not None and "physics_steps_at_reset" in report:
                try:
                    final_state = snapshot_arena_state(env)
                    np.savez_compressed(output / "final_state.npz", **final_state)
                    report["physics_steps_at_end"] = int(final_state["sim.physics_step_count"])
                    report["physics_time_at_end_s"] = float(final_state["sim.physics_time_s"])
                    report["physics_steps_since_reset"] = (
                        report["physics_steps_at_end"] - report["physics_steps_at_reset"])
                except Exception as exc:
                    report.update(status="component_evidence_failed", final_state_error_type=type(exc).__name__)
            if recorder is not None:
                recorder.close()
                report["actual_control_frames"] = len(recorder.rows)
                report["recorded_frames_equal_returned_control_steps"] = (
                    len(recorder.rows) == report["env_step_calls_returned"])
                report["execution_accounting_valid"] = (
                    report["env_step_calls_submitted"] == report["env_step_calls_returned"] == len(recorder.rows)
                    and report.get("physics_steps_since_reset") == len(recorder.rows) * native.cfg.decimation)
                if writer is not None and (output / "decisions" / "closed.json").exists():
                    report["decisions_validation"] = validate_decision_records(
                        output / "decisions", native_frame_count=len(recorder.rows))
                if report["status"] == "component_execution_complete" and (
                    not report["execution_accounting_valid"] or not report["decisions_validation"]["valid"]
                ):
                    report.update(status="component_evidence_failed", evidence_error="execution_or_recording_accounting_failed")
            count = _recorded_video(output, output / "rollout.mp4")
            if count:
                # H.264 is playable by the desktop preview; preserve all native frames.
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(output / "rollout.mp4"),
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                                str(output / "rollout_h264.mp4")], check=True)
                report["video"] = verify_video(output / "rollout_h264.mp4")
                report["video_kind"] = "native_component_frames"
                if report["video"]["decoded_frames"] != count:
                    raise RuntimeError("video_native_frame_count_mismatch")
        except Exception as exc:
            traceback.print_exc()
            report.update(status="component_evidence_failed", evidence_error_type=type(exc).__name__,
                          evidence_error=str(exc))
        finally:
            close_after_persisting(output, report, started,
                                  (("environment", env), ("simulation_app", simulation_app)))
    return 0 if report["status"] == "component_execution_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
