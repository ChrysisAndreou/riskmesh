"""Forecast calibration scoring and reputation-derived belief weights."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from riskmesh.forecasters import Forecast


@dataclass(frozen=True, slots=True)
class ForecastScore:
    contract_id: str
    agent_id: str
    probability: Decimal
    outcome: bool
    brier_score: Decimal
    tick: int


@dataclass(slots=True)
class AgentReputation:
    agent_id: str
    display_name: str
    forecasts_scored: int = 0
    brier_total: Decimal = Decimal("0")
    last_brier: Decimal | None = None

    @property
    def mean_brier(self) -> Decimal | None:
        if self.forecasts_scored == 0:
            return None
        return (self.brier_total / self.forecasts_scored).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )

    @property
    def calibration_score(self) -> Decimal:
        if self.mean_brier is None:
            return Decimal("0.5000")
        return (Decimal("1") - self.mean_brier).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )

    @property
    def belief_weight(self) -> Decimal:
        if self.forecasts_scored == 0:
            return Decimal("1.0000")
        weight = Decimal("0.5") + Decimal("2.5") * self.calibration_score
        return weight.quantize(Decimal("0.0001"), ROUND_HALF_UP)


@dataclass(slots=True)
class ReputationBook:
    agents: dict[str, AgentReputation] = field(default_factory=dict)
    scores: list[ForecastScore] = field(default_factory=list)
    _scored_keys: set[tuple[str, str]] = field(default_factory=set)

    def register(self, agent_id: str, display_name: str) -> AgentReputation:
        reputation = self.agents.get(agent_id)
        if reputation is None:
            reputation = AgentReputation(agent_id=agent_id, display_name=display_name)
            self.agents[agent_id] = reputation
        return reputation

    def score_forecasts(
        self,
        forecasts: list[Forecast] | tuple[Forecast, ...],
        *,
        outcome: bool,
        tick: int,
    ) -> list[ForecastScore]:
        scored: list[ForecastScore] = []
        realized = Decimal("1") if outcome else Decimal("0")
        for forecast in forecasts:
            key = (forecast.contract_id, forecast.agent_id)
            if key in self._scored_keys:
                raise ValueError(
                    f"Forecast already scored: {forecast.contract_id}/{forecast.agent_id}"
                )
            brier = ((forecast.probability - realized) ** 2).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
            reputation = self.register(forecast.agent_id, forecast.agent_name)
            reputation.forecasts_scored += 1
            reputation.brier_total += brier
            reputation.last_brier = brier
            score = ForecastScore(
                contract_id=forecast.contract_id,
                agent_id=forecast.agent_id,
                probability=forecast.probability,
                outcome=outcome,
                brier_score=brier,
                tick=tick,
            )
            self._scored_keys.add(key)
            self.scores.append(score)
            scored.append(score)
        return scored

    def weights(self, agent_ids: list[str] | tuple[str, ...]) -> dict[str, Decimal]:
        return {
            agent_id: self.agents.get(
                agent_id, AgentReputation(agent_id, agent_id)
            ).belief_weight
            for agent_id in agent_ids
        }

    def leaderboard(self) -> list[AgentReputation]:
        return sorted(
            self.agents.values(),
            key=lambda reputation: (
                reputation.calibration_score,
                reputation.forecasts_scored,
            ),
            reverse=True,
        )
