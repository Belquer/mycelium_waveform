"""
voice-to-form  —  tests/conftest.py  v0.1.0
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _synthesise_speech_like(sr: int = 22050, duration_s: float = 2.0) -> np.ndarray:
    """Speech-ish synthetic signal: an asymmetric burst plus a softer trailing burst.

    The asymmetry (different positive vs negative peaks) is the whole
    point — the envelope extraction must detect it.
    """
    n = int(sr * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False)

    # Carrier
    carrier = 0.6 * np.sin(2 * np.pi * 200.0 * t)
    # Asymmetric warp — pushes positive peaks higher than negative
    asymmetric = np.where(carrier > 0, carrier * 1.5, carrier * 0.55)

    # Two amplitude bursts
    burst1 = np.exp(-((t - 0.6) ** 2) / (2 * 0.10 ** 2))
    burst2 = 0.55 * np.exp(-((t - 1.5) ** 2) / (2 * 0.18 ** 2))
    env = burst1 + burst2
    return (asymmetric * env).astype(np.float32)


@pytest.fixture
def synth_wav(tmp_path) -> Path:
    sr = 22050
    y = _synthesise_speech_like(sr=sr, duration_s=2.0)
    path = tmp_path / "synth.wav"
    sf.write(str(path), y, sr, subtype="PCM_16")
    return path


@pytest.fixture
def synth_audio() -> tuple[np.ndarray, int]:
    sr = 22050
    return _synthesise_speech_like(sr=sr, duration_s=2.0), sr


@pytest.fixture
def short_audio() -> tuple[np.ndarray, int]:
    sr = 22050
    y = _synthesise_speech_like(sr=sr, duration_s=0.2)
    return y, sr


@pytest.fixture
def quiet_audio() -> tuple[np.ndarray, int]:
    sr = 22050
    y = _synthesise_speech_like(sr=sr, duration_s=1.0) * 0.001
    return y, sr


@pytest.fixture
def positive_only_audio() -> tuple[np.ndarray, int]:
    """Pathological case: all-positive signal — bottom envelope should be ~0."""
    sr = 22050
    n = int(sr * 1.0)
    t = np.linspace(0, 1.0, n, endpoint=False)
    y = (0.5 + 0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    return y, sr
