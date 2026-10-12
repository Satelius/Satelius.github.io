"""Online three-image teacher with bounded HTTP and immutable safe receipts.

No simulator state, geometry teacher, model fallback, or robot action is used
here. The caller freezes the scene and executes the returned legal token once.
"""
from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPSConnection, HTTPException
from io import BytesIO
import json
import math
from pathlib import Path
import re
import socket
from threading import Event, Thread
import time
from typing import Any
from urllib.parse import urlsplit

import numpy as np
from PIL import Image

from tacharness.first_collection_budget import BudgetExhausted, FirstCollectionBudget
from tacharness.teacher_preflight import TeacherServiceConfig, load_service_config


IMAGE_NAMES = ("scene_rgb", "wrist_rgb", "tactile_mosaic_rgb")
TOKENS = ("MV_FWD", "MV_BACK", "MV_LEFT", "MV_RIGHT", "MV_UP", "MV_DOWN", "GRASP", "RELEASE", "DONE")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SYSTEM_PROMPT = (
    "You are the online robot action teacher for a single Franka arm. "
    "Use only the three current images, complete task, and executed movement history. "
    "Images are ordered scene camera, wrist camera, tactile mosaic (left finger above right). "
    "The target is the colored coordinate-axis marker in the scene (not the cube). "
    "The cube must reach the target, not just be lifted. "
    "The interpreter holds a fixed downward gripper orientation. "
    "Directions use robot base axes: MV_FWD=+X, MV_BACK=-X, MV_LEFT=+Y, "
    "MV_RIGHT=-Y, MV_UP=+Z, MV_DOWN=-Z. GRASP closes the fingers; RELEASE opens them. "
    "Each movement token applies bounded control toward a fixed-direction target; actual motion "
    "may be smaller than requested, so use fresh images for each decision. "
    "Choose one action from the current images; tactile contact alone does not establish task success. "
    "DONE means stop and cannot declare native task success. "
    "Return exactly one token from: " + ", ".join(TOKENS) + ". No explanation or punctuation."
)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write(path: Path, value: Any) -> str:
    raw = _json_bytes(value)
    with path.open("xb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def _private_values(config: TeacherServiceConfig) -> tuple[str, ...]:
    parsed = urlsplit(config.base_url)
    return tuple(value for value in (config.api_key, config.base_url, parsed.netloc, parsed.hostname) if value)


def _safe_id(value: object, config: TeacherServiceConfig) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
        return None
    if any(secret in value for secret in _private_values(config)):
        return None
    return value


def _exchange(config: TeacherServiceConfig, endpoint_suffix: str, body: bytes, timeout_s: float) -> dict[str, Any]:
    """Bound connect, headers and slow-drip body by one absolute deadline.

    A daemon handles DNS (which cannot be interrupted portably). It checks the
    deadline after connecting and cannot send a late request. The waiting
    caller shuts down live sockets at the deadline, including detached HTTP
    response sockets, so per-read timeouts cannot extend the total wait.
    """
    deadline = time.monotonic() + timeout_s
    canceled = Event()
    result: dict[str, Any] = {}
    sockets: list[socket.socket] = []
    parsed = urlsplit(config.base_url)
    connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout_s)

    def work():
        try:
            connection.connect()
            if connection.sock is not None:
                sockets.append(connection.sock)
            if canceled.is_set() or time.monotonic() >= deadline:
                raise TimeoutError
            connection.request("POST", parsed.path.rstrip("/") + endpoint_suffix, body, headers={
                "Authorization": "Bearer " + config.api_key,
                "Content-Type": "application/json", "Accept": "application/json",
            })
            with connection.getresponse() as response:
                result["http_status"] = response.status
                if response.status != 200:
                    result["reason"] = "redirect_rejected" if 300 <= response.status < 400 else "http_error"
                    return  # Never retain error body or headers containing private text.
                chunks = []
                size = 0
                while True:
                    remaining = deadline - time.monotonic()
                    if canceled.is_set() or remaining <= 0:
                        raise TimeoutError
                    for live_socket in sockets:
                        live_socket.settimeout(remaining)
                    chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        result["reason"] = "response_too_large"
                        return
                if canceled.is_set() or time.monotonic() > deadline:
                    raise TimeoutError
                result["raw"] = b"".join(chunks)
        except (TimeoutError, socket.timeout):
            result["reason"] = "request_timeout"
        except (OSError, ValueError, HTTPException):
            result["reason"] = "transport_error"
        finally:
            connection.close()

    worker = Thread(target=work, daemon=True)
    worker.start()
    worker.join(max(0.0, deadline - time.monotonic()))
    if worker.is_alive():
        canceled.set()
        for live_socket in sockets:
            try:
                live_socket.shutdown(socket.SHUT_RDWR)
                live_socket.close()
            except OSError:
                pass
        return {"reason": "request_timeout", "http_status": result.get("http_status")}
    return result


def _response(raw: bytes, protocol: str, config: TeacherServiceConfig) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "model": None, "id": None, "token": None,
        "status": "invalid_response", "output_status": "invalid_response",
    }
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return safe
        safe["model"] = _safe_id(payload.get("model"), config)
        safe["id"] = _safe_id(payload.get("id"), config)
        if protocol == "chat_completions":
            choices = payload.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                return safe
            choice = choices[0]
            content = choice["message"]["content"]
        else:
            output = payload.get("output")
            if not isinstance(output, list):
                return safe
            texts = []
            for item in output:
                if not isinstance(item, dict):
                    return safe
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") != "output_text":
                            return safe
                        texts.append(part.get("text"))
            content = texts[0] if len(texts) == 1 else None
        token = content.strip() if isinstance(content, str) else None
        safe["token"] = token if token in TOKENS else None
        safe["status"] = "ok" if safe["token"] and safe["model"] else "invalid_response"
        safe["output_status"] = "valid_single_token" if safe["token"] else "invalid_single_token"
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError, AttributeError):
        pass
    return safe


class OnlineTeacher:
    def __init__(self, config_path: Path, model: str, budget: FirstCollectionBudget, *,
                 protocol: str = "chat_completions", request_timeout_s: float = 35.0,
                 expected_response_model: str | None = None):
        self.config = load_service_config(Path(config_path))
        if _safe_id(model, self.config) is None:
            raise ValueError("invalid_teacher_model")
        if expected_response_model is not None and _safe_id(expected_response_model, self.config) is None:
            raise ValueError("invalid_expected_response_model")
        if protocol not in {"chat_completions", "responses"}:
            raise ValueError("unsupported_teacher_protocol")
        if not math.isfinite(request_timeout_s) or not 0 < request_timeout_s <= 120:
            raise ValueError("invalid_teacher_request_timeout")
        self.model = model
        self.protocol = protocol
        self.budget = budget
        self.request_timeout_s = request_timeout_s
        self.expected_response_model = expected_response_model

    def prepare(self, images: Mapping[str, np.ndarray], task: str, history: list[str], *,
                prompt_version: str = "arena-online-teacher-v1") -> tuple[dict[str, Any], dict[str, Any]]:
        if set(images) != set(IMAGE_NAMES):
            raise ValueError("teacher_requires_exact_three_image_inputs")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("teacher_task_must_be_nonempty")
        if not isinstance(prompt_version, str) or not prompt_version.strip():
            raise ValueError("teacher_prompt_version_must_be_nonempty")
        if not isinstance(history, list) or len(history) > 5 or any(token not in TOKENS[:6] for token in history):
            raise ValueError("history_requires_at_most_five_executed_movement_tokens")
        text = json.dumps({"task": task, "movement_history_newest_first": history,
                           "prompt_version": prompt_version}, ensure_ascii=False)
        parts: list[dict[str, Any]] = []
        image_info = {}
        for name in IMAGE_NAMES:
            array = np.asarray(images[name])
            if array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3 or 0 in array.shape:
                raise ValueError("teacher_images_must_be_nonempty_uint8_hwc_rgb")
            array = np.array(array, order="C", copy=True)
            png = BytesIO()
            Image.fromarray(array).save(png, format="PNG")
            raw = png.getvalue()
            image_info[name] = {
                "shape": list(array.shape), "dtype": "uint8",
                "array_sha256": hashlib.sha256(array.tobytes()).hexdigest(),
                "png_sha256": hashlib.sha256(raw).hexdigest(),
            }
            url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": url, "detail": "high"}})
        if self.protocol == "chat_completions":
            body = {"model": self.model, "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [{"type": "text", "text": text}, *parts]},
            ], "temperature": 0}
        else:
            body = {"model": self.model, "instructions": SYSTEM_PROMPT,
                    "input": [{"role": "user", "content": [
                        {"type": "input_text", "text": text},
                        *[{"type": "input_image", "image_url": part["image_url"]["url"], "detail": "high"} for part in parts],
                    ]}], "temperature": 0}
        return body, image_info

    def decide(self, images: Mapping[str, np.ndarray], task: str, history: list[str], output: Path, *,
               prompt_version: str = "arena-online-teacher-v1",
               frozen_guard: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        body, image_info = self.prepare(images, task, history, prompt_version=prompt_version)
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        request_hash = _write(output / "request.json", body)
        request_raw = (output / "request.json").read_bytes()
        report: dict[str, Any] = {
            "schema": "tacharness.tacjev_online_inference.v1", "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "service_interruption", "reason": None, "token": None,
            "model_requested": self.model, "response_model": None, "protocol": self.protocol,
            "expected_response_model": self.expected_response_model,
            "prompt_version": prompt_version, "task": task, "history": list(history),
            "image_inputs": image_info, "request_path": "request.json", "request_sha256": request_hash,
            "attempts": [], "inference_requests": 0,
        }
        decision_deadline = started + 120.0
        for ordinal in range(1, 4):
            remaining = min(decision_deadline - time.monotonic(), self.budget.remaining_wall_s())
            if remaining <= 0:
                report["reason"] = "decision_wait_budget_exhausted" if time.monotonic() >= decision_deadline else "run_wall_budget_exhausted"
                break
            attempt: dict[str, Any] = {"attempt": ordinal, "request_path": "request.json", "request_sha256": request_hash,
                                      "freeze_before": None, "freeze_after": None}
            try:
                if frozen_guard:
                    attempt["freeze_before"] = frozen_guard()
            except Exception:
                report["reason"] = "freeze_guard_failed"
                break
            else:
                try:
                    attempt["budget_reservation"] = self.budget.reserve_request()
                except BudgetExhausted as exc:
                    report["reason"] = str(exc)
                    break
                else:
                    attempt_started = time.monotonic()
                    # Guard and ledger I/O also consume the absolute budgets.
                    remaining = min(decision_deadline - attempt_started, self.budget.remaining_wall_s())
                    if remaining <= 0:
                        report["reason"] = "wait_budget_exhausted_before_send"
                        break  # The reservation remains spent, conservatively.
                    report["inference_requests"] += 1
                    reply = _exchange(self.config, "/chat/completions" if self.protocol == "chat_completions" else "/responses",
                                      request_raw, min(self.request_timeout_s, remaining))
                    response = _response(reply["raw"], self.protocol, self.config) if "raw" in reply else {
                        "raw_sha256": None, "model": None, "id": None, "token": None,
                        "status": "service_interruption", "output_status": "no_valid_response",
                    }
                    response["http_status"] = reply.get("http_status")
                    response["reason"] = reply.get("reason") or (None if response["status"] == "ok" else "invalid_model_response")
                    if (response["model"] is not None and self.expected_response_model is not None
                            and response["model"] != self.expected_response_model):
                        response["status"] = "invalid_response"
                        response["reason"] = "teacher_identity_changed"
                    response_path = f"response-{ordinal:02d}.json"
                    attempt.update({"response_path": response_path,
                                    "response_sha256": _write(output / response_path, response),
                                    "response_raw_sha256": response["raw_sha256"],
                                    "http_status": response["http_status"], "status": response["status"],
                                    "reason": response["reason"], "token": response["token"],
                                    "response_model": response["model"],
                                    "elapsed_s": time.monotonic() - attempt_started})
                    try:
                        if frozen_guard:
                            attempt["freeze_after"] = frozen_guard()
                    except Exception:
                        report["reason"] = "freeze_guard_failed"
                    else:
                        report.update({"status": response["status"] if response["status"] == "ok" else "service_interruption",
                                       "reason": response["reason"], "token": response["token"] if response["status"] == "ok" else None,
                                       "response_model": response["model"]})
                    report["attempts"].append(attempt)
                    if report["reason"] == "freeze_guard_failed" or report["status"] == "ok":
                        break
        report["elapsed_s"] = time.monotonic() - started
        _write(output / "inference.json", report)
        return report
