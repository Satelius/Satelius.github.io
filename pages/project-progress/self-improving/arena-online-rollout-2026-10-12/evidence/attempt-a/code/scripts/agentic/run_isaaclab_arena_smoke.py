#!/usr/bin/env python3
"""Run an IsaacLab-Arena lab23 environment smoke with screenshot evidence."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from _isaac_gui import (
    apply_camera_view,
    capture_active_viewport,
    encode_png_sequence_to_mp4,
    parse_vector3,
    run_coroutine_with_timeout,
)


ROOT = Path(__file__).resolve().parents[2]
ARENA_ROOT = next(
    (candidate for candidate in (ROOT / "thirdparty" / "IsaacLab-Arena_lab23", ROOT / "thirdparty" / "IsaacLab-Arena", ROOT / "thirdparty" / "IsaacLab") if (candidate / "isaaclab_arena").is_dir()),
    ROOT / "thirdparty" / "IsaacLab-Arena_lab23",
)
LIGHTWHEEL_OFFLINE_PLACEHOLDER = (
    ROOT
    / "inputs"
    / "datasets"
    / "vendor"
    / "isaacsim_5_1_minimal"
    / "Isaac"
    / "Props"
    / "Blocks"
    / "DexCube"
    / "dex_cube_instanceable.usd"
)


def _jsonify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "detach") and hasattr(value, "cpu"):
        return value.detach().cpu().tolist()
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _display(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(_jsonify(payload), indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    tmp_path.replace(path)


def _add_pythonpaths(*, installed_isaaclab: bool = False) -> list[str]:
    paths = [ARENA_ROOT] if installed_isaaclab else [
        ARENA_ROOT,
        ROOT / "thirdparty" / "IsaacLab" / "source" / "isaaclab",
        ROOT / "thirdparty" / "IsaacLab" / "source" / "isaaclab_tasks",
        ROOT / "thirdparty" / "IsaacLab" / "source" / "isaaclab_assets",
    ]
    added: list[str] = []
    for path in reversed(paths):
        value = str(path)
        if path.exists() and value not in sys.path:
            sys.path.insert(0, value)
            added.append(_display(path))
    return list(reversed(added))


def _launcher_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        headless=bool(args.headless),
        enable_cameras=True,
        device=args.device,
        livestream=0,
        xr=False,
        offscreen_render=True,
        kit_args="",
        experience="",
        width=int(args.width),
        height=int(args.height),
        renderer="RaytracedLighting",
        display_options=3094,
        active_gpu=0,
        physics_gpu=0,
        portable=True,
        disable_fabric=False,
        seed=int(args.seed),
        num_envs=int(args.num_envs),
        env_spacing=30.0,
        enable_pinocchio=True,
        mimic=False,
        distributed=False,
        solve_relations=True,
        placement_seed=None,
        example_environment=args.arena_env,
        object=args.object,
        teleop_device=None,
        embodiment=args.embodiment,
        rl_training_mode=False,
    )


def _dry_run(args: argparse.Namespace, report: dict[str, Any]) -> int:
    imported = []
    for module_name in ("isaaclab_arena", "isaaclab_arena_environments"):
        module = importlib.import_module(module_name)
        imported.append({"module": module_name, "file": getattr(module, "__file__", "")})
    env_files = sorted((ARENA_ROOT / "isaaclab_arena_environments").glob("*_environment.py"))
    env_names = []
    for path in env_files:
        name = path.stem.removesuffix("_environment")
        if name == "lift_object":
            env_names.append("lift_object")
        else:
            env_names.append(name)
    env_path = ARENA_ROOT / "isaaclab_arena_environments" / f"{args.arena_env}_environment.py"
    report.update(
        {
            "status": "dry_run_ready" if env_path.is_file() else "failed",
            "imported_modules": imported,
            "available_environments": env_names,
            "arena_env_found": env_path.is_file(),
            "arena_env_path": _display(env_path),
            "note": "Dry-run intentionally avoids importing env CLI/policy modules because they require Kit modules before AppLauncher.",
        }
    )
    return 0 if report["status"] == "dry_run_ready" else 1


def _describe_stage(env: Any, search_terms: list[str]) -> dict[str, Any]:
    stage = getattr(getattr(getattr(env, "unwrapped", env), "scene", None), "stage", None)
    if stage is None:
        return {"ready": False, "reason": "stage_unavailable"}
    terms = [term.lower() for term in search_terms if term]
    matches: list[dict[str, str]] = []
    for prim in stage.Traverse():
        path = prim.GetPath().pathString
        if not terms or any(term in path.lower() for term in terms):
            matches.append({"path": path, "type": prim.GetTypeName()})
            if len(matches) >= 80:
                break
    return {
        "ready": True,
        "root_layer": str(stage.GetRootLayer().identifier),
        "matches": matches,
    }


def _selected_video_steps(total_steps: int, requested_count: int) -> set[int]:
    count = max(min(int(requested_count), max(int(total_steps), 0)), 0)
    if count <= 0:
        return set()
    if count == 1:
        return {max(int(total_steps) - 1, 0)}
    last = max(int(total_steps) - 1, 0)
    return {round(index * last / (count - 1)) for index in range(count)}


def _patch_unused_lightwheel_assets(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False}
    if not LIGHTWHEEL_OFFLINE_PLACEHOLDER.is_file():
        raise FileNotFoundError(LIGHTWHEEL_OFFLINE_PLACEHOLDER)

    from lightwheel_sdk.loader import object_loader

    def acquire_by_registry(**kwargs: Any) -> tuple[str, str, dict[str, Any]]:
        registry_names = kwargs.get("registry_name") or []
        object_name = str(kwargs.get("file_name") or (registry_names[0] if registry_names else "offline_placeholder"))
        return str(LIGHTWHEEL_OFFLINE_PLACEHOLDER), object_name, {
            "offline_placeholder": True,
            "reason": "unused class-level Lightwheel asset registration",
        }

    object_loader.acquire_by_registry = acquire_by_registry
    return {
        "enabled": True,
        "placeholder": _display(LIGHTWHEEL_OFFLINE_PLACEHOLDER),
        "scope": "unused class-level remote assets only; selected table, dex_cube, and franka remain native",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arena-env", default="lift_object")
    parser.add_argument("--object", default="dex_cube")
    parser.add_argument("--embodiment", default="franka")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--camera-eye", help="Override the task's scene camera eye")
    parser.add_argument("--camera-lookat", help="Override the task's scene camera target")
    parser.add_argument("--search-term", action="append", default=["Robot", "cube", "table", "Light"])
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--capture-timeout-s", type=int, default=180)
    parser.add_argument("--video-path", type=Path, default=None)
    parser.add_argument("--video-frame-dir", type=Path, default=None)
    parser.add_argument("--video-frame-count", type=int, default=12)
    parser.add_argument("--video-fps", type=float, default=8.0)
    parser.add_argument("--offline-lightwheel-assets", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--installed-isaaclab", action="store_true",
                        help="Use the locked environment wheel instead of the legacy IsaacLab submodule.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--record-tactile", action="store_true")
    parser.add_argument("--reference-checkpoint", type=Path)
    parser.add_argument("--geometric-lift-teacher", action="store_true")
    parser.add_argument("--teacher-translation-step", type=float, default=.08)
    parser.add_argument("--door-scaffold", type=Path)
    parser.add_argument("--tacumi", action="store_true", help="Experimental TacClaw embodiment; not a tactile rollout gate.")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    screenshot = args.screenshot if args.screenshot.is_absolute() else ROOT / args.screenshot
    video_path = None if args.video_path is None else (args.video_path if args.video_path.is_absolute() else ROOT / args.video_path)
    video_frame_dir = None if args.video_frame_dir is None else (
        args.video_frame_dir if args.video_frame_dir.is_absolute() else ROOT / args.video_frame_dir
    )
    from tacharness.runtime_ready import require_isaac_eula_acknowledgement

    require_isaac_eula_acknowledgement()
    os.environ.setdefault("ENABLE_CAMERAS", "1")
    added_paths = _add_pythonpaths(installed_isaaclab=args.installed_isaaclab)

    started = time.time()
    report: dict[str, Any] = {
        "schema": "agenticsim.isaaclab_arena_smoke.v0",
        "status": "started",
        "arena_root": _display(ARENA_ROOT),
        "installed_isaaclab": args.installed_isaaclab,
        "pythonpath_added": added_paths,
        "arena_env": args.arena_env,
        "object": args.object,
        "embodiment": args.embodiment,
        "steps_requested": int(args.steps),
        "num_envs": int(args.num_envs),
        "device": args.device,
        "screenshot": _display(screenshot),
    }
    _write_json(output, report)

    def checkpoint(status: str, **values: Any) -> None:
        report.update({"status": status, "elapsed_s": round(time.time() - started, 3), **values})
        _write_json(output, report)

    tactile_contract = None
    if args.dry_run:
        try:
            rc = _dry_run(args, report)
            report["elapsed_s"] = round(time.time() - started, 3)
            report["tactile_contract"] = tactile_contract
            _write_json(output, report)
            return rc
        except BaseException as exc:
            checkpoint("failed", error=repr(exc))
            return 1

    simulation_app = None
    env = None
    tactile_recorder = None
    try:
        launcher_args = _launcher_args(args)
        checkpoint("launching_app", launcher_args=vars(launcher_args))
        from isaaclab.app import AppLauncher

        app_launcher = AppLauncher(launcher_args)
        simulation_app = app_launcher.app
        checkpoint("app_launched")

        import gymnasium as gym
        import torch

        lightwheel_patch = _patch_unused_lightwheel_assets(bool(args.offline_lightwheel_assets))
        checkpoint("lightwheel_registration_patched", lightwheel_patch=lightwheel_patch)
        from tacharness.isaaclab.tacumi_arena import install_tacumi_franka_embodiments

        if args.tacumi:
            tactile_contract = install_tacumi_franka_embodiments()
            checkpoint("tacumi_embodiment_installed", tactile_contract=tactile_contract)
        from isaaclab_arena_environments.cli import get_arena_builder_from_cli

        arena_builder = get_arena_builder_from_cli(launcher_args)
        if args.installed_isaaclab:
            env_name, env_cfg, env_kwargs = arena_builder.build_registered()
        else:
            env_name, env_cfg = arena_builder.build_registered()
            env_kwargs = {}
        checkpoint("env_registered", env_name=env_name)
        env = gym.make(env_name, cfg=env_cfg, **env_kwargs)
        checkpoint("env_created", observation_space=str(env.observation_space), action_space=str(env.action_space))
        obs, reset_info = env.reset()
        checkpoint("env_reset", reset_info=_jsonify(reset_info), stage=_describe_stage(env, args.search_term))

        reference_policy = None
        if args.door_scaffold:
            if (args.arena_env != 'franka_put_and_close_door' or args.embodiment != 'franka_ik'
                    or args.reference_checkpoint or args.geometric_lift_teacher):
                raise ValueError('Door scaffold requires the Door/franka_ik task without another teacher')
            from tacharness.isaaclab.arena_door_teacher import ArenaDoorTeacher
            reference_policy = ArenaDoorTeacher(env, args.door_scaffold)
            obs = reference_policy.initial_observation
            checkpoint('door_seed_restored', seed_sha256=reference_policy.seed_sha256,
                       seed_episode=reference_policy.episode)

        camera_eye = parse_vector3(args.camera_eye) or tuple(env.unwrapped.cfg.viewer.eye)
        camera_lookat = parse_vector3(args.camera_lookat) or tuple(env.unwrapped.cfg.viewer.lookat)
        apply_camera_view(env, camera_eye, camera_lookat)
        checkpoint("camera_applied", camera_pose=[camera_eye, camera_lookat])

        if args.record_tactile:
            if not args.tacumi:
                raise ValueError('--record-tactile requires --tacumi')
            from tacharness.isaaclab.arena_tactile import ArenaTactileRecorder
            tactile_recorder = ArenaTactileRecorder(
                env, output.parent / 'native', args.arena_env, args.steps,
                camera_eye=camera_eye, camera_lookat=camera_lookat)
            checkpoint('tactile_recorder_ready')
        if args.door_scaffold:
            import inspect
            tactile_recorder.policy_mode = reference_policy.policy_mode
            tactile_recorder.policy_source_sha256 = reference_policy.source_sha256
            (tactile_recorder.output / 'teacher_source.py').write_bytes(
                Path(inspect.getfile(ArenaDoorTeacher)).read_bytes())
            _write_json(tactile_recorder.output / 'seed_receipt.json', {
                'source_sha256': reference_policy.seed_sha256, 'episode': reference_policy.episode,
                'state_restore_count': 1, 'later_object_pose_writes': False,
                'policy_mode': reference_policy.policy_mode,
                'source_frame_budget': len(reference_policy.targets)})
        if args.reference_checkpoint:
            if args.arena_env != 'lift_object' or args.embodiment != 'franka_ik':
                raise ValueError('Pinned reference policy requires lift_object with franka_ik')
            from tacharness.isaaclab.arena_reference_policy import ArenaLiftReferencePolicy
            reference_policy = ArenaLiftReferencePolicy(args.reference_checkpoint)
            if tactile_recorder is not None:
                tactile_recorder.policy_mode = 'arena_reference_ik_teacher'
                tactile_recorder.checkpoint_sha256 = reference_policy.sha256
            checkpoint('reference_policy_ready', reference_checkpoint_sha256=reference_policy.sha256)
        if args.geometric_lift_teacher:
            if args.reference_checkpoint or args.arena_env != 'lift_object' or args.embodiment != 'franka_ik':
                raise ValueError('Geometric lift teacher requires lift_object/franka_ik and no checkpoint')
            from tacharness.isaaclab.arena_lift_teacher import ArenaLiftTeacher
            reference_policy = ArenaLiftTeacher(env, translation_step=args.teacher_translation_step)
            tactile_recorder.policy_mode = reference_policy.policy_mode
            tactile_recorder.policy_source_sha256 = reference_policy.source_sha256
            import inspect
            (tactile_recorder.output / 'teacher_source.py').write_bytes(Path(inspect.getfile(ArenaLiftTeacher)).read_bytes())
            checkpoint('geometric_teacher_ready', policy_source_sha256=reference_policy.source_sha256,
                       teacher_translation_step=args.teacher_translation_step)
        step_rows = []
        if video_path is not None:
            video_path.parent.mkdir(parents=True, exist_ok=True)
            if video_frame_dir is None:
                video_frame_dir = video_path.parent / "frames" / video_path.stem
            video_frame_dir.mkdir(parents=True, exist_ok=True)
            for stale in video_frame_dir.glob("frame_*.png"):
                stale.unlink()
        selected_video_steps = _selected_video_steps(args.steps, args.video_frame_count)
        video_frame_captures: list[dict[str, Any]] = []
        for step_idx in range(max(int(args.steps), 0)):
            with torch.inference_mode():
                actions = (reference_policy.action(obs, env.unwrapped.device) if reference_policy else
                           torch.zeros(env.action_space.shape, device=torch.device(env.unwrapped.device)))
                if tactile_recorder is not None:
                    tactile_recorder.begin_step(actions, reference_policy.last_input if reference_policy else None)
                obs, reward, terminated, truncated, info = env.step(actions)
            if tactile_recorder is not None:
                tactile_recorder.finish_step(reward)
            if step_idx in {0, max(int(args.steps) - 1, 0)}:
                step_rows.append(
                    {
                        "step": step_idx,
                        "reward": _jsonify(reward),
                        "terminated": _jsonify(terminated),
                        "truncated": _jsonify(truncated),
                    }
                )
            simulation_app.update()
            if video_path is not None and video_frame_dir is not None and step_idx in selected_video_steps:
                apply_camera_view(env, camera_eye, camera_lookat)
                simulation_app.update()
                frame_path = video_frame_dir / f"frame_{len(video_frame_captures):05d}.png"
                run_coroutine_with_timeout(
                    simulation_app,
                    capture_active_viewport(
                        frame_path.resolve(),
                        warmup_frames=1,
                        timeout_s=float(args.capture_timeout_s),
                        prefer_new_viewport=True,
                        width=int(args.width),
                        height=int(args.height),
                        camera_eye=camera_eye,
                        camera_lookat=camera_lookat,
                    ),
                    timeout_s=float(args.capture_timeout_s),
                )
                video_frame_captures.append(
                    {
                        "step": int(step_idx),
                        "path": str(frame_path),
                        "size_bytes": frame_path.stat().st_size if frame_path.is_file() else 0,
                    }
                )
            if tactile_recorder is not None and tactile_recorder.terminal:
                break
        video_encode: dict[str, Any] = {}
        if video_path is not None and video_frame_dir is not None:
            video_encode = encode_png_sequence_to_mp4(video_frame_dir, video_path, fps=float(args.video_fps))
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        checkpoint(
            "capturing_screenshot",
            steps_completed=step_idx + 1 if args.steps > 0 else 0,
            capture_timeout_s=int(args.capture_timeout_s),
            screenshot_ready=False,
            screenshot_size_bytes=0,
        )
        run_coroutine_with_timeout(
            simulation_app,
            capture_active_viewport(
                screenshot.resolve(),
                warmup_frames=8,
                timeout_s=float(args.capture_timeout_s),
                prefer_new_viewport=True,
                width=int(args.width),
                height=int(args.height),
                camera_eye=camera_eye,
                camera_lookat=camera_lookat,
            ),
            timeout_s=float(args.capture_timeout_s),
        )
        screenshot_ready = screenshot.is_file()
        report.update(
            {
                "status": "captured",
                "elapsed_s": round(time.time() - started, 3),
                "env_name": env_name,
                "observation_space": str(env.observation_space),
                "action_space": str(env.action_space),
                "steps_completed": step_idx + 1 if args.steps > 0 else 0,
                "step_samples": step_rows,
                "stage": _describe_stage(env, args.search_term),
                "camera_pose": [camera_eye, camera_lookat],
                "screenshot_ready": screenshot_ready,
                "screenshot_size_bytes": screenshot.stat().st_size if screenshot_ready else 0,
                "video_path": str(video_path) if video_path is not None and video_encode.get("ready") else "",
                "video_frame_captures": video_frame_captures,
                "video_encode": video_encode,
            }
        )
        _write_json(output, report)
        return 0 if screenshot_ready else 1
    except BaseException as exc:
        traceback.print_exc()
        checkpoint(
            "failed",
            error=repr(exc),
            error_type=type(exc).__name__,
            error_message=str(exc),
            screenshot_ready=bool(screenshot.is_file()),
            screenshot_size_bytes=screenshot.stat().st_size if screenshot.is_file() else 0,
        )
        return 1
    finally:
        if tactile_recorder is not None:
            tactile_recorder.close()
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
        if simulation_app is not None:
            simulation_app.close()
        _write_json(output, report)


if __name__ == "__main__":
    raise SystemExit(main())
