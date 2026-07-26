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
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css, load_bundle, home_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# PAGE CONFIG + CHROME
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Portfolio Tracker", layout="wide")
inject_css()
render_sidebar(current_page="home")


# --------------------------------------------------------------------------- #
# HELPER: VALIDAZIONE E CARICAMENTO
# --------------------------------------------------------------------------- #
def _try_load(raw: bytes, source_name: str, demo: bool = False) -> None:
    """Valida i bytes del workbook e, se ok, li salva in sessione e ricarica.

    Sfrutta i validatori reali: load_bundle → pf.load_transactions solleva
    ValueError con messaggi in italiano (colonne mancanti, operazioni non
    valide). Blocca anche i file senza operazioni, che manderebbero in errore
    le pagine a valle.
    """
    try:
        bundle = load_bundle(raw)
    except ValueError as e:
        callout(f"The file is not valid: {escape(str(e))}", kind="danger")
        return
    except Exception:
        callout(
            "Couldn't read the file. Make sure it's an <strong>.xlsx</strong> "
            "with the template sheets (at least <strong>transactions</strong> and "
            "<strong>settings</strong>).",
            kind="danger",
        )
        return

    if bundle["tx"].empty:
        callout(
            "The file contains no transactions. Fill in the "
            "<strong>transactions</strong> sheet before uploading it.",
            kind="warning",
        )
        return

    st.session_state["workbook_bytes"] = raw
    st.session_state["source_name"] = source_name
    st.session_state["is_demo"] = demo
    st.rerun()


# --------------------------------------------------------------------------- #
# STATO 1: ONBOARDING (nessun dato caricato)
# --------------------------------------------------------------------------- #
def render_onboarding() -> None:
    """Landing pre-caricamento.

    Struttura: card "Usa i tuoi dati" (step numerati → download template →
    uploader) e, separata da un "oppure", la card della modalità demo.
    Il percorso principale è visivamente dominante; la demo resta un'uscita
    laterale per chi vuole solo dare un'occhiata.
    """
    st.markdown(home_css(), unsafe_allow_html=True)

    st.title("Portfolio Tracker")
    st.caption(
        "Track your ETF portfolio — performance, allocation, costs, risk and "
        "projections — starting from a simple Excel file."
    )
    st.write("")

    # ---------------------------- CARD: usa i tuoi dati ---------------------
    with st.container(key="pt_card_data"):
        st.markdown('<div class="pt-eyebrow">Use your own data</div>',
                    unsafe_allow_html=True)

        steps = [("1", "Download the template", True),
                 ("2", "Fill in your transactions", False),
                 ("3", "Upload the file", False)]
        st.markdown(
            '<div class="pt-steps">' + "".join(
                f'<div class="pt-step">'
                f'<span class="pt-step-n{" is-active" if act else ""}">{n}</span>'
                f'<span class="pt-step-l">{lab}</span></div>'
                for n, lab, act in steps
            ) + '</div>',
            unsafe_allow_html=True,
        )

        with st.container(key="btn_template"):
            st.download_button(
                "Download transactions_template.xlsx",
                data=tpl.build_template_workbook(),
                file_name="transactions_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        st.markdown(
            '<p class="pt-help">Sheets ready to go — transactions, settings, TER, '
            'stamp duty. The first two example rows should be replaced.</p>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="pt-hr"></div>', unsafe_allow_html=True)

        with st.container(key="pt_upload"):
            uploaded = st.file_uploader(
                "Upload your .xlsx file", type=["xlsx"],
                label_visibility="collapsed",
            )
        if uploaded is not None:
            _try_load(uploaded.getvalue(), source_name=uploaded.name)

    # ---------------------------- SEPARATORE --------------------------------
    st.markdown('<div class="pt-or"><span>or</span></div>',
                unsafe_allow_html=True)

    # ---------------------------- CARD: demo --------------------------------
    with st.container(key="pt_card_demo"):
        col_txt, col_btn = st.columns([3, 1.35], vertical_alignment="center")
        with col_txt:
            st.markdown(
                '<p class="pt-demo-t">Just want to take a look?</p>'
                '<p class="pt-demo-s">Explore the app with a pre-filled demo '
                'portfolio — no file required.</p>',
                unsafe_allow_html=True,
            )
        with col_btn:
            with st.container(key="btn_demo"):
                if st.button("Try with sample data"):
                    _try_load(tpl.build_demo_workbook(), source_name="Sample data", demo = True)

    st.markdown(
        '<p class="pt-note">Your data stays in the browser session '
        'and is never saved on the server.</p>',
        unsafe_allow_html=True,
    )


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
    f"Source: {st.session_state.get('source_name', '—')}  ·  "
    f"data as of {prices.index[-1]:%d/%m/%Y}"
)

if st.session_state.get("is_demo"):
    callout(
        "<strong>Sample portfolio.</strong> A simple recurring-investment plan "
        "(dollar-cost averaging): €500 invested monthly in a global all-world ETF "
        "(VWCE), plus two €1,500 yearly contributions — one in June into a US "
        "S&amp;P 500 ETF, one in December into a European ETF, echoing Italy's "
        "<em>quattordicesima</em> and <em>tredicesima</em> salary bonuses. "
        "Around €9,000 per year over roughly seven years. Use the "
        "<strong>left-hand navigation</strong> to explore, or <strong>Change file</strong> "
        "to load your own.",
        kind="info",
    )
else:
    callout(
        "Use the <strong>left-hand navigation</strong> to explore Holdings, "
        "Performance, Allocation, Value over time, Vs benchmark, Costs &amp; tax, "
        "Rebalancing, Risk and Monte Carlo. Use <strong>Change file</strong> in the "
        "sidebar to load a different portfolio.",
        kind="info",
    )

st.divider()

# --------------------------------------------------------------------------- #
# SINTESI (mini-anteprima; il dettaglio è in Holdings)
# --------------------------------------------------------------------------- #
st.subheader("Summary")

holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)

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

st.caption(
    f"Data as of {prices.index[-1]:%d/%m/%Y}  ·  "
    f" {len(tx)} transactions since {tx['date'].min():%d/%m/%Y}"
)
