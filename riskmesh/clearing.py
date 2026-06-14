"""Agent-to-agent matching and fully collateralized clearing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
    collateral_locked: Decimal
    tick: int


class ClearingEngine:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
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

        self.ledger.lock(
            risk_taker_id,
            contract.max_payout,
            note=f"{contract.contract_id} maximum payout collateral",
            tick=tick,
        )
        self.ledger.transfer(
            contract.hedger_id,
            risk_taker_id,
            quote.fair_premium,
            note=f"{contract.contract_id} fair premium",
            tick=tick,
        )
        contract.mark_matched(
            risk_taker_id=risk_taker_id,
            fair_probability=quote.probability,
            premium=quote.fair_premium,
            venue_fee=Decimal("0"),
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
            collateral_locked=contract.max_payout,
            tick=tick,
        )
