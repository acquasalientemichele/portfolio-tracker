"""
4_💰_Andamento.py — Andamento del valore del portafoglio nel tempo.

Mostra come è cresciuto (o decresciuto) il valore di mercato rispetto al
capitale investito cumulato. L'area shaded tra le due linee è il P&L
"a vista" giorno per giorno, scollegata da TWR e MWR (che sono percentuali).

È il "money chart" tipico delle dashboard: una sola immagine, ad alto
impatto visivo.

Mappa la sezione 7 del notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import streamlit as st

import portfolio as pf
import chart_style as cs
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Andamento", page_icon="💰", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="andamento")
cs.apply_global_style()

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
st.title("Andamento del valore")
st.caption("Valore di mercato del portafoglio vs capitale investito cumulato")

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Valore corrente", f"{last_v:,.2f} €")
with col2:
    kpi_card("Capitale investito", f"{last_i:,.2f} €")
with col3:
    kpi_card("P&L €", f"{pnl:+,.2f} €")
with col4:
    kpi_card("P&L %", f"{pnl_pct:+.2%}")

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO
# --------------------------------------------------------------------------- #
# Replica della sezione 7 del notebook. Stile FT: linee chiare, area shaded
# discreta, marker + label sui valori finali.

fig, ax = plt.subplots(figsize=(11, 5.5))
cs.style_axis(ax)

# Area gain/loss tra valore e capitale investito
ax.fill_between(
    vs.index, vs["value"], invested_cum,
    where=(vs["value"] >= invested_cum),
    color=cs.COLORS["gain"], alpha=0.13, interpolate=True, zorder=1,
)
ax.fill_between(
    vs.index, vs["value"], invested_cum,
    where=(vs["value"] < invested_cum),
    color=cs.COLORS["loss"], alpha=0.13, interpolate=True, zorder=1,
)

# Linee
ax.plot(vs.index, invested_cum,
        color=cs.COLORS["invested"], linewidth=1.4, linestyle="--",
        label="Capitale investito", zorder=2)
ax.plot(vs.index, vs["value"],
        color=cs.COLORS["value"], linewidth=2.2,
        label="Valore portafoglio", zorder=3)

# Marker e label sul valore corrente
ax.scatter([last_x], [last_v], color=cs.COLORS["value"], s=45, zorder=4,
           edgecolor="white", linewidth=1.8)
ax.annotate(
    f"  €{last_v:,.0f}", xy=(last_x, last_v),
    xytext=(6, 0), textcoords="offset points",
    va="center", ha="left", fontsize=10.5, fontweight="bold",
    color=cs.COLORS["value"],
)

# Marker e label sul capitale investito
ax.scatter([last_x], [last_i], color=cs.COLORS["invested"], s=32, zorder=4,
           edgecolor="white", linewidth=1.5)
ax.annotate(
    f"  €{last_i:,.0f}", xy=(last_x, last_i),
    xytext=(6, 0), textcoords="offset points",
    va="center", ha="left", fontsize=9.5, fontweight="medium",
    color=cs.COLORS["muted"],
)

# Margine destro extra per le label
span = vs.index[-1] - vs.index[0]
ax.set_xlim(vs.index[0], vs.index[-1] + span * 0.06)

cs.style_legend(ax)
sign = "+" if pnl >= 0 else "−"
cs.add_title(
    fig,
    title="Portfolio Performance",
    subtitle=f"€{last_v:,.0f}   ·   {sign}€{abs(pnl):,.0f} "
             f"({pnl_pct:+.1%}) dall'inizio",
    source=f"Fonte: yfinance (EOD)  ·  Aggiornato {vs.index[-1].date()}",
)

st.pyplot(fig, use_container_width=True)

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Come leggere il grafico"):
    st.markdown(
        """
        - **Linea blu** (continua): valore di mercato del portafoglio, giorno per giorno.
        - **Linea grigia** (tratteggiata): capitale investito cumulato, cioè
          quanto hai effettivamente versato fino a quel momento. Sale a scalini
          ad ogni nuovo acquisto, è piatta tra un acquisto e l'altro.
        - **Area verde**: il valore di mercato è sopra il capitale investito
          → il portafoglio è in guadagno "a vista".
        - **Area rossa**: il valore di mercato è sotto il capitale investito
          → il portafoglio è in perdita "a vista".

        Questo grafico mostra il **P&L in valore assoluto**, non il rendimento
        percentuale. Per le metriche di performance percentuali vedi la pagina
        **Performance** (TWR e MWR).

        Il valore di mercato è **al lordo** di bollo e imposta sulle plusvalenze:
        per il riepilogo netto vedi la pagina **Costi e fiscalità**.
        """
    )
