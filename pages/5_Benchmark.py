"""
5_Benchmark.py — Performance del portafoglio vs benchmark.

Tre serie a confronto, tutte normalizzate a 1.0 al primo giorno di
operatività:
- TWR lordo: rendimento dello strumento (timing-neutral, lordo bollo/tasse)
- TWR netto bollo: stesso TWR ma con il valore decurtato del bollo cumulato
- Benchmark: prezzo di chiusura del ticker benchmark, normalizzato

Il drag del bollo è la differenza in pp tra TWR lordo e netto.

Mappa la sezione 8 del notebook.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import portfolio as pf
import costs as cst
import plotly_style as ps
from streamlit_utils import ensure_data_loaded, render_sidebar, fetch_prices, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Benchmark", page_icon="🏆", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar(current_page="benchmark")

benchmark_ticker = settings.get("benchmark_ticker", "VWCE.DE")

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
vs = pf.portfolio_value_series(tx, prices)
twr = pf.time_weighted_return(vs)

# TWR netto bollo: ricalcolo il TWR sulla serie value decurtata del bollo cumulato
vs_net = cst.value_series_net_of_bollo(vs)
twr_net = pf.time_weighted_return(vs_net)

# Scarico il benchmark — riuso la cache di streamlit_utils
bench_df = fetch_prices((benchmark_ticker,), start=vs.index.min().strftime("%Y-%m-%d"))
bench = bench_df[benchmark_ticker].reindex(vs.index).ffill()
bench_norm = bench / bench.iloc[0]

# Allineo le serie sulla stessa griglia temporale
common_idx = twr.index.intersection(bench_norm.index)
twr_a = twr.reindex(common_idx)
bench_a = bench_norm.reindex(common_idx)

# Valori finali
last_p = float(twr_a.iloc[-1])
last_pn = float(twr_net.reindex(common_idx).iloc[-1])  # per KPI "TWR netto bollo"
last_b = float(bench_a.iloc[-1])

ret_p = (last_p - 1) * 100
ret_pn = (last_pn - 1) * 100
ret_b = (last_b - 1) * 100
drag_pp = ret_p - ret_pn
alpha_vs_bench = ret_p - ret_b  # outperformance vs benchmark (lordo)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Performance vs Benchmark")
st.caption(
    f"Confronto del rendimento (TWR) con il benchmark **{benchmark_ticker}**, "
    f"tutte le serie normalizzate a 1.0 al primo giorno di operatività"
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("TWR lordo", f"{ret_p:+.2f}%")
with col2:
    kpi_card(
        "TWR netto bollo",
        f"{ret_pn:+.2f}%",
        delta=f"−{drag_pp:.2f}pp drag",
        delta_kind="negative",
        help="Performance del portafoglio dopo aver detratto il bollo "
             "modellato (0,2% annuo sul valore giornaliero).",
    )
with col3:
    kpi_card(f"Benchmark ({benchmark_ticker})", f"{ret_b:+.2f}%")
with col4:
    kpi_card(
        "Alpha vs benchmark",
        f"{alpha_vs_bench:+.2f}pp",
        delta="Outperformance" if alpha_vs_bench > 0 else "Underperformance",
        delta_kind="positive" if alpha_vs_bench >= 0 else "negative",
        help="Differenza in punti percentuali tra TWR lordo del portafoglio "
             "e rendimento del benchmark.",
    )

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE
# --------------------------------------------------------------------------- #
# Messaggio dinamico basato sull'alpha
if benchmark_ticker in set(tx["ticker"].unique()):
    # Caso comune: benchmark coincide con uno degli ETF in portafoglio
    callout(
        f"Il benchmark <strong>{benchmark_ticker}</strong> è anche uno degli ETF "
        f"nel tuo portafoglio. È normale che la performance del portafoglio sia "
        f"molto vicina a quella del benchmark — la differenza è generata dal peso "
        f"degli altri ETF e dalle date dei versamenti.",
        kind="info",
    )
elif abs(alpha_vs_bench) < 0.5:
    callout(
        f"La performance del portafoglio è sostanzialmente in linea con il "
        f"benchmark (spread {alpha_vs_bench:+.2f}pp).",
        kind="info",
    )
elif alpha_vs_bench > 0:
    callout(
        f"Il portafoglio sovraperforma il benchmark di "
        f"<strong>{alpha_vs_bench:+.2f}pp</strong> (TWR lordo).",
        kind="success",
    )
else:
    callout(
        f"Il portafoglio sottoperforma il benchmark di "
        f"<strong>{alpha_vs_bench:.2f}pp</strong> (TWR lordo).",
        kind="warning",
    )

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO (Plotly interattivo)
# --------------------------------------------------------------------------- #
# Confronto TWR lordo vs benchmark. La linea "portafoglio netto post-bollo"
# è stata rimossa: il drag del bollo è irrilevante visivamente (< 0.1pp
# → linea sovrapposta a quella lorda) e il valore quantitativo resta
# esplicito nella KPI card "TWR netto bollo" con delta -X.XXpp drag.

# Trasformo le serie normalizzate (1.0 = base) in variazione %
# (0.0 = base). Plotly con y_format="percent" moltiplica × 100.
ret_p_series = twr_a - 1.0
ret_bench_series = bench_a - 1.0

# Area fill tra portafoglio e benchmark: verde quando lordo > benchmark
# (outperformance), rosso altrimenti. Stessa tecnica di Andamento:
# 4 trace mascherate con np.maximum/np.minimum.
p_upper = np.maximum(ret_p_series.values, ret_bench_series.values)
p_lower = np.minimum(ret_p_series.values, ret_bench_series.values)

fig = go.Figure()

# Baseline invisibile = benchmark (riferimento per il fill)
fig.add_trace(go.Scatter(
    x=common_idx, y=ret_bench_series.values,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    showlegend=False, hoverinfo="skip", name="_baseline",
))

# Area verde: sopra baseline dove portafoglio > benchmark
fig.add_trace(go.Scatter(
    x=common_idx, y=p_upper,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["gain"], 0.12),
    showlegend=False, hoverinfo="skip", name="_area_gain",
))

# Baseline invisibile duplicata (serve tra un fill e l'altro)
fig.add_trace(go.Scatter(
    x=common_idx, y=ret_bench_series.values,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    showlegend=False, hoverinfo="skip", name="_baseline2",
))

# Area rossa: sotto baseline dove portafoglio < benchmark
fig.add_trace(go.Scatter(
    x=common_idx, y=p_lower,
    mode="lines",
    line=dict(color="rgba(0,0,0,0)", width=0),
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["loss"], 0.12),
    showlegend=False, hoverinfo="skip", name="_area_loss",
))

# Linea benchmark (arancio bruciato, tratteggiata)
fig.add_trace(go.Scatter(
    x=common_idx, y=ret_bench_series.values,
    name="Benchmark",
    mode="lines",
    line=dict(color=ps.COLORS["benchmark"], width=1.6, dash="dash"),
    hovertemplate="<b>%{y:+.2%}</b><extra>Benchmark</extra>",
))

# Linea portafoglio lordo (navy solid, principale)
fig.add_trace(go.Scatter(
    x=common_idx, y=ret_p_series.values,
    name="Portafoglio",
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=2.2),
    hovertemplate="<b>%{y:+.2%}</b><extra>Portafoglio</extra>",
))

# Linea di base a 0 (riferimento visivo)
fig.add_hline(
    y=0,
    line=dict(color=ps.COLORS["grid"], width=1.0),
    opacity=0.6,
)

# Marker sui valori finali (portafoglio grande navy, benchmark medio arancio)
fig.add_trace(go.Scatter(
    x=[common_idx[-1]], y=[ret_p_series.iloc[-1]],
    mode="markers",
    marker=dict(color=ps.COLORS["value"], size=10,
                line=dict(color="white", width=1.8)),
    showlegend=False, hoverinfo="skip",
))
fig.add_trace(go.Scatter(
    x=[common_idx[-1]], y=[ret_bench_series.iloc[-1]],
    mode="markers",
    marker=dict(color=ps.COLORS["benchmark"], size=8,
                line=dict(color="white", width=1.5)),
    showlegend=False, hoverinfo="skip",
))

# Assi + hover unificato + endline annotations (pattern A: destra dopo i marker)
ps.style_axes(fig, y_format="percent", x_is_date=True)
ps.hover_unified(fig)
ps.add_endline_annotations(fig, [
    {"y": ret_p_series.iloc[-1], "text": f"{ret_p:+.1f}%",
     "color": ps.COLORS["value"]},
    {"y": ret_bench_series.iloc[-1], "text": f"{ret_b:+.1f}%",
     "color": ps.COLORS["benchmark"]},
])

ps.apply_layout(
    fig,
    title="Performance: Portafoglio vs Benchmark",
    subtitle=f"Lordo {ret_p:+.1f}%   ·   "
             f"Benchmark {ret_b:+.1f}%   ·   "
             f"Alpha {alpha_vs_bench:+.2f}pp",
    source=f"Fonte: yfinance (EOD)  ·  Aggiornato {common_idx[-1].date()}",
    height=500,
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Come leggere il grafico"):
    st.markdown(
        f"""
        - **Linea blu continua**: TWR del portafoglio al **lordo** di bollo e tasse.
          È la metrica standard GIPS, indipendente dal timing dei versamenti.
        - **Linea tratteggiata** (color benchmark): prezzo di {benchmark_ticker}
          normalizzato a 1.0 al primo giorno di operatività.
        - **Area verde / rossa**: outperformance / underperformance del
          portafoglio (lordo) rispetto al benchmark.

        **Sul drag del bollo**: la performance netta post-bollo modellato
        (0,2% annuo) è mostrata quantitativamente nella KPI card **TWR netto
        bollo** in alto (delta pp rispetto al lordo). Non è rappresentata
        come linea separata nel grafico perché il drag è tipicamente < 0.1pp
        → produrrebbe una linea sovrapposta al lordo, senza aggiungere
        informazione visiva.

        **Cosa NON include il "netto bollo"**:
        - L'imposta sulle plusvalenze (26%), che si applica solo in caso di
          vendita. Per la simulazione "se vendessi oggi" vedi la pagina
          **Costi e fiscalità**.
        - Il TER degli ETF: già incorporato nel NAV restituito da yfinance,
          quindi è implicitamente nel TWR lordo.

        **Nota sul confronto**: se il benchmark è uno degli ETF in portafoglio,
        la performance del portafoglio sarà strutturalmente vicina al benchmark.
        Per un confronto più informativo si può cambiare `benchmark_ticker` nel
        foglio `settings` del file Excel.
        """
    )
