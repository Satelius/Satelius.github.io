"""Causal online teacher records, separate from every offline record schema.

Raw records are never training adoption records. The publisher creates a new
view only after independent native, tactile, media and causal validation.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np

from .arena_decision_records import IMAGE_NAMES, MOVEMENT_TOKENS, TOKENS

SCHEMA = "tacharness.arena.online_decision_records.v1"
CONTROL_SOURCE = "online_multimodal_teacher"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("receipt_must_be_an_object")
    return value


def _index(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError("control_frame_must_be_nonnegative_integer")
    return int(value)


def _safe_file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("receipt_path_must_be_relative")
    path = (root / value).resolve()
    path.relative_to(root.resolve())
    if not path.is_file():
        raise ValueError("receipt_file_missing")
    return path


def _array_info(array: np.ndarray) -> dict[str, Any]:
    return {"shape": list(array.shape), "dtype": str(array.dtype),
            "array_sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest()}


def _load_images(directory: Path, pre: Mapping[str, Any]) -> dict[str, np.ndarray]:
    archive = _safe_file(directory, pre["images_file"])
    if sha256(archive) != pre["images_file_sha256"]:
        raise ValueError("observation_archive_hash_mismatch")
    with np.load(archive, allow_pickle=False) as loaded:
        if set(loaded.files) != set(IMAGE_NAMES):
            raise ValueError("observation_images_must_be_exactly_three")
        images = {key: np.array(loaded[key], copy=True) for key in IMAGE_NAMES}
    for name, array in images.items():
        if _array_info(array) != pre["images"][name]:
            raise ValueError("observation_array_hash_mismatch")
        if array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3 or 0 in array.shape:
            raise ValueError("observation_requires_uint8_rgb")
        array.setflags(write=False)
    return images


def _validate_request(request: Mapping[str, Any], pre: Mapping[str, Any],
                      images: Mapping[str, np.ndarray], inference: Mapping[str, Any]) -> None:
    from PIL import Image

    if request.get("model") != inference.get("model_requested"):
        raise ValueError("request_model_mismatch")
    if inference.get("protocol") == "chat_completions":
        messages = request.get("messages", [])
        users = [row for row in messages if row.get("role") == "user"]
    elif inference.get("protocol") == "responses":
        users = [row for row in request.get("input", []) if row.get("role") == "user"]
    else:
        raise ValueError("unsupported_request_protocol")
    if len(users) != 1 or not isinstance(users[0].get("content"), list):
        raise ValueError("request_requires_one_multimodal_user_input")
    parts = users[0]["content"]
    if len(parts) != 4 or parts[0].get("type") not in ("text", "input_text"):
        raise ValueError("request_visible_input_must_be_text_and_exactly_three_images")
    text = json.loads(parts[0]["text"])
    if (text.get("task") != pre["task"]
            or text.get("movement_history_newest_first") != pre["recent_movement_tokens"]
            or set(text) - {"task", "movement_history_newest_first", "prompt_version"}):
        raise ValueError("request_task_or_history_mismatch_or_privileged_input")
    for name, part in zip(IMAGE_NAMES, parts[1:]):
        source = part.get("image_url")
        if isinstance(source, Mapping):
            source = source.get("url")
        if not isinstance(source, str) or not source.startswith("data:image/png;base64,"):
            raise ValueError("request_images_must_be_inline_png")
        raw = base64.b64decode(source.split(",", 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            decoded = np.asarray(image.convert("RGB"))
        if not np.array_equal(decoded, images[name]):
            raise ValueError("request_image_differs_from_decision_observation")
        declared = inference["image_inputs"][name]
        if (declared.get("array_sha256") != pre["images"][name]["array_sha256"]
                or declared.get("shape") != list(images[name].shape)
                or declared.get("dtype") != "uint8"
                or declared.get("png_sha256") != hashlib.sha256(raw).hexdigest()):
            raise ValueError("request_image_receipt_hash_mismatch")


def _validate_inference(directory: Path, pre: Mapping[str, Any], attached: Mapping[str, Any],
                        images: Mapping[str, np.ndarray]) -> dict[str, Any]:
    inference_file = _safe_file(directory, attached["inference_file"])
    if sha256(inference_file) != attached["inference_sha256"]:
        raise ValueError("inference_receipt_hash_mismatch")
    receipt = read_json(inference_file)
    root = inference_file.parent
    if receipt.get("schema") != "tacharness.tacjev_online_inference.v1":
        raise ValueError("genuine_online_receipt_schema_required")
    if receipt.get("task") != pre["task"] or receipt.get("history") != pre["recent_movement_tokens"]:
        raise ValueError("inference_task_or_history_mismatch")
    if receipt.get("model_requested") != pre["teacher_model"]:
        raise ValueError("requested_teacher_model_mismatch")
    request = _safe_file(root, receipt["request_path"])
    if sha256(request) != receipt["request_sha256"]:
        raise ValueError("request_hash_mismatch")
    _validate_request(read_json(request), pre, images, receipt)
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > 3 or (not attempts and receipt.get("status") == "ok"):
        raise ValueError("inference_requires_at_most_three_actual_attempts")
    accepted = []
    for index, attempt in enumerate(attempts, start=1):
        request_file = _safe_file(root, attempt["request_path"])
        if (attempt["attempt"] != index or sha256(request_file) != receipt["request_sha256"]
                or attempt["request_sha256"] != receipt["request_sha256"]):
            raise ValueError("retry_request_must_match_frozen_request")
        if attempt.get("response_path"):
            response_file = _safe_file(root, attempt["response_path"])
            if sha256(response_file) != attempt["response_sha256"]:
                raise ValueError("response_receipt_hash_mismatch")
            response = read_json(response_file)
            if attempt.get("status") == "ok":
                if (response.get("token") != attempt.get("token")
                        or response.get("model") != attempt.get("response_model")
                        or attempt.get("token") not in TOKENS):
                    raise ValueError("accepted_response_token_or_model_mismatch")
                accepted.append(attempt)
        elif attempt.get("status") == "ok":
            raise ValueError("accepted_response_missing")
    if receipt.get("status") == "ok":
        if (len(accepted) != 1 or attempts[-1] != accepted[0]
                or receipt.get("token") != accepted[0]["token"]
                or receipt.get("response_model") != accepted[0]["response_model"]
                or attached.get("token") != receipt["token"]):
            raise ValueError("selected_token_requires_unique_final_accepted_response")
    elif receipt.get("status") == "service_interruption":
        if ((accepted and receipt.get("reason") != "freeze_guard_failed")
                or receipt.get("token") is not None or attached.get("token") is not None):
            raise ValueError("interrupted_request_cannot_select_token")
    else:
        raise ValueError("invalid_inference_status")
    return receipt


def _validate_freeze(directory: Path, pre: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    from .arena_collection_state import assert_arena_state_unchanged, ArenaStateChangedError

    frame, history = pre["observation_control_frame"], pre["recent_movement_tokens"]
    if (receipt.get("control_frame_before") != frame or receipt.get("control_frame_after") != frame
            or receipt.get("history_before") != history or receipt.get("history_after") != history):
        raise ValueError("HTTP_wait_advanced_control_frame_or_action_history")
    state_paths = [directory / "http_state_before.npz", directory / "http_state_after.npz"]
    for path, field in zip(state_paths, ("before_sha256", "after_sha256")):
        if not path.is_file() or sha256(path) != receipt.get(field):
            raise ValueError("frozen_state_evidence_missing_or_hash_mismatch")
    states = []
    for path in state_paths:
        with np.load(path, allow_pickle=False) as archive:
            states.append({name: np.array(archive[name], copy=True) for name in archive.files})
    try:
        checked = assert_arena_state_unchanged(*states)
    except ArenaStateChangedError as exc:
        checked = exc.report
    claimed = receipt.get("state_check", {})
    if claimed.get("unchanged") != checked["unchanged"]:
        raise ValueError("frozen_state_claim_does_not_match_actual_snapshots")
    verified = bool(checked["unchanged"] and receipt.get("verified") is True)
    return verified


class OnlineDecisionRecordWriter:
    def __init__(self, root: Path, *, task: str, observation_version: str,
                 interpreter_version: str, teacher_model: str):
        for value in (task, observation_version, interpreter_version, teacher_model):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("nonempty_task_versions_and_model_required")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.manifest = {"schema": SCHEMA, "task": task, "observation_version": observation_version,
                         "interpreter_version": interpreter_version, "teacher_model": teacher_model,
                         "control_source": CONTROL_SOURCE, "online_teacher": True,
                         "positive_demonstration": False, "train_action_mask": False}
        write_json(self.root / "manifest.json", self.manifest)
        self._records: list[dict[str, str]] = []
        self._pending: dict[str, Any] | None = None
        self._history: list[str] = []
        self._history_ids: list[str] = []
        self._frame_end = 0
        self._closed = False
        self._done = False

    @property
    def history(self) -> list[str]:
        return list(self._history)

    @property
    def recent_movement_tokens(self) -> list[str]:
        return self.history

    @property
    def pending_decision_id(self) -> str | None:
        return self._pending["decision_id"] if self._pending is not None else None

    def decision_directory(self, decision_id: str) -> Path:
        if not isinstance(decision_id, str) or not decision_id.startswith("decision_") or "/" in decision_id:
            raise ValueError("invalid_decision_id")
        return self.root / decision_id

    def begin(self, images: Mapping[str, Any], history: list[str], observation_control_frame: int,
              source_physical_frame: int | None, state_before: Mapping[str, Any] | None = None) -> str:
        if self._closed or self._done or self._pending is not None:
            raise ValueError("writer_closed_or_has_pending_decision")
        frame = _index(observation_control_frame)
        if frame != self._frame_end or history != self.history:
            raise ValueError("observation_boundary_or_executed_history_not_causal")
        if source_physical_frame != (None if frame == 0 else frame - 1):
            raise ValueError("source_physical_frame_must_precede_action")
        if set(images) != set(IMAGE_NAMES):
            raise ValueError("visible_input_must_be_exactly_three_images")
        copied = {name: np.array(images[name], copy=True, order="C") for name in IMAGE_NAMES}
        for array in copied.values():
            if array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3 or 0 in array.shape:
                raise ValueError("visible_images_require_nonempty_uint8_RGB")
        decision_id = f"decision_{len(self._records):06d}"
        directory = self.decision_directory(decision_id)
        directory.mkdir()
        with (directory / "images.npz").open("xb") as handle:
            np.savez_compressed(handle, **copied)
        pre = {**self.manifest, "decision_id": decision_id, "observation_control_frame": frame,
               "source_physical_frame_index": source_physical_frame,
               "recent_movement_tokens": self.history, "history_decision_ids": list(self._history_ids),
               "images_file": "images.npz", "images_file_sha256": sha256(directory / "images.npz"),
               "images": {name: _array_info(array) for name, array in copied.items()}}
        write_json(directory / "pre.json", pre)
        if state_before is not None:
            with (directory / "http_state_before.npz").open("xb") as handle:
                np.savez_compressed(handle, **state_before)
        self._pending = pre
        return decision_id

    def attach_inference(self, decision_id: str, inference_path: Path,
                         freeze_receipt: Mapping[str, Any], token: str | None) -> None:
        if self._pending is None or self.pending_decision_id != decision_id:
            raise ValueError("inference_requires_pending_decision")
        directory = self.decision_directory(decision_id)
        path = Path(inference_path)
        if path.is_dir():
            path /= "inference.json"
        relative = path.resolve().relative_to(directory.resolve()).as_posix()
        attached: dict[str, Any] = {"inference_file": relative, "inference_sha256": sha256(path),
                    "token": token, "freeze": dict(freeze_receipt)}
        _validate_inference(directory, self._pending, attached, _load_images(directory, self._pending))
        _validate_freeze(directory, self._pending, attached["freeze"])
        write_json(directory / "selected.json", attached)

    def complete(self, decision_id: str, start: int, end: int, *, status: str = "completed",
                 failure_reason: str | None = None, known_wrong: bool = False,
                 evidence: Mapping[str, Any] | None = None, execution_uncertain: bool = False) -> dict[str, Any]:
        if self._pending is None or self.pending_decision_id != decision_id:
            raise ValueError("execution_requires_pending_decision")
        start, end = _index(start), _index(end)
        if start != self._frame_end or end < start or status not in ("completed", "failed", "interrupted"):
            raise ValueError("execution_interval_or_status_invalid")
        if not isinstance(known_wrong, bool) or known_wrong and not evidence:
            raise ValueError("known_wrong_requires_audit_evidence")
        directory = self.decision_directory(decision_id)
        selected_path = directory / "selected.json"
        selected = read_json(selected_path) if selected_path.exists() else None
        token = selected.get("token") if selected else None
        if (token is None or token == "DONE") and end != start:
            raise ValueError("missing_token_or_DONE_cannot_have_physical_interval")
        if status == "completed" and (selected is None or token not in TOKENS or (token != "DONE" and end == start)):
            raise ValueError("completed_execution_requires_selected_token_and_actual_interval")
        if end > start or status == "completed":
            if selected is None or not _validate_freeze(directory, self._pending, selected["freeze"]):
                raise ValueError("execution_requires_verified_frozen_HTTP_state")
        result = {"decision_id": decision_id, "frame_start": start, "frame_end_exclusive": end,
                  "actual_control_frame_count": end - start, "token": token, "status": status,
                  "failure_reason": failure_reason, "execution_uncertain": bool(execution_uncertain),
                  "known_wrong": known_wrong, "audit_evidence": dict(evidence or {}),
                  "positive_demonstration": False, "train_action_mask": False,
                  "pre_sha256": sha256(directory / "pre.json"),
                  "selected_sha256": sha256(selected_path) if selected else None}
        write_json(directory / "finish.json", result)
        self._records.append({"decision_id": decision_id, "finish_sha256": sha256(directory / "finish.json")})
        if isinstance(token, str) and token in MOVEMENT_TOKENS and end > start and not execution_uncertain:
            self._history = ([token] + self._history)[:5]
            self._history_ids = ([decision_id] + self._history_ids)[:5]
        self._frame_end = end
        self._pending = None
        self._done = token == "DONE" or status != "completed" or execution_uncertain
        return result

    def close(self, *, native_frame_count: int | None = None) -> dict[str, Any]:
        if self._pending is not None:
            raise ValueError("unfinished_online_decision_preserved")
        if not self._closed:
            write_json(self.root / "index.json", {"schema": SCHEMA, "records": self._records,
                "manifest_sha256": sha256(self.root / "manifest.json"), "native_frame_count": self._frame_end})
            self._closed = True
        return validate_online_decision_records(self.root, native_frame_count=native_frame_count)


def _read_records(root: Path, native_frame_count: int | None) -> list[dict[str, Any]]:
    manifest, index = read_json(root / "manifest.json"), read_json(root / "index.json")
    if manifest.get("schema") != SCHEMA or index.get("schema") != SCHEMA:
        raise ValueError("online_record_schema_required")
    if index.get("manifest_sha256") != sha256(root / "manifest.json"):
        raise ValueError("manifest_hash_mismatch")
    if manifest.get("control_source") != CONTROL_SOURCE or manifest.get("online_teacher") is not True:
        raise ValueError("online_control_source_required")
    if manifest.get("positive_demonstration") is not False or manifest.get("train_action_mask") is not False:
        raise ValueError("raw_online_records_cannot_claim_training_adoption")
    records: list[dict[str, Any]] = []
    history: list[str] = []
    history_ids: list[str] = []
    end, stopped = 0, False
    for number, row in enumerate(index["records"]):
        decision_id = f"decision_{number:06d}"
        if row.get("decision_id") != decision_id or stopped:
            raise ValueError("decision_order_or_unique_execution_invalid")
        directory = root / decision_id
        pre = read_json(directory / "pre.json")
        finish = read_json(directory / "finish.json")
        if sha256(directory / "finish.json") != row["finish_sha256"] or sha256(directory / "pre.json") != finish["pre_sha256"]:
            raise ValueError("decision_record_hash_mismatch")
        if any(pre.get(key) != value for key, value in manifest.items()):
            raise ValueError("decision_versions_or_source_mismatch")
        if (pre.get("decision_id") != decision_id or finish.get("decision_id") != decision_id
                or pre.get("observation_control_frame") != end or finish.get("frame_start") != end
                or pre.get("source_physical_frame_index") != (None if end == 0 else end - 1)
                or pre.get("recent_movement_tokens") != history or pre.get("history_decision_ids") != history_ids):
            raise ValueError("pre_observation_or_history_not_causal")
        images = _load_images(directory, pre)
        selected = None
        inference = None
        frozen = False
        if finish.get("selected_sha256") is not None:
            selected = read_json(directory / "selected.json")
            if sha256(directory / "selected.json") != finish["selected_sha256"]:
                raise ValueError("selected_token_record_hash_mismatch")
            inference = _validate_inference(directory, pre, selected, images)
            frozen = _validate_freeze(directory, pre, selected["freeze"])
        token = selected.get("token") if selected else None
        next_end = _index(finish["frame_end_exclusive"])
        count = next_end - end
        if (finish.get("token") != token or count < 0 or finish.get("actual_control_frame_count") != count
                or finish.get("status") not in ("completed", "failed", "interrupted")
                or (token in (None, "DONE") and count != 0)
                or (count > 0 and not frozen)
                or (finish["status"] == "completed" and not frozen)
                or (finish["status"] == "completed" and (token not in TOKENS or (token != "DONE" and count == 0)))
                or finish.get("positive_demonstration") is not False or finish.get("train_action_mask") is not False):
            raise ValueError("physical_interval_or_adoption_claim_invalid")
        if finish.get("known_wrong") and not finish.get("audit_evidence"):
            raise ValueError("known_wrong_requires_evidence")
        records.append({"decision_id": decision_id, "token": token,
            "visible_observation": {"images": images, "task": pre["task"], "recent_movement_tokens": history.copy()},
            "execution": finish, "inference": inference,
            "audit": {**pre, "known_wrong": finish.get("known_wrong", False), "train_action_mask": False,
                      "freeze_verified": frozen, "selected": selected}})
        if isinstance(token, str) and token in MOVEMENT_TOKENS and count > 0 and not finish.get("execution_uncertain"):
            history, history_ids = ([token] + history)[:5], ([decision_id] + history_ids)[:5]
        end = next_end
        stopped = token == "DONE" or finish["status"] != "completed" or bool(finish.get("execution_uncertain"))
    if index.get("native_frame_count") != end or native_frame_count is not None and native_frame_count != end:
        raise ValueError("native_frame_count_mismatch")
    if set(path.name for path in root.glob("decision_*")) != {row["decision_id"] for row in index["records"]}:
        raise ValueError("unindexed_online_decision_preserved_but_not_publishable")
    return records


def validate_online_decision_records(root: Path, *, native_frame_count: int | None = None) -> dict[str, Any]:
    try:
        records = _read_records(Path(root), native_frame_count)
        return {"valid": True, "errors": [], "decisions": len(records)}
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        return {"valid": False, "errors": [str(exc)]}


def read_online_decision_records(root: Path, *, native_frame_count: int | None = None) -> list[dict[str, Any]]:
    checked = validate_online_decision_records(root, native_frame_count=native_frame_count)
    if not checked["valid"]:
        raise ValueError("invalid_online_decision_records: " + "; ".join(checked["errors"]))
    return _read_records(Path(root), native_frame_count)
