"""
2_📈_Performance.py — Performance complessiva del portafoglio.

Mostra TWR (rendimento dello strumento, timing-neutral) e MWR/IRR
(rendimento effettivo, dipendente dal timing dei versamenti), con
interpretazione automatica dello spread.

Mappa la sezione 5 del notebook: stessa logica, presentazione web.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import streamlit as st
from matplotlib.ticker import FuncFormatter

import portfolio as pf
import chart_style as cs
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Performance", page_icon="📈", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="performance")

# Applichiamo lo stile globale matplotlib una volta per pagina (rcParams)
cs.apply_global_style()

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
# GRAFICO TWR CUMULATO
# --------------------------------------------------------------------------- #
st.subheader("TWR cumulato")

fig, ax = plt.subplots(figsize=(12, 4.5))

# Trasformo il cumulato (1.0 → 1.08) in rendimento % (0 → 8)
ret_pct = (twr_cum - 1.0) * 100

# Linea principale + area shaded per profondità visiva
ax.plot(twr_cum.index, ret_pct, color=cs.COLORS["value"],
        linewidth=2.0, label="TWR cumulato")
ax.fill_between(twr_cum.index, 0, ret_pct,
                where=(ret_pct >= 0), color=cs.COLORS["value"],
                alpha=0.10, interpolate=True)
ax.fill_between(twr_cum.index, 0, ret_pct,
                where=(ret_pct < 0), color=cs.COLORS["loss"],
                alpha=0.10, interpolate=True)
ax.axhline(0, color=cs.COLORS["muted"], linewidth=0.8,
           linestyle="--", alpha=0.5)

# Annotazione sull'ultimo valore: aggancia un'etichetta numerica al cursore
last_x = twr_cum.index[-1]
last_y = float(ret_pct.iloc[-1])
ax.annotate(
    f"{last_y:+.2f}%",
    xy=(last_x, last_y),
    xytext=(8, 0), textcoords="offset points",
    color=cs.COLORS["value"], fontweight="bold", va="center", fontsize=10,
)

cs.style_axis(ax, euro=False, date_axis=True)
# Formatto l'asse Y in percentuali (non in euro)
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.1f}%"))
ax.set_ylabel("")  # ridondante con il formatter

cs.add_title(
    fig,
    "Time-Weighted Return",
    subtitle="Rendimento cumulato lordo degli strumenti, "
             "indipendente dal timing dei versamenti",
    source="Fonte: Yahoo Finance · elaborazione portfolio.py",
)

st.pyplot(fig, use_container_width=True)

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
