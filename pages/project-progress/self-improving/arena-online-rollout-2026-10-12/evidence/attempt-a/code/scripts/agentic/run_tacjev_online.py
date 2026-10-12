#!/usr/bin/env python3
"""One reserved online Arena attempt, with bounded parent supervision."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src", ROOT / "scripts", Path(__file__).resolve().parent):
    sys.path.insert(0, str(path))

from preflight_tacjev_arena import (
    TASK, archive_code, close_after_persisting, require_process_acknowledgement,
    save_initial_images, verify_video, write_json,
)


def record_code(output: Path) -> None:
    receipt = archive_code(output)
    paths = [Path(__file__).relative_to(ROOT), Path("src/tacharness/tacjev_teacher.py"),
             Path("src/tacharness/first_collection_budget.py")]
    paths += [Path("src/tacharness/isaaclab") / name for name in (
        "arena_online_execution.py", "arena_online_records.py", "tacjev_online_dataset.py")]
    for relative in paths:
        source = ROOT / relative
        destination = output / "code" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        destination.write_bytes(data)
        receipt["source_sha256"][str(relative)] = hashlib.sha256(data).hexdigest()
    write_json(output / "code_receipt.json", receipt)


def export_video(output: Path, report: dict) -> None:
    from run_p0_rollout import _recorded_video
    count = _recorded_video(output, output / "rollout.mp4")
    if count:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(output / "rollout.mp4"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(output / "rollout_h264.mp4")], check=True)
        report["video"] = verify_video(output / "rollout_h264.mp4")
        report["video_kind"] = "native_online_frames"
        if report["video"]["decoded_frames"] != count:
            raise RuntimeError("native_video_frame_count_mismatch")


def native_run(args) -> int:
    from tacharness.first_collection_budget import FirstCollectionBudget
    budget = FirstCollectionBudget.open(args.budget)
    output = args.output.resolve()
    reservation = json.loads((output / "reservation.json").read_text())
    ledger = budget.snapshot()
    matching = [entry for entry in ledger["reservations"] if entry.get("kind") == "native_attempt"
                and entry.get("ordinal") == reservation["attempt_number"] and entry.get("output") == str(output)]
    if (reservation["output"] != str(output) or not matching or budget.remaining_wall_s() <= 0
            or (output / "report.json").exists()):
        raise RuntimeError("native_reservation_invalid_or_expired")
    with (output / "native_started.json").open("x") as handle:
        json.dump({"ordinal": reservation["attempt_number"], "started_at": datetime.now(timezone.utc).isoformat()}, handle)
    from run_p0_rollout import _failure_video
    _failure_video(output / "startup_diagnostic.mp4", "Online Arena teacher", "No physical frames yet")
    started = time.monotonic()
    interpreter_version = f"arena-online-step{args.translation_step}-clamp{args.translation_clamp}-hold{args.hold_frames}-v1"
    report = {
        "schema": "tacharness.arena.online-run.v1", "status": "starting", "outcome": "starting",
        "started_at": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
        "seed_pool": "development", "environment": "lift_object", "object": "dex_cube",
        "control_source": "online_multimodal_teacher", "online_teacher": True,
        "positive_demonstration": False, "train_action_mask": False,
        "teacher_model": args.model, "teacher_inference_requests": 0,
        "teacher_response_model": args.response_model, "teacher_protocol": args.protocol,
        "observation_version": "arena-visible-online-v3", "interpreter_version": interpreter_version,
        "prompt_version": "arena-online-teacher-v1", "physical_frame_budget": 250,
        "native_success": False, "native_frame_count": 0, "task": TASK,
        "env_step_calls_submitted": 0, "env_step_calls_returned": 0,
        "video": verify_video(output / "startup_diagnostic.mp4"), "video_kind": "diagnostic_only",
        "privileged_teacher_inputs": [], "native_attempt_number": reservation["attempt_number"],
    }
    write_json(output / "report.json", report)
    record_code(output)
    simulation_app = env = recorder = writer = None
    native = None
    request_start = budget.snapshot()["teacher_inference_requests"]

    def checkpoint(status: str, **values) -> None:
        report.update(status=status, elapsed_s=time.monotonic() - started, **values)
        write_json(output / "report.json", report)

    def interrupted(signum, frame):
        raise KeyboardInterrupt("budget_or_operator_stop")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        require_process_acknowledgement()
        from tacharness.runtime_ready import require_isaac_eula_acknowledgement
        require_isaac_eula_acknowledgement()
        os.environ["ENABLE_CAMERAS"] = "1"
        os.environ["TACUMI_ARENA_GRIPPER_EFFORT_LIMIT"] = "1"
        from run_isaaclab_arena_smoke import _add_pythonpaths, _launcher_args
        _add_pythonpaths(installed_isaaclab=True)
        launch = _launcher_args(argparse.Namespace(
            headless=True, device=args.device, width=960, height=540, seed=args.seed,
            num_envs=1, arena_env="lift_object", object="dex_cube", embodiment="franka_ik"))
        checkpoint("launching_app", gripper_effort_limit_nm=1.0)
        from isaaclab.app import AppLauncher
        simulation_app = AppLauncher(launch).app
        import gymnasium as gym
        import numpy as np
        from tacharness.isaaclab.tacumi_arena import install_tacumi_franka_embodiments
        install_tacumi_franka_embodiments()
        from isaaclab_arena_environments.cli import get_arena_builder_from_cli
        builder = get_arena_builder_from_cli(launch)
        builder.cfg.language_instruction = TASK
        name, cfg, kwargs = builder.build_registered()
        env = gym.make(name, cfg=cfg, **kwargs)
        env.reset(seed=args.seed)
        native = env.unwrapped
        from tacharness.isaaclab.arena_collection_state import (
            snapshot_arena_state, assert_arena_state_unchanged, refresh_object_goal)
        from tacharness.isaaclab.arena_meta_actions import ArenaMetaActionInterpreter
        from tacharness.isaaclab.arena_decision_records import tactile_mosaic
        from tacharness.isaaclab.arena_online_records import OnlineDecisionRecordWriter
        from tacharness.isaaclab.arena_online_execution import execute_online_decision
        from tacharness.isaaclab.arena_tactile import ArenaTactileRecorder
        from tacharness.tacjev_teacher import OnlineTeacher
        write_json(output / "goal_receipt.json", refresh_object_goal(native))
        reset_state = snapshot_arena_state(native)
        np.savez_compressed(output / "reset_state.npz", **reset_state)
        report["physics_steps_at_reset"] = int(reset_state["sim.physics_step_count"])
        interpreter = ArenaMetaActionInterpreter(env, hold_frames=args.hold_frames,
            translation_step=args.translation_step, translation_clamp=args.translation_clamp,
            version=interpreter_version)
        write_json(output / "interpreter.json", interpreter.configuration())
        recorder = ArenaTactileRecorder(env, output / "native", "lift_object", 250,
            camera_eye=(1.6, 1.3, 1.1), camera_lookat=(.5, 0, .5),
            scene_focal_length_mm=14, verify_frozen=True)
        recorder.policy_mode = "online_multimodal_teacher"
        writer = OnlineDecisionRecordWriter(output / "decisions", task=TASK,
            observation_version=report["observation_version"], interpreter_version=interpreter_version,
            teacher_model=args.model)
        teacher = OnlineTeacher(args.service_config, args.model, budget,
                               request_timeout_s=args.request_timeout_s, protocol=args.protocol,
                               expected_response_model=args.response_model)
        snapshot = recorder.sample_observation()
        records: list[dict] = []
        while len(recorder.rows) < 250 and not recorder.terminal and budget.remaining_wall_s() > 0:
            if budget.snapshot()["teacher_requests_remaining"] <= 0:
                report["outcome"] = "teacher_request_budget_exhausted"
                break
            visible = {"scene_rgb": snapshot["scene_rgb"], "wrist_rgb": snapshot["wrist_rgb"],
                       "tactile_mosaic_rgb": tactile_mosaic(snapshot["tactile"])}
            if not records:
                save_initial_images(output, visible)
            result = execute_online_decision(images=visible, task=TASK, writer=writer, teacher=teacher,
                interpreter=interpreter, recorder=recorder, env=env, budget=budget,
                snapshot_state=lambda: snapshot_arena_state(native),
                check_state=assert_arena_state_unchanged, accounting=report)
            # Large actual request bodies stay in their immutable decision directory.
            records.append({key: value for key, value in result.items() if key != "inference"})
            report["teacher_inference_requests"] = budget.snapshot()["teacher_inference_requests"] - request_start
            write_json(output / "token_receipts.json", {"records": records})
            checkpoint("online_execution", native_frame_count=len(recorder.rows),
                       actual_control_frames=len(recorder.rows), decision_count=len(records),
                       last_token=result["token"], outcome=result["stop_reason"])
            print(json.dumps({"frames": len(recorder.rows), "decision": len(records),
                              "token": result["token"], "stop": result["stop_reason"]}), flush=True)
            if result["stop_reason"] != "continue":
                break
            snapshot = recorder.last_observation
        if budget.remaining_wall_s() <= 0:
            report["outcome"] = "wall_budget_exhausted"
        elif recorder.success:
            report["outcome"] = "native_success"
        elif len(recorder.rows) == 250:
            report["outcome"] = "full_physical_budget_non_success"
        checkpoint("online_execution_complete", native_success=bool(recorder.success),
                   native_terminal=bool(recorder.terminal))
    except (Exception, KeyboardInterrupt) as exc:
        # Transport details and exception messages can contain private endpoints.
        checkpoint("online_interrupted", outcome="interrupted", error_type=type(exc).__name__)
    finally:
        def evidence_failure(exc):
            report.update(status="online_evidence_incomplete", evidence_error_type=type(exc).__name__)

        try:
            if writer is not None:
                assert recorder is not None
                if writer.pending_decision_id is not None:
                    writer.complete(writer.pending_decision_id, len(recorder.rows), len(recorder.rows),
                                    status="interrupted", failure_reason="collector_interrupted")
                report["decisions_validation"] = writer.close(native_frame_count=len(recorder.rows))
                if not report["decisions_validation"]["valid"]:
                    report["status"] = "online_evidence_incomplete"
        except (Exception, KeyboardInterrupt) as exc:
            evidence_failure(exc)
        try:
            if env is not None and "physics_steps_at_reset" in report:
                import numpy as np
                from tacharness.isaaclab.arena_collection_state import snapshot_arena_state
                final_state = snapshot_arena_state(env)
                np.savez_compressed(output / "final_state.npz", **final_state)
                report["physics_steps_since_reset"] = int(final_state["sim.physics_step_count"]) - report["physics_steps_at_reset"]
            if recorder is not None:
                assert native is not None
                recorder.close()
                report.update(native_frame_count=len(recorder.rows), actual_control_frames=len(recorder.rows),
                              native_success=bool(recorder.success))
                report["execution_accounting_valid"] = (
                    report["env_step_calls_submitted"] == report["env_step_calls_returned"] == len(recorder.rows)
                    and report.get("physics_steps_since_reset") == len(recorder.rows) * native.cfg.decimation)
        except (Exception, KeyboardInterrupt) as exc:
            evidence_failure(exc)
        try:
            export_video(output, report)
        except (Exception, KeyboardInterrupt) as exc:
            evidence_failure(exc)
        finally:
            report["teacher_inference_requests"] = budget.snapshot()["teacher_inference_requests"] - request_start
            close_after_persisting(output, report, started, (("environment", env), ("simulation_app", simulation_app)))
    return 0 if report["status"] == "online_execution_complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--service-config", type=Path, default=ROOT / "Sub2API")
    parser.add_argument("--model", required=True)
    parser.add_argument("--response-model", required=True)
    parser.add_argument("--protocol", choices=("chat_completions", "responses"), default="chat_completions")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--hold-frames", type=int, default=5)
    parser.add_argument("--translation-step", type=float, default=.025)
    parser.add_argument("--translation-clamp", type=float, default=.025)
    parser.add_argument("--request-timeout-s", type=float, default=35)
    parser.add_argument("--native-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    import math
    if (args.hold_frames < 1 or not all(math.isfinite(value) and value > 0 for value in
            (args.translation_step, args.translation_clamp, args.request_timeout_s))
            or args.request_timeout_s > 120):
        parser.error("control_parameters_must_be_finite_positive_and_request_timeout_at_most_120")
    if args.native_child:
        return native_run(args)
    from tacharness.first_collection_budget import FirstCollectionBudget
    budget = FirstCollectionBudget.open(args.budget)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reserved = budget.reserve_native_attempt(output=output)
    write_json(output / "reservation.json", {"attempt_number": reserved["ordinal"], "output": str(output),
                                            "reserved_at": datetime.now(timezone.utc).isoformat()})
    from run_p0_rollout import _failure_video
    _failure_video(output / "startup_diagnostic.mp4", "Reserved online teacher attempt", "No physical frames yet")
    environment = dict(os.environ, OMNI_KIT_ACCEPT_EULA="YES")
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--native-child"]
    with (output / "runtime.log").open("w") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=environment, cwd=ROOT, start_new_session=True)
        except OSError as exc:
            write_json(output / "report.json", {"status": "startup_failed", "error_type": type(exc).__name__,
                "native_success": False, "native_frame_count": 0, "video_kind": "diagnostic_only",
                "video": verify_video(output / "startup_diagnostic.mp4")})
            return 1
        try:
            process.wait(timeout=max(.01, budget.remaining_wall_s()))
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            write_json(output / "supervisor_stop.json", {"reason": "deadline_or_interrupt",
                       "exit_code": process.returncode, "graceful_evidence_only_s": 40})
    if (output / "supervisor_stop.json").exists() or process.returncode != 0:
        recovered = {"schema": "tacharness.arena.online-interruption.v1", "exit_code": process.returncode}
        report_path = output / "report.json"
        if report_path.exists():
            recovered["original_report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        try:
            export_video(output, recovered)
        except Exception as exc:
            recovered["media_recovery_error_type"] = type(exc).__name__
        recovered["native_frames_preserved"] = len(list((output / "native/frames").glob("frame_*.npz")))
        write_json(output / "interruption_receipt.json", recovered)
    if not (output / "report.json").exists():
        from run_p0_rollout import _failure_video
        _failure_video(output / "startup_diagnostic.mp4", "Online teacher startup failed", "No native evidence")
        write_json(output / "report.json", {"status": "startup_failed", "native_success": False,
                   "native_frame_count": 0, "video_kind": "diagnostic_only", "online_teacher": False,
                   "video": verify_video(output / "startup_diagnostic.mp4")})
    print(json.dumps({"output": str(output), "exit_code": process.returncode,
                      "budget": budget.snapshot()}, ensure_ascii=False))
    return int(process.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())
