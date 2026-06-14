# RiskMesh two-minute demo script

## Before going on stage

```bash
uv sync --frozen
uv run python scripts/check_gemini.py
uv run streamlit run app.py
```

Open `http://localhost:8501`, keep **Gemini belief launch** enabled, leave
**Gemini every tick** disabled, and click **Reset venue**.

## 0:00-0:15 - Set the gap

> Agents can already communicate and pay for services. What they cannot do is
> transfer risk. RiskMesh is the exchange above the emerging agent payment rails.

Point to the empty venue and the five forecaster slots.

## 0:15-0:40 - Launch belief streams

Click **1. Launch micro-contract**.

> This is a bespoke BTC micro-contract: tiny notional, six replay ticks to
> expiry. Five Gemini personas see different market context and publish competing
> probabilities. RiskMesh weights each forecast by that agent's past calibration
> and turns the blended belief into one live fair premium.

Point to the five colored beliefs, the mint RiskMesh fair price, and the contract
strike.

## 0:40-1:05 - Match and collateralize

Click **2. Match + lock collateral**.

> A hedging agent pays the fair premium to offload the risk. A capital agent takes
> the other side. Before the premium moves, the taker locks the full twenty-five
> dollar maximum payout. The contract is now fully collateralized, so settlement
> has zero counterparty default risk.

Point to **Fair premium**, **Collateral locked**, and **Venue fees**.

## 1:05-1:30 - Expire and settle

Click **Run to settlement**.

> The venue advances through a bundled historical BTC replay, reads the reference
> price at expiry, resolves the binary outcome, and automatically moves the locked
> funds to the winner.

Point to the settlement event and changed agent balances.

## 1:30-1:48 - Show the moat

> Settlement also scores every forecast with a Brier calibration score and
> updates agent PnL. Better-calibrated agents receive more weight in the next
> belief stream. Every trade earns a fee; every resolved outcome improves the
> pricing data moat.

Point to the leaderboard sorting and the venue fee total.

## 1:48-2:00 - Close

> You just watched the first market where every participant is an AI - trading a
> brand-new asset class, machine-native micro-risk, priced by AI belief streams
> and cleared agent-to-agent. The payment rails for agents are being built by
> Google and Coinbase. We're the exchange on top.

## Recovery path

If Gemini is slow, disable **Gemini belief launch**, click **Reset venue**, and
repeat. The deterministic persona fallback exercises the identical clearing,
collateral, oracle, settlement, reputation, and fee lifecycle.
