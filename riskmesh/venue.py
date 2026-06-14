"""End-to-end RiskMesh venue orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal

from riskmesh.clearing import ClearingEngine, MatchResult
from riskmesh.contracts import BinaryContract, ContractStatus, TriggerDirection
from riskmesh.forecasters import (
    FORECASTER_PROFILES,
    BeliefAggregator,
    BeliefQuote,
    Forecast,
    GeminiForecaster,
    HeuristicForecaster,
)
from riskmesh.ledger import AccountRole, Ledger
from riskmesh.market import ReplayPriceFeed
from riskmesh.reputation import ReputationBook
from riskmesh.settlement import ReplayOracle, SettlementEngine, SettlementResult

HEDGER_ID = "hedge-bot"
VENUE_ID = "riskmesh-venue"


@dataclass(frozen=True, slots=True)
class VenueEvent:
    sequence: int
    tick: int
    kind: str
    message: str
    amount: Decimal | None = None


class RiskMeshVenue:
    def __init__(
        self,
        *,
        start_tick: int = 12,
        fee_rate: Decimal | str | float = Decimal("0.02"),
        warmup_reputation: bool = True,
    ) -> None:
        self.feed = ReplayPriceFeed.from_csv()
        self.feed.reset(start_tick)
        self.ledger = Ledger()
        self.ledger.create_account(
            HEDGER_ID, "Inventory Hedge Bot", AccountRole.HEDGER, "150"
        )
        for profile in FORECASTER_PROFILES:
            self.ledger.create_account(
                profile.agent_id,
                profile.display_name,
                AccountRole.RISK_TAKER,
                "100",
            )
        self.ledger.create_account(VENUE_ID, "RiskMesh Venue", AccountRole.VENUE, "0")

        self.reputation = ReputationBook()
        for profile in FORECASTER_PROFILES:
            self.reputation.register(profile.agent_id, profile.display_name)
        if warmup_reputation:
            self._warmup_reputation()

        self.aggregator = BeliefAggregator()
        self.clearing = ClearingEngine(
            self.ledger, venue_account_id=VENUE_ID, fee_rate=fee_rate
        )
        self.settlement = SettlementEngine(self.ledger, ReplayOracle(self.feed))
        self.contracts: dict[str, BinaryContract] = {}
        self.belief_history: list[BeliefQuote] = []
        self.pricing_quotes: dict[str, BeliefQuote] = {}
        self.settlements: list[SettlementResult] = []
        self.events: list[VenueEvent] = []
        self.active_contract_id: str | None = None
        self._event_sequence = 0
        self._emit(
            "system",
            f"Venue online at replay tick {self.feed.current.tick}; "
            f"BTCUSDT ${self.feed.current.close:,.2f}",
        )

    @property
    def active_contract(self) -> BinaryContract | None:
        if self.active_contract_id is None:
            return None
        return self.contracts[self.active_contract_id]

    @property
    def latest_quote(self) -> BeliefQuote | None:
        if not self.belief_history:
            return None
        quote = self.belief_history[-1]
        if self.active_contract_id == quote.contract_id:
            return quote
        return None

    def open_contract(
        self,
        *,
        duration_ticks: int = 6,
        notional: Decimal | str | float = Decimal("25"),
        strike_offset: Decimal | str | float = Decimal("20"),
        direction: TriggerDirection = TriggerDirection.ABOVE,
    ) -> BinaryContract:
        if (
            self.active_contract is not None
            and self.active_contract.status is not ContractStatus.SETTLED
        ):
            raise ValueError("Settle the active contract before opening another")
        expiry_tick = self.feed.current.tick + duration_ticks
        if expiry_tick >= len(self.feed.points):
            raise ValueError("Not enough replay data for this expiry")
        contract = BinaryContract(
            underlying="BTCUSDT",
            strike=self.feed.current.close + Decimal(str(strike_offset)),
            created_tick=self.feed.current.tick,
            expiry_tick=expiry_tick,
            notional=Decimal(str(notional)),
            hedger_id=HEDGER_ID,
            direction=direction,
        )
        self.contracts[contract.contract_id] = contract
        self.active_contract_id = contract.contract_id
        self._emit(
            "contract",
            f"{contract.contract_id}: pays ${contract.notional} if BTCUSDT closes "
            f"{direction.value} ${contract.strike:,.2f} at tick {expiry_tick}",
        )
        return contract

    def refresh_beliefs(self, *, use_gemini: bool = False) -> BeliefQuote:
        contract = self.active_contract
        if contract is None or contract.status is ContractStatus.SETTLED:
            raise ValueError("No active contract to forecast")
        history = self.feed.history(12)
        forecasts = self._run_forecasters(
            contract, history, tick=self.feed.current.tick, use_gemini=use_gemini
        )
        weights = self.reputation.weights(
            tuple(profile.agent_id for profile in FORECASTER_PROFILES)
        )
        quote = self.aggregator.aggregate(contract, forecasts, weights=weights)
        self.belief_history.append(quote)
        source = "Gemini agents" if use_gemini else "local replay agents"
        self._emit(
            "belief",
            f"{source}: fair probability {quote.probability:.1%}, "
            f"premium ${quote.fair_premium}, dispersion {quote.dispersion:.1%}",
            quote.fair_premium,
        )
        return quote

    def match_active(self, *, risk_taker_id: str | None = None) -> MatchResult:
        contract = self.active_contract
        quote = self.latest_quote
        if contract is None or quote is None:
            raise ValueError("Open and price a contract before matching")
        selected_taker = risk_taker_id or self._select_risk_taker(quote, contract)
        result = self.clearing.match(
            contract,
            risk_taker_id=selected_taker,
            quote=quote,
            tick=self.feed.current.tick,
        )
        self.pricing_quotes[contract.contract_id] = quote
        self._emit(
            "match",
            f"{selected_taker} accepted {contract.contract_id}; "
            f"${result.collateral_locked} collateral locked, "
            f"${result.premium} premium paid",
            result.premium,
        )
        if result.venue_fee > 0:
            self._emit(
                "fee",
                f"RiskMesh earned ${result.venue_fee} clearing fee",
                result.venue_fee,
            )
        return result

    def advance(self, *, use_gemini: bool = False) -> BeliefQuote | SettlementResult | None:
        point = self.feed.advance()
        self._emit("oracle", f"Replay oracle tick {point.tick}: BTCUSDT ${point.close:,.2f}")
        contract = self.active_contract
        if contract is None or contract.status is ContractStatus.SETTLED:
            return None
        if point.tick >= contract.expiry_tick:
            if contract.status is not ContractStatus.MATCHED:
                raise ValueError("Active contract expired before it was matched")
            return self._settle_active()
        return self.refresh_beliefs(use_gemini=use_gemini)

    def run_demo(self, *, use_gemini: bool = False) -> SettlementResult:
        self.open_contract()
        self.refresh_beliefs(use_gemini=use_gemini)
        self.match_active()
        while self.active_contract and self.active_contract.status is not ContractStatus.SETTLED:
            self.advance(use_gemini=False)
        return self.settlements[-1]

    def leaderboard_rows(self) -> list[dict[str, object]]:
        rows = []
        for reputation in self.reputation.leaderboard():
            account = self.ledger.account(reputation.agent_id)
            rows.append(
                {
                    "agent": reputation.display_name,
                    "calibration": float(reputation.calibration_score),
                    "mean_brier": (
                        float(reputation.mean_brier)
                        if reputation.mean_brier is not None
                        else None
                    ),
                    "weight": float(reputation.belief_weight),
                    "forecasts": reputation.forecasts_scored,
                    "pnl": float(account.pnl),
                    "available": float(account.available),
                    "locked": float(account.locked),
                }
            )
        return rows

    def _settle_active(self) -> SettlementResult:
        contract = self.active_contract
        if contract is None:
            raise ValueError("No active contract")
        result = self.settlement.settle(contract, current_tick=self.feed.current.tick)
        priced_quote = self.pricing_quotes[contract.contract_id]
        self.reputation.score_forecasts(
            priced_quote.forecasts,
            outcome=result.outcome,
            tick=result.settlement_tick,
        )
        self.settlements.append(result)
        outcome_text = "TRIGGERED" if result.outcome else "NOT TRIGGERED"
        self._emit(
            "settlement",
            f"{contract.contract_id} {outcome_text} at ${result.settlement_price:,.2f}; "
            f"${result.payout} payout, winner {result.winner_id}",
            result.payout,
        )
        self._emit("reputation", "Calibration scores and future belief weights updated")
        return result

    def _select_risk_taker(
        self, quote: BeliefQuote, contract: BinaryContract
    ) -> str:
        candidates = [
            forecast
            for forecast in quote.forecasts
            if self.ledger.account(forecast.agent_id).available >= contract.max_payout
        ]
        if not candidates:
            raise ValueError("No forecasting agent can fully collateralize this contract")
        return min(candidates, key=lambda forecast: forecast.probability).agent_id

    def _run_forecasters(
        self,
        contract: BinaryContract,
        history: list,
        *,
        tick: int,
        use_gemini: bool,
    ) -> list[Forecast]:
        if not use_gemini:
            return [
                HeuristicForecaster(profile).forecast(contract, history, tick=tick)
                for profile in FORECASTER_PROFILES
            ]

        forecasts_by_id: dict[str, Forecast] = {}
        with ThreadPoolExecutor(max_workers=len(FORECASTER_PROFILES)) as executor:
            futures = {
                executor.submit(
                    GeminiForecaster(profile).forecast,
                    contract,
                    history,
                    tick=tick,
                ): profile
                for profile in FORECASTER_PROFILES
            }
            for future in as_completed(futures):
                profile = futures[future]
                try:
                    forecasts_by_id[profile.agent_id] = future.result()
                except Exception as exc:
                    forecasts_by_id[profile.agent_id] = HeuristicForecaster(profile).forecast(
                        contract, history, tick=tick
                    )
                    self._emit(
                        "fallback",
                        f"{profile.display_name} used deterministic fallback "
                        f"after {type(exc).__name__}",
                    )
        return [forecasts_by_id[profile.agent_id] for profile in FORECASTER_PROFILES]

    def _warmup_reputation(self) -> None:
        for origin_tick in (3, 5, 7, 9):
            expiry_tick = origin_tick + 2
            origin = self.feed.point_at(origin_tick)
            offset = Decimal("8") if origin_tick % 4 == 1 else Decimal("-8")
            contract = BinaryContract(
                underlying="BTCUSDT",
                strike=origin.close + offset,
                created_tick=origin_tick,
                expiry_tick=expiry_tick,
                notional=Decimal("10"),
                hedger_id=HEDGER_ID,
                contract_id=f"PRE-{origin_tick:02d}",
            )
            history = self.feed.points[max(0, origin_tick - 9) : origin_tick + 1]
            forecasts = [
                HeuristicForecaster(profile).forecast(
                    contract, history, tick=origin_tick
                )
                for profile in FORECASTER_PROFILES
            ]
            outcome = contract.is_triggered(self.feed.point_at(expiry_tick).close)
            self.reputation.score_forecasts(
                forecasts, outcome=outcome, tick=expiry_tick
            )

    def _emit(self, kind: str, message: str, amount: Decimal | None = None) -> None:
        self._event_sequence += 1
        self.events.append(
            VenueEvent(
                sequence=self._event_sequence,
                tick=self.feed.current.tick,
                kind=kind,
                message=message,
                amount=amount,
            )
        )
