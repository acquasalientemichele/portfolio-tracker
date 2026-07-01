"""
5_🏆_Benchmark.py — Performance del portafoglio vs benchmark.

Tre serie a confronto, tutte normalizzate a 1.0 al primo giorno di
operatività:
- TWR lordo: rendimento dello strumento (timing-neutral, lordo bollo/tasse)
- TWR netto bollo: stesso TWR ma con il valore decurtato del bollo cumulato
- Benchmark: prezzo di chiusura del ticker benchmark, normalizzato

Il drag del bollo è la differenza in pp tra TWR lordo e netto.

Mappa la sezione 8 del notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import streamlit as st

import portfolio as pf
import costs as cst
import chart_style as cs
from streamlit_utils import ensure_data_loaded, render_sidebar, fetch_prices, inject_css

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Benchmark", page_icon="🏆", layout="wide")

inject_css()

tx, prices, settings = ensure_data_loaded()
render_sidebar()
cs.apply_global_style()

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

# Allineo tutte e tre le serie sulla stessa griglia temporale
common_idx = twr.index.intersection(bench_norm.index)
twr_a = twr.reindex(common_idx)
twr_net_a = twr_net.reindex(common_idx)
bench_a = bench_norm.reindex(common_idx)

# Valori finali
last_p = float(twr_a.iloc[-1])
last_pn = float(twr_net_a.iloc[-1])
last_b = float(bench_a.iloc[-1])

ret_p = (last_p - 1) * 100
ret_pn = (last_pn - 1) * 100
ret_b = (last_b - 1) * 100
drag_pp = ret_p - ret_pn
alpha_vs_bench = ret_p - ret_b  # outperformance vs benchmark (lordo)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("🏆 Performance vs Benchmark")
st.caption(
    f"Confronto del rendimento (TWR) con il benchmark **{benchmark_ticker}**, "
    f"tutte le serie normalizzate a 1.0 al primo giorno di operatività"
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("TWR lordo", f"{ret_p:+.2f}%")
col2.metric(
    "TWR netto bollo",
    f"{ret_pn:+.2f}%",
    delta=f"−{drag_pp:.2f}pp drag",
    delta_color="inverse",
    help="Performance del portafoglio dopo aver detratto il bollo "
         "modellato (0,2% annuo sul valore giornaliero).",
)
col3.metric(f"Benchmark ({benchmark_ticker})", f"{ret_b:+.2f}%")
col4.metric(
    "Alpha vs benchmark",
    f"{alpha_vs_bench:+.2f}pp",
    delta=("Outperformance" if alpha_vs_bench > 0 else "Underperformance"),
    delta_color="normal" if alpha_vs_bench >= 0 else "inverse",
    help="Differenza in punti percentuali tra TWR lordo del portafoglio "
         "e rendimento del benchmark.",
)

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE
# --------------------------------------------------------------------------- #
# Messaggio dinamico basato sull'alpha
if benchmark_ticker in set(tx["ticker"].unique()):
    # Caso comune: benchmark coincide con uno degli ETF in portafoglio
    st.info(
        f"ℹ️ Il benchmark **{benchmark_ticker}** è anche uno degli ETF nel tuo "
        f"portafoglio. È normale che la performance del portafoglio sia molto "
        f"vicina a quella del benchmark — la differenza è generata dal peso "
        f"degli altri ETF e dalle date dei versamenti."
    )
elif abs(alpha_vs_bench) < 0.5:
    st.info(f"📊 La performance del portafoglio è sostanzialmente in linea "
            f"con il benchmark (spread {alpha_vs_bench:+.2f}pp).")
elif alpha_vs_bench > 0:
    st.success(f"✅ Il portafoglio sovraperforma il benchmark di "
               f"**{alpha_vs_bench:+.2f}pp** (TWR lordo).")
else:
    st.warning(f"⚠️ Il portafoglio sottoperforma il benchmark di "
               f"**{alpha_vs_bench:.2f}pp** (TWR lordo).")

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICO
# --------------------------------------------------------------------------- #
fig, ax = plt.subplots(figsize=(11, 5.5))
cs.style_axis(ax, euro=False)

# Formatter asse Y: variazione % rispetto al base 1.0
def pct_fmt(v, _):
    delta = v - 1.0
    if abs(delta) < 0.0005:
        return "Base"
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta)*100:.0f}%"

ax.yaxis.set_major_formatter(plt.FuncFormatter(pct_fmt))

# Fill: outperformance/underperformance vs benchmark (sul lordo)
ax.fill_between(
    common_idx, twr_a, bench_a,
    where=(twr_a >= bench_a),
    color=cs.COLORS["gain"], alpha=0.12, interpolate=True, zorder=1,
)
ax.fill_between(
    common_idx, twr_a, bench_a,
    where=(twr_a < bench_a),
    color=cs.COLORS["loss"], alpha=0.12, interpolate=True, zorder=1,
)

# Linea base (1.0)
ax.axhline(1.0, color=cs.COLORS["grid"], linewidth=1.0, zorder=1)

# Linea benchmark (tratteggiata, color dedicato)
ax.plot(bench_a.index, bench_a,
        color=cs.COLORS["benchmark"], linewidth=1.6, linestyle="--",
        label="Benchmark", zorder=2)

# Linea portafoglio netto (puntinata, alpha)
ax.plot(twr_net_a.index, twr_net_a,
        color=cs.COLORS["value"], linewidth=1.3, linestyle=":",
        label="Portafoglio netto (post-bollo)", alpha=0.85, zorder=3)

# Linea portafoglio lordo (la principale)
ax.plot(twr_a.index, twr_a,
        color=cs.COLORS["value"], linewidth=2.2,
        label="Portafoglio lordo", zorder=4)

# Marker e annotazioni sui valori finali
ax.scatter([common_idx[-1]], [last_p], color=cs.COLORS["value"], s=45,
           zorder=6, edgecolor="white", linewidth=1.8)
ax.scatter([common_idx[-1]], [last_pn], color=cs.COLORS["value"], s=22,
           zorder=6, edgecolor="white", linewidth=1.2, alpha=0.8)
ax.scatter([common_idx[-1]], [last_b], color=cs.COLORS["benchmark"], s=32,
           zorder=6, edgecolor="white", linewidth=1.5)

ax.annotate(
    f"  {ret_p:+.1f}%", xy=(common_idx[-1], last_p),
    xytext=(6, 6), textcoords="offset points", va="bottom", ha="left",
    fontsize=10.5, fontweight="bold", color=cs.COLORS["value"],
)
ax.annotate(
    f"  {ret_pn:+.1f}% netto", xy=(common_idx[-1], last_pn),
    xytext=(6, -6), textcoords="offset points", va="top", ha="left",
    fontsize=9, color=cs.COLORS["value"], alpha=0.85,
)
ax.annotate(
    f"  {ret_b:+.1f}%", xy=(common_idx[-1], last_b),
    xytext=(6, 0), textcoords="offset points", va="center", ha="left",
    fontsize=10, color=cs.COLORS["benchmark"],
)

# Margine destro extra per le label
span = common_idx[-1] - common_idx[0]
ax.set_xlim(common_idx[0], common_idx[-1] + span * 0.09)

cs.style_legend(ax)
cs.add_title(
    fig,
    title="Performance: Lordo vs Netto vs Benchmark",
    subtitle=(f"Lordo {ret_p:+.1f}%   ·   "
              f"Netto bollo {ret_pn:+.1f}% (drag {drag_pp:.2f} pp)   ·   "
              f"Benchmark {ret_b:+.1f}%"),
    source=f"Fonte: yfinance (EOD)  ·  Aggiornato {common_idx[-1].date()}",
)

st.pyplot(fig, use_container_width=True)

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Come leggere il grafico"):
    st.markdown(
        f"""
        - **Linea blu continua**: TWR del portafoglio al **lordo** di bollo e tasse.
          È la metrica standard GIPS, indipendente dal timing dei versamenti.
        - **Linea blu puntinata**: stesso TWR ma **netto del bollo modellato**
          (0,2% annuo sul valore giornaliero, modellato con accrual giornaliero).
          Il *drag* è l'erosione di performance dovuta esclusivamente al bollo.
        - **Linea tratteggiata** (color benchmark): prezzo di {benchmark_ticker}
          normalizzato a 1.0 al primo giorno di operatività.
        - **Area verde / rossa**: outperformance / underperformance del
          portafoglio (lordo) rispetto al benchmark.

        **Cosa NON include il "netto"**:
        - L'imposta sulle plusvalenze (26%), che si applica solo in caso di
          vendita. Per la simulazione "se vendessi oggi" vedi la pagina
          **Costi e fiscalità** (in arrivo).
        - Il TER degli ETF: già incorporato nel NAV restituito da yfinance,
          quindi è implicitamente nel TWR lordo.

        **Nota sul confronto**: se il benchmark è uno degli ETF in portafoglio,
        la performance del portafoglio sarà strutturalmente vicina al benchmark.
        Per un confronto più informativo si può cambiare `benchmark_ticker` nel
        foglio `settings` del file Excel.
        """
    )
