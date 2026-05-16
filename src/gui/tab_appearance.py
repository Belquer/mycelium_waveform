"""
voice-to-form  —  src/gui/tab_appearance.py  v0.2.0

Appearance tab (preview-only — does NOT affect exported geometry).

v0.2.0:
  - Every change emits AppState.appearance_changed so the Geometry-tab
    viewport updates live as the artist tunes colour / background.
  - Default colour is now a brushed-aluminum mid-tone (was matte
    black, which rendered as black-on-black against the dark viewport).
"""
from __future__ import annotations

__version__ = "0.2.0"

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QColorDialog,
    QLineEdit, QGroupBox, QFormLayout, QSlider, QComboBox, QGridLayout,
)

from .state import AppState
from ..config import DEFAULT_PALETTE, BACKGROUND_PRESETS_RGB

print(f"[voice-to-form] tab_appearance.py v{__version__}", file=sys.stderr)


BUMP_PATTERNS = [
    "smooth", "sandblasted", "beadblasted", "brushed",
    "layered (FDM)", "porous (SLS)", "woven (carbon)", "mycelium-colonized",
]


class AppearanceTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ---- Colour
        color_group = QGroupBox("Diffuse colour")
        cg = QHBoxLayout(color_group)
        self.color_swatch = QPushButton()
        self.color_swatch.setFixedSize(48, 48)
        self.color_swatch.clicked.connect(self._pick_color)
        cg.addWidget(self.color_swatch)

        self.hex_edit = QLineEdit(self.state.config.appearance.color_hex)
        self.hex_edit.setMaximumWidth(120)
        self.hex_edit.editingFinished.connect(self._hex_changed)
        cg.addWidget(self.hex_edit)
        cg.addStretch()
        root.addWidget(color_group)

        # ---- Palette
        pal_group = QGroupBox("Palette")
        grid = QGridLayout(pal_group)
        for i, p in enumerate(DEFAULT_PALETTE):
            btn = QPushButton(p["name"])
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                f"background-color: {p['hex']}; color: {'#fff' if _is_dark(p['hex']) else '#000'};"
                "border: 1px solid #555;"
            )
            btn.clicked.connect(lambda _=False, h=p["hex"]: self._set_color(h))
            grid.addWidget(btn, i // 4, i % 4)
        root.addWidget(pal_group)

        # ---- PBR sliders (recorded; only colour + bg actually render in v0.2)
        pbr_group = QGroupBox("Surface (preview, not exported)")
        form = QFormLayout(pbr_group)
        self.roughness = self._slider(self.state.config.appearance.roughness, 0.0, 1.0)
        self.metalness = self._slider(self.state.config.appearance.metalness, 0.0, 1.0)
        self.bump = self._slider(self.state.config.appearance.bump_intensity, 0.0, 1.0)
        form.addRow("Roughness", self.roughness)
        form.addRow("Metalness", self.metalness)
        form.addRow("Bump intensity", self.bump)

        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(BUMP_PATTERNS)
        self.pattern_combo.setCurrentText(self.state.config.appearance.bump_pattern)
        self.pattern_combo.currentTextChanged.connect(self._pattern_changed)
        form.addRow("Bump pattern", self.pattern_combo)
        form.addRow(QLabel("<i>Roughness / metalness / bump patterns saved to config; full PBR in v0.3.</i>"))

        root.addWidget(pbr_group)

        # ---- Background
        bg_group = QGroupBox("Background")
        bg = QHBoxLayout(bg_group)
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(list(BACKGROUND_PRESETS_RGB.keys()))
        if self.state.config.appearance.background in BACKGROUND_PRESETS_RGB:
            self.bg_combo.setCurrentText(self.state.config.appearance.background)
        self.bg_combo.currentTextChanged.connect(self._bg_changed)
        bg.addWidget(self.bg_combo)
        bg.addStretch()
        root.addWidget(bg_group)

        root.addStretch()

        self._sync_swatch()

    # ------------------------------------------------------------------

    def _slider(self, value: float, lo: float, hi: float) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(int(round((value - lo) / (hi - lo) * 100)))
        s.valueChanged.connect(self._save_sliders)
        return s

    def _save_sliders(self):
        a = self.state.config.appearance
        a.roughness = self.roughness.value() / 100.0
        a.metalness = self.metalness.value() / 100.0
        a.bump_intensity = self.bump.value() / 100.0
        self.state.appearance_changed.emit()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.state.config.appearance.color_hex), self)
        if c.isValid():
            self._set_color(c.name())

    def _hex_changed(self):
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) == 7:
            self._set_color(text)

    def _set_color(self, hex_str: str):
        self.state.config.appearance.color_hex = hex_str
        self.hex_edit.setText(hex_str)
        self._sync_swatch()
        self.state.appearance_changed.emit()

    def _sync_swatch(self):
        h = self.state.config.appearance.color_hex
        self.color_swatch.setStyleSheet(f"background-color: {h}; border: 1px solid #333;")

    def _pattern_changed(self, text: str):
        self.state.config.appearance.bump_pattern = text
        # Pattern doesn't affect render in v0.2 but emit anyway so any
        # listener that does pattern preview later picks it up.
        self.state.appearance_changed.emit()

    def _bg_changed(self, text: str):
        self.state.config.appearance.background = text
        self.state.appearance_changed.emit()


def _is_dark(hex_str: str) -> bool:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return False
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128
