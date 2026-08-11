"""
4_Andamento.py — Andamento del valore del portafoglio nel tempo.

Mostra come è cresciuto (o decresciuto) il valore di mercato rispetto al
capitale investito cumulato. L'area shaded tra le due linee è il P&L
"a vista" giorno per giorno, scollegata da TWR e MWR (che sono percentuali).

È il "money chart" tipico delle dashboard: una sola immagine, ad alto
impatto visivo.

Mappa la sezione 7 del notebook.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import portfolio as pf
import plotly_style as ps
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Value over time", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="andamento")

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
vs = pf.portfolio_value_series(tx, prices)
invested_cum = vs["flow"].cumsum()

last_x = vs.index[-1]
last_v = float(vs["value"].iloc[-1])
last_i = float(invested_cum.iloc[-1])
pnl = last_v - last_i
pnl_pct = pnl / last_i if last_i else 0.0

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Portfolio value over time")
st.caption("Portfolio market value vs cumulative invested capital")

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Current value", f"{last_v:,.2f} €")
with col2:
    kpi_card("Invested capital", f"{last_i:,.2f} €")
with col3:
    kpi_card("P&L €", f"{pnl:+,.2f} €")
with col4:
    kpi_card("P&L %", f"{pnl_pct:+.2%}")

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO (Plotly interattivo)
# --------------------------------------------------------------------------- #

value = vs["value"].values
invested = invested_cum.values

# Area shading tra due serie con colore condizionale.
# Tecnica: 2 trace mascherate riempite verso una baseline invisibile:
# - value_upper = max(value, invested) → area verde solo dove value > invested
# - value_lower = min(value, invested) → area rossa solo dove value < invested
value_upper = np.maximum(value, invested)
value_lower = np.minimum(value, invested)

fig = go.Figure()

# Baseline invisibile = capitale investito (necessaria come riferimento per il fill)
fig.add_trace(go.Scatter(
    x=vs.index, y=invested,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    showlegend=False,
    hoverinfo="skip",
    name="_baseline",
))

# Area verde: sopra la baseline dove value > invested
fig.add_trace(go.Scatter(
    x=vs.index, y=value_upper,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["gain"], 0.13),
    showlegend=False,
    hoverinfo="skip",
    name="_area_gain",
))

# Baseline invisibile (di nuovo, serve tra un fill e l'altro per l'area rossa)
fig.add_trace(go.Scatter(
    x=vs.index, y=invested,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    showlegend=False,
    hoverinfo="skip",
    name="_baseline2",
))

# Area rossa: sotto la baseline dove value < invested
fig.add_trace(go.Scatter(
    x=vs.index, y=value_lower,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["loss"], 0.13),
    showlegend=False,
    hoverinfo="skip",
    name="_area_loss",
))

# Linea capitale investito (tratteggiata, grigia)
fig.add_trace(go.Scatter(
    x=vs.index, y=invested,
    name="Invested capital",
    mode="lines",
    line=dict(color=ps.COLORS["invested"], width=1.4, dash="dash"),
    hovertemplate="<b>€%{y:,.0f}</b><extra>Invested capital</extra>",
))

# Linea valore portafoglio (principale, navy)
fig.add_trace(go.Scatter(
    x=vs.index, y=value,
    name="Portfolio value",
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=2.2),
    hovertemplate="<b>€%{y:,.0f}</b><extra>Portfolio value</extra>",
))

# Marker sul valore finale (grande, navy)
fig.add_trace(go.Scatter(
    x=[last_x], y=[last_v],
    mode="markers",
    marker=dict(color=ps.COLORS["value"], size=10,
                line=dict(color="white", width=1.8)),
    showlegend=False,
    hoverinfo="skip",
))

# Marker sul capitale investito finale (più piccolo, grigio)
fig.add_trace(go.Scatter(
    x=[last_x], y=[last_i],
    mode="markers",
    marker=dict(color=ps.COLORS["invested"], size=7,
                line=dict(color="white", width=1.5)),
    showlegend=False,
    hoverinfo="skip",
))

# Assi + hover unificato
ps.style_axes(fig, y_format="euro", x_is_date=True)
ps.hover_unified(fig)

tick_annotations = [
    dict(
        text=f"<b>€{last_v:,.0f}</b>",
        xref="paper", yref="y",
        x=-0.01,   # subito fuori dal plot area a sinistra
        y=last_v,
        xanchor="right",
        yanchor="middle",
        showarrow=False,
        font=dict(size=12, color=ps.COLORS["value"], family="Inter, sans-serif"),
    ),
    dict(
        text=f"<b>€{last_i:,.0f}</b>",
        xref="paper", yref="y",
        x=-0.01,
        y=last_i,
        xanchor="right",
        yanchor="middle",
        showarrow=False,
        font=dict(size=12, color=ps.COLORS["muted"], family="Inter, sans-serif"),
    ),
]
existing = list(fig.layout.annotations)
fig.update_layout(annotations=existing + tick_annotations)

# Sottotitolo dinamico con valore attuale + P&L
sign = "+" if pnl >= 0 else "−"
ps.apply_layout(
    fig,
    title="Portfolio value",
    subtitle=f"€{last_v:,.0f}   ·   {sign}€{abs(pnl):,.0f} "
             f"({pnl_pct:+.1%}) since inception",
    source=f"Source: yfinance (EOD)  ·  Updated {vs.index[-1].date()}",
    height=500,   # leggermente più alto del default per aspect ratio simile a matplotlib originale
)

# Aumento margin sinistro per accomodare le etichette più larghe (€6,505)
fig.update_layout(margin=dict(l=90, r=80, t=80, b=90))

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("How to read this chart"):
    st.markdown(
        """
        - **Blue line** (solid): the portfolio's market value, day by day.
        - **Grey line** (dashed): cumulative invested capital — how much you've
          actually paid in up to that point. It steps up at each new purchase
          and stays flat in between.
        - **Green area**: market value is above invested capital
          → the portfolio is in unrealised gain.
        - **Red area**: market value is below invested capital
          → the portfolio is in unrealised loss.

        This chart shows **P&L in absolute value**, not percentage return.
        For percentage performance metrics see the **Performance** page
        (TWR and MWR).

        Market value is **gross** of stamp duty and capital-gains tax; for the
        net figure see the **Costs & tax** page.
        """
    )
