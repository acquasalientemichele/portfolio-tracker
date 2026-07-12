# Portfolio Tracker — State

Ultimo aggiornamento: 12 luglio 2026

## Overview

Portfolio tracker personale per investimenti PAC in ETF (Trade Republic).
Sviluppato in Python + Streamlit come app locale multi-page, con
architettura pulita (moduli Python "puri" separati dalla UI).

**Portafoglio tracciato**: VWCE.DE (80%) + VFEA.DE (20%) via PAC mensile.

**Scopo**:
- Uso personale (tracking preciso di TWR, allocazione, rischio, tax
  simulation)


## Architettura

### Moduli Python puri (nessuna dipendenza da Streamlit)

- **`portfolio.py`** — Holdings, TWR (GIPS-compliant), MWR (IRR),
  value series, cash flow. Cache parquet per prezzi yfinance.
- **`costs.py`** — Commissioni, bollo modellato (0.2% annuo giornaliero),
  bollo reale da TR, cap gain tax simulation (26%), TER.
- **`rebalance.py`** — Cash-flow rebalancing, threshold 2%, single-buy
  preferito, gap-closing strategy, proiezione convergenza.
- **`risk.py`** — Volatilità, Sharpe, Sortino, beta vs benchmark, max
  drawdown, top-N drawdown analysis, confidence level, interpretazione
  testuale.
- **`montecarlo.py`** — Simulazione probabilistica PAC (10k×20 anni),
  calibrazione da storia recente, quantili per orizzonte, probabilità
  di superare obiettivo, interpretazione dinamica.

### Moduli grafici

- **`chart_style.py`** — Palette + apply_global_style + style_axis +
  add_title. Usato dai notebook Jupyter e da Streamlit per grafici
  statici (donut Allocazione, bar deviation, waterfall Costi).
- **`plotly_style.py`** — Analogo Plotly per grafici interattivi.
  Palette importata da chart_style (single source of truth).
  Usato per Performance, Andamento, Vs Benchmark, Rischio drawdown,
  Monte Carlo fan chart.

### Layer Streamlit

- **`streamlit_utils.py`** — Cached loaders (`load_tx`, `load_settings`,
  `fetch_prices`), `ensure_data_loaded()`, `render_sidebar()`, e
  `inject_css()` con 8 blocchi CSS (chrome, typography, sidebar polish,
  brand+nav custom, KPI cards, callout).
- **`streamlit_components.py`** — Componenti HTML custom: `kpi_card()`
  con tooltip cliccabili + altezze uniformi garantite, `callout()`
  stile FT/Bloomberg con 4 kind semantici.

### Pagine

9 pagine multi-page in `pages/`:
1. Holdings (posizioni + P&L per ticker)
2. Performance (TWR/MWR/spread + cash flow)
3. Allocazione (pesi vs target + threshold check)
4. Andamento (valore portafoglio vs capitale investito)
5. Vs Benchmark (TWR vs VWCE.DE)
6. Costi e fiscalità (P&L → netto netto waterfall)
7. Ribilanciamento (suggerimento PAC + proiezione convergenza)
8. Rischio (volatilità, Sharpe, Sortino, beta, MaxDD)
9. Monte Carlo (proiezione probabilistica PAC)

## Stack tecnico

- **Python**: 3.11+
- **UI**: streamlit ≥ 1.50
- **Grafici**: matplotlib (statici) + plotly ≥ 5.20 (interattivi)
- **Dati**: pandas, numpy, scipy
- **Prezzi**: yfinance (EOD), cache parquet locale
- **Broker**: Trade Republic (frazioni libere, 1€/ordine)
- **File input**: Excel (`data/transactions.xlsx`) con fogli
  `transactions`, `settings`, `bollo_charges`, `ter`

## Convenzioni di sviluppo

- **Formato numeri**: US style `1,000.00` ovunque (in vista di
  migrazione UI a inglese per candidature Monaco)
- **UI**: italiano attualmente, migrazione EN pianificata
- **Docstring**: verbose italiano, contract-based, con esempi
- **Design system UI**: navy #0F4C81 (primary), slate #94A3B8, amber
  #D97706, gain #10B981, loss #EF4444, violet #7C3AED, white #FFFFFF
- **Font**: Inter globale + JetBrains Mono per valori KPI (tabular-nums
  per allineamento decimali)
- **Session state**: solo dati grezzi (tx, prices, settings, prices_last_date)
- **Cache**: `@st.cache_data` per loaders, cache parquet in
  `portfolio.fetch_prices()`

## Stato del progetto

### Completato ✅

**Core financial logic**
- portfolio.py, costs.py, rebalance.py, risk.py, montecarlo.py
- Tutti con test manuale nel notebook, TWR verificato GIPS-compliant

**Design system UI**
- config.toml + palette + Google Fonts
- inject_css con 8 blocchi CSS
- streamlit_components.py: kpi_card + callout
- 9 pagine migrate: 45 kpi_card + 27 callout
- Altezze uniformi garantite, tooltip cliccabili (mobile + tastiera)
- Callout stile FT/Bloomberg con 4 kind semantici

**Grafici interattivi**
- plotly_style.py: 5 funzioni pubbliche + PLOTLY_CONFIG
- 5 grafici migrati a Plotly con hover unified, zoom, download PNG:
  - Performance TWR cumulato
  - Andamento portfolio performance (tick speciali sull'asse Y)
  - Vs Benchmark portfolio vs benchmark
  - Rischio drawdown underwater
  - Monte Carlo fan chart (hover con distribuzione completa)
- 3 grafici restano matplotlib per scelta strategica:
  - Allocazione donut (label anti-collision migliore)
  - Costi waterfall (personalizzazione ricca già ottima)
  - Allocazione bar deviation (già ben curato)

**Extra emersi durante lo sviluppo**
- Fix del pulsante "Ricarica dati" (bug cache parquet)
- Popover parametri avanzati Ribilanciamento (allineamento con input)
- Format numeri US con thousand separator nelle tabelle
- Pattern callout con kind dinamico su threshold (Monte Carlo, Performance)

### In corso 🔄

Nessun blocco in corso — momento di consolidamento.

### Prossimi step (roadmap)

**Deploy preparation** (priorità alta se vuoi condividere l'app)
- Modalità demo con dati sintetici (per non esporre le tue transazioni reali)
- Home.py come entry point per st.navigation multi-page
- Deploy su Streamlit Community Cloud
- Template Excel scaricabile per utenti non tecnici

**Documentazione**
- README con overview, motivazioni, decisioni tecniche
- Screenshot delle pagine principali
- Integrazione nel CV con link al repo

**Migrazione UI a inglese** (priorità media, per Monaco)
- Traduzione delle stringhe visibili all'utente
- Nomi delle pagine, callout, KPI label
- Codice interno resta in italiano (docstring)

**Feature future** (backlog)
- Pagina Tax Optimizer (minusvalenze, switch ottimizzati)
- Icon set custom nella sidebar (SVG generati con Claude Design)
- Multi-portafoglio (se decidi di tracciare più account)

## Decisioni chiave e loro rationale

**TWR come metrica primaria di performance**
GIPS-compliant, indipendente dal timing dei versamenti. È lo standard
industry. MWR (IRR) mostrato come complementare per catturare l'effetto
del timing dei versamenti.

**Cash-flow rebalancing senza vendita**
Threshold 2%: sotto, non vale il costo di un secondo ordine (commissione
TR 1€ + drag fiscale del 26% su vendite). Single-buy preferito quando
possibile per risparmio fees.

**TER non sottratto dal P&L**
È già scontato nel NAV giornaliero degli ETF (per accumulating come
VWCE/VFEA). Sottrarlo sarebbe double counting. Mostrato come informativo.

**Cap gain tax simulata**
"Se vendessi oggi": 26% su plusvalenza netta (minus di una posizione
compensa plus di un'altra). Non sottratta dal P&L reale (le tasse si
pagano solo alla vendita).

**Bollo modellato + reale mostrati entrambi**
Il modellato (0.2% annuo giornaliero) è deterministico e prevedibile;
il reale (da Trade Republic, opzionale foglio Excel) fa da controllo.

**Coesistenza matplotlib + Plotly**
Approccio pragmatico: Plotly dove l'interattività aggiunge valore
(serie temporali, distribuzione probabilistica), matplotlib dove è
già ottimo (illustrazioni statiche). Un solo sistema sarebbe stato
più elegante ma con costi realistici (waterfall e donut peggiorano
in Plotly).

**Formato numeri US mantenuto**
`1,000.00` in tutta l'app, in vista di migrazione UI a inglese per
candidature Monaco. Evita rework futuro.

## Learning key dal progetto

- **Streamlit model**: script re-execution completo ad ogni interazione.
  Session state per dati grezzi, calcoli derivati sempre freshi.
  Latenza cross-page ~0.5-1s accettata come vincolo strutturale.
- **`@st.cache_data`**: richiede argomenti hashable (tuple, non list).
- **NumberColumn format**: sprintf-js, supporta `%,` per thousand
  separator, ma prefix `€` prima di `%` non funziona (usare suffix).
  `st.number_input` invece NON supporta `%,` (limite Streamlit noto).
- **Plotly nel fintech**: la vera killer feature è hover unified. Su
  serie multiple (portafoglio vs benchmark, percentili Monte Carlo)
  cambia sostanzialmente l'esperienza di lettura.
- **Design system minimale**: 2 componenti (kpi_card + callout) coprono
  95% dei bisogni UI. Aggiungere più componenti sarebbe over-engineering.
