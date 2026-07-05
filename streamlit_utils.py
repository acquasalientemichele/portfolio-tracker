"""
streamlit_utils.py — helper condivisi tra le pagine Streamlit.

Punto unico dove si definisce:
- il CSS custom della pagina (inject_css)
- come si caricano i dati base (transactions, prices, settings)
- come si presenta la sidebar globale (brand + nav custom + info file)

Le pagine in `pages/` chiamano queste tre funzioni all'inizio nell'ordine:

    inject_css()
    ensure_data_loaded()
    render_sidebar(current_page="benchmark")  # key da NAV_ITEMS

La nav automatica di Streamlit (`[data-testid="stSidebarNav"]`) viene
nascosta via CSS: la sostituiamo con una nav custom che monta le icone
SVG del design system (assets/icons/) e permette di evidenziare l'item
attivo con il pattern navy del mockup Claude Design.

Tutto ciò che è specifico di Streamlit vive qui o nelle pagine.
I moduli `portfolio.py`, `costs.py`, ecc. restano puri (zero `import
streamlit`), così continuano a funzionare nel notebook senza modifiche.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from textwrap import dedent

import pandas as pd
import streamlit as st

import portfolio as pf

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
TX_FILE = Path("data/transactions.xlsx")
ICONS_DIR = Path("assets/icons")

# Navigation della sidebar custom.
# Ordine = ordine di apparizione. La `key` è l'identificativo passato dalle
# pagine a render_sidebar() per evidenziare l'item attivo. L'`url` è il path
# gestito dal routing multi-page di Streamlit (derivato dal nome file in
# pages/ dopo che Streamlit rimuove prefisso numerico, emoji e .py).
NAV_ITEMS: tuple[dict, ...] = (
    {"key": "holdings",        "label": "Home",            "icon": "home",            "url": "/Holdings"},
    {"key": "performance",     "label": "Performance",     "icon": "performance",     "url": "/Performance"},
    {"key": "allocazione",     "label": "Allocazione",     "icon": "allocazione",     "url": "/Allocazione"},
    {"key": "andamento",       "label": "Andamento",       "icon": "andamento",       "url": "/Andamento"},
    {"key": "benchmark",       "label": "Vs benchmark",    "icon": "benchmark",       "url": "/Benchmark"},
    {"key": "costi",           "label": "Costi e fisco",   "icon": "costi",           "url": "/Costi"},
    {"key": "ribilanciamento", "label": "Ribilanciamento", "icon": "ribilanciamento", "url": "/Ribilanciamento"},
    {"key": "rischio",         "label": "Rischio",         "icon": "rischio",         "url": "/Rischio"},
    {"key": "monte_carlo",     "label": "Monte Carlo",     "icon": "monte-carlo",     "url": "/Monte_Carlo"},
)


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
        # Salva l'ultima data prezzo per mostrarla in sidebar: aiuta l'utente
        # a capire se i dati sono aggiornati senza dover aprire una pagina.
        st.session_state["prices_last_date"] = prices.index.max()

    return (
        st.session_state["tx"],
        st.session_state["prices"],
        st.session_state["settings"],
    )


# --------------------------------------------------------------------------- #
# ICON LOADER
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=None)
def load_icon(name: str) -> str:
    """Carica un'icona SVG dalla cartella `assets/icons/{name}.svg`.

    Le icone hanno `stroke="currentColor"` così ereditano il colore dal
    CSS del contenitore (navy #0F4C81 quando .active, slate #94A3B8 di
    default, tramite le regole del blocco F di inject_css).

    Cache con lru_cache: le SVG sono immutabili durante la sessione,
    lette una volta e riusate a ogni rerun di ogni pagina.

    Return: contenuto SVG come stringa. Se il file non esiste restituisce
    stringa vuota (graceful fallback: l'item appare senza icona invece
    di crashare la pagina).
    """
    path = ICONS_DIR / f"{name}.svg"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# SIDEBAR GLOBALE
# --------------------------------------------------------------------------- #
def render_sidebar(current_page: str = "") -> None:
    """Renderizza la sidebar globale: brand + nav custom + info file + reload.

    La nav automatica di Streamlit è nascosta da inject_css (blocco D).
    Qui iniettiamo:
    1) l'header "PORTFOLIO TRACKER" in navy caps
    2) la nav custom con SVG inline: un item per ogni voce di NAV_ITEMS
    3) la sezione "Dati" con info file + pulsante ricarica (invariata)

    L'item con `key == current_page` riceve la classe `.active` e viene
    evidenziato dal CSS con bordo left navy + background bianco + testo
    e icona in navy.

    Args:
        current_page: chiave dell'item attivo (deve matchare una `key` di
            NAV_ITEMS). Default "": nessun item risulta evidenziato — utile
            per pagine di "landing" o durante refactoring, senza rompere
            nulla.

    Va chiamata da ogni pagina dopo `inject_css()` ed `ensure_data_loaded()`.
    """
    with st.sidebar:
        # --- Brand + nav custom (HTML unico blocco) ---
        parts = ['<div class="pt-brand">Portfolio<br>Tracker</div>',
                 '<nav class="pt-nav">']
        for item in NAV_ITEMS:
            active_cls = " active" if item["key"] == current_page else ""
            icon_svg = load_icon(item["icon"])
            parts.append(
                f'<a href="{item["url"]}" target="_self" '
                f'class="pt-nav-item{active_cls}">'
                f'{icon_svg}<span>{item["label"]}</span>'
                f'</a>'
            )
        parts.append('</nav>')
        st.markdown("".join(parts), unsafe_allow_html=True)

        # --- Sezione Dati (invariata) ---
        st.divider()
        st.header("⚙️ Dati")

        if TX_FILE.exists():
            mtime = datetime.fromtimestamp(TX_FILE.stat().st_mtime)
            st.caption(f"📁 `{TX_FILE.name}`")
            st.caption(f"🕒 File aggiornato: {mtime:%d/%m/%Y %H:%M}")

        # Data dell'ultimo prezzo yfinance (salvata in session_state da
        # ensure_data_loaded). Utile per capire se serve premere Ricarica.
        if "prices_last_date" in st.session_state:
            last_date = st.session_state["prices_last_date"]
            st.caption(f"📈 Prezzi al: {last_date:%d/%m/%Y}")

        if st.button("🔄 Ricarica dati", use_container_width=True,
                     help="Forza il download da yfinance e ricarica l'Excel"):
            # Ordine critico:
            # 1) cancella la cache parquet di portfolio.py (prices_cache.parquet):
            #    senza questo, fetch_prices vede i ticker già in cache e non
            #    ri-scarica da yfinance, restituendo prezzi stale.
            # 2) svuota la cache Streamlit di load_tx/load_settings/fetch_prices.
            # 3) svuota session_state, altrimenti ensure_data_loaded trova
            #    i dati vecchi al rerun e non li ricarica.
            pf.refresh_cache()
            st.cache_data.clear()
            for key in ("tx", "prices", "settings", "prices_last_date"):
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
    D) Sidebar polish — padding ridotto e nav automatica di Streamlit
       nascosta (viene sostituita dalla nav custom in render_sidebar).
    E) `st.metric` come card — sfondo slate-50, border-radius 12px,
       padding 12px. Effetto "KPI card" uniforme su tutte le pagine.
    F) Nav custom della sidebar — stile brand, nav item, hover e active
       state con bordo left navy. Match del mockup Claude Design.
    G) KPI card custom (streamlit_components.kpi_card) — stile identico
       a st.metric ma con controllo garantito sull'altezza in riga
       tramite placeholder invisibile del delta.
    H) Callout (streamlit_components.callout) — stile FT/Bloomberg:
       border-left colorato + background pastello + tipografia coerente.
       Sostituisce st.info/warning/success/error nelle pagine.

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
        /* Nasconde la nav automatica: la sostituiamo con quella custom
           costruita in render_sidebar() (blocco F qui sotto). */
        [data-testid="stSidebarNav"] {
            display: none;
        }

        /* ==== E) st.metric come card ======================================= */
        [data-testid="stMetric"] {
            background-color: #F8FAFC;
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 0.5rem;
        }

        /* ==== F) Nav custom della sidebar ================================== */
        /* Brand "PORTFOLIO TRACKER" in caps navy */
        .pt-brand {
            color: #0F4C81;
            font-weight: 500;
            font-size: 22px;
            letter-spacing: -0.01em;
            line-height: 1.15;
            padding: 4px 6px 24px;
        }
        /* Container della nav */
        .pt-nav {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        /* Singolo item della nav (link) */
        .pt-nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 10px;
            border-radius: 6px;
            font-size: 14px;
            color: #475569;
            text-decoration: none;
            transition: background-color 0.15s ease;
        }
        .pt-nav-item svg {
            flex-shrink: 0;
            color: #94A3B8;
            width: 20px;
            height: 20px;
        }
        .pt-nav-item:hover {
            background-color: #F1F5F9;
            color: #475569;
        }
        .pt-nav-item:hover svg {
            color: #64748B;
        }
        /* Item attivo: bordo left navy + background bianco + testo/icona navy */
        .pt-nav-item.active {
            background: #FFFFFF;
            color: #0F4C81;
            font-weight: 500;
            box-shadow: inset 3px 0 0 #0F4C81;
            border-radius: 0 6px 6px 0;
            padding-left: 12px;
        }
        .pt-nav-item.active svg {
            color: #0F4C81;
        }
        
        /* ==== G) KPI card custom (streamlit_components.kpi_card) =========== */
        /* Container: stesso look di st.metric ma con controllo garantito
           sull'altezza in riga tramite il placeholder invisibile del delta. */
        .pt-kpi {
            background-color: #F8FAFC;
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 0.5rem;
        }
        .pt-kpi-label {
            font-size: 12px;
            color: #64748B;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 500;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .pt-kpi-help {
            font-size: 13px;
            color: #94A3B8;
            cursor: help;
            font-weight: 400;
        }
        .pt-kpi-value {
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            font-variant-numeric: tabular-nums;
            font-feature-settings: 'tnum';
            font-size: 24px;
            font-weight: 500;
            letter-spacing: -0.01em;
            color: #0F172A;
            line-height: 1.15;
        }
        .pt-kpi-delta {
            margin-top: 6px;
            display: inline-block;
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 6px;
            font-weight: 500;
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            font-variant-numeric: tabular-nums;
        }
        .pt-kpi-delta--positive { background: #DCFCE7; color: #166534; }
        .pt-kpi-delta--negative { background: #FEE2E2; color: #991B1B; }
        .pt-kpi-delta--neutral  { background: #E2E8F0; color: #475569; }
        /* Placeholder: invisibile ma occupa lo stesso spazio del delta.
           visibility:hidden (non display:none) mantiene il layout. */
        .pt-kpi-delta--placeholder { visibility: hidden; }

        /* ==== H) Callout (streamlit_components.callout) ==================== */
        /* Stile FT/Bloomberg: border-left colorato + background pastello.
           No border-radius perché single-sided borders non si arrotondano. */
        .pt-callout {
            padding: 12px 16px;
            border-radius: 0;
            margin: 0.5rem 0 1rem;
        }
        .pt-callout-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 500;
            margin: 0 0 6px;
        }
        .pt-callout-body {
            font-size: 13px;
            color: #0F172A;
            line-height: 1.55;
            margin: 0;
        }
        .pt-callout-body strong { font-weight: 500; }

        .pt-callout--info {
            background: #EFF6FF;
            border-left: 3px solid #0F4C81;
        }
        .pt-callout--info .pt-callout-title { color: #0F4C81; }

        .pt-callout--warning {
            background: #FEF9C3;
            border-left: 3px solid #A16207;
        }
        .pt-callout--warning .pt-callout-title { color: #854D0E; }

        .pt-callout--success {
            background: #DCFCE7;
            border-left: 3px solid #15803D;
        }
        .pt-callout--success .pt-callout-title { color: #166534; }

        .pt-callout--danger {
            background: #FEE2E2;
            border-left: 3px solid #B91C1C;
        }
        .pt-callout--danger .pt-callout-title { color: #991B1B; }
                           
        </style>
    """).strip()

    st.markdown(css, unsafe_allow_html=True)
