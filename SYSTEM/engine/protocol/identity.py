from __future__ import annotations

from engine.protocol.errors import ValidationError


def validate_account_id(account_id: str, module_name: str) -> str:
    if not isinstance(account_id, str):
        raise ValidationError(
            "account_id must be a string",
            module=module_name,
            context={"field": "account_id", "value_type": type(account_id).__name__},
        )
    value = account_id.strip()
    if not value:
        raise ValidationError(
            "account_id must not be empty",
            module=module_name,
            context={"field": "account_id"},
        )
    return value


def validate_symbol(symbol: str, module_name: str) -> str:
    if not isinstance(symbol, str):
        raise ValidationError(
            "symbol must be a string",
            module=module_name,
            context={"field": "symbol", "value_type": type(symbol).__name__},
        )
    value = symbol.strip()
    if not value:
        raise ValidationError(
            "symbol must not be empty",
            module=module_name,
            context={"field": "symbol"},
        )
    return value


def validate_magic(magic: int, module_name: str) -> int:
    if isinstance(magic, bool) or not isinstance(magic, int):
        raise ValidationError(
            "magic must be an integer",
            module=module_name,
            context={"field": "magic", "value_type": type(magic).__name__},
        )
    if magic < 0:
        raise ValidationError(
            "magic must be >= 0",
            module=module_name,
            context={"field": "magic", "value": magic},
        )
    return magic
