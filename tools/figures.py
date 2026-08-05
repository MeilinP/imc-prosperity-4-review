"""
figures.py — one plotting style for the whole review.

A single module rather than per-notebook styling, so that a chart from round 1 and a chart
from round 5 can be put side by side and compared without the reader having to check whether
a difference in appearance means a difference in substance.

Conventions:
  GREY    raw observations — dense, low contrast, never the point of the chart
  BLUE    the series under discussion
  ACCENT  a second series being compared against it
  HI      the thing the chart exists to show: a fitted line, a threshold, a reference level
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

GREY = "#9aa4b2"
BLUE = "#3b7dd8"
ACCENT = "#e0a13a"
HI = "#d1495b"
GRID = "#d8dee6"

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def style() -> None:
    """Apply the shared style. Call once at the top of a notebook."""
    mpl.rcParams.update({
        "figure.dpi": 120,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "600",
        "axes.labelsize": 9,
        "axes.edgecolor": GRID,
        "axes.linewidth": 0.9,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.alpha": 0.7,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def finish(ax, title: str = "", xlabel: str = "", ylabel: str = "",
           legend: bool = False) -> None:
    """Titles, labels, and the two spines that carry no information removed."""
    if title:
        ax.set_title(title, loc="left", pad=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if legend:
        ax.legend(loc="best")


def save(fig, name: str) -> None:
    """Write to assets/<name>.png so the markdown can embed it, and show it inline."""
    ASSETS.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(ASSETS / f"{name}.png")
    plt.show()
