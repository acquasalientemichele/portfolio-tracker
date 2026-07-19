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
from io import BytesIO   

import pandas as pd
import streamlit as st

import portfolio as pf
import costs as cst            
from streamlit_components import callout

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
TX_FILE = Path("data/transactions.xlsx")
ICONS_DIR = Path("assets/icons")
PAGES_DIR = Path("pages")

@lru_cache(maxsize=None)
def _page_path(slug: str) -> str:
    """Risolve il file-pagina in pages/ che termina con _{slug}.py.

    Evita di hardcodare numero/emoji del filename (fragili). Fallback ad
    app.py se non trovato, così st.page_link non riceve mai un path invalido.
    """
    matches = sorted(PAGES_DIR.glob(f"*_{slug}.py"))
    return str(matches[0]) if matches else "app.py"

# Navigation della sidebar custom.
# Ordine = ordine di apparizione. La `key` è l'identificativo passato dalle
# pagine a render_sidebar() per evidenziare l'item attivo. L'`url` è il path
# gestito dal routing multi-page di Streamlit (derivato dal nome file in
# pages/ dopo che Streamlit rimuove prefisso numerico, emoji e .py).
NAV_ITEMS: tuple[dict, ...] = (
    {"label": "Home",            "slug": None,             "icon": ":material/home:"},
    {"label": "Holdings",        "slug": "Holdings",       "icon": ":material/account_balance_wallet:"},
    {"label": "Performance",     "slug": "Performance",    "icon": ":material/trending_up:"},
    {"label": "Allocazione",     "slug": "Allocazione",    "icon": ":material/donut_small:"},
    {"label": "Andamento",       "slug": "Andamento",      "icon": ":material/show_chart:"},
    {"label": "Vs benchmark",    "slug": "Benchmark",      "icon": ":material/leaderboard:"},
    {"label": "Costi e fisco",   "slug": "Costi",          "icon": ":material/receipt_long:"},
    {"label": "Ribilanciamento", "slug": "Ribilanciamento","icon": ":material/balance:"},
    {"label": "Rischio",         "slug": "Rischio",        "icon": ":material/monitoring:"},
    {"label": "Monte Carlo",     "slug": "Monte_Carlo",    "icon": ":material/casino:"},
)


# --------------------------------------------------------------------------- #
# CACHED LOADERS
# --------------------------------------------------------------------------- #
# Wrappiamo qui le funzioni di portfolio.py con `@st.cache_data` così la
# libreria resta indipendente da Streamlit. La cache è condivisa tra tutte
# le pagine (è globale a livello di app, non per pagina).

@st.cache_data(show_spinner="Leggo il file delle operazioni…")
def load_bundle(workbook_bytes: bytes) -> dict:
    """Parsa il workbook caricato in un bundle di dati grezzi.

    Apre UN solo pd.ExcelFile dai bytes e lo riusa per tutti i loader:
    pd.read_excel accetta un ExcelFile e non lo 'consuma', quindi i moduli
    core restano immutati e Streamlit-free. `bytes` è hashable → la cache
    deduplica tra le pagine.

    Returns: {"tx": DataFrame, "settings": dict, "costs": dict}
    """
    xls = pd.ExcelFile(BytesIO(workbook_bytes))
    return {
        "tx": pf.load_transactions(xls),
        "settings": pf.load_settings(xls),
        "costs": cst.load_costs(xls),
    }


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
    """Garantisce i dati in session_state, o rimanda alla Home.

    Unico punto d'ingresso dati. I bytes del workbook vivono in
    session_state["workbook_bytes"], popolati dall'onboarding in app.py.
    Mette in session_state i soli dati GREZZI (tx, prices, settings, costs);
    i derivati li ricalcolano le pagine.
    """
    # Nessun dato (link diretto a pagina interna, o dopo "Cambia file"):
    # rimanda alla Home, dove sta l'onboarding con upload/demo.
    if "workbook_bytes" not in st.session_state:
        st.switch_page("app.py")

    if "tx" not in st.session_state:
        bundle = load_bundle(st.session_state["workbook_bytes"])
        tx = bundle["tx"]
        settings = bundle["settings"]

        start = tx["date"].min().strftime("%Y-%m-%d")
        tickers = tuple(sorted(tx["ticker"].unique()))
        try:
            prices = fetch_prices(tickers, start)
        except Exception:
            callout(
                "Non riesco a scaricare i prezzi da yfinance in questo momento. "
                "Riprova con <strong>🔄 Aggiorna prezzi</strong> nella sidebar.",
                kind="danger",
            )
            st.stop()

        if prices.empty:
            callout(
                "yfinance non ha restituito prezzi per i ticker del portafoglio. "
                "Verifica che i ticker nel file siano corretti (es. VWCE.DE).",
                kind="danger",
            )
            st.stop()

        st.session_state["tx"] = tx
        st.session_state["prices"] = prices
        st.session_state["settings"] = settings
        st.session_state["costs"] = bundle["costs"]
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
        # --- Brand ---
        st.markdown('<div class="pt-brand">Portfolio<br>Tracker</div>',
                    unsafe_allow_html=True)

        # --- Nav: st.page_link = navigazione CLIENT-SIDE che PRESERVA
        #     st.session_state. I vecchi <a href> facevano un full reload,
        #     azzerando la sessione (e con essa i dati da upload/demo). ---
        for item in NAV_ITEMS:
            page = "app.py" if item["slug"] is None else _page_path(item["slug"])
            st.page_link(page, label=item["label"], icon=item["icon"],
                         use_container_width=True)

        # --- Sezione Dati (solo quando c'è un dataset caricato) ---
        if "workbook_bytes" in st.session_state:
            st.divider()
            st.header("⚙️ Dati")

            source_name = st.session_state.get("source_name")
            if source_name:
                st.caption(f"📁 {source_name}")
            if "prices_last_date" in st.session_state:
                st.caption(f"📈 Prezzi al: {st.session_state['prices_last_date']:%d/%m/%Y}")

            # Due azioni distinte: aggiornare i prezzi ≠ cambiare file.
            if st.button("🔄 Aggiorna prezzi", use_container_width=True,
                         help="Ri-scarica i prezzi da yfinance mantenendo lo "
                              "stesso file di operazioni"):
                # refresh_cache() svuota prices_cache.parquet, poi le cache
                # Streamlit; teniamo workbook_bytes → si ri-scaricano solo i prezzi.
                pf.refresh_cache()
                st.cache_data.clear()
                for key in ("tx", "prices", "settings", "costs", "prices_last_date"):
                    st.session_state.pop(key, None)
                st.rerun()

            if st.button("📁 Cambia file", use_container_width=True,
                         help="Rimuovi i dati correnti e torna alla Home"):
                st.cache_data.clear()
                for key in ("tx", "prices", "settings", "costs",
                            "prices_last_date", "workbook_bytes", "source_name"):
                    st.session_state.pop(key, None)
                st.switch_page("app.py")


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
            font-variant-numeric: tabular-nums;
            font-feature-settings: 'tnum';
            letter-spacing: -0.01em;
        }
        }
        /* Classe custom per componenti HTML delle pagine (KPI cards, tabelle) */
        .num-mono {
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
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            color: #94A3B8;
            cursor: help;
            font-weight: 400;
            outline: none;
            user-select: none;
        }
        .pt-kpi-help:hover,
        .pt-kpi-help:focus {
            color: #64748B;
        }
        /* Tooltip custom: appare al hover (desktop) e al focus (click/tap).
           Sostituisce il tooltip nativo HTML title= che appariva solo su
           hover con delay e non su mobile. Feature-parity con st.metric. */
        .pt-kpi-tooltip {
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            width: 260px;
            padding: 10px 12px;
            background: #1E293B;
            color: #F8FAFC;
            border-radius: 6px;
            font-size: 12px;
            line-height: 1.5;
            text-transform: none;
            letter-spacing: normal;
            font-weight: 400;
            text-align: left;
            visibility: hidden;
            opacity: 0;
            transition: opacity 0.15s ease;
            z-index: 1000;
            pointer-events: none;
            white-space: normal;
        }
        /* Piccola freccia sotto il tooltip che punta all'icona ⓘ */
        .pt-kpi-tooltip::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 5px solid transparent;
            border-top-color: #1E293B;
        }
        .pt-kpi-help:hover .pt-kpi-tooltip,
        .pt-kpi-help:focus .pt-kpi-tooltip {
            visibility: visible;
            opacity: 1;
        }
        .pt-kpi-value {
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
