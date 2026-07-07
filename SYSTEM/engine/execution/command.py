from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from engine.protocol.constants import Decision, OrderAction, RiskResult, Side
from engine.protocol.errors import ValidationError

if TYPE_CHECKING:
    from engine.decision.engine import DecisionResult
    from engine.risk.engine import RiskEngineResult

MODULE_NAME = "execution.command"


def _validation_error(message: str, **context: object) -> ValidationError:
    return ValidationError(message, module=MODULE_NAME, context=dict(context))


@dataclass(frozen=True)
class OrderCommand:
    command_id: str
    action: str
    reason: str
    decision_id: str
    side: str | None = None
    volume: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    ticket: int | None = None


def _none_command(
    *,
    command_id: str,
    reason: str,
    decision_id: str,
) -> OrderCommand:
    return OrderCommand(
        command_id=command_id,
        action=OrderAction.NONE.value,
        reason=reason,
        decision_id=decision_id,
    )


def _open_command(
    *,
    command_id: str,
    side: str,
    volume: float,
    stop_loss: float,
    take_profit: float,
    reason: str,
    decision_id: str,
) -> OrderCommand:
    if side not in {Side.BUY.value, Side.SELL.value}:
        raise _validation_error("open command side must be BUY or SELL", side=side)
    if volume <= 0:
        raise _validation_error("open command volume must be > 0", volume=volume)

    return OrderCommand(
        command_id=command_id,
        action=OrderAction.OPEN.value,
        side=side,
        volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason=reason,
        decision_id=decision_id,
    )


def build_order_command(
    decision_result: DecisionResult,
    risk_engine_result: RiskEngineResult,
    *,
    command_id: str | None = None,
) -> OrderCommand:
    resolved_command_id = command_id or str(uuid4())

    if decision_result.decision in {Decision.WAIT.value, Decision.BLOCK.value}:
        return _none_command(
            command_id=resolved_command_id,
            reason=decision_result.reason,
            decision_id=decision_result.decision_id,
        )

    if risk_engine_result.result != RiskResult.ALLOW.value:
        return _none_command(
            command_id=resolved_command_id,
            reason=risk_engine_result.reason or decision_result.reason,
            decision_id=decision_result.decision_id,
        )

    if decision_result.decision not in {Decision.BUY.value, Decision.SELL.value}:
        return _none_command(
            command_id=resolved_command_id,
            reason=decision_result.reason,
            decision_id=decision_result.decision_id,
        )

    if (
        risk_engine_result.position_size is None
        or risk_engine_result.stop_loss is None
        or risk_engine_result.take_profit is None
    ):
        return _none_command(
            command_id=resolved_command_id,
            reason=risk_engine_result.reason or "risk allow missing trade levels",
            decision_id=decision_result.decision_id,
        )

    side = decision_result.preferred_side
    if side not in {Side.BUY.value, Side.SELL.value}:
        return _none_command(
            command_id=resolved_command_id,
            reason=decision_result.reason,
            decision_id=decision_result.decision_id,
        )

    return _open_command(
        command_id=resolved_command_id,
        side=side,
        volume=risk_engine_result.position_size,
        stop_loss=risk_engine_result.stop_loss,
        take_profit=risk_engine_result.take_profit,
        reason=decision_result.reason,
        decision_id=decision_result.decision_id,
    )
