from __future__ import annotations

from dataclasses import dataclass

from engine.analysis.behavior import BehaviorAnalysis, analyze_behavior
from engine.analysis.context import AnalysisContext, build_analysis_context, with_spread_filter_passed
from engine.analysis.impact import ImpactAnalysis, analyze_impact
from engine.analysis.momentum import MomentumAnalysis, analyze_momentum_and_trend
from engine.analysis.pressure import PressureAnalysis, analyze_pressure
from engine.analysis.structure import StructureAnalysis, analyze_structure
from engine.normalizer.market_normalizer import NormalizedMarketBar
from engine.protocol.models import UniverseRecord


@dataclass(frozen=True)
class TrendAnalysis:
    trend_direction: str
    trend_strength: float
    trend_duration_bars: int
    higher_highs: bool
    lower_lows: bool


@dataclass(frozen=True)
class AnalysisEngineResult:
    context: AnalysisContext
    structure: StructureAnalysis
    momentum: MomentumAnalysis
    trend: TrendAnalysis
    pressure: PressureAnalysis
    behavior: BehaviorAnalysis
    impact: ImpactAnalysis


def run_analysis_engine(
    universe: UniverseRecord,
    market_bars: tuple[NormalizedMarketBar, ...],
) -> AnalysisEngineResult:
    context = build_analysis_context(universe, market_bars)
    structure = analyze_structure(market_bars)
    momentum = analyze_momentum_and_trend(market_bars)
    pressure = analyze_pressure(market_bars)
    behavior = analyze_behavior(market_bars)
    impact = analyze_impact(
        context=context,
        structure=structure,
        momentum=momentum,
        pressure=pressure,
        behavior=behavior,
    )
    trend = TrendAnalysis(
        trend_direction=momentum.trend_direction,
        trend_strength=momentum.trend_strength,
        trend_duration_bars=momentum.trend_duration_bars,
        higher_highs=momentum.higher_highs,
        lower_lows=momentum.lower_lows,
    )
    return AnalysisEngineResult(
        context=context,
        structure=structure,
        momentum=momentum,
        trend=trend,
        pressure=pressure,
        behavior=behavior,
        impact=impact,
    )


def with_analysis_context(
    analysis: AnalysisEngineResult,
    context: AnalysisContext,
) -> AnalysisEngineResult:
    return AnalysisEngineResult(
        context=context,
        structure=analysis.structure,
        momentum=analysis.momentum,
        trend=analysis.trend,
        pressure=analysis.pressure,
        behavior=analysis.behavior,
        impact=analysis.impact,
    )
