"""
diversification_charts.py — grafici per la pagina di diversificazione.

Divisione dei compiti:
  - grafici categoriali (settori, regioni, matrice di overlap) in matplotlib,
    nello stile della dashboard (chart_style.COLORS / style_axis / add_title);
  - mappa geografica in plotly, perche' l'interattivita' (hover con paese e
    peso) e' il punto della mappa, e in Streamlit si integra nativamente.

Convenzione: le funzioni ricevono distribuzioni in FRAZIONE (somma 1), come le
produce diversification.py, e le mostrano in percentuale. Etichette in inglese
(UI del modulo in inglese, come da specifica).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from chart_style import COLORS, PALETTE, add_title, style_axis

SOURCE_NOTE = "Source: iShares / Vanguard fund holdings · look-through analysis"


# --------------------------------------------------------------------------- #
# Barre orizzontali per una distribuzione (settori, regioni, paesi)
# --------------------------------------------------------------------------- #
def plot_distribution_bar(
    dist: pd.Series,
    title: str,
    subtitle: str | None = None,
    *,
    color: str | None = None,
    top_n: int | None = None,
    figsize: tuple[float, float] = (9, 5),
):
    """Barre orizzontali di una distribuzione (frazioni), ordinate per peso.

    top_n: se valorizzato, tiene le prime n categorie e aggrega il resto in
    'Other' — utile per la dimensione paese, che puo' avere molte voci.
    """
    d = dist.sort_values(ascending=False)
    if top_n is not None and len(d) > top_n:
        testa = d.iloc[:top_n]
        altro = d.iloc[top_n:].sum()
        d = pd.concat([testa, pd.Series({"Other": altro})])

    d = d.sort_values(ascending=True)  # barh: dal basso verso l'alto
    color = color or COLORS["value"]

    fig, ax = plt.subplots(figsize=figsize)
    ax.barh(d.index, d.values * 100, color=color, height=0.72)

    # etichette percentuali a fine barra
    for y, v in enumerate(d.values):
        ax.text(v * 100 + 0.4, y, f"{v * 100:.1f}%", va="center",
                fontsize=9, color=COLORS["muted"])

    style_axis(ax, euro=False, date_axis=False)
    # per le barre orizzontali la griglia utile e' sulla x, non sulla y
    ax.grid(False, axis="y")
    ax.grid(True, axis="x", color=COLORS["grid"], linewidth=0.6)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlim(0, min(100, d.values.max() * 100 * 1.18))
    ax.tick_params(labelsize=9.5)

    add_title(fig, title, subtitle, source=SOURCE_NOTE)
    # le etichette di categoria (es. "Information Technology") stanno a sinistra:
    # servono piu' margine di quello che imposta add_title per le serie storiche.
    plt.subplots_adjust(top=0.84, bottom=0.11, left=0.24, right=0.94)
    return fig


# --------------------------------------------------------------------------- #
# Heatmap della matrice di overlap tra fondi
# --------------------------------------------------------------------------- #
def plot_overlap_heatmap(
    matrix: pd.DataFrame,
    title: str = "Fund overlap",
    subtitle: str | None = None,
    figsize: tuple[float, float] = (6.5, 5.5),
):
    """Heatmap della matrice di overlap (valori 0-1) tra fondi.

    `matrix` e' quadrata; indici/colonne sono le etichette dei fondi (es. i
    ticker). La diagonale e' 1 per costruzione.
    """
    fig, ax = plt.subplots(figsize=figsize)
    data = matrix.astype(float)

    im = ax.imshow(data.values, cmap="Blues", vmin=0, vmax=1, aspect="auto")

    ax.set_xticks(range(len(data.columns)))
    ax.set_yticks(range(len(data.index)))
    ax.set_xticklabels(data.columns, fontsize=9.5)
    ax.set_yticklabels(data.index, fontsize=9.5)

    # annota ogni cella; testo bianco sulle celle scure per leggibilita'
    for i in range(len(data.index)):
        for j in range(len(data.columns)):
            v = data.iloc[i, j]
            ax.text(j, i, f"{v * 100:.0f}%", ha="center", va="center",
                    fontsize=9.5, color="white" if v > 0.5 else COLORS["fg"])

    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=8, colors=COLORS["muted"], length=0)

    add_title(fig, title, subtitle, source=SOURCE_NOTE)
    plt.subplots_adjust(top=0.84, bottom=0.11, left=0.16, right=0.98)
    return fig


# --------------------------------------------------------------------------- #
# Mappa geografica interattiva (plotly)
# --------------------------------------------------------------------------- #
def plot_country_map(
    dist: pd.Series,
    title: str = "Geographic exposure (look-through)",
):
    """Choropleth interattiva dell'esposizione per paese (frazioni).

    Usa i nomi inglesi dei paesi (colonna `country` dello strato canonico) con
    locationmode='country names'. Voci non geografiche (es. 'European Union',
    dalle righe cash) restano fuori se si passa la distribuzione equity-only.
    """
    import plotly.express as px

    d = dist.rename("weight").reset_index()
    d.columns = ["country", "weight"]
    d["weight_pct"] = d["weight"] * 100

    # scala monocromatica coerente con la palette (chiaro -> navy).
    scala = [[0.0, "#EAF0F6"], [1.0, COLORS["value"]]]

    fig = px.choropleth(
        d,
        locations="country",
        locationmode="country names",
        color="weight_pct",
        color_continuous_scale=scala,
        hover_name="country",
        labels={"weight_pct": "Weight"},
    )
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>Weight: %{z:.1f}%<extra></extra>",
        marker_line_color="#FFFFFF",
        marker_line_width=0.4,
    )
    fig.update_layout(
        title=dict(text=title, x=0.02, font=dict(size=16, color=COLORS["fg"])),
        font=dict(family="Helvetica, Arial, sans-serif", color=COLORS["muted"]),
        geo=dict(showframe=False, showcoastlines=False, bgcolor=COLORS["bg"],
                 projection_type="natural earth"),
        coloraxis_colorbar=dict(title="%", ticksuffix="%", thickness=12, len=0.7),
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor=COLORS["bg"],
    )
    return fig
