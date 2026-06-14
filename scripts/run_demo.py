"""Run the complete RiskMesh lifecycle in the terminal."""

from __future__ import annotations

import argparse

from riskmesh.venue import VENUE_ID, RiskMeshVenue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gemini",
        action="store_true",
        help="Use Gemini for the initial five-agent belief stream.",
    )
    args = parser.parse_args()

    venue = RiskMeshVenue()
    result = venue.run_demo(use_gemini=args.gemini)

    for event in venue.events:
        print(f"[tick {event.tick:02d}] {event.kind.upper():10} {event.message}")
    print()
    print(
        f"Settlement: outcome={result.outcome} payout=${result.payout} "
        f"venue_fees=${venue.ledger.account(VENUE_ID).available}"
    )
    for row in venue.leaderboard_rows():
        print(
            f"{row['agent']:<12} calibration={row['calibration']:.1%} "
            f"weight={row['weight']:.2f} pnl=${row['pnl']:.2f}"
        )


if __name__ == "__main__":
    main()
