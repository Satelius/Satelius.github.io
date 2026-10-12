"""Immutable pre-action observations for declared offline Arena token sources.

This records a selected token before its physical interval starts. It neither
chooses actions nor contacts a model. Probe and scripted reference records
remain excluded from training, even when their native task predicate is true.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import numpy as np


SCHEMA = "tacharness.arena.decision-records.v1"
CONTROL_SOURCE = "component_token_probe"
REFERENCE_CONTROL_SOURCE = "feedback_meta_action_teacher"
OFFLINE_CONTROL_SOURCES = frozenset((CONTROL_SOURCE, REFERENCE_CONTROL_SOURCE))
TACTILE_MOSAIC_VERSION = "tacumi-render-indent-left-above-right-v1"
IMAGE_NAMES = ("scene_rgb", "wrist_rgb", "tactile_mosaic_rgb")
MOVEMENT_TOKENS = frozenset(
    ("MV_FWD", "MV_BACK", "MV_LEFT", "MV_RIGHT", "MV_UP", "MV_DOWN")
)
TOKENS = MOVEMENT_TOKENS | {"GRASP", "RELEASE", "DONE"}
STATUSES = frozenset(("completed", "failed", "interrupted"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(encoded)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("record_must_be_an_object")
    return value


def _index(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name}_must_be_a_nonnegative_integer")
    return int(value)


def _rgb_copy(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3 or 0 in array.shape:
        raise ValueError(f"{name}_must_be_nonempty_uint8_hwc_rgb")
    return np.array(array, copy=True, order="C")


def _array_info(array: np.ndarray) -> dict[str, Any]:
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def tactile_mosaic(
    tactile: Mapping[str, Mapping[str, Any]], *, indent_max_m: float = 0.0015
) -> np.ndarray:
    """Stack the existing indentation visualization, left above right.

    The input is the native runtime's metric ``indent`` and contact ``mask``;
    raw depth/deformation are not model-visible features here. This named
    component preprocessing is not an attested online teacher preprocessing.
    """
    from tacumi.visualization import render_indent

    if not np.isfinite(indent_max_m) or indent_max_m <= 0:
        raise ValueError("indent_max_m_must_be_positive_and_finite")
    panels = []
    shape = None
    for side in ("left", "right"):
        sample = tactile[side]
        indent = np.asarray(sample["indent"], dtype=np.float32)
        mask = np.asarray(sample["mask"], dtype=bool)
        if indent.ndim != 2 or 0 in indent.shape or mask.shape != indent.shape:
            raise ValueError("indent_and_mask_must_be_matching_nonempty_hw_arrays")
        if shape is not None and indent.shape != shape:
            raise ValueError("left_and_right_tactile_shapes_must_match")
        shape = indent.shape
        stats = sample.get("stats", {})
        if isinstance(stats, Mapping) and stats.get("has_contact") is False:
            mask = np.zeros_like(mask)
        panels.append(render_indent(indent, mask, indent_max_m))
    return np.ascontiguousarray(np.concatenate(panels, axis=0))


class ArenaDecisionRecordWriter:
    """Write a fresh offline evidence stream, never edit or adopt an old stream."""

    def __init__(
        self,
        root: Path,
        *,
        task: str,
        observation_version: str,
        interpreter_version: str,
        control_source: str = CONTROL_SOURCE,
        tactile_mosaic_version: str = TACTILE_MOSAIC_VERSION,
        tactile_indent_max_m: float = 0.0015,
    ):
        if control_source not in OFFLINE_CONTROL_SOURCES:
            raise ValueError("only_declared_offline_control_sources_are_supported")
        for name, value in (
            ("task", task), ("observation_version", observation_version),
            ("interpreter_version", interpreter_version),
            ("tactile_mosaic_version", tactile_mosaic_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_must_be_nonempty")
        if not np.isfinite(tactile_indent_max_m) or tactile_indent_max_m <= 0:
            raise ValueError("tactile_indent_max_m_must_be_positive_and_finite")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.manifest = {
            "schema": SCHEMA,
            "task": task,
            "control_source": control_source,
            "observation_version": observation_version,
            "interpreter_version": interpreter_version,
            "tactile_mosaic_version": tactile_mosaic_version,
            "tactile_mosaic_parameters": {
                "indent_max_m": float(tactile_indent_max_m),
                "layout": "left_above_right",
                "renderer": "tacumi.visualization.render_indent",
            },
            "online_teacher": False,
            "positive_demonstration": False,
            "train_action_mask": False,
            "image_names": list(IMAGE_NAMES),
        }
        _write_json(self.root / "manifest.json", self.manifest)
        self._pending: dict[str, Any] | None = None
        self._history: list[str] = []
        self._records: list[dict[str, str]] = []
        self._frame_end = 0
        self._closed = False
        self._done = False

    @property
    def recent_movement_tokens(self) -> list[str]:
        """Return a copy of at most five actually executed movement decisions."""
        return list(self._history)

    @property
    def pending_decision_id(self) -> str | None:
        return None if self._pending is None else self._pending["decision_id"]

    def begin(
        self,
        images: Mapping[str, Any],
        token: str,
        frame_start: int,
        *,
        observation_boundary_index: int | None = None,
        observation_frame_index: int | None = None,
        known_wrong: bool = False,
        evidence: Mapping[str, Any] | None = None,
    ) -> str:
        """Snapshot the state after ``frame_start`` steps, before the next step.

        Boundary zero has no native NPZ source frame. Boundary N follows physical
        frame N-1; it is never paired with post-action physical frame N. The old
        ``observation_frame_index`` argument is an alias for this state boundary,
        not a native ``frame_XXXXXX.npz`` index.
        """
        if self._closed or self._done or self._pending is not None:
            raise ValueError("writer_closed_done_or_has_unfinished_decision")
        if token not in TOKENS:
            raise ValueError("token_is_not_in_the_nine_token_vocabulary")
        start = _index(frame_start, "frame_start")
        if (observation_boundary_index is not None and observation_frame_index is not None
                and observation_boundary_index != observation_frame_index):
            raise ValueError("conflicting_observation_boundary_aliases")
        supplied_boundary = (
            observation_boundary_index if observation_boundary_index is not None
            else observation_frame_index
        )
        observed = start if supplied_boundary is None else _index(
            supplied_boundary, "observation_boundary_index"
        )
        if start != self._frame_end:
            raise ValueError("decision_intervals_must_be_contiguous_from_zero")
        if observed != start:
            raise ValueError("pre_observation_must_be_at_the_decision_start")
        if not isinstance(known_wrong, bool):
            raise ValueError("known_wrong_must_be_boolean")
        if evidence is not None and not isinstance(evidence, Mapping):
            raise ValueError("evidence_must_be_an_object")
        audit_evidence = json.loads(json.dumps(dict(evidence or {}), allow_nan=False))
        if known_wrong and not audit_evidence:
            raise ValueError("known_wrong_requires_audit_evidence")
        if set(images) != set(IMAGE_NAMES):
            raise ValueError("visible_images_must_be_exactly_scene_wrist_and_tactile_mosaic")
        copied = {name: _rgb_copy(images[name], name) for name in IMAGE_NAMES}
        decision_id = f"decision_{len(self._records):06d}"
        directory = self.root / decision_id
        directory.mkdir(exist_ok=False)
        image_path = directory / "images.npz"
        with image_path.open("xb") as handle:
            np.savez_compressed(handle, **copied)
        before = {
            **self.manifest,
            "decision_id": decision_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "token": token,
            "frame_start": start,
            "observation_boundary_index": observed,
            "source_physical_frame_index": None if observed == 0 else observed - 1,
            "recent_movement_tokens": list(self._history),
            "known_wrong": known_wrong,
            "audit_evidence": audit_evidence,
            "images_file": "images.npz",
            "images_file_sha256": _sha256(image_path),
            "images": {name: _array_info(copied[name]) for name in IMAGE_NAMES},
        }
        _write_json(directory / "pre.json", before)
        self._pending = before
        return decision_id

    def finish(
        self,
        frame_end: int,
        *,
        status: str = "completed",
        native_success: bool = False,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        if self._closed or self._pending is None:
            raise ValueError("no_pending_decision")
        end = _index(frame_end, "frame_end")
        before = self._pending
        start = before["frame_start"]
        if status not in STATUSES or not isinstance(native_success, bool):
            raise ValueError("invalid_execution_status_or_native_success")
        if end < start or (before["token"] == "DONE" and end != start):
            raise ValueError("invalid_actual_control_frame_interval")
        if status == "completed" and before["token"] != "DONE" and end == start:
            raise ValueError("a_completed_motion_requires_an_actual_control_frame")
        if status != "completed" and (not isinstance(failure_reason, str) or not failure_reason.strip()):
            raise ValueError("failed_or_interrupted_decisions_require_a_reason")
        directory = self.root / before["decision_id"]
        execution = {
            "schema": SCHEMA,
            "decision_id": before["decision_id"],
            "pre_record_sha256": _sha256(directory / "pre.json"),
            "frame_start": start,
            "frame_end_exclusive": end,
            "actual_control_frame_count": end - start,
            "status": status,
            "native_success": native_success,
            "failure_reason": failure_reason,
            "online_teacher": False,
            "positive_demonstration": False,
            "train_action_mask": False,
        }
        _write_json(directory / "finish.json", execution)
        self._records.append({
            "decision_id": before["decision_id"],
            "pre_sha256": execution["pre_record_sha256"],
            "finish_sha256": _sha256(directory / "finish.json"),
        })
        if before["token"] in MOVEMENT_TOKENS and end > start:
            self._history = [before["token"], *self._history][:5]
        self._frame_end = end
        self._done = before["token"] == "DONE"
        self._pending = None
        return json.loads(json.dumps(execution))

    def close(self) -> dict[str, Any]:
        if self._closed or self._pending is not None:
            raise ValueError("writer_already_closed_or_has_unfinished_decision")
        receipt = {
            "schema": SCHEMA,
            "manifest_sha256": _sha256(self.root / "manifest.json"),
            "decision_count": len(self._records),
            "actual_control_frame_count": self._frame_end,
            "records": list(self._records),
            "positive_demonstration_count": 0,
        }
        _write_json(self.root / "closed.json", receipt)
        self._closed = True
        return validate_decision_records(self.root)


def validate_decision_records(
    root: Path, *, native_frame_count: int | None = None
) -> dict[str, Any]:
    """Read only; check images, causal indices, history, counts and source claims."""
    root = Path(root)
    errors: list[str] = []
    count = 0
    frame_end = 0
    history: list[str] = []
    done = False
    try:
        manifest = _read_json(root / "manifest.json")
        closed = _read_json(root / "closed.json")
        if manifest.get("schema") != SCHEMA or closed.get("schema") != SCHEMA:
            errors.append("invalid_schema")
        if manifest.get("control_source") not in OFFLINE_CONTROL_SOURCES:
            errors.append("invalid_control_source")
        for key in ("task", "observation_version", "interpreter_version", "tactile_mosaic_version"):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip():
                errors.append(f"invalid_{key}")
        if manifest.get("image_names") != list(IMAGE_NAMES):
            errors.append("invalid_manifest_image_names")
        for flag in ("online_teacher", "positive_demonstration", "train_action_mask"):
            if manifest.get(flag) is not False:
                errors.append(f"component_records_cannot_claim_{flag}")
        if closed.get("manifest_sha256") != _sha256(root / "manifest.json"):
            errors.append("manifest_hash_mismatch")
        directories = sorted(path for path in root.glob("decision_*") if path.is_dir())
        records = closed.get("records")
        if not isinstance(records, list) or len(records) != len(directories):
            errors.append("decision_count_mismatch")
            records = []
        for position, directory in enumerate(directories):
            expected_id = f"decision_{position:06d}"
            label = directory.name
            before = _read_json(directory / "pre.json")
            execution = _read_json(directory / "finish.json")
            if label != expected_id or before.get("decision_id") != label or execution.get("decision_id") != label:
                errors.append(f"{label}:decision_identity_mismatch")
            if done:
                errors.append(f"{label}:decision_after_done")
            if any(before.get(key) != value for key, value in manifest.items()):
                errors.append(f"{label}:manifest_contract_mismatch")
            for flag in ("online_teacher", "positive_demonstration", "train_action_mask"):
                if before.get(flag) is not False or execution.get(flag) is not False:
                    errors.append(f"{label}:component_records_cannot_claim_{flag}")
            if before.get("known_wrong") is True and not before.get("audit_evidence"):
                errors.append(f"{label}:known_wrong_requires_evidence")
            if not isinstance(before.get("known_wrong"), bool) or not isinstance(before.get("audit_evidence"), dict):
                errors.append(f"{label}:invalid_known_wrong_evidence")
            token = before.get("token")
            if token not in TOKENS:
                errors.append(f"{label}:invalid_token")
            start = _index(before.get("frame_start"), "frame_start")
            observed = _index(before.get("observation_boundary_index"), "observation_boundary_index")
            end = _index(execution.get("frame_end_exclusive"), "frame_end_exclusive")
            if observed != start:
                errors.append(f"{label}:pre_observation_not_causal")
            if before.get("source_physical_frame_index") != (None if observed == 0 else observed - 1):
                errors.append(f"{label}:incorrect_source_physical_frame_index")
            if start != frame_end or execution.get("frame_start") != start or end < start:
                errors.append(f"{label}:noncontiguous_actual_frame_interval")
            if execution.get("actual_control_frame_count") != end - start:
                errors.append(f"{label}:actual_frame_count_mismatch")
            if token == "DONE" and end != start:
                errors.append(f"{label}:done_must_have_empty_interval")
            status = execution.get("status")
            if status not in STATUSES or not isinstance(execution.get("native_success"), bool):
                errors.append(f"{label}:invalid_execution_status")
            if status == "completed" and token != "DONE" and end == start:
                errors.append(f"{label}:completed_motion_has_no_frames")
            if status != "completed" and not execution.get("failure_reason"):
                errors.append(f"{label}:missing_failure_reason")
            if before.get("recent_movement_tokens") != history:
                errors.append(f"{label}:movement_history_mismatch")
            if before.get("images_file") != "images.npz":
                errors.append(f"{label}:invalid_images_path")
            image_path = directory / "images.npz"
            if before.get("images_file_sha256") != _sha256(image_path):
                errors.append(f"{label}:images_file_hash_mismatch")
            with np.load(image_path, allow_pickle=False) as images:
                if set(images.files) != set(IMAGE_NAMES) or set(before.get("images", {})) != set(IMAGE_NAMES):
                    errors.append(f"{label}:visible_image_names_mismatch")
                else:
                    for name in IMAGE_NAMES:
                        image = _rgb_copy(images[name], name)
                        if before["images"][name] != _array_info(image):
                            errors.append(f"{label}:{name}:image_hash_or_shape_mismatch")
            pre_hash = _sha256(directory / "pre.json")
            if execution.get("pre_record_sha256") != pre_hash:
                errors.append(f"{label}:pre_record_hash_mismatch")
            if position < len(records) and records[position] != {
                "decision_id": label, "pre_sha256": pre_hash,
                "finish_sha256": _sha256(directory / "finish.json"),
            }:
                errors.append(f"{label}:closure_record_hash_mismatch")
            if token in MOVEMENT_TOKENS and end > start:
                history = [token, *history][:5]
            frame_end = end
            done = token == "DONE"
            count += 1
        if closed.get("decision_count") != count or closed.get("actual_control_frame_count") != frame_end:
            errors.append("closure_count_mismatch")
        if closed.get("positive_demonstration_count") != 0:
            errors.append("component_records_cannot_be_positive_demonstrations")
        if native_frame_count is not None and _index(native_frame_count, "native_frame_count") != frame_end:
            errors.append("native_frame_count_mismatch")
    except (OSError, ValueError, TypeError, KeyError, BadZipFile, EOFError):
        errors.append("missing_or_invalid_record_artifact")
    return {
        "valid": not errors,
        "errors": errors,
        "decision_count": count,
        "actual_control_frame_count": frame_end,
        "positive_demonstration_count": 0,
        "online_teacher": False,
    }


def read_decision_records(
    root: Path, *, native_frame_count: int | None = None
) -> list[dict[str, Any]]:
    """Validate then return model-visible copies separately from audit metadata."""
    root = Path(root)
    validation = validate_decision_records(root, native_frame_count=native_frame_count)
    if not validation["valid"]:
        raise ValueError("invalid_decision_records: " + ", ".join(validation["errors"]))
    result = []
    for directory in sorted(path for path in root.glob("decision_*") if path.is_dir()):
        before = _read_json(directory / "pre.json")
        with np.load(directory / "images.npz", allow_pickle=False) as stored:
            images = {name: _rgb_copy(stored[name], name) for name in IMAGE_NAMES}
        for image in images.values():
            image.setflags(write=False)
        result.append({
            "decision_id": before["decision_id"],
            "token": before["token"],
            "visible_observation": {
                "images": images,
                "task": before["task"],
                "recent_movement_tokens": list(before["recent_movement_tokens"]),
            },
            "audit": before,
            "execution": _read_json(directory / "finish.json"),
        })
    return result
