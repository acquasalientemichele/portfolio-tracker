"""
template.py — generazione in-memory del workbook Excel del portfolio tracker.

Perché un modulo invece di un file .xlsx statico nel repo:
- unica-fonte-di-verità: la struttura dei fogli (colonne, ordine) resta
  ancorata al codice e non va mai in drift con i validatori di portfolio.py
- l'app su Cloud non ha filesystem persistente: il template va servito come
  bytes generati al volo (st.download_button), non letto da disco
- la stessa infrastruttura genera i dati demo (modalità "prova senza compilare")

Il modulo è puro: nessun `import streamlit`. Restituisce sempre `bytes`,
pronti per st.download_button (template) o per st.session_state (demo).

Struttura del workbook (4 fogli, coerente con i loader esistenti):
  - transactions : date | ticker | isin | name | operation | quantity |
                   price | currency | fees | notes      (letto da pf.load_transactions)
  - settings     : base_currency / benchmark_ticker + blocco target allocation
                                                         (letto da pf.load_settings)
  - ter          : ticker | ter_annual | note            (letto da cst.load_costs, opzionale)
  - bollo_charges: date | amount | notes                 (letto da cst.load_costs, opzionale)

Dipendenze: openpyxl (già in requirements per add_costs_sheets).
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# --------------------------------------------------------------------------- #
# STILE (allineato ad add_costs_sheets.py per coerenza visiva del workbook)
# --------------------------------------------------------------------------- #
NAVY = "1F4E78"
HDR_FILL = PatternFill("solid", start_color=NAVY)
HDR_FONT = Font(bold=True, color="FFFFFF", name="Arial", size=11)
NOTE_FONT = Font(italic=True, color="7F7F7F", name="Arial", size=10)
KEY_FONT = Font(bold=True, name="Arial", size=11)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")

# Colonne del foglio transactions, nell'ordine atteso da pf.REQUIRED_COLS
# (+ 'notes', opzionale ma utile all'utente per annotare i PAC).
TX_HEADERS = ["date", "ticker", "isin", "name", "operation",
              "quantity", "price", "currency", "fees", "notes"]

# Anagrafica di default dei due ETF del PAC di riferimento. Usata sia per
# pre-compilare ter/settings nel template, sia per generare la demo.
_ETF_META = {
    "VWCE.DE": {
        "isin": "IE00BK5BQT80",
        "name": "Vanguard FTSE All-World (Acc)",
        "ter": 0.0022,
        "ter_note": "0,22% TER (Vanguard FTSE All-World)",
        "target": 0.80,
    },
    "VFEA.DE": {
        "isin": "IE00BK5BR733",
        "name": "Vanguard FTSE Emerging Markets (Acc)",
        "ter": 0.0022,
        "ter_note": "0,22% TER (Vanguard FTSE Emerging Markets)",
        "target": 0.20,
    },
}


# --------------------------------------------------------------------------- #
# HELPER DI STILE
# --------------------------------------------------------------------------- #
def _style_header_row(ws, n_cols: int, row: int = 1) -> None:
    """Applica fill navy + font bianco grassetto + bordo alla riga header."""
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _set_widths(ws, widths: dict[str, int]) -> None:
    """Imposta la larghezza delle colonne. widths: {'A': 12, ...}."""
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


# --------------------------------------------------------------------------- #
# COSTRUZIONE DEI SINGOLI FOGLI
# --------------------------------------------------------------------------- #
def _write_transactions_sheet(wb: Workbook, rows: list[dict]) -> None:
    """Crea il foglio 'transactions' con header + righe fornite.

    Ogni riga è un dict con le chiavi di TX_HEADERS (notes opzionale).
    Applica number-format a date/quantity/price/fees per un'esperienza
    di compilazione pulita in Excel.
    """
    ws = wb.active
    ws.title = "transactions"
    ws.append(TX_HEADERS)
    _style_header_row(ws, len(TX_HEADERS))

    for r in rows:
        ws.append([r.get(h) for h in TX_HEADERS])

    # Number format per colonna (date=A, quantity=F, price=G, fees=I)
    for i in range(2, ws.max_row + 1):
        ws.cell(row=i, column=1).number_format = "yyyy-mm-dd"
        ws.cell(row=i, column=6).number_format = "#,##0.000000"
        ws.cell(row=i, column=7).number_format = "#,##0.0000"
        ws.cell(row=i, column=9).number_format = "#,##0.00"

    _set_widths(ws, {"A": 12, "B": 10, "C": 16, "D": 34, "E": 11,
                     "F": 12, "G": 12, "H": 10, "I": 8, "J": 22})
    ws.freeze_panes = "A2"


def _write_settings_sheet(wb: Workbook,
                          base_currency: str,
                          benchmark_ticker: str,
                          targets: dict[str, float]) -> None:
    """Crea il foglio 'settings' nel formato atteso da pf.load_settings.

    Layout (header=None lato lettura):
        base_currency     EUR
        benchmark_ticker  VWCE.DE
        <riga vuota>
        ticker            target_weight
        VWCE.DE           0.80
        VFEA.DE           0.20

    pf.load_settings cerca le chiavi note in col.A e il blocco allocation
    a partire dalla riga header 'ticker'/'...weight'.
    """
    ws = wb.create_sheet("settings")

    ws.append(["base_currency", base_currency])
    ws.append(["benchmark_ticker", benchmark_ticker])
    ws.append([])  # separatore

    header_row = ws.max_row + 1
    ws.append(["ticker", "target_weight"])
    _style_header_row(ws, 2, row=header_row)

    for tkr, w in targets.items():
        ws.append([tkr, w])
    for i in range(header_row + 1, ws.max_row + 1):
        ws.cell(row=i, column=2).number_format = "0.00"

    # Grassetto sulle chiavi di parametro
    ws.cell(row=1, column=1).font = KEY_FONT
    ws.cell(row=2, column=1).font = KEY_FONT
    _set_widths(ws, {"A": 20, "B": 16})


def _write_ter_sheet(wb: Workbook, tickers: list[str]) -> None:
    """Crea il foglio 'ter' (informativo, opzionale): ticker | ter_annual | note."""
    ws = wb.create_sheet("ter")
    ws.append(["ticker", "ter_annual", "note"])
    _style_header_row(ws, 3)
    for t in tickers:
        meta = _ETF_META.get(t, {"ter": 0.0, "ter_note": ""})
        ws.append([t, meta["ter"], meta["ter_note"]])
    for i in range(2, ws.max_row + 1):
        ws.cell(row=i, column=2).number_format = "0.00%"
    _set_widths(ws, {"A": 12, "B": 14, "C": 46})


def _write_bollo_sheet(wb: Workbook, rows: list[dict] | None = None) -> None:
    """Crea il foglio 'bollo_charges' (opzionale): date | amount | notes.

    Se rows è None lascia solo header + una riga-nota esplicativa: l'utente
    inserirà qui gli addebiti reali del bollo che vede su Trade Republic.
    """
    ws = wb.create_sheet("bollo_charges")
    ws.append(["date", "amount", "notes"])
    _style_header_row(ws, 3)

    if rows:
        for r in rows:
            ws.append([r.get("date"), r.get("amount"), r.get("notes")])
        for i in range(2, ws.max_row + 1):
            ws.cell(row=i, column=1).number_format = "yyyy-mm-dd"
            ws.cell(row=i, column=2).number_format = "#,##0.00"
    else:
        ws.append([None, None,
                   "Inserisci qui ogni addebito del bollo che vedi su TR "
                   "(facoltativo)"])
        ws["A2"].number_format = "yyyy-mm-dd"
        ws["B2"].number_format = "#,##0.00"
        ws["C2"].font = NOTE_FONT

    _set_widths(ws, {"A": 14, "B": 12, "C": 52})


def _workbook_to_bytes(wb: Workbook) -> bytes:
    """Serializza il workbook in memoria e restituisce i bytes .xlsx."""
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# API PUBBLICA
# --------------------------------------------------------------------------- #
def build_template_workbook(with_examples: bool = True) -> bytes:
    """Genera il workbook TEMPLATE che l'utente scarica e compila.

    Contiene i 4 fogli con intestazioni corrette, settings/ter pre-compilati
    con i default VWCE/VFEA (80/20), e — se with_examples=True — due righe di
    esempio nel foglio transactions per mostrare il formato atteso.

    Returns:
        bytes del file .xlsx, pronti per st.download_button.
    """
    example_rows: list[dict] = []
    if with_examples:
        example_rows = [
            {"date": date(2025, 11, 10), "ticker": "VWCE.DE",
             "isin": "IE00BK5BQT80", "name": "Vanguard FTSE All-World (Acc)",
             "operation": "BUY", "quantity": 10.00, "price": 144.50,
             "currency": "EUR", "fees": 1.00, "notes": "ESEMPIO — sostituisci"},
            {"date": date(2025, 12, 8), "ticker": "VFEA.DE",
             "isin": "IE00BK5BR733",
             "name": "Vanguard FTSE Emerging Markets (Acc)",
             "operation": "BUY", "quantity": 20.00, "price": 70.20,
             "currency": "EUR", "fees": 1.00, "notes": "ESEMPIO — sostituisci"},
        ]

    wb = Workbook()
    _write_transactions_sheet(wb, example_rows)
    _write_settings_sheet(
        wb, base_currency="EUR", benchmark_ticker="VWCE.DE",
        targets={t: m["target"] for t, m in _ETF_META.items()},
    )
    _write_ter_sheet(wb, list(_ETF_META.keys()))
    _write_bollo_sheet(wb, rows=None)
    return _workbook_to_bytes(wb)


def build_demo_workbook() -> bytes:
    """Genera un workbook DEMO con storia PAC sintetica ma plausibile.

    Serve la modalità "prova senza compilare": un amico apre l'app, clicca
    "Prova con dati demo" e vede una dashboard popolata senza dover creare
    un file Excel.

    I ticker sono reali (VWCE.DE, VFEA.DE) così fetch_prices ottiene prezzi
    veri da yfinance; i prezzi di carico qui sotto servono solo come cost
    basis e sono plausibili ma non storicamente esatti (irrilevante per una
    demo). PAC mensile ~350 €/mese in split 80/20 su ~9 mesi.

    Returns:
        bytes del file .xlsx, da mettere in st.session_state["workbook_bytes"].
    """
    vwce = _ETF_META["VWCE.DE"]
    vfea = _ETF_META["VFEA.DE"]

    # (anno, mese, giorno, ticker, quantità, prezzo di carico)
    plan = [
        (2025, 5, 12, "VWCE.DE", 1.95, 143.10),
        (2025, 6, 10, "VWCE.DE", 1.94, 144.20),
        (2025, 6, 10, "VFEA.DE", 1.00, 69.40),
        (2025, 7, 10, "VWCE.DE", 1.90, 147.00),
        (2025, 8, 11, "VWCE.DE", 1.93, 145.30),
        (2025, 8, 11, "VFEA.DE", 1.02, 68.90),
        (2025, 9, 10, "VWCE.DE", 1.88, 148.80),
        (2025, 10, 10, "VWCE.DE", 1.85, 151.20),
        (2025, 10, 10, "VFEA.DE", 0.98, 71.60),
        (2025, 11, 10, "VWCE.DE", 1.90, 147.40),
        (2025, 12, 10, "VWCE.DE", 1.92, 145.90),
        (2025, 12, 10, "VFEA.DE", 1.01, 69.80),
        (2026, 1, 12, "VWCE.DE", 1.89, 148.10),
    ]

    rows: list[dict] = []
    for y, mo, d, t, qty, px in plan:
        meta = vwce if t == "VWCE.DE" else vfea
        rows.append({
            "date": date(y, mo, d), "ticker": t,
            "isin": meta["isin"], "name": meta["name"],
            "operation": "BUY", "quantity": qty, "price": px,
            "currency": "EUR", "fees": 1.00,
            "notes": f"PAC demo {y}-{mo:02d}",
        })

    wb = Workbook()
    _write_transactions_sheet(wb, rows)
    _write_settings_sheet(
        wb, base_currency="EUR", benchmark_ticker="VWCE.DE",
        targets={"VWCE.DE": vwce["target"], "VFEA.DE": vfea["target"]},
    )
    _write_ter_sheet(wb, ["VWCE.DE", "VFEA.DE"])
    _write_bollo_sheet(wb, rows=None)
    return _workbook_to_bytes(wb)


if __name__ == "__main__":
    # Smoke test manuale: scrive i due file su disco per ispezione a occhio.
    with open("transactions_template.xlsx", "wb") as f:
        f.write(build_template_workbook())
    with open("transactions_demo.xlsx", "wb") as f:
        f.write(build_demo_workbook())
    print("Scritti: transactions_template.xlsx, transactions_demo.xlsx")
