from __future__ import annotations

import pytest

from engine.ai_decision_layer import (
    AIDecision,
    decide_final_decision,
    get_ai_decision,
)
from engine.protocol.constants import Decision, RiskResult
from engine.risk.engine import RiskEngineResult


def _risk_allow() -> RiskEngineResult:
    return RiskEngineResult(
        result=RiskResult.ALLOW.value,
        reason="",
        position_size=0.1,
        stop_loss=1.09,
        take_profit=1.11,
    )


def _risk_block() -> RiskEngineResult:
    return RiskEngineResult(
        result=RiskResult.BLOCK.value,
        reason="rules blocked",
        position_size=None,
        stop_loss=None,
        take_profit=None,
    )


def _ai(
    *,
    bias: str = "NEUTRAL",
    confidence: float = 0.8,
    allow_buy: bool = True,
    allow_sell: bool = False,
    allow_close: bool = True,
    reason: str = "ai ok",
) -> AIDecision:
    return AIDecision(
        bias=bias,
        confidence=confidence,
        allow_buy=allow_buy,
        allow_sell=allow_sell,
        allow_close=allow_close,
        reason=reason,
    )


def test_buy_ai_allows_risk_pass_final_buy() -> None:
    ai = _ai(allow_buy=True)
    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BUY.value


def test_buy_ai_rejects_final_block() -> None:
    ai = _ai(allow_buy=False)
    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_sell_ai_allows_risk_pass_final_sell() -> None:
    ai = _ai(bias="NEUTRAL", allow_buy=False, allow_sell=True)
    decision, _reason = decide_final_decision(
        system_signal=Decision.SELL.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.SELL.value


def test_sell_ai_rejects_final_block() -> None:
    ai = _ai(allow_buy=False, allow_sell=False)
    decision, _reason = decide_final_decision(
        system_signal=Decision.SELL.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_ai_avoid_final_block() -> None:
    ai = _ai(bias="AVOID", allow_buy=True, allow_sell=True)
    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_ai_timeout_returns_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force AI layer to treat timeout as no decision.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from engine import ai_decision_layer as mdl

    def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError("timeout")

    monkeypatch.setattr(mdl, "_call_openai", _raise_timeout)
    ai = get_ai_decision(system_signal=Decision.BUY.value, market_context={})
    assert ai is None

    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_ai_invalid_json_returns_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from engine import ai_decision_layer as mdl

    monkeypatch.setattr(mdl, "_call_openai", lambda *_a, **_k: "NOT_JSON")
    ai = get_ai_decision(system_signal=Decision.BUY.value, market_context={})
    assert ai is None

    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_ai_api_error_returns_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from engine import ai_decision_layer as mdl

    def _raise_error(*_args, **_kwargs):
        raise RuntimeError("api error")

    monkeypatch.setattr(mdl, "_call_openai", _raise_error)
    ai = get_ai_decision(system_signal=Decision.BUY.value, market_context={})
    assert ai is None

    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_allow(),
    )
    assert decision == Decision.BLOCK.value


def test_risk_fail_always_blocks_even_if_ai_allows() -> None:
    ai = _ai(allow_buy=True)
    decision, _reason = decide_final_decision(
        system_signal=Decision.BUY.value,
        ai_decision=ai,
        risk_engine_result=_risk_block(),
    )
    assert decision == Decision.BLOCK.value

