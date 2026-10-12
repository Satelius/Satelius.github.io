#!/usr/bin/env python3
"""Run an explicitly selected implemented P0 lane and retain video evidence.

RoboSynChallenge replaces Door in the active scope via its Isaac migration. Historical Door profiles remain readable, never selected by default.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TACTILE_CONTRACT = {
    "embodiment": "tacumi_dm25pd04_v1",
    "replacement_asset": "assets/robots/isaaclab_franka_tacumi_dm25pd04.usda",
    "sensor_roots": ["/World/envs/env_0/Robot/Gripper/Tacumi/Link4", "/World/envs/env_0/Robot/Gripper/Tacumi/Link5"],
    "recording_fields": ["depth_uint16", "indent_uint16", "deformation_uint16", "shear_uint16", "mask"],
    "contact_gate": "contact_gripper.net_forces_w",
    "native_tactile": False,
}

RUNS = {
    "vitaforge": {
        "task": "vitaforge:lift_can:clean:episode_000",
        "command": [sys.executable, "tools/replay_external_tacumi_demo.py", "vitaforge", "--output-dir", "{run}/native"],
        "input": "inputs/datasets/vendor/vitaforge/byml_UniVTAC/lift_can/clean/0.hdf5",
        "tactile_contract": {
            **TACTILE_CONTRACT,
            "replacement_asset": "assets/robots/franka_tacumi_dm25pd04.usda",
            "sensor_roots": [f"/World/TacumiExternal/Robot/Gripper/Tacumi/{link}" for link in ("Link5", "Link4")],
            "contact_gate": "RigidContactView.get_contact_force_matrix filtered to can",
        },
    },
    "isaaclab_arena_franka_lift_object": {
        "task": "isaaclab_arena_franka:lift_object",
        "command": [sys.executable, "scripts/agentic/run_isaaclab_arena_smoke.py", "--arena-env", "lift_object", "--object", "dex_cube", "--output", "{run}/smoke.json", "--screenshot", "{run}/screenshot.png", "--video-path", "{run}/rollout.mp4", "--steps", "24", "--installed-isaaclab", "--no-offline-lightwheel-assets", "--embodiment", "franka_joint_pos", "--tacumi", "--record-tactile"],
        "input": "inputs/datasets/vendor/isaac-manipulation/arena_franka_lift_object/lift_object_model.pt",
    },
    "isaaclab_arena_franka_put_and_close_door": {
        "task": "isaaclab_arena_franka:put_and_close_door",
        "command": [sys.executable, "scripts/agentic/run_isaaclab_arena_smoke.py", "--arena-env", "franka_put_and_close_door", "--object", "dex_cube", "--output", "{run}/smoke.json", "--screenshot", "{run}/screenshot.png", "--video-path", "{run}/rollout.mp4", "--steps", "24", "--installed-isaaclab", "--no-offline-lightwheel-assets", "--embodiment", "franka_ik", "--tacumi", "--record-tactile"],
        "input": "inputs/datasets/vendor/isaac-manipulation/arena_franka_put_and_close_door/test_sequential_task_mimic_data_generation.hdf5",
    },
}

HISTORICAL_RUNS = {
    "isaaclab_arena_franka_put_and_close_door": RUNS.pop("isaaclab_arena_franka_put_and_close_door"),
}
RUNS["robosynchallenge"] = {
    "task": "robosynchallenge:mixer_operating",
    "command": [sys.executable, "scripts/agentic/replay_robosynchallenge_mixer_operating_isaac.py",
                "--headless", "--retain-frames", "--report", "{run}/smoke.json",
                "--video", "{run}/rollout.mp4", "--screenshot", "{run}/cover.png",
                "--session-dir", "{run}/native", "--frame-dir", "{run}/rgb_frames"],
    "input": "inputs/datasets/vendor/robosynchallenge/datasets/sim/mixer_operating/data/chunk-000/episode_000000.parquet",
    "policy_mode": "source_action_contact_retarget_isaac_migration",
    "tactile_contract": {
        "embodiment": "dual_cobotmagic_tacumi_dm25pd04",
        "replacement_asset": "assets/robots/robosyn_cobotmagic_dual_tacumi_dm25pd04.usda",
        "sensor_count": 4,
        "sensor_roots": [f"/World/RoboSynMixerOperating/CobotMagic/{arm}/Gripper/Tacumi/{link}"
                         for arm in ("LeftArm", "RightArm") for link in ("Link5", "Link4")],
        "recording_fields": TACTILE_CONTRACT["recording_fields"],
        "contact_gate": "RigidContactView filtered to left mixer / right beaker",
        "native_tactile": False,
        "note": "Requires independent native episode validation; not original DexSim execution.",
    },
}


def _failure_video(path: Path, title: str, detail: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2.0, (960, 540))
    if not writer.isOpened():
        raise RuntimeError(f"cannot open video writer: {path}")
    for index in range(4):
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        cv2.putText(frame, "TacHarness P0 rollout attempt", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        cv2.putText(frame, title[:70], (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (100, 220, 255), 2)
        cv2.putText(frame, "NO SIMULATION VIDEO - diagnostic only", (40, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 255), 2)
        cv2.putText(frame, detail[:95], (40, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 220, 220), 1)
        cv2.putText(frame, f"evidence frame {index + 1}/4", (40, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
        writer.write(frame)
    writer.release()


def _recorded_video(run_dir: Path, video: Path) -> int:
    """Keep available simulation frames, including interrupted attempts."""
    frames = sorted((run_dir / "native/frames").glob("frame_*.npz"))
    if not frames:
        return 0
    info = json.loads((run_dir / "native/meta/info.json").read_text())
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), float(info["fps"]), (960, 930))
    if not writer.isOpened():
        raise RuntimeError(f"cannot encode recorded frames: {video}")
    count = 0
    try:
        for path in frames:
            with np.load(path) as frame:
                scene = cv2.resize(frame["observation.images.rgb_dual_view"], (960, 540))
                tactile = cv2.resize(frame["observation.images.tacumi_tactile_composite"], (960, 390))
                panel = np.concatenate([scene, tactile], axis=0)
                writer.write(cv2.cvtColor(panel, cv2.COLOR_RGB2BGR))
                count += 1
    finally:
        writer.release()
    return count


def run_one(name: str, spec: dict, root: Path, *, python: str | None = None, timeout_s: float = 600) -> dict[str, object]:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=False)
    command = [part.format(run=str(run_dir)) for part in spec["command"]]
    if python is not None:
        command[0] = python
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src"), str(ROOT / "src/tac_infra")])
    git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    tracked_diff = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=ROOT)
    (run_dir / 'code.patch').write_bytes(tracked_diff)
    code_receipt = {'git_head': git_head, 'tracked_diff_sha256': hashlib.sha256(tracked_diff).hexdigest(),
                    'note': 'Tracked working-tree patch; teacher source is also archived in native/teacher_source.py when used.'}
    (run_dir / 'code_receipt.json').write_text(json.dumps(code_receipt, indent=2) + '\n')
    started = time.time()
    failure = ""
    with (run_dir / "stdout.log").open("w") as stdout, (run_dir / "stderr.log").open("w") as stderr:
        try:
            completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout,
                                       stderr=stderr, timeout=timeout_s, check=False)
            returncode = completed.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            returncode = -1
            failure = str(exc)
            stderr.write(failure + "\n")
    smoke_path = run_dir / "smoke.json"
    smoke = json.loads(smoke_path.read_text()) if smoke_path.exists() else {}
    failure = failure or smoke.get("error_message", "") or smoke.get("error", "")
    video = run_dir / "rollout.mp4"
    recorded_frames = (_recorded_video(run_dir, video) if name != "robosynchallenge"
                       else len(list((run_dir / "native/frames").glob("frame_*.npz"))))
    diagnostic = not video.is_file() or video.stat().st_size == 0
    if diagnostic:
        log = (run_dir / "stderr.log").read_text().strip()
        detail = failure or (log.splitlines()[-1] if log else f"exit code {returncode}; no simulation video")
        _failure_video(video, spec["task"], detail)
    failed = returncode != 0 or smoke.get("status") == "failed"
    input_path = ROOT / spec["input"]
    input_sha256 = None
    if input_path.is_file():
        with input_path.open("rb") as handle:
            input_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    tactile_audit = None
    native_root = run_dir / "native"
    if name != "robosynchallenge" and all((native_root / name).is_file() for name in ("summary.json", "trajectory.json")):
        sys.path.insert(0, str(ROOT))
        from tools.audit_p0_tactile_episode import audit

        tactile_audit = audit(native_root)
        (run_dir / "tactile_audit.json").write_text(json.dumps(tactile_audit, indent=2) + "\n")
    native_success = bool(tactile_audit and tactile_audit["task_success"])
    if name == "robosynchallenge" and "contact_force_trace" in smoke:
        from tools.audit_p0_robosyn_tactile import audit as audit_mixer

        tactile_audit = audit_mixer(run_dir)
        (run_dir / "tactile_audit.json").write_text(json.dumps(tactile_audit, indent=2) + "\n")
        native_success = bool(smoke.get("success") and smoke.get("verification_status") == "passed")
    report = {
        "schema": "tacharness.p0_rollout_attempt.v1",
        "source": name,
        "task": spec["task"],
        "status": "failed" if failed else "unverified",
        "failure": failure,
        "video_kind": "diagnostic" if diagnostic else "simulation_unverified",
        "input_sha256": input_sha256,
        "code_receipt": code_receipt,
        "recorded_frames": recorded_frames,
        "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "native_success": native_success,
        "native_tactile": bool(tactile_audit and tactile_audit["passed"]),
        "p0_complete": False,
        "policy_mode": spec.get("policy_mode") or (tactile_audit["policy_mode"] if tactile_audit else ("bc_observation_closed_loop" if "--policy-checkpoint" in command else "recorded_action_replay" if name == "vitaforge" else "zero_action_smoke")),
        "tactile_contract": spec.get("tactile_contract", TACTILE_CONTRACT),
        "exit_code": returncode,
        "command": command,
        "input": spec["input"],
        "video": str(video),
        "video_bytes": video.stat().st_size,
        "elapsed_s": round(time.time() - started, 3),
        "note": "A failure video is retained when native execution does not produce media; it is not simulator evidence.",
    }
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs" / "p0-rollouts")
    parser.add_argument("--only", choices=sorted(RUNS), action="append")
    parser.add_argument("--python", help="Native simulator Python; leaves the recording environment unchanged.")
    parser.add_argument("--timeout-s", type=float, default=600)
    parser.add_argument("--policy-checkpoint", type=Path)
    parser.add_argument("--arena-reference-policy", action="store_true")
    parser.add_argument("--arena-geometric-teacher", action="store_true")
    parser.add_argument("--arena-door-teacher", action="store_true")
    parser.add_argument("--arena-door-steps", type=int, default=1192)
    parser.add_argument("--target-only-tactile", action="store_true")
    parser.add_argument("--depth-diagnostics", action="store_true")
    parser.add_argument("--robosyn-beaker-rest-offset", type=float, default=0.0)
    parser.add_argument("--robosyn-full-pad-fov", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--tactile-render-passes", type=int, default=2)
    args = parser.parse_args()
    if not args.only:
        parser.error('Select --only explicitly: the updated third source is RoboSynChallenge, '
                     'Door is historical and no longer a P0 lane.')
    if 'isaaclab_arena_franka_put_and_close_door' in args.only:
        parser.error('Door is historical evidence, not the updated third P0 source (RoboSynChallenge).')
    root = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    root = root / datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S-%f")
    selected = args.only
    if args.robosyn_full_pad_fov:
        RUNS["robosynchallenge"]["command"].append("--tactile-full-pad-fov")
    if args.robosyn_beaker_rest_offset is not None:
        RUNS["robosynchallenge"]["command"].extend(["--beaker-rest-offset", str(args.robosyn_beaker_rest_offset)])
    RUNS["vitaforge"]["command"].extend(["--tactile-render-passes", str(args.tactile_render_passes)])
    if args.policy_checkpoint:
        RUNS["vitaforge"]["command"].extend(["--policy-checkpoint", str(args.policy_checkpoint.resolve())])
    if args.depth_diagnostics:
        RUNS["vitaforge"]["command"].append("--depth-diagnostics")
        RUNS["robosynchallenge"]["command"].append("--depth-diagnostics")
    if args.target_only_tactile:
        RUNS["vitaforge"]["command"].append("--target-only-tactile")
    if args.arena_reference_policy:
        spec = RUNS['isaaclab_arena_franka_lift_object']
        command = spec['command']
        command[command.index('--embodiment') + 1] = 'franka_ik'
        command[command.index('--steps') + 1] = '250'
        command.extend(['--reference-checkpoint', str((ROOT / spec['input']).resolve())])
    if args.arena_geometric_teacher:
        RUNS['isaaclab_arena_franka_lift_object']['input'] = 'src/tacharness/isaaclab/arena_lift_teacher.py'
        command = RUNS['isaaclab_arena_franka_lift_object']['command']
        command[command.index('--embodiment') + 1] = 'franka_ik'
        command[command.index('--steps') + 1] = '250'
        command.append('--geometric-lift-teacher')
    if args.arena_door_teacher:
        spec = HISTORICAL_RUNS['isaaclab_arena_franka_put_and_close_door']
        command = spec['command']
        command[command.index('--steps') + 1] = str(args.arena_door_steps)
        command.extend(['--door-scaffold', str((ROOT / spec['input']).resolve())])
    reports = [run_one(name, RUNS[name], root, python=args.python, timeout_s=args.timeout_s) for name in selected]
    summary = {"schema": "tacharness.p0_rollout_summary.v1", "tactile_contracts": {r["source"]: r["tactile_contract"] for r in reports}, "runs": reports, "native_success_count": sum(bool(r["native_success"]) for r in reports), "native_tactile_count": sum(bool(r["native_tactile"]) for r in reports)}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(r["status"] == "succeeded" and r["native_success"] for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
