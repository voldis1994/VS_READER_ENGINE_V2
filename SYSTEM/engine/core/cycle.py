from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from engine.analysis.structure import StructureAnalysis, analyze_structure
from engine.core.clock import now_utc
from engine.core.instance import Instance
from engine.core.lifecycle import LiveRuntime
from engine.core.paths import SystemPaths
from engine.decision.engine import DecisionResult, run_decision_engine
from engine.execution.engine import ExecutionResult, run_execution_engine
from engine.journal.decision_journal import log_decision
from engine.journal.error_journal import log_error
from engine.loader.market_loader import RawMarketData, load_market_data
from engine.loader.sensor_loader import RawSensorData, load_sensor_data
from engine.loader.status_loader import RawStatusData, load_status_data
from engine.loader.universe_loader import RawUniverseData, load_universe_data
from engine.normalizer.instrument_params import derive_instrument_params, detect_params_change
from engine.normalizer.market_normalizer import NormalizedMarketBar, normalize_market_csv
from engine.normalizer.spread_model import SpreadModelSnapshot, update_spread_model_from_sensor
from engine.protocol.constants import (
    Decision,
    ErrorType,
    REASON_ACCOUNT_NOT_TRADEABLE,
    RiskResult,
)
from engine.protocol.errors import DataIOError, SystemError
from engine.protocol.models import SensorReading, StatusRecord, UniverseRecord
from engine.protocol.parser import parse_sensor_csv, parse_universe
from engine.reason import build_reason
from engine.risk.engine import RiskEngineResult, RiskEngineTradeParams, run_risk_engine
from engine.state.memory import InstanceMemory
from engine.validator.market_validator import ValidationResult, validate_market_csv
from engine.validator.sensor_validator import validate_sensor_csv
from engine.validator.status_validator import StatusValidationResult, validate_status_json
from engine.validator.universe_validator import validate_universe_json

MODULE_NAME = "core.cycle"

DEFAULT_MAX_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_VOLUME_STEP = 0.01
DEFAULT_MAX_STOP_LOSS_PIPS = 100.0


@dataclass(frozen=True)
class InstanceCycleData:
    market_raw: RawMarketData
    sensor_raw: RawSensorData
    status_raw: RawStatusData
    universe_raw: RawUniverseData


@dataclass(frozen=True)
class InstanceCycleResult:
    instance: Instance
    timestamp_utc: str
    completed: bool
    error_logged: bool
    decision_result: DecisionResult | None = None
    risk_engine_result: RiskEngineResult | None = None
    decision_journal_logged: bool = False
    execution_result: ExecutionResult | None = None
    trade_executed: bool = False


def build_risk_trade_params() -> RiskEngineTradeParams:
    return RiskEngineTradeParams(
        max_risk_per_trade_percent=DEFAULT_MAX_RISK_PER_TRADE_PERCENT,
        volume_step=DEFAULT_VOLUME_STEP,
        max_stop_loss_pips=DEFAULT_MAX_STOP_LOSS_PIPS,
    )


def resolve_use_global_universe(paths: SystemPaths) -> bool:
    return paths.universe_file.exists()


def load_instance_cycle_data(
    paths: SystemPaths,
    instance: Instance,
    *,
    use_global_universe: bool | None = None,
    cache: MutableMapping[str, Any] | None = None,
) -> InstanceCycleData:
    resolved_use_global = (
        resolve_use_global_universe(paths)
        if use_global_universe is None
        else use_global_universe
    )
    return InstanceCycleData(
        market_raw=load_market_data(paths, instance, cache=cache),
        sensor_raw=load_sensor_data(paths, instance, cache=cache),
        status_raw=load_status_data(paths, instance.account_id, cache=cache),
        universe_raw=load_universe_data(
            paths,
            instance.account_id,
            use_global_universe=resolved_use_global,
            cache=cache,
        ),
    )


def validate_market_for_cycle(market_raw: RawMarketData) -> tuple[NormalizedMarketBar, ...] | ValidationResult:
    validation = validate_market_csv(market_raw.raw_text)
    if not validation.is_valid:
        return validation
    return normalize_market_csv(market_raw.raw_text)


def validate_sensor_for_cycle(sensor_raw: RawSensorData) -> SensorReading | ValidationResult:
    validation = validate_sensor_csv(sensor_raw.raw_text)
    if not validation.is_valid:
        return validation
    readings = parse_sensor_csv(sensor_raw.raw_text)
    if not readings:
        return ValidationResult(
            status=validation.status,
            errors=("sensor csv contains no readings",),
            row_count=0,
        )
    return readings[-1]


def validate_status_for_cycle(status_raw: RawStatusData) -> StatusValidationResult:
    return validate_status_json(status_raw.raw_text)


def validate_universe_for_cycle(universe_raw: RawUniverseData) -> UniverseRecord | ValidationResult:
    validation = validate_universe_json(universe_raw.raw_text)
    if not validation.is_valid:
        return validation
    return parse_universe(universe_raw.raw_text)


def build_account_block_reason(status: StatusRecord) -> str | None:
    if status.connected and status.trade_allowed:
        return None
    return build_reason(REASON_ACCOUNT_NOT_TRADEABLE, "account is not tradeable")


def update_instance_instrument_state(
    instance_memory: InstanceMemory,
    market_bars: tuple[NormalizedMarketBar, ...],
) -> None:
    params = derive_instrument_params(market_bars)
    current_digits = instance_memory.instance_state.instrument_digits
    current_point = instance_memory.instance_state.instrument_point
    if current_digits > 0 and current_point > 0:
        from engine.normalizer.instrument_params import InstrumentParams

        if not detect_params_change(
            InstrumentParams(
                symbol=instance_memory.instance.symbol,
                digits=current_digits,
                point=current_point,
                pip=instance_memory.instance_state.instrument_pip,
            ),
            params,
        ):
            return
    instance_memory.instance_state.update_instrument(
        digits=params.digits,
        point=params.point,
        pip=params.pip,
    )


def update_instance_spread_model(
    *,
    instance_memory: InstanceMemory,
    spread_models: dict[tuple[str, str, int], SpreadModelSnapshot],
    sensor_reading: SensorReading,
    lookback_bars: int,
    timestamp_utc: str,
) -> SpreadModelSnapshot:
    key = instance_memory.instance.instance_key
    existing = spread_models.get(key)
    history = existing.history if existing is not None else ()
    snapshot = update_spread_model_from_sensor(
        history,
        sensor_reading,
        lookback_bars=lookback_bars,
    )
    spread_models[key] = snapshot
    instance_memory.spread_state.update_from_snapshot(snapshot, timestamp_utc)
    return snapshot


def resolve_structure_levels(
    market_bars: tuple[NormalizedMarketBar, ...],
) -> StructureAnalysis:
    return analyze_structure(market_bars)


def run_instance_decision_phase(
    *,
    universe: UniverseRecord,
    market_bars: tuple[NormalizedMarketBar, ...],
    instance_memory: InstanceMemory,
    relative_spread: float,
    runtime: LiveRuntime,
    block_reason: str | None = None,
) -> DecisionResult:
    return run_decision_engine(
        universe=universe,
        market_bars=market_bars,
        instance_state=instance_memory.instance_state,
        relative_spread=relative_spread,
        system_config=runtime.config,
        block_reason=block_reason,
        paths=runtime.paths,
    )


def run_instance_risk_phase(
    *,
    decision_result: DecisionResult,
    instance_memory: InstanceMemory,
    status: StatusRecord,
    market_bars: tuple[NormalizedMarketBar, ...],
    runtime: LiveRuntime,
    trade_params: RiskEngineTradeParams | None = None,
) -> RiskEngineResult:
    structure = resolve_structure_levels(market_bars)
    return run_risk_engine(
        decision_result=decision_result,
        risk_config=runtime.config.risk,
        instance_state=instance_memory.instance_state,
        status=status,
        trade_params=trade_params or build_risk_trade_params(),
        swing_low=structure.swing_low,
        swing_high=structure.swing_high,
    )


def should_execute_trade(
    *,
    runtime: LiveRuntime,
    decision_result: DecisionResult,
    risk_engine_result: RiskEngineResult,
) -> bool:
    if not runtime.allow_control_writes:
        return False
    if decision_result.decision not in {Decision.BUY.value, Decision.SELL.value}:
        return False
    return risk_engine_result.result == RiskResult.ALLOW.value


def _log_cycle_error(
    paths: SystemPaths,
    instance: Instance,
    *,
    message: str,
    context: dict[str, object] | None = None,
) -> None:
    log_error(
        paths,
        instance,
        module=MODULE_NAME,
        error_type=ErrorType.VALIDATION.value,
        message=message,
        context=context,
    )


def _finalize_cycle_state(
    *,
    instance_memory: InstanceMemory,
    runtime: LiveRuntime,
    decision_result: DecisionResult,
    timestamp_utc: str,
) -> None:
    instance_memory.instance_state.update_cycle(
        decision=decision_result.decision,
        reason=decision_result.reason,
        cycle_utc=timestamp_utc,
    )
    instance_memory.instance_state.save(runtime.paths)
    if instance_memory.spread_state.record is not None:
        instance_memory.spread_state.save(runtime.paths)


def run_instance_cycle(
    runtime: LiveRuntime,
    instance: Instance,
    *,
    use_global_universe: bool | None = None,
    trade_params: RiskEngineTradeParams | None = None,
    timestamp_utc: str | None = None,
    cache: MutableMapping[str, Any] | None = None,
) -> InstanceCycleResult:
    resolved_timestamp = timestamp_utc or now_utc()
    instance_memory = runtime.memory.get_or_create(instance)

    try:
        loaded = load_instance_cycle_data(
            runtime.paths,
            instance,
            use_global_universe=use_global_universe,
            cache=cache,
        )
    except DataIOError as exc:
        _log_cycle_error(
            runtime.paths,
            instance,
            message="failed to load instance cycle data",
            context={"error": str(exc)},
        )
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )

    market_result = validate_market_for_cycle(loaded.market_raw)
    if isinstance(market_result, ValidationResult):
        _log_cycle_error(
            runtime.paths,
            instance,
            message="market validation failed",
            context={"errors": list(market_result.errors)},
        )
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )
    market_bars = market_result

    sensor_result = validate_sensor_for_cycle(loaded.sensor_raw)
    if isinstance(sensor_result, ValidationResult):
        _log_cycle_error(
            runtime.paths,
            instance,
            message="sensor validation failed",
            context={"errors": list(sensor_result.errors)},
        )
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )
    sensor_reading = sensor_result

    status_result = validate_status_for_cycle(loaded.status_raw)
    if not status_result.is_valid or status_result.record is None:
        _log_cycle_error(
            runtime.paths,
            instance,
            message="status validation failed",
            context={"errors": list(status_result.errors)},
        )
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )
    status = status_result.record

    universe_result = validate_universe_for_cycle(loaded.universe_raw)
    if isinstance(universe_result, ValidationResult):
        _log_cycle_error(
            runtime.paths,
            instance,
            message="universe validation failed",
            context={"errors": list(universe_result.errors)},
        )
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )
    universe = universe_result

    update_instance_instrument_state(instance_memory, market_bars)
    spread_snapshot = update_instance_spread_model(
        instance_memory=instance_memory,
        spread_models=runtime.spread_models,
        sensor_reading=sensor_reading,
        lookback_bars=runtime.config.analysis.lookback_bars,
        timestamp_utc=resolved_timestamp,
    )

    block_reason = build_account_block_reason(status)
    try:
        decision_result = run_instance_decision_phase(
            universe=universe,
            market_bars=market_bars,
            instance_memory=instance_memory,
            relative_spread=spread_snapshot.relative_spread,
            runtime=runtime,
            block_reason=block_reason,
        )
        risk_engine_result = run_instance_risk_phase(
            decision_result=decision_result,
            instance_memory=instance_memory,
            status=status,
            market_bars=market_bars,
            runtime=runtime,
            trade_params=trade_params,
        )
    except SystemError:
        return InstanceCycleResult(
            instance=instance,
            timestamp_utc=resolved_timestamp,
            completed=False,
            error_logged=True,
        )

    log_decision(
        runtime.paths,
        instance,
        decision_result,
        risk_engine_result,
        timestamp_utc=resolved_timestamp,
    )

    execution_result: ExecutionResult | None = None
    trade_executed = False
    if runtime.allow_control_writes:
        execution_result = run_execution_engine(
            paths=runtime.paths,
            instance=instance,
            instance_state=instance_memory.instance_state,
            decision_result=decision_result,
            risk_engine_result=risk_engine_result,
            runtime=runtime.config.runtime,
            timestamp_utc=resolved_timestamp,
        )
        trade_executed = should_execute_trade(
            runtime=runtime,
            decision_result=decision_result,
            risk_engine_result=risk_engine_result,
        )

    _finalize_cycle_state(
        instance_memory=instance_memory,
        runtime=runtime,
        decision_result=decision_result,
        timestamp_utc=resolved_timestamp,
    )

    return InstanceCycleResult(
        instance=instance,
        timestamp_utc=resolved_timestamp,
        completed=True,
        error_logged=False,
        decision_result=decision_result,
        risk_engine_result=risk_engine_result,
        decision_journal_logged=True,
        execution_result=execution_result,
        trade_executed=trade_executed,
    )
