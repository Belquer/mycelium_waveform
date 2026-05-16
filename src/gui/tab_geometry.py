"""
voice-to-form  —  src/gui/tab_geometry.py  v0.2.0

Geometry tab: length, min/max radius, n_theta, nx, smoothing sigmas.
Also hosts the 3D preview viewport so parameter sweeps are visible in
real time.

v0.2.0:
  - Listens to AppState.appearance_changed and updates the preview
    colour and background live (no mesh rebuild).
  - Applies the configured background on mesh load so the very first
    preview already shows the artist's chosen scene.
"""
from __future__ import annotations

__version__ = "0.2.0"

import sys
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QSpinBox,
    QGroupBox, QGridLayout, QFormLayout, QSplitter, QFrame,
)

from .state import AppState
from ..preview import PreviewWidget
from ..config import BACKGROUND_PRESETS_RGB

print(f"[voice-to-form] tab_geometry.py v{__version__}", file=sys.stderr)


class GeometryTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._apply_params)
        self._build_ui()

        state.mesh_changed.connect(self._on_mesh)
        state.appearance_changed.connect(self._on_appearance_changed)

        # Apply the initial background so the empty viewport already
        # reflects the configured studio.
        self._apply_background()

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- left: controls ---
        controls = QWidget()
        ctl_layout = QVBoxLayout(controls)

        dims = QGroupBox("Dimensions")
        form = QFormLayout(dims)

        self.length_box = QDoubleSpinBox()
        self.length_box.setRange(20.0, 1000.0)
        self.length_box.setSuffix(" mm")
        self.length_box.setValue(self.state.config.geometry_length_mm)
        self.length_box.setDecimals(1)
        form.addRow("Length", self.length_box)

        self.min_r_box = QDoubleSpinBox()
        self.min_r_box.setRange(0.1, 20.0)
        self.min_r_box.setSuffix(" mm")
        self.min_r_box.setDecimals(2)
        self.min_r_box.setValue(self.state.config.geometry_min_r_mm)
        form.addRow("Min radius", self.min_r_box)

        self.max_r_box = QDoubleSpinBox()
        self.max_r_box.setRange(2.0, 200.0)
        self.max_r_box.setSuffix(" mm")
        self.max_r_box.setDecimals(1)
        self.max_r_box.setValue(self.state.config.geometry_max_r_mm)
        form.addRow("Max radius", self.max_r_box)

        self.n_theta_box = QSpinBox()
        self.n_theta_box.setRange(16, 256)
        self.n_theta_box.setSingleStep(2)
        self.n_theta_box.setValue(self.state.config.geometry_n_theta)
        form.addRow("N θ (around)", self.n_theta_box)

        self.nx_box = QSpinBox()
        self.nx_box.setRange(50, 4000)
        self.nx_box.setSingleStep(50)
        self.nx_box.setValue(self.state.config.geometry_nx)
        form.addRow("NX (along)", self.nx_box)

        ctl_layout.addWidget(dims)

        smooth = QGroupBox("Audio smoothing (advanced)")
        sform = QFormLayout(smooth)

        self.hop_box = QDoubleSpinBox()
        self.hop_box.setRange(0.5, 20.0)
        self.hop_box.setSuffix(" ms")
        self.hop_box.setDecimals(1)
        self.hop_box.setValue(self.state.config.audio.hop_ms)
        sform.addRow("hop", self.hop_box)

        self.jitter_box = QDoubleSpinBox()
        self.jitter_box.setRange(0.0, 4.0)
        self.jitter_box.setDecimals(2)
        self.jitter_box.setSingleStep(0.1)
        self.jitter_box.setValue(self.state.config.audio.digital_jitter_sigma)
        sform.addRow("jitter σ", self.jitter_box)

        self.length_smooth_box = QDoubleSpinBox()
        self.length_smooth_box.setRange(0.0, 4.0)
        self.length_smooth_box.setDecimals(2)
        self.length_smooth_box.setSingleStep(0.1)
        self.length_smooth_box.setValue(self.state.config.audio.length_smooth_sigma)
        sform.addRow("length σ", self.length_smooth_box)

        self.gamma_box = QDoubleSpinBox()
        self.gamma_box.setRange(0.5, 2.5)
        self.gamma_box.setDecimals(2)
        self.gamma_box.setSingleStep(0.05)
        self.gamma_box.setValue(self.state.config.audio.gamma)
        sform.addRow("γ (keep 1.0)", self.gamma_box)

        ctl_layout.addWidget(smooth)

        self.stats_label = QLabel("(no mesh yet)")
        self.stats_label.setStyleSheet("color: #555")
        self.stats_label.setWordWrap(True)
        ctl_layout.addWidget(self.stats_label)

        ctl_layout.addStretch()

        # --- right: 3D viewport ---
        self.preview = PreviewWidget()
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(self.preview.widget())

        splitter.addWidget(controls)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        # Hook up change signals (all debounced through _apply_params).
        for w in (self.length_box, self.min_r_box, self.max_r_box,
                  self.hop_box, self.jitter_box, self.length_smooth_box,
                  self.gamma_box):
            w.valueChanged.connect(lambda *_: self._debounce.start())
        for w in (self.n_theta_box, self.nx_box):
            w.valueChanged.connect(lambda *_: self._debounce.start())

    # ------------------------------------------------------------------

    def _apply_params(self):
        cfg = self.state.config
        cfg.geometry_length_mm = float(self.length_box.value())
        cfg.geometry_min_r_mm = float(self.min_r_box.value())
        cfg.geometry_max_r_mm = float(self.max_r_box.value())
        cfg.geometry_n_theta = int(self.n_theta_box.value())
        if cfg.geometry_n_theta % 2 != 0:
            cfg.geometry_n_theta += 1
            self.n_theta_box.blockSignals(True)
            self.n_theta_box.setValue(cfg.geometry_n_theta)
            self.n_theta_box.blockSignals(False)
        cfg.geometry_nx = int(self.nx_box.value())
        cfg.audio.hop_ms = float(self.hop_box.value())
        cfg.audio.digital_jitter_sigma = float(self.jitter_box.value())
        cfg.audio.length_smooth_sigma = float(self.length_smooth_box.value())
        cfg.audio.gamma = float(self.gamma_box.value())

        # Re-extract envelopes (and via that, rebuild mesh).
        if self.state.audio is not None:
            self.state.recompute_envelopes()

    def _on_mesh(self, mesh):
        a = self.state.config.appearance
        self.preview.set_mesh(mesh, color_hex=a.color_hex,
                              roughness=a.roughness, metalness=a.metalness)
        self._apply_background()
        self.stats_label.setText(
            f"mesh:  {mesh.triangle_count():,} triangles   ·   "
            f"{mesh.vertex_count():,} vertices"
        )

    def _on_appearance_changed(self):
        a = self.state.config.appearance
        self.preview.set_color(a.color_hex)
        self._apply_background()

    def _apply_background(self):
        name = self.state.config.appearance.background
        hex_str = BACKGROUND_PRESETS_RGB.get(name, "#2e3236")
        self.preview.set_background(hex_str)
