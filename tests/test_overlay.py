"""tests/test_overlay.py  v0.1.0"""
from __future__ import annotations

__version__ = "0.1.0"

import numpy as np

from src.audio import extract_envelopes
from src.geometry import GeometryParams
from src.overlay import build_figure, peak_report


def test_build_figure_three_axes(synth_audio):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=300)
    p = GeometryParams(nx=300, n_theta=32)
    fig = build_figure(y, env, p)
    assert len(fig.axes) == 3


def test_peak_report_runs(synth_audio):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=300)
    report = peak_report(y, env, n_peaks=4)
    assert len(report.rows) >= 1
    for row in report.rows:
        assert 0.0 <= row.audio_rel <= 1.0
        assert 0.0 <= row.form_rel <= 1.0


def test_overlay_handles_quiet_audio(quiet_audio):
    y, sr = quiet_audio
    env = extract_envelopes(y, sr, nx=300)
    p = GeometryParams(nx=300, n_theta=32)
    fig = build_figure(y, env, p)
    # Should produce a figure without raising.
    assert fig is not None


def test_overlay_handles_positive_only(positive_only_audio):
    y, sr = positive_only_audio
    env = extract_envelopes(y, sr, nx=300)
    p = GeometryParams(nx=300, n_theta=32)
    fig = build_figure(y, env, p)
    assert fig is not None
