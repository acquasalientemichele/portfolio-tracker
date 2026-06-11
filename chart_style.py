"""
chart_style.py — stile coerente per tutti i grafici della dashboard.

Ispirato a Bloomberg / FT: sfondo chiaro, tipografia sans-serif, griglia
discreta, palette finanziaria sobria. Importa COLORS e usa le funzioni
style_axis(ax) e add_title(fig, title, subtitle) su ogni grafico.
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

COLORS = {
    'bg':       '#FFFFFF',
    'fg':       '#0F172A',   # testo principale
    'muted':    '#64748B',   # testo secondario, assi
    'grid':     '#E2E8F0',
    'value':    '#0F4C81',   # navy — serie principale
    'invested': '#94A3B8',   # grigio — riferimento
    'benchmark':'#D97706',   # arancio bruciato — benchmark
    'gain':     '#10B981',   # verde area gain
    'loss':     '#EF4444',   # rosso area loss
    'accent':   '#7C3AED',   # viola — secondaria (es. emerging markets)
    'amber': '#F59E0B',
}

# Palette ciclica per allocazioni / serie multiple
PALETTE = ['#0F4C81', '#7C3AED', '#D97706', '#10B981', '#EF4444',
           '#64748B', '#0891B2', '#DB2777']


def apply_global_style():
    """Imposta i default matplotlib. Chiamare una volta a inizio notebook."""
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
        'figure.facecolor': COLORS['bg'],
        'axes.facecolor': COLORS['bg'],
        'axes.edgecolor': COLORS['grid'],
        'axes.labelcolor': COLORS['muted'],
        'xtick.color': COLORS['muted'],
        'ytick.color': COLORS['muted'],
        'axes.titlesize': 12,
        'axes.titleweight': 'bold',
        'axes.titlelocation': 'left',
    })


def style_axis(ax, euro=True, date_axis=True):
    """Applica lo stile base a un axis (spine, griglia, formatters)."""
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(COLORS['grid'])
    ax.tick_params(colors=COLORS['muted'], labelsize=9)
    ax.grid(True, axis='y', color=COLORS['grid'], linewidth=0.6)
    ax.grid(False, axis='x')
    ax.set_axisbelow(True)
    if euro:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'€{v:,.0f}'))
    if date_axis:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    return ax


def add_title(fig, title, subtitle=None, source=None):
    """Aggiunge titolo + sottotitolo (headline) + footer fonte."""
    fig.text(0.075, 0.95, title, fontsize=16, fontweight='bold',
             color=COLORS['fg'], ha='left')
    if subtitle:
        fig.text(0.075, 0.905, subtitle, fontsize=11,
                 color=COLORS['muted'], ha='left')
    if source:
        fig.text(0.075, 0.02, source, fontsize=8.5,
                 color=COLORS['muted'], ha='left', style='italic')
    plt.subplots_adjust(top=0.84, bottom=0.11, left=0.075, right=0.96)


def style_legend(ax, **kwargs):
    """Legenda senza cornice, testo grigio coerente."""
    defaults = dict(loc='upper left', frameon=False, fontsize=9.5)
    defaults.update(kwargs)
    leg = ax.legend(**defaults)
    for text in leg.get_texts():
        text.set_color(COLORS['muted'])
    return leg