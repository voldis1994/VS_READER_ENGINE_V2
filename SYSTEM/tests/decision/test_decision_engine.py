from __future__ import annotations

from datetime import datetime, timezone

import pytest

import engine.decision.engine as decision_engine_module
from engine.core.instance import Instance
from engine.core.paths import SystemPaths
from engine.decision.engine import DecisionResult, run_decision_engine
from engine.decision.reason import build_reason
from engine.journal.error_journal import build_error_journal_path
from engine.normalizer.market_normalizer import NormalizedMarketBar
from engine.protocol.constants import (
    REASON_SPREAD_ABNORMAL,
    Decision,
)
from engine.protocol.models import UniverseRecord
from engine.state.instance_state import InstanceState


def _bar(index: int, open_: float, high: float, low: float, close: float) -> NormalizedMarketBar:
    return NormalizedMarketBar(
        time_utc=datetime(2026, 7, 7, 6, index, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        symbol="EURUSD",
        timeframe="M1",
        digits=5,
        point=0.00001,
        bar_index=index,
    )


def _universe() -> UniverseRecord:
    return UniverseRecord(
        schema_version="1.0.0",
        timestamp_utc="2026-07-07T06:00:00.000Z",
        session="LONDON",
        market_regime="trending",
        news_window_active=False,
    )


def _bullish_bars() -> tuple[NormalizedMarketBar, ...]:
    return (
        _bar(0, 1.1000, 1.1020, 1.0990, 1.1015),
        _bar(1, 1.1015, 1.1030, 1.1005, 1.1022),
        _bar(2, 1.1022, 1.1040, 1.1010, 1.1031),
    )


def _buy_invalid_sell_valid_bars() -> tuple[NormalizedMarketBar, ...]:
    return (
        _bar(0, 1.1030, 1.1040, 1.1020, 1.1030),
        _bar(1, 1.1030, 1.1040, 1.1020, 1.1020),
    )


def _sell_invalid_buy_valid_bars() -> tuple[NormalizedMarketBar, ...]:
    return (
        _bar(0, 1.1000, 1.1020, 1.0990, 1.1010),
        _bar(1, 1.1010, 1.1020, 1.1010, 1.1020),
    )


def _weights() -> dict[str, float]:
    return {
        "momentum": 1.0,
        "trend": 1.0,
        "structure": 1.0,
        "pressure": 1.0,
        "behavior": 1.0,
        "impact": 1.0,
        "context": 1.0,
    }


def _instance_state() -> InstanceState:
    state = InstanceState(instance=Instance(account_id="12345", symbol="EURUSD", magic=100001))
    state.update_instrument(digits=5, point=0.00001, pip=0.0001)
    return state


def _engine_kwargs(
    *,
    market_bars: tuple[NormalizedMarketBar, ...],
    relative_spread: float = 1.0,
    spread_threshold: float = 1.5,
    stop_loss_buffer: float = 0.0002,
) -> dict[str, object]:
    return {
        "universe": _universe(),
        "market_bars": market_bars,
        "instance_state": _instance_state(),
        "relative_spread": relative_spread,
        "spread_threshold": spread_threshold,
        "volatility_threshold": 1.5,
        "lookback_bars": 3,
        "block_high_impact_news": True,
        "weights": _weights(),
        "stop_loss_buffer": stop_loss_buffer,
        "reward_ratio": 2.0,
    }


def test_both_directions_are_always_calculated() -> None:
    result = run_decision_engine(**_engine_kwargs(market_bars=_bullish_bars()))

    assert isinstance(result, DecisionResult)
    assert result.buy_candidate is not None
    assert result.sell_candidate is not None
    assert result.buy_score >= 0.0
    assert result.sell_score >= 0.0


def test_sell_is_evaluated_when_buy_is_invalid() -> None:
    result = run_decision_engine(
        **_engine_kwargs(market_bars=_buy_invalid_sell_valid_bars(), stop_loss_buffer=0.0),
    )

    assert not result.buy_candidate.valid
    assert result.sell_candidate.valid
    assert result.decision == Decision.SELL.value


def test_buy_is_evaluated_when_sell_is_invalid() -> None:
    result = run_decision_engine(
        **_engine_kwargs(market_bars=_sell_invalid_buy_valid_bars(), stop_loss_buffer=0.0),
    )

    assert result.buy_candidate.valid
    assert not result.sell_candidate.valid
    assert result.decision == Decision.BUY.value


def test_decision_result_includes_decision_id_and_reason() -> None:
    result = run_decision_engine(**_engine_kwargs(market_bars=_bullish_bars()))

    assert result.decision_id
    assert result.reason
    assert ":" in result.reason


def test_block_reason_produces_block_decision() -> None:
    result = run_decision_engine(
        **_engine_kwargs(market_bars=_bullish_bars()),
        block_reason=build_reason(REASON_SPREAD_ABNORMAL, "relative spread above threshold"),
    )

    assert result.decision == Decision.BLOCK.value
    assert REASON_SPREAD_ABNORMAL in result.reason


def test_equal_scores_can_produce_wait_decision() -> None:
    weights = {
        "momentum": 0.0,
        "trend": 0.0,
        "structure": 0.0,
        "pressure": 0.0,
        "behavior": 0.0,
        "impact": 0.0,
        "context": 1.0,
    }
    kwargs = _engine_kwargs(market_bars=_bullish_bars())
    kwargs["weights"] = weights
    result = run_decision_engine(**kwargs)

    assert result.buy_candidate.valid
    assert result.sell_candidate.valid
    assert result.buy_score == result.sell_score
    assert result.decision == Decision.WAIT.value
    assert "EQUAL_SCORES" in result.reason


def test_decision_engine_logs_error_and_does_not_swallow_exception(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = SystemPaths(root_path=tmp_path)
    instance_state = _instance_state()

    def _raise_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("forced decision engine failure")

    monkeypatch.setattr(decision_engine_module, "run_analysis_engine", _raise_error)

    with pytest.raises(RuntimeError, match="forced decision engine failure"):
        run_decision_engine(
            **_engine_kwargs(market_bars=_bullish_bars()),
            paths=paths,
        )

    journal_path = build_error_journal_path(paths, instance_state.instance)
    journal_text = journal_path.read_text(encoding="utf-8")
    assert "decision engine failed" in journal_text
    assert "forced decision engine failure" in journal_text
