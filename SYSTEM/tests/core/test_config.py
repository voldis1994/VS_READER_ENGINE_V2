from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.core.config import load_system_config, parse_config_payload
from engine.core.paths import SystemPaths
from engine.protocol.constants import CONFIG_SCHEMA_VERSION
from engine.protocol.errors import ConfigurationError


def _valid_payload() -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "system": {
            "name": "SYSTEM",
            "root_path": r"C:\SYSTEM",
            "timeframe": "M1",
        },
        "paths": {
            "clients": "data/clients",
            "logs": "data/logs",
            "cache": "data/cache",
            "history": "data/history",
            "universe": "data/universe",
        },
        "runtime": {
            "cycle_interval_ms": 1000,
            "ack_timeout_ms": 5000,
            "retry_max": 3,
            "retry_delay_ms": 200,
            "data_stale_threshold_ms": 15000,
            "cycle_max_duration_ms": 30000,
            "metrics_interval_ms": 60000,
            "auto_discover_instances": True,
        },
        "instances": [
            {
                "account_id": "12345",
                "symbol": "EURUSD",
                "magic": 100001,
                "enabled": True,
            }
        ],
        "risk": {
            "max_open_positions_per_instance": 1,
            "max_daily_loss_percent": 2.0,
            "max_drawdown_percent": 10.0,
        },
        "analysis": {"lookback_bars": 120},
        "journal": {"retention_days": 30},
        "dashboard": {"refresh_interval_ms": 1000},
        "logging": {"level": "INFO", "format": "standard"},
    }


def test_parse_config_payload_valid_config_loads() -> None:
    config = parse_config_payload(_valid_payload())
    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.system.timeframe == "M1"
    assert len(config.instances) == 1


def test_parse_config_payload_missing_required_field_raises() -> None:
    payload = _valid_payload()
    del payload["runtime"]["ack_timeout_ms"]
    with pytest.raises(ConfigurationError, match="unsupported fields|invalid config payload"):
        parse_config_payload(payload)


def test_parse_config_payload_non_m1_timeframe_raises() -> None:
    payload = _valid_payload()
    payload["system"]["timeframe"] = "H1"
    with pytest.raises(ConfigurationError, match="invalid config payload"):
        parse_config_payload(payload)


def test_parse_config_payload_hard_spread_limits_rejected() -> None:
    payload = _valid_payload()
    payload["risk"]["max_spread_points"] = 30
    with pytest.raises(ConfigurationError, match="hard spread limits"):
        parse_config_payload(payload)


def test_parse_config_payload_hard_symbol_list_rejected() -> None:
    payload = _valid_payload()
    payload["analysis"]["symbols"] = ["EURUSD", "GBPUSD"]
    with pytest.raises(ConfigurationError, match="hard symbol lists"):
        parse_config_payload(payload)


def test_load_system_config_reads_file_successfully(tmp_path: Path) -> None:
    config_path = tmp_path / "system.json"
    config_path.write_text(json.dumps(_valid_payload()), encoding="utf-8")
    config = load_system_config(config_path)
    assert config.system.name == "SYSTEM"


def test_load_system_config_uses_system_paths_default(tmp_path: Path) -> None:
    paths = SystemPaths(tmp_path)
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    paths.config_path.write_text(json.dumps(_valid_payload()), encoding="utf-8")
    config = load_system_config(system_paths=paths)
    assert config.paths.clients == "data/clients"


def test_load_system_config_invalid_json_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "system.json"
    config_path.write_text("{invalid-json", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="invalid JSON"):
        load_system_config(config_path)


def test_load_system_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="failed to read config file"):
        load_system_config(tmp_path / "missing.json")


def test_load_system_config_repository_file() -> None:
    config = load_system_config(Path("config/system.json"))
    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.system.name == "SYSTEM"
    assert config.system.timeframe == "M1"
    assert config.paths.clients == "data/clients"
