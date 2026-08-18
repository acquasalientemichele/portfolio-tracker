"""
risk.py — metriche di rischio del portafoglio.

Filosofia di design (vedi DESIGN_DECISIONS.md per il dettaglio):

1. ANNUALIZZAZIONE A 252 TRADING DAYS, non 365 giorni di calendario.
   Standard finanziario: solo i giorni di mercato contribuiscono alla
   volatilità. Usare 365 sovrastima la vol annuale di ~21%.

2. DRAWDOWN SU TWR CUMULATO, mai sul valore di mercato. In un portafoglio
   con flussi, i versamenti possono mascherare i drawdown reali. Esempio:
   il mercato fa -3% ma tu versi 500€ → il valore di mercato cresce, sembra
   non ci sia drawdown. Sbagliato. Il TWR depurato dai flussi cattura
   correttamente il calo.

3. CONFIDENCE FLAG A 4 LIVELLI basato sulla lunghezza della serie:
   VERY_LOW (<6m) / LOW (<1y) / MEDIUM (<3y) / HIGH (3y+). Mostrare uno
   Sharpe come "+1.8" su una serie di 7 mesi è statisticamente disonesto.

4. RISK-FREE RATE configurabile, default BTP 3y (3.0% nel giugno 2026).
   Proxy realistico per investitore retail italiano.

5. 5 METRICHE in v1: volatilità, Sharpe, Sortino, max drawdown analysis,
   beta vs benchmark. Più: top-N drawdowns (default 3, threshold 0.5%).

ESCLUSI deliberatamente (vedi design decisions per ragioni complete):
   - VaR parametrico (assume gaussianità, sottostima code estreme)
   - Tracking error (poco interessante per portafoglio quasi-replicante)
   - Information ratio (per gestori attivi, non per passive PAC)
   - Calmar ratio (instabile, poco usata)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Costanti
# --------------------------------------------------------------------------- #
DEFAULT_RISK_FREE_RATE = 0.030          # BTP 3y giugno 2026
TRADING_DAYS_PER_YEAR = 252             # standard finanziario
DEFAULT_DRAWDOWN_THRESHOLD = 0.005      # 0.5%
DEFAULT_TOP_N_DRAWDOWNS = 3

# Confidence thresholds (in giorni di calendario)
CONFIDENCE_VERY_LOW_MAX = 180           # < 6 mesi
CONFIDENCE_LOW_MAX = 365                # < 1 anno
CONFIDENCE_MEDIUM_MAX = 1095            # < 3 anni
# >= 1095 giorni: HIGH


# --------------------------------------------------------------------------- #
# Funzioni atomiche (calcoli puri)
# --------------------------------------------------------------------------- #
def compute_returns(twr_cum: pd.Series) -> pd.Series:
    """Rendimenti giornalieri dalla serie TWR cumulata.

    Input:  serie TWR cumulata (base 1.0), tipo [1.000, 1.005, 0.997, ...]
    Output: serie rendimenti giornalieri, primo NaN droppato

    NOTA: filtra i rendimenti esattamente zero (weekend/festivi senza
    movimento) per non sottostimare la volatilità.
    """
    returns = twr_cum.pct_change().dropna()
    # Filtra giorni senza movimento (es. weekend ripetuti come 0)
    returns = returns[returns != 0]
    return returns


def volatility_annualized(returns: pd.Series) -> float:
    """Volatilità annualizzata = std giornaliera × √252."""
    if len(returns) < 2:
        return float('nan')
    return float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def annualized_return(returns: pd.Series) -> float:
    """Rendimento medio annualizzato geometrico.

    Formula: (1 + r_total)^(252/N) - 1
    dove r_total è il rendimento cumulato e N il numero di giorni.
    """
    if len(returns) < 1:
        return float('nan')
    total_return = (1 + returns).prod() - 1
    n_days = len(returns)
    return float((1 + total_return) ** (TRADING_DAYS_PER_YEAR / n_days) - 1)


def sharpe_ratio(returns: pd.Series, rf_annual: float) -> float:
    """Sharpe ratio annualizzato.

    Formula: (R_annual - Rf) / σ_annual
    dove R_annual è il rendimento geometrico annualizzato e σ_annual la
    volatilità annualizzata.
    """
    if len(returns) < 2:
        return float('nan')
    r_ann = annualized_return(returns)
    vol_ann = volatility_annualized(returns)
    if vol_ann == 0 or np.isnan(vol_ann):
        return float('nan')
    return float((r_ann - rf_annual) / vol_ann)


def sortino_ratio(returns: pd.Series, rf_annual: float,
                  target: float = 0.0) -> float:
    """Sortino ratio: penalizza solo la volatilità sotto il target.

    Variante "filosoficamente più giusta" dello Sharpe per investitori
    retail: la volatilità positiva (rendimenti sopra il target) non è
    "rischio", solo quella negativa lo è.

    target: soglia sotto la quale i rendimenti vengono penalizzati.
            Convenzione: 0% (rendimento nullo).
    """
    if len(returns) < 2:
        return float('nan')
    # Downside deviation: std dei soli rendimenti sotto il target
    daily_target = (1 + target) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    downside = returns[returns < daily_target]
    if len(downside) < 2:
        # Nessun rendimento negativo: Sortino infinito teorico
        return float('inf')
    # Downside deviation calcolata rispetto al target (non alla media)
    downside_dev = np.sqrt(((downside - daily_target) ** 2).mean())
    downside_dev_ann = downside_dev * np.sqrt(TRADING_DAYS_PER_YEAR)
    if downside_dev_ann == 0:
        return float('inf')
    r_ann = annualized_return(returns)
    return float((r_ann - rf_annual) / downside_dev_ann)


def beta(returns_portfolio: pd.Series,
         returns_benchmark: pd.Series) -> float:
    """Beta vs benchmark: covarianza / varianza del benchmark.

    Le due serie devono essere già allineate per data. Allineamento
    avviene nella funzione di alto livello risk_summary().
    """
    if len(returns_portfolio) < 2 or len(returns_benchmark) < 2:
        return float('nan')
    # Allinea per indice (intersezione)
    aligned = pd.concat([returns_portfolio, returns_benchmark], axis=1).dropna()
    if len(aligned) < 2:
        return float('nan')
    rp = aligned.iloc[:, 0]
    rb = aligned.iloc[:, 1]
    var_b = rb.var()
    if var_b == 0:
        return float('nan')
    return float(rp.cov(rb) / var_b)


# --------------------------------------------------------------------------- #
# Drawdown analysis
# --------------------------------------------------------------------------- #
def compute_drawdown_series(twr_cum: pd.Series) -> pd.DataFrame:
    """Serie giornaliera di peak running, drawdown, days_since_peak.

    Output DataFrame con colonne:
      - peak: massimo cumulato fino a quel giorno
      - drawdown: (valore - peak) / peak, sempre ≤ 0
      - days_since_peak: giorni dal peak più recente (0 quando si è al picco)
    """
    peak = twr_cum.cummax()
    drawdown = (twr_cum - peak) / peak

    # Days since peak: per ogni giorno, distanza dall'ultimo peak
    days_since_peak = []
    last_peak_idx = 0
    for i, (val, pk) in enumerate(zip(twr_cum.values, peak.values)):
        if val >= pk:  # nuovo peak
            last_peak_idx = i
            days_since_peak.append(0)
        else:
            days_since_peak.append(i - last_peak_idx)

    return pd.DataFrame({
        'value': twr_cum.values,
        'peak': peak.values,
        'drawdown': drawdown.values,
        'days_since_peak': days_since_peak,
    }, index=twr_cum.index)


def max_drawdown_analysis(twr_cum: pd.Series) -> dict:
    """Identifica il singolo MAX drawdown della serie.

    Restituisce: depth, start_date, bottom_date, recovery_date,
    duration_days (start→bottom), recovery_days (bottom→recovery),
    is_currently_in_drawdown.
    """
    if len(twr_cum) < 2:
        return _empty_drawdown_dict()

    dd_series = compute_drawdown_series(twr_cum)
    # Trova il giorno di max drawdown (più negativo)
    bottom_idx = dd_series['drawdown'].idxmin()
    max_dd = float(dd_series.loc[bottom_idx, 'drawdown'])

    if max_dd >= 0:
        return _empty_drawdown_dict()

    # Trova lo start: ultimo peak prima del bottom
    pre_bottom = dd_series.loc[:bottom_idx]
    # Il peak precedente al bottom è dove value == peak per l'ultima volta
    at_peak = pre_bottom[pre_bottom['value'] >= pre_bottom['peak']]
    start_idx = at_peak.index[-1] if len(at_peak) else pre_bottom.index[0]

    # Trova il recovery: primo giorno dopo bottom in cui torna al peak
    peak_at_start = dd_series.loc[start_idx, 'peak']
    post_bottom = dd_series.loc[bottom_idx:]
    recovered = post_bottom[post_bottom['value'] >= peak_at_start]
    recovery_idx = recovered.index[0] if len(recovered) > 1 else None
    # (>1 perché il bottom stesso è incluso, e non lo consideriamo recovery)

    duration_days = (bottom_idx - start_idx).days
    recovery_days = ((recovery_idx - bottom_idx).days
                     if recovery_idx is not None else None)
    is_in_dd = (recovery_idx is None)

    return {
        'max_drawdown': max_dd,
        'max_drawdown_start': start_idx,
        'max_drawdown_bottom': bottom_idx,
        'max_drawdown_recovery': recovery_idx,
        'max_drawdown_duration_days': duration_days,
        'max_drawdown_recovery_days': recovery_days,
        'is_currently_in_drawdown': is_in_dd,
    }


def top_drawdowns(twr_cum: pd.Series, n: int = DEFAULT_TOP_N_DRAWDOWNS,
                  threshold: float = DEFAULT_DRAWDOWN_THRESHOLD
                  ) -> pd.DataFrame:
    """Identifica i top-N drawdowns distinti (non sovrapposti).

    Macchina a stati che itera la serie:
    - traccia il peak corrente
    - quando il valore scende sotto il peak, apre un drawdown
    - aggiorna il bottom mentre il drawdown peggiora
    - quando il valore torna ≥ peak, chiude il drawdown e registra
    - alla fine: se ancora in drawdown, registra come 'ongoing'

    Filtra drawdowns < threshold (default 0.5%) per evitare rumore.

    Restituisce DataFrame ordinato per profondità (peggiori in cima),
    con colonne: start_date, bottom_date, end_date, depth, duration_days,
    recovery_days, recovered.
    """
    if len(twr_cum) < 2:
        return pd.DataFrame(columns=['start_date', 'bottom_date', 'end_date',
                                     'depth', 'duration_days',
                                     'recovery_days', 'recovered'])

    drawdowns = []

    # Stato macchina
    current_peak = float(twr_cum.iloc[0])
    current_peak_date = twr_cum.index[0]
    in_drawdown = False
    dd_start_date = None
    dd_bottom_value = None
    dd_bottom_date = None
    peak_at_start = None

    for date, value in twr_cum.iloc[1:].items():
        value = float(value)
        if value >= current_peak:
            # Tocchiamo (o superiamo) il picco
            if in_drawdown:
                # Drawdown chiuso: registriamolo
                depth = (dd_bottom_value / peak_at_start) - 1
                duration = (dd_bottom_date - dd_start_date).days
                recovery = (date - dd_bottom_date).days
                drawdowns.append({
                    'start_date': dd_start_date,
                    'bottom_date': dd_bottom_date,
                    'end_date': date,
                    'depth': depth,
                    'duration_days': duration,
                    'recovery_days': recovery,
                    'recovered': True,
                })
                in_drawdown = False
            current_peak = value
            current_peak_date = date
        else:
            # Sotto il picco
            if not in_drawdown:
                # Apertura nuovo drawdown
                dd_start_date = current_peak_date
                dd_bottom_value = value
                dd_bottom_date = date
                peak_at_start = current_peak
                in_drawdown = True
            else:
                # Aggiorna bottom se peggiora
                if value < dd_bottom_value:
                    dd_bottom_value = value
                    dd_bottom_date = date

    # Fine del loop: se ancora in drawdown, registralo come ongoing
    if in_drawdown:
        depth = (dd_bottom_value / peak_at_start) - 1
        duration = (dd_bottom_date - dd_start_date).days
        drawdowns.append({
            'start_date': dd_start_date,
            'bottom_date': dd_bottom_date,
            'end_date': None,
            'depth': depth,
            'duration_days': duration,
            'recovery_days': None,
            'recovered': False,
        })

    if not drawdowns:
        return pd.DataFrame(columns=['start_date', 'bottom_date', 'end_date',
                                     'depth', 'duration_days',
                                     'recovery_days', 'recovered'])

    df = pd.DataFrame(drawdowns)
    # Filtra threshold
    df = df[df['depth'] <= -threshold].copy()
    # Ordina per profondità (depth più negativo = peggiore)
    df = df.sort_values('depth').head(n).reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# Confidence flag
# --------------------------------------------------------------------------- #
def confidence_level(n_days: int) -> str:
    """Restituisce affidabilità statistica delle metriche su n_days di storia."""
    if n_days < CONFIDENCE_VERY_LOW_MAX:
        return 'VERY_LOW'
    elif n_days < CONFIDENCE_LOW_MAX:
        return 'LOW'
    elif n_days < CONFIDENCE_MEDIUM_MAX:
        return 'MEDIUM'
    else:
        return 'HIGH'


# --------------------------------------------------------------------------- #
# Interpretazione testuale (sintetica, 1-2 frasi)
# --------------------------------------------------------------------------- #
def _interpret_volatility(vol: float) -> str:
    """Contestualizza la volatilità."""
    if np.isnan(vol):
        return ""
    vol_pct = vol * 100
    if vol < 0.08:
        return f"low volatility ({vol_pct:.1f}%, below a typical bond portfolio)"
    elif vol < 0.12:
        return f"moderate volatility ({vol_pct:.1f}%, in line with a balanced portfolio)"
    elif vol < 0.18:
        return f"normal volatility ({vol_pct:.1f}%, in line with global equities)"
    else:
        return f"elevated volatility ({vol_pct:.1f}%, above standard global equities)"


def _interpret_confidence(conf: str, n_days: int) -> str:
    """Caveat sull'affidabilità delle metriche."""
    if conf == 'VERY_LOW':
        return (f"Treat these figures with great caution: with only {n_days} "
                "days of history, the statistical metrics are dominated by noise.")
    elif conf == 'LOW':
        return (f"Treat these figures with caution: with {n_days} days of "
                "history, metrics like the Sharpe ratio are not yet "
                "statistically significant.")
    elif conf == 'MEDIUM':
        return ("The basic metrics are reliable; the Sharpe ratio will become "
                "more robust with a few more years of history.")
    else:  # HIGH
        return f"The {n_days // 365}-year horizon makes the metrics statistically robust."


def generate_interpretation(metrics: dict) -> str:
    """Compone l'interpretazione testuale (1-2 frasi) dalle metriche."""
    parts = []

    # Frase 1: volatilità contestualizzata
    vol_text = _interpret_volatility(metrics.get('volatility_annualized', float('nan')))
    if vol_text:
        parts.append(f"The portfolio shows {vol_text}.")

    # Frase 2: caveat sull'affidabilità
    conf_text = _interpret_confidence(
        metrics.get('confidence', 'VERY_LOW'),
        metrics.get('period_days', 0),
    )
    parts.append(conf_text)

    # Frase 3 opzionale: drawdown significativo
    max_dd = metrics.get('max_drawdown', 0)
    if max_dd is not None and max_dd < -0.05:
        if metrics.get('is_currently_in_drawdown'):
            start = metrics.get('max_drawdown_start')
            start_str = start.strftime('%d %b %Y') if start else 'unknown date'
            parts.append(
                f"Currently in a {abs(max_dd)*100:.1f}% drawdown "
                f"that started on {start_str}."
            )
        else:
            duration = metrics.get('max_drawdown_duration_days', 0)
            recovery = metrics.get('max_drawdown_recovery_days', 0)
            parts.append(
                f"Largest historical drawdown of {abs(max_dd)*100:.1f}% "
                f"({duration}d duration, recovered in {recovery}d)."
            )

    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Funzione principale: risk_summary
# --------------------------------------------------------------------------- #
def risk_summary(twr_cum: pd.Series,
                 bench_norm: pd.Series,
                 rf_annual: float = DEFAULT_RISK_FREE_RATE,
                 dd_threshold: float = DEFAULT_DRAWDOWN_THRESHOLD,
                 top_n: int = DEFAULT_TOP_N_DRAWDOWNS) -> dict:
    """Calcola tutte le metriche di rischio e restituisce un dict completo.

    Parametri
    ---------
    twr_cum : Serie TWR cumulata del portafoglio (base 1.0)
    bench_norm : Serie del benchmark normalizzata (stesso indice temporale)
                 OBBLIGATORIO (la scelta è di forzare il contesto di
                 riferimento)
    rf_annual : Risk-free rate annualizzato (default 3% = BTP 3y)
    dd_threshold : Soglia minima per i top drawdowns (default 0.5%)
    top_n : Numero di top drawdowns da identificare (default 3)

    Returns
    -------
    dict con metriche, confidence flags, drawdown analysis, interpretazione.
    """
    if bench_norm is None or len(bench_norm) == 0:
        raise ValueError("bench_norm is required to compute beta")

    # Rendimenti giornalieri del portafoglio
    returns_p = compute_returns(twr_cum)

    # Rendimenti del benchmark allineati
    returns_b = compute_returns(bench_norm)

    # Periodo di analisi
    n_days = (twr_cum.index[-1] - twr_cum.index[0]).days
    n_years = n_days / 365.25
    conf = confidence_level(n_days)

    # Metriche atomiche
    vol_ann = volatility_annualized(returns_p)
    sharpe = sharpe_ratio(returns_p, rf_annual)
    sortino = sortino_ratio(returns_p, rf_annual)
    beta_val = beta(returns_p, returns_b)

    # Drawdown analysis
    max_dd = max_drawdown_analysis(twr_cum)
    top_dds = top_drawdowns(twr_cum, n=top_n, threshold=dd_threshold)

    # Costruisce il dict risultato
    result = {
        # Meta
        'period_days': n_days,
        'period_years': round(n_years, 2),
        'confidence': conf,
        'risk_free_rate_used': rf_annual,

        # Performance per Sharpe/Sortino
        'annualized_return': annualized_return(returns_p),

        # Volatility
        'volatility_annualized': vol_ann,

        # Risk-adjusted returns
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,

        # Drawdown max
        **max_dd,

        # Beta
        'beta_vs_benchmark': beta_val,

        # Top drawdowns
        'top_drawdowns': top_dds,
    }

    # Interpretazione testuale (alla fine, usa le altre metriche)
    result['interpretation'] = generate_interpretation(result)

    return result


# --------------------------------------------------------------------------- #
# Helpers privati
# --------------------------------------------------------------------------- #
def _empty_drawdown_dict() -> dict:
    return {
        'max_drawdown': 0.0,
        'max_drawdown_start': None,
        'max_drawdown_bottom': None,
        'max_drawdown_recovery': None,
        'max_drawdown_duration_days': 0,
        'max_drawdown_recovery_days': None,
        'is_currently_in_drawdown': False,
    }
