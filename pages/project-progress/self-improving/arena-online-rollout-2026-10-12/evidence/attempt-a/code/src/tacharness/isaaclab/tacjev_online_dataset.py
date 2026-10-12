"""Publish a separate, fail-closed TacJev decision dataset and replay catalog."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Sequence

import numpy as np

from .arena_online_records import (
    CONTROL_SOURCE, read_json, read_online_decision_records, sha256, write_json,
    validate_online_decision_records,
)

SCHEMA = "tacharness.tacjev_online_dataset.v1"
ADOPTION_VERSION = "native-success-bilateral-tactile-causal-known-error-excluded-v1"


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("dataset_paths_must_be_repository_relative")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    if not path.is_file():
        raise ValueError("published_evidence_missing")
    return path


def _media(source: Path, destination: Path, timestamps: list[float], fps: float) -> dict[str, Any]:
    import cv2

    subprocess.run(["ffmpeg", "-v", "error", "-n", "-i", str(source), "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(destination)],
                   check=True, capture_output=True)
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
                             "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(destination)],
                            check=True, capture_output=True, text=True)
    pts = [float(row["best_effort_timestamp_time"]) for row in json.loads(result.stdout)["frames"]]
    capture = cv2.VideoCapture(str(destination))
    count = 0
    while True:
        available, frame = capture.read()
        if not available:
            break
        if count == 0:
            if not cv2.imwrite(str(destination.parent / "poster.png"), frame):
                raise ValueError("poster_write_failed")
        count += 1
    capture.release()
    if count == 0 or count != len(pts):
        raise ValueError("all_attempt_media_must_fully_decode")
    # Zero-physical-frame interruption videos are retained as diagnostic media.
    if timestamps and (len(pts) != len(timestamps) or not np.allclose(pts, timestamps, atol=1e-5, rtol=0)):
        raise ValueError("published_video_must_match_each_native_physical_frame")
    return {"decoded_frames": count, "fps": fps, "native_timeline_verified": bool(timestamps),
            "max_pts_error_s": float(np.max(np.abs(np.asarray(pts) - timestamps))) if timestamps else None,
            "sha256": sha256(destination)}


def _audit(native: Path) -> dict[str, Any]:
    from tools.audit_p0_tactile_episode import audit

    try:
        return audit(native)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"schema": "tacharness.online_tactile_audit_failure.v1", "passed": False,
                "task_success": False, "failure_type": type(exc).__name__}


def _publish_run(run: Path, destination: Path, repository_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    run.resolve().relative_to((repository_root / "outputs").resolve())
    report = read_json(run / "report.json")
    summary = read_json(run / "native/summary.json")
    if (report.get("control_source") != CONTROL_SOURCE or report.get("online_teacher") is not True
            or summary.get("source") != "isaaclab_arena_franka" or summary.get("task_id") != "lift_object"):
        raise ValueError("publisher_requires_declared_Arena_online_teacher_attempt")
    destination.mkdir()
    native = run / "native"
    frames = sorted((native / "frames").glob("frame_*.npz"))
    if len(frames) != summary["frame_count"] or report.get("native_frame_count") != len(frames):
        raise ValueError("report_native_frame_count_mismatch")
    accounting_valid = (report.get("env_step_calls_submitted") == report.get("env_step_calls_returned") == len(frames)
                        and report.get("physics_steps_since_reset") == len(frames) * 4
                        and report.get("actual_control_frames") == len(frames)
                        and report.get("execution_accounting_valid") is True)
    causal = validate_online_decision_records(run / "decisions", native_frame_count=len(frames))
    samples = read_online_decision_records(run / "decisions", native_frame_count=len(frames)) if causal["valid"] else []
    if samples:
        declared = read_json(run / "decisions/manifest.json")
        if any(report.get(key) != declared[key] for key in ("teacher_model", "observation_version", "interpreter_version")):
            raise ValueError("online_report_versions_or_model_do_not_match_actual_decisions")
    tactile = _audit(native)
    write_json(destination / "tactile_audit.json", tactile)
    rows: dict[str, list[Any]] = {"timestamp": [], "observation.state": [], "action": []}
    native_hashes = []
    for path in frames:
        with np.load(path, allow_pickle=False) as frame:
            for key in rows:
                rows[key].append(np.asarray(frame[key]).reshape(-1).tolist())
        native_hashes.append({"path": _relative(path, repository_root), "sha256": sha256(path)})
    timestamps = [row[0] for row in rows["timestamp"]]
    fps = float(summary["fps"])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("native_fps_must_be_positive")
    source_media = run / "rollout_h264.mp4"
    if not source_media.is_file():
        source_media = run / "rollout.mp4"
    checked_media = _media(source_media, destination / "replay.mp4", timestamps, fps)
    checked_media["path"] = _relative(destination / "replay.mp4", repository_root)
    feature_info = read_json(native / "meta/info.json") if frames else {"features": {}}
    series = []
    for key, label in (("observation.state", "机器人状态"), ("action", "实际连续动作")):
        if frames:
            names = feature_info["features"][key]["names"]
            if any(len(row) != len(names) for row in rows[key]):
                raise ValueError("native_numeric_feature_names_mismatch")
            series.append({"id": key, "label": label, "names": names,
                           "units": ["native_contract"] * len(names), "values": rows[key]})
    write_json(destination / "series.json", {"schema": "tacharness.series.v1", "label": "在线教师实际控制",
        "fps": fps, "frame_count": len(frames), "timestamps": timestamps, "series": series,
        "metadata": {"control_source": CONTROL_SOURCE, "online_teacher": True, "student_evaluation": False}})
    native_success = report.get("native_success") is True and summary.get("success") is True
    execution_complete = (report.get("status") == "online_execution_complete"
                          and all(not sample["execution"]["execution_uncertain"] for sample in samples))
    positive = bool(native_success and tactile.get("passed") is True and tactile.get("task_success") is True
                    and causal["valid"] and samples and checked_media["native_timeline_verified"]
                    and accounting_valid and execution_complete)
    published_samples = []
    for sample in samples:
        decision_id = sample["decision_id"]
        decision = run / "decisions" / decision_id
        execution = sample["execution"]
        selected = sample["audit"]["selected"]
        mask = bool(positive and execution["status"] == "completed" and not execution["execution_uncertain"]
                    and not execution["known_wrong"] and sample["token"] is not None)
        row = {"episode_id": run.name, "decision_id": decision_id, "token": sample["token"],
               "task": sample["visible_observation"]["task"],
               "recent_movement_tokens": sample["visible_observation"]["recent_movement_tokens"],
               "images_file": _relative(decision / "images.npz", repository_root),
               "images_sha256": sha256(decision / "images.npz"), "images": sample["audit"]["images"],
               "frame_start": execution["frame_start"], "frame_end_exclusive": execution["frame_end_exclusive"],
               "observation_control_frame": sample["audit"]["observation_control_frame"],
               "inference_file": _relative(decision / selected["inference_file"], repository_root) if selected else None,
               "inference_sha256": selected["inference_sha256"] if selected else None,
               "observation_version": sample["audit"]["observation_version"],
               "interpreter_version": sample["audit"]["interpreter_version"],
               "teacher_model": sample["audit"]["teacher_model"], "known_wrong": execution["known_wrong"],
               "positive_demonstration": positive, "train_action_mask": mask,
               "adoption_version": ADOPTION_VERSION, "status": execution["status"]}
        published_samples.append(row)
    with (destination / "samples.jsonl").open("x", encoding="utf-8") as handle:
        for row in published_samples:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    evidence = {"schema": "tacharness.tacjev_online_publication_episode.v1", "episode_id": run.name,
        "native_run": _relative(run, repository_root), "native_success": native_success,
        "positive_demonstration": positive, "adoption_version": ADOPTION_VERSION,
        "tactile_passed": tactile.get("passed") is True, "causal_readback": causal,
        "execution_accounting_valid": accounting_valid,
        "execution_complete": execution_complete,
        "media": checked_media, "native_frames": len(frames), "native_frame_evidence": native_hashes,
        "attempt_report_sha256": sha256(run / "report.json"),
        "native_summary_sha256": sha256(native / "summary.json"),
        "decision_index_sha256": sha256(run / "decisions/index.json") if (run / "decisions/index.json").is_file() else None,
        "samples_file": _relative(destination / "samples.jsonl", repository_root),
        "samples_sha256": sha256(destination / "samples.jsonl"),
        "tactile_audit_file": _relative(destination / "tactile_audit.json", repository_root),
        "tactile_audit_sha256": sha256(destination / "tactile_audit.json"),
        "raw_record_adoption_modified": False, "student_training_run": False}
    write_json(destination / "report.json", evidence)
    entry = {"id": "online-" + run.name, "name": "Arena 在线教师 · " + run.name,
        "dataset_id": "tacjev-online-first", "suite_id": "arena-online-collection", "group_id": "isaaclab",
        "view_id": "data", "task": "lift_object", "kind": "online_teacher_collection", "episode_count": 1,
        "status": "positive_demonstration" if positive else "diagnostic", "source": "isaaclab_arena_franka",
        "report": _relative(destination / "report.json", repository_root),
        "metadata_fields": {"控制来源": CONTROL_SOURCE, "合格示范": str(positive), "学生评测": "未执行"},
        "videos": [{"path": _relative(destination / "replay.mp4", repository_root),
                    "poster_path": _relative(destination / "poster.png", repository_root),
                    "series_path": _relative(destination / "series.json", repository_root) if frames else None,
                    "report_path": _relative(destination / "report.json", repository_root),
                    "stream_id": "rgb_tactile_panel", "stream_label": "在线教师 RGB / 触觉",
                    "episode_index": 0, "seed": report.get("seed"), "fps": fps,
                    "frame_count": checked_media["decoded_frames"], "native_frame_count": len(frames),
                    "duration_s": checked_media["decoded_frames"] / fps,
                    "record_source": CONTROL_SOURCE, "diagnostic_only": not bool(frames)}]}
    return entry, published_samples, evidence


def publish_online_collection(runs: Sequence[Path], destination: Path, *, repository_root: Path | None = None) -> dict[str, Any]:
    from tacharness.data_engine.contracts import build_catalog_envelope, catalog_envelope_to_legacy
    from tacharness.paths import REPOSITORY_ROOT

    root = Path(repository_root or REPOSITORY_ROOT).resolve()
    destination = Path(destination).resolve()
    destination.relative_to(root / "outputs")
    if not runs or len({Path(run).resolve() for run in runs}) != len(runs):
        raise ValueError("publication_requires_unique_attempts")
    if len({Path(run).name for run in runs}) != len(runs):
        raise ValueError("publication_episode_names_must_be_unique")
    destination.mkdir(parents=True, exist_ok=False)
    entries, episodes, sample_count, training_count = [], [], 0, 0
    for run in runs:
        entry, samples, evidence = _publish_run(Path(run).resolve(), destination / Path(run).name, root)
        entries.append(entry)
        episodes.append(evidence)
        sample_count += len(samples)
        training_count += sum(sample["train_action_mask"] for sample in samples)
    manifest = {"schema": SCHEMA, "adoption_version": ADOPTION_VERSION, "episodes": episodes,
                "diagnostic_episodes": len(episodes), "positive_episodes": sum(ep["positive_demonstration"] for ep in episodes),
                "sample_count": sample_count, "training_sample_count": training_count,
                "model_visible_fields": ["scene_rgb", "wrist_rgb", "tactile_mosaic_rgb", "task", "recent_movement_tokens"],
                "raw_record_adoption_modified": False, "student_training_run": False}
    write_json(destination / "manifest.json", manifest)
    envelope = build_catalog_envelope(catalog_id=destination.name,
        datasets=[{"id": "tacjev-online-first", "manifest_path": _relative(destination / "manifest.json", root),
                   "sample_count": sample_count, "training_sample_count": training_count}],
        suites=[{"id": "arena-online-collection"}], groups=[{"id": "isaaclab"}], entries=entries,
        views=[{"id": "data", "label": "在线教师数据", "order": 10}],
        metadata={"dataset_manifest": _relative(destination / "manifest.json", root), "student_training_run": False})
    write_json(destination / "canonical.json", envelope)
    write_json(destination / "catalog.json", catalog_envelope_to_legacy(envelope, schema="agenticsim.media_catalog.supplement.v1"))
    # Dataset readback is required before returning any adoption conclusion.
    read_online_dataset(destination, repository_root=root)
    return {**manifest, "manifest": _relative(destination / "manifest.json", root),
            "catalog": _relative(destination / "catalog.json", root), "manifest_sha256": sha256(destination / "manifest.json")}


def read_online_dataset(dataset: Path, *, training_only: bool = False,
                        repository_root: Path | None = None) -> list[dict[str, Any]]:
    from tacharness.paths import REPOSITORY_ROOT

    root = Path(repository_root or REPOSITORY_ROOT).resolve()
    manifest = read_json(Path(dataset) / "manifest.json")
    if manifest.get("schema") != SCHEMA or manifest.get("adoption_version") != ADOPTION_VERSION:
        raise ValueError("published_online_dataset_schema_required")
    output = []
    for episode in manifest["episodes"]:
        run = (root / episode["native_run"]).resolve()
        run.relative_to(root / "outputs")
        for path, expected in ((run / "report.json", episode["attempt_report_sha256"]),
                               (run / "native/summary.json", episode["native_summary_sha256"])):
            if sha256(path) != expected:
                raise ValueError("published_native_evidence_hash_mismatch")
        if episode["decision_index_sha256"] is not None:
            if sha256(run / "decisions/index.json") != episode["decision_index_sha256"]:
                raise ValueError("published_decision_index_hash_mismatch")
        original = read_online_decision_records(run / "decisions", native_frame_count=episode["native_frames"]) if episode["causal_readback"]["valid"] else []
        for frame in episode["native_frame_evidence"]:
            if sha256(_file(root, frame["path"])) != frame["sha256"]:
                raise ValueError("published_native_frame_hash_mismatch")
        samples_file = _file(root, episode["samples_file"])
        if sha256(samples_file) != episode["samples_sha256"]:
            raise ValueError("published_samples_hash_mismatch")
        audit_file = _file(root, episode["tactile_audit_file"])
        if sha256(audit_file) != episode["tactile_audit_sha256"]:
            raise ValueError("published_tactile_audit_hash_mismatch")
        audit = read_json(audit_file)
        report, summary = read_json(run / "report.json"), read_json(run / "native/summary.json")
        count = episode["native_frames"]
        accounting = (report.get("env_step_calls_submitted") == report.get("env_step_calls_returned") == count
                      and report.get("actual_control_frames") == count and report.get("native_frame_count") == count
                      and report.get("physics_steps_since_reset") == count * 4
                      and report.get("execution_accounting_valid") is True)
        complete = (report.get("status") == "online_execution_complete"
                    and all(not sample["execution"]["execution_uncertain"] for sample in original))
        if sha256(_file(root, episode["media"]["path"])) != episode["media"]["sha256"]:
            raise ValueError("published_media_hash_mismatch")
        can_adopt = (report.get("native_success") is True and summary.get("success") is True and audit.get("passed") is True
                     and audit.get("task_success") is True and episode["causal_readback"]["valid"]
                     and episode["media"]["native_timeline_verified"] is True
                     and accounting and complete and bool(original))
        if bool(episode["positive_demonstration"]) != bool(can_adopt):
            raise ValueError("published_adoption_gate_mismatch")
        published = [json.loads(line) for line in samples_file.read_text().splitlines() if line.strip()]
        if len(published) != len(original):
            raise ValueError("published_sample_count_mismatch")
        for sample, source in zip(published, original):
            if (sample["token"] != source["token"] or sample["decision_id"] != source["decision_id"]
                    or sample["task"] != source["visible_observation"]["task"]
                    or sample["recent_movement_tokens"] != source["visible_observation"]["recent_movement_tokens"]
                    or sample["frame_start"] != source["execution"]["frame_start"]
                    or sample["frame_end_exclusive"] != source["execution"]["frame_end_exclusive"]
                    or sample["known_wrong"] != source["execution"]["known_wrong"]
                    or any(sample[key] != source["audit"][key] for key in (
                        "observation_version", "interpreter_version", "teacher_model"))):
                raise ValueError("published_sample_is_not_original_causal_label")
            valid_mask = bool(can_adopt and source["execution"]["status"] == "completed"
                              and not source["execution"]["execution_uncertain"]
                              and not source["execution"]["known_wrong"] and source["token"] is not None)
            if sample["train_action_mask"] is not valid_mask:
                raise ValueError("published_training_mask_invalid")
            if sha256(_file(root, sample["images_file"])) != sample["images_sha256"]:
                raise ValueError("published_visible_observation_hash_mismatch")
            if sample["inference_file"] and sha256(_file(root, sample["inference_file"])) != sample["inference_sha256"]:
                raise ValueError("published_inference_hash_mismatch")
            if not training_only or valid_mask:
                output.append({**sample, "visible_observation": source["visible_observation"]})
    return output
