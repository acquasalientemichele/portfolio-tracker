"""
rebalance.py — suggerimenti di ribilanciamento per PAC retail italiano.

Filosofia di design (scelte deliberate, non default per pigrizia):

1. CASH-FLOW REBALANCING ONLY: compra ma non vende. Motivazione:
   - Per ETF armonizzati in Italia, vendere realizza plusvalenze tassate al 26%
   - Il tax drag rende il classico "sell-high/buy-low" sub-ottimale per retail
   - Il PAC mensile fornisce naturalmente flussi per auto-correggere il drift

2. SINGLE-BUY PREFERRED: privilegia l'acquisto di un solo strumento per PAC.
   Motivazione:
   - Commissione TR di ~1€ per ordine: su 500€ di PAC vale 0.2% (più del bollo annuo)
   - Se la deviazione post-singolo-ordine è sotto soglia, non ha senso pagare 2 commissioni
   - Il mese successivo correggerà comunque

3. THRESHOLD 2%: scostamenti più piccoli vengono ignorati (default configurabile).
   Motivazione:
   - Su un orizzonte di lungo periodo, lo 1-2% di drift è rumore, non segnale
   - Evita over-trading psicologico (uno dei principali errori del retail)

4. PROJECTION: stima del numero di mesi per tornare entro 0.5% dal target.
   Motivazione: dare visibilità sulla velocità di auto-correzione del PAC.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


# Default configurabili
DEFAULT_THRESHOLD = 0.02            # 2%
DEFAULT_FEE_PER_ORDER = 1.00        # 1€ stile Trade Republic
PROJECTION_TARGET_BAND = 0.005      # 0.5%: soglia "tornato a target"
PROJECTION_MAX_MONTHS = 60          # safety cap (5 anni)


# --------------------------------------------------------------------------- #
# 1. SUGGERIMENTO DI ALLOCAZIONE PER UN SINGOLO PAC
# --------------------------------------------------------------------------- #
def suggest_rebalance(
    holdings_valued: pd.DataFrame,
    target_allocation: dict,
    new_cash: float,
    prices: pd.Series | dict,
    threshold: float = DEFAULT_THRESHOLD,
    fee_per_order: float = DEFAULT_FEE_PER_ORDER,
) -> dict:
    """Calcola come distribuire `new_cash` per avvicinarsi al target.

    Strategia gap-closing single-buy:
      1. Calcola il portafoglio post-investimento ideale
      2. Identifica il ticker più sottopesato
      3. Tenta l'acquisto singolo: tutto il cash sull'etichetta più carente
      4. Verifica la deviazione post: se sotto soglia → stop (1 commissione)
      5. Altrimenti split su due ticker (2 commissioni)

    Parametri
    ---------
    holdings_valued : DataFrame con indice=ticker, colonne includono
                      'market_value' e 'weight'
    target_allocation : {ticker: peso_target} con somma 1.0
    new_cash : importo netto da investire effettivamente in ETF (€).
               Le commissioni sono AGGIUNTIVE e vengono pagate sopra questa cifra.
               Esempio: new_cash=1000 con fee=1€ → 1000€ in ETF, totale conto 1001€.
    prices : ultimo prezzo per ticker (Series o dict)
    threshold : deviazione percentuale sotto cui non vale la pena split
    fee_per_order : commissione fissa per ordine

    Returns
    -------
    dict con:
      - 'orders': DataFrame degli ordini suggeriti
      - 'summary': dict con metriche di sintesi
      - 'message': stringa di spiegazione human-readable
    """
    if new_cash <= fee_per_order:
        return _empty_result(
            new_cash, f"Cash insufficiente: {new_cash:.2f}€ ≤ commissione {fee_per_order:.2f}€"
        )

    # Normalizza prices a dict
    if isinstance(prices, pd.Series):
        prices = prices.to_dict()

    # Universe: union di tickers in holdings e in target
    all_tickers = sorted(set(holdings_valued.index) | set(target_allocation.keys()))

    # Stato attuale
    current_value = {t: float(holdings_valued.loc[t, 'market_value'])
                     if t in holdings_valued.index else 0.0
                     for t in all_tickers}
    v_total = sum(current_value.values())
    v_post = v_total + new_cash

    # Target post-investimento
    target_value_post = {t: target_allocation.get(t, 0.0) * v_post
                         for t in all_tickers}

    # Gap (positivo = sottopesato, da comprare)
    gaps = {t: target_value_post[t] - current_value[t] for t in all_tickers}

    # Tickers realmente sottopesati (gap > 0): solo questi sono candidati al BUY
    underweight = [t for t in all_tickers if gaps[t] > 0]

    if not underweight:
        # Tutti sovra-pesati (caso raro: portafoglio drift in direzione opposta al nuovo cash).
        # Default: compra il ticker con peso TARGET maggiore.
        underweight = [max(all_tickers,
                           key=lambda t: target_allocation.get(t, 0))]

    # Primary = sottopesato con gap maggiore
    primary = max(underweight, key=lambda t: gaps[t])

    # Calcola scenario "single buy" sul primary
    cash_invested_A = new_cash
    new_holdings_A = {**current_value,
                      primary: current_value[primary] + cash_invested_A}
    weights_post_A = {t: new_holdings_A[t] / v_post for t in all_tickers}
    deviation_post_A = {t: weights_post_A[t] - target_allocation.get(t, 0.0)
                        for t in all_tickers}
    max_dev_A = max(abs(d) for d in deviation_post_A.values())

    # Lo SPLIT ha senso solo se:
    #   1. Deviazione post-single > threshold (gap troppo grande da chiudere con un solo ETF)
    #   2. Esiste almeno un altro ticker sottopesato in cui versare cash
    # Altrimenti pagheresti 2 commissioni per nulla.
    other_underweight = [t for t in underweight if t != primary]
    cash_net_B = new_cash 

    if (max_dev_A < threshold) or (not other_underweight) or (cash_net_B <= 0):
        return _build_single_order(
            primary, cash_invested_A, prices[primary], fee_per_order,
            weights_post_A, deviation_post_A, target_allocation,
            holdings_valued, threshold,
        )

    # Split tra primary e il secondo ticker più sottopesato
    secondary = max(other_underweight, key=lambda t: gaps[t])
    gap_p = gaps[primary]
    gap_s = gaps[secondary]
    gap_sum = gap_p + gap_s
    share_p = gap_p / gap_sum  # garantito > 0 perché entrambi underweight
    cash_to_primary = cash_net_B * share_p
    cash_to_secondary = cash_net_B - cash_to_primary

    return _build_double_order(
        primary, secondary,
        cash_to_primary, cash_to_secondary,
        prices, fee_per_order,
        current_value, v_post, target_allocation,
        holdings_valued, threshold,
    )


# --------------------------------------------------------------------------- #
# 2. PROIEZIONE: in quanti mesi torno entro 0.5% dal target?
# --------------------------------------------------------------------------- #
def project_convergence(
    holdings_valued: pd.DataFrame,
    target_allocation: dict,
    monthly_cash: float,
    prices: pd.Series | dict,
    threshold: float = DEFAULT_THRESHOLD,
    fee_per_order: float = DEFAULT_FEE_PER_ORDER,
    target_band: float = PROJECTION_TARGET_BAND,
    max_months: int = PROJECTION_MAX_MONTHS,
) -> dict:
    """Simula PAC mensili futuri assumendo prezzi costanti e returns nulli.

    Restituisce numero di mesi necessari perché la deviazione massima
    scenda sotto `target_band` (default 0.5%).

    Nota metodologica: l'ipotesi di "prezzi costanti" è una semplificazione.
    Nella realtà i prezzi si muovono e influenzano l'auto-correzione (a volte
    aiutando, a volte ostacolando). Per una proiezione fedele alle dinamiche
    di mercato vedi il modulo Monte Carlo (in arrivo).
    """
    if isinstance(prices, pd.Series):
        prices = prices.to_dict()

    all_tickers = sorted(set(holdings_valued.index) | set(target_allocation.keys()))
    current_value = {t: float(holdings_valued.loc[t, 'market_value'])
                     if t in holdings_valued.index else 0.0
                     for t in all_tickers}
    history = []

    # Stato iniziale
    v_total = sum(current_value.values())
    weights = {t: current_value[t] / v_total if v_total > 0 else 0.0
               for t in all_tickers}
    max_dev_now = max(abs(weights[t] - target_allocation.get(t, 0))
                      for t in all_tickers)
    history.append({'month': 0, 'value': v_total,
                    **{f'w_{t}': weights[t] for t in all_tickers},
                    'max_dev': max_dev_now})

    if max_dev_now < target_band:
        return {'months_to_target': 0, 'history': pd.DataFrame(history),
                'converged': True}

    # Simula mese per mese
    converged = False
    months = 0
    for m in range(1, max_months + 1):
        # Costruisci holdings_valued sintetico per la prossima iterazione
        hv = pd.DataFrame({
            'market_value': [current_value[t] for t in all_tickers],
            'weight': [weights[t] for t in all_tickers],
        }, index=all_tickers)

        rec = suggest_rebalance(hv, target_allocation, monthly_cash,
                                prices, threshold, fee_per_order)
        orders = rec['orders']

        # Aggiorna lo stato
        for _, row in orders.iterrows():
            t = row['ticker']
            current_value[t] = current_value.get(t, 0.0) + row['cash_invested']

        v_total = sum(current_value.values())
        weights = {t: current_value[t] / v_total if v_total > 0 else 0.0
                   for t in all_tickers}
        max_dev_now = max(abs(weights[t] - target_allocation.get(t, 0))
                          for t in all_tickers)
        history.append({'month': m, 'value': v_total,
                        **{f'w_{t}': weights[t] for t in all_tickers},
                        'max_dev': max_dev_now})

        months = m
        if max_dev_now < target_band:
            converged = True
            break

    return {
        'months_to_target': months if converged else None,
        'converged': converged,
        'final_max_dev': max_dev_now,
        'history': pd.DataFrame(history),
    }


# --------------------------------------------------------------------------- #
# Helpers privati
# --------------------------------------------------------------------------- #
def _empty_result(cash, msg):
    return {
        'orders': pd.DataFrame(columns=['ticker', 'cash_invested', 'fees',
                                        'quantity', 'price', 'weight_post',
                                        'deviation_post']),
        'summary': {'cash_input': cash, 'cash_invested': 0.0,
                    'fees_total': 0.0, 'n_orders': 0,
                    'max_deviation_post': None},
        'message': msg,
    }


def _build_single_order(ticker, cash_net, price, fee, weights_post,
                        deviation_post, target_alloc, holdings_valued,
                        threshold):
    qty = cash_net / price
    max_dev = max(abs(d) for d in deviation_post.values())

    orders = pd.DataFrame([{
        'ticker': ticker, 'cash_invested': cash_net, 'fees': fee,
        'quantity': qty, 'price': price,
        'weight_post': weights_post[ticker],
        'deviation_post': deviation_post[ticker],
    }])

    summary = {
        'cash_input': cash_net + fee,
        'cash_invested': cash_net,
        'fees_total': fee, 'n_orders': 1,
        'max_deviation_post': max_dev,
    }

    target_pct = target_alloc.get(ticker, 0) * 100
    weight_pct = weights_post[ticker] * 100
    dev_pct = deviation_post[ticker] * 100
    message = (f"Investi {cash_net:.2f}€ su {ticker} (totale uscito dal conto: "
               f"{cash_net + fee:.2f}€, di cui {fee:.2f}€ di commissione). "
               f"Peso post: {weight_pct:.1f}% (target {target_pct:.0f}%, "
               f"deviazione {dev_pct:+.2f} pp, soglia {threshold*100:.1f}%).")
    return {'orders': orders, 'summary': summary, 'message': message}


def _build_double_order(t1, t2, cash1, cash2, prices, fee,
                        current_value, v_post, target_alloc,
                        holdings_valued, threshold):
    qty1 = cash1 / prices[t1]
    qty2 = cash2 / prices[t2]
    nv1 = current_value[t1] + cash1
    nv2 = current_value[t2] + cash2
    w1, w2 = nv1 / v_post, nv2 / v_post
    d1 = w1 - target_alloc.get(t1, 0)
    d2 = w2 - target_alloc.get(t2, 0)

    orders = pd.DataFrame([
        {'ticker': t1, 'cash_invested': cash1, 'fees': fee,
         'quantity': qty1, 'price': prices[t1],
         'weight_post': w1, 'deviation_post': d1},
        {'ticker': t2, 'cash_invested': cash2, 'fees': fee,
         'quantity': qty2, 'price': prices[t2],
         'weight_post': w2, 'deviation_post': d2},
    ])
    total_fees = 2 * fee
    cash_invested = cash1 + cash2
    summary = {
        'cash_input': cash_invested + total_fees,
        'cash_invested': cash_invested,
        'fees_total': total_fees, 'n_orders': 2,
        'max_deviation_post': max(abs(d1), abs(d2)),
    }
    message = (
        f"Split necessario (deviazione singolo > {threshold*100:.1f}%). "
        f"{cash1:.2f}€ su {t1}, {cash2:.2f}€ su {t2} "
        f"(totale uscito dal conto: {cash1 + cash2 + total_fees:.2f}€, "
        f"di cui {total_fees:.2f}€ di commissioni). "
        f"Pesi post: {w1*100:.1f}% / {w2*100:.1f}%."
    )
    return {'orders': orders, 'summary': summary, 'message': message}
