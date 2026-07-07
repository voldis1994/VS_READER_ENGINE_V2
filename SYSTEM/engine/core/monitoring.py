from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, MutableMapping

from engine.core.alerts import dispatch_cycle_alerts, should_emit_account_not_tradeable_alert
from engine.core.cycle import InstanceCycleResult
from engine.core.instance import Instance
from engine.core.lifecycle import LiveRuntime
from engine.core.logging_setup import log_event
from engine.core.retry import RetryAlertContext, build_retry_policy
from engine.loader.market_loader import load_market_data
from engine.protocol.constants import LogLevel
from engine.protocol.errors import SystemError

MODULE_NAME = "core.monitoring"

INSTANCE_HEALTH_VALID = "VALID"
INSTANCE_HEALTH_BLOCKED = "BLOCKED"
INSTANCE_HEALTH_ERROR = "ERROR"


@dataclass(frozen=True)
class InstanceMonitoringMetrics:
    instance: Instance
    cycle_latency_ms: int | None
    ack_latency_ms: int | None
    data_freshness_ms: int | None
    error_count: int
    instance_health: str


@dataclass
class MonitoringState:
    error_counts: dict[tuple[str, str, int], int] = field(default_factory=dict)


def parse_utc_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compute_elapsed_ms(start_utc: str, end_utc: str) -> int:
    delta = parse_utc_timestamp(end_utc) - parse_utc_timestamp(start_utc)
    return max(0, int(delta.total_seconds() * 1000))


def compute_data_freshness_ms(market_modified_utc: str, current_utc: str) -> int:
    return compute_elapsed_ms(market_modified_utc, current_utc)


def is_data_stale(freshness_ms: int, threshold_ms: int) -> bool:
    if threshold_ms <= 0:
        return False
    return freshness_ms > threshold_ms


def resolve_instance_health(cycle_result: InstanceCycleResult) -> str:
    if cycle_result.error_logged or not cycle_result.completed:
        return INSTANCE_HEALTH_ERROR
    if (
        cycle_result.decision_result is not None
        and cycle_result.decision_result.decision == "BLOCK"
    ):
        return INSTANCE_HEALTH_BLOCKED
    return INSTANCE_HEALTH_VALID


def resolve_ack_latency_ms(
    cycle_result: InstanceCycleResult,
    *,
    measured_ack_latency_ms: int | None,
    ack_timeout_ms: int,
) -> int | None:
    execution_result = cycle_result.execution_result
    if execution_result is None:
        return measured_ack_latency_ms
    interpretation = execution_result.ack_interpretation
    if interpretation is None:
        return measured_ack_latency_ms
    if interpretation.is_timeout:
        return ack_timeout_ms
    if measured_ack_latency_ms is not None:
        return measured_ack_latency_ms
    return None


def record_cycle_error(state: MonitoringState, instance: Instance) -> MonitoringState:
    key = instance.instance_key
    state.error_counts[key] = state.error_counts.get(key, 0) + 1
    return state


def build_instance_metrics(
    instance: Instance,
    cycle_result: InstanceCycleResult,
    *,
    market_modified_utc: str | None,
    measured_ack_latency_ms: int | None,
    ack_timeout_ms: int,
    current_utc: str,
    error_count: int,
) -> InstanceMonitoringMetrics:
    cycle_latency_ms = None
    data_freshness_ms = None
    if market_modified_utc is not None:
        data_freshness_ms = compute_data_freshness_ms(market_modified_utc, current_utc)
        if cycle_result.decision_result is not None:
            cycle_latency_ms = compute_elapsed_ms(
                market_modified_utc,
                cycle_result.timestamp_utc,
            )

    return InstanceMonitoringMetrics(
        instance=instance,
        cycle_latency_ms=cycle_latency_ms,
        ack_latency_ms=resolve_ack_latency_ms(
            cycle_result,
            measured_ack_latency_ms=measured_ack_latency_ms,
            ack_timeout_ms=ack_timeout_ms,
        ),
        data_freshness_ms=data_freshness_ms,
        error_count=error_count,
        instance_health=resolve_instance_health(cycle_result),
    )


def format_metrics_message(metrics: InstanceMonitoringMetrics) -> str:
    instance = metrics.instance
    cycle_latency = "-" if metrics.cycle_latency_ms is None else str(metrics.cycle_latency_ms)
    ack_latency = "-" if metrics.ack_latency_ms is None else str(metrics.ack_latency_ms)
    freshness = "-" if metrics.data_freshness_ms is None else str(metrics.data_freshness_ms)
    return (
        f"metrics account={instance.account_id} symbol={instance.symbol} "
        f"magic={instance.magic} health={metrics.instance_health} "
        f"cycle_latency_ms={cycle_latency} ack_latency_ms={ack_latency} "
        f"data_freshness_ms={freshness} error_count={metrics.error_count}"
    )


def log_instance_metrics(logger, metrics: InstanceMonitoringMetrics) -> None:
    instance = metrics.instance
    log_event(
        logger,
        level=LogLevel.INFO.value,
        module=MODULE_NAME,
        message=format_metrics_message(metrics),
        account_id=instance.account_id,
        symbol=instance.symbol,
        magic=instance.magic,
    )


def observe_instance_cycle(
    runtime: LiveRuntime,
    instance: Instance,
    cycle_result: InstanceCycleResult,
    *,
    cache: MutableMapping[str, Any] | None = None,
    state: MonitoringState | None = None,
    measured_ack_latency_ms: int | None = None,
) -> MonitoringState:
    monitoring_state = state or MonitoringState()
    if cycle_result.error_logged:
        record_cycle_error(monitoring_state, instance)

    market_modified_utc: str | None = None
    retry_policy = build_retry_policy(runtime.config.runtime)
    retry_alert_context = RetryAlertContext(
        logger=runtime.system_logger,
        instance=instance,
        operation="monitoring market load",
    )
    try:
        market_modified_utc = load_market_data(
            runtime.paths,
            instance,
            cache=cache,
            retry_policy=retry_policy,
            retry_alert_context=retry_alert_context,
        ).modified_utc
    except SystemError:
        market_modified_utc = None

    error_count = monitoring_state.error_counts.get(instance.instance_key, 0)
    metrics = build_instance_metrics(
        instance,
        cycle_result,
        market_modified_utc=market_modified_utc,
        measured_ack_latency_ms=measured_ack_latency_ms,
        ack_timeout_ms=runtime.config.runtime.ack_timeout_ms,
        current_utc=cycle_result.timestamp_utc,
        error_count=error_count,
    )
    log_instance_metrics(runtime.system_logger, metrics)

    stale_threshold_ms = runtime.config.runtime.data_stale_threshold_ms
    data_stale = (
        metrics.data_freshness_ms is not None
        and is_data_stale(metrics.data_freshness_ms, stale_threshold_ms)
    )
    ack_timed_out = (
        cycle_result.execution_result is not None
        and cycle_result.execution_result.ack_interpretation is not None
        and cycle_result.execution_result.ack_interpretation.is_timeout
    )
    command_id = None
    if cycle_result.execution_result is not None:
        command_id = cycle_result.execution_result.order_command.command_id

    decision = cycle_result.decision_result.decision if cycle_result.decision_result else None
    reason = cycle_result.decision_result.reason if cycle_result.decision_result else None

    dispatch_cycle_alerts(
        runtime.system_logger,
        instance,
        data_stale=data_stale,
        freshness_ms=metrics.data_freshness_ms,
        stale_threshold_ms=stale_threshold_ms,
        ack_timed_out=ack_timed_out,
        command_id=command_id,
        validation_failed=cycle_result.error_logged,
        validation_message="instance cycle validation failed" if cycle_result.error_logged else None,
        account_not_tradeable=should_emit_account_not_tradeable_alert(decision, reason),
    )
    return monitoring_state


def log_runtime_monitoring_summary(
    runtime: LiveRuntime,
    *,
    instance_count: int,
    completed_count: int,
    failed_count: int,
    total_errors: int,
) -> None:
    log_event(
        runtime.system_logger,
        level=LogLevel.INFO.value,
        module=MODULE_NAME,
        message=(
            f"runtime monitoring summary instances={instance_count} "
            f"completed={completed_count} failed={failed_count} "
            f"error_count={total_errors}"
        ),
    )
