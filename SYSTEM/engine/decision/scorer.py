from __future__ import annotations

from dataclasses import dataclass

from engine.analysis.context import AnalysisContext
from engine.decision.buy import BuyCandidate
from engine.decision.sell import SellCandidate
from engine.protocol.constants import Side


@dataclass(frozen=True)
class ScoringResult:
    buy_score: float
    sell_score: float
    score_delta: float
    preferred_side: str


def _resolve_preferred_side_from_scores(
    *,
    buy_valid: bool,
    sell_valid: bool,
    buy_score: float,
    sell_score: float,
) -> str:
    if buy_valid and sell_valid:
        if buy_score > sell_score:
            return Side.BUY.value
        if sell_score > buy_score:
            return Side.SELL.value
        return Side.NONE.value
    if buy_valid:
        return Side.BUY.value
    if sell_valid:
        return Side.SELL.value
    return Side.NONE.value


def resolve_preferred_side(
    buy_candidate: BuyCandidate,
    sell_candidate: SellCandidate,
) -> str:
    return _resolve_preferred_side_from_scores(
        buy_valid=buy_candidate.valid,
        sell_valid=sell_candidate.valid,
        buy_score=buy_candidate.buy_score,
        sell_score=sell_candidate.sell_score,
    )


def compare_candidates(
    *,
    buy_candidate: BuyCandidate,
    sell_candidate: SellCandidate,
    context: AnalysisContext,
) -> ScoringResult:
    buy_score = buy_candidate.buy_score * context.context_quality
    sell_score = sell_candidate.sell_score * context.context_quality
    preferred_side = _resolve_preferred_side_from_scores(
        buy_valid=buy_candidate.valid,
        sell_valid=sell_candidate.valid,
        buy_score=buy_score,
        sell_score=sell_score,
    )
    return ScoringResult(
        buy_score=buy_score,
        sell_score=sell_score,
        score_delta=buy_score - sell_score,
        preferred_side=preferred_side,
    )
