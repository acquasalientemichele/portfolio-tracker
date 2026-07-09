"""
2_📈_Performance.py — Performance complessiva del portafoglio.

Mostra TWR (rendimento dello strumento, timing-neutral) e MWR/IRR
(rendimento effettivo, dipendente dal timing dei versamenti), con
interpretazione automatica dello spread.

Mappa la sezione 5 del notebook: stessa logica, presentazione web.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import portfolio as pf
import plotly_style as ps
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Performance", page_icon="📈", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="performance")

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
vs = pf.portfolio_value_series(tx, prices)
twr_cum = pf.time_weighted_return(vs)

# Per il MWR serve il valore corrente del portafoglio
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)
current_value = float(holdings_valued["market_value"].sum())

mwr = pf.money_weighted_return(tx, current_value=current_value)
compare = pf.compare_twr_mwr(twr_cum, mwr)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Performance")
st.caption("Time-Weighted Return (GIPS-compliant) e Money-Weighted Return (IRR)")

# --------------------------------------------------------------------------- #
# METRICHE DI SINTESI
# --------------------------------------------------------------------------- #
twr_cum_pct = compare["twr_cumulative"]
twr_ann = compare["twr_annualized"]
mwr_ann = compare["mwr_annualized"]
spread = compare["spread_annualized"]
days = compare["days"]
short = compare["is_short_period"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("TWR cumulato", f"{twr_cum_pct:+.2%}")
with col2:
    kpi_card(
        "TWR annualizzato",
        f"{twr_ann:+.2%}" if twr_ann is not None else "—",
        help="Rendimento annuo composto equivalente del TWR. "
             "Su periodi < 1 anno tende a sovrastimare la performance attesa.",
    )
with col3:
    kpi_card(
        "MWR (IRR) annualizzato",
        f"{mwr_ann:+.2%}" if mwr_ann is not None else "—",
        help="Tasso di rendimento interno dei flussi di cassa. "
             "Risente del timing dei versamenti.",
    )
with col4:
    kpi_card(
        "Spread MWR − TWR",
        f"{spread:+.2%}" if spread is not None else "—",
        help="Misura quanto il timing ha aiutato (>0) o penalizzato (<0).",
    )

if short and days is not None:
    callout(
        f"Periodo di storia: <strong>{days} giorni</strong> (< 1 anno). "
        f"I valori annualizzati vanno letti con prudenza.",
        kind="warning",
    )

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO TWR CUMULATO (Plotly interattivo)
# --------------------------------------------------------------------------- #
st.subheader("TWR cumulato")

# Trasformo il cumulato (1.0 → 1.08) in rendimento frazione (0 → 0.08).
# Plotly con y_format="percent" moltiplica × 100 per la visualizzazione.
ret = twr_cum - 1.0

fig = go.Figure()

# Linea principale TWR
fig.add_trace(go.Scatter(
    x=twr_cum.index,
    y=ret.values,
    name="TWR cumulato",
    line=dict(color=ps.COLORS["value"], width=2.0),
    mode="lines",
    hovertemplate="<b>%{y:+.2%}</b><extra></extra>",
))

# Area shading: navy tenue quando ret > 0, rosso tenue quando ret < 0.
# color_positive="value" (navy) invece del default gain (verde) per
# fedeltà al design matplotlib originale.
ps.add_area_shading(
    fig, twr_cum.index, ret.values,
    split_at=0,
    color_positive=ps.COLORS["value"],
    color_negative=ps.COLORS["loss"],
    alpha=0.10,
)

# Linea orizzontale a 0 (riferimento visivo)
fig.add_hline(
    y=0,
    line=dict(color=ps.COLORS["muted"], width=0.8, dash="dash"),
    opacity=0.5,
)

# Marker cerchietto sul valore finale (visual anchor per l'annotation)
last_x = twr_cum.index[-1]
last_y = float(ret.iloc[-1])
fig.add_trace(go.Scatter(
    x=[last_x], y=[last_y],
    mode="markers",
    marker=dict(color=ps.COLORS["value"], size=8),
    showlegend=False,
    hoverinfo="skip",
))

# Assi + hover unificato + endline annotation
ps.style_axes(fig, y_format="percent", x_is_date=True)
ps.hover_unified(fig)
ps.add_endline_annotations(fig, [
    {"y": last_y, "text": f"{last_y:+.2%}", "color": ps.COLORS["value"]},
])
ps.apply_layout(
    fig,
    title="Time-Weighted Return",
    subtitle="Rendimento cumulato lordo degli strumenti, "
             "indipendente dal timing dei versamenti",
    source="Fonte: Yahoo Finance · elaborazione portfolio.py",
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE
# --------------------------------------------------------------------------- #
st.subheader("Interpretazione")

# `compare_twr_mwr` ha già generato il testo interpretativo, compreso il
# caveat sull'annualizzazione su periodi brevi. Il kind del callout è
# ricavato dal segno dello spread: neutrale se piccolo, success se positivo
# (timing favorevole), warning se negativo (timing sfavorevole).
if spread is None or abs(spread) < 0.005:
    kind = "info"
elif spread > 0:
    kind = "success"
else:
    kind = "warning"
callout(compare["interpretation"], kind=kind)

with st.expander("ℹ️ Differenza TWR vs MWR — promemoria"):
    st.markdown(
        """
        - **TWR** (Time-Weighted Return) misura il rendimento *dello strumento*:
          neutralizza i versamenti, quindi due investitori con strategie diverse
          ma stessi ETF hanno lo stesso TWR. È la metrica **GIPS-compliant**
          per confrontare gestori e strategie.
        - **MWR** (Money-Weighted Return, IRR) misura il rendimento *effettivo
          del tuo portafoglio*: considera quando hai versato e quanto. Due
          investitori con gli stessi ETF possono avere MWR molto diversi.
        - **Spread MWR − TWR > 0**: hai mediamente versato di più nei periodi
          di mercato basso (timing favorevole).
        - **Spread MWR − TWR < 0**: hai mediamente versato di più nei periodi
          di mercato alto (timing sfavorevole).
        """
    )

st.divider()

# --------------------------------------------------------------------------- #
# DETTAGLIO CASH FLOW
# --------------------------------------------------------------------------- #
st.subheader("Cash flow")

cf = tx[tx["operation"].isin(["BUY", "SELL"])].copy()
cf["importo"] = cf.apply(
    lambda r: -(r["quantity"] * r["price"] + r["fees"])
              if r["operation"] == "BUY"
              else +(r["quantity"] * r["price"] - r["fees"]),
    axis=1,
)
cf = cf.sort_values("date").reset_index(drop=True)
cf["cumulato_investito"] = (-cf["importo"]).cumsum()

# Metriche aggregate sul cash flow
tot_invested_net = float((-cf["importo"]).sum())
n_buy = int((cf["operation"] == "BUY").sum())
n_sell = int((cf["operation"] == "SELL").sum())

ccol1, ccol2, ccol3 = st.columns(3)
with ccol1:
    kpi_card("Capitale investito netto", f"{tot_invested_net:,.2f} €")
with ccol2:
    kpi_card("N° acquisti", f"{n_buy}")
with ccol3:
    kpi_card("N° vendite", f"{n_sell}")

# Tabella operazioni
view = cf[["date", "operation", "ticker", "quantity", "price",
           "fees", "importo", "cumulato_investito"]].copy()
view = view.rename(columns={
    "date": "Data",
    "operation": "Operazione",
    "ticker": "Ticker",
    "quantity": "Quantità",
    "price": "Prezzo",
    "fees": "Fees",
    "importo": "Importo netto",
    "cumulato_investito": "Cumulato investito",
})

st.dataframe(
    view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Data":               st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Quantità":           st.column_config.NumberColumn(format="%.4f"),
        "Prezzo":             st.column_config.NumberColumn(format="%.2f €"),
        "Fees":               st.column_config.NumberColumn(format="%.2f €"),
        "Importo netto":      st.column_config.NumberColumn(format="%+.2f €"),
        "Cumulato investito": st.column_config.NumberColumn(format="%.2f €"),
    },
)

st.caption(
    "**Importo netto**: cash flow dal punto di vista dell'investitore "
    "(negativo per BUY = soldi che escono, positivo per SELL). "
    "**Cumulato investito** = somma degli outflow netti fino a oggi."
)
