"""
streamlit_utils.py — helper condivisi tra le pagine Streamlit.

Punto unico dove si definisce:
- il CSS custom della pagina (inject_css)
- come si caricano i dati base (transactions, prices, settings)
- come si presenta la sidebar globale

Le pagine in `pages/` chiamano queste tre funzioni all'inizio nell'ordine:

    inject_css()          # CSS custom (tipografia, KPI cards, sidebar polish)
    ensure_data_loaded()  # tx, prices, settings in session_state
    render_sidebar()      # info file + pulsante ricarica

Tutto ciò che è specifico di Streamlit vive qui o nelle pagine.
I moduli `portfolio.py`, `costs.py`, ecc. restano puri (zero `import
streamlit`), così continuano a funzionare nel notebook senza modifiche.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent

import pandas as pd
import streamlit as st

import portfolio as pf

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
TX_FILE = Path("data/transactions.xlsx")


# --------------------------------------------------------------------------- #
# CACHED LOADERS
# --------------------------------------------------------------------------- #
# Wrappiamo qui le funzioni di portfolio.py con `@st.cache_data` così la
# libreria resta indipendente da Streamlit. La cache è condivisa tra tutte
# le pagine (è globale a livello di app, non per pagina).

@st.cache_data(show_spinner="Carico le transazioni…")
def load_tx(path: str) -> pd.DataFrame:
    """Wrapper cacheato di pf.load_transactions."""
    return pf.load_transactions(path)


@st.cache_data(show_spinner="Carico le impostazioni…")
def load_settings(path: str) -> dict:
    """Wrapper cacheato di pf.load_settings."""
    return pf.load_settings(path)


@st.cache_data(show_spinner="Scarico i prezzi da yfinance…")
def fetch_prices(tickers: tuple[str, ...], start: str) -> pd.DataFrame:
    """Wrapper cacheato di pf.fetch_prices.

    Tickers passati come tuple (hashable) e convertiti a list dentro.
    """
    return pf.fetch_prices(list(tickers), start=start)


# --------------------------------------------------------------------------- #
# ENSURE DATA LOADED
# --------------------------------------------------------------------------- #
def ensure_data_loaded() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Carica i dati base e li mette in session_state se non già presenti.

    Restituisce sempre (tx, prices, settings), così le pagine non devono
    fare lookup espliciti su st.session_state.

    Mettiamo in session_state solo i dati GREZZI (tx, prices, settings).
    I dati derivati (holdings, value_series, twr…) li ricalcolano le pagine
    che ne hanno bisogno: sono operazioni pandas pure, veloci, senza I/O.
    Trade-off: qualche ms in più per pagina in cambio di zero rischi di
    staleness e meno complessità mentale.
    """
    if "tx" not in st.session_state:
        if not TX_FILE.exists():
            st.error(f"❌ File non trovato: `{TX_FILE}`")
            st.info(
                "Verifica che la cartella `data/` esista nella root del "
                "progetto e contenga `transactions.xlsx`."
            )
            st.stop()

        tx = load_tx(str(TX_FILE))
        settings = load_settings(str(TX_FILE))

        start = tx["date"].min().strftime("%Y-%m-%d")
        tickers = tuple(sorted(tx["ticker"].unique()))
        prices = fetch_prices(tickers, start)

        st.session_state["tx"] = tx
        st.session_state["prices"] = prices
        st.session_state["settings"] = settings

    return (
        st.session_state["tx"],
        st.session_state["prices"],
        st.session_state["settings"],
    )


# --------------------------------------------------------------------------- #
# SIDEBAR GLOBALE
# --------------------------------------------------------------------------- #
def render_sidebar() -> None:
    """Renderizza la sidebar globale: info file + pulsante ricarica.

    Va chiamata da ogni pagina dopo `ensure_data_loaded()`.
    Streamlit non ha un meccanismo nativo di "sidebar condivisa" in modalità
    pages/: la sidebar di navigazione è automatica, ma il contenuto extra
    va aggiunto pagina per pagina.
    """
    with st.sidebar:
        st.divider()
        st.header("⚙️ Dati")

        if TX_FILE.exists():
            mtime = datetime.fromtimestamp(TX_FILE.stat().st_mtime)
            st.caption(f"📁 `{TX_FILE.name}`")
            st.caption(f"🕒 Ultima modifica: {mtime:%d/%m/%Y %H:%M}")

        if st.button("🔄 Ricarica dati", use_container_width=True,
                     help="Svuota la cache e ricarica file Excel + prezzi"):
            st.cache_data.clear()
            # Svuota anche session_state, altrimenti i dati vecchi
            # restano fino al prossimo cambio di chiave
            for key in ("tx", "prices", "settings"):
                st.session_state.pop(key, None)
            st.rerun()


# --------------------------------------------------------------------------- #
# CSS INJECTION
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    """Inietta il CSS custom del portfolio tracker nella pagina corrente.

    Da chiamare in cima a ogni pagina, subito dopo `st.set_page_config()`
    e prima di `ensure_data_loaded()` / `render_sidebar()`.

    Il CSS applica cinque blocchi di rifinitura, complementari a quanto
    già definito in `.streamlit/config.toml`:

    A) Chrome cleanup — nasconde il footer "Made with Streamlit" e
       riduce il padding-top del main container (default ~6rem → 2rem).
       Il MainMenu resta visibile (utile in sviluppo).
    B) Tipografia dei numeri — JetBrains Mono con `tabular-nums` sulle
       cifre di `st.metric` e sui componenti HTML con classe `.num-mono`.
       Allineamento decimali pulito e look "terminale finanziario".
    C) Tipografia dei titoli — letter-spacing leggero + font-weight 500
       (Inter Medium) su h1/h2/h3; label delle metric in small-caps
       (uppercase, tracking, size 12px).
    D) Sidebar polish — padding ridotto (i default Streamlit sono un po'
       larghi), hover leggermente più scuro sulla nav automatica.
    E) `st.metric` come card — sfondo slate-50, border-radius 12px,
       padding 12px. Effetto "KPI card" uniforme su tutte le pagine.

    Non modifica nulla che sia già gestito da:
    - `.streamlit/config.toml`  →  colori base, font, radius dei widget
    - `chart_style.py`          →  grafici matplotlib
    - `plotly_style.py` (WIP)   →  grafici Plotly futuri

    Sicuro da chiamare a ogni rerun: Streamlit rimpiazza il blocco
    <style> nella stessa posizione del render tree, non lo accumula.

    Selettori `data-testid` verificati per Streamlit 1.50+. Se aggiorni
    a una major successiva controlla che non siano stati rinominati:
    stMetricValue, stMetricDelta, stMetricLabel, stMetric, stSidebar,
    stSidebarNav, stMainBlockContainer.
    """
    css = dedent("""
        <style>
        /* ==== A) Chrome cleanup ============================================ */
        footer { visibility: hidden; }
        [data-testid="stMainBlockContainer"] {
            padding-top: 2rem;
        }

        /* ==== B) Tipografia dei numeri ===================================== */
        /* JetBrains Mono + tabular-nums per allineamento decimali pulito */
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            font-variant-numeric: tabular-nums;
            font-feature-settings: 'tnum';
            letter-spacing: -0.01em;
        }
        /* Classe custom per componenti HTML delle pagine (KPI cards, tabelle) */
        .num-mono {
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            font-variant-numeric: tabular-nums;
            font-feature-settings: 'tnum';
        }

        /* ==== C) Tipografia dei titoli ===================================== */
        h1, h2, h3 {
            letter-spacing: -0.005em;
            font-weight: 500;
        }
        /* Label delle metric in small-caps stile Bloomberg/FT */
        [data-testid="stMetricLabel"] {
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 12px;
            color: #64748B;
            font-weight: 500;
        }

        /* ==== D) Sidebar polish ============================================ */
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        [data-testid="stSidebarNav"] a:hover {
            background-color: #F1F5F9;
        }

        /* ==== E) st.metric come card ======================================= */
        [data-testid="stMetric"] {
            background-color: #F8FAFC;
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 0.5rem;
        }
        </style>
    """).strip()

    st.markdown(css, unsafe_allow_html=True)
