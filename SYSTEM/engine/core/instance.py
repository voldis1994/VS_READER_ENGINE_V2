from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.protocol.constants import (
    FILENAME_ACK,
    FILENAME_CONTROL,
    FILENAME_DECISION_JOURNAL,
    FILENAME_ERROR_JOURNAL,
    FILENAME_INSTANCE_STATE,
    FILENAME_MARKET,
    FILENAME_SENSOR,
    FILENAME_SPREAD_STATE,
    FILENAME_STATUS,
    FILENAME_TRADE_JOURNAL,
)
from engine.protocol.errors import ValidationError

INSTANCE_MODULE = "core.instance"


def _validation_error(message: str, **context: object) -> ValidationError:
    return ValidationError(message, module=INSTANCE_MODULE, context=dict(context))


def _validate_account_id(account_id: str) -> str:
    if not isinstance(account_id, str):
        raise _validation_error(
            "account_id must be a string",
            field="account_id",
            value_type=type(account_id).__name__,
        )
    value = account_id.strip()
    if not value:
        raise _validation_error("account_id must not be empty", field="account_id")
    return value


def _validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise _validation_error(
            "symbol must be a string",
            field="symbol",
            value_type=type(symbol).__name__,
        )
    value = symbol.strip()
    if not value:
        raise _validation_error("symbol must not be empty", field="symbol")
    return value


def _validate_magic(magic: int) -> int:
    if isinstance(magic, bool) or not isinstance(magic, int):
        raise _validation_error(
            "magic must be an integer",
            field="magic",
            value_type=type(magic).__name__,
        )
    if magic < 0:
        raise _validation_error("magic must be >= 0", field="magic", value=magic)
    return magic


@dataclass(frozen=True)
class Instance:
    account_id: str
    symbol: str
    magic: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _validate_account_id(self.account_id))
        object.__setattr__(self, "symbol", _validate_symbol(self.symbol))
        object.__setattr__(self, "magic", _validate_magic(self.magic))

    @property
    def instance_key(self) -> tuple[str, str, int]:
        return (self.account_id, self.symbol, self.magic)

    def matches(self, account_id: str, symbol: str, magic: int) -> bool:
        return self.instance_key == (
            _validate_account_id(account_id),
            _validate_symbol(symbol),
            _validate_magic(magic),
        )

    def market_filename(self) -> str:
        return FILENAME_MARKET.format(symbol=self.symbol, magic=self.magic)

    def sensor_filename(self) -> str:
        return FILENAME_SENSOR.format(symbol=self.symbol, magic=self.magic)

    def control_filename(self) -> str:
        return FILENAME_CONTROL.format(symbol=self.symbol, magic=self.magic)

    def ack_filename(self) -> str:
        return FILENAME_ACK.format(symbol=self.symbol, magic=self.magic)

    def decision_journal_filename(self) -> str:
        return FILENAME_DECISION_JOURNAL.format(symbol=self.symbol, magic=self.magic)

    def trade_journal_filename(self) -> str:
        return FILENAME_TRADE_JOURNAL.format(symbol=self.symbol, magic=self.magic)

    def error_journal_filename(self) -> str:
        return FILENAME_ERROR_JOURNAL.format(symbol=self.symbol, magic=self.magic)

    def instance_state_filename(self) -> str:
        return FILENAME_INSTANCE_STATE.format(symbol=self.symbol, magic=self.magic)

    def spread_state_filename(self) -> str:
        return FILENAME_SPREAD_STATE.format(symbol=self.symbol, magic=self.magic)

    def status_filename(self) -> str:
        return FILENAME_STATUS.format(account_id=self.account_id)


def ensure_unique_instance_keys(instances: Iterable[Instance]) -> None:
    seen: set[tuple[str, str, int]] = set()
    duplicates: list[tuple[str, str, int]] = []
    for instance in instances:
        key = instance.instance_key
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise _validation_error(
            "duplicate instance keys detected",
            duplicates=duplicates,
        )
