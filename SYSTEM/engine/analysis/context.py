from __future__ import annotations

from dataclasses import dataclass

from engine.normalizer.market_normalizer import NormalizedMarketBar
from engine.protocol.constants import MarketRegime, TradeEnvironment
from engine.protocol.models import UniverseRecord


@dataclass(frozen=True)
class AnalysisContext:
    session: str
    regime: str
    news_active: bool
    context_quality: float
    trade_environment: str


def _resolve_trade_environment(regime: str, news_active: bool) -> str:
    if news_active:
        return TradeEnvironment.HOSTILE.value
    if regime == MarketRegime.TRENDING.value:
        return TradeEnvironment.FAVORABLE.value
    if regime in {MarketRegime.RANGING.value, MarketRegime.QUIET.value}:
        return TradeEnvironment.NEUTRAL.value
    return TradeEnvironment.HOSTILE.value


def _resolve_context_quality(regime: str, news_active: bool, bars: tuple[NormalizedMarketBar, ...]) -> float:
    if news_active:
        return 0.2
    if not bars:
        return 0.4
    if regime == MarketRegime.TRENDING.value:
        return 0.9
    if regime == MarketRegime.RANGING.value:
        return 0.6
    if regime == MarketRegime.QUIET.value:
        return 0.5
    return 0.3


def build_analysis_context(
    universe: UniverseRecord,
    market_bars: tuple[NormalizedMarketBar, ...],
) -> AnalysisContext:
    environment = _resolve_trade_environment(universe.market_regime, universe.news_window_active)
    quality = _resolve_context_quality(universe.market_regime, universe.news_window_active, market_bars)
    return AnalysisContext(
        session=universe.session,
        regime=universe.market_regime,
        news_active=universe.news_window_active,
        context_quality=quality,
        trade_environment=environment,
    )
