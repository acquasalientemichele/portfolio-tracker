"""
10_Diversificazione.py — Diversificazione del portafoglio (look-through).

Guarda "dentro" gli ETF e aggrega l'esposizione effettiva per settore, paese e
regione. Misura:
- Concentrazione via HHI -> numero effettivo di settori/paesi/regioni
- Sovrapposizione (overlap coefficient) tra i fondi in portafoglio
- Mappa geografica interattiva dell'esposizione per paese

Due modalita':
- Actual   : pesi reali dal portafoglio
- Simulate : slider per fondo, per vedere come cambia la diversificazione

Logica di calcolo in diversification.py (Streamlit-free); grafici in
diversification_charts.py. I dati arrivano dallo snapshot generato da
refresh_holdings.py + normalizzazione canonica.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import portfolio as pf
import chart_style as cs
import diversification as dv
import diversification_charts as dc
from holdings_canonical import canonicalize
from holdings_registry import REGISTRY
from refresh_holdings import SNAPSHOT_PATH
from streamlit_utils import ensure_data_loaded, render_sidebar, inject_css
from streamlit_components import kpi_card, callout

# --------------------------------------------------------------------------- #
# SETUP PAGINA
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Diversification", layout="wide")

inject_css()

tx, prices, _ = ensure_data_loaded()
render_sidebar(current_page="diversificazione")
cs.apply_global_style()


# --------------------------------------------------------------------------- #
# LOADER SNAPSHOT (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_snapshot() -> pd.DataFrame:
    """Legge lo snapshot holdings e applica la normalizzazione canonica.

    Cachato: lo snapshot cambia solo quando rilanci refresh_holdings.py, non
    a ogni interazione con gli slider.
    """
    raw = pd.read_parquet(SNAPSHOT_PATH)
    return canonicalize(raw, verbose=False)


# --------------------------------------------------------------------------- #
# HEADER
# --------------------------------------------------------------------------- #
st.title("Diversification")
st.caption(
    "Look-through analysis: your effective exposure by sector, country and "
    "region, seen through the ETFs' holdings."
)

# Se manca lo snapshot, spiego come generarlo invece di crashare.
if not SNAPSHOT_PATH.exists():
    callout(
        "No holdings snapshot found. Generate it by placing the issuers' "
        "holdings files in <strong>data/holdings_raw/</strong> and running "
        "<strong>python refresh_holdings.py</strong>.",
        kind="info",
    )
    st.stop()

snap = load_snapshot()

# ISIN presenti nello snapshot + etichette ticker dal registry.
present_isins = sorted(snap["fund_isin"].unique())
label_map = {isin: (REGISTRY[isin].ticker if isin in REGISTRY else isin)
             for isin in present_isins}

# Pesi reali dal portafoglio (per la modalita' Actual e come default degli slider).
holdings_valued = pf.value_holdings(pf.compute_holdings(tx), prices)
actual_weights = dv.weights_from_valued_holdings(holdings_valued)

# --------------------------------------------------------------------------- #
# MODALITA': Actual vs Simulate
# --------------------------------------------------------------------------- #
mode = st.radio(
    "Weighting",
    ["Actual", "Simulate"],
    horizontal=True,
    help="Actual: current portfolio weights. Simulate: set weights manually "
         "to see how composition changes diversification.",
)

if mode == "Actual":
    weights = actual_weights
else:
    st.caption("Set a weight per fund — values are normalised automatically.")
    scol = st.columns(min(len(present_isins), 4))
    weights = {}
    for i, isin in enumerate(present_isins):
        default = int(round(actual_weights.get(isin, 1.0 / len(present_isins)) * 100))
        with scol[i % len(scol)]:
            weights[isin] = st.slider(label_map[isin], 0, 100, default, step=1)

# Copertura del look-through (quota di portafoglio di cui abbiamo le holding).
cov = dv.coverage(snap, weights)

# In Actual, se non copriamo tutto il portafoglio, va detto chiaramente.
if mode == "Actual" and cov < 0.999:
    missing_isins = [i for i in actual_weights if i not in present_isins]
    mancanti = sorted(REGISTRY[i].ticker if i in REGISTRY else i for i in missing_isins)
    manc_txt = ", ".join(mancanti) if mancanti else "some funds"
    callout(
        f"<strong>Look-through covers {cov:.0%} of the portfolio.</strong> "
        f"Holdings are missing for: {manc_txt}. The exposures below are "
        f"renormalised over the covered part — add the missing snapshots for "
        f"the full picture.",
        kind="warning",
    )

# Report (distribuzioni + HHI + numero effettivo per ogni dimensione).
report = dv.diversification_report(snap, weights)
sec = report["sector"]["distribution"]
cty = report["country"]["distribution"]
reg = report["region"]["distribution"]

# --------------------------------------------------------------------------- #
# KPI: numero effettivo per dimensione + copertura
# --------------------------------------------------------------------------- #
col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card(
        "Effective sectors",
        f"{report['sector']['effective_number']:.1f}",
        delta=f"of {len(sec)} with exposure",
        delta_kind="neutral",
        help="1 / HHI on the sector look-through. Higher = more diversified.",
    )
with col2:
    n_eff_cty = report["country"]["effective_number"]
    kpi_card(
        "Effective countries",
        f"{n_eff_cty:.1f}",
        delta=f"of {len(cty)} with exposure",
        delta_kind="negative" if n_eff_cty < 1.5 else "neutral",
        help="1 / HHI on the country look-through. A value near 1 means "
             "almost single-country exposure.",
    )
with col3:
    kpi_card(
        "Effective regions",
        f"{report['region']['effective_number']:.1f}",
        delta=f"of {len(reg)} with exposure",
        delta_kind="neutral",
    )
with col4:
    kpi_card(
        "Look-through coverage",
        f"{cov:.0%}",
        delta="of portfolio value" if mode == "Actual" else "of simulated set",
        delta_kind="positive" if cov >= 0.999 else "negative",
    )

# Evidenzio l'insight tipico: buona diversificazione settoriale ma geografica bassa.
if report["country"]["effective_number"] < 1.5:
    callout(
        "Your equity exposure is concentrated in essentially a single country. "
        "Sector diversification can mask geographic concentration — they are "
        "different risks.",
        kind="info",
    )

st.divider()

# --------------------------------------------------------------------------- #
# GRAFICI: settori | regioni
# --------------------------------------------------------------------------- #
gcol1, gcol2 = st.columns(2)
with gcol1:
    st.subheader("Sector allocation")
    fig = dc.plot_distribution_bar(sec, "Sector allocation",
                                   subtitle=f"Look-through · coverage {cov:.0%}")
    st.pyplot(fig, use_container_width=True)
with gcol2:
    st.subheader("Regional allocation")
    fig = dc.plot_distribution_bar(reg, "Regional allocation",
                                   subtitle="Look-through", color=cs.COLORS["accent"])
    st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------- #
# MAPPA GEOGRAFICA INTERATTIVA
# --------------------------------------------------------------------------- #
st.subheader("Geographic exposure")
st.plotly_chart(dc.plot_country_map(cty), use_container_width=True)

st.divider()

# --------------------------------------------------------------------------- #
# OVERLAP TRA FONDI (solo se almeno due fondi)
# --------------------------------------------------------------------------- #
if len(present_isins) >= 2:
    st.subheader("Fund overlap")
    st.caption(
        "Overlap coefficient = Σ min(wᵢ) category by category. 100% = identical "
        "profiles, 0% = no shared exposure. Measured on the sector distribution."
    )
    ocol1, ocol2 = st.columns([3, 2])
    with ocol1:
        mat = dv.pairwise_overlap(snap, "sector").rename(index=label_map, columns=label_map)
        st.pyplot(dc.plot_overlap_heatmap(mat, "Fund overlap — sector space"),
                  use_container_width=True)
    with ocol2:
        # Coppie ordinate per overlap decrescente (esclude la diagonale).
        pairs = []
        isins = list(mat.index)
        for a in range(len(isins)):
            for b in range(a + 1, len(isins)):
                pairs.append((isins[a], isins[b], mat.iloc[a, b]))
        pairs_df = pd.DataFrame(pairs, columns=["Fund A", "Fund B", "Overlap"])
        pairs_df["Overlap"] = pairs_df["Overlap"] * 100
        st.dataframe(
            pairs_df.sort_values("Overlap", ascending=False),
            use_container_width=True, hide_index=True,
            column_config={"Overlap": st.column_config.NumberColumn(format="%.0f%%")},
        )

st.divider()

# --------------------------------------------------------------------------- #
# FOOTER DIDATTICO
# --------------------------------------------------------------------------- #
with st.expander("Methodology"):
    st.markdown(
        """
        **Look-through**: each ETF is decomposed into its holdings; sector,
        country and region weights are aggregated across funds, each weighted by
        its share of the portfolio. Cash and derivatives are excluded and the
        equity sleeve is renormalised.

        **Effective number (1 / HHI)**: the Herfindahl-Hirschman Index is the sum
        of squared weights. Its reciprocal reads as "how many equally-weighted
        categories would give the same concentration". Five effective sectors ≈
        as diversified as an equal split across five sectors.

        **Overlap coefficient**: Σ min(wᵢ) over shared categories. It measures how
        similar two funds are on a given dimension (sector/geography), not how
        many individual securities they share.

        **Coverage**: the share of the portfolio for which holdings are available.
        Below 100%, exposures are conditional on the covered funds.

        *Source: iShares / Vanguard published holdings.*
        """
    )
