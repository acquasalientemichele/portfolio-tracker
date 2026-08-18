"""
montecarlo.py — Monte Carlo per pianificazione PAC di lungo periodo.

Filosofia di design (vedi DESIGN_DECISIONS.md per dettaglio):

1. HISTORICAL BOOTSTRAP NON-PARAMETRICO (no assunzione gaussiana).
   Campioniamo direttamente dalla distribuzione empirica dei rendimenti
   storici. Preserva code grasse, asimmetria e leptocurtosi reali del
   mercato, che il classico Geometric Brownian Motion (gaussiano)
   sottostima sistematicamente.

2. ARCHITETTURA "FUTURE-PROOF" PER MULTI-ASSET.
   La calibrazione è separata dal motore di simulazione (seam pattern).
   v1: calibrate_returns_aggregated() costruisce un portafoglio sintetico
       come combinazione pesata dei rendimenti storici.
   v2 futura: calibrate_returns_multivariate() simulerà rendimenti
       correlati per asset poco correlati (es. azioni + obbligazioni).
   Il motore run_pac_simulation() è agnostico al metodo di calibrazione.

3. SIMULAZIONE DEL PAC, non solo dell'evoluzione dei prezzi.
   Ad ogni mese aggiungiamo i versamenti, ricalcoliamo il valore con i
   rendimenti del periodo. Output: distribuzione del valore finale a
   ciascun orizzonte temporale.

4. PERCENTILI E PROBABILITÀ DI OBIETTIVO.
   Restituiamo percentili 5/10/25/50/75/90/95 a ogni orizzonte (1, 5, 10,
   20 anni di default) + probabilità di superare soglie utente-definite.

5. VALORI NOMINALI E REALI (inflazione 2% di default).
   Su orizzonti di 20 anni l'inflazione erode ~33% del potere d'acquisto.
   Mostrare solo valori nominali sarebbe didatticamente fuorviante.

CAVEATS METODOLOGICI (esplicitati nell'output):
- IID assumption: ogni rendimento giornaliero simulato è indipendente da
  quello precedente. Nella realtà esistono cluster di volatilità (volatility
  clustering). Un block bootstrap li preserverebbe meglio.
- Calibration window: se i dati storici coprono pochi anni, le code estreme
  potrebbero non essere rappresentate (es. un crash tipo 2008 non simulato
  perché non presente nella finestra).
- I rendimenti del benchmark NON includono le ritenute fiscali alla fonte
  sui dividendi (level 1 withholding tax tipica ~15%).
- Stiamo simulando il "portafoglio target" (con pesi target), non quello
  effettivo che oscilla col drift. È approssimazione accettabile per
  portafogli ribilanciati frequentemente via PAC.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# yfinance importato dentro le funzioni che lo usano, per permettere ai test
# di mockarlo senza dipendere dalla rete.


# --------------------------------------------------------------------------- #
# Costanti
# --------------------------------------------------------------------------- #
DEFAULT_INFLATION_RATE = 0.020              # 2% annuo (target BCE)
DEFAULT_N_SIMULATIONS = 10_000
DEFAULT_HORIZONS_YEARS = [1, 5, 10, 20]
DEFAULT_PERCENTILES = [5, 10, 25, 50, 75, 90, 95]
TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12
TRADING_DAYS_PER_MONTH = 21                  # 252 / 12


# --------------------------------------------------------------------------- #
# 1. CALIBRAZIONE DEI RENDIMENTI
# --------------------------------------------------------------------------- #
def calibrate_returns_aggregated(tickers: list[str],
                                 weights: dict[str, float],
                                 lookback_years: int = 7) -> dict:
    """Calibra una serie di rendimenti del 'portafoglio sintetico'.

    Scarica i rendimenti storici di ciascun ticker e costruisce la serie
    aggregata: r_port = Σ w_i × r_i.

    Note metodologiche:
    - Allinea le serie troncando alla data più tarda di inizio (intersezione)
    - Calcola rendimenti giornalieri come pct_change semplice (non log)
      perché poi simuleremo aritmeticamente. Equivalente in pratica per
      rendimenti piccoli; più chiaro da interpretare.
    - I pesi devono sommare a 1.0

    v2 future: questa funzione sarà sostituita/affiancata da una versione
    multivariata che simula rendimenti correlati per ciascun ticker.

    Parametri
    ---------
    tickers : lista di ticker yfinance (es. ['VWCE.DE', 'VFEA.DE'])
    weights : dict {ticker: peso_target}, deve sommare a 1.0
    lookback_years : quanti anni di storia scaricare (yfinance darà quello
                     che ha disponibile)

    Returns
    -------
    dict con:
      - 'returns': pd.Series dei rendimenti giornalieri del portafoglio sintetico
      - 'start_date', 'end_date': intervallo coperto
      - 'n_days': numero di giorni nella calibrazione
      - 'n_years': anni effettivi di storia
      - 'tickers_used': ticker effettivamente scaricati
      - 'method': stringa 'aggregated_synthetic_v1' per tracciabilità
    """
    import yfinance as yf

    # Validazione pesi
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(
            f"I pesi devono sommare a 1.0, somma attuale: {sum(weights.values())}"
        )

    end_date = pd.Timestamp.today()
    start_date = end_date - pd.DateOffset(years=lookback_years)

    # Scarico dati: yfinance può restituire MultiIndex se multipli ticker
    raw = yf.download(tickers, start=start_date, end=end_date,
                      auto_adjust=True, progress=False)

    # Normalizza colonna Close
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw['Close']
    else:
        # Singolo ticker: yfinance può dare DataFrame plain
        close = raw[['Close']].rename(columns={'Close': tickers[0]})

    # Drop ticker senza dati (yfinance a volte restituisce colonne tutte NaN)
    close = close.dropna(axis=1, how='all')
    available_tickers = [t for t in tickers if t in close.columns]

    if not available_tickers:
        raise RuntimeError(
            f"Nessun ticker scaricato con successo. Richiesti: {tickers}"
        )

    # Allinea: tieni solo i giorni con prezzo disponibile per TUTTI i ticker
    close = close[available_tickers].dropna(how='any')

    # Rendimenti giornalieri
    daily_returns = close.pct_change().dropna()

    # Costruisci serie aggregata: r_port = Σ w_i × r_i
    # Se mancano alcuni ticker, ridistribuisci i pesi proporzionalmente
    used_weights = {t: weights[t] for t in available_tickers}
    weight_sum = sum(used_weights.values())
    if weight_sum < 1.0:
        # Riallineo i pesi a 1.0 sui ticker disponibili
        used_weights = {t: w / weight_sum for t, w in used_weights.items()}

    synthetic_returns = sum(
        used_weights[t] * daily_returns[t] for t in available_tickers
    )

    return {
        'returns': synthetic_returns,
        'start_date': synthetic_returns.index.min(),
        'end_date': synthetic_returns.index.max(),
        'n_days': len(synthetic_returns),
        'n_years': len(synthetic_returns) / TRADING_DAYS_PER_YEAR,
        'tickers_used': available_tickers,
        'weights_applied': used_weights,
        'method': 'aggregated_synthetic_v1',
    }


# --------------------------------------------------------------------------- #
# 2. MOTORE DI SIMULAZIONE (agnostico al metodo di calibrazione)
# --------------------------------------------------------------------------- #
def run_pac_simulation(returns_series: pd.Series,
                       initial_value: float,
                       monthly_contribution: float,
                       horizons_years: list[int] = None,
                       n_simulations: int = DEFAULT_N_SIMULATIONS,
                       inflation_rate: float = DEFAULT_INFLATION_RATE,
                       seed: int | None = 42) -> dict:
    """Esegue la simulazione Monte Carlo del PAC.

    Per ogni path:
      - Mese 0: capitale iniziale
      - Ogni mese successivo: aggiungi monthly_contribution, applica il
        rendimento mensile composto da TRADING_DAYS_PER_MONTH (~21) rendimenti
        giornalieri estratti i.i.d. dalla serie storica.

    Parametri
    ---------
    returns_series : Serie dei rendimenti giornalieri da cui campionare
    initial_value : Valore iniziale del portafoglio (€)
    monthly_contribution : PAC mensile netto investito (€)
    horizons_years : Lista di orizzonti in anni (default [1, 5, 10, 20])
    n_simulations : Numero di path Monte Carlo (default 10.000)
    inflation_rate : Tasso annuo per il calcolo dei valori reali (default 2%)
    seed : Random seed per riproducibilità (default 42)

    Returns
    -------
    dict con:
      - 'simulations': array (n_simulations, max_months+1) di tutti i path
      - 'horizons': dict {anni: {percentili nominali e reali, contribuzione totale}}
      - 'metadata': parametri usati
    """
    if horizons_years is None:
        horizons_years = DEFAULT_HORIZONS_YEARS

    if seed is not None:
        np.random.seed(seed)

    # Pulisci la serie: drop NaN e zeri sospetti
    returns_clean = returns_series.dropna()
    returns_array = returns_clean.values
    n_historical = len(returns_array)

    if n_historical < TRADING_DAYS_PER_MONTH:
        raise ValueError(
            f"Serie storica troppo corta: {n_historical} giorni, "
            f"servono almeno {TRADING_DAYS_PER_MONTH} (1 mese)"
        )

    max_horizon = max(horizons_years)
    n_months = max_horizon * MONTHS_PER_YEAR

    # Pre-calcolo: per ogni mese di ogni path, estrai 21 rendimenti casuali
    # e composti per ottenere il rendimento mensile.
    # Tensor 3D: (n_simulations, n_months, days_per_month)
    # Memoria: 10000 × 240 × 21 × 8 bytes = ~400 MB. Troppo per essere safe.
    # Approccio più efficiente: genera mese per mese.

    # Array dei valori del portafoglio: (n_simulations, n_months+1)
    values = np.zeros((n_simulations, n_months + 1), dtype=np.float64)
    values[:, 0] = initial_value

    # Per ogni mese, estraiamo gli indici dei rendimenti da campionare
    # e applichiamo il rendimento composto del mese a tutti i path.
    for month in range(1, n_months + 1):
        # Campiona TRADING_DAYS_PER_MONTH × n_simulations indici random
        # dalla serie storica
        idx = np.random.randint(0, n_historical,
                                size=(n_simulations, TRADING_DAYS_PER_MONTH))
        # Rendimento mensile composto per ogni simulazione
        daily_rets = returns_array[idx]                   # shape: (n_sims, 21)
        monthly_returns = np.prod(1 + daily_rets, axis=1) - 1   # shape: (n_sims,)

        # Aggiungi contribuzione a inizio mese, poi applica rendimento
        # (convenzione: il versamento "guadagna" il rendimento del mese)
        values[:, month] = (values[:, month - 1]
                            + monthly_contribution) * (1 + monthly_returns)

    # Estrai percentili a ciascun orizzonte
    horizons_results = {}
    for years in horizons_years:
        month_idx = years * MONTHS_PER_YEAR
        if month_idx > n_months:
            continue

        values_at_horizon = values[:, month_idx]
        total_contributed = initial_value + monthly_contribution * month_idx
        inflation_factor = (1 + inflation_rate) ** years

        # Percentili nominali
        perc_nominal = {
            p: float(np.percentile(values_at_horizon, p))
            for p in DEFAULT_PERCENTILES
        }
        # Percentili reali (potere d'acquisto in €-oggi)
        perc_real = {
            p: v / inflation_factor for p, v in perc_nominal.items()
        }

        horizons_results[years] = {
            'years': years,
            'total_contributed': total_contributed,
            'percentiles_nominal': perc_nominal,
            'percentiles_real': perc_real,
            'inflation_factor': inflation_factor,
            'median_nominal': perc_nominal[50],
            'median_real': perc_real[50],
            'mean_nominal': float(values_at_horizon.mean()),
            'std_nominal': float(values_at_horizon.std()),
        }

    return {
        'simulations': values,
        'horizons': horizons_results,
        'metadata': {
            'n_simulations': n_simulations,
            'initial_value': initial_value,
            'monthly_contribution': monthly_contribution,
            'horizons_years': horizons_years,
            'inflation_rate': inflation_rate,
            'historical_days_used': n_historical,
            'historical_years_used': n_historical / TRADING_DAYS_PER_YEAR,
            'seed': seed,
        },
    }


# --------------------------------------------------------------------------- #
# 3. API DI ALTO LIVELLO (orchestratore)
# --------------------------------------------------------------------------- #
def simulate_pac(tickers: list[str],
                 weights: dict[str, float],
                 initial_value: float,
                 monthly_contribution: float,
                 horizons_years: list[int] = None,
                 n_simulations: int = DEFAULT_N_SIMULATIONS,
                 inflation_rate: float = DEFAULT_INFLATION_RATE,
                 lookback_years: int = 7,
                 seed: int | None = 42) -> dict:
    """API di alto livello: calibra + simula PAC in un'unica chiamata.

    È l'entry point principale per il notebook. Combina calibrazione e
    simulazione in un workflow lineare.

    Parametri
    ---------
    tickers : lista ticker yfinance (es. ['VWCE.DE', 'VFEA.DE'])
    weights : dict {ticker: peso_target}, somma 1.0
    initial_value : valore iniziale del portafoglio (€)
    monthly_contribution : PAC mensile netto (€)
    horizons_years : orizzonti in anni (default [1, 5, 10, 20])
    n_simulations : numero di path (default 10.000)
    inflation_rate : tasso annuo per valori reali (default 2%)
    lookback_years : quanti anni di storia scaricare (default 7)
    seed : random seed (default 42 per riproducibilità)

    Returns
    -------
    dict completo con: calibration + simulation + interpretation
    """
    calibration = calibrate_returns_aggregated(tickers, weights, lookback_years)
    simulation = run_pac_simulation(
        calibration['returns'],
        initial_value=initial_value,
        monthly_contribution=monthly_contribution,
        horizons_years=horizons_years,
        n_simulations=n_simulations,
        inflation_rate=inflation_rate,
        seed=seed,
    )

    result = {
        'calibration': calibration,
        'simulation': simulation,
        'interpretation': _generate_interpretation(calibration, simulation),
    }
    return result


# --------------------------------------------------------------------------- #
# 4. PROBABILITÀ DI OBIETTIVI
# --------------------------------------------------------------------------- #
def probability_of_target(simulation_result: dict,
                          target_value: float,
                          horizon_years: int,
                          use_real_values: bool = False) -> float:
    """Probabilità che il valore al dato orizzonte superi `target_value`.

    Parametri
    ---------
    simulation_result : output di simulate_pac() o run_pac_simulation()
    target_value : soglia in € (nominali o reali a seconda di use_real_values)
    horizon_years : orizzonte temporale
    use_real_values : se True, deflaziona i valori simulati prima del confronto

    Returns
    -------
    float ∈ [0, 1]: probabilità che il valore finale superi il target
    """
    # Supporta sia output di simulate_pac (con chiave 'simulation') che diretto
    if 'simulation' in simulation_result:
        sim = simulation_result['simulation']
    else:
        sim = simulation_result

    month_idx = horizon_years * MONTHS_PER_YEAR
    values_at_horizon = sim['simulations'][:, month_idx]

    if use_real_values:
        inflation_rate = sim['metadata']['inflation_rate']
        values_at_horizon = values_at_horizon / (1 + inflation_rate) ** horizon_years

    return float((values_at_horizon >= target_value).mean())


# --------------------------------------------------------------------------- #
# 5. INTERPRETAZIONE TESTUALE
# --------------------------------------------------------------------------- #
def _generate_interpretation(calibration: dict, simulation: dict) -> str:
    """Genera 2-3 frasi di sintesi sui risultati."""
    parts = []

    # Frase 1: calibrazione
    n_years_cal = calibration['n_years']
    if n_years_cal < 3:
        parts.append(
            f"The calibration is based on only {n_years_cal:.1f} years of "
            f"history: it may not include extreme events (2008 crisis, 2020 "
            f"crash). The tails of the distribution may be underestimated."
        )
    elif n_years_cal < 10:
        parts.append(
            f"The calibration is based on {n_years_cal:.1f} years of the "
            f"target portfolio's history."
        )
    else:
        parts.append(
            f"Robust calibration on {n_years_cal:.0f} years of history."
        )

    # Frase 2: risultato per l'orizzonte più lungo
    horizons = simulation['horizons']
    if horizons:
        max_h = max(horizons.keys())
        h_data = horizons[max_h]
        median_nom = h_data['median_nominal']
        median_real = h_data['median_real']
        p10 = h_data['percentiles_nominal'][10]
        p90 = h_data['percentiles_nominal'][90]
        contributed = h_data['total_contributed']
        multiplier_median = median_nom / contributed
        parts.append(
            f"At {max_h} years: the portfolio's median value is estimated at "
            f"€{median_nom:,.0f} nominal (€{median_real:,.0f} in today's "
            f"purchasing power), on €{contributed:,.0f} contributed "
            f"({multiplier_median:.2f}× the capital). Likely range "
            f"(10th-90th percentile): €{p10:,.0f} - €{p90:,.0f}."
        )

    parts.append(
        "Methodological caveats: IID bootstrap (no volatility clustering); "
        "dividend withholding taxes not included; assumes contributions "
        "continue even during drawdowns."
    )

    return " ".join(parts)
