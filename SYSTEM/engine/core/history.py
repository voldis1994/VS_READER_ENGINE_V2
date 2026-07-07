from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from engine.core.atomic_io import atomic_read_text
from engine.core.clock import format_utc_timestamp
from engine.core.instance import Instance
from engine.core.paths import SystemPaths
from engine.execution.ack_reader import build_ack_path
from engine.execution.control_writer import build_control_path
from engine.loader.market_loader import build_market_file_path
from engine.protocol.errors import DataIOError

MODULE_NAME = "core.history"


def _history_error(message: str, **context: object) -> DataIOError:
    return DataIOError(message, module=MODULE_NAME, context=dict(context))


def _archive_file(source: Path, destination_dir: Path, *, suffix: str) -> Path | None:
    if not source.exists():
        return None
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = format_utc_timestamp(datetime.now(timezone.utc)).replace(":", "").replace("-", "")
    destination = destination_dir / f"{source.stem}_{timestamp}{suffix}"
    shutil.move(str(source), str(destination))
    return destination


def archive_processed_control(paths: SystemPaths, instance: Instance) -> Path | None:
    control_path = build_control_path(paths, instance)
    destination_dir = paths.instance_history_dir(
        instance.account_id,
        instance.symbol,
        instance.magic,
    )
    return _archive_file(control_path, destination_dir, suffix=".json")


def archive_processed_ack(paths: SystemPaths, instance: Instance) -> Path | None:
    ack_path = build_ack_path(paths, instance)
    destination_dir = paths.instance_history_dir(
        instance.account_id,
        instance.symbol,
        instance.magic,
    )
    return _archive_file(ack_path, destination_dir, suffix=".json")


def archive_market_snapshot(paths: SystemPaths, instance: Instance) -> Path | None:
    market_path = build_market_file_path(paths, instance)
    if not market_path.exists():
        return None
    destination_dir = paths.instance_history_dir(
        instance.account_id,
        instance.symbol,
        instance.magic,
    )
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = format_utc_timestamp(datetime.now(timezone.utc)).replace(":", "").replace("-", "")
    destination = destination_dir / f"market_{instance.symbol}_{instance.magic}_{timestamp}.csv"
    content = atomic_read_text(market_path)
    destination.write_text(content, encoding="utf-8")
    return destination


def find_latest_archived_file(directory: Path, *, prefix: str) -> Path | None:
    if not directory.is_dir():
        return None
    matches = sorted(
        (entry for entry in directory.iterdir() if entry.is_file() and entry.name.startswith(prefix)),
        key=lambda entry: entry.stat().st_mtime,
    )
    if not matches:
        return None
    return matches[-1]


def read_archived_control_text(paths: SystemPaths, instance: Instance) -> str | None:
    history_dir = paths.instance_history_dir(
        instance.account_id,
        instance.symbol,
        instance.magic,
    )
    archived = find_latest_archived_file(history_dir, prefix="control_")
    if archived is None:
        return None
    return atomic_read_text(archived)
