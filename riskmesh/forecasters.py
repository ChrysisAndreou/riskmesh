"""Gemini-driven forecasting agents with deterministic stage-demo fallbacks."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean, pstdev

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from riskmesh.contracts import BinaryContract, TriggerDirection
from riskmesh.market import PricePoint

DEFAULT_MODEL = "gemini-3.5-flash"
MIN_PROBABILITY = Decimal("0.02")
MAX_PROBABILITY = Decimal("0.98")


@dataclass(frozen=True, slots=True)
class ForecasterProfile:
    agent_id: str
    display_name: str
    mandate: str
    focus: str
    lookback: int
    momentum_weight: float
    bias: float = 0.0


FORECASTER_PROFILES = (
    ForecasterProfile(
        "momentum",
        "Momentum-7",
        "You are a short-horizon momentum trader. Follow persistent direction, but quantify risk.",
        "closing-price momentum and acceleration",
        7,
        0.85,
        0.04,
    ),
    ForecasterProfile(
        "mean_reversion",
        "Revert-9",
        "You are a mean-reversion specialist. Fade stretched moves toward the local average.",
        "distance from rolling mean",
        9,
        -0.65,
        -0.02,
    ),
    ForecasterProfile(
        "volatility",
        "VolGuard",
        "You price event probability from realized range and changing short-horizon volatility.",
        "high-low ranges and volatility regime",
        6,
        0.15,
        0.02,
    ),
    ForecasterProfile(
        "flow",
        "FlowLens",
        "You infer pressure from candle direction and volume concentration.",
        "signed volume and candle bodies",
        8,
        0.45,
        0.0,
    ),
    ForecasterProfile(
        "skeptic",
        "BaseRate",
        "You are a conservative calibration expert. Resist weak signals and stay near base rates.",
        "base rates and signal uncertainty",
        10,
        0.08,
        -0.03,
    ),
)


class ForecastPayload(BaseModel):
    probability: float = Field(ge=0.02, le=0.98)
    rationale: str = Field(min_length=5, max_length=180)


@dataclass(frozen=True, slots=True)
class Forecast:
    agent_id: str
    agent_name: str
    contract_id: str
    tick: int
    probability: Decimal
    rationale: str
    source: str


@dataclass(frozen=True, slots=True)
class BeliefQuote:
    contract_id: str
    tick: int
    probability: Decimal
    fair_premium: Decimal
    dispersion: Decimal
    forecasts: tuple[Forecast, ...]
    weights: dict[str, Decimal]


class GeminiForecaster:
    def __init__(
        self,
        profile: ForecasterProfile,
        *,
        model: str = DEFAULT_MODEL,
        client: genai.Client | None = None,
    ) -> None:
        load_dotenv()
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is missing")
        self.profile = profile
        self.model = model
        self.client = client or genai.Client()

    def forecast(
        self,
        contract: BinaryContract,
        history: list[PricePoint],
        *,
        tick: int,
    ) -> Forecast:
        prompt = _forecast_prompt(self.profile, contract, history, tick)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.profile.mandate,
                temperature=0.25,
                max_output_tokens=512,
                response_mime_type="application/json",
                response_schema=ForecastPayload,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        payload = response.parsed
        if isinstance(payload, ForecastPayload):
            parsed = payload
        elif payload is None and response.text:
            parsed = ForecastPayload.model_validate_json(response.text)
        else:
            parsed = ForecastPayload.model_validate(payload)
        return Forecast(
            agent_id=self.profile.agent_id,
            agent_name=self.profile.display_name,
            contract_id=contract.contract_id,
            tick=tick,
            probability=_probability(parsed.probability),
            rationale=parsed.rationale,
            source=f"Gemini {self.model}",
        )


class HeuristicForecaster:
    """Deterministic fallback that mirrors each Gemini agent's assigned signal."""

    def __init__(self, profile: ForecasterProfile) -> None:
        self.profile = profile

    def forecast(
        self,
        contract: BinaryContract,
        history: list[PricePoint],
        *,
        tick: int,
    ) -> Forecast:
        window = history[-self.profile.lookback :]
        closes = [float(point.close) for point in window]
        current = closes[-1]
        returns = [
            (closes[index] - closes[index - 1]) / closes[index - 1]
            for index in range(1, len(closes))
        ]
        average_move = max(fmean(abs(value) for value in returns), 0.00015) if returns else 0.0003
        momentum = (current - closes[0]) / closes[0] if len(closes) > 1 else 0.0
        horizon = max(contract.expiry_tick - tick, 1)
        scaled_distance = (float(contract.strike) - current) / current
        uncertainty = average_move * math.sqrt(horizon)
        signal = (
            -scaled_distance / uncertainty
            + self.profile.momentum_weight * momentum / average_move
            + self.profile.bias
        )
        probability_above = 1 / (1 + math.exp(-max(min(signal, 8), -8)))
        probability = (
            probability_above
            if contract.direction is TriggerDirection.ABOVE
            else 1 - probability_above
        )
        return Forecast(
            agent_id=self.profile.agent_id,
            agent_name=self.profile.display_name,
            contract_id=contract.contract_id,
            tick=tick,
            probability=_probability(probability),
            rationale=(
                f"{self.profile.focus}; signal={signal:+.2f}, "
                f"horizon={horizon} replay ticks"
            ),
            source="deterministic fallback",
        )


class BeliefAggregator:
    def aggregate(
        self,
        contract: BinaryContract,
        forecasts: list[Forecast],
        *,
        weights: dict[str, Decimal | str | float] | None = None,
    ) -> BeliefQuote:
        if not forecasts:
            raise ValueError("At least one forecast is required")
        if any(forecast.contract_id != contract.contract_id for forecast in forecasts):
            raise ValueError("Cannot aggregate forecasts from different contracts")

        resolved_weights = {
            forecast.agent_id: Decimal(str((weights or {}).get(forecast.agent_id, 1)))
            for forecast in forecasts
        }
        if any(weight <= 0 for weight in resolved_weights.values()):
            raise ValueError("Belief weights must be positive")
        total_weight = sum(resolved_weights.values(), Decimal("0"))
        blended = sum(
            (
                forecast.probability * resolved_weights[forecast.agent_id]
                for forecast in forecasts
            ),
            Decimal("0"),
        ) / total_weight
        premium = (blended * contract.notional).quantize(Decimal("0.01"), ROUND_HALF_UP)
        dispersion = Decimal(
            str(pstdev(float(forecast.probability) for forecast in forecasts))
        ).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        return BeliefQuote(
            contract_id=contract.contract_id,
            tick=max(forecast.tick for forecast in forecasts),
            probability=blended.quantize(Decimal("0.0001"), ROUND_HALF_UP),
            fair_premium=premium,
            dispersion=dispersion,
            forecasts=tuple(forecasts),
            weights=resolved_weights,
        )


def _forecast_prompt(
    profile: ForecasterProfile,
    contract: BinaryContract,
    history: list[PricePoint],
    tick: int,
) -> str:
    window = history[-profile.lookback :]
    rows = "\n".join(
        (
            f"tick={point.tick}, close={point.close}, high={point.high}, "
            f"low={point.low}, volume={point.volume}"
        )
        for point in window
    )
    return f"""Estimate the probability that this binary micro-risk contract triggers.
Contract: {contract.underlying} closes {contract.direction.value} {contract.strike}
at replay tick {contract.expiry_tick}. Current tick: {tick}.
Your exclusive signal focus: {profile.focus}.
Only use the market context below. Return a calibrated probability, not a trading command.

Market context:
{rows}
"""


def _probability(value: Decimal | float | str) -> Decimal:
    probability = Decimal(str(value))
    probability = min(max(probability, MIN_PROBABILITY), MAX_PROBABILITY)
    return probability.quantize(Decimal("0.0001"), ROUND_HALF_UP)
