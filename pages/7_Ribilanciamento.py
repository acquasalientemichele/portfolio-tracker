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
st.set_page_config(page_title="Ribilanciamento", page_icon="⚖️", layout="wide")

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
st.title("Ribilanciamento PAC")
st.caption(
    "Suggerimento operativo per il prossimo versamento e proiezione "
    "della convergenza al target."
)

if not target:
    callout(
        "<strong>Target allocation non configurata.</strong> "
        "Aggiungi i pesi target nel foglio <strong>settings</strong> del "
        "file Excel (formato: <strong>ticker | target_weight</strong>, somma = 1.0).",
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
    kpi_card("Valore portafoglio", f"{total_value:,.2f} €")
with scol2:
    kpi_card(
        "Max scostamento attuale",
        f"{max_dev_now:.2%}",
        delta=f"soglia {DEFAULT_THRESHOLD:.0%}",
        delta_kind="negative" if max_dev_now > DEFAULT_THRESHOLD else "positive",
    )
with scol3:
    kpi_card("Ticker fuori soglia", f"{n_off}/{len(all_tickers)}")

st.divider()

# --------------------------------------------------------------------------- #
# INPUT INTERATTIVO
# --------------------------------------------------------------------------- #
st.subheader("Parametri del versamento")

icol1, icol2 = st.columns([3, 1])
with icol1:
    new_cash = st.number_input(
        "Importo netto da investire (€)",
        min_value=10.0,
        value=500.0,
        step=50.0,
        format="%.2f",
        help="Importo che verrà effettivamente investito in ETF. "
             "Le commissioni sono aggiuntive e vengono pagate sopra questa cifra.",
    )

with icol2:
    # Spacer per allineare il bottone popover all'altezza del campo input
    # a sinistra (compensa l'altezza della label del number_input, ~28px).
    st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    with st.popover("⚙️ Parametri avanzati", use_container_width=True):
        threshold = st.slider(
            "Soglia di tolleranza (%)",
            min_value=0.5, max_value=5.0,
            value=DEFAULT_THRESHOLD * 100, step=0.5,
            help="Sotto questa soglia non vale la pena fare uno split su 2 ETF.",
        ) / 100
        fee_per_order = st.number_input(
            "Commissione per ordine (€)",
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
st.subheader(f"Suggerimento per PAC di {new_cash:,.2f} €")

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
        kpi_card("Cash investito", f"{s['cash_invested']:,.2f} €")
    with mcol2:
        kpi_card(
            "Commissioni",
            f"{s['fees_total']:,.2f} €",
            delta=f"{s['n_orders']} ordine/i",
            delta_kind="neutral",
        )
    with mcol3:
        kpi_card("Totale uscita conto", f"{s['cash_input']:,.2f} €")
    with mcol4:
        # Deviazione minore è meglio: se scende → positive, se sale → negative
        dev_delta = s['max_deviation_post'] - max_dev_now
        kpi_card(
            "Max deviazione post",
            f"{s['max_deviation_post']:.2%}",
            delta=f"{dev_delta*100:+.2f}pp vs attuale",
            delta_kind="positive" if dev_delta < 0 else "negative",
        )

    # Tabella ordini
    st.markdown("##### Ordini da eseguire")

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
        "name": "Nome",
        "quantity": "Quantità",
        "price": "Prezzo",
        "cash_invested": "Cash investito",
        "fees": "Commissione",
        "weight_post": "Peso post",
        "deviation_post": "Dev. post (pp)",
    })

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Quantità":       st.column_config.NumberColumn(format="%.4f"),
            "Prezzo":         st.column_config.NumberColumn(format="%.2f €"),
            "Cash investito": st.column_config.NumberColumn(format="%.2f €"),
            "Commissione":    st.column_config.NumberColumn(format="%.2f €"),
            "Peso post":      st.column_config.NumberColumn(format="%.2f%%"),
            "Dev. post (pp)": st.column_config.NumberColumn(format="%+.2f"),
        },
    )

st.divider()

# --------------------------------------------------------------------------- #
# PROIEZIONE CONVERGENZA
# --------------------------------------------------------------------------- #
st.subheader("Proiezione: in quanti mesi torno a target?")
st.caption(
    f"Simulazione con PAC mensile di {new_cash:,.0f} € ripetuto fino a "
    f"deviazione massima < {PROJECTION_TARGET_BAND:.1%}. "
    f"Ipotesi: prezzi costanti (semplificazione)."
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
            "Già a target",
            "✅",
            help=f"La deviazione massima è già sotto {PROJECTION_TARGET_BAND:.1%}.",
        )
    elif converged:
        kpi_card(
            "Mesi alla convergenza",
            f"{months_to_target}",
            delta=f"banda ±{PROJECTION_TARGET_BAND:.1%}",
            delta_kind="neutral",
        )
    else:
        final_dev = proj.get("final_max_dev", max_dev_now)
        kpi_card(
            "Non converge in 60 mesi",
            "—",
            delta=f"dev finale: {final_dev:.2%}",
            delta_kind="negative",
        )

with pcol2:
    if converged and months_to_target == 0:
        callout(
            f"Il portafoglio è già entro la banda di "
            f"{PROJECTION_TARGET_BAND:.1%} dal target. Nessuna azione "
            f"correttiva necessaria.",
            kind="success",
        )
    elif converged:
        callout(
            f"Continuando con un PAC mensile di <strong>{new_cash:,.0f} €</strong>, "
            f"il portafoglio rientrerà entro la banda di "
            f"<strong>{PROJECTION_TARGET_BAND:.1%}</strong> dal target in circa "
            f"<strong>{months_to_target} mesi</strong>. Nessuna vendita necessaria — "
            f"l'auto-correzione avviene tramite versamenti.",
            kind="info",
        )
    else:
        callout(
            f"Con un PAC di {new_cash:,.0f} €, il portafoglio non rientra "
            f"entro la banda di {PROJECTION_TARGET_BAND:.1%} nei prossimi "
            f"60 mesi (deviazione finale: {proj.get('final_max_dev', 0):.2%}). "
            f"Considera un PAC più alto o una vendita parziale (con il drag "
            f"fiscale del 26% sulle plusvalenze).",
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
        markeredgewidth=1.0, label="Max deviazione")

# Area shaded: zona target (< target_band)
ax.axhspan(0, target_band_pct, color=cs.COLORS["gain"], alpha=0.10,
           zorder=0, label=f"Banda target (< {target_band_pct:.1f}%)")

# Linea threshold (più alta)
ax.axhline(threshold_pct, color=cs.COLORS["muted"], linewidth=0.8,
           linestyle="--", alpha=0.6, label=f"Soglia {threshold_pct:.1f}%")

# Marker sul punto di convergenza
if converged and months_to_target is not None and months_to_target > 0:
    convergence_y = history.loc[history["month"] == months_to_target,
                                 "max_dev"].iloc[0] * 100
    ax.scatter([months_to_target], [convergence_y],
               color=cs.COLORS["gain"], s=120, zorder=5,
               edgecolor="white", linewidth=2.0,
               label=f"Convergenza al mese {months_to_target}")

cs.style_axis(ax, euro=False, date_axis=False)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}%"))
ax.set_xlabel("Mese", fontsize=10, color=cs.COLORS["fg"])
ax.set_ylim(bottom=0)

cs.style_legend(ax, loc="upper right")
cs.add_title(
    fig,
    title="Convergenza al target",
    subtitle=f"Max deviazione di portafoglio nel tempo · "
             f"PAC mensile {new_cash:,.0f} € · prezzi costanti",
    source=None,
)
st.pyplot(fig, use_container_width=True)

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Logica del ribilanciamento"):
    st.markdown(
        f"""
        **Strategia gap-closing single-buy**:
        1. Calcola il valore totale post-investimento e l'allocazione "ideale"
           (peso target × valore post)
        2. Identifica il ticker più sottopesato (gap maggiore tra ideale e attuale)
        3. **Prova un acquisto singolo** mettendo tutto il cash sul primary
        4. Se la deviazione post-acquisto è **sotto la soglia di {threshold:.1%}**,
           ferma qui (1 ordine, 1 commissione)
        5. Altrimenti **split su due ticker** in proporzione ai gap (2 ordini, 2 commissioni)

        **Perché single-buy preferito**:
        - La commissione TR di {fee_per_order:.2f} € su un PAC di {new_cash:,.0f} €
          vale {fee_per_order/new_cash:.2%} di drag (più del bollo annuo dello 0,2%)
        - Se la singola operazione chiude la deviazione, lo split è uno spreco
        - Il mese successivo correggerà naturalmente eventuali drift residui

        **Perché no vendite**:
        - Per ETF armonizzati italiani, vendere realizza plusvalenze tassate al 26%
        - Il tax drag rende il "sell-high/buy-low" sub-ottimale per retail
        - Il PAC fornisce naturalmente flussi per auto-correggere il drift

        **Caveat della proiezione**:
        - Assume **prezzi costanti** e **rendimenti nulli**: è una semplificazione
        - Nella realtà i prezzi si muovono e influenzano l'auto-correzione (a volte
          aiutando, a volte ostacolando)
        - Per una proiezione fedele alle dinamiche reali → pagina **Monte Carlo** (in arrivo)
        """
    )
