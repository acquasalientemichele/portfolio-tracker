"""
holdings_registry.py
====================

Registro esplicito degli ETF di cui vogliamo la composizione (holdings).

E' la singola fonte di verita' che collega un fondo al suo provider e al file
grezzo da cui estrarre i dati. Aggiungere un ETF = aggiungere una riga qui.

Scelta di design: niente auto-discovery del file a partire dal ticker. Per un
portafoglio di pochi fondi un registro curato e' piu' robusto e piu' difendibile
di uno scraper che indovina URL. Il campo `source` e' il nome del file grezzo
gia' scaricato (in RAW_DIR); in futuro potra' diventare un productId/URL quando
e se aggiungeremo il download automatico.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ETFEntry:
    """Un ETF nel registro.

    Attributes
    ----------
    isin : str
        ISIN del fondo (identificatore stabile, indipendente dalla borsa).
    ticker : str
        Ticker di riferimento (quello che usi altrove nel progetto).
    name : str
        Nome esteso del fondo.
    provider : str
        Chiave del provider in holdings_providers._PROVIDERS (es. "iShares").
    source : str
        Nome del file grezzo in RAW_DIR da cui estrarre la composizione.
    """

    isin: str
    ticker: str
    name: str
    provider: str
    source: str


# Registro degli ETF. Chiave = ISIN del fondo.
# NB: SXR8 (Xetra) e CSSPX (Milano) sono lo stesso fondo -> un solo file.
REGISTRY: dict[str, ETFEntry] = {
    "IE00B5BMR087": ETFEntry(
        isin="IE00B5BMR087",
        ticker="SXR8",
        name="iShares Core S&P 500 UCITS ETF (Acc)",
        provider="iShares",
        source="CSSPX_holdings.csv",
    ),
    # --- ETF registrati, in attesa del rispettivo file grezzo ---
    # Scarica il file dalla pagina del fondo e mettilo in RAW_DIR con questo nome.
    "DE0002635307": ETFEntry(
        isin="DE0002635307",
        ticker="EXSA",
        name="iShares STOXX Europe 600 UCITS ETF (Dist)",
        provider="iShares",
        source="EXSA_holdings.csv",
    ),
    "IE00BK5BQT80": ETFEntry(
        isin="IE00BK5BQT80",
        ticker="VWCE",
        name="Vanguard FTSE All-World UCITS ETF (Acc)",
        provider="Vanguard",  # parser da implementare
        source="VWCE_holdings.json",
    ),
    "IE00BK5BR626": ETFEntry(
        isin="IE00BK5BR626",
        ticker="VFEA",
        name="Vanguard FTSE Emerging Markets UCITS ETF (Acc)",
        provider="Vanguard",  # parser da implementare
        source="VFEA_holdings.json",
    ),
}


def iter_entries() -> list[ETFEntry]:
    """Restituisce gli ETF del registro come lista."""
    return list(REGISTRY.values())
