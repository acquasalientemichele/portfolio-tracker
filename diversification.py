"""
diversification.py
==================

Analisi di diversificazione del portafoglio per look-through sugli ETF.

Idea di fondo
-------------
Un ETF non e' una scatola nera: e' un paniere di titoli con settori e paesi.
"Guardando dentro" (look-through) ogni ETF e pesandolo per la sua quota di
portafoglio, si ricava l'esposizione EFFETTIVA aggregata per settore, paese e
regione. Da li' si misurano concentrazione (HHI) e sovrapposizione tra fondi
(overlap coefficient).

Il modulo e' puro: dipende solo da pandas/numpy e accetta DataFrame/dict, non
importa ne' Streamlit ne' portfolio.py. I pesi arrivano dall'esterno, cosi' la
stessa funzione serve sia il portafoglio reale sia scenari ipotetici.

Convenzioni
-----------
- `snapshot`: DataFrame prodotto da refresh_holdings + canonicalize, con almeno
  le colonne `fund_isin, weight, asset_class` e la dimensione richiesta
  (`sector`, `country` o `region`). `weight` e' in PERCENTUALE (0-100).
- Le distribuzioni restituite sono in FRAZIONE e sommano a 1.0 (comodo per HHI).
- `weights`: dict {fund_isin: peso_di_portafoglio}. Non deve necessariamente
  sommare a 1: viene normalizzato internamente sui fondi effettivamente coperti.
"""

from __future__ import annotations

import pandas as pd

# Dimensioni di analisi ammesse.
DIMENSIONS = ("sector", "country", "region")


# --------------------------------------------------------------------------- #
# 1. DISTRIBUZIONE DI UN SINGOLO FONDO
# --------------------------------------------------------------------------- #
def fund_distribution(
    snapshot: pd.DataFrame,
    fund_isin: str,
    dim: str,
    *,
    equity_only: bool = True,
) -> pd.Series:
    """Distribuzione dei pesi di UN fondo lungo una dimensione (frazioni, somma 1).

    Parameters
    ----------
    dim : str
        Una fra DIMENSIONS ('sector', 'country', 'region').
    equity_only : bool
        Se True esclude cash e derivati (asset_class != 'Equity') e rinormalizza.
        La quota cash di questi ETF e' ~0.2%, ma escluderla rende l'analisi
        dell'esposizione azionaria pulita e confrontabile fra fondi.
    """
    if dim not in DIMENSIONS:
        raise ValueError(f"dim deve essere una di {DIMENSIONS}, ricevuto '{dim}'.")

    df = snapshot[snapshot["fund_isin"] == fund_isin]
    if df.empty:
        raise KeyError(f"Nessuna holding per il fondo {fund_isin} nello snapshot.")

    if equity_only:
        df = df[df["asset_class"] == "Equity"]

    dist = df.groupby(dim)["weight"].sum()
    total = dist.sum()
    if total <= 0:
        return dist * 0.0
    return dist / total  # frazioni, somma 1


# --------------------------------------------------------------------------- #
# 2. LOOK-THROUGH DI PORTAFOGLIO
# --------------------------------------------------------------------------- #
def _covered_weights(snapshot: pd.DataFrame, weights: dict[str, float]) -> dict[str, float]:
    """Filtra i pesi tenendo solo i fondi presenti nello snapshot, e normalizza."""
    presenti = set(snapshot["fund_isin"].unique())
    coperti = {k: v for k, v in weights.items() if k in presenti and v > 0}
    tot = sum(coperti.values())
    if tot <= 0:
        return {}
    return {k: v / tot for k, v in coperti.items()}


def coverage(snapshot: pd.DataFrame, weights: dict[str, float]) -> float:
    """Quota di portafoglio (0-1) per cui abbiamo le holding.

    Se hai VWCE al 60% ma non ne hai ancora lo snapshot, il look-through copre
    solo il 40%: questa funzione lo rende esplicito, cosi' la pagina puo'
    dichiararlo invece di far finta che il risultato sia sul 100%.
    """
    tot = sum(v for v in weights.values() if v > 0)
    if tot <= 0:
        return 0.0
    presenti = set(snapshot["fund_isin"].unique())
    coperto = sum(v for k, v in weights.items() if k in presenti and v > 0)
    return coperto / tot


def look_through(
    snapshot: pd.DataFrame,
    weights: dict[str, float],
    dim: str,
    *,
    equity_only: bool = True,
) -> pd.Series:
    """Esposizione aggregata del portafoglio lungo `dim` (frazioni, somma 1).

    Combina le distribuzioni dei singoli fondi pesandole per la quota di
    portafoglio. I pesi vengono normalizzati sui soli fondi coperti: il
    risultato e' quindi *condizionato* alla parte di portafoglio visibile
    (vedi coverage()).
    """
    w = _covered_weights(snapshot, weights)
    if not w:
        raise ValueError("Nessun fondo coperto: impossibile fare il look-through.")

    parti = [
        fund_distribution(snapshot, isin, dim, equity_only=equity_only) * peso
        for isin, peso in w.items()
    ]
    agg = pd.concat(parti, axis=1).fillna(0.0).sum(axis=1)
    return agg.sort_values(ascending=False)


# --------------------------------------------------------------------------- #
# 3. CONCENTRAZIONE (HHI)
# --------------------------------------------------------------------------- #
def hhi(distribution: pd.Series) -> float:
    """Herfindahl-Hirschman Index: somma dei quadrati dei pesi (frazioni).

    1.0 = tutto concentrato in una categoria; ~0 = molto diversificato.
    """
    w = distribution[distribution > 0]
    return float((w ** 2).sum())


def effective_number(distribution: pd.Series) -> float:
    """Numero effettivo di categorie = 1 / HHI.

    Interpretazione intuitiva: un portafoglio con questo HHI e' diversificato
    "come se" fosse equiripartito su questo numero di settori/paesi.
    Es. HHI 0.5 -> 2 categorie effettive.
    """
    h = hhi(distribution)
    return float(1.0 / h) if h > 0 else 0.0


# --------------------------------------------------------------------------- #
# 4. SOVRAPPOSIZIONE TRA FONDI (overlap coefficient)
# --------------------------------------------------------------------------- #
def overlap_coefficient(dist_a: pd.Series, dist_b: pd.Series) -> float:
    """Overlap fra due distribuzioni = somma dei minimi categoria per categoria.

    Con distribuzioni che sommano a 1, il risultato e' in [0, 1]:
      1.0 = identiche;  0.0 = nessuna categoria in comune.
    Misura la sovrapposizione sulla DIMENSIONE (es. quanto due ETF condividono
    lo stesso profilo settoriale/geografico), non sui singoli titoli.
    """
    idx = dist_a.index.union(dist_b.index)
    a = dist_a.reindex(idx, fill_value=0.0)
    b = dist_b.reindex(idx, fill_value=0.0)
    return float(pd.concat([a, b], axis=1).min(axis=1).sum())


def pairwise_overlap(
    snapshot: pd.DataFrame,
    dim: str,
    *,
    equity_only: bool = True,
) -> pd.DataFrame:
    """Matrice di overlap fra tutti i fondi dello snapshot, lungo `dim`."""
    isins = sorted(snapshot["fund_isin"].unique())
    dists = {i: fund_distribution(snapshot, i, dim, equity_only=equity_only) for i in isins}
    mat = pd.DataFrame(index=isins, columns=isins, dtype=float)
    for a in isins:
        for b in isins:
            mat.loc[a, b] = overlap_coefficient(dists[a], dists[b])
    return mat


# --------------------------------------------------------------------------- #
# 5. REPORT COMPLESSIVO (comodo per la pagina)
# --------------------------------------------------------------------------- #
def diversification_report(
    snapshot: pd.DataFrame,
    weights: dict[str, float],
    *,
    equity_only: bool = True,
) -> dict:
    """Report pronto per la UI: distribuzioni + concentrazione per ogni dimensione.

    Struttura restituita::

        {
          'coverage': float,
          'sector':  {'distribution': Series, 'hhi': float, 'effective_number': float},
          'country': {...},
          'region':  {...},
        }
    """
    report: dict = {"coverage": coverage(snapshot, weights)}
    for dim in DIMENSIONS:
        dist = look_through(snapshot, weights, dim, equity_only=equity_only)
        report[dim] = {
            "distribution": dist,
            "hhi": hhi(dist),
            "effective_number": effective_number(dist),
        }
    return report


# --------------------------------------------------------------------------- #
# 6. ADAPTER: pesi reali dal portafoglio
# --------------------------------------------------------------------------- #
def weights_from_valued_holdings(holdings_valued: pd.DataFrame) -> dict[str, float]:
    """Estrae {fund_isin: peso} dall'output di portfolio.value_holdings().

    Usa la colonna `isin` come chiave (stabile fra borse) e `weight` (valore di
    mercato / totale). Non importa portfolio.py: accetta solo il suo DataFrame.
    """
    if "isin" not in holdings_valued or "weight" not in holdings_valued:
        raise ValueError("Attese le colonne 'isin' e 'weight' (output di value_holdings).")
    return {
        str(isin): float(w)
        for isin, w in zip(holdings_valued["isin"], holdings_valued["weight"])
        if pd.notna(isin) and w > 0
    }
