from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from engine.analysis.engine import AnalysisEngineResult
from engine.decision.filters.news_filter import NewsFilterResult
from engine.decision.filters.spread_filter import SpreadFilterResult
from engine.decision.filters.volatility_filter import VolatilityFilterResult
from engine.decision.reason import build_reason
from engine.normalizer.market_normalizer import NormalizedMarketBar
from engine.protocol.constants import (
    REASON_DATA_INVALID,
    StructureBias,
    TrendDirection,
)
from engine.state.instance_state import InstanceState

_COMPONENT_KEYS = (
    "momentum",
    "trend",
    "structure",
    "pressure",
    "behavior",
    "impact",
    "context",
)


@dataclass(frozen=True)
class SellCandidate:
    valid: bool
    invalid_reason: str | None
    entry_price: float
    stop_loss: float
    take_profit: float
    component_scores: dict[str, float]
    sell_score: float


def _round_price(price: float, digits: int) -> float:
    return round(price, digits)


def build_sell_component_scores(analysis: AnalysisEngineResult) -> dict[str, float]:
    momentum_component = (1.0 - analysis.momentum.momentum_score) / 2.0
    if analysis.momentum.trend_direction == TrendDirection.DOWN.value:
        trend_component = analysis.momentum.trend_strength
    elif analysis.momentum.trend_direction == TrendDirection.UP.value:
        trend_component = 1.0 - analysis.momentum.trend_strength
    else:
        trend_component = 0.5

    if analysis.structure.structure_bias == StructureBias.BEARISH.value:
        structure_component = 1.0
    elif analysis.structure.structure_bias == StructureBias.BULLISH.value:
        structure_component = 0.0
    else:
        structure_component = 0.5

    return {
        "momentum": momentum_component,
        "trend": trend_component,
        "structure": structure_component,
        "pressure": analysis.pressure.sell_pressure,
        "behavior": analysis.behavior.behavior_score,
        "impact": analysis.impact.impact_score,
        "context": analysis.context.context_quality,
    }


def calculate_sell_score(
    component_scores: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    weight_total = sum(weights[key] for key in _COMPONENT_KEYS)
    if weight_total <= 0:
        return 0.0
    return sum(component_scores[key] * weights[key] for key in _COMPONENT_KEYS) / weight_total


def _invalid_candidate(
    *,
    invalid_reason: str,
    component_scores: dict[str, float],
    sell_score: float,
) -> SellCandidate:
    return SellCandidate(
        valid=False,
        invalid_reason=invalid_reason,
        entry_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        component_scores=component_scores,
        sell_score=sell_score,
    )


def calculate_sell_candidate(
    *,
    analysis: AnalysisEngineResult,
    market_bars: tuple[NormalizedMarketBar, ...],
    spread_filter: SpreadFilterResult,
    volatility_filter: VolatilityFilterResult,
    news_filter: NewsFilterResult,
    instance_state: InstanceState,
    weights: Mapping[str, float],
    stop_loss_buffer: float,
    reward_ratio: float,
) -> SellCandidate:
    component_scores = build_sell_component_scores(analysis)
    sell_score = calculate_sell_score(component_scores, weights)

    if not analysis.context.spread_filter_passed:
        return _invalid_candidate(
            invalid_reason=spread_filter.reason or build_reason(
                REASON_DATA_INVALID,
                "spread filter rejected sell setup",
            ),
            component_scores=component_scores,
            sell_score=sell_score,
        )
    if not volatility_filter.volatility_acceptable:
        return _invalid_candidate(
            invalid_reason=volatility_filter.reason or build_reason(
                REASON_DATA_INVALID,
                "volatility filter rejected sell setup",
            ),
            component_scores=component_scores,
            sell_score=sell_score,
        )
    if not news_filter.news_acceptable:
        return _invalid_candidate(
            invalid_reason=news_filter.reason or build_reason(
                REASON_DATA_INVALID,
                "news filter rejected sell setup",
            ),
            component_scores=component_scores,
            sell_score=sell_score,
        )
    if not market_bars:
        return _invalid_candidate(
            invalid_reason=build_reason(REASON_DATA_INVALID, "market bars required for sell setup"),
            component_scores=component_scores,
            sell_score=sell_score,
        )

    digits = instance_state.instrument_digits
    entry_price = _round_price(market_bars[-1].close, digits)
    stop_loss = _round_price(analysis.structure.swing_high + stop_loss_buffer, digits)
    if stop_loss <= entry_price:
        return _invalid_candidate(
            invalid_reason=build_reason(
                REASON_DATA_INVALID,
                "sell stop loss must be above entry price",
                entry_price=entry_price,
                stop_loss=stop_loss,
            ),
            component_scores=component_scores,
            sell_score=sell_score,
        )

    stop_loss_distance = stop_loss - entry_price
    take_profit = _round_price(entry_price - stop_loss_distance * reward_ratio, digits)

    return SellCandidate(
        valid=True,
        invalid_reason=None,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        component_scores=component_scores,
        sell_score=sell_score,
    )
