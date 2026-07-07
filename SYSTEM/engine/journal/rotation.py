from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.core.atomic_io import atomic_read_text, atomic_write_text
from engine.core.clock import format_utc_timestamp
from engine.core.paths import SystemPaths

MODULE_NAME = "journal.rotation"


@dataclass(frozen=True)
class JournalRotationResult:
    journal_path: Path
    archived_lines: int
    retained_lines: int
    archive_path: Path | None = None


def _parse_journal_timestamp(line: str) -> datetime | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    timestamp = payload.get("timestamp_utc")
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    normalized = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rotate_journal_file(
    journal_path: Path,
    *,
    retention_days: int,
    history_dir: Path,
    current_utc: str | None = None,
) -> JournalRotationResult:
    if not journal_path.exists():
        return JournalRotationResult(
            journal_path=journal_path,
            archived_lines=0,
            retained_lines=0,
        )

    resolved_current = current_utc or format_utc_timestamp(datetime.now(timezone.utc))
    current_time = datetime.fromisoformat(resolved_current.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    cutoff = current_time - timedelta(days=retention_days)

    lines = [line for line in atomic_read_text(journal_path).splitlines() if line.strip()]
    retained: list[str] = []
    archived: list[str] = []
    for line in lines:
        timestamp = _parse_journal_timestamp(line)
        if timestamp is not None and timestamp < cutoff:
            archived.append(line)
        else:
            retained.append(line)

    if not archived:
        return JournalRotationResult(
            journal_path=journal_path,
            archived_lines=0,
            retained_lines=len(retained),
        )

    history_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{journal_path.stem}_{current_time.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    archive_path = history_dir / archive_name
    archive_path.write_text("\n".join(archived) + "\n", encoding="utf-8")

    output = "\n".join(retained)
    if output:
        output = f"{output}\n"
    atomic_write_text(journal_path, output)

    return JournalRotationResult(
        journal_path=journal_path,
        archived_lines=len(archived),
        retained_lines=len(retained),
        archive_path=archive_path,
    )


def rotate_account_journals(
    paths: SystemPaths,
    account_id: str,
    *,
    retention_days: int,
    current_utc: str | None = None,
) -> tuple[JournalRotationResult, ...]:
    journal_dir = paths.account_journal_dir(account_id)
    history_dir = paths.history_dir / account_id / "journals"
    if not journal_dir.is_dir():
        return ()

    results: list[JournalRotationResult] = []
    for journal_path in sorted(journal_dir.glob("*.jsonl")):
        results.append(
            rotate_journal_file(
                journal_path,
                retention_days=retention_days,
                history_dir=history_dir,
                current_utc=current_utc,
            )
        )
    return tuple(results)
