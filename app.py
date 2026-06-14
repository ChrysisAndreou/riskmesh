"""RiskMesh Streamlit dashboard."""

from __future__ import annotations

import os
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from riskmesh.contracts import ContractStatus
from riskmesh.forecasters import FORECASTER_PROFILES
from riskmesh.venue import VENUE_ID, RiskMeshVenue

load_dotenv()

st.set_page_config(
    page_title="RiskMesh | Agent Risk Exchange",
    page_icon="RM",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .stApp {
        background:
            radial-gradient(circle at 85% 5%, rgba(77,240,192,.09), transparent 28rem),
            linear-gradient(180deg, #07111f 0%, #08131f 100%);
    }
    [data-testid="stSidebar"] {
        background: #081520;
        border-right: 1px solid rgba(99, 124, 157, .2);
    }
    .block-container { padding-top: 1.6rem; max-width: 1500px; }
    .eyebrow {
        color: #4df0c0; font-size: .72rem; font-weight: 750; letter-spacing: .16em;
        text-transform: uppercase; margin-bottom: .25rem;
    }
    .hero-title {
        font-size: 2.65rem; line-height: 1; font-weight: 820; letter-spacing: -.04em;
        margin: 0; color: #f5f8ff;
    }
    .hero-copy { color: #90a2ba; margin-top: .65rem; font-size: 1rem; }
    .contract-card {
        border: 1px solid rgba(77,240,192,.28); border-radius: 14px;
        padding: 1rem 1.2rem; background: rgba(10, 27, 41, .82); margin: .8rem 0 1rem;
        box-shadow: inset 3px 0 0 #4df0c0;
    }
    .contract-card strong { color: #f4f8ff; }
    .contract-meta { color: #8da0b7; font-size: .85rem; margin-top: .35rem; }
    [data-testid="stMetric"] {
        background: rgba(13, 28, 43, .82); border: 1px solid rgba(118, 143, 174, .16);
        padding: .8rem 1rem; border-radius: 12px;
    }
    [data-testid="stMetricValue"] {
        color: #f4f8ff; font-weight: 720; font-size: 1.72rem; white-space: nowrap;
    }
    [data-testid="stMetricLabel"] { color: #8fa2ba; }
    .status-pill {
        display: inline-block; padding: .18rem .55rem; border-radius: 999px;
        font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
        background: rgba(77,240,192,.12); color: #4df0c0; border: 1px solid rgba(77,240,192,.3);
    }
    .agent-card {
        border: 1px solid rgba(118, 143, 174, .16); border-radius: 11px;
        padding: .72rem .8rem; background: rgba(12, 27, 42, .72); min-height: 112px;
    }
    .agent-name { font-size: .82rem; color: #9cafc6; }
    .agent-prob { font-size: 1.45rem; font-weight: 760; color: #f4f8ff; }
    .agent-source { color: #607792; font-size: .68rem; margin-top: .3rem; }
    .small-note { color: #6f839c; font-size: .76rem; }
    hr { border-color: rgba(118, 143, 174, .14) !important; }
    .stButton > button {
        border-radius: 9px; border: 1px solid rgba(77,240,192,.35);
        font-weight: 720;
    }
</style>
""",
    unsafe_allow_html=True,
)


def venue() -> RiskMeshVenue:
    if "venue" not in st.session_state:
        st.session_state.venue = RiskMeshVenue()
    return st.session_state.venue


def money(value: Decimal | float | None) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.2f}"


def price_figure(market: RiskMeshVenue) -> go.Figure:
    points = market.feed.points[: market.feed.current.tick + 1]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[point.timestamp for point in points],
            y=[float(point.close) for point in points],
            mode="lines",
            line={"color": "#4DF0C0", "width": 2.4},
            name="BTCUSDT",
        )
    )
    contract = market.active_contract
    if contract is not None:
        figure.add_hline(
            y=float(contract.strike),
            line_dash="dot",
            line_color="#FFB86B",
            annotation_text=f"Strike ${contract.strike:,.0f}",
            annotation_font_color="#FFB86B",
        )
    figure.update_layout(
        height=330,
        margin={"l": 10, "r": 10, "t": 25, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"gridcolor": "rgba(110,135,165,.10)", "title": None},
        yaxis={
            "gridcolor": "rgba(110,135,165,.10)",
            "title": None,
            "tickprefix": "$",
        },
        legend={"orientation": "h", "y": 1.08},
        hovermode="x unified",
    )
    return figure


def belief_figure(market: RiskMeshVenue) -> go.Figure:
    figure = go.Figure()
    if market.active_contract is not None:
        contract_quotes = [
            quote
            for quote in market.belief_history
            if quote.contract_id == market.active_contract.contract_id
        ]
        colors = ["#5EA7FF", "#FFB86B", "#D787FF", "#FF6B9A", "#A3E635"]
        for profile, color in zip(FORECASTER_PROFILES, colors, strict=True):
            figure.add_trace(
                go.Scatter(
                    x=[quote.tick for quote in contract_quotes],
                    y=[
                        float(
                            next(
                                forecast.probability
                                for forecast in quote.forecasts
                                if forecast.agent_id == profile.agent_id
                            )
                        )
                        for quote in contract_quotes
                    ],
                    mode="lines+markers",
                    name=profile.display_name,
                    line={"color": color, "width": 1.3},
                    marker={"size": 5},
                    opacity=0.72,
                )
            )
        figure.add_trace(
            go.Scatter(
                x=[quote.tick for quote in contract_quotes],
                y=[float(quote.probability) for quote in contract_quotes],
                mode="lines+markers",
                name="RiskMesh fair",
                line={"color": "#4DF0C0", "width": 3.5},
                marker={"size": 8, "symbol": "diamond"},
            )
        )
    figure.update_layout(
        height=330,
        margin={"l": 10, "r": 10, "t": 25, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"title": "Replay tick", "gridcolor": "rgba(110,135,165,.10)"},
        yaxis={
            "title": "Trigger probability",
            "tickformat": ".0%",
            "range": [0, 1],
            "gridcolor": "rgba(110,135,165,.10)",
        },
        legend={"orientation": "h", "y": 1.18, "font": {"size": 10}},
        hovermode="x unified",
    )
    return figure


market = venue()
active = market.active_contract
quote = market.latest_quote

with st.sidebar:
    st.markdown('<div class="eyebrow">Venue controls</div>', unsafe_allow_html=True)
    st.markdown("### Run the market")
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    use_gemini = st.toggle(
        "Gemini belief launch",
        value=has_key,
        help="Calls five Gemini 3.5 Flash personas in parallel for the opening quote.",
    )
    gemini_each_tick = st.toggle(
        "Gemini every tick",
        value=False,
        help="Higher latency. Off uses deterministic persona updates after the Gemini launch.",
    )

    if st.button("1. Launch micro-contract", width="stretch", type="primary"):
        try:
            if (
                market.active_contract is None
                or market.active_contract.status is ContractStatus.SETTLED
            ):
                market.open_contract()
            market.refresh_beliefs(use_gemini=use_gemini)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    active = market.active_contract
    quote = market.latest_quote
    if st.button(
        "2. Match + lock collateral",
        width="stretch",
        disabled=active is None or active.status is not ContractStatus.OPEN or quote is None,
    ):
        try:
            market.match_active()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    active = market.active_contract
    if st.button(
        "3. Advance one tick",
        width="stretch",
        disabled=active is None or active.status is ContractStatus.SETTLED,
    ):
        try:
            market.advance(use_gemini=gemini_each_tick)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    active = market.active_contract
    if st.button(
        "Run to settlement",
        width="stretch",
        disabled=active is None or active.status is not ContractStatus.MATCHED,
    ):
        try:
            while (
                market.active_contract
                and market.active_contract.status is not ContractStatus.SETTLED
            ):
                market.advance(use_gemini=False)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if st.button("Reset venue", width="stretch"):
        st.session_state.venue = RiskMeshVenue()
        st.rerun()

    st.divider()
    st.markdown("**Mechanism guarantee**")
    st.markdown(
        '<div class="small-note">Maximum payout is locked before the premium moves. '
        "Every contract is fully collateralized, so settlement has zero counterparty "
        "default risk.</div>",
        unsafe_allow_html=True,
    )
    st.caption("Replay: bundled Binance BTCUSDT 1m bars, compressed for the demo.")

active = market.active_contract
quote = market.latest_quote
st.markdown('<div class="eyebrow">AI & Intelligent Trading</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">RiskMesh</h1>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-copy">The agent-to-agent exchange for machine-native micro-risk, '
    "priced by track-record-weighted AI belief streams.</div>",
    unsafe_allow_html=True,
)

if active is None:
    st.markdown(
        '<div class="contract-card"><span class="status-pill">Ready</span> '
        "<strong>Launch the first machine-native risk contract.</strong>"
        '<div class="contract-meta">Five AI forecasters will price it; one capital agent '
        "will fully collateralize it.</div></div>",
        unsafe_allow_html=True,
    )
else:
    ticks_left = max(active.expiry_tick - market.feed.current.tick, 0)
    st.markdown(
        f'<div class="contract-card"><span class="status-pill">{active.status.value}</span>'
        f"&nbsp;<strong>{active.contract_id}</strong>&nbsp;pays "
        f"<strong>{money(active.notional)}</strong>&nbsp;"
        f"if BTCUSDT closes {active.direction.value} "
        f"<strong>${active.strike:,.2f}</strong>&nbsp;at tick {active.expiry_tick}."
        f'<div class="contract-meta">{ticks_left} ticks to expiry | '
        f"Hedger: {active.hedger_id} | Taker: {active.risk_taker_id or 'awaiting match'}"
        "</div></div>",
        unsafe_allow_html=True,
    )

metric_cols = st.columns(5)
metric_cols[0].metric(
    "Replay BTCUSDT", f"${float(market.feed.current.close) / 1000:.2f}k"
)
metric_cols[1].metric(
    "Blended belief", f"{quote.probability:.1%}" if quote else "-"
)
metric_cols[2].metric("Fair premium", money(quote.fair_premium if quote else None))
metric_cols[3].metric(
    "Collateral locked",
    money(
        market.ledger.account(active.risk_taker_id).locked
        if active and active.risk_taker_id
        else Decimal("0")
    ),
)
metric_cols[4].metric(
    "Venue fees", money(market.ledger.account(VENUE_ID).available)
)

chart_left, chart_right = st.columns([1.05, 1])
with chart_left:
    st.markdown("#### Deterministic oracle replay")
    st.plotly_chart(
        price_figure(market),
        width="stretch",
        config={"displayModeBar": False},
    )
with chart_right:
    st.markdown("#### Live belief streams")
    st.plotly_chart(
        belief_figure(market), width="stretch", config={"displayModeBar": False}
    )

if quote:
    st.markdown("#### Competing AI forecasters")
    agent_columns = st.columns(len(quote.forecasts))
    for column, forecast in zip(agent_columns, quote.forecasts, strict=True):
        weight = quote.weights[forecast.agent_id]
        with column:
            st.markdown(
                f'<div class="agent-card"><div class="agent-name">{forecast.agent_name}</div>'
                f'<div class="agent-prob">{forecast.probability:.1%}</div>'
                f'<div class="small-note">reputation weight {weight:.2f}x</div>'
                f'<div class="agent-source">{forecast.source}</div></div>',
                unsafe_allow_html=True,
            )

leaderboard_col, tape_col = st.columns([1.1, 1])
with leaderboard_col:
    st.markdown("#### Agent reputation + PnL")
    leaderboard = pd.DataFrame(market.leaderboard_rows())
    if not leaderboard.empty:
        leaderboard["calibration"] = leaderboard["calibration"].map(
            lambda value: f"{value:.1%}"
        )
        leaderboard["mean_brier"] = leaderboard["mean_brier"].map(
            lambda value: f"{value:.3f}" if value is not None else "-"
        )
        leaderboard["weight"] = leaderboard["weight"].map(lambda value: f"{value:.2f}x")
        leaderboard["pnl"] = leaderboard["pnl"].map(lambda value: f"${value:,.2f}")
        leaderboard["available"] = leaderboard["available"].map(
            lambda value: f"${value:,.2f}"
        )
        leaderboard["locked"] = leaderboard["locked"].map(
            lambda value: f"${value:,.2f}"
        )
        st.dataframe(
            leaderboard,
            hide_index=True,
            width="stretch",
            column_order=[
                "agent",
                "calibration",
                "mean_brier",
                "weight",
                "forecasts",
                "pnl",
                "available",
                "locked",
            ],
        )

with tape_col:
    st.markdown("#### Match + settlement tape")
    events = pd.DataFrame(
        [
            {"tick": event.tick, "type": event.kind.upper(), "event": event.message}
            for event in reversed(market.events[-14:])
        ]
    )
    st.dataframe(
        events,
        hide_index=True,
        width="stretch",
        column_order=["tick", "type", "event"],
    )

st.caption(
    "Simulation only. Production path: AWS deployment, live reference feeds, "
    "regulated onboarding, and x402/AP2-compatible settlement rails."
)
