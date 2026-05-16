"""
voice-to-form  —  src/audio.py  v0.1.0

Audio I/O and envelope extraction for the shared-spine elliptical sweep.

The envelope-extraction algorithm here is load-bearing.  See README
"Why the diagnostic overlay exists" for the history.  Do not change
the architecture casually:

  - top_env[i]    = max of POSITIVE samples in window i
  - bottom_env[i] = abs(min of NEGATIVE samples in window i)
  - rms_env[i]    = sqrt(mean(samples**2)) in window i

These three are computed *separately*.  In particular top/bottom are
NOT taken from abs(samples) — speech has genuinely different positive
and negative peaks and conflating them produces a symmetric "table-leg"
form.

The two halves are then normalised JOINTLY to max(both) so their
relative asymmetry is preserved.  Scaling is linear (gamma = 1.0):
earlier iterations used gamma > 1 to "emphasise" loud peaks but it
overshoots and the form stops looking like the audio.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.ndimage import gaussian_filter1d

# Print version on import — visible in the boot log so users can verify
# which build is loaded.  Per the user's global versioning rule.
print(f"[voice-to-form] audio.py v{__version__}", file=sys.stderr)


@dataclass
class Envelopes:
    """Container for the three per-window envelopes plus metadata."""

    top: np.ndarray          # shape (NX,), 0..1, JOINTLY normalised with bottom
    bottom: np.ndarray       # shape (NX,), 0..1, JOINTLY normalised with top
    rms: np.ndarray          # shape (NX,), 0..1 of its own max (display only)
    sample_rate: int
    duration_s: float
    hop_ms: float
    nx: int

    def as_dict(self) -> dict:
        return {
            "top": self.top.tolist(),
            "bottom": self.bottom.tolist(),
            "rms": self.rms.tolist(),
            "sample_rate": self.sample_rate,
            "duration_s": self.duration_s,
            "hop_ms": self.hop_ms,
            "nx": self.nx,
        }


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_wav(path: str | Path, target_sr: int = 22050) -> tuple[np.ndarray, int]:
    """Load a WAV file as mono float32 in [-1, 1].

    Anything non-mono is averaged across channels.  Anything not at
    target_sr is resampled (librosa).
    """
    import librosa
    path = str(path)
    y, sr = librosa.load(path, sr=target_sr, mono=True)
    y = y.astype(np.float32, copy=False)
    return y, sr


def trim_silence(y: np.ndarray, sr: int, top_db: float = 30.0) -> np.ndarray:
    """Trim leading/trailing silence at ``top_db`` below the peak."""
    import librosa
    trimmed, _ = librosa.effects.trim(y, top_db=top_db)
    # Guard against pathological case where the whole clip trims to zero.
    if trimmed.size < int(0.05 * sr):
        return y
    return trimmed


# --------------------------------------------------------------------------
# Envelope extraction — the load-bearing routine
# --------------------------------------------------------------------------

def extract_envelopes(
    y: np.ndarray,
    sr: int,
    hop_ms: float = 3.0,
    nx: int = 700,
    digital_jitter_sigma: float = 0.4,
    length_smooth_sigma: float = 0.6,
    gamma: float = 1.0,
) -> Envelopes:
    """Extract top/bottom/rms envelopes per the shared-spine spec.

    Parameters mirror the README — see module docstring.  The defaults
    are the values that worked across many iterations; tune carefully.

    Returns three arrays of length ``nx``:
      - top, bottom: jointly normalised to max(top∪bottom), in [0, 1]
      - rms: normalised to its own max, in [0, 1] (display only)
    """
    if y.ndim != 1:
        y = y.mean(axis=tuple(range(1, y.ndim)))

    hop = max(1, int(round(sr * hop_ms / 1000.0)))
    n_windows = max(1, len(y) // hop)
    # Trim the trailing partial window so all three envelopes have the
    # same length.
    usable = n_windows * hop
    frames = y[:usable].reshape(n_windows, hop)

    pos = np.where(frames > 0, frames, 0.0)
    neg = np.where(frames < 0, frames, 0.0)

    top_raw = pos.max(axis=1)
    bottom_raw = np.abs(neg.min(axis=1))
    rms_raw = np.sqrt(np.mean(frames * frames, axis=1))

    # Step 1: clean digital jitter (very mild gaussian on the raw window-
    # level envelope).
    if digital_jitter_sigma > 0:
        top_raw = gaussian_filter1d(top_raw, sigma=digital_jitter_sigma)
        bottom_raw = gaussian_filter1d(bottom_raw, sigma=digital_jitter_sigma)
        rms_raw = gaussian_filter1d(rms_raw, sigma=digital_jitter_sigma)

    # Step 2: JOINT normalisation — preserves natural top/bottom asymmetry.
    joint_max = max(top_raw.max(), bottom_raw.max(), 1e-9)
    top_n = top_raw / joint_max
    bottom_n = bottom_raw / joint_max

    # Step 3: linear scaling.  gamma=1 by design; the parameter exists so
    # the GUI can expose it as an "advanced" tunable, but DO NOT default
    # to anything else.
    if gamma != 1.0:
        top_n = np.power(top_n, gamma)
        bottom_n = np.power(bottom_n, gamma)

    # Step 4: resample to nx evenly along the form's length.
    top_x = _resample_to(top_n, nx)
    bottom_x = _resample_to(bottom_n, nx)
    rms_x = _resample_to(rms_raw / (rms_raw.max() + 1e-9), nx)

    # Step 5: mild lengthwise smoothing — just enough to soften
    # single-sample jumps.  NEVER apply this to mesh vertex positions.
    if length_smooth_sigma > 0:
        top_x = gaussian_filter1d(top_x, sigma=length_smooth_sigma)
        bottom_x = gaussian_filter1d(bottom_x, sigma=length_smooth_sigma)
        rms_x = gaussian_filter1d(rms_x, sigma=length_smooth_sigma)

    # Clip in case smoothing pushed something just past 1.
    top_x = np.clip(top_x, 0.0, 1.0)
    bottom_x = np.clip(bottom_x, 0.0, 1.0)
    rms_x = np.clip(rms_x, 0.0, 1.0)

    return Envelopes(
        top=top_x.astype(np.float32),
        bottom=bottom_x.astype(np.float32),
        rms=rms_x.astype(np.float32),
        sample_rate=sr,
        duration_s=len(y) / float(sr),
        hop_ms=hop_ms,
        nx=nx,
    )


def _resample_to(arr: np.ndarray, n: int) -> np.ndarray:
    """Linear-interp resample a 1-D array to length n."""
    if len(arr) == n:
        return arr.copy()
    if len(arr) < 2:
        return np.full(n, arr.item() if len(arr) else 0.0)
    xp = np.linspace(0.0, 1.0, num=len(arr))
    x = np.linspace(0.0, 1.0, num=n)
    return np.interp(x, xp, arr)


# --------------------------------------------------------------------------
# Mic recording (optional — used by tab_input "Record" button)
# --------------------------------------------------------------------------

def record_to_wav(
    out_path: str | Path,
    duration_s: float,
    sr: int = 22050,
    channels: int = 1,
) -> Path:
    """Blocking microphone capture.  Returns the path written."""
    import sounddevice as sd
    import soundfile as sf

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration_s * sr)
    audio = sd.rec(frames, samplerate=sr, channels=channels, dtype="float32")
    sd.wait()
    if channels > 1:
        audio = audio.mean(axis=1)
    sf.write(str(out_path), audio, sr, subtype="PCM_16")
    return out_path


# --------------------------------------------------------------------------
# Peak detection (used by the verify tab to display side-by-side ratios)
# --------------------------------------------------------------------------

def find_envelope_peaks(env: np.ndarray, min_distance: int = 20, n: int = 6) -> list[int]:
    """Return up to ``n`` peak indices in ``env``, ordered by amplitude.

    Simple local-maxima detector; good enough for the diagnostic display.
    The verify tab calls this on a combined envelope (max(top, bottom)).
    """
    from scipy.signal import find_peaks
    peaks, props = find_peaks(env, distance=min_distance)
    if peaks.size == 0:
        return []
    ranked = sorted(peaks.tolist(), key=lambda i: -env[i])
    return ranked[:n]
