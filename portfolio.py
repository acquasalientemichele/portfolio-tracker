"""
portfolio.py — logica di calcolo del portfolio tracker.

Tutte le funzioni di calcolo vivono qui, separate dal notebook.
Il notebook importa queste funzioni e le usa. Questo evita il
"notebook spaghetti" e rende la logica testabile e riusabile.

Dipendenze: pandas, numpy, yfinance, openpyxl, pyarrow (per il cache parquet)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# yfinance è importato dentro le funzioni che lo usano, così il resto
# del modulo funziona anche offline (utile per i test).

DATA_DIR = Path(__file__).parent / "data"
CACHE_FILE = DATA_DIR / "prices_cache.parquet"

REQUIRED_COLS = ["date", "ticker", "isin", "name", "operation",
                 "quantity", "price", "currency", "fees"]


# --------------------------------------------------------------------------- #
# 1. CARICAMENTO TRANSAZIONI
# --------------------------------------------------------------------------- #
def load_transactions(path: str | Path) -> pd.DataFrame:
    """Legge il file Excel delle operazioni e lo valida.

    Restituisce un DataFrame ordinato per data, con tipi corretti.
    Solleva ValueError se mancano colonne o ci sono valori non validi.
    """
    df = pd.read_excel(path, sheet_name="transactions", parse_dates=["date"])

    # validazione colonne
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonne mancanti nel file: {missing}")

    # rimuove righe completamente vuote
    df = df.dropna(how="all").copy()

    # normalizza operation
    df["operation"] = df["operation"].str.upper().str.strip()
    valid_ops = {"BUY", "SELL", "DIV"}
    bad = set(df["operation"].dropna().unique()) - valid_ops
    if bad:
        raise ValueError(f"Operazioni non valide {bad}. Ammesse: {valid_ops}")

    # tipi numerici
    for col in ["quantity", "price", "fees"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["ticker"] = df["ticker"].str.strip()
    return df.sort_values("date").reset_index(drop=True)


def load_settings(path: str | Path) -> dict:
    """Legge il foglio 'settings': parametri + target allocation."""
    raw = pd.read_excel(path, sheet_name="settings", header=None)
    params = {}
    for _, row in raw.iterrows():
        key = str(row[0]).strip() if pd.notna(row[0]) else ""
        if key in ("base_currency", "benchmark_ticker"):
            params[key] = str(row[1]).strip()

    # target allocation: cerca la riga header "ticker"/"target_weight"
    targets = {}
    start = None
    for i, row in raw.iterrows():
        if str(row[0]).strip() == "ticker" and "weight" in str(row[1]).lower():
            start = i + 1
            break
    if start is not None:
        for _, row in raw.iloc[start:].iterrows():
            t = row[0]
            w = row[1]
            if pd.notna(t) and pd.notna(w) and str(t).strip().upper() != "TOTALE":
                try:
                    targets[str(t).strip()] = float(w)
                except (ValueError, TypeError):
                    pass

    return {
        "base_currency": params.get("base_currency", "EUR"),
        "benchmark_ticker": params.get("benchmark_ticker", "VWCE.DE"),
        "target_allocation": targets,
    }


# --------------------------------------------------------------------------- #
# 2. PREZZI (yfinance + cache locale)
# --------------------------------------------------------------------------- #
def fetch_prices(tickers: list[str], start: str | datetime,
                 end: str | datetime | None = None,
                 use_cache: bool = True) -> pd.DataFrame:
    """Scarica i prezzi di chiusura giornalieri (EOD) per i ticker dati.

    Usa una cache parquet locale: se i dati richiesti sono già presenti
    non ri-scarica. Restituisce un DataFrame con indice = date e una
    colonna per ticker (Close in valuta nativa del listino).
    """
    import yfinance as yf

    DATA_DIR.mkdir(exist_ok=True)
    end = end or datetime.today()

    cache = pd.DataFrame()
    if use_cache and CACHE_FILE.exists():
        cache = pd.read_parquet(CACHE_FILE)

    have = set(cache.columns) if not cache.empty else set()
    need = [t for t in tickers if t not in have]

    if need:
        dl = yf.download(need, start=start, end=end,
                         auto_adjust=True, progress=False)
        if isinstance(dl.columns, pd.MultiIndex):
            dl = dl["Close"]
        else:
            dl = dl[["Close"]].rename(columns={"Close": need[0]})
        cache = dl if cache.empty else cache.join(dl, how="outer")
        cache.to_parquet(CACHE_FILE)

    cols = [t for t in tickers if t in cache.columns]
    out = cache[cols].copy()
    out.index = pd.to_datetime(out.index)
    return out.loc[str(pd.to_datetime(start).date()):].ffill()


def refresh_cache():
    """Cancella la cache prezzi per forzare un download pulito."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()


# --------------------------------------------------------------------------- #
# 3. POSIZIONI CORRENTI (holdings)
# --------------------------------------------------------------------------- #
def compute_holdings(tx: pd.DataFrame) -> pd.DataFrame:
    """Da transazioni a posizioni: quantità, costo, prezzo medio di carico.

    Il prezzo medio di carico (cost basis) usa il metodo del costo medio
    ponderato sugli acquisti. Le vendite riducono la quantità mantenendo
    invariato il prezzo medio (metodo average cost, coerente col fisco IT).
    """
    rows = []
    for ticker, g in tx.groupby("ticker"):
        qty = 0.0
        cost = 0.0  # costo totale residuo
        avg = 0.0
        for _, r in g.iterrows():
            if r["operation"] == "BUY":
                add_cost = r["quantity"] * r["price"] + r["fees"]
                cost += add_cost
                qty += r["quantity"]
                avg = cost / qty if qty else 0.0
            elif r["operation"] == "SELL":
                cost -= avg * r["quantity"]   # rimuove a costo medio
                qty -= r["quantity"]
            # DIV non muove quantità/costo (gestito altrove)
        if qty > 1e-9:
            rows.append({
                "ticker": ticker,
                "isin": g["isin"].iloc[0],
                "name": g["name"].iloc[0],
                "quantity": qty,
                "avg_cost": avg,
                "invested": qty * avg,
            })
    return pd.DataFrame(rows).set_index("ticker")


def value_holdings(holdings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge valore di mercato e P&L usando l'ultimo prezzo disponibile."""
    h = holdings.copy()
    last = prices.iloc[-1]
    h["last_price"] = h.index.map(last)
    h["market_value"] = h["quantity"] * h["last_price"]
    h["pnl_eur"] = h["market_value"] - h["invested"]
    h["pnl_pct"] = np.where(h["invested"] > 0,
                            h["pnl_eur"] / h["invested"], 0.0)
    h["weight"] = h["market_value"] / h["market_value"].sum()
    return h


# --------------------------------------------------------------------------- #
# 4. SERIE STORICA DEL VALORE & PERFORMANCE
# --------------------------------------------------------------------------- #
def portfolio_value_series(tx: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Ricostruisce giorno per giorno il valore del portfolio e i flussi.

    Restituisce un DataFrame con colonne:
      - value     : valore di mercato del portfolio
      - flow       : flusso netto di cassa del giorno (BUY = +, SELL = -)
                     dal punto di vista del capitale investito
    Serve per il calcolo del rendimento time-weighted.
    """
    dates = prices.index
    tickers = list(prices.columns)

    # quantità cumulata per ticker, allineata al calendario prezzi
    qty = pd.DataFrame(0.0, index=dates, columns=tickers)
    flow = pd.Series(0.0, index=dates)

    for _, r in tx.iterrows():
        d = pd.Timestamp(r["date"]).normalize()
        # snap alla prima data di mercato >= data operazione
        idx = dates[dates >= d]
        if len(idx) == 0:
            continue
        d0 = idx[0]
        t = r["ticker"]
        if t not in tickers:
            continue
        if r["operation"] == "BUY":
            qty.loc[d0:, t] += r["quantity"]
            flow.loc[d0] += r["quantity"] * r["price"] + r["fees"]
        elif r["operation"] == "SELL":
            qty.loc[d0:, t] -= r["quantity"]
            flow.loc[d0] -= r["quantity"] * r["price"] - r["fees"]

    value = (qty * prices).sum(axis=1)
    return pd.DataFrame({"value": value, "flow": flow})


def time_weighted_return(vs: pd.DataFrame) -> pd.Series:
    """Rendimento time-weighted (TWR) cumulato, metodo GIPS-compliant.

    Per ogni giorno il rendimento di periodo è:
        r_t = (V_t - F_t) / V_{t-1} - 1
    dove F_t è il flusso del giorno (assunto a inizio giornata).
    I sotto-periodi vengono concatenati geometricamente.
    Restituisce una serie di indice cumulato (base 1.0).
    """
    v = vs["value"]
    f = vs["flow"]
    daily = pd.Series(0.0, index=v.index)
    prev = v.shift(1)
    mask = prev > 0
    daily[mask] = (v[mask] - f[mask]) / prev[mask] - 1.0
    cum = (1.0 + daily).cumprod()
    return cum


def summary(holdings_valued: pd.DataFrame, twr_cum: pd.Series) -> dict:
    """Riepilogo numerico di alto livello per la dashboard."""
    mv = holdings_valued["market_value"].sum()
    inv = holdings_valued["invested"].sum()
    return {
        "market_value": mv,
        "invested": inv,
        "pnl_eur": mv - inv,
        "pnl_pct": (mv - inv) / inv if inv else 0.0,
        "twr_total": twr_cum.iloc[-1] - 1.0 if len(twr_cum) else 0.0,
    }
