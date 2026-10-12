"""One online decision owns one physical interval; uncertain execution stops."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import numpy as np


def execute_online_decision(
    *, images: dict, task: str, writer: Any, teacher: Any, interpreter: Any,
    recorder: Any, env: Any, budget: Any, snapshot_state: Callable,
    check_state: Callable, accounting: dict,
) -> dict:
    """Freeze the scene and history throughout HTTP, then execute once.

    Only images, task and executed movement history cross the teacher boundary.
    Native state is retained solely for guards and control, never in its prompt.
    """
    start = len(recorder.rows)
    history = list(writer.history)
    identity = writer.begin(images, history, start, start - 1 if start else None)
    directory = writer.decision_directory(identity)
    before = snapshot_state()
    before_path = directory / "http_state_before.npz"
    np.savez_compressed(before_path, **before)

    def guard() -> dict:
        receipt = check_state(before, snapshot_state())
        if list(writer.history) != history or len(recorder.rows) != start:
            raise RuntimeError("history_or_control_frame_changed_during_http")
        return receipt

    inference = teacher.decide(images=images, task=task, history=history,
                               output=directory / "inference", frozen_guard=guard)
    after = snapshot_state()
    state_check = guard()
    after_path = directory / "http_state_after.npz"
    np.savez_compressed(after_path, **after)
    freeze = {
        "verified": True, "state_check": state_check,
        "before_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
        "after_sha256": hashlib.sha256(after_path.read_bytes()).hexdigest(),
        "control_frame_before": start, "control_frame_after": len(recorder.rows),
        "history_before": history, "history_after": list(writer.history),
        "state_file": before_path.name, "after_state_file": after_path.name,
    }
    token = inference.get("token")
    writer.attach_inference(identity, directory / "inference", freeze, token)
    if inference["status"] != "ok":
        writer.complete(identity, start, start, status="interrupted",
                        failure_reason="service_interruption")
        return {"decision_id": identity, "token": None,
                "stop_reason": "service_interruption", "inference": inference}
    metadata = interpreter.begin(token)
    (directory / "interpreter.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    try:
        while interpreter.remaining_frames and len(recorder.rows) < 250 and not recorder.terminal:
            if budget.remaining_wall_s() <= 0:
                raise RuntimeError("first_collection_wall_budget_exhausted")
            action = interpreter.action()
            recorder.begin_step(action)
            accounting["env_step_calls_submitted"] += 1
            _, reward, _, _, _ = env.step(action)
            accounting["env_step_calls_returned"] += 1
            recorder.finish_step(reward)
    except BaseException:
        uncertain = (accounting["env_step_calls_submitted"] != accounting["env_step_calls_returned"]
                     or len(recorder.rows) != accounting["env_step_calls_returned"])
        writer.complete(identity, start, len(recorder.rows), status="interrupted",
                        failure_reason="execution_interrupted_no_retry",
                        execution_uncertain=uncertain,
                        evidence={"execution_uncertain": uncertain})
        raise
    writer.complete(identity, start, len(recorder.rows), evidence={
        "native_success": bool(recorder.success), "interpreter": metadata,
        "unissued_control_frames": interpreter.remaining_frames,
    })
    reason = ("native_terminal" if recorder.terminal else "teacher_done" if interpreter.done
              else "physical_budget" if len(recorder.rows) >= 250 else "continue")
    return {"decision_id": identity, "token": token, "stop_reason": reason,
            "inference": inference, "control_frame_start": start, "control_frame_end": len(recorder.rows)}
