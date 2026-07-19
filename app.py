"""
app.py — Home / onboarding del Portfolio Tracker.

Entry point della multi-page app (servita su "/"). Ha due stati:

1) Nessun dato in sessione → schermata di onboarding: presentazione,
   istruzioni in 3 passi, download del template Excel, uploader e modalità
   demo. È qui che si popola st.session_state["workbook_bytes"].

2) Dati caricati → benvenuto + sintesi del portafoglio, con la navigazione
   a sinistra verso le pagine di dettaglio.

La logica di calcolo NON vive qui: sta nei moduli core (portfolio.py,
costs.py, ...), usati dalle singole pagine.

Per lanciare, dalla root del progetto:
    streamlit run app.py
"""
from __future__ import annotations

from html import escape

import streamlit as st

import portfolio as pf
import template as tpl
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css, load_bundle
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# PAGE CONFIG + CHROME
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Portfolio Tracker", page_icon="📊", layout="wide")
inject_css()
render_sidebar(current_page="home")


# --------------------------------------------------------------------------- #
# HELPER: VALIDAZIONE E CARICAMENTO
# --------------------------------------------------------------------------- #
def _try_load(raw: bytes, source_name: str) -> None:
    """Valida i bytes del workbook e, se ok, li salva in sessione e ricarica.

    Sfrutta i validatori reali: load_bundle → pf.load_transactions solleva
    ValueError con messaggi in italiano (colonne mancanti, operazioni non
    valide). Blocca anche i file senza operazioni, che manderebbero in errore
    le pagine a valle.
    """
    try:
        bundle = load_bundle(raw)
    except ValueError as e:
        callout(f"Il file non è valido: {escape(str(e))}", kind="danger")
        return
    except Exception:
        callout(
            "Non riesco a leggere il file. Assicurati che sia un <strong>.xlsx</strong> "
            "con i fogli del template (almeno <strong>transactions</strong> e "
            "<strong>settings</strong>).",
            kind="danger",
        )
        return

    if bundle["tx"].empty:
        callout(
            "Il file non contiene operazioni. Compila il foglio "
            "<strong>transactions</strong> prima di caricarlo.",
            kind="warning",
        )
        return

    st.session_state["workbook_bytes"] = raw
    st.session_state["source_name"] = source_name
    st.rerun()


# --------------------------------------------------------------------------- #
# STATO 1: ONBOARDING (nessun dato caricato)
# --------------------------------------------------------------------------- #
def render_onboarding() -> None:
    """Landing pre-caricamento: presentazione + 3 passi + download + upload + demo."""
    st.title("Portfolio Tracker")
    st.caption(
        "Monitora il tuo portafoglio ETF — performance, allocazione, costi, "
        "rischio e proiezioni — partendo da un semplice file Excel."
    )

    callout(
        "<strong>Come funziona.</strong> Tre passi: scarichi il template, ci "
        "inserisci le tue operazioni, lo ricarichi qui. I dati restano nella "
        "sessione del tuo browser e non vengono salvati sul server.",
        kind="info",
    )

    st.subheader("1 · Scarica il template")
    st.write(
        "Un file Excel con i fogli già pronti (operazioni, impostazioni, TER, "
        "bollo). Le prime due righe del foglio operazioni sono esempi da sostituire."
    )
    st.download_button(
        "⬇️  Scarica transactions_template.xlsx",
        data=tpl.build_template_workbook(),
        file_name="transactions_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("2 · Inserisci le tue operazioni")
    st.write(
        "Nel foglio **transactions** aggiungi ogni acquisto/vendita (data, "
        "ticker, ISIN, quantità, prezzo, commissioni). Nel foglio **settings** "
        "imposti valuta base, benchmark e allocazione target."
    )

    st.subheader("3 · Carica il file")
    uploaded = st.file_uploader(
        "Carica il tuo file .xlsx", type=["xlsx"], label_visibility="collapsed"
    )
    if uploaded is not None:
        _try_load(uploaded.getvalue(), source_name=uploaded.name)

    st.divider()
    st.caption("Vuoi solo dare un'occhiata senza compilare nulla?")
    if st.button("▶️  Prova con dati demo"):
        _try_load(tpl.build_demo_workbook(), source_name="Dati demo")


# --------------------------------------------------------------------------- #
# ROUTING: onboarding vs dashboard
# --------------------------------------------------------------------------- #
if "workbook_bytes" not in st.session_state:
    render_onboarding()
    st.stop()

# --------------------------------------------------------------------------- #
# STATO 2: DASHBOARD (dati presenti)
# --------------------------------------------------------------------------- #
tx, prices, settings = ensure_data_loaded()

st.title("Portfolio Tracker")
st.caption(
    f"Sorgente: {st.session_state.get('source_name', '—')}  ·  "
    f"dati al {prices.index[-1]:%d/%m/%Y}"
)

callout(
    "Usa la <strong>navigazione a sinistra</strong> per esplorare Holdings, "
    "Performance, Allocazione, Andamento, Vs Benchmark, Costi, Ribilanciamento, "
    "Rischio e Monte Carlo. Con <strong>📁 Cambia file</strong> nella sidebar "
    "carichi un altro portafoglio.",
    kind="info",
)

st.divider()

# --------------------------------------------------------------------------- #
# SINTESI (mini-anteprima; il dettaglio è in Holdings)
# --------------------------------------------------------------------------- #
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
