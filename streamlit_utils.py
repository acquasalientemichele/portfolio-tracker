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

import base64                      
from functools import lru_cache
from io import BytesIO             
from pathlib import Path
from textwrap import dedent
from html import escape

import pandas as pd
import streamlit as st

import portfolio as pf
import costs as cst   
import re                           

from streamlit_components import callout         

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
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
    {"label": "Home",            "slug": None,              "icon": "home"},
    {"label": "Holdings",        "slug": "Holdings",        "icon": "holdings"},
    {"label": "Performance",     "slug": "Performance",     "icon": "performance"},
    {"label": "Allocation",      "slug": "Allocazione",     "icon": "allocazione"},
    {"label": "Value over time", "slug": "Andamento",       "icon": "andamento"},
    {"label": "Vs benchmark",    "slug": "Benchmark",       "icon": "benchmark"},
    {"label": "Costs & tax",     "slug": "Costi",           "icon": "costi"},
    {"label": "Rebalancing",     "slug": "Ribilanciamento", "icon": "ribilanciamento"},
    {"label": "Risk",            "slug": "Rischio",         "icon": "rischio"},
    {"label": "Monte Carlo",     "slug": "Monte_Carlo",     "icon": "monte-carlo"},
)

@lru_cache(maxsize=None)
def _page_path(slug: str) -> str:
    """Risolve il file-pagina in pages/ che termina con _{slug}.py.

    Evita di hardcodare numero/emoji del filename (fragili). Fallback ad
    app.py se non trovato, così st.page_link non riceve mai un path invalido.
    """
    matches = sorted(PAGES_DIR.glob(f"*_{slug}.py"))
    return str(matches[0]) if matches else "app.py"


def _nav_key(item: dict) -> str:
    """Chiave DOM stabile per una voce di nav.

    st.container(key=X) rende un elemento con classe `st-key-X`: è un hook
    pubblico e stabile, a differenza dei data-testid interni o del match
    sull'href (che cambiano tra versioni di Streamlit).
    """
    base = "home" if item["slug"] is None else item["slug"]
    return "nav_" + re.sub(r"[^a-z0-9]+", "_", base.lower())


def _icon_url(svg: str, color: str) -> str:
    """SVG → data URI con il colore già sostituito.

    Le icone hanno stroke="currentColor": in un <img>/background-image
    currentColor non si risolve, quindi lo rimpiazziamo a monte con
    l'esadecimale desiderato e generiamo una variante per stato.
    """
    colored = svg.replace("currentColor", color)
    b64 = base64.b64encode(colored.encode("utf-8")).decode("ascii")
    return f'url("data:image/svg+xml;base64,{b64}")'


def _nav_css(current_page: str) -> str:
    """CSS della nav sidebar: design system + icone SVG custom.

    Le icone sono background-image sull'<a> (non ::before + mask-image, che
    non rendeva), con lo spazio riservato da padding-left. Tre varianti di
    colore: slate default, navy su hover e sull'item attivo.

    Due accortezze:
    - i selettori sono costruiti con sel(), che applica il suffisso a OGNI
      voce (f'{lista} p' lo attaccherebbe solo all'ultima);
    - sugli anchor si usa SEMPRE background-color, mai la shorthand
      background, che azzererebbe background-image.
    """
    SLATE, NAVY = "#94A3B8", "#0F4C81"
    keys = [_nav_key(i) for i in NAV_ITEMS]

    def sel(suffix: str = "") -> str:
        return ", ".join(f".st-key-{k} a{suffix}" for k in keys)

    r = [
        # Container neutro
        f'{", ".join(f".st-key-{k}" for k in keys)}{{background:transparent!important;'
        f'border:none!important;padding:0!important;box-shadow:none!important;}}',
        # Riga di nav (padding-left 44px = spazio per l'icona)
        f'{sel()}{{display:flex!important;align-items:center!important;width:100%!important;'
        f'padding:9px 12px 9px 44px!important;margin:1px 0!important;border-radius:6px!important;'
        f'background-color:transparent!important;background-repeat:no-repeat!important;'
        f'background-position:12px center!important;background-size:20px 20px!important;'
        f'text-decoration:none!important;transition:background-color .15s ease!important;}}',
        # Testo della label
        f'{sel(" p")}, {sel(" span")}, {sel(" div")}{{font-size:14px!important;'
        f'font-weight:500!important;color:#64748B!important;margin:0!important;'
        f'line-height:1.35!important;letter-spacing:0!important;}}',
        # Hover
        f'{sel(":hover")}{{background-color:#F1F5F9!important;}}',
        f'{sel(":hover p")}, {sel(":hover span")}{{color:{NAVY}!important;}}',
    ]

    # Icone: variante slate (default) + navy (hover), una regola per voce
    for item in NAV_ITEMS:
        k, svg = _nav_key(item), load_icon(item["icon"])
        if not svg:
            continue  # icona mancante (es. holdings.svg): voce senza icona
        r.append(f'.st-key-{k} a{{background-image:{_icon_url(svg, SLATE)}!important;}}')
        r.append(f'.st-key-{k} a:hover{{background-image:{_icon_url(svg, NAVY)}!important;}}')

    # Stato attivo: sfondo bianco, barra navy, testo e icona navy
    active = next(
        (i for i in NAV_ITEMS
         if ("home" if i["slug"] is None else i["slug"].lower()) == current_page),
        None,
    )
    if active:
        k, svg = _nav_key(active), load_icon(active["icon"])
        r.append(f'.st-key-{k} a{{background-color:#FFFFFF!important;'
                 f'box-shadow:inset 3px 0 0 {NAVY}!important;'
                 f'border-radius:0 6px 6px 0!important;}}')
        r.append(f'.st-key-{k} a p, .st-key-{k} a span, .st-key-{k} a div'
                 f'{{color:{NAVY}!important;font-weight:600!important;}}')
        if svg:
            r.append(f'.st-key-{k} a{{background-image:{_icon_url(svg, NAVY)}!important;}}')

    return "<style>" + "".join(r) + "</style>"

def _btn_icon_css(key: str, icon: str, color: str, size: int = 17) -> str:
    """Icona dentro un pulsante Streamlit, affiancata alla label.

    Il testo del bottone sta in un <p>: lo rendiamo flex e ci attacchiamo
    un ::before con l'icona, così icona e label restano centrate insieme.
    """
    svg = load_icon(icon)
    if not svg:
        return ""
    return (f'.st-key-{key} button p{{display:flex!important;align-items:center!important;'
            f'justify-content:center!important;gap:8px!important;}}'
            f'.st-key-{key} button p::before{{content:""!important;flex:0 0 {size}px!important;'
            f'width:{size}px!important;height:{size}px!important;'
            f'background-image:{_icon_url(svg, color)}!important;'
            f'background-repeat:no-repeat!important;background-position:center!important;'
            f'background-size:contain!important;}}')


def _sidebar_data_css() -> str:
    """CSS della sezione 'Dati': header, righe info, due pulsanti.

    Gerarchia visiva: 'Aggiorna prezzi' è primario (fill navy, azione
    frequente), 'Cambia file' secondario (outline, azione rara e
    distruttiva). Le righe info usano JetBrains Mono come i valori KPI.
    """
    NAVY, SLATE, WHITE = "#0F4C81", "#94A3B8", "#FFFFFF"
    r = [
        # Header "DATI"
        '.pt-sb-head{display:flex;align-items:center;gap:8px;margin:4px 0 10px;}',
        f'.pt-sb-head svg{{width:15px;height:15px;color:{SLATE};flex:0 0 15px;}}',
        f'.pt-sb-head span{{font-family:"JetBrains Mono",monospace;font-size:11px;'
        f'font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:{SLATE};}}',
        # Righe info (file, data prezzi)
        '.pt-sb-row{display:flex;align-items:center;gap:8px;margin:0 0 6px;}',
        f'.pt-sb-row svg{{width:14px;height:14px;color:{SLATE};flex:0 0 14px;}}',
        f'.pt-sb-row span{{font-family:"JetBrains Mono",monospace;font-size:11.5px;'
        f'color:#64748B;line-height:1.4;overflow-wrap:anywhere;}}',
        # Pulsante primario
        f'.st-key-btn_prices button{{width:100%!important;background-color:{NAVY}!important;'
        f'border:1px solid {NAVY}!important;border-radius:7px!important;'
        f'padding:9px 12px!important;box-shadow:none!important;}}',
        f'.st-key-btn_prices button p{{color:{WHITE}!important;font-size:13.5px!important;'
        f'font-weight:600!important;}}',
        '.st-key-btn_prices button:hover{background-color:#0D4270!important;'
        'border-color:#0D4270!important;}',
        # Pulsante secondario
        f'.st-key-btn_file button{{width:100%!important;background-color:{WHITE}!important;'
        f'border:1px solid #E2E8F0!important;border-radius:7px!important;'
        f'padding:9px 12px!important;box-shadow:none!important;}}',
        f'.st-key-btn_file button p{{color:{NAVY}!important;font-size:13.5px!important;'
        f'font-weight:500!important;}}',
        '.st-key-btn_file button:hover{background-color:#F8FAFC!important;'
        'border-color:#CBD5E1!important;}',
        # Icone dei pulsanti
        _btn_icon_css("btn_prices", "refresh", WHITE),
        _btn_icon_css("btn_file", "folder-open", NAVY),
    ]
    return "<style>" + "".join(x for x in r if x) + "</style>"

def home_css() -> str:
    """CSS della pagina Home (onboarding).

    Copre: card contenitore, eyebrow, step numerati, pulsante primario di
    download, restyle del file_uploader (testi in italiano), separatore
    'oppure', card demo e nota finale.
    """
    NAVY, SLATE, WHITE, NAVY_H = "#0F4C81", "#94A3B8", "#FFFFFF", "#0D4270"
    r = [
        '.st-key-pt_card_data, .st-key-pt_card_demo{background:#FFFFFF!important;'
        'border:1px solid #E2E8F0!important;border-radius:12px!important;'
        'padding:26px 28px!important;margin-bottom:8px!important;}',
        f'.pt-eyebrow{{font-family:"JetBrains Mono",monospace;font-size:11px;font-weight:600;'
        f'letter-spacing:.11em;text-transform:uppercase;color:{SLATE};margin:0 0 18px;}}',
        '.pt-steps{display:flex;flex-wrap:wrap;gap:14px 34px;margin:0 0 22px;}',
        '.pt-step{display:flex;align-items:center;gap:10px;}',
        f'.pt-step-n{{flex:0 0 28px;width:28px;height:28px;border-radius:50%;'
        f'display:flex;align-items:center;justify-content:center;font-size:12.5px;'
        f'font-weight:600;background:#F1F5F9;color:{SLATE};}}',
        f'.pt-step-n.is-active{{background:{NAVY};color:{WHITE};}}',
        '.pt-step-l{font-size:14.5px;color:#334155;font-weight:500;}',
        f'.pt-help{{font-size:13px;color:{SLATE};margin:10px 0 0;}}',
        '.pt-hr{height:1px;background:#E2E8F0;margin:22px 0;}',
        '.pt-or{display:flex;align-items:center;gap:16px;margin:22px 0;}',
        '.pt-or::before,.pt-or::after{content:"";flex:1;height:1px;background:#E2E8F0;}',
        f'.pt-or span{{font-size:13px;color:{SLATE};}}',
        '.pt-demo-t{font-size:15.5px;font-weight:600;color:#0F172A;margin:0 0 4px;}',
        '.pt-demo-s{font-size:13.5px;color:#64748B;margin:0;}',
        f'.pt-note{{font-size:12.5px;color:{SLATE};text-align:center;margin:18px 0 0;}}',
        # Pulsante primario (download template)
        f'.st-key-btn_template button{{background-color:{NAVY}!important;'
        f'border:1px solid {NAVY}!important;border-radius:8px!important;'
        f'padding:11px 20px!important;box-shadow:none!important;}}',
        f'.st-key-btn_template button p{{color:{WHITE}!important;font-size:14.5px!important;'
        f'font-weight:600!important;}}',
        f'.st-key-btn_template button:hover{{background-color:{NAVY_H}!important;'
        f'border-color:{NAVY_H}!important;}}',
        # Pulsante demo (outline navy)
        f'.st-key-btn_demo button{{width:100%!important;background-color:{WHITE}!important;'
        f'border:1px solid {NAVY}!important;border-radius:8px!important;'
        f'padding:11px 18px!important;box-shadow:none!important;}}',
        f'.st-key-btn_demo button p{{color:{NAVY}!important;font-size:14.5px!important;'
        f'font-weight:600!important;}}',
        '.st-key-btn_demo button:hover{background-color:#F8FAFC!important;}',
        # File uploader: dropzone tratteggiata
        '.st-key-pt_upload [data-testid="stFileUploaderDropzone"]{'
        'background:#F8FAFC!important;border:1.5px dashed #CBD5E1!important;'
        'border-radius:10px!important;padding:20px 22px!important;}',
        '.st-key-pt_upload [data-testid="stFileUploaderDropzone"]:hover{'
        'border-color:#94A3B8!important;}',
        # Testi in italiano: azzero l'originale inglese e inserisco il mio
        '.st-key-pt_upload [data-testid="stFileUploaderDropzoneInstructions"] > div{'
        'font-size:0!important;line-height:0!important;}',
        '.st-key-pt_upload [data-testid="stFileUploaderDropzoneInstructions"] > div::after{'
        'content:"Drag and drop your file here\\A XLSX · max 200MB";white-space:pre-line;'
        'display:block;font-size:14.5px!important;line-height:1.45!important;'
        'color:#334155!important;font-weight:500;}',
        '.st-key-pt_upload [data-testid="stFileUploaderDropzone"] button{'
        'font-size:0!important;background:#FFFFFF!important;border:1px solid #E2E8F0!important;'
        'border-radius:7px!important;padding:9px 16px!important;box-shadow:none!important;}',
        f'.st-key-pt_upload [data-testid="stFileUploaderDropzone"] button::after{{'
        f'content:"Browse files";font-size:13.5px!important;font-weight:500!important;'
        f'color:{NAVY}!important;}}',
        _btn_icon_css("btn_template", "download", WHITE, size=18),
        _btn_icon_css("btn_demo", "play-circle", NAVY, size=18),
    ]
    return "<style>" + "".join(x for x in r if x) + "</style>"

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
                "Couldn't download prices from yfinance right now. "
                "Try again with <strong>Refresh prices</strong> in the sidebar.",
                kind="danger",
            )
            st.stop()

        if prices.empty:
            callout(
                "yfinance returned no prices for the portfolio tickers. "
                "Check that the tickers in your file are correct. ",
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
        # CSS della nav (design system + icone SVG via mask-image)
        st.markdown(_nav_css(current_page), unsafe_allow_html=True)


        # --- Brand ---
        st.markdown('<div class="pt-brand">Portfolio<br>Tracker</div>',
                    unsafe_allow_html=True)

        # --- Nav: st.page_link (client-side, PRESERVA session_state).
        #     I vecchi <a href> facevano un full reload azzerando la sessione.
        #     Niente icon=: le icone arrivano dal CSS sopra. ---
        for item in NAV_ITEMS:
            page = "app.py" if item["slug"] is None else _page_path(item["slug"])
            # Il container con key= crea la classe st-key-* su cui aggancia il CSS.
            with st.container(key=_nav_key(item)):
                st.page_link(page, label=item["label"])

        # --- Sezione Dati (solo con un dataset caricato) ---
        if "workbook_bytes" in st.session_state:
            st.markdown(_sidebar_data_css(), unsafe_allow_html=True)
            st.divider()

            # Header + righe info: SVG inline, così ereditano il colore dal CSS.
            rows = [f'<div class="pt-sb-head">{load_icon("settings")}<span>Data</span></div>']
            source_name = st.session_state.get("source_name")
            if source_name:
                rows.append(f'<div class="pt-sb-row">{load_icon("file-data")}'
                            f'<span>{escape(source_name)}</span></div>')
            if "prices_last_date" in st.session_state:
                d = st.session_state["prices_last_date"]
                rows.append(f'<div class="pt-sb-row">{load_icon("price-clock")}'
                            f'<span>Prices as of {d:%d/%m/%Y}</span></div>')
            st.markdown("".join(rows), unsafe_allow_html=True)

            st.write("")  # micro-spaziatura prima dei pulsanti

            # Primario: azione frequente. Il container key= aggancia il CSS.
            with st.container(key="btn_prices"):
                if st.button("Refresh prices",
                             help="Download again prices from yfinance, keeping "
                                  "the same transactions file"):
                    pf.refresh_cache()
                    st.cache_data.clear()
                    for key in ("tx", "prices", "settings", "costs", "prices_last_date"):
                        st.session_state.pop(key, None)
                    st.rerun()

            # Secondario: azione rara e distruttiva.
            with st.container(key="btn_file"):
                if st.button("Change file",
                             help="Clear the current data and return to the Home page"):
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
