"""
7_Ribilanciamento.py — Suggerimento di ribilanciamento PAC.

Prima pagina interattiva dell'app: l'utente inserisce l'importo del prossimo
versamento e ottiene la proposta di allocazione + la proiezione di convergenza
al target.

Strategia: cash-flow rebalancing only (no vendita), single-buy preferito,
threshold 2% configurabile. Vedi DESIGN_DECISIONS.md per le motivazioni.

Mappa la sezione 10 del notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.ticker import FuncFormatter

import portfolio as pf
import chart_style as cs
from rebalance import (
    suggest_rebalance, project_convergence,
    DEFAULT_THRESHOLD, DEFAULT_FEE_PER_ORDER,
    PROJECTION_TARGET_BAND,
)
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Rebalancing", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="ribilanciamento")
cs.apply_global_style()

# --------------------------------------------------------------------------- #
# CALCOLI DI BASE
# --------------------------------------------------------------------------- #
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)
target = settings.get("target_allocation", {})

# Prezzi correnti: ultima riga del df prezzi → Series ticker → last_price
prices_now = prices.iloc[-1]

# --------------------------------------------------------------------------- #
# HEADER + GUARD
# --------------------------------------------------------------------------- #
st.title("Rebalancing")
st.caption(
    "Actionable suggestion for your next contribution and a projection of "
    "convergence to target."
)

if not target:
    callout(
        "<strong>Target allocation not configured.</strong> "
        "Add the target weights in the <strong>settings</strong> sheet of the "
        "Excel file (format: <strong>ticker | target_weight</strong>, sum = 1.0).",
        kind="danger",
    )
    st.stop()

# --------------------------------------------------------------------------- #
# STATO ATTUALE (sintetico, riprende Allocazione)
# --------------------------------------------------------------------------- #
all_tickers = sorted(set(holdings_valued.index) | set(target.keys()))
deviations = {
    t: (float(holdings_valued.loc[t, "weight"]) if t in holdings_valued.index else 0.0)
       - target.get(t, 0.0)
    for t in all_tickers
}
max_dev_now = max(abs(d) for d in deviations.values()) if deviations else 0.0
n_off = sum(1 for d in deviations.values() if abs(d) > DEFAULT_THRESHOLD)
total_value = float(holdings_valued["market_value"].sum())

scol1, scol2, scol3 = st.columns(3)
with scol1:
    kpi_card("Portfolio value", f"{total_value:,.2f} €")
with scol2:
    kpi_card(
        "Current max deviation",
        f"{max_dev_now:.2%}",
        delta=f"threshold {DEFAULT_THRESHOLD:.0%}",
        delta_kind="negative" if max_dev_now > DEFAULT_THRESHOLD else "positive",
    )
with scol3:
     kpi_card("Tickers off threshold", f"{n_off}/{len(all_tickers)}")

st.divider()

# --------------------------------------------------------------------------- #
# INPUT INTERATTIVO
# --------------------------------------------------------------------------- #
st.subheader("Contribution parameters")

icol1, icol2 = st.columns([3, 1])
with icol1:
    new_cash = st.number_input(
        "Net amount to invest (€)",
        min_value=10.0,
        value=500.0,
        step=50.0,
        format="%.2f",
        help="Amount actually invested in ETFs. Fees are additional and paid "
             "on top of this figure.",
    )

with icol2:
    # Spacer per allineare il bottone popover all'altezza del campo input
    # a sinistra (compensa l'altezza della label del number_input, ~28px).
    st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    with st.popover("Advanced parameters", use_container_width=True):
        threshold = st.slider(
            "Tolerance threshold (%)",
            min_value=0.5, max_value=5.0,
            value=DEFAULT_THRESHOLD * 100, step=0.5,
            help="Below this threshold, splitting across 2 ETFs isn't worth it.",
        ) / 100
        fee_per_order = st.number_input(
            "Fee per order (€)",
            min_value=0.0, value=DEFAULT_FEE_PER_ORDER, step=0.5,
            format="%.2f",
        )

# --------------------------------------------------------------------------- #
# CALCOLO SUGGERIMENTO
# --------------------------------------------------------------------------- #
rec = suggest_rebalance(
    holdings_valued, target, new_cash, prices_now,
    threshold=threshold, fee_per_order=fee_per_order,
)

# --------------------------------------------------------------------------- #
# OUTPUT SUGGERIMENTO
# --------------------------------------------------------------------------- #
st.subheader(f"Suggestion for a {new_cash:,.2f} € contribution")

# Caso edge: cash insufficiente
if rec["summary"]["n_orders"] == 0:
    callout(rec['message'], kind="danger")
else:
    # Kind dinamico: success se 1 ordine (situazione ottimale, single-buy),
    # info se 2+ ordini (split necessario, comportamento nominale).
    kind = "success" if rec["summary"]["n_orders"] == 1 else "info"
    callout(rec['message'], kind=kind)

    # 4 metriche di sintesi
    s = rec["summary"]
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    with mcol1:
        kpi_card("Cash invested", f"{s['cash_invested']:,.2f} €")
    with mcol2:
        kpi_card(
            "Fees",
            f"{s['fees_total']:,.2f} €",
            delta=f"{s['n_orders']} order(s)",
            delta_kind="neutral",
        )
    with mcol3:
        kpi_card("Total cash out", f"{s['cash_input']:,.2f} €")
    with mcol4:
        # Deviazione minore è meglio: se scende → positive, se sale → negative
        dev_delta = s['max_deviation_post'] - max_dev_now
        kpi_card(
            "Max deviation after",
            f"{s['max_deviation_post']:.2%}",
            delta=f"{dev_delta*100:+.2f}pp vs current",
            delta_kind="positive" if dev_delta < 0 else "negative",
        )

    # Tabella ordini
    st.markdown("##### Orders to place")

    orders = rec["orders"].copy()
    # Aggiungo il nome dell'ETF per leggibilità
    orders["name"] = orders["ticker"].map(
        lambda t: holdings_valued.loc[t, "name"]
                  if t in holdings_valued.index else t
    )
    # Trasformo le percentuali da frazione a numero per il display
    orders["weight_post"] = orders["weight_post"] * 100
    orders["deviation_post"] = orders["deviation_post"] * 100

    view = orders[[
        "ticker", "name", "quantity", "price", "cash_invested",
        "fees", "weight_post", "deviation_post"
    ]].rename(columns={
        "ticker": "Ticker",
        "name": "Name",
        "quantity": "Quantity",
        "price": "Price",
        "cash_invested": "Cash invested",
        "fees": "Fee",
        "weight_post": "Weight after",
        "deviation_post": "Dev. after (pp)",
    })

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Quantity":       st.column_config.NumberColumn(format="%.4f"),
            "Price":          st.column_config.NumberColumn(format="%.2f €"),
            "Cash invested":  st.column_config.NumberColumn(format="%.2f €"),
            "Fee":            st.column_config.NumberColumn(format="%.2f €"),
            "Weight after":   st.column_config.NumberColumn(format="%.2f%%"),
            "Dev. after (pp)": st.column_config.NumberColumn(format="%+.2f"),
        },
    )

st.divider()

# --------------------------------------------------------------------------- #
# PROIEZIONE CONVERGENZA
# --------------------------------------------------------------------------- #
st.subheader("Projection: how many months back to target?")
st.caption(
    f"Simulation with a monthly {new_cash:,.0f} € contribution, repeated until "
    f"max deviation < {PROJECTION_TARGET_BAND:.1%}. "
    f"Assumption: constant prices (a simplification)."
)

proj = project_convergence(
    holdings_valued, target, new_cash, prices_now,
    threshold=threshold, fee_per_order=fee_per_order,
)

history = proj["history"]
converged = proj["converged"]
months_to_target = proj["months_to_target"]

# Metric + interpretazione
pcol1, pcol2 = st.columns([1, 3])
with pcol1:
    if converged and months_to_target == 0:
        kpi_card(
            "Already on target",
            "✅",
            help=f"Max deviation is already below {PROJECTION_TARGET_BAND:.1%}.",
        )
    elif converged:
        kpi_card(
            "Months to convergence",
            f"{months_to_target}",
            delta=f"band ±{PROJECTION_TARGET_BAND:.1%}",
            delta_kind="neutral",
        )
    else:
        final_dev = proj.get("final_max_dev", max_dev_now)
        kpi_card(
            "No convergence in 60 months",
            "—",
            delta=f"final dev: {final_dev:.2%}",
            delta_kind="negative",
        )

with pcol2:
    if converged and months_to_target == 0:
        callout(
            f"The portfolio is already within the "
            f"{PROJECTION_TARGET_BAND:.1%} band around target. No corrective "
            f"action needed.",
            kind="success",
        )
    elif converged:
        callout(
            f"Continuing with a monthly <strong>{new_cash:,.0f} €</strong> "
            f"contribution, the portfolio returns within the "
            f"<strong>{PROJECTION_TARGET_BAND:.1%}</strong> band around target in "
            f"about <strong>{months_to_target} months</strong>. No selling needed — "
            f"self-correction happens through contributions.",
            kind="info",
        )
    else:
        callout(
            f"With a {new_cash:,.0f} € contribution, the portfolio doesn't return "
            f"within the {PROJECTION_TARGET_BAND:.1%} band over the next "
            f"60 months (final deviation: {proj.get('final_max_dev', 0):.2%}). "
            f"Consider a larger contribution or a partial sale (with the 26% "
            f"tax drag on gains).",
            kind="warning",
        )

# Grafico convergenza: max deviation nel tempo
fig, ax = plt.subplots(figsize=(11, 4.5))

months_axis = history["month"]
max_devs_pct = history["max_dev"] * 100
target_band_pct = PROJECTION_TARGET_BAND * 100
threshold_pct = threshold * 100

# Linea principale: max deviation
ax.plot(months_axis, max_devs_pct, color=cs.COLORS["value"],
        linewidth=2.0, marker="o", markersize=4,
        markerfacecolor=cs.COLORS["value"], markeredgecolor="white",
        markeredgewidth=1.0, label="Max deviation")

# Area shaded: zona target (< target_band)
ax.axhspan(0, target_band_pct, color=cs.COLORS["gain"], alpha=0.10,
           zorder=0, label=f"Target band (< {target_band_pct:.1f}%)")

# Linea threshold (più alta)
ax.axhline(threshold_pct, color=cs.COLORS["muted"], linewidth=0.8,
           linestyle="--", alpha=0.6, label=f"Threshold {threshold_pct:.1f}%")

# Marker sul punto di convergenza
if converged and months_to_target is not None and months_to_target > 0:
    convergence_y = history.loc[history["month"] == months_to_target,
                                 "max_dev"].iloc[0] * 100
    ax.scatter([months_to_target], [convergence_y],
               color=cs.COLORS["gain"], s=120, zorder=5,
               edgecolor="white", linewidth=2.0,
               label=f"Convergence at month {months_to_target}")

cs.style_axis(ax, euro=False, date_axis=False)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}%"))
ax.set_xlabel("Month", fontsize=10, color=cs.COLORS["fg"])
ax.set_ylim(bottom=0)

cs.style_legend(ax, loc="upper right")
cs.add_title(
    fig,
    title="Convergence to target",
    subtitle=f"Portfolio max deviation over time · "
             f"monthly {new_cash:,.0f} € contribution · constant prices",
    source=None,
)
st.pyplot(fig, use_container_width=True)

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("Rebalancing logic"):
    st.markdown(
        f"""
        **Single-buy gap-closing strategy**:
        1. Compute the total post-investment value and the "ideal" allocation
           (target weight × post value)
        2. Identify the most underweight ticker (largest gap between ideal and current)
        3. **Try a single buy**, putting all the cash on that primary ticker
        4. If the post-buy deviation is **below the {threshold:.1%} threshold**,
           stop here (1 order, 1 fee)
        5. Otherwise **split across two tickers** in proportion to the gaps (2 orders, 2 fees)

        **Why single-buy is preferred**:
        - A TR fee of {fee_per_order:.2f} € on a {new_cash:,.0f} € contribution
          is a {fee_per_order/new_cash:.2%} drag (more than the 0.2% annual stamp duty)
        - If a single order closes the deviation, splitting is wasteful
        - The following month naturally corrects any residual drift

        **Why no selling**:
        - For Italian harmonised ETFs, selling realises gains taxed at 26%
        - The tax drag makes "sell-high / buy-low" sub-optimal for retail investors
        - Recurring contributions naturally provide the flows to self-correct drift

        **Projection caveats**:
        - It assumes **constant prices** and **zero returns**: a simplification
        - In reality prices move and affect self-correction (sometimes helping,
          sometimes hindering)
        - For a projection faithful to real dynamics → the **Monte Carlo** page
        """
    )
