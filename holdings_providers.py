"""
holdings_providers.py
=====================

Estrazione e normalizzazione delle composizioni (holdings) degli ETF a partire
dai file ufficiali pubblicati dagli emittenti.

Principio di design
-------------------
Il *parsing* (file grezzo -> DataFrame normalizzato) e' separato dal *download*
(URL -> file grezzo). Qui vive solo il parsing, che e' puro, deterministico e
testabile offline su un file gia' scaricato. Il download, fragile per natura
(URL che cambiano, misure anti-bot), resta fuori da questo modulo.

Ogni provider (iShares, Vanguard, ...) e' UNA implementazione dell'interfaccia
`HoldingsProvider`: il formato del file e' identico per tutti i fondi dello
stesso emittente, quindi serve un parser per *provider*, non per ETF.

Schema normalizzato in uscita (colonne fisse, indipendenti dal provider):

    ticker        str      ticker cosi' come appare nel file (puo' essere storpiato)
    name          str      nome del titolo
    sector_raw    str      settore nella tassonomia DELL'EMITTENTE (non canonico)
    asset_class   str      vocabolario controllato: Equity / Cash / Derivative / Other
    weight        float    peso in PERCENTUALE (es. 8.13, non 0.0813)
    country_raw   str      paese nella tassonomia DELL'EMITTENTE (non canonico)
    market_value  float    valore di mercato nella valuta del fondo
    currency      str      valuta del titolo
    provider      str      chiave del provider (es. "iShares")

I campi *_raw sono volutamente fedeli alla sorgente: la mappatura verso una
tassonomia canonica (GICS in inglese, ISO paesi) e' uno strato successivo, per
non accoppiare il parser alle scelte di normalizzazione.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

# Colonne dello schema normalizzato, nell'ordine canonico.
SCHEMA: tuple[str, ...] = (
    "ticker",
    "name",
    "sector_raw",
    "asset_class",
    "weight",
    "country_raw",
    "market_value",
    "currency",
    "provider",
)


@dataclass(frozen=True)
class ParsedHoldings:
    """Risultato del parsing di un singolo file di composizione.

    Attributes
    ----------
    holdings : pd.DataFrame
        Righe dei titoli, colonne = SCHEMA.
    as_of : date | None
        Data di riferimento della composizione, estratta dal file.
    provider : str
        Provider che ha prodotto il parsing.
    """

    holdings: pd.DataFrame
    as_of: date | None
    provider: str


class HoldingsProvider(Protocol):
    """Contratto minimo di un provider di composizioni.

    E' un Protocol (tipizzazione strutturale): una classe e' un provider valido
    se espone `name` e `parse`, senza bisogno di ereditare da nulla.
    """

    #: Chiave identificativa del provider (es. "iShares", "Vanguard").
    name: str

    def parse(self, path: str | Path) -> ParsedHoldings:
        """Legge un file grezzo e restituisce le posizioni normalizzate."""
        ...


# ---------------------------------------------------------------------------
# Helper di parsing per il formato numerico italiano
# ---------------------------------------------------------------------------

def _to_float_ita(value: object) -> float:
    """Converte un numero in formato italiano ("1.234,56") in float.

    Gestisce separatore migliaia '.', decimale ',', stringhe vuote e '-'
    (usato da iShares per i campi non applicabili, es. area dei futures).

    >>> _to_float_ita("13.059.961.109,00")
    13059961109.0
    >>> _to_float_ita("8,13")
    8.13
    >>> import math; math.isnan(_to_float_ita("-"))
    True
    """
    if value is None:
        return float("nan")
    s = str(value).strip()
    if s in ("", "-"):
        return float("nan")
    return float(s.replace(".", "").replace(",", "."))


# ---------------------------------------------------------------------------
# Provider iShares (BlackRock)
# ---------------------------------------------------------------------------

class ISharesProvider:
    """Parser per i CSV di composizione iShares (sito regionale italiano).

    Formato atteso:
      - encoding UTF-8 con BOM;
      - riga 0: `Al,"DD/MM/YYYY"` (data di riferimento);
      - riga 1: riga vuota / con soli spazi;
      - riga 2: header in italiano;
      - righe successive: posizioni, tutti i campi tra virgolette, numeri in
        formato italiano.

    Il layout delle colonne del sito iShares italiano puo' variare leggermente
    tra fondi (azionari vs obbligazionari). Qui mappiamo per NOME di colonna,
    non per posizione, cosi' colonne extra o riordinate non rompono il parser.
    """

    name = "iShares"

    # Header italiano del file -> nome nello schema normalizzato.
    _COLMAP = {
        "Ticker dell'emittente": "ticker",
        "Nome": "name",
        "Settore": "sector_raw",
        "Valore di mercato": "market_value",
        "Ponderazione (%)": "weight",
        "Area Geografica": "country_raw",
        "Valuta di mercato": "currency",
    }

    # Asset class iShese (italiano) -> vocabolario controllato.
    _ASSET_CLASS_MAP = {
        "Azionario": "Equity",
        "Contanti": "Cash",
        "Cash Collateral and Margins": "Cash",
        "Futures": "Derivative",
    }

    _SKIPROWS = 2  # righe di preambolo prima dell'header

    def parse(self, path: str | Path) -> ParsedHoldings:
        path = Path(path)

        as_of = self._read_as_of(path)

        # Leggo tutto come stringa: i numeri li converto io, evitando che
        # pandas interpreti male il formato italiano o storpi i ticker.
        raw = pd.read_csv(
            path,
            skiprows=self._SKIPROWS,
            encoding="utf-8-sig",
            dtype=str,
            skip_blank_lines=True,
        )
        raw.columns = [c.strip() for c in raw.columns]

        # Verifico che le colonne attese ci siano (fail-fast e messaggio chiaro).
        attese = set(self._COLMAP) | {"Asset Class"}
        mancanti = attese - set(raw.columns)
        if mancanti:
            raise ValueError(
                f"[iShares] Colonne mancanti nel file {path.name}: {sorted(mancanti)}. "
                f"Colonne trovate: {list(raw.columns)}"
            )

        # Rinomino e normalizzo asset class.
        df = raw.rename(columns=self._COLMAP)
        df["asset_class"] = (
            raw["Asset Class"].str.strip().map(self._ASSET_CLASS_MAP).fillna("Other")
        )

        # Numeri in formato italiano -> float.
        df["weight"] = df["weight"].map(_to_float_ita)
        df["market_value"] = df["market_value"].map(_to_float_ita)

        # Pulizia campi testuali: '-' -> NA (usato dai futures per l'area).
        for col in ("ticker", "name", "sector_raw", "country_raw", "currency"):
            df[col] = df[col].astype("string").str.strip()
            df[col] = df[col].replace({"-": pd.NA, "": pd.NA})

        df["provider"] = self.name

        # Elimino righe spurie (es. riga finale con soli spazi -> nome NA e peso NaN).
        df = df[df["name"].notna() | df["weight"].notna()].copy()

        df = df[list(SCHEMA)].reset_index(drop=True)
        return ParsedHoldings(holdings=df, as_of=as_of, provider=self.name)

    @staticmethod
    def _read_as_of(path: Path) -> date | None:
        """Estrae la data di riferimento dalla prima riga `Al,"DD/MM/YYYY"`."""
        first = path.read_text(encoding="utf-8-sig").splitlines()[0]
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", first)
        if not m:
            return None
        giorno, mese, anno = map(int, m.groups())
        try:
            return datetime(anno, mese, giorno).date()
        except ValueError:
            return None


# Registro dei provider disponibili, per chiave.
_PROVIDERS: dict[str, HoldingsProvider] = {
    ISharesProvider.name: ISharesProvider(),
}


def get_provider(name: str) -> HoldingsProvider:
    """Restituisce il provider registrato con la chiave data.

    >>> get_provider("iShares").name
    'iShares'
    """
    try:
        return _PROVIDERS[name]
    except KeyError:
        disponibili = ", ".join(sorted(_PROVIDERS))
        raise KeyError(f"Provider '{name}' non registrato. Disponibili: {disponibili}")
