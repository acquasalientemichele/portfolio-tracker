"""
costs.py — gestione costi del portafoglio: commissioni, bollo, TER, fiscalità.

Separato da portfolio.py per chiarezza: portfolio.py tratta la performance,
costs.py tratta il "drag" sui rendimenti causato da costi e tasse.

Costi modellati:
- Commissioni di esecuzione: già nella colonna 'fees' del file transactions
- Bollo titoli (0.20% annuo): modellato giornalmente + reale da TR
- TER (Total Expense Ratio): solo informativo (già scontato nel NAV)
- Imposta plusvalenze (26%): solo in caso di liquidazione

Riferimenti normativi:
- Bollo titoli: DL 201/2011 art.19, comma 1 (aliquota 0.20% annuo)
- Cap gain ETF armonizzati: redditi diversi, imposta sostitutiva 26%
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

# Costanti regolatorie italiane
ITALIAN_BOLLO_RATE = 0.0020       # 0.20% annuo
ITALIAN_CAP_GAIN_RATE = 0.26      # 26% imposta sostitutiva
YEAR_DAYS = 365                   # convenzione bollo


# --------------------------------------------------------------------------- #
# 1. CARICAMENTO CONFIGURAZIONE COSTI
# --------------------------------------------------------------------------- #
def load_costs(path: str | Path) -> dict:
    """Carica TER per ticker e addebiti bollo reali dal file Excel.

    Si aspetta due fogli opzionali:
      - 'ter'          : ticker | ter_annual | note
      - 'bollo_charges': date   | amount     | notes

    Se un foglio non esiste, restituisce strutture vuote (graceful).
    """
    # TER
    ter_map = {}
    try:
        ter_df = pd.read_excel(path, sheet_name='ter')
        ter_df = ter_df.dropna(subset=['ticker', 'ter_annual'])
        for _, row in ter_df.iterrows():
            try:
                ter_map[str(row['ticker']).strip()] = float(row['ter_annual'])
            except (ValueError, TypeError):
                pass
    except Exception:
        pass

    # Bollo reale
    try:
        bollo = pd.read_excel(path, sheet_name='bollo_charges',
                              parse_dates=['date'])
        bollo = bollo.dropna(subset=['date', 'amount']).copy()
        bollo['amount'] = pd.to_numeric(bollo['amount'], errors='coerce')
        bollo = bollo.dropna(subset=['amount']).reset_index(drop=True)
    except Exception:
        bollo = pd.DataFrame(columns=['date', 'amount', 'notes'])

    return {'ter': ter_map, 'bollo_real': bollo}


# --------------------------------------------------------------------------- #
# 2. BOLLO MODELLATO
# --------------------------------------------------------------------------- #
def bollo_daily_accrual(value_series: pd.Series,
                        rate: float = ITALIAN_BOLLO_RATE) -> pd.Series:
    """Accrual giornaliero del bollo = valore × aliquota / 365.

    Approccio coerente con la prassi di TR: il bollo annuo si distribuisce
    pro-rata sul valore giornaliero del portafoglio.
    """
    return value_series * rate / YEAR_DAYS


def bollo_cumulative(value_series: pd.Series,
                     rate: float = ITALIAN_BOLLO_RATE) -> pd.Series:
    """Bollo accumulato dal modello, giorno per giorno."""
    return bollo_daily_accrual(value_series, rate).cumsum()


def bollo_by_quarter(value_series: pd.Series,
                     rate: float = ITALIAN_BOLLO_RATE) -> pd.DataFrame:
    """Bollo modellato aggregato per trimestre solare (Q1, Q2, ...).

    Restituisce DataFrame con colonne: period_end, bollo, avg_value.
    """
    daily = bollo_daily_accrual(value_series, rate)
    bollo_q = daily.groupby(pd.Grouper(freq='QE')).sum()
    avg_q   = value_series.groupby(pd.Grouper(freq='QE')).mean()
    out = pd.DataFrame({'bollo': bollo_q, 'avg_value': avg_q})
    out.index.name = 'period_end'
    return out.reset_index()


# --------------------------------------------------------------------------- #
# 3. IMPOSTA PLUSVALENZA (simulazione "se vendessi oggi")
# --------------------------------------------------------------------------- #
def cap_gain_tax(holdings_valued: pd.DataFrame,
                 rate: float = ITALIAN_CAP_GAIN_RATE) -> float:
    """Imposta stimata sul guadagno netto se si liquidasse l'intero portafoglio.

    Per ETF armonizzati: 26% sulla plusvalenza netta totale (le minusvalenze
    di una posizione compensano le plusvalenze di un'altra in caso di
    liquidazione simultanea). Se il netto è negativo, imposta = 0 (genera
    minusvalenza compensabile, non gestita qui).
    """
    net_gain = (holdings_valued['market_value']
                - holdings_valued['invested']).sum()
    return max(0.0, float(net_gain)) * rate


# --------------------------------------------------------------------------- #
# 4. TWR NETTO BOLLO (per il grafico lordo vs netto)
# --------------------------------------------------------------------------- #
def value_series_net_of_bollo(vs: pd.DataFrame,
                              rate: float = ITALIAN_BOLLO_RATE) -> pd.DataFrame:
    """Restituisce una copia del value series con il valore al netto del
    bollo cumulato giorno per giorno.
    Il vettore dei flussi resta invariato."""
    bollo_cum = bollo_cumulative(vs['value'], rate)
    vs_net = vs.copy()
    vs_net['value'] = vs['value'] - bollo_cum
    return vs_net


# --------------------------------------------------------------------------- #
# 5. RIEPILOGO COMPLETO
# --------------------------------------------------------------------------- #
def cost_summary(tx: pd.DataFrame,
                 holdings_valued: pd.DataFrame,
                 vs: pd.DataFrame,
                 costs: dict) -> dict:
    """Aggrega tutti i costi e il P&L netto netto.

    Conviene leggerla come una cascata:
      P&L lordo
       − Commissioni                (cash effettivo)
       − Bollo modello              (cash effettivo, stimato)
       − Imposta plusvalenze        (virtuale, solo se vendi)
       = P&L netto netto
    """
    invested = float(holdings_valued['invested'].sum())
    mv       = float(holdings_valued['market_value'].sum())
    pnl_lordo = mv - invested

    fees_total = float(tx['fees'].sum())
    bollo_model = float(bollo_cumulative(vs['value']).iloc[-1])
    bollo_real  = (float(costs['bollo_real']['amount'].sum())
                   if len(costs['bollo_real']) else 0.0)

    # TER pesato sul valore corrente (informativo, NON viene sottratto)
    weights = holdings_valued['weight']
    ter_weighted = sum(weights.get(t, 0) * costs['ter'].get(t, 0)
                       for t in weights.index)
    ter_annual_eur = ter_weighted * mv

    tax = cap_gain_tax(holdings_valued)
    cash_costs = fees_total + bollo_model
    pnl_nn = pnl_lordo - cash_costs - tax

    return {
        # base
        'invested':         invested,
        'market_value':     mv,
        # P&L
        'pnl_lordo':        pnl_lordo,
        'pnl_lordo_pct':    pnl_lordo / invested if invested else 0.0,
        'pnl_net_net':      pnl_nn,
        'pnl_net_net_pct':  pnl_nn / invested if invested else 0.0,
        # componenti
        'fees_total':       fees_total,
        'bollo_model':      bollo_model,
        'bollo_real':       bollo_real,
        'cash_costs':       cash_costs,
        'cap_gain_tax':     tax,
        # informativo
        'ter_weighted':     ter_weighted,
        'ter_annual_eur':   ter_annual_eur,
    }
