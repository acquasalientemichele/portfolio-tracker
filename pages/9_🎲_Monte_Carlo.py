"""
9_🎲_Monte_Carlo.py — Proiezioni PAC a lungo periodo.

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
st.set_page_config(page_title="Monte Carlo", page_icon="🎲", layout="wide")

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
st.title("Monte Carlo — Proiezione PAC")
st.caption(
    "Simulazione probabilistica del portafoglio nei prossimi anni, "
    "assumendo continuazione del PAC mensile e rendimenti IID calibrati "
    "sulla storia recente del portafoglio target."
)

if not target:
    callout(
        "<strong>Target allocation non configurata.</strong> "
        "La simulazione richiede i pesi target dal foglio "
        "<strong>settings</strong> del file Excel.",
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
    show_spinner="⏳ Calibrazione + 10.000 simulazioni Monte Carlo…",
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
st.subheader("Parametri della simulazione")

pcol1, pcol2, pcol3 = st.columns(3)

with pcol1:
    initial_value = st.number_input(
        "Valore iniziale (€)",
        min_value=0.0,
        value=round(current_value, 2),
        step=500.0,
        format="%.2f",
        help="Default: valore corrente del portafoglio. "
             "Puoi partire da 0 per simulare un PAC da zero.",
    )

with pcol2:
    monthly_pac = st.number_input(
        "PAC mensile (€)",
        min_value=0.0,
        value=500.0,
        step=50.0,
        format="%.2f",
        help="Importo versato ogni mese. Costante per tutta la simulazione.",
    )

with pcol3:
    inflation_pct = st.slider(
        "Inflazione annua (%)",
        min_value=0.0, max_value=6.0,
        value=mc.DEFAULT_INFLATION_RATE * 100, step=0.25,
        help="Usata per calcolare i valori reali (potere d'acquisto oggi). "
             "Default: 2% (target BCE).",
    )
    inflation_rate = inflation_pct / 100

# Riga 2 di parametri
pcol4, pcol5, pcol6 = st.columns(3)

with pcol4:
    horizons = st.multiselect(
        "Orizzonti (anni)",
        options=[1, 3, 5, 10, 15, 20, 25, 30],
        default=[1, 5, 10, 20],
        help="Anni per cui calcolare i percentili nella tabella. "
             "L'orizzonte massimo determina la lunghezza del fan chart.",
    )
if not horizons:
        callout("Seleziona almeno un orizzonte.", kind="warning")
        st.stop()

with pcol5:
    n_simulations = st.select_slider(
        "N° simulazioni",
        options=[1_000, 5_000, 10_000, 25_000],
        value=mc.DEFAULT_N_SIMULATIONS,
        format_func=lambda n: f"{n:,}",
        help="Più simulazioni = code più stabili ma calcolo più lento. "
             "10.000 è un buon compromesso.",
    )

with pcol6:
    lookback_years = st.slider(
        "Lookback storico (anni)",
        min_value=3, max_value=15,
        value=7, step=1,
        help="Quanti anni di storia usare per calibrare i rendimenti. "
             "Più lungo = più stabile ma include regimi datati. "
             "Più corto = più reattivo ma rumoroso.",
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
    callout(f"Errore nella simulazione: {e}", kind="danger")
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
st.subheader("Calibrazione storica")

ccol1, ccol2, ccol3 = st.columns(3)
with ccol1:
    kpi_card(
        "Rendimento storico ann.",
        f"{ann_return:+.2%}",
        help="Rendimento geometrico annualizzato calcolato sul periodo di lookback.",
    )
with ccol2:
    kpi_card(
        "Volatilità storica ann.",
        f"{ann_vol:.2%}",
        help="Deviazione standard annualizzata dei rendimenti giornalieri.",
    )
with ccol3:
    kpi_card(
        "Storia usata",
        f"{cal['n_days']:,} giorni",
        delta=f"{cal['n_days']/252:.1f} anni",
        delta_kind="neutral",
        help=f"Periodo: {cal['start_date']:%d/%m/%Y} → {cal['end_date']:%d/%m/%Y}",
    )

st.divider()

# --------------------------------------------------------------------------- #
# FAN CHART
# --------------------------------------------------------------------------- #
st.subheader("Fan chart — proiezione probabilistica")

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
    name="95° percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>95° perc.</extra>",
))
fig.add_trace(go.Scatter(
    x=months_axis, y=p5,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.4,
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["value"], 0.10),
    name="5° percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>5° perc.</extra>",
))

# Fascia interna 25-75:
fig.add_trace(go.Scatter(
    x=months_axis, y=p75,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.5,
    name="75° percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>75° perc.</extra>",
))
fig.add_trace(go.Scatter(
    x=months_axis, y=p25,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=0.5),
    opacity=0.5,
    fill="tonexty",
    fillcolor=ps._hex_to_rgba(ps.COLORS["value"], 0.22),
    name="25° percentile",
    hovertemplate="<b>€%{y:,.0f}</b><extra>25° perc.</extra>",
))

# Linea mediana p50 (spessa, navy)
fig.add_trace(go.Scatter(
    x=months_axis, y=p50,
    mode="lines",
    line=dict(color=ps.COLORS["value"], width=2.4),
    name="Mediana (50°)",
    hovertemplate="<b>€%{y:,.0f}</b><extra>Mediana</extra>",
))

# Linea capitale versato (arancione tratteggiata)
fig.add_trace(go.Scatter(
    x=months_axis, y=contributed,
    mode="lines",
    line=dict(color=ps.COLORS["benchmark"], width=1.6, dash="dash"),
    name="Capitale versato",
    hovertemplate="<b>€%{y:,.0f}</b><extra>Capitale versato</extra>",
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
ps.hover_unified(fig, x_format="%d mesi")   # x è numerico (mesi)

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
    title=dict(text="Anni", font=dict(size=10, color=ps.COLORS["muted"])),
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
    title=f"Proiezione {max_horizon} anni · PAC {monthly_pac:,.0f} €/mese",
    subtitle=f"Mediana a {max_horizon} anni: €{median_final:,.0f}  ·  "
             f"{n_simulations:,} simulazioni Monte Carlo",
    source=f"Calibrazione: {cal['start_date']:%m/%Y}–{cal['end_date']:%m/%Y} "
           f"({cal['n_days']/252:.1f} anni)",
    height=500,
)

st.plotly_chart(fig, use_container_width=True, config=ps.PLOTLY_CONFIG)

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA PERCENTILI PER ORIZZONTE
# --------------------------------------------------------------------------- #
st.subheader("Percentili per orizzonte")

nominal_toggle = st.radio(
    "Vista",
    options=["Nominali", "Reali (a prezzi di oggi)"],
    horizontal=True,
    help="**Nominali**: valori assoluti nel futuro. "
         "**Reali**: deflazionati per l'inflazione, mostrano il potere "
         "d'acquisto in euro di oggi. La differenza cresce con l'orizzonte.",
)
use_real = "Reali" in nominal_toggle

rows = []
for years in sorted(horizons):
    if years not in sim["horizons"]:
        continue  # orizzonte oltre la lunghezza della simulazione
    h = sim["horizons"][years]
    perc = h["percentiles_real"] if use_real else h["percentiles_nominal"]
    rows.append({
    "Orizzonte": f"{years} anni",
    "Versato tot.": round(h["total_contributed"]),
    "5° (worst)": round(perc[5]),
    "25°": round(perc[25]),
    "Mediana (50°)": round(perc[50]),
    "75°": round(perc[75]),
    "95° (best)": round(perc[95]),
})

df = pd.DataFrame(rows)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Versato tot.":   st.column_config.NumberColumn(format="euro"),
        "5° (worst)":     st.column_config.NumberColumn(format="euro"),
        "25°":            st.column_config.NumberColumn(format="euro"),
        "Mediana (50°)":  st.column_config.NumberColumn(format="euro"),
        "75°":            st.column_config.NumberColumn(format="euro"),
        "95° (best)":     st.column_config.NumberColumn(format="euro"),
    },
)

if use_real:
    st.caption(
        f"💡 I valori reali sono deflazionati per un'inflazione annua del "
        f"**{inflation_pct:.2f}%**. A 20 anni, l'erosione del potere d'acquisto "
        f"è di circa {(1 - 1/(1+inflation_rate)**20)*100:.1f}%."
    )

st.divider()

# --------------------------------------------------------------------------- #
# PROBABILITÀ DI UN OBIETTIVO
# --------------------------------------------------------------------------- #
st.subheader("Probabilità di raggiungere un obiettivo")
st.caption(
    "Data una soglia in € e un orizzonte, calcola la probabilità che il "
    "portafoglio la superi. Utile per calibrare obiettivi realistici."
)

tcol1, tcol2, tcol3 = st.columns([1, 1, 1])
with tcol1:
    target_value = st.number_input(
        "Obiettivo (€)",
        min_value=0.0,
        value=100_000.0,
        step=10_000.0,
        format="%.0f",
    )
with tcol2:
    target_horizon = st.selectbox(
        "Orizzonte", options=sorted(horizons),
        index=len(sorted(horizons)) // 2,  # default: orizzonte "medio"
    )
with tcol3:
    # Spacer per allineare il checkbox all'altezza dei campi input a sinistra
    # (compensa l'altezza della label del number_input, ~28px).
    st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    target_use_real = st.checkbox(
        "Obiettivo in € di oggi (reali)",
        value=False,
        help="Se attivo, l'obiettivo è confrontato con i valori "
             "deflazionati per l'inflazione.",
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
        "Probabilità",
        f"{prob:.1%}",
        delta=f"a {target_horizon} anni",
        delta_kind="neutral",
    )

with mcol2:
    real_suffix = ' (reali)' if target_use_real else ''
    if prob >= 0.90:
        callout(
            f"<strong>Obiettivo molto probabile</strong> ({prob:.1%}). Con questi "
            f"parametri, superare €{target_value:,.0f}{real_suffix} a "
            f"{target_horizon} anni è quasi scontato.",
            kind="success",
        )
    elif prob >= 0.50:
        callout(
            f"<strong>Obiettivo plausibile</strong> ({prob:.1%}). C'è più di 1 "
            f"chance su 2 di superare €{target_value:,.0f}{real_suffix} a "
            f"{target_horizon} anni.",
            kind="info",
        )
    elif prob >= 0.20:
        callout(
            f"<strong>Obiettivo ambizioso</strong> ({prob:.1%}). Meno di 1 chance "
            f"su 4. Considera un PAC più alto o un orizzonte più lungo.",
            kind="warning",
        )
    else:
        callout(
            f"<strong>Obiettivo poco realistico</strong> ({prob:.1%}). Con questi "
            f"parametri, superare €{target_value:,.0f} a {target_horizon} anni "
            f"è improbabile.",
            kind="danger",
        )

st.divider()

# --------------------------------------------------------------------------- #
# INTERPRETAZIONE TESTUALE (auto-generata dal modulo)
# --------------------------------------------------------------------------- #
st.subheader("Interpretazione")
callout(result["interpretation"], kind="info")

# --------------------------------------------------------------------------- #
# EXPANDER DIDATTICO / CAVEAT METODOLOGICI
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Metodologia e caveat"):
    st.markdown(
        f"""
        **Come funziona la simulazione**
        1. **Calibrazione**: si scaricano `{lookback_years}` anni di storia
           degli ETF target e si costruisce una serie di rendimenti giornalieri
           del portafoglio pesato secondo l'allocazione target
        2. **Bootstrap IID**: per ogni giorno futuro si campiona (con
           ripetizione) un giorno storico. È il metodo più semplice che
           preserva la distribuzione empirica dei rendimenti (skewness,
           fat tails), a differenza del classico GBM gaussiano
        3. **Composizione mensile**: si aggregano 21 giorni per mese,
           si applica il rendimento composto al capitale + PAC del mese
        4. **`{n_simulations:,}` path** proiettati per l'orizzonte massimo
           di **{max(horizons)} anni**

        **Caveat metodologici** (importanti da tenere presenti):

        - **IID assumption**: ignora il *volatility clustering* (i giorni
          volatili tendono a raggrupparsi, cf. GARCH). È una semplificazione
          ma migliore del GBM gaussiano
        - **Calibration window limitata** ({lookback_years} anni): potrebbe
          non includere crash estremi tipo 2008 o 2020
        - **Rendimenti passati ≠ futuri**: la calibrazione assume che la
          distribuzione futura assomigli a quella passata. È l'ipotesi più
          debole ma anche l'unica ragionevole senza modelli macro
        - **Ritenute fiscali sui dividendi**: non considerate
          (impatto ~0.1-0.3% annuo sui rendimenti netti)
        - **Bias comportamentale del retail**: la simulazione assume
          mantenimento del PAC anche durante i drawdown. In pratica, molti
          smettono di versare nei momenti peggiori — **esattamente quando
          bisognerebbe insistere**

        **Come leggere i percentili**

        - **5° percentile**: scenario molto pessimistico (95 casi su 100 vanno meglio)
        - **25° percentile**: scenario pessimistico ma plausibile
        - **50° (mediana)**: risultato "atteso" — metà dei casi va meglio, metà peggio
        - **75° percentile**: scenario ottimistico ma plausibile
        - **95° percentile**: scenario molto ottimistico (solo 5 casi su 100 vanno meglio)

        Il **range 25°-75°** (fascia più marcata nel fan chart) è quello
        che vale la pena guardare per pianificazione realistica.
        """
    )
