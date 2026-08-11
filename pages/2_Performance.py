"""
2_Performance.py — Performance complessiva del portafoglio.

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
st.set_page_config(page_title="Performance", layout="wide")

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
st.caption("Time-Weighted Return and Money-Weighted Return (IRR)")

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
    kpi_card("Cumulative TWR", f"{twr_cum_pct:+.2%}")
with col2:
    kpi_card(
        "Annualised TWR",
        f"{twr_ann:+.2%}" if twr_ann is not None else "—",
        help="Equivalent compound annual TWR. Over periods shorter than a "
             "year it tends to overstate expected performance.",
    )
with col3:
    kpi_card(
        "Annualised MWR (IRR)",
        f"{mwr_ann:+.2%}" if mwr_ann is not None else "—",
        help="Internal rate of return of the cash flows. Sensitive to the "
             "timing of contributions.",
    )
with col4:
    kpi_card(
        "Spread MWR − TWR",
        f"{spread:+.2%}" if spread is not None else "—",
        help="How much timing helped (>0) or hurt (<0).",
    )

if short and days is not None:
    callout(
        f"History window: <strong>{days} days</strong> (< 1 year). "
        f"Read the annualised figures with caution.",
        kind="warning",
    )

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO TWR CUMULATO (Plotly interattivo)
# --------------------------------------------------------------------------- #
st.subheader("Cumulative TWR")

# Plotly con y_format="percent" moltiplica × 100 per la visualizzazione.
ret = twr_cum - 1.0

fig = go.Figure()

# Linea principale TWR
fig.add_trace(go.Scatter(
    x=twr_cum.index,
    y=ret.values,
    name="Cumulative TWR",
    line=dict(color=ps.COLORS["value"], width=2.0),
    mode="lines",
    hovertemplate="<b>%{y:+.2%}</b><extra></extra>",
))

# Area shading: navy tenue quando ret > 0, rosso tenue quando ret < 0.
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
    ssubtitle="Cumulative gross return of the instruments, "
             "independent of contribution timing",
    source="Source: Yahoo Finance · computed with portfolio.py",
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE
# --------------------------------------------------------------------------- #
st.subheader("Interpretation")

if spread is None or abs(spread) < 0.005:
    kind = "info"
elif spread > 0:
    kind = "success"
else:
    kind = "warning"
callout(compare["interpretation"], kind=kind)

with st.expander("TWR vs MWR — a quick reminder"):
    st.markdown(
        """
        - **TWR** (Time-Weighted Return) measures the return *of the instruments*:
          it neutralises contributions, so two investors with different strategies
          but the same ETFs get the same TWR. It's the **GIPS-compliant** metric
          for comparing managers and strategies.
        - **MWR** (Money-Weighted Return, IRR) measures the *actual return of your
          portfolio*: it accounts for when and how much you contributed. Two
          investors holding the same ETFs can have very different MWRs.
        - **Spread MWR − TWR > 0**: on average you contributed more when the
          market was low (favourable timing).
        - **Spread MWR − TWR < 0**: on average you contributed more when the
          market was high (unfavourable timing).
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
    kpi_card("Net invested capital", f"{tot_invested_net:,.2f} €")
with ccol2:
    kpi_card("Buys", f"{n_buy}")
with ccol3:
    kpi_card("Sells", f"{n_sell}")

# Tabella operazioni
view = cf[["date", "operation", "ticker", "quantity", "price",
           "fees", "importo", "cumulato_investito"]].copy()
view = view.rename(columns={
    "date": "Date",
    "operation": "Operation",
    "ticker": "Ticker",
    "quantity": "Quantity",
    "price": "Price",
    "fees": "Fees",
    "importo": "Net amount",
    "cumulato_investito": "Cumulative invested",
})

st.dataframe(
    view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Date":                st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Quantity":            st.column_config.NumberColumn(format="%.4f"),
        "Price":               st.column_config.NumberColumn(format="%.2f €"),
        "Fees":                st.column_config.NumberColumn(format="%.2f €"),
        "Net amount":          st.column_config.NumberColumn(format="%+.2f €"),
        "Cumulative invested": st.column_config.NumberColumn(format="%.2f €"),
    },
)

st.caption(
    "**Net amount**: cash flow from the investor's perspective "
    "(negative for BUY = money out, positive for SELL). "
    "**Cumulative invested** = sum of net outflows to date."
)
