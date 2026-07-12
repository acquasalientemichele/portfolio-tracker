"""
8_📉_Rischio.py — Metriche di rischio del portafoglio.

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
st.set_page_config(page_title="Rischio", page_icon="📉", layout="wide")

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
st.title("Rischio")
st.caption(
    "Metriche di rischio e drawdown analysis. "
    "Le metriche annualizzate vanno lette tenendo conto della storia disponibile."
)

# Parametro avanzato: risk-free rate (impatta Sharpe e Sortino)
with st.expander("⚙️ Parametri di calcolo"):
    rf_annual = st.slider(
        "Risk-free rate annualizzato (%)",
        min_value=0.0, max_value=6.0,
        value=rf_default * 100, step=0.25,
        help="Tasso 'risk-free' usato per Sharpe e Sortino. "
             "Default: 3% (rendimento BTP 3y). "
             "Aumentarlo riduce Sharpe e Sortino.",
    ) / 100
    st.caption(
        "💡 Modificare il risk-free rate non cambia volatilità, beta o drawdown. "
        "Impatta solo Sharpe e Sortino, che sono rendimenti *al netto del riferimento*."
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
    "VERY_LOW": ("danger",  "Affidabilità molto bassa",
                 "le metriche annualizzate su < 6 mesi di storia sono "
                 "essenzialmente rumore"),
    "LOW":      ("warning", "Affidabilità bassa",
                 "su < 1 anno di storia, l'annualizzazione tende a "
                 "sovrastimare la performance attesa"),
    "MEDIUM":   ("info",    "Affidabilità media",
                 "su 1-3 anni di storia, le metriche cominciano a essere "
                 "indicative ma con ampi intervalli di confidenza"),
    "HIGH":     ("success", "Affidabilità alta",
                 "con > 3 anni di storia, le metriche sono statisticamente "
                 "informative"),
}

kind, title, descr = CONFIDENCE_CONFIG[conf]
body = f"{period_days} giorni di storia ({period_years} anni): {descr}."
callout(body, kind=kind, title=title)

st.divider()

# --------------------------------------------------------------------------- #
# METRICHE DI SINTESI (2 righe × 3 colonne)
# --------------------------------------------------------------------------- #
st.subheader("Metriche")


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
        "Volatilità annualizzata",
        fmt_pct(metrics["volatility_annualized"]),
        help="Deviazione standard dei rendimenti giornalieri × √252. "
             "È la misura standard di rischio per portafogli azionari.",
    )
with row1c2:
    kpi_card(
        "Sharpe ratio",
        fmt_ratio(metrics["sharpe_ratio"]),
        delta=f"vs rf {rf_annual:.1%}",
        delta_kind="neutral",
        help="(Rendimento ann. − risk-free) / volatilità ann. "
             "Misura il rendimento per unità di rischio totale. "
             "Indicativamente: > 1 buono, > 2 eccellente, < 0 il portafoglio "
             "rende meno del risk-free.",
    )
with row1c3:
    kpi_card(
        "Sortino ratio",
        fmt_ratio(metrics["sortino_ratio"]),
        delta=f"vs rf {rf_annual:.1%}",
        delta_kind="neutral",
        help="Come Sharpe ma usa solo la volatilità *downside* (rendimenti < 0). "
             "Filosoficamente più giusto per chi considera 'rischio' solo le "
             "perdite. ∞ = nessun rendimento negativo in tutta la storia.",
    )

# Riga 2: beta, max drawdown, rendimento annualizzato
row2c1, row2c2, row2c3 = st.columns(3)
with row2c1:
    kpi_card(
        f"Beta vs {benchmark_ticker}",
        fmt_ratio(metrics["beta_vs_benchmark"]),
        help="Sensibilità del portafoglio ai movimenti del benchmark. "
             "= 1: si muove come il benchmark. "
             "> 1: più volatile del benchmark. "
             "< 1: meno volatile.",
    )
with row2c2:
    in_dd = metrics["is_currently_in_drawdown"]
    kpi_card(
        "Max drawdown",
        fmt_pct(metrics["max_drawdown"], signed=True),
        delta="in corso" if in_dd else "recuperato",
        delta_kind="negative" if in_dd else "positive",
        help="Massima perdita peak-to-trough nel periodo. "
             "È la metrica più 'pancia' del rischio: è quanto vedi rosso "
             "nel momento peggiore.",
    )
with row2c3:
    kpi_card(
        "Rendimento annualizzato",
        fmt_pct(metrics["annualized_return"], signed=True),
        help="Rendimento geometrico annualizzato del portafoglio. "
             "Su periodi brevi tende a sovrastimare la performance attesa.",
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
                      f"{'  (in corso)' if not drow['recovered'] else ''}"
                      f"<extra></extra>",
    ))

    # Annotation
    label = f"#{i+1}: {depth:+.2%}"
    if not drow["recovered"]:
        label += "  (in corso)"

    yshift = -14 if i == 0 else 14
    yanchor = "top" if i == 0 else "bottom"

    fig.add_annotation(
        x=bottom_date, y=depth,
        text=f"<b>{label}</b>",
        showarrow=False,
        xanchor="left", yanchor=yanchor,
        xshift=8, yshift=yshift,
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
    title="Drawdown nel tempo",
    subtitle=f"Perdita percentuale dal peak running.  "
             f"Max DD: {max_dd_pct:+.2%},  durata {max_dd_dur} giorni",
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
        f"Nessun drawdown significativo (> "
        f"{rk.DEFAULT_DRAWDOWN_THRESHOLD:.1%}) registrato finora.",
        kind="success",
    )
else:
    view = top_dds.copy()
    view["status"] = view["recovered"].apply(
        lambda r: "🟢 Recuperato" if r else "🔴 In corso"
    )
    view["depth"] = view["depth"] * 100  # in %

    view = view[["start_date", "bottom_date", "end_date", "depth",
                 "duration_days", "recovery_days", "status"]].rename(columns={
        "start_date":    "Inizio",
        "bottom_date":   "Fondo",
        "end_date":      "Recupero",
        "depth":         "Profondità",
        "duration_days": "Durata (gg)",
        "recovery_days": "Recovery (gg)",
        "status":        "Stato",
    })

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Inizio":        st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Fondo":         st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Recupero":      st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Profondità":    st.column_config.NumberColumn(format="%+.2f%%"),
            "Durata (gg)":   st.column_config.NumberColumn(format="%d"),
            "Recovery (gg)": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.caption(
        "**Durata** = giorni dal peak al fondo del drawdown. "
        "**Recovery** = giorni dal fondo al recupero del peak. "
        "I drawdown in corso non hanno data di recupero."
    )

st.divider()

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE TESTUALE
# --------------------------------------------------------------------------- #
st.subheader("Interpretazione")

# Il modulo risk.py genera già un'interpretazione testuale ricca
# che incorpora confidence, vol, Sharpe e drawdown.
callout(metrics["interpretation"], kind="info")

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Promemoria sulle metriche"):
    st.markdown(
        """
        **Volatilità annualizzata**
        Deviazione standard dei rendimenti giornalieri × √252.
        Misura quanto i rendimenti si discostano dalla media — *quanto balla*
        il portafoglio. Tipicamente 10-15% per portafogli azionari globali,
        20%+ per single-stock o emerging.

        **Sharpe ratio**
        `(Rendimento ann. − Rf) / Volatilità ann.`
        Quanti euro di rendimento "extra" guadagni per ogni euro di
        volatilità che sopporti. > 1 buono, > 2 eccellente. Sotto 0
        significa che il portafoglio rende meno del risk-free, e quindi
        stai prendendo rischio per nulla.

        **Sortino ratio**
        Variante dello Sharpe che usa solo la volatilità *negativa*.
        Filosoficamente: la volatilità positiva (rendimenti sopra zero)
        non è "rischio" per un investitore, solo quella negativa lo è.
        Su portafogli sempre in crescita può essere ∞ (nessun rendimento
        negativo in tutta la storia).

        **Beta vs benchmark**
        Sensibilità del portafoglio ai movimenti del benchmark.
        β = 1: si muove come il benchmark.
        β = 1.5: oscilla del 50% in più del benchmark.
        β = 0.5: oscilla la metà del benchmark.

        **Max drawdown**
        Massima caduta percentuale dal picco più recente.
        È la metrica più "pancia" del rischio: quanto rosso vedi al
        momento peggiore. Per portafogli azionari globali, drawdown del
        20-30% sono fisiologici in 5+ anni di storia. Crash come 2008,
        2020 hanno raggiunto -35% / -50%.

        **Confidence level**
        Indicatore di quanto fidarsi delle metriche annualizzate. La
        regola dei "pollici" finanziari: serve almeno 1 anno di storia
        per metriche indicative, 3+ anni per metriche statisticamente
        robuste. Sotto 6 mesi, l'annualizzazione è essenzialmente rumore.
        """
    )
