from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.core.paths import SystemPaths
from engine.protocol.errors import ConfigurationError, ProtocolError
from engine.protocol.models import SystemConfig
from engine.protocol.parser import parse_system_config

CONFIG_MODULE = "core.config"
CONFIG_ENCODING = "utf-8"

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "system",
        "paths",
        "runtime",
        "instances",
        "risk",
        "analysis",
        "journal",
        "dashboard",
        "logging",
    }
)
_SYSTEM_FIELDS = frozenset({"name", "root_path", "timeframe"})
_PATHS_FIELDS = frozenset({"clients", "logs", "cache", "history", "universe"})
_RUNTIME_FIELDS = frozenset(
    {
        "cycle_interval_ms",
        "ack_timeout_ms",
        "retry_max",
        "retry_delay_ms",
        "data_stale_threshold_ms",
        "cycle_max_duration_ms",
        "metrics_interval_ms",
        "auto_discover_instances",
    }
)
_INSTANCE_FIELDS = frozenset({"account_id", "symbol", "magic", "enabled"})
_RISK_FIELDS = frozenset(
    {
        "max_open_positions_per_instance",
        "max_daily_loss_percent",
        "max_drawdown_percent",
    }
)
_ANALYSIS_FIELDS = frozenset({"lookback_bars"})
_JOURNAL_FIELDS = frozenset({"retention_days"})
_DASHBOARD_FIELDS = frozenset({"refresh_interval_ms"})
_LOGGING_FIELDS = frozenset({"level", "format"})


def _config_error(message: str, **context: object) -> ConfigurationError:
    return ConfigurationError(message, module=CONFIG_MODULE, context=dict(context))


def _ensure_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _config_error(
            f"{field_name} must be an object",
            field=field_name,
            value_type=type(value).__name__,
        )
    return value


def _assert_exact_fields(
    data: dict[str, Any],
    expected: frozenset[str],
    field_name: str,
) -> None:
    unknown = sorted(set(data.keys()) - expected)
    if unknown:
        raise _config_error(
            f"{field_name} contains unsupported fields",
            field=field_name,
            unknown_fields=unknown,
        )


def _assert_no_forbidden_fields(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise _config_error(
                    "config keys must be strings",
                    field_path=path,
                    key_type=type(key).__name__,
                )
            key_lower = key.lower()
            field_path = f"{path}.{key}"
            if "spread" in key_lower and ("max" in key_lower or "limit" in key_lower):
                raise _config_error(
                    "hard spread limits are forbidden",
                    field_path=field_path,
                )
            if key_lower in {"digits", "point", "pip", "pip_value"}:
                raise _config_error(
                    "hard instrument parameters are forbidden",
                    field_path=field_path,
                )
            if ("symbol" in key_lower or "instrument" in key_lower) and isinstance(
                nested_value,
                list,
            ):
                raise _config_error(
                    "hard symbol lists are forbidden",
                    field_path=field_path,
                )
            _assert_no_forbidden_fields(nested_value, field_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_fields(item, f"{path}[{index}]")


def _assert_schema_shape(payload: dict[str, Any]) -> None:
    _assert_exact_fields(payload, _TOP_LEVEL_FIELDS, "config")
    _assert_exact_fields(_ensure_mapping(payload["system"], "system"), _SYSTEM_FIELDS, "system")
    _assert_exact_fields(_ensure_mapping(payload["paths"], "paths"), _PATHS_FIELDS, "paths")
    _assert_exact_fields(_ensure_mapping(payload["runtime"], "runtime"), _RUNTIME_FIELDS, "runtime")
    instances = payload["instances"]
    if not isinstance(instances, list):
        raise _config_error(
            "instances must be a list",
            field="instances",
            value_type=type(instances).__name__,
        )
    for index, item in enumerate(instances):
        item_mapping = _ensure_mapping(item, f"instances[{index}]")
        _assert_exact_fields(item_mapping, _INSTANCE_FIELDS, f"instances[{index}]")
    _assert_exact_fields(_ensure_mapping(payload["risk"], "risk"), _RISK_FIELDS, "risk")
    _assert_exact_fields(
        _ensure_mapping(payload["analysis"], "analysis"),
        _ANALYSIS_FIELDS,
        "analysis",
    )
    _assert_exact_fields(_ensure_mapping(payload["journal"], "journal"), _JOURNAL_FIELDS, "journal")
    _assert_exact_fields(
        _ensure_mapping(payload["dashboard"], "dashboard"),
        _DASHBOARD_FIELDS,
        "dashboard",
    )
    _assert_exact_fields(_ensure_mapping(payload["logging"], "logging"), _LOGGING_FIELDS, "logging")


def parse_config_payload(payload: dict[str, Any]) -> SystemConfig:
    if not isinstance(payload, dict):
        raise _config_error(
            "config payload must be an object",
            field="config",
            value_type=type(payload).__name__,
        )
    _assert_no_forbidden_fields(payload)
    _assert_schema_shape(payload)
    try:
        return parse_system_config(payload)
    except ProtocolError as exc:
        raise _config_error(
            "invalid config payload",
            protocol_message=exc.message,
            protocol_context=exc.context,
        ) from exc


def load_system_config(
    config_path: str | Path | None = None,
    *,
    system_paths: SystemPaths | None = None,
) -> SystemConfig:
    resolved_path = (
        Path(config_path)
        if config_path is not None
        else (system_paths.config_path if system_paths is not None else SystemPaths().config_path)
    )
    try:
        text = resolved_path.read_text(encoding=CONFIG_ENCODING)
    except OSError as exc:
        raise _config_error(
            "failed to read config file",
            path=str(resolved_path),
            error=str(exc),
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _config_error(
            "config file contains invalid JSON",
            path=str(resolved_path),
            error=str(exc),
        ) from exc
    if not isinstance(payload, dict):
        raise _config_error(
            "config file root must be an object",
            path=str(resolved_path),
            root_type=type(payload).__name__,
        )
    return parse_config_payload(payload)
