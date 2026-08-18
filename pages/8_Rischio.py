"""
8_Rischio.py — Metriche di rischio del portafoglio.

Mostra:
- Confidence badge (affidabilità delle metriche in base alla storia)
- 6 metriche di sintesi (volatilità, Sharpe, Sortino, beta, max DD, rend ann.)
- Drawdown underwater chart con marker top-3
- Tabella top drawdowns con badge di status
- Interpretazione testuale auto-generata dal modulo
- Promemoria didattico sulle metriche

Mappa la sezione 11 del notebook.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import portfolio as pf
import risk as rk
import plotly_style as ps
from streamlit_utils import ensure_data_loaded, render_sidebar, fetch_prices, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Risk", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="rischio")

benchmark_ticker = settings.get("benchmark_ticker", "VWCE.DE")

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
vs = pf.portfolio_value_series(tx, prices)
twr_cum = pf.time_weighted_return(vs)

# Benchmark: stesso pattern della pagina Performance vs Benchmark
bench_df = fetch_prices((benchmark_ticker,), start=vs.index.min().strftime("%Y-%m-%d"))
bench = bench_df[benchmark_ticker].reindex(vs.index).ffill()
bench_norm = bench / bench.iloc[0]

# Risk-free rate: default 3% (BTP 3y) — controllabile via parametro avanzato
# (per ora costante, in futuro si può aggiungere uno slider in sidebar)
rf_default = rk.DEFAULT_RISK_FREE_RATE

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Risk")
st.caption(
    "Risk metrics and drawdown analysis. "
    "Annualised metrics should be read in light of the available history."
)

# Parametro avanzato: risk-free rate (impatta Sharpe e Sortino)
with st.expander("Calculation parameters"):
    rf_annual = st.slider(
        "Annualised risk-free rate (%)",
        min_value=0.0, max_value=6.0,
        value=rf_default * 100, step=0.25,
        help="'Risk-free' rate used for Sharpe and Sortino. "
             "Default: 3% (3-year BTP yield). "
             "Raising it lowers Sharpe and Sortino.",
    ) / 100
    st.caption(
        "Changing the risk-free rate does not affect volatility, beta or drawdown. "
        "It only impacts Sharpe and Sortino, which are returns *net of the reference rate*."
    )

# Calcolo completo via risk_summary
metrics = rk.risk_summary(twr_cum, bench_norm, rf_annual=rf_annual)

# --------------------------------------------------------------------------- #
# CONFIDENCE BADGE
# --------------------------------------------------------------------------- #
# La prima cosa che l'utente deve vedere: quanto sono affidabili le metriche.
conf = metrics["confidence"]
period_days = metrics["period_days"]
period_years = metrics["period_years"]

CONFIDENCE_CONFIG = {
    "VERY_LOW": ("danger",  "Very low confidence",
                 "annualised metrics on < 6 months of history are "
                 "essentially noise"),
    "LOW":      ("warning", "Low confidence",
                 "on < 1 year of history, annualisation tends to "
                 "overstate expected performance"),
    "MEDIUM":   ("info",    "Medium confidence",
                 "on 1-3 years of history, metrics start to be "
                 "indicative but with wide confidence intervals"),
    "HIGH":     ("success", "High confidence",
                 "with > 3 years of history, metrics are statistically "
                 "informative"),
}

kind, title, descr = CONFIDENCE_CONFIG[conf]
body = f"{period_days} days of history ({period_years} years): {descr}."
callout(body, kind=kind, title=title)

st.divider()

# --------------------------------------------------------------------------- #
# METRICHE DI SINTESI (2 righe × 3 colonne)
# --------------------------------------------------------------------------- #
st.subheader("Metrics")


def fmt_ratio(v: float) -> str:
    """Formatta uno Sharpe/Sortino/Beta. Gestisce NaN e inf."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    return f"{v:.2f}"


def fmt_pct(v: float, signed: bool = False) -> str:
    """Formatta un valore in % con o senza segno."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:+.2%}" if signed else f"{v:.2%}"


# Riga 1: volatilità, Sharpe, Sortino
row1c1, row1c2, row1c3 = st.columns(3)
with row1c1:
    kpi_card(
        "Annualised volatility",
        fmt_pct(metrics["volatility_annualized"]),
        help="Standard deviation of daily returns × √252. "
             "The standard risk measure for equity portfolios.",
    )
with row1c2:
    kpi_card(
        "Sharpe ratio",
        fmt_ratio(metrics["sharpe_ratio"]),
        delta=f"vs rf {rf_annual:.1%}",
        delta_kind="neutral",
        help="(Annualised return − risk-free) / annualised volatility. "
             "Return per unit of total risk. "
             "As a rule of thumb: > 1 good, > 2 excellent, < 0 the portfolio "
             "returns less than the risk-free rate.",
    )
with row1c3:
    kpi_card(
        "Sortino ratio",
        fmt_ratio(metrics["sortino_ratio"]),
        delta=f"vs rf {rf_annual:.1%}",
        delta_kind="neutral",
        help="Like Sharpe but uses only *downside* volatility (returns < 0). "
             "Philosophically fairer if you consider only losses to be 'risk'. "
             "∞ = no negative return over the whole history.",
    )

# Riga 2: beta, max drawdown, rendimento annualizzato
row2c1, row2c2, row2c3 = st.columns(3)
with row2c1:
    kpi_card(
        f"Beta vs {benchmark_ticker}",
        fmt_ratio(metrics["beta_vs_benchmark"]),
        help="Sensitivity of the portfolio to benchmark moves. "
             "= 1: moves like the benchmark. "
             "> 1: more volatile than the benchmark. "
             "< 1: less volatile.",
    )
with row2c2:
    in_dd = metrics["is_currently_in_drawdown"]
    kpi_card(
        "Max drawdown",
        fmt_pct(metrics["max_drawdown"], signed=True),
        delta="ongoing" if in_dd else "recovered",
        delta_kind="negative" if in_dd else "positive",
        help="Largest peak-to-trough loss over the period. "
             "The most 'gut-level' risk metric: how much red you see at "
             "the worst moment.",
    )
with row2c3:
    kpi_card(
        "Annualised return",
        fmt_pct(metrics["annualized_return"], signed=True),
        help="Geometric annualised return of the portfolio. "
             "Over short periods it tends to overstate expected performance.",
    )

st.divider()

# --------------------------------------------------------------------------- #
# DRAWDOWN CHART (Plotly interattivo)
# --------------------------------------------------------------------------- #
st.subheader("Drawdown underwater chart")

dd_series = rk.compute_drawdown_series(twr_cum)
top_dds = metrics["top_drawdowns"]

# Serie drawdown in frazione (0 → -0.15 per un DD del 15%).
# Plotly con y_format="percent" moltiplica × 100 per la visualizzazione.
dd = dd_series["drawdown"]

fig = go.Figure()

# Area shaded rossa sotto la curva (verso zero)
fig.add_trace(go.Scatter(
    x=dd_series.index, y=dd.values,
    mode="lines",
    line=dict(color=ps.COLORS["loss"], width=1.4),
    fill="tozeroy",
    fillcolor=ps._hex_to_rgba(ps.COLORS["loss"], 0.15),
    hovertemplate="<b>%{y:+.2%}</b><extra>Drawdown</extra>",
    name="Drawdown",
))

# Linea orizzontale a 0 (livello peak)
fig.add_hline(
    y=0,
    line=dict(color=ps.COLORS["muted"], width=0.8, dash="dash"),
    opacity=0.6,
)

# Marker + annotazioni sui top-N drawdowns.
# Convenzione posizionale: il primo (più profondo) ha l'annotation SOTTO
# il marker per non affollare l'area centrale del grafico; gli altri
# hanno l'annotation SOPRA per allontanarli dal cluster centrale.
for i, drow in top_dds.iterrows():
    bottom_date = drow["bottom_date"]
    depth = drow["depth"]

    # Marker
    fig.add_trace(go.Scatter(
        x=[bottom_date], y=[depth],
        mode="markers",
        marker=dict(color=ps.COLORS["loss"], size=11,
                    line=dict(color="white", width=1.5)),
        showlegend=False,
         hovertemplate=f"<b>#{i+1}: {depth:+.2%}</b>"
                      f"{'  (ongoing)' if not drow['recovered'] else ''}"
                      f"<extra></extra>",
    ))

    # Annotation — sempre sotto il punto e centrata, per leggibilità uniforme
    label = f"#{i+1}: {depth:+.2%}"
    if not drow["recovered"]:
        label += "  (ongoing)"

    fig.add_annotation(
        x=bottom_date, y=depth,
        text=f"<b>{label}</b>",
        showarrow=False,
        xanchor="center", yanchor="top",
        yshift=-12,
        font=dict(size=10, color=ps.COLORS["loss"], family="Inter, sans-serif"),
    )

# Assi + hover unificato
ps.style_axes(fig, y_format="percent", x_is_date=True)
ps.hover_unified(fig)

# Un po' di aria sopra la linea 0 per non far comprimere il grafico
# quando i drawdown sono piccoli
y_top = max(0.005, abs(dd.min()) * 0.15)   # almeno 0.5% sopra
y_bottom = dd.min() * 1.25                  # 25% di aria sotto (era 10%)
fig.update_yaxes(range=[y_bottom, y_top])

max_dd_pct = metrics["max_drawdown"]
max_dd_dur = metrics["max_drawdown_duration_days"] or "—"
ps.apply_layout(
    fig,
    title="Drawdown over time",
    subtitle=f"Percentage loss from the running peak.  "
             f"Max DD: {max_dd_pct:+.2%},  duration {max_dd_dur} days",
    source=None,
    height=380,   # più basso del default 420 perché il DD è "underwater" (poca aria sopra)
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

# --------------------------------------------------------------------------- #
# TABELLA TOP DRAWDOWNS
# --------------------------------------------------------------------------- #
st.subheader(f"Top {rk.DEFAULT_TOP_N_DRAWDOWNS} drawdowns")

if len(top_dds) == 0:
    callout(
        f"No significant drawdown (> "
        f"{rk.DEFAULT_DRAWDOWN_THRESHOLD:.1%}) recorded so far.",
        kind="success",
    )
else:
    view = top_dds.copy()
    view["status"] = view["recovered"].apply(
        lambda r: "🟢 Recovered" if r else "🔴 Ongoing"
    )
    view["depth"] = view["depth"] * 100  # in %

    view = view[["start_date", "bottom_date", "end_date", "depth",
                 "duration_days", "recovery_days", "status"]].rename(columns={
        "start_date":    "Start",
        "bottom_date":   "Bottom",
        "end_date":      "Recovery",
        "depth":         "Depth",
        "duration_days": "Duration (d)",
        "recovery_days": "Recovery (d)",
        "status":        "Status",
    })

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Start":        st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Bottom":       st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Recovery":     st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Depth":        st.column_config.NumberColumn(format="%+.2f%%"),
            "Duration (d)": st.column_config.NumberColumn(format="%d"),
            "Recovery (d)": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.caption(
        "**Duration** = days from peak to the bottom of the drawdown. "
        "**Recovery** = days from the bottom back to the peak. "
        "Ongoing drawdowns have no recovery date."
    )

st.divider()

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE TESTUALE
# --------------------------------------------------------------------------- #
st.subheader("Interpretation")

callout(metrics["interpretation"], kind="info")

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("Metrics reminder"):
    st.markdown(
        """
        **Annualised volatility**
        Standard deviation of daily returns × √252.
        Measures how far returns deviate from the mean — *how much the
        portfolio swings*. Typically 10-15% for global equity portfolios,
        20%+ for single stocks or emerging markets.

        **Sharpe ratio**
        `(Annualised return − Rf) / Annualised volatility`
        How much "extra" return you earn per unit of volatility you bear.
        > 1 good, > 2 excellent. Below 0 means the portfolio returns less
        than the risk-free rate — you're taking risk for nothing.

        **Sortino ratio**
        A variant of Sharpe that uses only *downside* volatility.
        Philosophically: upside volatility (returns above zero) isn't
        "risk" for an investor, only the downside is. For portfolios that
        only grow it can be ∞ (no negative return over the whole history).

        **Beta vs benchmark**
        Sensitivity of the portfolio to benchmark moves.
        β = 1: moves like the benchmark.
        β = 1.5: swings 50% more than the benchmark.
        β = 0.5: swings half as much as the benchmark.

        **Max drawdown**
        Largest percentage fall from the most recent peak.
        The most "gut-level" risk metric: how much red you see at the worst
        moment. For global equity portfolios, 20-30% drawdowns are normal
        over 5+ years of history. Crashes like 2008 and 2020 reached
        -35% / -50%.

        **Confidence level**
        An indicator of how much to trust the annualised metrics. The
        financial rule of thumb: you need at least 1 year of history for
        indicative metrics, 3+ years for statistically robust ones. Below
        6 months, annualisation is essentially noise.
        """
    )
