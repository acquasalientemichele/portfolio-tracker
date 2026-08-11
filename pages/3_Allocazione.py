"""
3_Allocazione.py — Pesi correnti vs target.

Mostra:
- Allocazione corrente del portafoglio (donut chart)
- Scostamento per ticker rispetto al target (bar chart orizzontale)
- Tabella dettaglio con flag "fuori soglia"
- Alert se almeno un ticker richiede attenzione (> 2%)

Mappa la sezione 6 del notebook. Threshold default 2% (vedi DESIGN_DECISIONS).
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import portfolio as pf
import chart_style as cs
from rebalance import DEFAULT_THRESHOLD
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Allocation", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="allocazione")
cs.apply_global_style()

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)
target = settings.get("target_allocation", {})

# Universe: union dei ticker (alcuni potrebbero essere solo in holdings
# se non sono nel target, o solo in target se mai acquistati)
all_tickers = sorted(set(holdings_valued.index) | set(target.keys()))

# Costruisco il DataFrame di confronto pesi
alloc = pd.DataFrame(index=all_tickers)
alloc["name"] = [
    holdings_valued.loc[t, "name"] if t in holdings_valued.index else t
    for t in all_tickers
]
alloc["weight_current"] = [
    float(holdings_valued.loc[t, "weight"]) if t in holdings_valued.index else 0.0
    for t in all_tickers
]
alloc["weight_target"] = [target.get(t, 0.0) for t in all_tickers]
alloc["deviation"] = alloc["weight_current"] - alloc["weight_target"]
alloc["abs_deviation"] = alloc["deviation"].abs()

threshold = DEFAULT_THRESHOLD
alloc["off_threshold"] = alloc["abs_deviation"] > threshold

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Allocation")
st.caption(
    "Current weights vs target. The threshold beyond which rebalancing is "
    f"worth considering is {threshold:.0%}."
)

# Metriche di sintesi
max_dev = float(alloc["abs_deviation"].max()) if len(alloc) else 0.0
n_off = int(alloc["off_threshold"].sum())

col1, col2, col3 = st.columns(3)
with col1:
    kpi_card(
        "Max deviation",
        f"{max_dev:.2%}",
        delta=f"threshold {threshold:.0%}",
        delta_kind="negative" if max_dev > threshold else "positive",
    )
with col2:
    kpi_card("Tickers off threshold", f"{n_off}/{len(alloc)}")
with col3:
    kpi_card(
        "Threshold",
        f"{threshold:.1%}",
        help="Deviation threshold above which to consider rebalancing. "
             "Configured in rebalance.DEFAULT_THRESHOLD.",
    )

# --------------------------------------------------------------------------- #
# ALERT DINAMICO
# --------------------------------------------------------------------------- #
if n_off > 0:
    off_list = alloc[alloc["off_threshold"]].sort_values("abs_deviation", ascending=False)
    tickers_off = ", ".join(off_list.index)
    callout(
        f"<strong>{n_off} ticker(s) off threshold</strong>: {tickers_off}. "
        f"The <strong>Rebalancing</strong> page suggests how to correct the "
        f"deviation with your next contribution.",
        kind="warning",
    )
else:
    callout(
        "All tickers are within the tolerance threshold.",
        kind="success",
    )

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICI — due colonne
# --------------------------------------------------------------------------- #
gcol1, gcol2 = st.columns(2)

# -- Donut chart: allocazione corrente
with gcol1:
    st.subheader("Current allocation")

    # Mostro solo i ticker con peso > 0 (escludo target a 0 mai comprati)
    present = alloc[alloc["weight_current"] > 0].sort_values(
        "weight_current", ascending=False
    )

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = cs.PALETTE[: len(present)]
    wedges, _, autotexts = ax.pie(
        present["weight_current"],
        labels=present.index,
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct="%1.1f%%",
        pctdistance=0.78,
        wedgeprops={"width": 0.4, "edgecolor": cs.COLORS["bg"], "linewidth": 2},
        textprops={"color": cs.COLORS["fg"], "fontsize": 10},
    )
    for t in autotexts:
        t.set_color(cs.COLORS["bg"])
        t.set_fontweight("bold")
        t.set_fontsize(9)

    ax.set_aspect("equal")
    cs.add_title(
        fig,
        "Composition",
        subtitle=f"{len(present)} positions · "
                 f"{prices.index[-1]:%d/%m/%Y}",
        source=None,
    )
    st.pyplot(fig, use_container_width=True)

# -- Bar chart orizzontale: scostamenti
with gcol2:
    st.subheader("Deviation from target")

    # Ordino per scostamento per leggibilità
    bar_df = alloc.sort_values("deviation").copy()
    deviations_pp = bar_df["deviation"] * 100  # in punti percentuali

    # Colore condizionato
    def color_for(dev_pp: float) -> str:
        if abs(dev_pp) <= threshold * 100:
            return cs.COLORS["gain"]      # in soglia → verde
        if abs(dev_pp) <= threshold * 200:
            return cs.COLORS["amber"]     # 1x-2x soglia → ambra
        return cs.COLORS["loss"]          # >2x soglia → rosso

    colors_bars = [color_for(d) for d in deviations_pp]

    fig, ax = plt.subplots(figsize=(6, 5))
    y_pos = range(len(bar_df))
    ax.barh(y_pos, deviations_pp, color=colors_bars, edgecolor="none")

    # Linee soglia
    ax.axvline(0, color=cs.COLORS["muted"], linewidth=0.8)
    ax.axvline(threshold * 100, color=cs.COLORS["muted"],
               linewidth=0.6, linestyle="--", alpha=0.6)
    ax.axvline(-threshold * 100, color=cs.COLORS["muted"],
               linewidth=0.6, linestyle="--", alpha=0.6)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(bar_df.index)

    # Etichetta valore alla fine di ogni barra
    for i, (idx, val) in enumerate(deviations_pp.items()):
        offset = 0.15 if val >= 0 else -0.15
        ha = "left" if val >= 0 else "right"
        ax.text(val + offset, i, f"{val:+.2f}pp",
                va="center", ha=ha, fontsize=9, color=cs.COLORS["fg"])

    cs.style_axis(ax, euro=False, date_axis=False)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0f}pp"))
    ax.grid(False, axis="y")
    ax.grid(True, axis="x", color=cs.COLORS["grid"], linewidth=0.6)

    cs.add_title(
        fig,
        "Deviation from ticker",
        subtitle=f"dashed line = threshold ±{threshold:.0%}",
        source=None,
    )
    st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA DETTAGLIO
# --------------------------------------------------------------------------- #
st.subheader("Breakdown by ticker")

view = alloc.copy()
view["status"] = view.apply(
    lambda r: "🔴 Off threshold" if r["off_threshold"]
              else "🟢 On target",
    axis=1,
)

# Trasformo le frazioni in numeri 0-100 per il NumberColumn percent
view["weight_current"] = view["weight_current"] * 100
view["weight_target"] = view["weight_target"] * 100
view["deviation"] = view["deviation"] * 100

view = view[["name", "weight_current", "weight_target",
             "deviation", "status"]].rename(columns={
    "name": "Name",
    "weight_current": "Current weight",
    "weight_target": "Target weight",
    "deviation": "Deviation (pp)",
    "status": "Status",
})

st.dataframe(
    view,
    use_container_width=True,
    column_config={
        "Current weight": st.column_config.ProgressColumn(
                              format="%.2f%%", min_value=0, max_value=100),
        "Target weight":  st.column_config.ProgressColumn(
                              format="%.2f%%", min_value=0, max_value=100),
        "Deviation (pp)": st.column_config.NumberColumn(format="%+.2f"),
    },
)

st.caption(
    "**Deviation** = current weight − target weight, in percentage points. "
    "A ticker is off threshold when the absolute deviation exceeds "
    f"**{threshold:.0%}**."
)
