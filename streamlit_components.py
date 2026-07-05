"""
streamlit_components.py — componenti UI custom del portfolio tracker.

Modulo dedicato ai componenti HTML custom che sostituiscono i widget
nativi di Streamlit dove serve maggiore controllo grafico:

- kpi_card(): sostituisce st.metric. Vantaggi: altezze uniformi
  garantite in riga (anche con card senza delta), formattazione delta
  esplicita (positive/negative/neutral), stile coerente al design
  system del portfolio tracker.

- callout(): sostituisce st.info / st.warning / st.success / st.error.
  Stile FT/Bloomberg: border-left colorato + background pastello +
  tipografia Inter coerente. Titolo opzionale in small-caps.

Le regole CSS delle classi usate (.pt-kpi, .pt-callout, ecc.) sono
definite in streamlit_utils.inject_css() nei blocchi G e H. inject_css()
va chiamata in cima ad ogni pagina prima di usare questi componenti,
altrimenti il rendering sarà "nudo" (HTML senza stile).

Convenzione: le funzioni chiamano st.markdown con unsafe_allow_html=True
e usano html.escape() sui contenuti user-provided per sicurezza. Le
label/value/body sono trattati come testo semplice, non HTML — se
l'utente vuole passare markup deve modificare il componente.
"""
from __future__ import annotations

from html import escape

import streamlit as st

# --------------------------------------------------------------------------- #
# COSTANTI
# --------------------------------------------------------------------------- #
_VALID_DELTA_KINDS = ("positive", "negative", "neutral")
_VALID_CALLOUT_KINDS = ("info", "warning", "success", "danger")


# --------------------------------------------------------------------------- #
# KPI CARD
# --------------------------------------------------------------------------- #
def kpi_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_kind: str = "neutral",
    help: str | None = None,
) -> None:
    """Renderizza una KPI card custom con altezza uniforme garantita.

    Sostituisce `st.metric` con controllo grafico maggiore:
    - Label in small-caps 12px con letter-spacing (stile Bloomberg/FT)
    - Value in 24px JetBrains Mono con tabular-nums (allineamento
      decimali pulito quando più card in riga)
    - Delta come chip colorato (bg pastello + testo scuro semantico)
    - Se delta=None, un placeholder invisibile riserva lo stesso
      spazio del delta: tutte le card in riga risultano della
      stessa altezza senza coordinamento tra chiamate

    Args:
        label: Etichetta della metrica. Es. "Capitale investito",
            "TWR cumulato". Renderizzata in small-caps automaticamente
            dal CSS: passa il testo in case naturale ("Capitale investito"
            non "CAPITALE INVESTITO").

        value: Valore già formattato come stringa. Es. "6,505.20 €",
            "+13.06%", "1.82", "1,719 days". Il componente non conosce
            le regole di formattazione: le decide il chiamante col
            f-string appropriato al tipo di dato.

        delta: Testo del delta (opzionale). Es. "↑ +12.39%",
            "↓ -0.86pp", "vs rf 3.0%". Default None = card senza
            delta ma spazio riservato per uniformità.

        delta_kind: Semantica del delta, uno tra:
            - "positive": chip verde (bg #DCFCE7, text #166534)
            - "negative": chip rosso (bg #FEE2E2, text #991B1B)
            - "neutral": chip grigio (bg #E2E8F0, text #475569)
            Default "neutral". Ignorato se delta=None.
            Semantica esplicita perché inferire dal segno del delta
            è fragile: es. "-0.08pp drag" è negativo tecnicamente
            ma informativo semanticamente.

        help: Testo del tooltip (opzionale). Se presente, un piccolo
            "?" appare accanto alla label; hover mostra il testo in
            un tooltip. Feature-parity con st.metric(help=...).
            Default None = nessun tooltip.

    Returns:
        None. Renderizza direttamente in st.markdown.

    Raises:
        ValueError: se delta_kind non è tra i valori validi.

    Esempio:
        col1, col2, col3 = st.columns(3)
        with col1:
            kpi_card("Capitale investito", f"{invested:,.2f} €")
        with col2:
            kpi_card("P&L", f"+{pnl:,.2f} €",
                     delta=f"↑ +{pnl_pct:.2f}%", delta_kind="positive")
        with col3:
            kpi_card("Sharpe ratio", f"{sharpe:.2f}",
                     delta=f"vs rf {rf:.1%}", delta_kind="neutral",
                     help="Rendimento in eccesso per unità di volatilità.")
    """
    if delta_kind not in _VALID_DELTA_KINDS:
        raise ValueError(
            f"delta_kind '{delta_kind}' non valido. "
            f"Valori ammessi: {_VALID_DELTA_KINDS}"
        )

   # Label con tooltip opzionale
    label_html = escape(label)
    if help is not None:
        label_html += (
            f'<span class="pt-kpi-help" tabindex="0" '
            f'role="button" aria-label="Info: {escape(help)}">'
            f'&#9432;'  # ⓘ info icon
            f'<span class="pt-kpi-tooltip" role="tooltip">'
            f'{escape(help)}</span>'
            f'</span>'
        )

    # Delta: chip visibile se fornito, altrimenti placeholder invisibile
    # che occupa lo stesso spazio per garantire altezze uniformi in riga
    if delta is not None:
        delta_html = (
            f'<span class="pt-kpi-delta pt-kpi-delta--{delta_kind}">'
            f'{escape(delta)}</span>'
        )
    else:
        delta_html = (
            '<span class="pt-kpi-delta pt-kpi-delta--placeholder">'
            '&nbsp;</span>'
        )

    html = (
        f'<div class="pt-kpi">'
        f'<div class="pt-kpi-label">{label_html}</div>'
        f'<div class="pt-kpi-value">{escape(value)}</div>'
        f'{delta_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# CALLOUT
# --------------------------------------------------------------------------- #
def callout(
    body: str,
    kind: str = "info",
    title: str | None = None,
) -> None:
    """Renderizza un callout in stile FT/Bloomberg.

    Sostituisce st.info / st.warning / st.success / st.error con uno
    stile editoriale coerente al design system del portfolio tracker.
    Caratteristiche visive:
    - Border-left colorato (3px) invece che background pieno
    - Background pastello leggero (tono chiaro dello stesso hue)
    - Titolo opzionale in small-caps (stile Bloomberg terminal)
    - Tipografia Inter 13px con line-height rilassata
    - No emoji automatici: il border-left color veicola la semantica

    Args:
        body: Corpo del messaggio. Supporta <strong> per enfasi
            tramite tag HTML (unsafe_allow_html è attivo). Per
            testo semplice viene renderizzato as-is.

        kind: Tipo semantico, uno tra:
            - "info": accento navy #0F4C81 (default)
            - "warning": accento ambra #A16207
            - "success": accento verde #15803D
            - "danger": accento rosso #B91C1C

        title: Titolo opzionale in small-caps sopra il body.
            Es. "Affidabilità bassa", "Interpretazione". Se None,
            il callout ha solo il body. Utile per warning/danger
            dove il titolo dà contesto immediato.

    Returns:
        None. Renderizza direttamente in st.markdown.

    Raises:
        ValueError: se kind non è tra i valori validi.

    Esempio:
        callout(
            "The benchmark VWCE.DE is also one of the ETFs in your "
            "portfolio. Similar performance is expected.",
            kind="info",
        )

        callout(
            "205 days of history (0.56 years): under 1 year of "
            "history, annualization tends to overestimate performance.",
            kind="warning",
            title="Low reliability",
        )

    Note: il parametro body NON viene passato per escape() perché
    supporta HTML minimo (<strong>, <em>). Non passare user input
    non-sanitizzato nel body — in questa app tutto è controllato dallo
    sviluppatore, non è un concern pratico.
    """
    if kind not in _VALID_CALLOUT_KINDS:
        raise ValueError(
            f"kind '{kind}' non valido. "
            f"Valori ammessi: {_VALID_CALLOUT_KINDS}"
        )

    title_html = (
        f'<div class="pt-callout-title">{escape(title)}</div>'
        if title is not None else ""
    )

    html = (
        f'<div class="pt-callout pt-callout--{kind}">'
        f'{title_html}'
        f'<p class="pt-callout-body">{body}</p>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
