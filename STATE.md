# Stato attuale — Portfolio Tracker

**Ultimo aggiornamento**: 13 giugno 2026
**Autore**: Michele Acquasaliente
**Stack**: Python 3.11+ / Jupyter Notebook / GitHub Desktop / VS Code / Mac

---

## Cosa funziona oggi

### Moduli core (cartella `portfolio-tracker/`)

| Modulo | Funzioni principali | Status |
|---|---|---|
| `portfolio.py` | load_transactions, load_settings, fetch_prices, compute_holdings, value_holdings, portfolio_value_series, time_weighted_return, money_weighted_return, compare_twr_mwr, summary | ✅ Stabile |
| `costs.py` | load_costs, bollo_cumulative, bollo_by_quarter, cap_gain_tax, value_series_net_of_bollo, cost_summary | ✅ Stabile |
| `rebalance.py` | suggest_rebalance (gap-closing), project_convergence | ✅ Stabile |
| `chart_style.py` | apply_global_style, style_axis, add_title, style_legend, COLORS, PALETTE | ✅ Stabile |
| `add_costs_sheets.py` | Helper one-shot per aggiungere fogli `ter` e `bollo_charges` al file Excel | ✅ Stabile |
| `risk.py` | *Da creare in questa sessione* | 🔄 In corso |

### Funzionalità nel notebook `portfolio.ipynb`

| Sezione | Cosa fa | Status |
|---|---|---|
| 1. Setup | Import moduli, parametri globali | ✅ |
| 2. Caricamento operazioni e settings | Da Excel | ✅ |
| 3. Download prezzi | yfinance + cache parquet | ✅ |
| 4. Holdings | Costo medio ponderato, P&L per posizione | ✅ |
| 5. Performance complessiva | P&L cash + TWR + MWR + interpretazione timing | ✅ |
| 6. Allocazione | Donut + bar chart vs target + chip scostamento | ✅ |
| 7. Andamento del valore | Linea valore + capitale investito con marker end-of-line | ✅ |
| 8. Performance vs Benchmark | TWR lordo + netto bollo + benchmark | ✅ |
| 9. Costi e fiscalità | Riepilogo + waterfall lordo→netto netto | ✅ |
| 10. Ribilanciamento PAC | Suggerimento ordini + grafico proiezione convergenza | ✅ |
| 11. Rischio | *Da aggiungere in questa sessione* | 🔄 |

---

## Dati del portafoglio reale (Michele)

- **Broker**: Trade Republic
- **ETF**: VWCE.DE (IE00BK5BQT80, FTSE All-World Acc, ~78%) + VFEA.DE (IE00BK5BR733, FTSE Emerging Acc, ~22%)
- **Target allocation**: 80% / 20%
- **Storia**: ~7 mesi di PAC mensile da novembre 2025
- **Valuta base**: EUR
- **Benchmark in dashboard**: VWCE.DE stesso

---

## Decisioni di design già prese

Vedi `DESIGN_DECISIONS.md` per il dettaglio completo. Riassunto:

- **TWR + MWR** come metriche di performance complementari
- **Cash-flow rebalancing only**, threshold 2%, single-buy preferito
- **`cash_to_invest` = netto investito**, fees aggiuntive
- **Bollo modellato + bollo reale** affiancati
- **TER non sottratto** (già nel NAV)
- **Cap gain tax** simulata "se vendessi oggi", 26% su plusvalenza netta
- **Stile Bloomberg/FT** unificato (`chart_style.py`)
- **252 trading days** per annualizzazione (non 365)
- **4 confidence levels** per le risk metrics (VERY_LOW/LOW/MEDIUM/HIGH)
- **Risk-free rate default**: BTP 3y (3.0%), configurabile
- **Top drawdowns** filtrati a 0.5% minimum

---

## Stato Git

- **Repo**: privato su GitHub
- **Branch unico**: `main`
- **Commit recenti** (in ordine cronologico inverso):
  - `Add invested capital end label to portfolio value chart`
  - `Change rebalance cash semantics from gross to net`
  - `Add PAC rebalancing feature with convergence projection`
  - `Add Money-Weighted Return (MWR) with TWR comparison`
  - `Add rebalance module with gap-closing strategy`
  - `Initial commit: portfolio tracker MVP`

---

## Prossimi step pianificati

### Immediato (questa sessione)
- ✅ Creare `DESIGN_DECISIONS.md`
- ✅ Creare `STATE.md` (questo file)
- 🔄 Creare modulo `risk.py` con 5 metriche + drawdown analysis
- ⏳ Aggiungere sezione 11 al notebook (testuali + drawdown chart + top drawdowns table)

### Breve termine
- `montecarlo.py`: simulazioni PAC su 20+ anni con bootstrap dai rendimenti storici, percentili 10/50/90
- `tax.py`: tracking minusvalenze pregresse (scadenza 4 anni), suggerimenti switch ETF equivalenti con tax drag

### Medio termine
- Migrazione a Streamlit (app web personale)
- SQLite invece di Excel
- Test pytest sui moduli core
- README pubblicabile + screenshot

### Lungo termine
- Pubblicazione repo (passaggio a public)
- Eventuale condivisione con amici tester
- Possibile portfolio piece per candidature finance/quant a Monaco

---

## Note per future sessioni Claude

- Quando si lavora su un nuovo modulo: design first (perché, come, alternative,
  test con dati sintetici), poi codice
- Le modifiche a moduli esistenti si fanno **puntuali** (l'utente edita in VS
  Code, non si sostituiscono file interi)
- I file nuovi si consegnano interi e si copiano in cartella
- Sempre aggiornare `STATE.md` quando si aggiunge una feature significativa
- Commit Git in inglese, messaggi descrittivi
- Tutti i messaggi all'utente in italiano
