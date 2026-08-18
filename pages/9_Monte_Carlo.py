"""
9_Monte_Carlo.py — Proiezioni PAC a lungo periodo.

Simulazione Monte Carlo di N path futuri del portafoglio con:
- Calibrazione: bootstrap IID dai rendimenti storici del portafoglio target
- Simulazione: composizione mese per mese con PAC ricorrente
- Output: fan chart con percentili + tabella orizzonti + widget prob target

Ultima pagina della sequenza notebook. Mappa la sezione 12 del notebook.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import portfolio as pf
import montecarlo as mc
import plotly_style as ps

from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Monte Carlo", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="monte_carlo")

# --------------------------------------------------------------------------- #
# DATI DI PARTENZA
# --------------------------------------------------------------------------- #
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)
current_value = float(holdings_valued["market_value"].sum())
target = settings.get("target_allocation", {})

# --------------------------------------------------------------------------- #
# HEADER + GUARD
# --------------------------------------------------------------------------- #
st.title("Monte Carlo — contribution projection")
st.caption(
    "Probabilistic simulation of the portfolio over the coming years, "
    "assuming the monthly contribution continues and IID returns calibrated "
    "on the recent history of the target portfolio."
)

if not target:
    callout(
        "<strong>Target allocation not configured.</strong> "
        "The simulation needs the target weights from the "
        "<strong>settings</strong> sheet of the Excel file.",
        kind="danger",
    )
    st.stop()

# --------------------------------------------------------------------------- #
# CACHED SIMULATION WRAPPER
# --------------------------------------------------------------------------- #
# `simulate_pac` è lenta (~5-15 sec per 10k simulazioni). Wrappiamo con
# @st.cache_data per evitare ricalcoli se l'utente cambia solo widget
# non impattanti (es. slider probabilità target).
#
# Gli argomenti devono essere hashable: dict → tuple di items.
@st.cache_data(
    show_spinner="Calibration + 10,000 Monte Carlo simulations…",
    ttl=3600,
)
def run_mc(
    tickers_tuple: tuple[str, ...],
    weights_items: tuple[tuple[str, float], ...],
    initial_value: float,
    monthly_contribution: float,
    horizons_tuple: tuple[int, ...],
    n_simulations: int,
    inflation_rate: float,
    lookback_years: int,
    seed: int,
) -> dict:
    """Wrapper cacheato di montecarlo.simulate_pac."""
    return mc.simulate_pac(
        tickers=list(tickers_tuple),
        weights=dict(weights_items),
        initial_value=initial_value,
        monthly_contribution=monthly_contribution,
        horizons_years=list(horizons_tuple),
        n_simulations=n_simulations,
        inflation_rate=inflation_rate,
        lookback_years=lookback_years,
        seed=seed,
    )


# --------------------------------------------------------------------------- #
# PARAMETRI INTERATTIVI
# --------------------------------------------------------------------------- #
st.subheader("Simulation parameters")

pcol1, pcol2, pcol3 = st.columns(3)

with pcol1:
    initial_value = st.number_input(
        "Initial value (€)",
        min_value=0.0,
        value=round(current_value, 2),
        step=500.0,
        format="%.2f",
        help="Default: current portfolio value. "
             "Start from 0 to simulate a plan from scratch.",
    )

with pcol2:
    monthly_pac = st.number_input(
        "Monthly contribution (€)",
        min_value=0.0,
        value=500.0,
        step=50.0,
        format="%.2f",
        help="Amount contributed each month. Constant across the whole simulation.",
    )

with pcol3:
    inflation_pct = st.slider(
        "Annual inflation (%)",
        min_value=0.0, max_value=6.0,
        value=mc.DEFAULT_INFLATION_RATE * 100, step=0.25,
        help="Used to compute real values (today's purchasing power). "
             "Default: 2% (ECB target).",
    )
    inflation_rate = inflation_pct / 100

# Riga 2 di parametri
pcol4, pcol5, pcol6 = st.columns(3)

with pcol4:
    horizons = st.multiselect(
        "Horizons (years)",
        options=[1, 3, 5, 10, 15, 20, 25, 30],
        default=[1, 5, 10, 20],
        help="Years for which to compute the percentiles in the table. "
             "The longest horizon sets the length of the fan chart.",
    )
if not horizons:
        callout("Select at least one horizon.", kind="warning")
        st.stop()

with pcol5:
    n_simulations = st.select_slider(
        "Simulations",
        options=[1_000, 5_000, 10_000, 25_000],
        value=mc.DEFAULT_N_SIMULATIONS,
        format_func=lambda n: f"{n:,}",
        help="More simulations = more stable tails but slower computation. "
             "10,000 is a good compromise.",
    )

with pcol6:
    lookback_years = st.slider(
        "Historical lookback (years)",
        min_value=3, max_value=15,
        value=7, step=1,
        help="How many years of history to use to calibrate returns. "
             "Longer = more stable but includes dated regimes. "
             "Shorter = more responsive but noisier.",
    )

# --------------------------------------------------------------------------- #
# LANCIA LA SIMULAZIONE
# --------------------------------------------------------------------------- #
tickers_tuple = tuple(sorted(target.keys()))
weights_items = tuple(sorted(target.items()))

try:
    result = run_mc(
        tickers_tuple=tickers_tuple,
        weights_items=weights_items,
        initial_value=initial_value,
        monthly_contribution=monthly_pac,
        horizons_tuple=tuple(sorted(horizons)),
        n_simulations=n_simulations,
        inflation_rate=inflation_rate,
        lookback_years=lookback_years,
        seed=42,
    )
except Exception as e:
    callout(f"Simulation error: {e}", kind="danger")
    st.stop()

cal = result["calibration"]
sim = result["simulation"]

# Il dict `cal` espone la Series `returns` grezza ma non gli aggregati
# annualizzati: li calcoliamo qui con le formule standard.
ann_return = (1 + cal["returns"]).prod() ** (mc.TRADING_DAYS_PER_YEAR / cal["n_days"]) - 1
ann_vol = cal["returns"].std() * np.sqrt(mc.TRADING_DAYS_PER_YEAR)

# --------------------------------------------------------------------------- #
# CALIBRAZIONE — pannello informativo compatto
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Historical calibration")

ccol1, ccol2, ccol3 = st.columns(3)
with ccol1:
    kpi_card(
        "Historical annual return",
        f"{ann_return:+.2%}",
        help="Geometric annualised return computed over the lookback period.",
    )
with ccol2:
    kpi_card(
        "Historical annual volatility",
        f"{ann_vol:.2%}",
        help="Annualised standard deviation of daily returns.",
    )
with ccol3:
    kpi_card(
        "History used",
        f"{cal['n_days']:,} days",
        delta=f"{cal['n_days']/252:.1f} years",
        delta_kind="neutral",
        help=f"Period: {cal['start_date']:%d/%m/%Y} → {cal['end_date']:%d/%m/%Y}",
    )

st.divider()

# --------------------------------------------------------------------------- #
# FAN CHART
# --------------------------------------------------------------------------- #
st.subheader("Fan chart — probabilistic projection")

simulations = sim["simulations"]  # shape: (n_sims, n_months+1)
n_months = simulations.shape[1] - 1
months_axis = np.arange(n_months + 1)

# Calcolo percentili per ogni mese
p5 = np.percentile(simulations, 5, axis=0)
p25 = np.percentile(simulations, 25, axis=0)
p50 = np.percentile(simulations, 50, axis=0)
p75 = np.percentile(simulations, 75, axis=0)
p95 = np.percentile(simulations, 95, axis=0)

# Capitale versato deterministico (linea di riferimento)
contributed = initial_value + monthly_pac * months_axis

fig = go.Figure()

# Fascia esterna 5-95:
# Trace p95 come "limite superiore" (linea invisibile ma con hover)
# Trace p5 con fill="tonexty" che riempie tra p5 e p95
fig.add_trace(go.Scatter(
    x=months_axis, y=p95,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.4,
    name="95th percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>95th pct.</extra>",
))
fig.add_trace(go.Scatter(
    x=months_axis, y=p5,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.4,
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["value"], 0.10),
    name="5th percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>5th pct.</extra>",
))

# Fascia interna 25-75:
fig.add_trace(go.Scatter(
    x=months_axis, y=p75,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.5,
    name="75th percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>75th pct.</extra>",
))
fig.add_trace(go.Scatter(
    x=months_axis, y=p25,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.5,
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["value"], 0.22),
    name="25th percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>25th pct.</extra>",
))

# Linea mediana p50 (spessa, navy)
fig.add_trace(go.Scatter(
    x=months_axis, y=p50,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=2.4),
    name="Median (50th)",
    hovertemplate="<b>€%{y:,.0f}</b><extra>Median</extra>",
))

# Linea capitale versato (arancione tratteggiata)
fig.add_trace(go.Scatter(
    x=months_axis, y=contributed,
    mode="lines",
    line=dict(color=ps.COLORS["benchmark"], width=1.6, dash="dash"),
    name="Contributed capital",
    hovertemplate="<b>€%{y:,.0f}</b><extra>Contributed capital</extra>",
))

# Marker sui valori finali (mediana + versato)
last_m = months_axis[-1]
fig.add_trace(go.Scatter(
    x=[last_m], y=[p50[-1]],
    mode="markers",
    marker=dict(color=ps.COLORS["value"], size=10,
                line=dict(color="white", width=1.8)),
    showlegend=False, hoverinfo="skip",
))
fig.add_trace(go.Scatter(
    x=[last_m], y=[contributed[-1]],
    mode="markers",
    marker=dict(color=ps.COLORS["benchmark"], size=7,
                line=dict(color="white", width=1.5)),
    showlegend=False, hoverinfo="skip",
))

# Assi + hover unificato + endline annotations
ps.style_axes(fig, y_format="euro", x_is_date=False)
ps.hover_unified(fig, x_format="%d months")   # x è numerico (mesi)

# Custom tickvals X: mostro "anni" invece di mesi.
# Es. n_months=240 (20 anni) → tick a 0, 12, 24, ..., 240 con label 0,1,2,...,20
years_max = n_months // 12
# Determino step per non affollare l'asse (max ~10 tick)
year_step = max(1, years_max // 10)
year_ticks = list(range(0, years_max + 1, year_step))
month_tickvals = [y * 12 for y in year_ticks]
year_ticktext = [str(y) for y in year_ticks]
fig.update_xaxes(
    tickvals=month_tickvals,
    ticktext=year_ticktext,
    title=dict(text="Years", font=dict(size=10, color=ps.COLORS["muted"])),
)

# Endline annotations sui valori finali (pattern A: destra dopo i marker)
ps.add_endline_annotations(fig, [
    {"y": p50[-1], "text": f"€{p50[-1]:,.0f}", "color": ps.COLORS["value"]},
    {"y": contributed[-1], "text": f"€{contributed[-1]:,.0f}",
     "color": ps.COLORS["benchmark"]},
])

max_horizon = max(horizons)
median_final = p50[max_horizon * 12] if max_horizon * 12 <= n_months else p50[-1]
ps.apply_layout(
    fig,
    title=f"{max_horizon}-year projection · {monthly_pac:,.0f} €/month",
    subtitle=f"Median at {max_horizon} years: €{median_final:,.0f}  ·  "
             f"{n_simulations:,} Monte Carlo simulations",
    source=f"Calibration: {cal['start_date']:%m/%Y}–{cal['end_date']:%m/%Y} "
           f"({cal['n_days']/252:.1f} years)",
    height=500,
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA PERCENTILI PER ORIZZONTE
# --------------------------------------------------------------------------- #
st.subheader("Percentiles by horizon")

nominal_toggle = st.radio(
    "View",
    options=["Nominal", "Real (in today's money)"],
    horizontal=True,
    help="**Nominal**: absolute future values. "
         "**Real**: deflated for inflation, showing purchasing power in "
         "today's euros. The difference grows with the horizon.",
)
use_real = "Real" in nominal_toggle

rows = []
for years in sorted(horizons):
    if years not in sim["horizons"]:
        continue  # orizzonte oltre la lunghezza della simulazione
    h = sim["horizons"][years]
    perc = h["percentiles_real"] if use_real else h["percentiles_nominal"]
    rows.append({
    "Horizon": f"{years} years",
    "Total contributed": round(h["total_contributed"]),
    "5th (worst)": round(perc[5]),
    "25th": round(perc[25]),
    "Median (50th)": round(perc[50]),
    "75th": round(perc[75]),
    "95th (best)": round(perc[95]),
})

df = pd.DataFrame(rows)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Total contributed": st.column_config.NumberColumn(format="euro"),
        "5th (worst)":       st.column_config.NumberColumn(format="euro"),
        "25th":              st.column_config.NumberColumn(format="euro"),
        "Median (50th)":     st.column_config.NumberColumn(format="euro"),
        "75th":              st.column_config.NumberColumn(format="euro"),
        "95th (best)":       st.column_config.NumberColumn(format="euro"),
    },
)

if use_real:
    st.caption(
        f"Real values are deflated for annual inflation of "
        f"**{inflation_pct:.2f}%**. Over 20 years, the erosion of purchasing "
        f"power is about {(1 - 1/(1+inflation_rate)**20)*100:.1f}%."
    )

st.divider()

# --------------------------------------------------------------------------- #
# PROBABILITÀ DI UN OBIETTIVO
# --------------------------------------------------------------------------- #
st.subheader("Probability of reaching a goal")
st.caption(
    "Given a € threshold and a horizon, computes the probability that the "
    "portfolio exceeds it. Useful for setting realistic goals."
)

tcol1, tcol2, tcol3 = st.columns([1, 1, 1])
with tcol1:
    target_value = st.number_input(
        "Goal (€)",
        min_value=0.0,
        value=100_000.0,
        step=10_000.0,
        format="%.0f",
    )
with tcol2:
    target_horizon = st.selectbox(
        "Horizon", options=sorted(horizons),
        index=len(sorted(horizons)) // 2,  # default: orizzonte "medio"
    )
with tcol3:
    # Spacer per allineare il checkbox all'altezza dei campi input a sinistra
    # (compensa l'altezza della label del number_input, ~28px).
    st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    target_use_real = st.checkbox(
        "Goal in today's € (real)",
        value=False,
        help="If enabled, the goal is compared against inflation-deflated values.",
    )

prob = mc.probability_of_target(
    result,
    target_value=target_value,
    horizon_years=target_horizon,
    use_real_values=target_use_real,
)

# Metric + interpretazione dinamica
mcol1, mcol2 = st.columns([1, 2])
with mcol1:
    kpi_card(
        "Probability",
        f"{prob:.1%}",
        delta=f"at {target_horizon} years",
        delta_kind="neutral",
    )

with mcol2:
    real_suffix = ' (real)' if target_use_real else ''
    if prob >= 0.90:
        callout(
            f"<strong>Goal very likely</strong> ({prob:.1%}). With these "
            f"parameters, exceeding €{target_value:,.0f}{real_suffix} at "
            f"{target_horizon} years is almost a given.",
            kind="success",
        )
    elif prob >= 0.50:
        callout(
             f"<strong>Goal plausible</strong> ({prob:.1%}). There's better than "
            f"a 1-in-2 chance of exceeding €{target_value:,.0f}{real_suffix} at "
            f"{target_horizon} years.",
            kind="info",
        )
    elif prob >= 0.20:
        callout(
            f"<strong>Goal ambitious</strong> ({prob:.1%}). Less than a 1-in-4 "
            f"chance. Consider a larger contribution or a longer horizon.",
            kind="warning",
        )
    else:
        callout(
            f"<strong>Goal unrealistic</strong> ({prob:.1%}). With these "
            f"parameters, exceeding €{target_value:,.0f} at {target_horizon} years "
            f"is unlikely.",
            kind="danger",
        )

st.divider()

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE TESTUALE (auto-generata dal modulo)
# --------------------------------------------------------------------------- #
st.subheader("Interpretation")
callout(result["interpretation"], kind="info")

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO / CAVEAT METODOLOGICI
# --------------------------------------------------------------------------- #
with st.expander("Methodology and caveats"):
    st.markdown(
        f"""
        **How the simulation works**
        1. **Calibration**: `{lookback_years}` years of history for the target
           ETFs are downloaded and a series of daily returns is built for the
           portfolio weighted by the target allocation
        2. **IID bootstrap**: for each future day, a historical day is sampled
           (with replacement). It's the simplest method that preserves the
           empirical return distribution (skewness, fat tails), unlike the
           classic Gaussian GBM
        3. **Monthly compounding**: 21 days are aggregated per month, and the
           compounded return is applied to capital + that month's contribution
        4. **`{n_simulations:,}` paths** projected over the longest horizon of
           **{max(horizons)} years**

        **Methodological caveats** (worth keeping in mind):

        - **IID assumption**: ignores *volatility clustering* (volatile days
          tend to cluster, cf. GARCH). A simplification, but better than
          Gaussian GBM
        - **Limited calibration window** ({lookback_years} years): may not
          include extreme crashes like 2008 or 2020
        - **Past returns ≠ future**: calibration assumes the future distribution
          resembles the past one. It's the weakest assumption, but also the only
          reasonable one without macro models
        - **Dividend withholding taxes**: not accounted for
          (~0.1-0.3% per year impact on net returns)
        - **Retail behavioural bias**: the simulation assumes contributions
          continue even during drawdowns. In practice many stop contributing at
          the worst moments — **exactly when they should persist**

        **How to read the percentiles**

        - **5th percentile**: very pessimistic scenario (95 out of 100 do better)
        - **25th percentile**: pessimistic but plausible scenario
        - **50th (median)**: the "expected" result — half the cases do better, half worse
        - **75th percentile**: optimistic but plausible scenario
        - **95th percentile**: very optimistic scenario (only 5 out of 100 do better)

        The **25th-75th range** (the darker band in the fan chart) is the one
        worth watching for realistic planning.
        """
    )
