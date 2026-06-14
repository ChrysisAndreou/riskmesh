from decimal import Decimal

from riskmesh.contracts import BinaryContract, TriggerDirection
from riskmesh.forecasters import (
    FORECASTER_PROFILES,
    BeliefAggregator,
    Forecast,
    HeuristicForecaster,
)
from riskmesh.market import ReplayPriceFeed


def contract_for(feed: ReplayPriceFeed) -> BinaryContract:
    return BinaryContract(
        underlying="BTCUSDT",
        strike=feed.current.close + Decimal("20"),
        created_tick=0,
        expiry_tick=5,
        notional=Decimal("20"),
        hedger_id="hedger",
        direction=TriggerDirection.ABOVE,
        contract_id="RM-TEST",
    )


def test_fallback_forecasters_produce_bounded_distinct_beliefs() -> None:
    feed = ReplayPriceFeed.from_csv()
    feed.advance(4)
    contract = contract_for(feed)

    forecasts = [
        HeuristicForecaster(profile).forecast(contract, feed.history(10), tick=4)
        for profile in FORECASTER_PROFILES
    ]

    assert all(Decimal("0.02") <= item.probability <= Decimal("0.98") for item in forecasts)
    assert len({item.probability for item in forecasts}) >= 3


def test_aggregation_rewards_higher_track_record_weight() -> None:
    feed = ReplayPriceFeed.from_csv()
    contract = contract_for(feed)
    forecasts = [
        Forecast("skilled", "Skilled", contract.contract_id, 0, Decimal("0.80"), "a", "test"),
        Forecast("noisy", "Noisy", contract.contract_id, 0, Decimal("0.20"), "b", "test"),
    ]

    quote = BeliefAggregator().aggregate(
        contract,
        forecasts,
        weights={"skilled": Decimal("3"), "noisy": Decimal("1")},
    )

    assert quote.probability == Decimal("0.6500")
    assert quote.fair_premium == Decimal("13.00")
