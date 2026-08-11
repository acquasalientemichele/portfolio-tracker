"""Holdings — current positions, per-ticker P&L and portfolio weights."""

from __future__ import annotations

import streamlit as st

import portfolio as pf
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Holdings", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="holdings")

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Holdings")
st.caption("Current positions, P&L by ticker and portfolio weights")

# --------------------------------------------------------------------------- #
# METRICHE DI SINTESI
# --------------------------------------------------------------------------- #
invested = float(holdings_valued["invested"].sum())
market_value = float(holdings_valued["market_value"].sum())
pnl_eur = market_value - invested
pnl_pct = pnl_eur / invested if invested else 0.0

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Invested capital", f"{invested:,.2f} €")
with col2:
    kpi_card("Market value", f"{market_value:,.2f} €")
with col3:
    kpi_card(
        "P&L",
        f"{pnl_eur:+,.2f} €",
        delta=f"{pnl_pct:+.2%}",
        delta_kind="positive" if pnl_eur >= 0 else "negative",
    )
with col4:
    kpi_card("Positions", f"{len(holdings_valued)}")

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA DETTAGLIATA
# --------------------------------------------------------------------------- #
st.subheader("Breakdown by ticker")

# Trasformo le percentuali da frazione (0.087) a numero (8.7) perché
# st.column_config.NumberColumn non ha un format "percent" automatico.
view = holdings_valued[[
    "name", "quantity", "avg_cost", "last_price",
    "invested", "market_value", "pnl_eur", "pnl_pct", "weight"
]].copy()
view["pnl_pct"] = view["pnl_pct"] * 100
view["weight"] = view["weight"] * 100
view = view.rename(columns={
    "name": "Name",
    "quantity": "Quantity",
    "avg_cost": "Avg cost",
    "last_price": "Last price",
    "invested": "Invested",
    "market_value": "Value",
    "pnl_eur": "P&L €",
    "pnl_pct": "P&L %",
    "weight": "Weight",
})

st.dataframe(
    view,
    use_container_width=True,
    column_config={
        "Quantity":   st.column_config.NumberColumn(format="%.4f"),
        "Avg cost":   st.column_config.NumberColumn(format="%.2f €"),
        "Last price": st.column_config.NumberColumn(format="%.2f €"),
        "Invested":   st.column_config.NumberColumn(format="%.2f €"),
        "Value":      st.column_config.NumberColumn(format="%.2f €"),
        "P&L €":      st.column_config.NumberColumn(format="%+.2f €"),
        "P&L %":      st.column_config.NumberColumn(format="%+.2f%%"),
        "Weight":     st.column_config.ProgressColumn(
                        format="%.1f%%", min_value=0, max_value=100),
    },
)

st.caption(
    f"Latest available price: {prices.index[-1]:%d/%m/%Y}  ·  "
    f"P&L is gross of stamp duty and capital-gains tax"
)
