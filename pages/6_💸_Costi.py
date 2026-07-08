"""
6_💸_Costi.py — Riepilogo costi e fiscalità del portafoglio.

Mostra la cascata dal P&L lordo al P&L netto netto, sottraendo:
- Commissioni TR (cash effettivo)
- Bollo modellato (cash effettivo, stimato)
- Imposta plusvalenze 26% (virtuale, solo se vendi oggi)

Il TER è mostrato come informativo ma NON viene sottratto (già scontato
dal NAV degli ETF accumulating).

Mappa la sezione 9 del notebook.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import streamlit as st
from matplotlib.ticker import FuncFormatter

import portfolio as pf
import costs as cst
import chart_style as cs
from streamlit_utils import ensure_data_loaded, render_sidebar, TX_FILE, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Costi", page_icon="💸", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="costi")
cs.apply_global_style()


# --------------------------------------------------------------------------- #
# CACHED LOADER DEI COSTI
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Carico configurazione costi…")
def load_costs_cached(path: str) -> dict:
    """Wrapper cacheato di cst.load_costs.

    Lo definisco qui (e non in streamlit_utils.py) perché finora solo questa
    pagina lo usa. Se in futuro la pagina Ribilanciamento ne avrà bisogno,
    si centralizza.
    """
    return cst.load_costs(path)


costs_cfg = load_costs_cached(str(TX_FILE))

# --------------------------------------------------------------------------- #
# CALCOLI
# --------------------------------------------------------------------------- #
vs = pf.portfolio_value_series(tx, prices)
holdings = pf.compute_holdings(tx)
holdings_valued = pf.value_holdings(holdings, prices)

summary = cst.cost_summary(tx, holdings_valued, vs, costs_cfg)

# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Costi e fiscalità")
st.caption(
    "Cascata dal P&L lordo al P&L netto netto. "
    "Le imposte sulle plusvalenze sono **simulate** ('se vendessi oggi')."
)

# 4 metriche di sintesi
col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card(
        "P&L lordo",
        f"{summary['pnl_lordo']:+,.2f} €",
        delta=f"{summary['pnl_lordo_pct']:+.2%}",
        delta_kind="positive" if summary['pnl_lordo'] >= 0 else "negative",
    )
with col2:
    kpi_card(
        "Costi cash",
        f"−{summary['cash_costs']:,.2f} €",
        delta=f" {summary['fees_total']:,.2f} comm. + "
              f"{summary['bollo_model']:,.2f} bollo",
        delta_kind="neutral",
        help="Commissioni TR (effettive) + bollo modellato (0,2% annuo).",
    )
with col3:
    kpi_card(
        "Tax simulata (26%)",
        f"−{summary['cap_gain_tax']:,.2f} €",
        delta="se vendi oggi",
        delta_kind="neutral",
        help="Stima dell'imposta sulle plusvalenze in caso di liquidazione "
             "totale del portafoglio. Per ETF armonizzati: 26% sulla plusvalenza "
             "netta (le minusvalenze di una posizione compensano le plusvalenze "
             "di un'altra).",
    )
with col4:
    kpi_card(
        "P&L netto netto",
        f"{summary['pnl_net_net']:+,.2f} €",
        delta=f"{summary['pnl_net_net_pct']:+.2%}",
        delta_kind="positive" if summary['pnl_net_net'] >= 0 else "negative",
    )

st.divider()

# --------------------------------------------------------------------------- #
# WATERFALL CHART
# --------------------------------------------------------------------------- #
st.subheader("Cascata: dal lordo al netto netto")

pnl_lordo = summary["pnl_lordo"]
fees = summary["fees_total"]
bollo = summary["bollo_model"]
tax = summary["cap_gain_tax"]
pnl_nn = summary["pnl_net_net"]

# Costruisco arrays per il waterfall: bottoms, heights, colors.
# Le barre intermedie "fluttuano" tra due livelli consecutivi della cascata.
labels = ["P&L lordo", "− Commissioni", "− Bollo modello",
          "− Cap gain tax", "P&L netto netto"]

bottoms = []
heights = []
colors = []

# Barra 1: totale P&L lordo
bottoms.append(0)
heights.append(pnl_lordo)
colors.append(cs.COLORS["gain"] if pnl_lordo >= 0 else cs.COLORS["loss"])

# Barre intermedie: delta che riducono il running
running = pnl_lordo
running_levels = [pnl_lordo]  # serve per le linee di collegamento
for delta in [-fees, -bollo, -tax]:
    new_running = running + delta
    # Per delta negativi: barra parte dal nuovo livello (basso) e sale al livello precedente
    bottoms.append(min(running, new_running))
    heights.append(abs(delta))
    colors.append(cs.COLORS["loss"] if delta < 0 else cs.COLORS["gain"])
    running = new_running
    running_levels.append(running)

# Barra 5: totale P&L netto netto
bottoms.append(0)
heights.append(pnl_nn)
colors.append(cs.COLORS["gain"] if pnl_nn >= 0 else cs.COLORS["loss"])

# Plot
fig, ax = plt.subplots(figsize=(11, 5.5))
x_pos = list(range(len(labels)))
bar_width = 0.6

ax.bar(x_pos, heights, bottom=bottoms, color=colors,
       width=bar_width, edgecolor="white", linewidth=1.2)

# Linee di collegamento tratteggiate tra una barra e la successiva
for i, level in enumerate(running_levels):
    # Linea che parte dal lato destro della barra i e arriva al lato sinistro della barra i+1
    ax.plot(
        [x_pos[i] + bar_width / 2, x_pos[i + 1] - bar_width / 2],
        [level, level],
        color=cs.COLORS["muted"], linewidth=1.0, linestyle="--", alpha=0.6,
    )

# Etichette di valore sopra/dentro ogni barra
for i, (lbl, b, h) in enumerate(zip(labels, bottoms, heights)):
    top = b + h
    # Per le barre "totali" (prima e ultima) l'etichetta sopra la barra
    if i in (0, len(labels) - 1):
        val = pnl_lordo if i == 0 else pnl_nn
        ax.text(i, top + abs(pnl_lordo) * 0.03,
                f"€{val:+,.2f}", ha="center", va="bottom",
                fontsize=10.5, fontweight="bold",
                color=cs.COLORS["fg"])
    else:
        # Per le barre intermedie: il delta dentro la barra (in rosso)
        delta_value = -[fees, bollo, tax][i - 1]
        ax.text(i, b + h / 2, f"€{delta_value:+,.2f}",
                ha="center", va="center",
                fontsize=9.5, fontweight="bold", color="white")

# Etichette X
ax.set_xticks(x_pos)
ax.set_xticklabels(labels, fontsize=10)

# Asse Y in euro
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"€{v:,.0f}"))
cs.style_axis(ax, euro=False, date_axis=False)
ax.grid(False, axis="x")
ax.axhline(0, color=cs.COLORS["muted"], linewidth=0.8)

# Margine verticale sopra le barre per le etichette
ymax = max(pnl_lordo, pnl_nn, 0) * 1.15
ymin = min(0, pnl_nn) * 1.05 if pnl_nn < 0 else 0
ax.set_ylim(ymin, ymax)

cs.add_title(
    fig,
    title="Cascata costi e fiscalità",
    subtitle=f"P&L netto netto = P&L lordo − commissioni − bollo − imposta plus",
    source=None,
)
st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------- #
# TABELLA DETTAGLIO
# --------------------------------------------------------------------------- #
st.subheader("Dettaglio voci")

inv = summary["invested"]
rows = [
    ("P&L lordo",
     summary["pnl_lordo"], summary["pnl_lordo_pct"],
     "valore di mercato − capitale investito"),
    ("  − Commissioni TR",
     -summary["fees_total"], -summary["fees_total"] / inv if inv else 0,
     "fees effettive sulle operazioni"),
    ("  − Bollo (modello)",
     -summary["bollo_model"], -summary["bollo_model"] / inv if inv else 0,
     "0,20% annuo modellato con accrual giornaliero"),
    ("     Bollo (reale TR)",
     -summary["bollo_real"], -summary["bollo_real"] / inv if inv else 0,
     "informativo: addebiti reali, se compilati"),
    ("  − Imposta plus 26%",
     -summary["cap_gain_tax"], -summary["cap_gain_tax"] / inv if inv else 0,
     "simulata 'se vendi oggi', su plusvalenza netta"),
    ("P&L netto netto",
     summary["pnl_net_net"], summary["pnl_net_net_pct"],
     "= lordo − cash costs − tax simulata"),
]

import pandas as pd
detail = pd.DataFrame(rows, columns=["Voce", "Importo (€)", "% su investito", "Nota"])
detail["% su investito"] = detail["% su investito"] * 100

st.dataframe(
    detail,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Importo (€)":     st.column_config.NumberColumn(format="%+.2f €"),
        "% su investito":  st.column_config.NumberColumn(format="%+.3f%%"),
    },
)

st.caption(
    "**Bollo modello vs reale**: il modello stima il bollo con accrual "
    "giornaliero, il reale è quanto TR ha effettivamente addebitato. "
    "Le due cifre dovrebbero convergere su periodi lunghi."
)

st.divider()

# --------------------------------------------------------------------------- #
# BOLLO MODELLO VS REALE (se disponibile)
# --------------------------------------------------------------------------- #
bollo_real_df = costs_cfg["bollo_real"]

st.subheader("Bollo modellato vs reale")

if len(bollo_real_df) > 0:
    # Bar chart side-by-side
    bcol1, bcol2 = st.columns([2, 1])

    with bcol1:
        fig, ax = plt.subplots(figsize=(8, 4))
        cats = ["Modello", "Reale TR"]
        vals = [summary["bollo_model"], summary["bollo_real"]]
        bar_colors = [cs.COLORS["value"], cs.COLORS["benchmark"]]
        bars = ax.bar(cats, vals, color=bar_colors, width=0.45,
                      edgecolor="white", linewidth=1.2)

        # Etichette di valore sopra le barre
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() * 1.02,
                    f"€{v:,.2f}", ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=cs.COLORS["fg"])

        ax.set_ylabel("€")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"€{v:,.2f}"))
        cs.style_axis(ax, euro=False, date_axis=False)
        ax.grid(False, axis="x")
        cs.add_title(fig, "Bollo modellato vs addebiti reali",
                     subtitle="Confronto cumulato a oggi", source=None)
        st.pyplot(fig, use_container_width=True)

    with bcol2:
        delta_abs = summary["bollo_model"] - summary["bollo_real"]
        delta_pct = (delta_abs / summary["bollo_real"]
                     if summary["bollo_real"] else 0)
        kpi_card(
            "Differenza modello − reale",
            f"€{delta_abs:+,.2f}",
            delta=f"{delta_pct:+.1%}" if summary["bollo_real"] else None,
            delta_kind="neutral",
        )
        st.markdown(
            f"**Addebiti registrati**: {len(bollo_real_df)}  \n"
            f"**Totale**: €{summary['bollo_real']:,.2f}"
        )

    # Tabella addebiti reali (compatta)
    with st.expander("📋 Dettaglio addebiti reali registrati"):
        breal = bollo_real_df.copy()
        breal["date"] = pd.to_datetime(breal["date"])
        breal = breal.sort_values("date")
        breal = breal.rename(columns={
            "date": "Data", "amount": "Importo", "notes": "Note"
        })
        st.dataframe(
            breal,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data":    st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Importo": st.column_config.NumberColumn(format="%.2f €"),
            },
        )
else:
    callout(
        "Non sono stati registrati addebiti reali del bollo. "
        "Per popolare questo confronto, aggiungi un foglio "
        "<strong>bollo_charges</strong> al file Excel con colonne "
        "<strong>date</strong>, <strong>amount</strong>, <strong>notes</strong> "
        "e inserisci gli addebiti trimestrali di TR.",
        kind="info",
    )

st.divider()

# --------------------------------------------------------------------------- #
# TER INFORMATIVO
# --------------------------------------------------------------------------- #
st.subheader("TER (Total Expense Ratio)")

if costs_cfg["ter"]:
    tcol1, tcol2 = st.columns([1, 2])

    with tcol1:
        kpi_card(
            "TER pesato annuo",
            f"{summary['ter_weighted']*100:.3f}%",
            delta=f"≈ {summary['ter_annual_eur']:,.2f} €/anno",
            delta_kind="neutral",
            help="Media pesata sui pesi correnti del portafoglio. "
                 "Il valore in euro è una stima sul valore di mercato attuale.",
        )

    with tcol2:
        callout(
            "Il <strong>TER non viene sottratto</strong> dal P&L perché è già "
            "scontato dal NAV giornaliero degli ETF (per ETF accumulating come "
            "VWCE/VFEA i prezzi yfinance riflettono già il NAV post-TER). "
            "Sottrarlo nuovamente sarebbe double counting. È mostrato qui solo "
            "a fini informativi, per dare visibilità di un costo strutturalmente "
            "invisibile.",
            kind="info",
        )

    # Tabella TER per ticker
    ter_rows = [
        (t, costs_cfg["ter"][t], holdings_valued.loc[t, "weight"]
         if t in holdings_valued.index else 0.0)
        for t in costs_cfg["ter"]
    ]
    ter_df = pd.DataFrame(ter_rows, columns=["Ticker", "TER annuo", "Peso"])
    ter_df["TER annuo"] = ter_df["TER annuo"] * 100
    ter_df["Peso"] = ter_df["Peso"] * 100

    st.dataframe(
        ter_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "TER annuo": st.column_config.NumberColumn(format="%.3f%%"),
            "Peso":      st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
else:
    callout(
        "Non è stato configurato il TER degli ETF. "
        "Per popolare questa sezione, aggiungi un foglio <strong>ter</strong> "
        "al file Excel con colonne <strong>ticker</strong>, "
        "<strong>ter_annual</strong>, <strong>note</strong> "
        "(es. VWCE.DE → 0.0022 per 0,22%).",
        kind="info",
    )

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ Logica della cascata"):
    st.markdown(
        """
        **Cosa viene sottratto** (e perché):
        - **Commissioni TR**: cash effettivo già pagato sulle operazioni
        - **Bollo modellato**: stima del bollo annuo italiano (0,20%) accruato
          giornalmente. È *cash effettivo* anche se non ancora addebitato
        - **Imposta plusvalenze 26%**: **virtuale** — si paga solo se vendi.
          Per ETF armonizzati italiani, le minusvalenze di una posizione
          compensano le plusvalenze di un'altra in caso di liquidazione
          simultanea. Se il netto è in perdita, l'imposta è zero (genera
          minusvalenza compensabile entro 4 anni)

        **Cosa NON viene sottratto** (e perché):
        - **TER**: già scontato dal NAV degli ETF accumulating, vedi sopra
        - **Bollo reale**: è solo *informativo*, per verificare l'accuratezza
          del modello. Il modello è quello che entra nella cascata perché è
          continuo e prevedibile
        """
    )
