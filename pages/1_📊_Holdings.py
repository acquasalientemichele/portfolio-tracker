"""
1_📊_Holdings.py — Posizioni correnti del portafoglio.

In Streamlit multi-page (cartella `pages/`), il prefisso numerico definisce
l'ordine in sidebar e viene rimosso dal display. Le emoji nel nome file
appaiono nella navigazione.

Questa pagina mostra:
- 4 metriche di sintesi (investito, valore, P&L, n° posizioni)
- Tabella dettagliata per ticker con formattazione per colonna
"""
from __future__ import annotations

import streamlit as st

import portfolio as pf
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Holdings", page_icon="📊", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar()

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
# Sono operazioni pandas pure, < 100ms. Le ricalcoliamo ad ogni rerun
# invece di cacheare: meno complessità, zero rischio staleness.
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("📊 Holdings")
st.caption("Posizioni correnti, P&L per ticker e pesi nel portafoglio")

# --------------------------------------------------------------------------- #
# METRICHE DI SINTESI
# --------------------------------------------------------------------------- #
invested = float(holdings_valued["invested"].sum())
market_value = float(holdings_valued["market_value"].sum())
pnl_eur = market_value - invested
pnl_pct = pnl_eur / invested if invested else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Capitale investito", f"{invested:,.2f} €")
col2.metric("Valore di mercato", f"{market_value:,.2f} €")
col3.metric("P&L", f"{pnl_eur:+,.2f} €", delta=f"{pnl_pct:+.2%}")
col4.metric("N° posizioni", f"{len(holdings_valued)}")

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA DETTAGLIATA
# --------------------------------------------------------------------------- #
st.subheader("Dettaglio per ticker")

# Trasformo le percentuali da frazione (0.087) a numero (8.7) perché
# st.column_config.NumberColumn non ha un format "percent" automatico.
view = holdings_valued[[
    "name", "quantity", "avg_cost", "last_price",
    "invested", "market_value", "pnl_eur", "pnl_pct", "weight"
]].copy()
view["pnl_pct"] = view["pnl_pct"] * 100
view["weight"] = view["weight"] * 100
view = view.rename(columns={
    "name": "Nome",
    "quantity": "Quantità",
    "avg_cost": "Costo medio",
    "last_price": "Ultimo prezzo",
    "invested": "Investito",
    "market_value": "Valore",
    "pnl_eur": "P&L €",
    "pnl_pct": "P&L %",
    "weight": "Peso",
})

st.dataframe(
    view,
    use_container_width=True,
    column_config={
        "Quantità":      st.column_config.NumberColumn(format="%.4f"),
        "Costo medio":   st.column_config.NumberColumn(format="%.2f €"),
        "Ultimo prezzo": st.column_config.NumberColumn(format="%.2f €"),
        "Investito":     st.column_config.NumberColumn(format="%.2f €"),
        "Valore":        st.column_config.NumberColumn(format="%.2f €"),
        "P&L €":         st.column_config.NumberColumn(format="%+.2f €"),
        "P&L %":         st.column_config.NumberColumn(format="%+.2f%%"),
        "Peso":          st.column_config.ProgressColumn(
                            format="%.1f%%", min_value=0, max_value=100),
    },
)

st.caption(
    f"📅 Ultimo prezzo disponibile: {prices.index[-1]:%d/%m/%Y}  ·  "
    f"il P&L è al lordo di bollo e imposta sulle plusvalenze "
    f"(vedi pagina **Costi e fiscalità**, in arrivo)"
)
