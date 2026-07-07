from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.core.cycle import run_instance_cycle
from engine.core.instance import Instance
from engine.core.lifecycle import startup
from engine.core.paths import SystemPaths
from engine.execution.control_writer import build_control_path
from engine.normalizer.market_normalizer import NormalizedMarketBar
from engine.protocol.constants import AckStatus, OrderAction, Side
from engine.protocol.parser import parse_control
from engine.state.instance_state import InstanceState
from tests.core.config_payload import valid_system_config_payload
from tests.e2e.simulator.mt4_simulator import MT4Simulator, build_market_csv
from tests.core.config_payload import FIXTURE_CYCLE_UTC
from tests.e2e.test_full_cycle import _patch_fixed_command_id, _startup_runtime


def _instance() -> Instance:
    return Instance(account_id="12345", symbol="EURUSD", magic=100001)


def test_e2e_open_modify_cycle_updates_stop_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fixed_command_id(monkeypatch)
    paths = SystemPaths(tmp_path)
    simulator = MT4Simulator(paths)
    instance = _instance()
    runtime = _startup_runtime(tmp_path)
    simulator.export_tick(instance, market_scenario="bullish", timestamp_utc=FIXTURE_CYCLE_UTC)
    simulator.install_auto_ack_hook(monkeypatch)

    open_result = run_instance_cycle(
        runtime,
        instance,
        use_global_universe=False,
        timestamp_utc=FIXTURE_CYCLE_UTC,
    )
    assert open_result.completed
    state = InstanceState.load(paths, instance)
    assert state.open_ticket is not None
    original_stop_loss = state.position_stop_loss
    assert original_stop_loss is not None

    modify_timestamp = "2026-07-07T06:03:00.000Z"
    simulator.export_tick(
        instance,
        market_scenario="bullish",
        timestamp_utc=modify_timestamp,
        close_override=1.10800,
    )
    modify_result = run_instance_cycle(
        runtime,
        instance,
        use_global_universe=False,
        timestamp_utc=modify_timestamp,
    )
    assert modify_result.completed
    assert modify_result.execution_result is not None
    assert modify_result.execution_result.order_command.action == OrderAction.MODIFY.value

    updated_state = InstanceState.load(paths, instance)
    assert updated_state.open_ticket == state.open_ticket
    assert updated_state.position_stop_loss is not None
    assert updated_state.position_stop_loss > original_stop_loss
    assert updated_state.last_ack_status == AckStatus.SUCCESS.value

    control = parse_control(build_control_path(paths, instance).read_text(encoding="utf-8"))
    assert control.action == OrderAction.MODIFY.value


def test_e2e_open_close_cycle_clears_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fixed_command_id(monkeypatch)
    paths = SystemPaths(tmp_path)
    simulator = MT4Simulator(paths)
    instance = _instance()
    runtime = _startup_runtime(tmp_path)
    simulator.export_tick(instance, market_scenario="bullish", timestamp_utc=FIXTURE_CYCLE_UTC)
    simulator.install_auto_ack_hook(monkeypatch)

    open_result = run_instance_cycle(
        runtime,
        instance,
        use_global_universe=False,
        timestamp_utc=FIXTURE_CYCLE_UTC,
    )
    assert open_result.completed
    item = runtime.memory.get_or_create(instance)
    item.instance_state.position_bars_open = 119
    item.instance_state.save(paths)

    close_timestamp = "2026-07-07T06:04:00.000Z"
    simulator.export_tick(instance, market_scenario="bullish", timestamp_utc=close_timestamp)
    close_result = run_instance_cycle(
        runtime,
        instance,
        use_global_universe=False,
        timestamp_utc=close_timestamp,
    )
    assert close_result.completed
    assert close_result.execution_result is not None
    assert close_result.execution_result.order_command.action == OrderAction.CLOSE.value

    cleared_state = InstanceState.load(paths, instance)
    assert cleared_state.open_ticket is None
    assert cleared_state.position_volume is None
    assert cleared_state.last_ack_status == AckStatus.SUCCESS.value
