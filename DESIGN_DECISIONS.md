# Design Decisions — Portfolio Tracker

Documento vivo che raccoglie le decisioni di design importanti del progetto,
con il **ragionamento** dietro a ciascuna. Serve a:
- Non dimenticare il *perché* delle scelte fatte
- Documentare il pensiero per colloqui e portfolio piece
- Permettere a chiunque (incluso un altro Claude) di proseguire il lavoro
  con coerenza

---

## 1. Architettura generale

### Separazione `core/` vs presentation
**Decisione**: tutta la logica vive in moduli `.py` puri (`portfolio.py`,
`costs.py`, `rebalance.py`, `risk.py`); il notebook è solo l'orchestratore
che importa funzioni e produce visualizzazioni.

**Perché**: 
- Permette di riusare la logica in contesti diversi (notebook oggi,
  Streamlit domani) senza riscriverla
- Le funzioni sono testabili indipendentemente
- Evita il classico anti-pattern "notebook spaghetti" dove la stessa
  logica viene rifatta inline in più celle

### Excel come fonte dati iniziale (poi SQLite, poi DB)
**Decisione**: nella v1, le transazioni vivono in `transactions.xlsx`.
Step successivi: SQLite quando passeremo a Streamlit; PostgreSQL solo
se mai diventerà multi-utente serio.

**Perché**:
- Excel è familiare per l'investitore retail, zero curva di apprendimento
- SQLite copre 99% dei casi sotto i 100 utenti, niente server da gestire
- Postgres è over-engineering finché non serve davvero

---

## 2. Performance

### TWR come metrica primaria (GIPS-compliant)
**Decisione**: la performance principale del portafoglio è misurata col
Time-Weighted Return giornaliero, formula GIPS:
```
r_t = (V_t - F_t) / V_{t-1} - 1
TWR_cum = ∏(1 + r_t)
```

**Perché**:
- Standard internazionale per misurare la performance al netto del timing
  dei flussi (GIPS = Global Investment Performance Standards, CFA Institute)
- Confrontabile con benchmark anche per portafogli che ricevono versamenti
  periodici come un PAC

### MWR (IRR) come metrica complementare
**Decisione**: oltre al TWR, calcoliamo il Money-Weighted Return risolvendo
l'IRR sui flussi di cassa. Risolto numericamente con `scipy.optimize.brentq`.

**Perché**:
- TWR misura la performance degli strumenti, MWR misura il rendimento
  effettivo dell'investitore considerando *quando* ha versato
- Lo spread MWR - TWR è informazione preziosa: positivo = timing
  vantaggioso, negativo = timing svantaggioso
- Per un investitore PAC retail è particolarmente rilevante (CFA L2)

### Annualizzazione su periodi brevi con caveat
**Decisione**: `money_weighted_return()` restituisce `is_short_period=True`
se i giorni di storia sono < 365. L'interpretazione testuale aggiunge un
warning esplicito.

**Perché**:
- Annualizzare un rendimento di pochi mesi sovrastima drammaticamente la
  performance attesa (effetto del compounding)
- Vendere precisione non supportata dai dati è disonesto

---

## 3. Costi e fiscalità

### Bollo modellato giornalmente + bollo reale da TR
**Decisione**: il modulo `costs.py` calcola il bollo giornaliero come
`valore_corrente × 0.20% / 365`, sommato cumulativamente. L'utente può
inserire anche gli addebiti reali da TR nel foglio `bollo_charges`. I
due numeri vengono mostrati affiancati.

**Perché**:
- Il modello dà visibilità continua del drag, anche tra un addebito e
  l'altro
- Confrontarlo col reale verifica l'accuratezza del modello
- Trasparenza totale all'utente

### TER NON sottratto dal P&L
**Decisione**: il TER (Total Expense Ratio) viene **mostrato come
informativo** ma non viene sottratto dal P&L o dal rendimento.

**Perché**:
- Per ETF accumulating come VWCE/VFEA il TER è già scontato dal NAV
  giornalmente
- I prezzi yfinance riflettono già il NAV post-TER
- Sottrarlo nuovamente sarebbe double counting
- Mostrarlo separatamente educa l'utente su un costo invisibile

### Cap gain tax: 26% su plusvalenza netta, simulazione "se vendessi oggi"
**Decisione**: simuliamo la tax solo se l'utente liquidasse oggi.
Le minusvalenze di una posizione compensano le plusvalenze di un'altra
in caso di liquidazione simultanea (regola ETF armonizzati italiani).
Se il netto è negativo, tax = 0.

**Perché**:
- Onestà concettuale: la tax è ipotetica finché non vendi
- Per ETF armonizzati la regola fiscale italiana permette compensazione
- Trattare le minusvalenze come "scartate" sarebbe sbagliato

### P&L cascade in EUR (non in %)
**Decisione**: la tabella di riepilogo costi presenta un waterfall in
**valori monetari**: P&L lordo → −commissioni → −bollo → −tasse → P&L
netto netto.

**Perché**:
- I costi sono pagamenti reali in euro, non percentuali
- TWR (%) e P&L (€) misurano cose diverse: il primo serve per confronti
  vs benchmark, il secondo per dire "quanti soldi ho fatto"
- Il waterfall mostra dove va ogni euro del guadagno lordo

---

## 4. Ribilanciamento

### Cash-flow rebalancing only (no vendita)
**Decisione**: il modulo `rebalance.py` propone *solo* acquisti, mai
vendite. Riequilibra il portafoglio sfruttando il nuovo cash del PAC.

**Perché**:
- Per ETF armonizzati italiani, vendere realizza plusvalenze tassate al 26%
- Il tax drag rende il classico "sell-high/buy-low" sub-ottimale per retail
- Il PAC mensile fornisce naturalmente flussi per auto-correggere il drift
- Filosoficamente più "etico" verso il cliente: meno transazioni, meno tax

### Single-buy preferito quando possibile
**Decisione**: l'algoritmo prova prima un single-buy (1 ordine, 1 commissione).
Lo split su 2 ETF avviene solo se:
1. La deviazione post-single-buy supera il threshold (default 2%), E
2. Esiste un secondo ticker davvero sottopesato

**Perché**:
- Commissione TR ~1€ per ordine vale 0.2% di drag su 500€ di PAC
  (più del bollo annuo!)
- Se la deviazione si chiude col solo primary, lo split è uno spreco
- Non ha senso fare split su un ticker che è già sovra-pesato

### Threshold 2% (configurabile)
**Decisione**: deviazioni sotto 2% vengono accettate (no split).

**Perché**:
- Su un orizzonte lungo, 1-2% di drift è rumore, non segnale
- Evita over-trading psicologico (uno dei principali errori del retail)
- Il PAC successivo correggerà naturalmente

### `cash_to_invest` = netto investito (fees aggiuntive)
**Decisione**: il parametro `new_cash` del modulo `rebalance.py`
rappresenta l'importo *netto* investito in ETF. Le commissioni sono
*aggiuntive* sul totale uscito dal conto.

**Perché**:
- Coerente con la mental model dell'investitore: "voglio investire 1000€"
  significa 1000€ in ETF + fee a parte
- Più trasparente nel reporting: "totale uscito dal conto = X + fees"

### Frazioni libere (Trade Republic style)
**Decisione**: il modulo permette quantità frazionarie (es. 3.85 quote
di VWCE).

**Perché**:
- TR le permette nativamente
- Niente cash residuo non investito (efficienza)
- Configurabile per supportare broker più "tradizionali" in futuro

### Proiezione di convergenza
**Decisione**: `project_convergence()` simula PAC futuri assumendo prezzi
costanti e stima i mesi necessari per tornare entro 0.5% dal target.

**Perché**:
- Visibilità sulla velocità di auto-correzione del PAC
- Educativo: l'utente vede che il drift si chiude naturalmente in
  pochi mesi senza ribilanciamenti attivi
- Caveat metodologico: assume prezzi costanti, in pratica i prezzi si
  muovono. Per fedeltà alle dinamiche reali → Monte Carlo (futuro).

---

## 5. Risk metrics

### 252 trading days per annualizzazione (non 365)
**Decisione**: tutte le metriche annualizzate usano 252 giorni di trading,
non 365 giorni di calendario.

**Perché**:
- Standard finanziario: solo i giorni di mercato contribuiscono alla vol
- Usare 365 sovrastima la vol annuale di ~21%
- Errore comune nei tool retail amatoriali

### Drawdown su TWR cumulato, NON su valore di mercato
**Decisione**: max drawdown e top-N drawdowns calcolati sulla serie TWR
cumulata, mai sul valore di mercato.

**Perché**:
- In un portafoglio con flussi, i versamenti mascherano i drawdown reali
- Esempio: il mercato fa -3% ma tu versi 500€ → il valore di mercato
  cresce, sembra non ci sia drawdown. Sbagliato.
- Il TWR depurato dai flussi cattura correttamente il calo

### Confidence flag a 4 livelli
**Decisione**: ogni metrica include un flag di affidabilità basato sulla
lunghezza della serie:
- `VERY_LOW`: < 6 mesi (~126 giorni)
- `LOW`: < 1 anno (~252 giorni)
- `MEDIUM`: < 3 anni (~756 giorni)
- `HIGH`: ≥ 3 anni

**Perché**:
- Su 6 mesi lo Sharpe è dominato dal rumore (errore standard ~5%)
- Mostrare uno Sharpe come "+1.8" su una serie di 7 mesi è disonesto
- Il flag invita prudenza interpretativa senza nascondere il numero

### Risk-free rate: BTP 3y configurabile
**Decisione**: default 3.0% (BTP 3y giugno 2026), configurabile dal notebook.

**Perché**:
- Proxy realistico per un investitore retail italiano
- T-Bill USA sarebbe culturalmente fuori contesto
- Configurabilità permette analisi di sensitività

### 5 metriche v1, non di più
**Decisione**: in v1 includiamo: volatilità annualizzata, Sharpe, Sortino,
max drawdown analysis, beta vs benchmark. Più: top-N drawdowns (default 3).

**Esclusi** (con motivazione):
- **VaR parametrico**: assume distribuzione gaussiana (falsa in finanza),
  sottostima sistematicamente le code estreme. Fuorviante per retail.
- **Tracking error**: poco interessante per portafoglio quasi-replicante
  del benchmark
- **Information ratio**: per gestori attivi, non per passive PAC retail
- **Calmar ratio**: elegante ma instabile, poco usata in pratica

### Threshold 0.5% per top drawdowns
**Decisione**: drawdowns sotto 0.5% sono ignorati nella top-N.

**Perché**:
- Sotto 0.5% è rumore giornaliero, non eventi significativi
- I "top 3" devono essere drawdown veri, non micro-oscillazioni

### Beta obbligatorio (benchmark sempre richiesto)
**Decisione**: la funzione `risk_summary()` richiede sempre il benchmark.

**Perché**:
- Forza l'utente a pensare al contesto di riferimento
- Riduce codepath alternativi, design più solido
- In Python: parametro obbligatorio = "pensaci"

---

## 6. Stile grafico

### Linguaggio visivo Bloomberg/FT
**Decisione**: tutti i grafici seguono un'estetica unificata definita
in `chart_style.py`:
- Sfondo chiaro, tipografia sans-serif (Helvetica)
- Spine top/right rimossi, griglia solo orizzontale
- Titolo bold + sottotitolo con KPI (headline style)
- Footer con fonte e data
- Palette finanziaria sobria (navy, viola, arancio bruciato)
- End-of-line annotations sui valori correnti

**Perché**:
- Coerenza visiva tra tutti i grafici della dashboard
- Aspetto "report di studio" vs "esperimento da studente"
- Riusabile: un singolo cambio in `chart_style.py` si propaga ovunque

---

## 7. Convenzioni terminologiche

### "Modulo" vs "Funzionalità"
- **Modulo** = file `.py` (es. `portfolio.py`, `costs.py`, `rebalance.py`)
- **Funzionalità** = quello che vede l'utente nel notebook (cella + grafico)

Es: "il modulo rebalance esiste, ma la funzionalità ribilanciamento PAC
non era ancora stata aggiunta nella sezione 10 del notebook."

### Lingua
- Codice e docstring in italiano (utenti target)
- Messaggi commit Git in inglese (convenzione internazionale)
- Nomi variabili e funzioni in inglese (convenzione Python)

---

## 8. Workflow di sviluppo

### GitHub Desktop + VS Code
**Decisione**: editing del codice in VS Code, version control via GitHub
Desktop (no terminale Git nella v1).

**Perché**:
- VS Code è lo standard de facto, perfetto per Python
- GitHub Desktop è grafico e abbatte la curva di apprendimento Git
- Si può passare al terminale Git in seguito senza perdere niente

### Repo privato fino a "presentable"
**Decisione**: repository GitHub privato durante lo sviluppo, pubblico
solo quando avrà:
- 4-5 funzionalità complete
- README curato con screenshot
- Template + sample Excel
- Disclaimer + License
- Eventualmente test base

**Perché**:
- Evita di mostrare uno work-in-progress
- Quando esce pubblico, deve fare buona impressione (CV)
- Privato non significa solo "io": si possono aggiungere collaboratori
  per i tester

### Modifiche incrementali, non sostituzione file
**Decisione**: per modificare moduli esistenti, indicare al utente *dove*
e *cosa* modificare, non riconsegnare il file intero.

**Perché**:
- L'utente legge il codice e impara
- Diff Git informativi (mostrano cosa cambia davvero)
- Niente rischio di sovrascrivere modifiche personali

**Eccezione**: file nuovi (es. la prima volta di `risk.py`) vanno
consegnati interi e copiati in cartella.

---

## 9. Cosa esplicitamente NON fare

Decisioni di "non fare" altrettanto importanti di quelle di fare:

- **No ML/AI per forecasting prezzi**: rumore travestito da segnale,
  rischio reputazionale in colloqui seri
- **No live/intraday data**: irrilevante per PAC retail, complica
- **No multi-currency con cambio storico**: overkill per portafoglio EUR
- **No import automatico da PDF di TR**: API privata, fragile, perdita
  di tempo. Excel manuale resta la fonte primaria.
- **No microservizi/architetture "scalabili"**: 5 utenti, KISS.
- **No PostgreSQL prima del tempo**: SQLite copre tutto.

---

## 10. Roadmap

### ✅ Completato
- `portfolio.py`: load, holdings, TWR, MWR
- `costs.py`: bollo, TER, cap gain, cost summary
- `rebalance.py`: gap-closing, convergence projection
- `chart_style.py`: Bloomberg/FT style coerente
- Notebook con 10 sezioni complete
- Repo GitHub (privato)

### 🔄 In corso
- `risk.py`: 5 metriche + top drawdowns + confidence flags

### ⏳ Prossimi step
- `montecarlo.py`: simulazioni PAC lungo periodo (bootstrap dai rendimenti)
- `tax.py`: simulazione fiscale italiana (minusvalenze, switch ottimizzati)
- Streamlit web app (dopo che i moduli core sono maturi)
- Test pytest sul core
- README pubblicabile + screenshot
- Eventuale rendering pubblico del repo
