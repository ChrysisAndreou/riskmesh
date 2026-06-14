"""Deterministic historical market-data replay."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

DEFAULT_FEED_PATH = Path(__file__).parent / "data" / "btcusdt_1m.csv"


@dataclass(frozen=True, slots=True)
class PricePoint:
    tick: int
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class ReplayPriceFeed:
    """Replays bundled Binance BTCUSDT minute bars one deterministic tick at a time."""

    def __init__(self, points: list[PricePoint]) -> None:
        if not points:
            raise ValueError("Price feed requires at least one point")
        self.points = points
        self.cursor = 0

    @classmethod
    def from_csv(cls, path: Path = DEFAULT_FEED_PATH) -> ReplayPriceFeed:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            points = [
                PricePoint(
                    tick=int(row["tick"]),
                    timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=Decimal(row["volume"]),
                )
                for row in reader
            ]
        return cls(points)

    @property
    def current(self) -> PricePoint:
        return self.points[self.cursor]

    @property
    def exhausted(self) -> bool:
        return self.cursor >= len(self.points) - 1

    def advance(self, steps: int = 1) -> PricePoint:
        if steps < 1:
            raise ValueError("steps must be positive")
        self.cursor = min(self.cursor + steps, len(self.points) - 1)
        return self.current

    def point_at(self, tick: int) -> PricePoint:
        if tick < 0 or tick >= len(self.points):
            raise IndexError(f"Tick {tick} is outside the replay feed")
        return self.points[tick]

    def reset(self, tick: int = 0) -> PricePoint:
        self.cursor = self.point_at(tick).tick
        return self.current

    def history(self, length: int = 8) -> list[PricePoint]:
        start = max(0, self.cursor - length + 1)
        return self.points[start : self.cursor + 1]
