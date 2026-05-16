"""
voice-to-form  —  src/overlay.py  v0.1.0

Diagnostic overlay — the three stacked plots that catch proportion
errors before export.  Required by Part 4 of the spec; the Export tab
is gated on the user opening Verify and ticking "Reviewed".

  Plot 1 (top):    original audio waveform, x-axis scaled to mm
  Plot 2 (middle): form's side silhouette (top_r_v above 0, -bottom_r_v below)
  Plot 3 (bottom): direct overlay — audio in semi-transparent purple
                   under the form's top/bottom envelopes traced in red.

Returns a matplotlib Figure for embedding in the Verify tab (FigureCanvas)
and a numerical PeakReport for the side panel.

This module is the diagnostic that caught proportion bugs during
development.  Treat its appearance as part of the artist's QA flow,
not as decoration.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")  # default backend; the GUI re-binds to Qt-Agg.
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from .audio import Envelopes, find_envelope_peaks
from .geometry import GeometryParams, silhouette

print(f"[voice-to-form] overlay.py v{__version__}", file=sys.stderr)


WARN_THRESHOLD = 0.10  # 10% disagreement on any major peak triggers a warning


@dataclass
class PeakRow:
    rank: int
    audio_rel: float        # relative to audio's max combined envelope = 1.00
    form_rel: float         # relative to the form's max (top or bottom) radius
    delta: float            # form_rel - audio_rel
    flagged: bool           # |delta| > WARN_THRESHOLD

    def fmt(self) -> str:
        flag = "  ⚠" if self.flagged else ""
        return (
            f"Peak {self.rank}:  audio rel {self.audio_rel:0.2f}   "
            f"form rel {self.form_rel:0.2f}   Δ {self.delta:+0.2f}{flag}"
        )


@dataclass
class PeakReport:
    rows: list[PeakRow] = field(default_factory=list)
    any_flagged: bool = False

    def as_text(self) -> str:
        if not self.rows:
            return "(no peaks detected)"
        lines = [r.fmt() for r in self.rows]
        if self.any_flagged:
            lines.append("")
            lines.append(
                "⚠  At least one peak disagrees by more than "
                f"{int(WARN_THRESHOLD*100)}%.  Consider checking smoothing "
                "sigmas, the hop_ms window, or whether your audio has a long "
                "near-silence that's pulling MIN_R upward."
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------

def build_figure(
    y: np.ndarray,
    envelopes: Envelopes,
    params: GeometryParams,
    figsize: tuple[float, float] = (9.5, 7.5),
) -> Figure:
    """Build the three-stack diagnostic figure."""
    xs, top_r_v_mm, bottom_r_v_mm = silhouette(envelopes, params)

    fig = Figure(figsize=figsize, dpi=110)
    gs = fig.add_gridspec(3, 1, hspace=0.45)

    # --- Plot 1: audio waveform, x-scaled to form length ----------------
    ax1 = fig.add_subplot(gs[0])
    audio_x = np.linspace(0.0, params.length_mm, num=len(y))
    # Scale audio amplitude to match form's MAX_R for visual comparison.
    audio_scaled = y * params.max_r_mm
    ax1.plot(audio_x, audio_scaled, color="#444", lw=0.5)
    ax1.axhline(0, color="#888", lw=0.4)
    ax1.set_title("audio waveform (amplitude → mm)", fontsize=10)
    ax1.set_xlim(0, params.length_mm)
    ax1.set_ylabel("mm")

    # --- Plot 2: form silhouette ----------------------------------------
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.fill_between(xs, 0, top_r_v_mm, color="#d33", alpha=0.85)
    ax2.fill_between(xs, 0, -bottom_r_v_mm, color="#933", alpha=0.85)
    ax2.axhline(0, color="#000", lw=0.4)
    ax2.set_title(
        f"form side silhouette  ·  length {params.length_mm:.0f} mm  ·  "
        f"min {params.min_r_mm:.1f} mm / max {params.max_r_mm:.1f} mm",
        fontsize=10,
    )
    ax2.set_xlim(0, params.length_mm)
    ax2.set_ylabel("mm")

    # --- Plot 3: direct overlay -----------------------------------------
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.plot(audio_x, audio_scaled, color="#7a3aa8", lw=0.45, alpha=0.45,
             label="audio (semi-transparent)")
    ax3.plot(xs, top_r_v_mm, color="#d33", lw=1.4, label="form top envelope")
    ax3.plot(xs, -bottom_r_v_mm, color="#d33", lw=1.4, label="form bottom envelope")
    ax3.axhline(0, color="#000", lw=0.4)
    ax3.set_title("direct overlay — audio (purple) under form envelopes (red)", fontsize=10)
    ax3.set_xlim(0, params.length_mm)
    ax3.set_xlabel("position along form (mm)")
    ax3.set_ylabel("mm")
    ax3.legend(loc="lower right", fontsize=7, framealpha=0.85)

    return fig


# --------------------------------------------------------------------------
# Numerical peak report
# --------------------------------------------------------------------------

def peak_report(y: np.ndarray, envelopes: Envelopes, n_peaks: int = 6) -> PeakReport:
    """Compute the audio-vs-form peak proportion table.

    Audio peaks are detected on a coarse envelope of |y|.  Form peaks
    are detected on max(top, bottom).  We align them by sorted position
    along x (so peak 1 = leftmost, etc.), normalise each side to its
    own max, and flag rows where they disagree by > WARN_THRESHOLD.
    """
    combined = np.maximum(envelopes.top, envelopes.bottom)
    form_peak_ix = sorted(find_envelope_peaks(combined, n=n_peaks))
    if not form_peak_ix:
        return PeakReport()

    # Audio peaks: down-sample |y| to envelopes.nx so peak indices line up.
    audio_env = _envelope_of_abs(y, envelopes.nx)
    audio_peak_ix = sorted(find_envelope_peaks(audio_env, n=n_peaks))
    if not audio_peak_ix:
        return PeakReport()

    # Pair them by rank along the axis.  If counts differ, pair what we can.
    pairs = list(zip(audio_peak_ix, form_peak_ix))

    audio_max = float(audio_env.max() + 1e-9)
    form_max = float(combined.max() + 1e-9)

    rows: list[PeakRow] = []
    any_flagged = False
    for rank, (ai, fi) in enumerate(pairs, start=1):
        a_rel = float(audio_env[ai] / audio_max)
        f_rel = float(combined[fi] / form_max)
        delta = f_rel - a_rel
        flagged = abs(delta) > WARN_THRESHOLD
        rows.append(PeakRow(rank=rank, audio_rel=a_rel, form_rel=f_rel,
                            delta=delta, flagged=flagged))
        any_flagged = any_flagged or flagged

    return PeakReport(rows=rows, any_flagged=any_flagged)


def _envelope_of_abs(y: np.ndarray, nx: int) -> np.ndarray:
    """Quick |y| envelope at length nx for peak alignment."""
    if y.size == 0:
        return np.zeros(nx, dtype=np.float32)
    hop = max(1, len(y) // nx)
    usable = (len(y) // hop) * hop
    frames = np.abs(y[:usable]).reshape(-1, hop)
    env = frames.max(axis=1)
    if len(env) == nx:
        return env.astype(np.float32)
    xp = np.linspace(0, 1, num=len(env))
    x = np.linspace(0, 1, num=nx)
    return np.interp(x, xp, env).astype(np.float32)


# --------------------------------------------------------------------------
# Convenience: save as PNG (used by library thumbnail)
# --------------------------------------------------------------------------

def save_png(fig: Figure, path: str) -> str:
    fig.savefig(path, bbox_inches="tight", dpi=120)
    return path
