"""
refresh_holdings.py
===================

Script offline: scorre il registro degli ETF, estrae la composizione di ognuno
dal rispettivo file grezzo e salva uno snapshot unico normalizzato in Parquet.

Uso
---
1. Scarica i file di composizione dai siti degli emittenti e mettili in RAW_DIR
   con il nome indicato in holdings_registry (campo `source`).
2. Lancia:  python refresh_holdings.py
3. L'app legge SNAPSHOT_PATH; NON scarica nulla a runtime.

Perche' offline e non a runtime: scaricare dai provider a ogni caricamento
pagina significa latenza, rate limit e possibili blocchi IP sul deploy. Le
composizioni degli indici cambiano lentamente (ribilanciamenti ~trimestrali),
quindi uno snapshot rigenerato su richiesta e' piu' che sufficiente.

Parquet e non Excel: lo snapshot e' output rigenerato dalla macchina, non un
input da editare a mano. Parquet preserva i tipi (pesi float, niente ambiguita'
sul separatore decimale italiano) e non storpia ticker/ISIN come farebbe Excel.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from holdings_providers import ParsedHoldings, get_provider
from holdings_registry import ETFEntry, iter_entries

# Percorsi (relativi alla root del progetto).
RAW_DIR = Path("data/holdings_raw")           # file grezzi scaricati a mano
SNAPSHOT_PATH = Path("data/holdings_snapshot.parquet")  # output letto dall'app


def refresh_one(entry: ETFEntry) -> pd.DataFrame | None:
    """Estrae e normalizza la composizione di un singolo ETF.

    Restituisce None (con avviso) se il file grezzo non e' presente o il
    provider non e' ancora implementato, cosi' un fondo mancante non blocca
    l'aggiornamento degli altri.
    """
    raw_path = RAW_DIR / entry.source

    if not raw_path.exists():
        print(f"  [skip] {entry.ticker:6s} file assente: {raw_path}")
        return None

    try:
        provider = get_provider(entry.provider)
    except KeyError as exc:
        print(f"  [skip] {entry.ticker:6s} {exc}")
        return None

    parsed: ParsedHoldings = provider.parse(raw_path)
    df = parsed.holdings.copy()

    # Aggancio i metadati del fondo a ogni riga (per poter concatenare piu' ETF).
    df.insert(0, "fund_isin", entry.isin)
    df.insert(1, "fund_ticker", entry.ticker)
    df["as_of"] = parsed.as_of

    somma = df["weight"].sum()
    print(
        f"  [ok]   {entry.ticker:6s} {len(df):4d} titoli | "
        f"somma pesi {somma:6.2f}% | as_of {parsed.as_of}"
    )
    return df


def refresh_all() -> pd.DataFrame:
    """Aggiorna lo snapshot per tutti gli ETF del registro."""
    print(f"Refresh holdings da {RAW_DIR}/ ...")
    frames = [df for entry in iter_entries() if (df := refresh_one(entry)) is not None]

    if not frames:
        raise SystemExit(
            "Nessun file grezzo trovato. Scarica le composizioni in "
            f"{RAW_DIR}/ (vedi i nomi in holdings_registry.REGISTRY)."
        )

    snapshot = pd.concat(frames, ignore_index=True)

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(SNAPSHOT_PATH, index=False)
    print(
        f"\nSnapshot salvato: {SNAPSHOT_PATH} "
        f"({len(snapshot)} righe, {snapshot['fund_isin'].nunique()} ETF)"
    )
    return snapshot


if __name__ == "__main__":
    refresh_all()
