from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from engine.core.atomic_io import atomic_write_text
from engine.core.clock import now_utc
from engine.core.instance import Instance
from engine.core.paths import SystemPaths
from engine.protocol.models import ErrorJournalEntry
from engine.protocol.writer import write_error_journal_entry


def build_error_journal_path(paths: SystemPaths, instance: Instance) -> Path:
    return paths.account_journal_dir(instance.account_id) / instance.error_journal_filename()


def append_error_journal_entry(paths: SystemPaths, instance: Instance, entry: ErrorJournalEntry) -> None:
    journal_path = build_error_journal_path(paths, instance)
    paths.ensure_account_directories(instance.account_id)
    if journal_path.exists():
        existing = journal_path.read_text(encoding="utf-8")
    else:
        existing = ""
    line = write_error_journal_entry(entry)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    suffix = "" if line.endswith("\n") else "\n"
    atomic_write_text(journal_path, f"{existing}{separator}{line}{suffix}")


def log_error(
    paths: SystemPaths,
    instance: Instance,
    *,
    module: str,
    error_type: str,
    message: str,
    context: dict[str, object] | None = None,
) -> ErrorJournalEntry:
    entry = ErrorJournalEntry(
        error_id=str(uuid4()),
        timestamp_utc=now_utc(),
        account_id=instance.account_id,
        symbol=instance.symbol,
        magic=instance.magic,
        module=module,
        error_type=error_type,
        message=message,
        context=context,
    )
    append_error_journal_entry(paths, instance, entry)
    return entry
