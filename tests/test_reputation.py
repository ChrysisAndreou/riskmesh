from decimal import Decimal

from riskmesh.forecasters import Forecast
from riskmesh.reputation import ReputationBook


def test_brier_calibration_reweights_future_beliefs() -> None:
    forecasts = [
        Forecast("skilled", "Skilled", "RM-1", 1, Decimal("0.80"), "good", "test"),
        Forecast("noisy", "Noisy", "RM-1", 1, Decimal("0.20"), "bad", "test"),
    ]
    book = ReputationBook()

    scores = book.score_forecasts(forecasts, outcome=True, tick=2)
    weights = book.weights(("skilled", "noisy"))

    assert scores[0].brier_score == Decimal("0.0400")
    assert scores[1].brier_score == Decimal("0.6400")
    assert weights["skilled"] > weights["noisy"]
    assert book.leaderboard()[0].agent_id == "skilled"
