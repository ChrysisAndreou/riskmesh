"""Binary micro-risk contract specification and lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4


class ContractError(ValueError):
    """Raised when a contract lifecycle transition is invalid."""


class TriggerDirection(StrEnum):
    ABOVE = "above"
    BELOW = "below"


class ContractStatus(StrEnum):
    OPEN = "open"
    MATCHED = "matched"
    SETTLED = "settled"


@dataclass(slots=True)
class BinaryContract:
    underlying: str
    strike: Decimal
    created_tick: int
    expiry_tick: int
    notional: Decimal
    hedger_id: str
    direction: TriggerDirection = TriggerDirection.ABOVE
    contract_id: str = ""
    status: ContractStatus = ContractStatus.OPEN
    risk_taker_id: str | None = None
    fair_probability: Decimal | None = None
    premium: Decimal | None = None
    venue_fee: Decimal | None = None
    settlement_price: Decimal | None = None
    outcome: bool | None = None
    payout: Decimal | None = None

    def __post_init__(self) -> None:
        self.strike = Decimal(str(self.strike))
        self.notional = Decimal(str(self.notional))
        if not self.contract_id:
            self.contract_id = f"RM-{uuid4().hex[:8].upper()}"
        if self.expiry_tick <= self.created_tick:
            raise ContractError("Expiry must be after contract creation")
        if self.notional <= 0:
            raise ContractError("Notional must be positive")

    @property
    def max_payout(self) -> Decimal:
        return self.notional

    def is_triggered(self, settlement_price: Decimal) -> bool:
        if self.direction is TriggerDirection.ABOVE:
            return settlement_price >= self.strike
        return settlement_price <= self.strike

    def mark_matched(
        self,
        *,
        risk_taker_id: str,
        fair_probability: Decimal,
        premium: Decimal,
        venue_fee: Decimal,
    ) -> None:
        if self.status is not ContractStatus.OPEN:
            raise ContractError(f"Cannot match contract in {self.status} state")
        probability = Decimal(str(fair_probability))
        premium_value = Decimal(str(premium))
        fee_value = Decimal(str(venue_fee))
        if probability < 0 or probability > 1:
            raise ContractError("Fair probability must be between zero and one")
        if premium_value < 0 or fee_value < 0:
            raise ContractError("Premium and fee cannot be negative")
        self.risk_taker_id = risk_taker_id
        self.fair_probability = probability
        self.premium = premium_value
        self.venue_fee = fee_value
        self.status = ContractStatus.MATCHED
