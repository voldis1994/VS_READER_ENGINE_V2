from __future__ import annotations

import json
import os
import re
import socket
import urllib.request
from dataclasses import dataclass
from typing import Any

from engine.protocol.constants import Decision, RiskResult
from engine.protocol.errors import SystemError
from engine.risk.engine import RiskEngineResult

MODULE_NAME = "ai.decision_layer"


@dataclass(frozen=True)
class AIDecision:
    bias: str  # BULLISH|BEARISH|NEUTRAL|AVOID
    confidence: float
    allow_buy: bool
    allow_sell: bool
    allow_close: bool
    reason: str


_BIAS_ALLOWED = {"BULLISH", "BEARISH", "NEUTRAL", "AVOID"}


def _json_extract(text: str) -> str | None:
    """
    Try to extract a JSON object from arbitrary text.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(0)


def parse_ai_decision_json(text: str) -> AIDecision | None:
    """
    Parse the AI response JSON and validate the required schema.
    Returns None if invalid.
    """
    extracted = _json_extract(text)
    if extracted is None:
        return None
    try:
        payload = json.loads(extracted)
    except Exception:
        return None

    try:
        bias = str(payload["bias"])
        confidence = float(payload["confidence"])
        allow_buy = bool(payload["allow_buy"])
        allow_sell = bool(payload["allow_sell"])
        allow_close = bool(payload["allow_close"])
        reason = str(payload["reason"])
    except Exception:
        return None

    if bias not in _BIAS_ALLOWED:
        return None
    if confidence < 0.0 or confidence > 1.0:
        return None
    if not reason:
        return None

    return AIDecision(
        bias=bias,
        confidence=confidence,
        allow_buy=allow_buy,
        allow_sell=allow_sell,
        allow_close=allow_close,
        reason=reason,
    )


def _build_openai_prompt(*, system_signal: str, market_context: dict[str, Any]) -> str:
    context_text = json.dumps(market_context, ensure_ascii=False, default=str)
    return (
        "You are a strict decision layer for a trading system.\n"
        "You must output ONLY valid JSON with this exact schema:\n"
        '{\n'
        '  "bias": "BULLISH|BEARISH|NEUTRAL|AVOID",\n'
        '  "confidence": 0.0, \n'
        '  "allow_buy": true, \n'
        '  "allow_sell": false, \n'
        '  "allow_close": true, \n'
        '  "reason": "..." \n'
        "}\n\n"
        "Rules reminder:\n"
        "- If you say bias=AVOID, the final decision must be BLOCK.\n"
        "- If you set allow_buy/allow_sell to false, the system signal must be blocked.\n"
        "- Do NOT output any additional keys.\n"
        "- Output MUST be parseable JSON.\n\n"
        f"System signal: {system_signal}\n"
        f"Market context: {context_text}\n"
    )


def _call_openai(*, api_key: str, prompt: str, timeout_s: int) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    data = {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": "Return strictly valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    # Ensure socket-level timeout even if urllib internals differ by platform.
    socket.setdefaulttimeout(timeout_s)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
    finally:
        # Reset to default for safety.
        socket.setdefaulttimeout(None)

    obj = json.loads(raw)
    content = obj["choices"][0]["message"]["content"]
    return str(content)


def get_ai_decision(*, system_signal: str, market_context: dict[str, Any]) -> AIDecision | None:
    """
    Call OpenAI and return parsed AIDecision.

    On any API error/timeout/missing key/invalid JSON:
    - returns None (caller must BLOCK).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    prompt = _build_openai_prompt(system_signal=system_signal, market_context=market_context)

    try:
        content = _call_openai(api_key=api_key, prompt=prompt, timeout_s=10)
    except (socket.timeout, TimeoutError):
        return None
    except Exception:
        return None

    return parse_ai_decision_json(content)


def decide_final_decision(
    *,
    system_signal: str,
    ai_decision: AIDecision | None,
    risk_engine_result: RiskEngineResult,
) -> tuple[str, str]:
    """
    Final decision rules:
    1) If SYSTEM=BUY and AI allow_buy=true and risk=PASS => final BUY
    2) If SYSTEM=SELL and AI allow_sell=true and risk=PASS => final SELL
    3) If AI says AVOID => final BLOCK
    4) If AI rejects system signal => final WAIT or BLOCK.
       For this project we map rejection to BLOCK (tests require BLOCK).
    5) AI API error/timeout/no response => final BLOCK
    6) AI never bypasses risk engine: risk is always last safety check.
    7) Risk engine is last: risk FAIL => final BLOCK even if AI allows.
    """
    if ai_decision is None:
        return Decision.BLOCK.value, "AI_ERROR: no response/timeout"
    if ai_decision.bias == "AVOID":
        return Decision.BLOCK.value, f"AI_AVOID: {ai_decision.reason}"

    # Risk is always required to allow BUY/SELL.
    risk_pass = risk_engine_result.result == RiskResult.ALLOW.value
    if system_signal == Decision.BUY.value:
        if not ai_decision.allow_buy:
            return Decision.BLOCK.value, f"AI_REJECT_BUY: {ai_decision.reason}"
        if risk_pass:
            return Decision.BUY.value, f"AI_ALLOW_BUY: {ai_decision.reason}"
        return Decision.BLOCK.value, "RISK_FAIL: risk rules blocked"

    if system_signal == Decision.SELL.value:
        if not ai_decision.allow_sell:
            return Decision.BLOCK.value, f"AI_REJECT_SELL: {ai_decision.reason}"
        if risk_pass:
            return Decision.SELL.value, f"AI_ALLOW_SELL: {ai_decision.reason}"
        return Decision.BLOCK.value, "RISK_FAIL: risk rules blocked"

    # For WAIT/BLOCK, AI AVOID already handled; keep system decision.
    return system_signal, "SYSTEM_SIGNAL: unchanged"


def apply_ai_to_decision_result(
    *,
    decision_result: Any,
    ai_decision: AIDecision | None,
    risk_engine_result: RiskEngineResult,
) -> Any:
    """
    Create a new DecisionResult with updated `decision` and `reason`.

    `decision_result` is treated as an Any to avoid importing DecisionResult at module
    load time (keeps imports stable and avoids circular dependency risk).
    """
    final_decision, final_reason = decide_final_decision(
        system_signal=decision_result.decision,
        ai_decision=ai_decision,
        risk_engine_result=risk_engine_result,
    )
    # Preserve system-provided reason for WAIT/BLOCK when AI does not explicitly
    # force AVOID. This prevents breaking existing tests that assert specific
    # decision reasons generated by the SYSTEM decision engine.
    if (
        final_decision == decision_result.decision
        and decision_result.decision in {Decision.WAIT.value, Decision.BLOCK.value}
        and ai_decision is not None
        and ai_decision.bias != "AVOID"
    ):
        return decision_result
    if final_decision == decision_result.decision and final_reason == decision_result.reason:
        return decision_result

    # Re-create frozen dataclass with changed fields.
    return decision_result.__class__(
        decision_id=decision_result.decision_id,
        decision=final_decision,
        reason=final_reason,
        preferred_side=decision_result.preferred_side,
        buy_candidate=decision_result.buy_candidate,
        sell_candidate=decision_result.sell_candidate,
        buy_score=decision_result.buy_score,
        sell_score=decision_result.sell_score,
        analysis_context=decision_result.analysis_context,
    )

