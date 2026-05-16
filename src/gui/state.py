"""
voice-to-form  —  src/gui/state.py  v0.5.0

Shared application state for the GUI tabs.  Holds the current source
WAV, decoded audio, envelopes, mesh, and the working FormConfig.
Emits Qt signals when anything downstream needs to recompute.

v0.5.0 — `load_source` honours the new `trim_silence_enabled` flag so
the form's tapered ends mirror the audio's natural fade-in/out.

v0.2.0 added the `appearance_changed` signal so the Appearance tab
can trigger a live colour/background update in the Geometry tab's
preview without rebuilding the mesh.
"""
from __future__ import annotations

__version__ = "0.5.0"

import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ..audio import Envelopes, load_wav, trim_silence, extract_envelopes
from ..config import FormConfig
from ..geometry import GeometryParams, Mesh, build_mesh

print(f"[voice-to-form] gui/state.py v{__version__}", file=sys.stderr)


class AppState(QObject):
    audio_loaded = pyqtSignal(object)        # ndarray
    envelopes_changed = pyqtSignal(object)   # Envelopes
    mesh_changed = pyqtSignal(object)        # Mesh
    config_changed = pyqtSignal(object)      # FormConfig
    overlay_reviewed_changed = pyqtSignal(bool)
    appearance_changed = pyqtSignal()        # cheap signal — live render redraw

    def __init__(self):
        super().__init__()
        self.source_wav: Optional[Path] = None
        self.audio: Optional[np.ndarray] = None
        self.sample_rate: Optional[int] = None
        self.envelopes: Optional[Envelopes] = None
        self.mesh: Optional[Mesh] = None
        self.config: FormConfig = FormConfig()

    # ------------------------------------------------------------------

    def load_source(self, path: Path) -> None:
        self.source_wav = Path(path)
        y, sr = load_wav(path, target_sr=self.config.audio.target_sr)
        if self.config.audio.trim_silence_enabled:
            y = trim_silence(y, sr, top_db=self.config.audio.trim_top_db)
        self.audio = y
        self.sample_rate = sr
        self.audio_loaded.emit(y)
        self.recompute_envelopes()

    def recompute_envelopes(self) -> None:
        if self.audio is None or self.sample_rate is None:
            return
        ap = self.config.audio
        env = extract_envelopes(
            self.audio, self.sample_rate,
            hop_ms=ap.hop_ms,
            nx=self.config.geometry_nx,
            digital_jitter_sigma=ap.digital_jitter_sigma,
            length_smooth_sigma=ap.length_smooth_sigma,
            gamma=ap.gamma,
        )
        self.envelopes = env
        # Whenever envelopes change, geometry must regen too.
        self._invalidate_overlay_review("envelopes recomputed")
        self.envelopes_changed.emit(env)
        self.recompute_mesh()

    def recompute_mesh(self) -> None:
        if self.envelopes is None:
            return
        params = self.config.geometry_params()
        # Make sure NX agrees.  If the user changed nx in geometry params,
        # re-extract envelopes first.
        if self.envelopes.nx != params.nx:
            self.recompute_envelopes()
            return
        self.mesh = build_mesh(self.envelopes, params)
        self._invalidate_overlay_review("mesh rebuilt")
        self.mesh_changed.emit(self.mesh)

    # ------------------------------------------------------------------

    def set_overlay_reviewed(self, value: bool) -> None:
        self.config.reviewed_overlay = value
        self.overlay_reviewed_changed.emit(value)

    def _invalidate_overlay_review(self, reason: str) -> None:
        if self.config.reviewed_overlay:
            print(f"[voice-to-form] invalidating overlay review: {reason}", file=sys.stderr)
            self.config.reviewed_overlay = False
            self.overlay_reviewed_changed.emit(False)

    def announce_config(self) -> None:
        self.config_changed.emit(self.config)
