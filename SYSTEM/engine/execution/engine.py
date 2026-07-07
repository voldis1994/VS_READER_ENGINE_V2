from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.core.clock import now_utc
from engine.core.instance import Instance
from engine.core.paths import SystemPaths
from engine.core.retry import validate_control_command_retry
from engine.core.timeout import build_ack_timeout_config, is_ack_timeout_elapsed, log_ack_timeout
from engine.execution.ack_reader import (
    AckInterpretation,
    build_ack_path,
    build_ack_timeout_interpretation,
    interpret_ack,
    read_ack_for_command,
)
from engine.execution.command import OrderCommand, build_order_command
from engine.execution.control_writer import publish_control
from engine.journal.error_journal import log_error
from engine.journal.trade_journal import TradeIntentParams, log_trade_ack, log_trade_intent
from engine.protocol.constants import AckStatus, ErrorType, OrderAction, TradeEvent
from engine.protocol.models import AckRecord, RuntimeConfig, TradeJournalEntry
from engine.state.instance_state import InstanceState

if TYPE_CHECKING:
    from engine.decision.engine import DecisionResult
    from engine.risk.engine import RiskEngineResult

MODULE_NAME = "execution.engine"


@dataclass(frozen=True)
class ExecutionResult:
    order_command: OrderCommand
    control_published: bool
    trade_intent_logged: bool
    ack_interpretation: AckInterpretation | None
    trade_journal_entry: TradeJournalEntry | None
    state_updated: bool


def build_trade_intent_params(order_command: OrderCommand) -> TradeIntentParams:
    return TradeIntentParams(
        command_id=order_command.command_id,
        event=order_command.action,
        reason=order_command.reason,
        side=order_command.side,
        volume=order_command.volume,
        ticket=order_command.ticket,
    )


def wait_for_ack(
    *,
    started_monotonic: float,
    ack_timeout_ms: int,
    ack_available: Callable[[], bool],
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    poll_interval_ms: int = 50,
) -> bool:
    while not is_ack_timeout_elapsed(
        started_monotonic=started_monotonic,
        current_monotonic=monotonic_fn(),
        ack_timeout_ms=ack_timeout_ms,
    ):
        if ack_available():
            return True
        sleep_fn(poll_interval_ms / 1000.0)
    return ack_available()


def apply_ack_to_instance_state(
    instance_state: InstanceState,
    order_command: OrderCommand,
    ack_record: AckRecord,
) -> None:
    instance_state.update_execution(
        command_id=ack_record.command_id,
        ack_status=ack_record.status,
    )
    if (
        ack_record.status == AckStatus.SUCCESS.value
        and order_command.action == OrderAction.OPEN.value
        and ack_record.ticket is not None
        and order_command.side is not None
        and order_command.volume is not None
    ):
        instance_state.update_position(
            open_ticket=ack_record.ticket,
            position_side=order_command.side,
            position_volume=order_command.volume,
        )


def log_ack_failure(
    paths: SystemPaths,
    instance: Instance,
    ack_record: AckRecord,
) -> None:
    if ack_record.status not in {AckStatus.FAILED.value, AckStatus.REJECTED.value}:
        return

    context: dict[str, object] = {
        "command_id": ack_record.command_id,
        "status": ack_record.status,
    }
    if ack_record.error_code is not None:
        context["error_code"] = ack_record.error_code
    if ack_record.error_message is not None:
        context["error_message"] = ack_record.error_message

    log_error(
        paths,
        instance,
        module=MODULE_NAME,
        error_type=ErrorType.EXECUTION.value,
        message=f"execution ack {ack_record.status.lower()}",
        context=context,
    )


def _requires_trade_execution(order_command: OrderCommand) -> bool:
    return order_command.action in {
        OrderAction.OPEN.value,
        OrderAction.MODIFY.value,
        OrderAction.CLOSE.value,
    }


def run_execution_engine(
    *,
    paths: SystemPaths,
    instance: Instance,
    instance_state: InstanceState,
    decision_result: DecisionResult,
    risk_engine_result: RiskEngineResult,
    runtime: RuntimeConfig,
    timestamp_utc: str | None = None,
    started_monotonic: float | None = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    poll_interval_ms: int = 50,
) -> ExecutionResult:
    resolved_timestamp = timestamp_utc or now_utc()
    order_command = build_order_command(decision_result, risk_engine_result)

    if instance_state.last_command_id:
        validate_control_command_retry(
            previous_command_id=instance_state.last_command_id,
            command_id=order_command.command_id,
        )

    publish_control(
        paths,
        instance,
        order_command,
        timestamp_utc=resolved_timestamp,
    )

    if not _requires_trade_execution(order_command):
        return ExecutionResult(
            order_command=order_command,
            control_published=True,
            trade_intent_logged=False,
            ack_interpretation=None,
            trade_journal_entry=None,
            state_updated=False,
        )

    log_trade_intent(
        paths,
        instance,
        build_trade_intent_params(order_command),
        timestamp_utc=resolved_timestamp,
    )

    ack_timeout = build_ack_timeout_config(runtime)
    wait_started = started_monotonic if started_monotonic is not None else monotonic_fn()
    ack_ready = wait_for_ack(
        started_monotonic=wait_started,
        ack_timeout_ms=ack_timeout.ack_timeout_ms,
        ack_available=lambda: build_ack_path(paths, instance).exists(),
        monotonic_fn=monotonic_fn,
        sleep_fn=sleep_fn,
        poll_interval_ms=poll_interval_ms,
    )

    if not ack_ready:
        log_ack_timeout(paths, instance, command_id=order_command.command_id)
        instance_state.update_execution(
            command_id=order_command.command_id,
            ack_status=AckStatus.TIMEOUT.value,
        )
        return ExecutionResult(
            order_command=order_command,
            control_published=True,
            trade_intent_logged=True,
            ack_interpretation=build_ack_timeout_interpretation(command_id=order_command.command_id),
            trade_journal_entry=None,
            state_updated=True,
        )

    ack_record = read_ack_for_command(
        paths,
        instance,
        expected_command_id=order_command.command_id,
    )
    interpretation = interpret_ack(ack_record)
    log_ack_failure(paths, instance, ack_record)
    apply_ack_to_instance_state(instance_state, order_command, ack_record)
    trade_entry = log_trade_ack(
        paths,
        instance,
        ack_record,
        timestamp_utc=resolved_timestamp,
        price=order_command.stop_loss if order_command.action == OrderAction.OPEN.value else None,
    )

    return ExecutionResult(
        order_command=order_command,
        control_published=True,
        trade_intent_logged=True,
        ack_interpretation=interpretation,
        trade_journal_entry=trade_entry,
        state_updated=True,
    )


def execution_engine_performs_analysis() -> bool:
    source = inspect.getsource(run_execution_engine)
    return "engine.analysis" in source or "run_analysis_engine" in source
