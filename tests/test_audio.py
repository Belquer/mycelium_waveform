"""tests/test_audio.py  v0.1.0"""
from __future__ import annotations

__version__ = "0.1.0"

import numpy as np
import pytest

from src.audio import (
    extract_envelopes, load_wav, trim_silence, find_envelope_peaks,
)


def test_load_wav_returns_mono_float(synth_wav):
    y, sr = load_wav(str(synth_wav), target_sr=22050)
    assert y.ndim == 1
    assert y.dtype == np.float32
    assert sr == 22050
    assert -1.0 <= y.min() <= y.max() <= 1.0


def test_load_wav_resamples(synth_wav):
    y, sr = load_wav(str(synth_wav), target_sr=8000)
    assert sr == 8000


def test_extract_envelopes_shape(synth_audio):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=700)
    assert env.top.shape == (700,)
    assert env.bottom.shape == (700,)
    assert env.rms.shape == (700,)
    assert 0.0 <= env.top.min() and env.top.max() <= 1.0
    assert 0.0 <= env.bottom.min() and env.bottom.max() <= 1.0


def test_envelopes_jointly_normalised(synth_audio):
    """One of top.max() / bottom.max() must equal 1.0; the other must NOT
    (joint normalisation preserves asymmetry).
    """
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=700)
    joint_max = max(env.top.max(), env.bottom.max())
    assert joint_max == pytest.approx(1.0, abs=1e-3)
    # The smaller side should genuinely be < 1.0 for our asymmetric input.
    smaller = min(env.top.max(), env.bottom.max())
    assert smaller < 0.99


def test_top_bottom_asymmetry_preserved(synth_audio):
    """Top peaks > bottom peaks for our asymmetric signal."""
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=700)
    assert env.top.max() > env.bottom.max()


def test_positive_only_has_zero_bottom(positive_only_audio):
    y, sr = positive_only_audio
    env = extract_envelopes(y, sr, nx=400)
    # Bottom envelope should be near zero (a positive-only signal has no
    # negative peaks).
    assert env.bottom.max() < 0.05
    assert env.top.max() == pytest.approx(1.0, abs=1e-3)


def test_quiet_audio_does_not_crash(quiet_audio):
    y, sr = quiet_audio
    env = extract_envelopes(y, sr, nx=300)
    # Very quiet still resolves to a finite envelope, jointly normalised.
    assert np.isfinite(env.top).all()
    assert np.isfinite(env.bottom).all()


def test_short_audio_handled(short_audio):
    y, sr = short_audio
    env = extract_envelopes(y, sr, nx=200)
    assert env.top.shape == (200,)


def test_trim_silence_preserves_signal(synth_audio):
    y, sr = synth_audio
    padded = np.concatenate([np.zeros(sr // 4, dtype=np.float32), y, np.zeros(sr // 4, dtype=np.float32)])
    trimmed = trim_silence(padded, sr, top_db=30.0)
    # Trimmed should be shorter than padded but not zero.
    assert 0 < trimmed.size < padded.size


def test_find_envelope_peaks(synth_audio):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=600)
    combined = np.maximum(env.top, env.bottom)
    peaks = find_envelope_peaks(combined, n=4)
    assert len(peaks) >= 1
