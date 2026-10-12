#!/usr/bin/env python3
"""Create a portable, read-only presentation of the sealed online evidence.

No network, inference, native runtime, budget mutation, or source edits occur.
Run with the repository Python that provides numpy and Pillow. Existing outputs
are verified byte-for-byte instead of overwritten. Endpoint/key values are read
only for an in-memory negative leak check and are never emitted or retained.
"""
from __future__ import annotations

import argparse
import base64
import collections
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import numpy as np
from PIL import Image


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    repo = args.repository.resolve()
    stage = (args.source or repo / "outputs/collections/tacjev-first/online-resume-20261012T014737Z").resolve()
    out = Path(__file__).resolve().parent
    if out == stage or stage in out.parents:
        raise SystemExit("Destination must be separate from original evidence")
    sys.path.insert(0, str(repo / "src"))
    from tacharness.teacher_preflight import load_service_config

    config = load_service_config(repo / "Sub2API")
    parsed = urlsplit(config.base_url)
    private_bytes = tuple(v.encode() for v in (config.base_url, config.api_key, parsed.netloc, parsed.hostname) if v)
    entries: list[dict] = []
    sources_before: dict[Path, str] = {}

    def safe(data: bytes) -> None:
        if any(value in data for value in private_bytes):
            raise SystemExit("Private configuration match detected; output stopped without disclosing value")

    def write(relative: str, data: bytes) -> str:
        safe(data)
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise SystemExit("Refusing to replace a different generated artifact: " + relative)
        else:
            path.write_bytes(data)
        return relative

    def copied(path: Path, relative: str | None = None, *, purpose: str = "原件字节副本") -> str:
        data = path.read_bytes()
        src_hash = sha(data)
        sources_before[path] = src_hash
        target = relative or "evidence/" + str(path.relative_to(stage))
        write(target, data)
        entries.append({"path": target, "bytes": len(data), "sha256": src_hash,
                        "source": str(path.relative_to(repo)), "source_sha256": src_hash,
                        "copy_sha256": sha((out / target).read_bytes()), "kind": "exact_copy", "purpose": purpose})
        return target

    def derived(relative: str, data: bytes, *, source: str, source_hash: str, purpose: str) -> str:
        write(relative, data)
        entries.append({"path": relative, "bytes": len(data), "sha256": sha(data),
                        "source": source, "source_sha256": source_hash,
                        "copy_sha256": sha(data), "kind": "derived", "purpose": purpose})
        return relative

    for path in sorted(stage.glob("*.json")):
        copied(path)
    copied(stage / "README.md")
    copied(stage / "analyze_pair.py")
    for path in sorted((stage / "validation").glob("*")):
        if path.is_file():
            copied(path)
    for path in sorted((stage / "publication_code").rglob("*")):
        if path.is_file():
            copied(path)
    copied(repo / "GLOSSARY.md", "evidence/repository/GLOSSARY.md")
    copied(repo / "repo-docs/glossary.md", "evidence/repository/glossary.md")
    copied(repo / "docs/TACJEV_ROLLOUT_CONTRACT.md", "evidence/repository/TACJEV_ROLLOUT_CONTRACT.md")

    def unpack_request(request_path: Path, relative_prefix: str, inference: dict):
        body = load(request_path)
        display = copy.deepcopy(body)
        image_items = []
        for message in display["messages"]:
            if isinstance(message["content"], list):
                image_items.extend(item for item in message["content"] if item.get("type") == "image_url")
        assert len(image_items) == 3
        images = {}
        for item, name, short in zip(image_items, ["scene_rgb", "wrist_rgb", "tactile_mosaic_rgb"], ["scene", "wrist", "tactile"]):
            url = item["image_url"]["url"]
            assert url.startswith("data:image/png;base64,")
            data = base64.b64decode(url.split(",", 1)[1], validate=True)
            source_meta = inference["image_inputs"][name]
            assert sha(data) == source_meta["png_sha256"]
            pixels = np.asarray(Image.open(io.BytesIO(data)))
            assert list(pixels.shape) == source_meta["shape"]
            assert sha(pixels.tobytes()) == source_meta["array_sha256"]
            relative = f"assets/{relative_prefix}/{name}.png"
            derived(relative, data, source=str(request_path.relative_to(repo)), source_hash=sha(request_path.read_bytes()),
                    purpose="由真实请求dataURL解码；原PNG字节和数组哈希均核对")
            images[short] = relative
            item["image_url"]["url"] = f"[PNG bytes preserved at {relative}; sha256={sha(data)}]"
        system = "\n".join(m["content"] for m in body["messages"] if m["role"] == "system" and isinstance(m["content"], str))
        user = "\n".join(item["text"] for m in body["messages"] if m["role"] == "user" for item in m["content"] if item.get("type") == "text")
        return images, system, user, display

    preflight = stage / "teacher_inference_preflight"
    for path in sorted(preflight.glob("*.json")):
        copied(path)
    p_infer = load(preflight / "inference.json")
    p_images, p_system, p_user, p_request = unpack_request(preflight / "request.json", "preflight", p_infer)

    runs = []
    for identity, folder in [("A", "attempt-a"), ("B", "attempt-b")]:
        root = stage / folder
        report = load(root / "report.json")
        config = load(root / "interpreter.json")
        summary = load(root / "native/summary.json")
        trajectory = load(root / "native/trajectory.json")
        assert len(trajectory) == 250
        fps = summary["fps"]
        video = copied(root / "rollout_h264.mp4", f"assets/{identity}/rollout_h264.mp4", purpose="原生在线帧H264视频原件")
        initial_images = {short: copied(root / f"initial_{name}.png", f"assets/{identity}/initial_{name}.png")
                          for name, short in [("scene_rgb", "scene"), ("wrist_rgb", "wrist"), ("tactile_mosaic_rgb", "tactile")]}
        for path in sorted(root.glob("*.json")):
            copied(path)
        copied(root / "runtime.log")
        copied(root / "startup_diagnostic.mp4", f"assets/{identity}/startup_diagnostic.mp4", purpose="原生启动诊断媒体，不作在线执行帧证据")
        copied(root / "reset_state.npz")
        copied(root / "final_state.npz")
        for path in sorted((root / "code").rglob("*")):
            if path.is_file():
                copied(path)
        for path in sorted((root / "native").glob("*.json")):
            copied(path)
        for filename in ["manifest.json", "index.json"]:
            copied(root / "decisions" / filename)
        frames = [{"index": i, "timeS": i / fps, "afterTimeS": (i + 1) / fps, "positionUnit": "m", "tcpFrame": "robot_base", "cubeFrame": "world",
                   "tcp": row["control_tcp_pose_base_xyzw"][:3], "tcpPose": row["control_tcp_pose_base_xyzw"],
                   "cube": row["rigid_object_poses_xyzw"]["dex_cube"][:3], "cubePose": row["rigid_object_poses_xyzw"]["dex_cube"],
                   "action": row["target_action"], "contact": row["physical_contact"], "forceN": row["contact_force_n"],
                   "jointTarget": row["joint_position_target"], "jointVelocity": row["robot_joint_velocity"],
                   "terminal": row["terminal_before_reset"], "renderFrozen": row["render_frozen_check"]["unchanged"]}
                  for i, row in enumerate(trajectory)]
        decisions = []
        for index, directory in enumerate(sorted((root / "decisions").glob("decision_*"))):
            pre, selected, finish, interpreter, inference = [load(directory / path) for path in ["pre.json", "selected.json", "finish.json", "interpreter.json", "inference/inference.json"]]
            raw_links = {}
            for key, filename in [("pre", "pre.json"), ("selected", "selected.json"), ("finish", "finish.json"), ("interpreter", "interpreter.json"),
                                  ("request", "inference/request.json"), ("inference", "inference/inference.json"),
                                  ("httpBefore", "http_state_before.npz"), ("httpAfter", "http_state_after.npz")]:
                raw_links[key] = copied(directory / filename)
            raw_links["responses"] = [copied(path) for path in sorted((directory / "inference").glob("response-*.json"))]
            images, system, user, display = unpack_request(directory / "inference/request.json", f"{identity}/{directory.name}", inference)
            assert sha((directory / "inference/request.json").read_bytes()) == inference["request_sha256"]
            start, end = finish["frame_start"], finish["frame_end_exclusive"]
            initial = np.array(interpreter["initial_tcp_position_base_m"], dtype=float)
            after = np.array(trajectory[end - 1]["control_tcp_pose_base_xyzw"][:3], dtype=float)
            delta = after - initial
            direction = config["token_directions_base"].get(finish["token"])
            projection = float(delta @ np.array(direction)) if direction else None
            cross = float(np.linalg.norm(delta - projection * np.array(direction))) if direction else None
            decisions.append({"id": directory.name, "index": index, "token": finish["token"], "history": pre["recent_movement_tokens"],
                              "observationBoundary": pre["observation_control_frame"], "observationSourceFrame": pre["source_physical_frame_index"],
                              "frameStart": start, "frameEnd": end, "physicalStartS": start / fps, "physicalEndS": end / fps,
                              "waitS": inference["elapsed_s"], "httpAttempts": inference["attempts"], "images": images,
                              "systemPrompt": system, "userText": user, "requestText": json.dumps(display, ensure_ascii=False, indent=2),
                              "messages": display["messages"], "requestMeta": {k: v for k, v in display.items() if k != "messages"},
                              "responseText": "\n\n".join((directory / "inference" / Path(path).name).read_text(encoding="utf-8") for path in raw_links["responses"]),
                              "responseReceipts": [load(directory / "inference" / Path(path).name) for path in raw_links["responses"]],
                              "pre": pre, "selected": selected, "finish": finish, "interpreter": interpreter,
                              "target": interpreter["target_position_base_m"], "actualDelta": delta.tolist(), "actualAfter": after.tolist(),
                              "positionUnit": "m", "positionFrame": "robot_base", "requestTextIsDisplayAbbreviation": True,
                              "projectionMm": None if projection is None else 1000 * projection, "crossMm": None if cross is None else 1000 * cross,
                              "knownWrong": identity == "B" and directory.name == "decision_000011", "rawLinks": raw_links})
        assert len(decisions) == 50 and sum(len(d["httpAttempts"]) for d in decisions) == report["teacher_inference_requests"]
        runs.append({"id": identity, "name": f"{identity}：{1000*config['translation_step_m']:g} mm / hold{config['hold_frames']}",
                     "report": report, "interpreter": config, "summary": summary, "video": video, "initialImages": initial_images,
                     "decisions": decisions, "frames": frames, "tokenCounts": dict(collections.Counter(d["token"] for d in decisions)),
                     "totalWaitS": sum(d["waitS"] for d in decisions), "rawLinks": {"report": f"evidence/{folder}/report.json",
                      "trajectory": f"evidence/{folder}/native/trajectory.json", "summary": f"evidence/{folder}/native/summary.json",
                      "interpreter": f"evidence/{folder}/interpreter.json", "runtime": f"evidence/{folder}/runtime.log",
                      "codeReceipt": f"evidence/{folder}/code_receipt.json", "tokenReceipts": f"evidence/{folder}/token_receipts.json"}})

    # Keep derived UI small; full comparison/tactile frame hashes remain in the exact-copy evidence.
    comparison = load(stage / "comparison.json")
    for identity in ["A", "B"]:
        comparison[identity]["tactile"].pop("frame_evidence", None)
    mapping = {"frame": "robot_base", "quaternionOrder": "xyzw", "directionMap": runs[0]["interpreter"]["token_directions_base"],
               "tokens": [*runs[0]["interpreter"]["token_directions_base"], "GRASP", "RELEASE", "DONE"],
               "GRASP": {"gripperTarget": -1, "description": "固定当前TCP位置为目标，闭合手指；仍保持声明的朝下姿态并执行5控制帧"},
               "RELEASE": {"gripperTarget": 1, "description": "固定当前TCP位置为目标，打开手指；保持声明的朝下姿态并执行5控制帧"},
               "DONE": {"frames": 0, "description": "停止本次attempt，不等于原生任务成功"},
               "translationFormula": "target = TCP_before + direction * step；每帧servo_translation = clip(target - TCP_now, -clamp, +clamp) / 0.5",
               "rotationFormula": "servo_rotation = clip(pose_error(TCP_quaternion_now, fixed_down_xyzw), -0.08, +0.08) / 0.5",
               "nativeActionOrder": ["dx", "dy", "dz", "rx", "ry", "rz", "gripper"],
               "source": "evidence/attempt-b/code/src/tacharness/isaaclab/arena_meta_actions.py",
               "holdFrames": 5, "controlHz": 50, "physicsHz": 200,
               "stepDoesNotGuaranteeTravel": True, "calibration": "uncalibrated"}
    top = {"meta": {"schema": "tacharness.arena.rollout-explainer.v1", "date": "2026-10-12", "timezone": "Asia/Shanghai",
                    "sourceStage": str(stage.relative_to(repo)), "title": "Arena 在线教师：两次 rollout 的逐步回放与诊断",
                    "requestBoundary": "每次决策均为独立HTTP请求，messages只含一条system和一条user；服务端隐藏状态未知，不作断言。",
                    "responseBoundary": "仅有已保存的脱敏响应收据、合法token、服务声明model与原HTTP响应正文SHA256；未留存完整原始响应JSON或解释/思维过程，不能还原。",
                    "imageBoundary": "300张模型实际PNG输入从原request dataURL解码，保留PNG字节并核对PNG SHA、像素数组SHA；不是视频截图。",
                    "requestDisplayBoundary": "requestText和messages保留文字原文，但图片dataURL长体用带路径/哈希的展示占位替换；rawLinks.request为包含全部base64 PNG的实际完整JSON原文。",
                    "imageSizes": {"scene": [640, 360], "wrist": [640, 360], "tactile": [384, 576]},
                    "units": {"target": "m, robot_base", "actualDelta": "m, robot_base", "frameTcp": "m, robot_base", "frameCube": "m, world"},
                    "sameStateDifferentRgb": "开局16个物理状态字段相同，但A/B初始场景和腕部RGB哈希不相同，不声称像素输入完全一致。",
                    "frameBoundary": "frames来自250条真实native trajectory行；位置/动作供审计，不是教师输入。完整原生帧NPZ仍保留在源阶段，便携包不重复复制其RGB/触觉巨量数组。",
                    "runBudgetMutation": False, "newNetworkRequests": 0, "newNativeStarts": 0, "trainSamples": 0},
           "budget": load(stage / "budget_ledger.json"), "acceptance": load(stage / "phase_acceptance.json"),
           "teacherIdentity": load(stage / "teacher_identity.json"), "comparison": comparison,
           "diagnosis": load(stage / "diagnosis_before_b_v2.json"), "initialPair": load(stage / "initial_pair_check.json"),
           "emptyClose": load(stage / "empty_close_audit.json"), "knownError": load(stage / "known_error_receipt.json"),
           "verification": load(stage / "independent_verification.json"), "readback": load(stage / "dataengine_readback.json"),
           "checks": load(stage / "validation/checks.json"), "mapping": mapping,
           "preflight": {"inference": p_infer, "images": p_images, "systemPrompt": p_system, "userText": p_user,
                         "requestText": json.dumps(p_request, ensure_ascii=False, indent=2), "requestLink": "evidence/teacher_inference_preflight/request.json"},
           "runs": runs,
           "evidence": [{"title": title, "path": path} for title, path in [
               ("首批验收", "evidence/phase_acceptance.json"), ("事前诊断v2", "evidence/diagnosis_before_b_v2.json"),
               ("A/B配对比较", "evidence/comparison.json"), ("开局16字段一致", "evidence/initial_pair_check.json"),
               ("空闭合事实审计", "evidence/empty_close_audit.json"), ("已知错误独立收据", "evidence/known_error_receipt.json"),
               ("DataEngine实际回读", "evidence/dataengine_readback.json"), ("35项独立核验", "evidence/independent_verification.json"),
               ("闭合预算台账", "evidence/budget_ledger.json"), ("原件保护检查", "evidence/validation/checks.json"),
               ("相关测试日志", "evidence/validation/pytest_targeted.log"), ("全仓CPU检查日志", "evidence/validation/pytest_full.log"),
               ("Standards/Spec审查", "evidence/validation/code_review.md"), ("合同原文", "evidence/repository/TACJEV_ROLLOUT_CONTRACT.md")]]}
    js = "window.ROLLOUT_DATA = " + json.dumps(top, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n"
    derived("data.js", js.encode("utf-8"), source=str(stage.relative_to(repo)), source_hash=sha((stage / "phase_acceptance.json").read_bytes()),
            purpose="只读汇总；可file://打开，无fetch和外部CDN依赖")
    for source, before_hash in sources_before.items():
        assert sha(source.read_bytes()) == before_hash, "Source evidence changed during copy"
    manifest = {"schema": "tacharness.arena.explainer-evidence-manifest.v1", "created_at": datetime.now(timezone.utc).isoformat(),
                "source_stage": str(stage.relative_to(repo)), "entries": entries,
                "checks": {"source_hashes_unchanged": True, "exact_copies_verified": True,
                           "request_png_hashes_and_arrays_verified": True, "decision_count": 100,
                           "actual_request_count_with_retries": 102, "model_input_png_count": 300,
                           "preflight_png_count": 3, "native_frames": 500,
                           "private_values_scanned_in_memory": True, "private_value_match_count": 0,
                           "new_requests": 0, "native_starts": 0, "budget_modified": False},
                "boundaries": top["meta"], "total_evidence_bytes": sum(entry["bytes"] for entry in entries)}
    write("evidence_manifest.json", dump(manifest))
    print(json.dumps({"output": str(out), "evidence_files": len(entries), "total_evidence_bytes": manifest["total_evidence_bytes"],
                      "data_js_bytes": len(js.encode()), "checks": manifest["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
