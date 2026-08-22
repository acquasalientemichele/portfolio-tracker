"""
holdings_canonical.py
=====================

Normalizzazione delle tassonomie grezze dei provider verso uno standard comune,
condizione necessaria per confrontare ETF di emittenti diversi.

Problema
--------
Ogni provider nomina settori e paesi a modo suo. iShares (sito italiano) scrive
"IT", "Generi di largo consumo", "Regno unito"; Vanguard usera' GICS in inglese;
yfinance un'altra convenzione ancora. Confrontare "IT" con "Technology" darebbe
un overlap falso. Qui portiamo tutto a una chiave canonica.

Design
------
- Settori -> 11 settori GICS in inglese (+ un bucket "Cash & Derivatives").
- Paesi -> codice ISO-3166 alpha-2 come CHIAVE canonica; nome inglese e regione
  derivano dall'ISO. Normalizzare sull'ISO (non sul nome) e' robusto: e' l'unico
  identificatore stabile.
- Le mappe sono un'UNIONE di grafie: quando aggiungeremo Vanguard/yfinance
  basta aggiungere le loro grafie qui (le stringhe non collidono tra lingue).
- Comportamento *fail-soft*: un valore non mappato NON rompe nulla. Viene tenuto
  grezzo e segnalato, cosi' lo si aggiunge alla mappa senza perdere dati.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Settori -> GICS (inglese)
# ---------------------------------------------------------------------------
SECTOR_MAP: dict[str, str] = {
    # iShares (italiano)
    "Comunicazione": "Communication Services",
    "Consumi Discrezionali": "Consumer Discretionary",
    "Generi di largo consumo": "Consumer Staples",
    "Energia": "Energy",
    "Finanziari": "Financials",
    "Salute": "Health Care",
    "Industriali": "Industrials",
    "IT": "Information Technology",
    "Materiali": "Materials",
    "Immobili": "Real Estate",
    "Imprese di servizi di pubblica utilita'": "Utilities",
    "Imprese di servizi di pubblica utilità": "Utilities",  # con accento
    "Liquidità e/o derivati": "Cash & Derivatives",
    "Liquidita' e/o derivati": "Cash & Derivatives",
}

# ---------------------------------------------------------------------------
# Paesi -> ISO-3166 alpha-2 (chiave canonica)
# ---------------------------------------------------------------------------
COUNTRY_TO_ISO: dict[str, str] = {
    # iShares (italiano)
    "Australia": "AU",
    "Austria": "AT",
    "Belgio": "BE",
    "Danimarca": "DK",
    "Finlandia": "FI",
    "Francia": "FR",
    "Georgia": "GE",
    "Germania": "DE",
    "Irlanda": "IE",
    "Italia": "IT",
    "Messico": "MX",
    "Norvegia": "NO",
    "Paesi Bassi": "NL",
    "Polonia": "PL",
    "Portogallo": "PT",
    "Regno unito": "GB",
    "Regno Unito": "GB",
    "Spagna": "ES",
    "Stati Uniti": "US",
    "Svezia": "SE",
    "Svizzera": "CH",
    "Unione Europea": "EU",  # pseudo-codice: riga cash in EUR, non un vero paese
}

# ISO -> nome inglese canonico.
ISO_TO_NAME: dict[str, str] = {
    "AU": "Australia", "AT": "Austria", "BE": "Belgium", "DK": "Denmark",
    "FI": "Finland", "FR": "France", "GE": "Georgia", "DE": "Germany",
    "IE": "Ireland", "IT": "Italy", "MX": "Mexico", "NO": "Norway",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "GB": "United Kingdom",
    "ES": "Spain", "US": "United States", "SE": "Sweden", "CH": "Switzerland",
    "EU": "European Union",
}

# ISO -> macro-regione (per la diversificazione geografica aggregata).
ISO_TO_REGION: dict[str, str] = {
    "US": "North America",
    "MX": "Latin America",
    "AU": "Asia-Pacific",
    "AT": "Europe", "BE": "Europe", "DK": "Europe", "FI": "Europe",
    "FR": "Europe", "DE": "Europe", "IE": "Europe", "IT": "Europe",
    "NO": "Europe", "NL": "Europe", "PL": "Europe", "PT": "Europe",
    "GB": "Europe", "ES": "Europe", "SE": "Europe", "CH": "Europe",
    "GE": "Europe",
    "EU": "Supranational",
}


def canonicalize(df: pd.DataFrame, *, verbose: bool = True) -> pd.DataFrame:
    """Aggiunge colonne canoniche a uno snapshot di holdings.

    Colonne aggiunte:
        sector       str   settore GICS in inglese
        country_iso  str   codice ISO-3166 alpha-2
        country      str   nome inglese del paese
        region       str   macro-regione

    Le colonne grezze (sector_raw, country_raw) restano, per tracciabilita'.
    Valori non mappati: tenuti grezzi (sector) o marcati Unknown (region) e
    segnalati a schermo se verbose=True.

    Parameters
    ----------
    df : pd.DataFrame
        Snapshot con almeno le colonne `sector_raw` e `country_raw`.
    verbose : bool
        Se True, stampa gli eventuali valori non mappati.
    """
    df = df.copy()

    # --- Settori ---
    df["sector"] = df["sector_raw"].map(SECTOR_MAP)
    non_mappati_settore = sorted(
        set(df.loc[df["sector"].isna() & df["sector_raw"].notna(), "sector_raw"])
    )
    df["sector"] = df["sector"].fillna(df["sector_raw"])  # fail-soft

    # --- Paesi (normalizzati sull'ISO) ---
    df["country_iso"] = df["country_raw"].map(COUNTRY_TO_ISO)
    non_mappati_paese = sorted(
        set(df.loc[df["country_iso"].isna() & df["country_raw"].notna(), "country_raw"])
    )
    df["country"] = df["country_iso"].map(ISO_TO_NAME).fillna(df["country_raw"])
    df["region"] = df["country_iso"].map(ISO_TO_REGION).fillna("Unknown")

    if verbose:
        if non_mappati_settore:
            print(f"[canonical] settori non mappati: {non_mappati_settore}")
        if non_mappati_paese:
            print(f"[canonical] paesi non mappati: {non_mappati_paese}")
        if not non_mappati_settore and not non_mappati_paese:
            print("[canonical] ok: tutti i settori e i paesi sono mappati.")

    return df
