"""
app.py — Home page del Portfolio Tracker.

In una multi-page Streamlit (cartella `pages/`), `app.py` è la "entry
point": viene visualizzata di default quando l'utente apre l'app.
Le altre pagine sono caricate al click sulla sidebar di navigazione.

Compito di questo file:
- Configurare la pagina (titolo, layout)
- Caricare i dati base (delegato a ensure_data_loaded)
- Mostrare una sintesi minimale del portafoglio
- Linkare alle pagine di dettaglio

La logica di calcolo NON vive qui. Sta nei moduli portfolio.py, costs.py
ecc., importati dalle singole pagine.

Per lanciare l'app, dalla root del progetto:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

import portfolio as pf
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# PAGE CONFIG
# --------------------------------------------------------------------------- #
# `set_page_config` deve essere la prima chiamata Streamlit di QUESTO script.
# In una multi-page app ogni pagina può avere la sua config.
st.set_page_config(
    page_title="Portfolio Tracker",
    page_icon="📊",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# DATA LOADING + SIDEBAR
# --------------------------------------------------------------------------- #
inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="home")

# --------------------------------------------------------------------------- #
# CONTENUTO HOME
# --------------------------------------------------------------------------- #
st.title("Portfolio Tracker")
st.caption("Dashboard di monitoraggio del portafoglio ETF")

callout(
    "Usa la <strong>navigazione a sinistra</strong> per esplorare le sezioni "
    "di dettaglio: Holdings, Performance, Allocazione, Andamento, "
    "Vs Benchmark, Costi e fiscalità, Ribilanciamento, Rischio e Monte Carlo. "
    "I dati vengono caricati al primo accesso e tenuti in memoria fino al "
    "click su <strong>🔄 Ricarica dati</strong> nella sidebar.",
    kind="info",
)

st.divider()

st.divider()

# --------------------------------------------------------------------------- #
# SINTESI
# --------------------------------------------------------------------------- #
# Mini-anteprima delle 4 metriche principali, così la home non è "vuota".
# Il dettaglio sta nella pagina Holdings.
st.subheader("Sintesi")

holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)

invested = float(holdings_valued["invested"].sum())
market_value = float(holdings_valued["market_value"].sum())
pnl_eur = market_value - invested
pnl_pct = pnl_eur / invested if invested else 0.0

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Capitale investito", f"{invested:,.2f} €")
with col2:
    kpi_card("Valore di mercato", f"{market_value:,.2f} €")
with col3:
    kpi_card(
        "P&L",
        f"{pnl_eur:+,.2f} €",
        delta=f"{pnl_pct:+.2%}",
        delta_kind="positive" if pnl_eur >= 0 else "negative",
    )
with col4:
    kpi_card("N° posizioni", f"{len(holdings_valued)}")

st.caption(
    f"📅 Dati al {prices.index[-1]:%d/%m/%Y}  ·  "
    f"📈 {len(tx)} operazioni dal {tx['date'].min():%d/%m/%Y}"
)
