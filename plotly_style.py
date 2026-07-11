"""
plotly_style.py — stile coerente per i grafici interattivi Plotly.

Analogo funzionale di `chart_style.py` per matplotlib, dedicato ai
grafici che beneficiano dell'interattività (hover unificato, zoom, pan,
download PNG). Usato nelle pagine dove esplorare i dati aggiunge valore:
- Performance / TWR cumulato
- Andamento del valore
- Vs Benchmark
- Rischio / Drawdown underwater

Le altre pagine (Allocazione donut, Costi waterfall, Monte Carlo fan
chart) continuano a usare `chart_style.py` (matplotlib) perché sono
grafici statici / illustrativi che non guadagnano dall'interattività.

Convenzioni:
- La palette è importata da `chart_style` per single source of truth.
  Cambiare un colore in `chart_style.COLORS` propaga automaticamente
  ai grafici Plotly (e viceversa non c'è dipendenza).
- Font Inter globale, coerente con l'UI Streamlit (caricato via Google
  Fonts nel `.streamlit/config.toml`).
- Formato numeri US (dot decimal, comma thousands) per coerenza con
  le tabelle `st.column_config.NumberColumn`.

Pattern d'uso in una pagina:

    import plotly.graph_objects as go
    import plotly_style as ps

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=twr_series, name="TWR",
        line=dict(color=ps.COLORS["value"], width=2.2),
    ))
    ps.add_area_shading(fig, dates, twr_series, split_at=0)
    ps.style_axes(fig, y_format="percent")
    ps.hover_unified(fig)
    ps.add_endline_annotations(fig, [
        {"y": twr_series.iloc[-1],
         "text": f"{twr_series.iloc[-1]:+.2%}",
         "color": ps.COLORS["value"]},
    ])
    ps.apply_layout(
        fig,
        title="Time-Weighted Return",
        subtitle="Rendimento cumulato lordo degli strumenti",
        source="yfinance",
    )
    st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)
"""
from __future__ import annotations

import plotly.graph_objects as go

from chart_style import COLORS, PALETTE

# --------------------------------------------------------------------------- #
# CONFIG PLOTLY GLOBALE
# --------------------------------------------------------------------------- #
# Config passato a st.plotly_chart(..., config=PLOTLY_CONFIG).
# Nasconde il logo Plotly nella modebar, semplifica i tool di interazione
# (rimosse selezioni lasso/select che non servono per dati finanziari),
# configura il download PNG in qualità retina.
PLOTLY_CONFIG: dict = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "lasso2d",     # selezione lasso (data science, non utile qui)
        "select2d",    # selezione rettangolare (idem)
        "autoScale2d", # ridondante con zoom out
    ],
    "toImageButtonOptions": {
        "format":   "png",
        "filename": "portfolio_chart",
        "height":   720,
        "width":    1280,
        "scale":    2,   # retina quality per export
    },
}


# --------------------------------------------------------------------------- #
# LAYOUT — titolo editoriale + footer fonte
# --------------------------------------------------------------------------- #
def apply_layout(
    fig: go.Figure,
    title: str,
    subtitle: str | None = None,
    source: str | None = None,
    height: int = 420,
) -> None:
    """Applica il layout editoriale del portfolio tracker.

    Equivalente Plotly di `chart_style.add_title()`:
    - Titolo bold + subtitle muted allineati a sinistra
    - Footer con fonte in italic (opzionale)
    - Background bianco, font Inter (coerente con l'UI Streamlit)
    - Margini calibrati per lasciare spazio a headline + footer

    Args:
        fig: figura Plotly da stilare (modificata in-place).
        title: titolo principale (bold, 16px, navy).
        subtitle: sottotitolo grigio (11px). None = nessun sottotitolo.
        source: footer con fonte in italic (10px, muted). Es. "yfinance".
        height: altezza in pixel del grafico. Default 420.
            Override per grafici particolari (es. fan chart = 500,
            drawdown underwater compatto = 320).
    """
    annotations = []

    # Titolo (bold, allineato a sinistra)
    annotations.append(dict(
        text=f"<b>{title}</b>",
        xref="paper", yref="paper",
        x=0, y=1.15,
        xanchor="left", yanchor="top",
        showarrow=False,
        font=dict(size=16, color=COLORS["fg"], family="Inter, sans-serif"),
    ))

    # Sottotitolo (muted, sotto il titolo)
    if subtitle:
        annotations.append(dict(
            text=subtitle,
            xref="paper", yref="paper",
            x=0, y=1.08,
            xanchor="left", yanchor="top",
            showarrow=False,
            font=dict(size=11, color=COLORS["muted"], family="Inter, sans-serif"),
        ))

    # Footer con fonte (italic, in basso a sinistra)
    if source:
        annotations.append(dict(
            text=f"<i>{source}</i>",
            xref="paper", yref="paper",
            x=0, y=-0.12,
            xanchor="left", yanchor="top",
            showarrow=False,
            font=dict(size=10, color=COLORS["muted"], family="Inter, sans-serif"),
        ))

    fig.update_layout(
        height=height,
        plot_bgcolor=COLORS["bg"],
        paper_bgcolor=COLORS["bg"],
        font=dict(family="Inter, sans-serif", color=COLORS["fg"]),
        # Margini: top per titolo+subtitle, bottom per fonte+asse X (b=90
        # per garantire che la fonte non sia coperta dall'expander sotto).
        margin=dict(l=60, r=80, t=80, b=90),
        annotations=list(fig.layout.annotations) + annotations,
        showlegend=False,   # usiamo endline annotations invece
        # Formato numeri US (dot decimal, comma thousands)
        separators=".,",
    )


# --------------------------------------------------------------------------- #
# ASSI — spine puliti, griglia orizzontale, formattazione
# --------------------------------------------------------------------------- #
def style_axes(
    fig: go.Figure,
    y_format: str | None = None,
    x_is_date: bool = True,
) -> None:
    """Applica lo stile base agli assi.

    Equivalente Plotly di `chart_style.style_axis()`:
    - Spine top/right rimossi (in Plotly = mostro solo asse X in basso
      e asse Y a sinistra, senza mirror)
    - Griglia solo orizzontale, hairline colore `#E2E8F0`
    - Colori tick e label muted grigio
    - Formattazione asse Y: percent (12.3%) / euro (€1,234) / plain

    Args:
        fig: figura Plotly (modificata in-place).
        y_format: formato asse Y. Valori:
            - "percent" → "12.3%"
            - "euro"    → "€1,234"
            - None      → default Plotly (numero raw)
        x_is_date: True se asse X è temporale (default). Configura
            tick format come "Mar 26". False per assi X numerici.
    """
    # Asse X
    xaxis_config = dict(
        showline=True,
        linecolor=COLORS["muted"],
        linewidth=0.6,
        showgrid=False,             # no griglia verticale
        zeroline=False,
        ticks="outside",
        tickcolor=COLORS["muted"],
        tickfont=dict(size=10, color=COLORS["muted"]),
        mirror=False,               # no spine top
    )
    if x_is_date:
        xaxis_config["tickformat"] = "%b %y"

    # Asse Y
    yaxis_config = dict(
        showline=True,
        linecolor=COLORS["muted"],
        linewidth=0.6,
        showgrid=True,
        gridcolor=COLORS["grid"],
        gridwidth=0.6,
        zeroline=False,
        ticks="outside",
        tickcolor=COLORS["muted"],
        tickfont=dict(size=10, color=COLORS["muted"]),
        mirror=False,               # no spine right
    )
    if y_format == "percent":
        yaxis_config["tickformat"] = ".1%"
    elif y_format == "euro":
        yaxis_config["tickformat"] = "$,.0f"  # $ in tickformat = simbolo generico
        yaxis_config["tickprefix"] = "€"
        yaxis_config["tickformat"] = ",.0f"

    fig.update_xaxes(**xaxis_config)
    fig.update_yaxes(**yaxis_config)


# --------------------------------------------------------------------------- #
# END-OF-LINE ANNOTATIONS — etichette sui valori finali delle serie
# --------------------------------------------------------------------------- #
def add_endline_annotations(
    fig: go.Figure,
    annotations: list[dict],
) -> None:
    """Aggiunge etichette allineate a destra sui valori finali di ogni serie.

    Equivalente Plotly delle end-of-line annotations di `chart_style`.
    Sostituisce la legenda tradizionale: l'utente vede il colore e il
    valore finale della serie proprio dove finisce la linea.

    Il posizionamento X è ricavato automaticamente dal max dell'asse X
    di ogni trace già aggiunto alla figura. Le annotazioni sono
    posizionate con `xshift=8` per un piccolo gap dalla fine della linea.

    Args:
        fig: figura Plotly (modificata in-place). Le trace devono
            essere già state aggiunte.
        annotations: lista di dict con chiavi:
            - "y": valore Y dove appare l'etichetta (deve corrispondere
                   al valore finale della serie)
            - "text": testo dell'etichetta. Es. "+13.06%", "€7,356"
            - "color": colore hex dell'etichetta (di solito lo stesso
                       della serie corrispondente)
            - "x": (opzionale) valore X dell'ancoraggio. Se omesso,
                   viene usato l'ultimo X della prima trace nella figura.

    Esempio:
        add_endline_annotations(fig, [
            {"y": 0.1306, "text": "+13.06%", "color": COLORS["value"]},
            {"y": 0.1462, "text": "+14.62%", "color": COLORS["benchmark"]},
        ])
    """
    # Ricavo la X finale dalla prima trace (assumo tutte le serie
    # abbiano lo stesso asse X)
    if not fig.data:
        return

    default_x = fig.data[0].x[-1] if len(fig.data[0].x) > 0 else None

    new_annotations = []
    for ann in annotations:
        x_val = ann.get("x", default_x)
        new_annotations.append(dict(
            x=x_val,
            y=ann["y"],
            text=ann["text"],
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            xshift=8,   # gap dalla fine della linea
            font=dict(
                size=11,
                color=ann["color"],
                family="Inter, sans-serif",
            ),
        ))

    existing = list(fig.layout.annotations)
    fig.update_layout(annotations=existing + new_annotations)


# --------------------------------------------------------------------------- #
# HOVER UNIFICATO — passi il mouse su una data, vedi tutti i valori
# --------------------------------------------------------------------------- #
def hover_unified(
    fig: go.Figure,
    x_format: str = "%d %b %Y",
) -> None:
    """Configura hover unificato: passi il mouse su una data, vedi tutti
    i valori delle serie insieme in una sola tooltip.

    Nessun equivalente in matplotlib — è il vero valore aggiunto di
    Plotly per grafici a serie temporali con più linee sovrapposte.
    Utile per confrontare portafoglio vs benchmark, o TWR lordo vs
    netto vs benchmark su Vs Benchmark.

    Args:
        fig: figura Plotly (modificata in-place).
        x_format: formato data mostrato nella tooltip.
            Default "%d %b %Y" → "15 Mar 2026".
            Alternative: "%b %Y" (compatto), "%Y-%m-%d" (ISO).

    Nota: ogni trace deve avere un `name` significativo — è il testo
    che appare nella tooltip prima del valore. Es. `go.Scatter(name="TWR")`
    produce "TWR: +13.06%" nella tooltip.
    """
    fig.update_layout(
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=COLORS["bg"],
            bordercolor=COLORS["grid"],
            font=dict(
                family="Inter, sans-serif",
                size=12,
                color=COLORS["fg"],
            ),
        ),
        xaxis=dict(
            hoverformat=x_format,
        ),
    )


# --------------------------------------------------------------------------- #
# AREA SHADING — riempimento sotto la linea con colore semantico
# --------------------------------------------------------------------------- #
def add_area_shading(
    fig: go.Figure,
    x,
    y,
    split_at: float = 0.0,
    color_positive: str | None = None,
    color_negative: str | None = None,
    alpha: float = 0.08,
) -> None:
    """Aggiunge area shading positive/negative rispetto a una soglia.

    Utile per grafici TWR: area verde sotto la linea quando il rendimento
    è positivo, area rossa quando è negativo. Comunica visivamente
    "quanto tempo siamo stati in profitto vs perdita".

    Implementazione: aggiunge due trace `go.Scatter` con
    `fill='tozeroy'` mascherate rispettivamente sopra/sotto la soglia.
    Vengono aggiunte SOTTO alle trace esistenti (zorder più basso) così
    la linea principale resta in primo piano.

    Args:
        fig: figura Plotly (modificata in-place).
        x: valori asse X (date o numerici).
        y: valori asse Y (serie da cui derivare l'area).
        split_at: soglia di separazione tra area positiva e negativa.
            Default 0 (rendimento positivo/negativo). Può essere altro
            valore per soglie custom (es. benchmark = X%).
        color_positive: hex color area positiva. Default: COLORS["gain"].
        color_negative: hex color area negativa. Default: COLORS["loss"].
        alpha: opacità dell'area (0-1). Default 0.08 = molto tenue,
            per non oscurare la linea principale.

    Esempio (TWR cumulato):
        fig.add_trace(go.Scatter(x=dates, y=twr, name="TWR",
                                 line=dict(color=COLORS["value"])))
        add_area_shading(fig, dates, twr, split_at=0)
    """
    import numpy as np

    color_positive = color_positive or COLORS["gain"]
    color_negative = color_negative or COLORS["loss"]

    y_array = np.asarray(y, dtype=float)

    # Area positiva: y se > split, NaN altrimenti (Plotly non riempie NaN)
    y_pos = np.where(y_array > split_at, y_array, np.nan)
    # Area negativa: y se < split, NaN altrimenti
    y_neg = np.where(y_array < split_at, y_array, np.nan)

    # Trace area positiva (verde tenue, sotto la linea principale)
    fig.add_trace(go.Scatter(
        x=x,
        y=y_pos,
        fill="tozeroy",
        fillcolor=_hex_to_rgba(color_positive, alpha),
        line=dict(color="rgba(0,0,0,0)", width=0),   # invisibile
        hoverinfo="skip",
        showlegend=False,
        name="_area_positive",
    ))

    # Trace area negativa (rossa tenue)
    fig.add_trace(go.Scatter(
        x=x,
        y=y_neg,
        fill="tozeroy",
        fillcolor=_hex_to_rgba(color_negative, alpha),
        line=dict(color="rgba(0,0,0,0)", width=0),
        hoverinfo="skip",
        showlegend=False,
        name="_area_negative",
    ))


# --------------------------------------------------------------------------- #
# HELPERS PRIVATI
# --------------------------------------------------------------------------- #
def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Converte un colore hex (#RRGGBB) in rgba(r,g,b,alpha) per Plotly.

    Plotly accetta hex ma non hex+alpha in un solo string. Per l'area
    shading semi-trasparente serve la forma rgba().

    Args:
        hex_color: colore in formato "#RRGGBB" o "RRGGBB".
        alpha: opacità 0-1.

    Returns:
        Stringa "rgba(r, g, b, alpha)".
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"
