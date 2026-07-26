# Portfolio Tracker

A multi-page analytics application for retail ETF investors following a
recurring-investment (PAC / dollar-cost-averaging) strategy. It turns a simple
Excel file of transactions into a full dashboard: performance, allocation,
costs and taxation, rebalancing suggestions, risk metrics and Monte Carlo
projections.

The project is deliberately built around **financial correctness** first and a
clean **engineering architecture** second — the two things a buy-side team
actually evaluates.

**▶️ Live demo:** `https://<your-app>.streamlit.app`
_No file required — click **"Prova con dati demo"** to explore a real
seven-year, three-ETF portfolio built from historical end-of-day prices._

> The user-facing app is in **Italian** by design: it models the Italian retail
> context (stamp duty / *imposta di bollo*, 26% capital-gains tax, Trade
> Republic conventions). This domain specificity is intentional, not an
> oversight.

---

## What it does

Nine pages, each backed by a standalone calculation module:

| Page | Question it answers |
|------|---------------------|
| **Holdings** | What do I own right now, at what cost and market value? |
| **Performance** | How have my instruments performed, independent of *when* I paid in? (TWR) |
| **Allocazione** | How is capital distributed across instruments vs. target? |
| **Andamento** | How has portfolio value evolved over time? |
| **Vs benchmark** | How do I compare against a chosen benchmark? |
| **Costi e fiscalità** | What am I paying in fees, stamp duty and TER, and what tax would I owe if I sold today? |
| **Ribilanciamento** | Where should my *next* contribution go to converge to target — without selling? |
| **Rischio** | Volatility, Sharpe, Sortino, max drawdown, beta. |
| **Monte Carlo** | Where could this PAC realistically end up over the long run? |

---

## Financial methodology

The choices below are the substance of the project.

- **Time-Weighted Return (TWR), GIPS-compliant, as the primary performance
  metric.** Daily sub-period returns are chained geometrically and cash flows
  are neutralised, so performance reflects the *instruments*, not the timing of
  contributions — the correct way to judge a strategy independently of when
  money went in.
- **Money-Weighted Return (IRR) reported alongside**, precisely to *measure*
  the effect of contribution timing. TWR and MWR answer different questions;
  the app shows both and explains the gap rather than collapsing them.
- **Cash-flow rebalancing, never selling.** Rebalancing is achieved by steering
  each new contribution toward the underweight sleeves (gap-closing), with a
  **2% deviation threshold** to avoid over-trading and a **single-order
  preference** when one buy suffices, to minimise fees. This mirrors how a
  disciplined retail PAC actually rebalances — no taxable events triggered.
- **Cost and tax modelling for the Italian retail context.** Stamp duty
  (*imposta di bollo*) is modelled daily *and* shown against the real charges
  reported by the broker; the TER is displayed as informational and **not**
  double-counted against P&L (it is already embedded in the fund NAV);
  capital-gains tax (26% on net realised gains) is simulated as an
  "if I sold today" figure.
- **Risk metrics:** annualised volatility, Sharpe and Sortino ratios, maximum
  drawdown, and beta vs. the benchmark.
- **Monte Carlo projections** for the long-horizon PAC.

**Methodological guardrails.** The app is explicit about traps that quietly
break naïve implementations: annualisation is flagged as misleading on short
windows; a coverage-aware price cache prevents accumulated positions from
"appearing" in a single day and producing a spurious vertical jump in the TWR
curve; and unadjusted close prices are used as cost basis (the price actually
paid), separate from dividend-adjusted valuation.

---

## Architecture

The codebase separates **calculation** from **presentation**:

- **Core modules are Streamlit-free** — `portfolio.py`, `costs.py`,
  `rebalance.py`, `risk.py`, `montecarlo.py`, `chart_style.py`. They take
  DataFrames in and return DataFrames/values out, with no UI dependency. This
  keeps the financial logic testable in isolation and API-ready (a FastAPI
  extraction is a planned v2).
- **A thin Streamlit layer** (`app.py`, `pages/`, `streamlit_utils.py`,
  `streamlit_components.py`, `plotly_style.py`) handles routing, state and
  rendering.

**Data flow.** Data enters via file upload (or the built-in demo) on the home
page; the raw workbook bytes live in `st.session_state`; a single cached loader
parses them once (`pd.ExcelFile` reused across sheet readers, so the core
modules stay untouched); prices are fetched from yfinance and memoised. Every
internal page reads from session state through one choke point, so no page ever
touches the filesystem.

**Price cache.** End-of-day prices are cached to Parquet with a per-ticker
**coverage map**: a ticker is re-downloaded not only when absent but also when
the cache does not reach back far enough for the requested start date. Without
this, a shared cache would serve a too-short history and corrupt long-horizon
returns.

**Design system.** A small custom SVG icon set (outline style, colour driven by
CSS so a single asset serves every state), a navy/slate palette, `tabular-nums`
for decimal alignment, and consistent Plotly/Matplotlib styling via shared
design tokens.

---

## Tech stack

Python · pandas · NumPy · SciPy · yfinance · Streamlit · Plotly · Matplotlib ·
openpyxl. Deployed on Streamlit Community Cloud.

---

## Running locally

```bash
git clone https://github.com/<user>/portfolio-tracker.git
cd portfolio-tracker
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens on the onboarding page. Either download the Excel template, fill
it and upload it, or click **"Prova con dati demo"** to explore immediately.

---

## Data model

The input is a single `.xlsx` workbook with four sheets:

- **`transactions`** — one row per buy/sell: `date, ticker, isin, name,
  operation, quantity, price, currency, fees` (+ optional `notes`).
- **`settings`** — base currency, benchmark ticker, and the target allocation.
- **`ter`** — annual TER per instrument (informational).
- **`bollo_charges`** — real stamp-duty charges from the broker (optional).

The template and the demo workbook are both generated in code
(`template.py`), so their structure never drifts from the loaders that validate
them.

---

## Project structure

```
portfolio-tracker/
├── app.py                 # entry point / onboarding + summary
├── pages/                 # the nine analytics pages
├── portfolio.py           # holdings, valuation, TWR, MWR, prices
├── costs.py               # fees, stamp duty, TER, capital-gains simulation
├── rebalance.py           # cash-flow rebalancing (gap-closing)
├── risk.py                # volatility, Sharpe, Sortino, drawdown, beta
├── montecarlo.py          # long-horizon projections
├── template.py            # in-memory Excel template + demo workbook
├── chart_style.py         # shared design tokens
├── plotly_style.py        # Plotly styling
├── streamlit_utils.py     # loaders, sidebar, data guard, price cache
├── streamlit_components.py# KPI cards, callouts
├── assets/icons/          # custom SVG icon set
└── requirements.txt
```

---

## Roadmap

- `tax.py` — loss carry-forward and tax-optimised switches.
- FastAPI extraction of the core modules (the Streamlit-free design already
  supports it).

---

## Notes

- This is a personal analytics tool, **not investment advice**.
- Uploaded data stays in the browser session and is not persisted server-side.
- Prices are end-of-day, sourced from Yahoo Finance via yfinance.

---

**Author:** Michele — [LinkedIn](https://www.linkedin.com/in/<your-handle>)
