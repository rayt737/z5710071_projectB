"""Shared FT-style plotting module for Part A figures.

Provides a consistent, professional design system across all figures:
- Light background, minimal gridlines, no top/right spines
- Restrained colour palette (navy, warm accent, greys)
- Dollar/percent axis formatting
- Self-contained captions and labels

Usage:
    import src.style as sty
    fig, ax = sty.new_fig()
    ax.plot(...)
    sty.save_fig(fig, "my_figure.png", caption="Source: ...")
"""
from __future__ import annotations

import math
import pathlib
import textwrap

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------------
# Colour palette (FT-esque: navy primary, warm accent, greys for references)
# ---------------------------------------------------------------------------
NAVY = "#1a1a2e"
CORAL = "#e76f51"
AMBER = "#f4a261"
GREY = "#999999"
LIGHT_GREY = "#e0e0e0"
BG = "#fafafa"  # off-white background

PALETTE = [NAVY, CORAL, AMBER, "#264653", "#2a9d8f"]

# ---------------------------------------------------------------------------
# Typography defaults
# ---------------------------------------------------------------------------
FONT_TITLE = 14
FONT_LABEL = 10
FONT_CAPTION = 8
FONT_LEGEND = 9

# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------

def _apply_ft_style():
    """Set global matplotlib rcParams for the FT look."""
    mpl.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "axes.edgecolor": GREY,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.linestyle": "--",
        "grid.linewidth": 0.4,
        "grid.color": LIGHT_GREY,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "font.family": "sans-serif",
        "font.size": FONT_LABEL,
    })

_apply_ft_style()


def new_fig(figsize: tuple[float, float] = (10, 6)) -> tuple[plt.Figure, plt.Axes]:
    """Create a new figure+axes with FT styling (top+right spines removed)."""
    fig, ax = plt.subplots(figsize=figsize)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return fig, ax


def format_date_axis(
    ax: plt.Axes,
    max_ticks: int = 8,
    rotation: float = 0,
    labelsize: float | None = None,
) -> None:
    """Clean 'Jan 2021'-style date axis with bounded tick density.

    The month interval is derived from the axis span (matplotlib date units are
    float days), so a 3-year window and a 4-year window both land on month
    boundaries without cramming ticks (prompt_09 item 1).
    """
    xmin, xmax = ax.get_xlim()
    span_months = max(round((xmax - xmin) / 30.44), 1)
    interval = max(1, math.ceil(span_months / max_ticks))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(axis="x", rotation=rotation)
    if labelsize is not None:
        ax.tick_params(axis="x", labelsize=labelsize)


def save_fig(
    fig: plt.Figure,
    filename: str,
    results_dir: str | pathlib.Path = "results/figures",
    caption: str = "",
    dpi: int = 150,
) -> pathlib.Path:
    """Save figure with tight layout and optional caption below.

    The caption is placed below the axes using fig.text so it renders
    inside the saved image. Long single-line captions are wrapped to roughly
    the figure width so ``bbox_inches="tight"`` never stretches the saved
    canvas out to the caption's full single-line length (prompt_09 item 6).
    """
    outdir = pathlib.Path(results_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    caption_lines = 1
    if caption:
        width = max(40, int(fig.get_figwidth() * 12))
        caption = "\n".join(
            textwrap.fill(line, width=width) for line in caption.splitlines())
        caption_lines = caption.count("\n") + 1
        fig.text(
            0.05, 0.01, caption, fontsize=FONT_CAPTION, color=GREY,
            ha="left", va="bottom",
        )
    fig.tight_layout(rect=[0, 0.03 + 0.03 * (caption_lines - 1), 1, 1])
    path = outdir / filename
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def label_end_values(
    ax: plt.Axes,
    entries: list[tuple[str, float, str]],
    x: object,
    fmt: str = "$%.2f",
    min_gap_px: float = 14,
    fontsize: float = 7.5,
    extend_axis: float = 0.08,
    fontweight: str | None = None,
) -> None:
    """Label each line's final value at the right edge with collision avoidance.

    Ported from Part A's `_plot_growth_of_1` (run_part_a.py ~line 224) so every
    Part B growth-of-$1-style figure shares the same end-labelling:
    - one label per entry, placed at the rightmost data x;
    - `$X.XX` format, color-matched to its line;
    - labels are pushed upward (with a leader line when nudged) so no two
      labels sit closer than ``min_gap_px`` pixels;
    - the x-axis is extended to give the label text room.

    Args:
        ax: the Axes the lines live on.
        entries: iterable of (text, final_value, color) tuples, one per line.
        x: the data-x at which each line ends (its last date).
        fmt: how to format ``final_value``.
        min_gap_px: minimum vertical separation between labels, in pixels.
        extend_axis: fraction of the x-range to add on the right for label room.
    """
    entries = sorted(entries, key=lambda e: e[1])
    if not entries:
        return

    fig = ax.figure
    fig.canvas.draw()
    data_to_pixel = ax.transData.transform
    actual_pix_ys = [data_to_pixel((0, v))[1] for _, v, _ in entries]

    # Bottom-up placement: track the last placed label's pixel-y and push the
    # next label up until it clears MIN_GAP_PX (local pixel<->data ratio).
    final_ys: list[float] = []
    placed_pix: float | None = None
    for i, (_, actual_y, _) in enumerate(entries):
        pix_here = actual_pix_ys[i]
        pix_plus_1 = data_to_pixel((0, actual_y + 1))[1]
        dpy = max(abs(pix_here - pix_plus_1), 0.01)  # pixels per data-unit
        if placed_pix is None or (pix_here - placed_pix) >= min_gap_px:
            placed_y = actual_y
            placed_pix = pix_here
        else:
            needed_data = (min_gap_px - (pix_here - placed_pix)) / dpy
            placed_y = actual_y + needed_data
            placed_pix = data_to_pixel((0, placed_y))[1]
        final_ys.append(placed_y)

    for (text, actual_y, color), display_y in zip(entries, final_ys):
        nudged = abs(display_y - actual_y) > 0.02
        if nudged:
            ax.plot([x, x], [actual_y, display_y], color=color,
                    linewidth=0.6, alpha=0.45)
        ax.annotate(
            fmt % actual_y,
            xy=(x, actual_y),
            xytext=(8, 0),
            textcoords="offset points",
            fontsize=fontsize,
            color=color,
            va="center",
            fontweight=fontweight,
        )

    x_min, x_max = ax.get_xlim()
    ax.set_xlim(x_min, x_max + (x_max - x_min) * extend_axis)


def fmt_dollar(x, _pos=None):
    """Format y-axis as plain dollar amounts."""
    if abs(x) >= 1e6:
        return f"${x/1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"${x/1e3:.0f}K"
    return f"${x:.2f}"


def fmt_pct(x, _pos=None):
    """Format y-axis as percentage."""
    return f"{x:.1f}%"


def fmt_plain(x, _pos=None):
    """Format y-axis as plain number (no scientific notation)."""
    if abs(x) >= 1e6:
        return f"{x/1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"{x/1e3:.0f}K"
    return f"{x:,.0f}"


def dollar_formatter() -> mticker.FuncFormatter:
    return mticker.FuncFormatter(fmt_dollar)


def pct_formatter() -> mticker.FuncFormatter:
    return mticker.FuncFormatter(fmt_pct)


def plain_formatter() -> mticker.FuncFormatter:
    return mticker.FuncFormatter(fmt_plain)
