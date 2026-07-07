from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from engine.protocol.errors import ExecutionError
from engine.protocol.models import RuntimeConfig

MODULE_NAME = "core.retry"

T = TypeVar("T")


def _execution_error(message: str, **context: object) -> ExecutionError:
    return ExecutionError(message, module=MODULE_NAME, context=dict(context))


@dataclass(frozen=True)
class RetryPolicy:
    retry_max: int
    retry_delay_ms: int


def build_retry_policy(runtime: RuntimeConfig) -> RetryPolicy:
    return RetryPolicy(
        retry_max=runtime.retry_max,
        retry_delay_ms=runtime.retry_delay_ms,
    )


def max_retry_attempts(policy: RetryPolicy) -> int:
    return 1 + policy.retry_max


def validate_control_command_retry(
    *,
    previous_command_id: str,
    command_id: str,
) -> None:
    if previous_command_id == command_id:
        raise _execution_error(
            "control must not be retried with the same command_id",
            previous_command_id=previous_command_id,
            command_id=command_id,
        )


def run_with_retry(
    policy: RetryPolicy,
    operation: Callable[[], T],
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    attempts = max_retry_attempts(policy)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            if policy.retry_delay_ms > 0:
                sleep_fn(policy.retry_delay_ms / 1000.0)

    if last_error is None:
        raise RuntimeError("retry loop ended without result or error")
    raise last_error
