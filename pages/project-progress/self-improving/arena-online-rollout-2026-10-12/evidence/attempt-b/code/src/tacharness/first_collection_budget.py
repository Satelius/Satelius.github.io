"""Locked, durable continuation of the already-spent first collection budget."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any


class BudgetExhausted(RuntimeError):
    """The authorized resource cannot be reserved, using only a safe reason."""


def _boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirstCollectionBudget:
    """Reserve before a real HTTP send or native launcher, including failures.

    Creation starts a continuous resumed window. Development and the previous
    idle handoff are excluded, while HTTP waiting, retries, analysis between
    live attempts, failed starts, and teardown count. Reopening does not reset
    counters or the deadline. A closed window cannot be reopened for work.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "budget_ledger.json"
        self.lock_path = self.root / ".budget_ledger.lock"

    @classmethod
    def create(cls, root: Path, historical_path: Path) -> FirstCollectionBudget:
        raw = Path(historical_path).read_bytes()
        historical = json.loads(raw)
        caps = (historical["native_attempt_cap"], historical["teacher_request_cap"], historical["run_wall_cap_s"])
        if caps != (6, 300, 7200):
            raise ValueError("historical_budget_caps_do_not_match_first_batch")
        attempts = historical["native_attempts_started"]
        requests = historical["teacher_inference_requests"]
        wall = historical["conservative_first_start_to_phase_close_wall_s"]
        for value, cap in ((attempts, 6), (requests, 300)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= cap:
                raise ValueError("invalid_historical_count")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(wall) or not 0 <= wall <= 7200:
            raise ValueError("invalid_historical_wall")
        budget = cls(root)
        budget.root.mkdir(parents=True, exist_ok=True)
        with budget._locked():
            if budget.path.exists():
                raise FileExistsError("first_batch_resume_already_exists")
            started = time.monotonic()
            budget._write({
                "schema": "tacharness.first-collection.online-budget.v1",
                "historical_sha256": hashlib.sha256(raw).hexdigest(),
                "historical_native_attempts": attempts,
                "historical_teacher_requests": requests,
                "historical_run_wall_s": wall,
                "native_attempt_cap": 6, "teacher_request_cap": 300,
                "run_wall_cap_s": 7200,
                "native_attempts_started": attempts,
                "teacher_inference_requests": requests,
                "resumed_started_at": _utc(),
                "resumed_started_monotonic_s": started,
                "resumed_deadline_monotonic_s": started + 7200 - wall,
                "resumed_boot_id": _boot_id(),
                "resumed_wall_s": 0.0,
                "run_wall_used_s": wall,
                "phase": "online_first_batch_active",
                "accounting": "historical_conservative_wall_plus_continuous_resumed_window",
                "closed_at": None,
                "close_reason": None,
                "reservations": [],
            })
        return budget

    @classmethod
    def open(cls, root: Path) -> FirstCollectionBudget:
        budget = cls(root)
        budget.snapshot()  # Validate and account elapsed wall; never starts over.
        return budget

    @contextmanager
    def _locked(self):
        with self.lock_path.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        value = json.loads(self.path.read_text())
        if value.get("schema") != "tacharness.first-collection.online-budget.v1":
            raise ValueError("invalid_first_batch_ledger")
        if not value["closed_at"]:
            elapsed_utc = (datetime.now(timezone.utc) - datetime.fromisoformat(value["resumed_started_at"])).total_seconds()
            elapsed = elapsed_utc
            if value["resumed_boot_id"] == _boot_id():
                elapsed = max(elapsed, time.monotonic() - value["resumed_started_monotonic_s"])
            value["resumed_wall_s"] = max(value["resumed_wall_s"], elapsed, 0.0)
            value["run_wall_used_s"] = value["historical_run_wall_s"] + value["resumed_wall_s"]
        value["native_attempts_remaining"] = max(0, value["native_attempt_cap"] - value["native_attempts_started"])
        value["teacher_requests_remaining"] = max(0, value["teacher_request_cap"] - value["teacher_inference_requests"])
        value["run_wall_remaining_s"] = max(0.0, value["run_wall_cap_s"] - value["run_wall_used_s"])
        return value

    def _write(self, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=".budget-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            value = self._read()
            self._write(value)
            return value

    def remaining_wall_s(self) -> float:
        value = self.snapshot()
        return 0.0 if value["closed_at"] else value["run_wall_remaining_s"]

    def _reserve(self, kind: str, count_key: str, cap_key: str, output: Path | None = None) -> dict[str, Any]:
        with self._locked():
            value = self._read()
            reason = None
            if value["closed_at"]:
                reason = "first_batch_closed"
            elif value["run_wall_remaining_s"] <= 0:
                reason = "run_wall_budget_exhausted"
            elif value[count_key] >= value[cap_key]:
                reason = kind + "_budget_exhausted"
            elif kind == "native_attempt" and value["teacher_requests_remaining"] <= 0:
                reason = "teacher_request_budget_exhausted"
            if reason:
                self._write(value)
                raise BudgetExhausted(reason)
            value[count_key] += 1
            reservation = {"kind": kind, "ordinal": value[count_key], "reserved_at": _utc()}
            if output is not None:
                reservation["output"] = str(Path(output).resolve())
            value["reservations"].append(reservation)
            self._write(value)
            return value["reservations"][-1]

    def reserve_request(self) -> dict[str, Any]:
        return self._reserve("teacher_request", "teacher_inference_requests", "teacher_request_cap")

    def reserve_native_attempt(self, output: Path | None = None) -> dict[str, Any]:
        return self._reserve("native_attempt", "native_attempts_started", "native_attempt_cap", output)

    def close(self, reason: str = "completed") -> dict[str, Any]:
        if not isinstance(reason, str) or not reason or not reason.replace("_", "").isalnum():
            raise ValueError("invalid_budget_close_reason")
        with self._locked():
            value = self._read()
            if not value["closed_at"]:
                value["closed_at"] = _utc()
                value["close_reason"] = reason
                value["phase"] = "online_first_batch_closed"
                self._write(value)
            return value
