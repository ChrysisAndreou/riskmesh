"""Agent-to-agent matching and fully collateralized clearing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from riskmesh.contracts import BinaryContract, ContractError, ContractStatus
from riskmesh.forecasters import BeliefQuote
from riskmesh.ledger import InsufficientFunds, Ledger


@dataclass(frozen=True, slots=True)
class CollateralPosition:
    contract_id: str
    risk_taker_id: str
    amount: Decimal
    locked_tick: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    contract_id: str
    hedger_id: str
    risk_taker_id: str
    fair_probability: Decimal
    premium: Decimal
    venue_fee: Decimal
    collateral_locked: Decimal
    tick: int


class ClearingEngine:
    def __init__(
        self,
        ledger: Ledger,
        *,
        venue_account_id: str | None = None,
        fee_rate: Decimal | str | float = Decimal("0.02"),
    ) -> None:
        self.ledger = ledger
        self.venue_account_id = venue_account_id
        self.fee_rate = Decimal(str(fee_rate))
        if self.fee_rate < 0 or self.fee_rate >= 1:
            raise ValueError("Fee rate must be between zero and one")
        if self.venue_account_id is not None:
            self.ledger.account(self.venue_account_id)
        self.collateral: dict[str, CollateralPosition] = {}

    def match(
        self,
        contract: BinaryContract,
        *,
        risk_taker_id: str,
        quote: BeliefQuote,
        tick: int,
    ) -> MatchResult:
        if contract.status is not ContractStatus.OPEN:
            raise ContractError(f"Cannot match contract in {contract.status} state")
        if quote.contract_id != contract.contract_id:
            raise ContractError("Belief quote does not belong to this contract")
        if tick >= contract.expiry_tick:
            raise ContractError("Cannot match an expired contract")
        if risk_taker_id == contract.hedger_id:
            raise ContractError("Hedger and risk-taker must be different agents")

        hedger = self.ledger.account(contract.hedger_id)
        risk_taker = self.ledger.account(risk_taker_id)
        if hedger.available < quote.fair_premium:
            raise InsufficientFunds(
                f"{contract.hedger_id} cannot fund premium {quote.fair_premium}"
            )
        if risk_taker.available < contract.max_payout:
            raise InsufficientFunds(
                f"{risk_taker_id} cannot fully collateralize {contract.max_payout}"
            )

        venue_fee = Decimal("0")
        if self.venue_account_id is not None:
            venue_fee = (quote.fair_premium * self.fee_rate).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )
        taker_premium = quote.fair_premium - venue_fee

        self.ledger.lock(
            risk_taker_id,
            contract.max_payout,
            note=f"{contract.contract_id} maximum payout collateral",
            tick=tick,
        )
        if taker_premium > 0:
            self.ledger.transfer(
                contract.hedger_id,
                risk_taker_id,
                taker_premium,
                note=f"{contract.contract_id} net risk premium",
                tick=tick,
            )
        if venue_fee > 0 and self.venue_account_id is not None:
            self.ledger.transfer(
                contract.hedger_id,
                self.venue_account_id,
                venue_fee,
                note=f"{contract.contract_id} venue fee",
                tick=tick,
            )
        contract.mark_matched(
            risk_taker_id=risk_taker_id,
            fair_probability=quote.probability,
            premium=quote.fair_premium,
            venue_fee=venue_fee,
        )
        self.collateral[contract.contract_id] = CollateralPosition(
            contract_id=contract.contract_id,
            risk_taker_id=risk_taker_id,
            amount=contract.max_payout,
            locked_tick=tick,
        )
        return MatchResult(
            contract_id=contract.contract_id,
            hedger_id=contract.hedger_id,
            risk_taker_id=risk_taker_id,
            fair_probability=quote.probability,
            premium=quote.fair_premium,
            venue_fee=venue_fee,
            collateral_locked=contract.max_payout,
            tick=tick,
        )
