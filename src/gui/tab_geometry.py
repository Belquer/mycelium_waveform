"""
voice-to-form  —  src/gui/tab_geometry.py  v0.7.5

Design tab — geometry + appearance combined.

v0.7.3 — explicit camera-fit control.  set_mesh no longer reframes
the camera on every rebuild, so dimension and audio-smoothing
sliders now actually look like they're changing the form's size.
The camera refits only on the first mesh, on a fresh audio load,
on Fit-view button press, or on F keyboard shortcut.

v0.7.0 — design presets.  Named bundles of geometry + appearance +
audio-smoothing settings.  Built-ins ship with the app (polished
bronze, raw PLA, carbon fibre, mycelium cocoon, etc.); user presets
persist to ``~/.voice_to_form/presets.yaml`` and can be saved /
replaced / deleted from the Preset group at the top of the panel.

v0.6.2 — placeholder mesh so the viewport isn't blank on startup.  A
synthetic tapered-bell form (asymmetric top/bottom) is generated from
the current dimensions; dimension + aspect + appearance changes all
update it live.  As soon as real audio is loaded the placeholder is
replaced by the audio-driven mesh.

v0.6.1 — layout fixes after a v0.6.0 regression report:
  - The scroll panel's max-width was being ignored by the splitter
    (which sizes from child sizeHints).  Switched to setFixedWidth
    plus splitter.setSizes so the left column can't sprawl across
    the viewport area.
  - Palette grid now uses equal column stretches; the leftmost
    button no longer eats all the horizontal space.
  - Dimensions group rewritten with QGridLayout (was QFormLayout)
    — more deterministic rendering across Qt/PyQt builds; works
    around an empty-form-rows artefact reported on macOS.

v0.6.0:
  - Aspect editable (slider + QDoubleSpinBox, synced).
  - Surface sliders wired to the custom GLSL shader in preview.py.
"""
from __future__ import annotations

__version__ = "0.7.5"

import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QSpinBox,
    QGroupBox, QFormLayout, QSplitter, QScrollArea, QPushButton, QLineEdit,
    QColorDialog, QSlider, QComboBox, QGridLayout, QSizePolicy,
    QInputDialog, QMessageBox,
)

from .state import AppState
from ..preview import PreviewWidget
from ..config import BACKGROUND_PRESETS_RGB, DEFAULT_PALETTE
from .. import presets as presets_mod
from ..presets import Preset, CUSTOM_LABEL

print(f"[voice-to-form] tab_geometry.py v{__version__}", file=sys.stderr)


BUMP_PATTERNS = [
    "smooth", "sandblasted", "beadblasted", "brushed",
    "layered (FDM)", "porous (SLS)", "woven (carbon)", "mycelium-colonized",
]


class DesignTab(QWidget):
    """Combined geometry + appearance designer with the live 3D viewport."""

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        self._geom_debounce = QTimer(self)
        self._geom_debounce.setSingleShot(True)
        self._geom_debounce.setInterval(120)
        self._geom_debounce.timeout.connect(self._apply_geometry_params)

        # Refit the camera at well-defined moments:
        #   - the first time anything is rendered (placeholder)
        #   - when a fresh audio source is loaded
        # Parameter tweaks (length, aspect, smoothing, …) preserve
        # the user's current zoom so the form visibly changes size.
        self._pending_fit = True

        self._build_ui()

        state.mesh_changed.connect(self._on_mesh)
        state.appearance_changed.connect(self._on_appearance_changed)
        state.audio_loaded.connect(self._on_audio_loaded)

        # F = fit view, anywhere in the Design tab.
        fit_shortcut = QShortcut(QKeySequence("F"), self)
        fit_shortcut.activated.connect(self._fit_view_now)

        # Apply the initial background so the viewport already reflects
        # the configured scene.
        self._apply_background()

        # Drop a placeholder mesh into the viewport so it's not blank
        # on startup.  Real audio will replace it via _on_mesh.
        self._show_placeholder()

    # ------------------------------------------------------------------

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- LEFT: scrollable controls --------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # setFixedWidth pins both min and max plus the size policy.
        # setMaximumWidth alone was being ignored by QSplitter, which
        # gave the scroll area whatever its content's sizeHint
        # suggested — sprawling across the viewport area.
        scroll.setFixedWidth(440)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        controls = QWidget()
        # Constrain inner contents so they never push the scroll area
        # to widen.  20 px shy of scroll width to leave room for the
        # vertical scrollbar.
        controls.setMaximumWidth(420)
        ctl = QVBoxLayout(controls)
        ctl.setContentsMargins(8, 8, 8, 8)

        ctl.addWidget(self._presets_group())
        ctl.addWidget(self._dimensions_group())
        ctl.addWidget(self._shape_group())
        ctl.addWidget(self._surface_group())
        ctl.addWidget(self._background_group())
        ctl.addWidget(self._advanced_group())

        self.stats_label = QLabel("(load a WAV to generate a mesh)")
        self.stats_label.setStyleSheet("color: #555;")
        self.stats_label.setWordWrap(True)
        ctl.addWidget(self.stats_label)
        ctl.addStretch()

        scroll.setWidget(controls)

        # ---- RIGHT: 3D viewport ---------------------------------------
        self.preview = PreviewWidget()
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(2)

        # Thin toolbar above the viewport.  Today: just "Fit view";
        # room for export-PNG / lock-camera in v0.8.
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 0)
        self.fit_btn = QPushButton("Fit view")
        self.fit_btn.setToolTip("Reframe the camera to fit the current mesh (F)")
        self.fit_btn.clicked.connect(self._fit_view_now)
        toolbar.addWidget(self.fit_btn)
        toolbar.addStretch()
        rlay.addLayout(toolbar)

        rlay.addWidget(self.preview.widget(), stretch=1)

        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # Force initial split so neither pane "wins" via sizeHint.
        splitter.setSizes([440, 1100])
        splitter.setChildrenCollapsible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _presets_group(self) -> QGroupBox:
        g = QGroupBox("Preset")
        outer = QVBoxLayout(g)

        self.preset_combo = QComboBox()
        self.preset_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        self.preset_combo.currentTextChanged.connect(self._preset_selected)
        outer.addWidget(self.preset_combo)

        row = QHBoxLayout()
        self.save_preset_btn = QPushButton("Save as…")
        self.save_preset_btn.setToolTip(
            "Save the current geometry + surface + background settings "
            "as a named preset."
        )
        self.save_preset_btn.clicked.connect(self._save_preset_clicked)
        row.addWidget(self.save_preset_btn)

        self.delete_preset_btn = QPushButton("Delete")
        self.delete_preset_btn.setToolTip(
            "Delete the selected user preset.  Built-ins can't be deleted."
        )
        self.delete_preset_btn.clicked.connect(self._delete_preset_clicked)
        row.addWidget(self.delete_preset_btn)
        row.addStretch()
        outer.addLayout(row)

        # Populate dropdown.  Done last so handlers don't fire during init.
        self._refresh_preset_list(initial=True)
        return g

    def _dimensions_group(self) -> QGroupBox:
        g = QGroupBox("Dimensions")
        grid = QGridLayout(g)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        cfg = self.state.config

        self.length_box = self._double(cfg.geometry_length_mm, 20.0, 1000.0, suffix=" mm", decimals=1)
        self.min_r_box = self._double(cfg.geometry_min_r_mm, 0.1, 20.0, suffix=" mm", decimals=2)
        self.max_r_box = self._double(cfg.geometry_max_r_mm, 2.0, 200.0, suffix=" mm", decimals=1)
        self.n_theta_box = QSpinBox(); self.n_theta_box.setRange(16, 256); self.n_theta_box.setSingleStep(2)
        self.n_theta_box.setValue(cfg.geometry_n_theta)
        self.nx_box = QSpinBox(); self.nx_box.setRange(50, 4000); self.nx_box.setSingleStep(50)
        self.nx_box.setValue(cfg.geometry_nx)

        # Spinboxes get a comfortable minimum height so they're not
        # collapsed by the form layout's row math.
        for sb in (self.length_box, self.min_r_box, self.max_r_box,
                   self.n_theta_box, self.nx_box):
            sb.setMinimumHeight(24)

        rows = [
            ("Length", self.length_box),
            ("Min radius", self.min_r_box),
            ("Max radius", self.max_r_box),
            ("N θ (around)", self.n_theta_box),
            ("NX (along)", self.nx_box),
        ]
        for i, (lbl, w) in enumerate(rows):
            grid.addWidget(QLabel(lbl), i, 0)
            grid.addWidget(w, i, 1)

        for w in (self.length_box, self.min_r_box, self.max_r_box):
            w.valueChanged.connect(self._queue_geometry)
        for w in (self.n_theta_box, self.nx_box):
            w.valueChanged.connect(self._queue_geometry)
        return g

    def _shape_group(self) -> QGroupBox:
        g = QGroupBox("Cross-section")
        form = QFormLayout(g)
        cfg = self.state.config

        # Aspect: slider (visual) + editable spinbox (precise input).
        # Two-way synced — moving one updates the other, then both
        # forward to _apply_aspect.
        self.aspect_slider = QSlider(Qt.Orientation.Horizontal)
        self.aspect_slider.setRange(10, 200)  # maps 10..200 → 0.10..2.00
        self.aspect_slider.setValue(int(round(cfg.geometry_cross_section_aspect * 100)))

        self.aspect_spin = QDoubleSpinBox()
        self.aspect_spin.setRange(0.10, 2.00)
        self.aspect_spin.setDecimals(2)
        self.aspect_spin.setSingleStep(0.05)
        self.aspect_spin.setValue(cfg.geometry_cross_section_aspect)
        self.aspect_spin.setFixedWidth(70)

        self.aspect_slider.valueChanged.connect(self._aspect_slider_moved)
        self.aspect_spin.valueChanged.connect(self._aspect_spin_changed)

        aspect_row = QHBoxLayout()
        aspect_row.addWidget(self.aspect_slider, stretch=1)
        aspect_row.addWidget(self.aspect_spin)
        aspect_wrap = QWidget(); aspect_wrap.setLayout(aspect_row)

        form.addRow("Aspect", aspect_wrap)
        form.addRow(QLabel(
            "<i>Horizontal radius as a fraction of the mean vertical.<br>"
            "0.30 = very tall, 0.70 = portrait, 1.00 = ~circular,<br>"
            "1.50 = squashed.  Type a value or drag the slider.<br>"
            "Clamped to Min radius.</i>"
        ))
        return g

    def _surface_group(self) -> QGroupBox:
        g = QGroupBox("Surface (preview only)")
        outer = QVBoxLayout(g)
        cfg = self.state.config

        # Colour swatch + hex
        color_row = QHBoxLayout()
        self.color_swatch = QPushButton()
        self.color_swatch.setFixedSize(40, 28)
        self.color_swatch.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_swatch)

        self.hex_edit = QLineEdit(cfg.appearance.color_hex)
        self.hex_edit.setMaximumWidth(120)
        self.hex_edit.editingFinished.connect(self._hex_changed)
        color_row.addWidget(self.hex_edit)
        color_row.addStretch()
        outer.addLayout(color_row)
        self._sync_color_swatch()

        # Palette grid — 3 columns sharing horizontal space equally.
        # Without explicit stretch, Qt gives column 0 most of the space
        # and collapses the rest.
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        for i, p in enumerate(DEFAULT_PALETTE):
            btn = QPushButton(p["name"])
            btn.setFixedHeight(24)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(
                f"background-color: {p['hex']}; "
                f"color: {'#fff' if _is_dark(p['hex']) else '#000'};"
                "border: 1px solid #555; padding: 2px;"
            )
            btn.clicked.connect(lambda _=False, h=p["hex"]: self._set_color(h))
            grid.addWidget(btn, i // 3, i % 3)
        outer.addLayout(grid)

        # Roughness / Metalness are binary toggles — four useful combos:
        #   ☐ Rough  ☐ Metal  → glossy paint    (sharp white highlight)
        #   ☑ Rough  ☐ Metal  → matte paint     (no highlight)
        #   ☐ Rough  ☑ Metal  → mirror metal    (sharp base-tinted highlight)
        #   ☑ Rough  ☑ Metal  → brushed metal   (soft base-tinted highlight)
        slider_form = QFormLayout()

        self.rough_check = QCheckBox()
        self.rough_check.setChecked(cfg.appearance.roughness >= 0.5)
        self.rough_check.setToolTip(
            "Matte vs glossy.  Off = sharp highlight (mirror / gloss).  "
            "On = no highlight (matte)."
        )
        self.rough_check.toggled.connect(self._rough_toggled)

        self.metal_check = QCheckBox()
        self.metal_check.setChecked(cfg.appearance.metalness >= 0.5)
        self.metal_check.setToolTip(
            "Painted vs metal.  Off = white highlight on coloured base "
            "(paint / plastic).  On = highlight takes the base colour, "
            "diffuse fades — polished metal of that tint.  Combine with "
            "Rough off for a mirror, Rough on for brushed metal."
        )
        self.metal_check.toggled.connect(self._metal_toggled)

        # Keep the same attribute names the preset-apply code already
        # writes to, but make them None — _apply_preset's helper that
        # calls .setValue() will skip None safely (see _apply_preset).
        self.roughness = None
        self.metalness = None

        self.bump = self._slider(cfg.appearance.bump_intensity)
        self.bump.setToolTip(
            "Strength of the procedural surface relief picked below."
        )
        slider_form.addRow("Rough", self.rough_check)
        slider_form.addRow("Metal", self.metal_check)
        slider_form.addRow("Bump", self.bump)

        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(BUMP_PATTERNS)
        self.pattern_combo.setCurrentText(cfg.appearance.bump_pattern)
        self.pattern_combo.setToolTip(
            "Procedural noise applied to the surface normal:\n"
            "  smooth         no relief\n"
            "  sandblasted    high-freq random\n"
            "  beadblasted    fine, rounder\n"
            "  brushed        directional sine\n"
            "  layered (FDM)  horizontal print lines\n"
            "  porous (SLS)   large pits\n"
            "  woven (carbon) crossing grid\n"
            "  mycelium-colonized  organic fractal noise"
        )
        self.pattern_combo.currentTextChanged.connect(self._pattern_changed)
        slider_form.addRow("Bump pattern", self.pattern_combo)
        outer.addLayout(slider_form)

        outer.addWidget(QLabel(
            "<i>All four sliders affect the render live.  Roughness "
            "sharpens / broadens the highlight, metalness tints the "
            "specular by the base colour, bump patterns add procedural "
            "surface relief.</i>"
        ))
        return g

    def _background_group(self) -> QGroupBox:
        g = QGroupBox("Viewport background")
        outer = QVBoxLayout(g)
        cfg = self.state.config

        row = QHBoxLayout()
        self.bg_swatch = QPushButton()
        self.bg_swatch.setFixedSize(40, 28)
        self.bg_swatch.clicked.connect(self._pick_bg)
        row.addWidget(self.bg_swatch)

        self.bg_hex_edit = QLineEdit(self._current_bg_hex())
        self.bg_hex_edit.setMaximumWidth(120)
        self.bg_hex_edit.editingFinished.connect(self._bg_hex_changed)
        row.addWidget(self.bg_hex_edit)
        row.addStretch()
        outer.addLayout(row)
        self._sync_bg_swatch()

        # Brightness slider — instant lighten/darken control without the
        # color dialog.  Operates on the current chosen colour by
        # scaling toward white/black.
        bright_row = QHBoxLayout()
        bright_row.addWidget(QLabel("Brightness"))
        self.bg_brightness = QSlider(Qt.Orientation.Horizontal)
        self.bg_brightness.setRange(0, 100)
        self.bg_brightness.setValue(50)
        self.bg_brightness.setToolTip(
            "Quickly lighten / darken the picked background. "
            "50 = the picked colour unchanged."
        )
        self.bg_brightness.valueChanged.connect(self._bg_brightness_changed)
        bright_row.addWidget(self.bg_brightness)
        outer.addLayout(bright_row)

        # Preset dropdown
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset"))
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(list(BACKGROUND_PRESETS_RGB.keys()))
        if cfg.appearance.background in BACKGROUND_PRESETS_RGB:
            self.bg_combo.setCurrentText(cfg.appearance.background)
        self.bg_combo.currentTextChanged.connect(self._bg_preset_changed)
        preset_row.addWidget(self.bg_combo, stretch=1)
        outer.addLayout(preset_row)

        return g

    def _advanced_group(self) -> QGroupBox:
        g = QGroupBox("Audio smoothing (advanced)")
        form = QFormLayout(g)
        cfg = self.state.config

        self.hop_box = self._double(cfg.audio.hop_ms, 0.5, 20.0, suffix=" ms", decimals=1)
        self.jitter_box = self._double(cfg.audio.digital_jitter_sigma, 0.0, 4.0, decimals=2, step=0.1)
        self.length_smooth_box = self._double(cfg.audio.length_smooth_sigma, 0.0, 4.0, decimals=2, step=0.1)
        self.gamma_box = self._double(cfg.audio.gamma, 0.5, 2.5, decimals=2, step=0.05)

        form.addRow("hop", self.hop_box)
        form.addRow("jitter σ", self.jitter_box)
        form.addRow("length σ", self.length_smooth_box)
        form.addRow("γ (keep 1.0)", self.gamma_box)

        for w in (self.hop_box, self.jitter_box, self.length_smooth_box, self.gamma_box):
            w.valueChanged.connect(self._queue_geometry)
        return g

    # ------------------------------------------------------------------
    # Presets — save / apply / delete
    # ------------------------------------------------------------------

    def _refresh_preset_list(self, *, initial: bool = False, select: str | None = None):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem(CUSTOM_LABEL, userData=None)
        for p in presets_mod.all_presets():
            self.preset_combo.addItem(p.name, userData=p.name)
        # Pick selection.
        target_index = 0
        if select is not None:
            for i in range(self.preset_combo.count()):
                if self.preset_combo.itemData(i) == select:
                    target_index = i
                    break
        self.preset_combo.setCurrentIndex(target_index)
        self.preset_combo.blockSignals(False)
        if not initial and select is not None and target_index != 0:
            # Apply the selected preset since we just set it programmatically.
            chosen = self._lookup_preset(select)
            if chosen is not None:
                self._apply_preset(chosen)

    def _preset_selected(self, name: str):
        if not name or name == CUSTOM_LABEL:
            return
        chosen = self._lookup_preset(name)
        if chosen is None:
            return
        self._apply_preset(chosen)

    def _lookup_preset(self, name: str) -> Preset | None:
        for p in presets_mod.all_presets():
            if p.name == name:
                return p
        return None

    def _save_preset_clicked(self):
        suggested = self.preset_combo.currentText()
        if suggested == CUSTOM_LABEL:
            suggested = ""
        name, ok = QInputDialog.getText(
            self, "Save preset", "Preset name:",
            text=suggested,
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name == CUSTOM_LABEL:
            QMessageBox.warning(self, "Reserved name",
                                f"'{CUSTOM_LABEL}' is reserved.  Pick a different name.")
            return
        if presets_mod.is_builtin(name):
            QMessageBox.warning(
                self, "Built-in name",
                f"'{name}' is a built-in preset name.  Pick something else "
                "to keep the built-in around.",
            )
            return
        if presets_mod.user_has(name):
            resp = QMessageBox.question(
                self, "Replace preset",
                f"A preset called '{name}' already exists. Replace it?",
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        preset = self._current_as_preset(name)
        presets_mod.save_or_replace(preset)
        self._refresh_preset_list(initial=True, select=name)
        # Restore selection to the new preset (initial=True suppresses
        # auto-apply since we just saved from the current state).
        self.preset_combo.blockSignals(True)
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == name:
                self.preset_combo.setCurrentIndex(i)
                break
        self.preset_combo.blockSignals(False)

    def _delete_preset_clicked(self):
        name = self.preset_combo.currentData()
        if not name:
            return
        if presets_mod.is_builtin(name) and not presets_mod.user_has(name):
            QMessageBox.information(
                self, "Built-in preset",
                f"'{name}' is a built-in preset and can't be deleted.",
            )
            return
        resp = QMessageBox.question(
            self, "Delete preset", f"Delete preset '{name}'?",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        presets_mod.delete_user_preset(name)
        self._refresh_preset_list(initial=True)

    def _current_as_preset(self, name: str) -> Preset:
        cfg = self.state.config
        return Preset(
            name=name,
            length_mm=cfg.geometry_length_mm,
            min_r_mm=cfg.geometry_min_r_mm,
            max_r_mm=cfg.geometry_max_r_mm,
            n_theta=cfg.geometry_n_theta,
            nx=cfg.geometry_nx,
            cross_section_aspect=cfg.geometry_cross_section_aspect,
            hop_ms=cfg.audio.hop_ms,
            digital_jitter_sigma=cfg.audio.digital_jitter_sigma,
            length_smooth_sigma=cfg.audio.length_smooth_sigma,
            gamma=cfg.audio.gamma,
            color_hex=cfg.appearance.color_hex,
            roughness=cfg.appearance.roughness,
            metalness=cfg.appearance.metalness,
            bump_intensity=cfg.appearance.bump_intensity,
            bump_pattern=cfg.appearance.bump_pattern,
            background=cfg.appearance.background,
            viewport_bg_hex=cfg.viewport_bg_hex,
        )

    def _apply_preset(self, preset: Preset):
        """Copy preset values into config, sync every UI control, and
        push the new look to the preview."""
        cfg = self.state.config
        cfg.geometry_length_mm = preset.length_mm
        cfg.geometry_min_r_mm = preset.min_r_mm
        cfg.geometry_max_r_mm = preset.max_r_mm
        cfg.geometry_n_theta = preset.n_theta
        cfg.geometry_nx = preset.nx
        cfg.geometry_cross_section_aspect = preset.cross_section_aspect
        cfg.audio.hop_ms = preset.hop_ms
        cfg.audio.digital_jitter_sigma = preset.digital_jitter_sigma
        cfg.audio.length_smooth_sigma = preset.length_smooth_sigma
        cfg.audio.gamma = preset.gamma
        cfg.appearance.color_hex = preset.color_hex
        cfg.appearance.roughness = preset.roughness
        cfg.appearance.metalness = preset.metalness
        cfg.appearance.bump_intensity = preset.bump_intensity
        cfg.appearance.bump_pattern = preset.bump_pattern
        cfg.appearance.background = preset.background
        cfg.viewport_bg_hex = preset.viewport_bg_hex

        # Sync UI without re-triggering handlers.
        def _set(ctl, value):
            ctl.blockSignals(True)
            ctl.setValue(value)
            ctl.blockSignals(False)

        _set(self.length_box, preset.length_mm)
        _set(self.min_r_box, preset.min_r_mm)
        _set(self.max_r_box, preset.max_r_mm)
        _set(self.n_theta_box, preset.n_theta)
        _set(self.nx_box, preset.nx)
        _set(self.hop_box, preset.hop_ms)
        _set(self.jitter_box, preset.digital_jitter_sigma)
        _set(self.length_smooth_box, preset.length_smooth_sigma)
        _set(self.gamma_box, preset.gamma)
        _set(self.aspect_slider, int(round(preset.cross_section_aspect * 100)))
        _set(self.aspect_spin, preset.cross_section_aspect)
        _set(self.bump, int(round(preset.bump_intensity * 100)))
        _set(self.bg_brightness, 50)

        # Rough/Metal are checkboxes — use setChecked, not setValue.
        self.rough_check.blockSignals(True)
        self.rough_check.setChecked(preset.roughness >= 0.5)
        self.rough_check.blockSignals(False)
        self.metal_check.blockSignals(True)
        self.metal_check.setChecked(preset.metalness >= 0.5)
        self.metal_check.blockSignals(False)

        self.pattern_combo.blockSignals(True)
        self.pattern_combo.setCurrentText(preset.bump_pattern)
        self.pattern_combo.blockSignals(False)

        self.hex_edit.blockSignals(True)
        self.hex_edit.setText(preset.color_hex)
        self.hex_edit.blockSignals(False)
        self._sync_color_swatch()

        self.bg_combo.blockSignals(True)
        if preset.background in BACKGROUND_PRESETS_RGB:
            self.bg_combo.setCurrentText(preset.background)
        self.bg_combo.blockSignals(False)

        self.bg_hex_edit.blockSignals(True)
        self.bg_hex_edit.setText(self._current_bg_hex())
        self.bg_hex_edit.blockSignals(False)
        self._sync_bg_swatch()

        # Push to preview.
        self.preview.set_color(preset.color_hex)
        self.preview.set_pbr(
            roughness=preset.roughness,
            metalness=preset.metalness,
            bump_intensity=preset.bump_intensity,
            bump_pattern=preset.bump_pattern,
        )
        self._apply_background()

        # Rebuild the form.
        if self.state.audio is not None:
            self.state.recompute_envelopes()
        else:
            self._show_placeholder()

    # ------------------------------------------------------------------
    # Placeholder mesh — shown before any audio is loaded
    # ------------------------------------------------------------------

    def _show_placeholder(self):
        """Generate a synthetic tapered-bell mesh from current dimensions.

        Gives the viewport something to render before the artist loads
        or records audio, and lets dimension / aspect / appearance
        sliders have visible effect on the empty state.  Replaced by
        real audio-driven mesh via _on_mesh().
        """
        if self.state.audio is not None:
            return
        import numpy as np
        from ..audio import Envelopes
        from ..geometry import build_mesh, GeometryParams

        nx = 200
        x = np.linspace(0.0, 1.0, nx, dtype=np.float32)
        # Asymmetric bell: pronounced top, softer bottom.  Echoes a
        # real recording's positive-vs-negative envelope.  Clamp to
        # >=0 before the fractional power — floating-point underflow
        # makes sin(π·1) slightly negative, and (-tiny)**0.6 = NaN.
        s = np.maximum(np.sin(np.pi * x), 0.0)
        env_top = (s ** 0.6).astype(np.float32)
        env_bot = (s ** 0.45 * 0.7).astype(np.float32)
        env = Envelopes(
            top=env_top, bottom=env_bot, rms=env_top,
            sample_rate=22050, duration_s=1.0, hop_ms=3.0, nx=nx,
        )

        cfg = self.state.config
        # n_theta must stay even; clamp to a snappy value for the
        # placeholder so dimension drags don't lag.
        n_theta = max(16, min(48, cfg.geometry_n_theta if cfg.geometry_n_theta % 2 == 0 else cfg.geometry_n_theta + 1))
        params = GeometryParams(
            length_mm=cfg.geometry_length_mm,
            min_r_mm=cfg.geometry_min_r_mm,
            max_r_mm=cfg.geometry_max_r_mm,
            n_theta=n_theta,
            nx=nx,
            cross_section_aspect=cfg.geometry_cross_section_aspect,
        )
        try:
            mesh = build_mesh(env, params)
        except Exception as e:
            self.stats_label.setText(f"(placeholder failed: {e!r})")
            return

        a = cfg.appearance
        self.preview.set_mesh(
            mesh,
            color_hex=a.color_hex,
            roughness=a.roughness,
            metalness=a.metalness,
            bump_intensity=a.bump_intensity,
            bump_pattern=a.bump_pattern,
        )
        self._maybe_fit()
        self.stats_label.setText(
            "placeholder shape — load or record audio to generate the real form "
            f"(showing {mesh.triangle_count():,} triangles)"
        )

    # ------------------------------------------------------------------
    # Geometry update path (debounced — full envelope/mesh rebuild)
    # ------------------------------------------------------------------

    def _queue_geometry(self, *_):
        self._geom_debounce.start()

    def _aspect_slider_moved(self, value: int):
        aspect = value / 100.0
        # Block the spin's signal so we don't loop.
        self.aspect_spin.blockSignals(True)
        self.aspect_spin.setValue(aspect)
        self.aspect_spin.blockSignals(False)
        self._apply_aspect(aspect)

    def _aspect_spin_changed(self, value: float):
        aspect = float(value)
        self.aspect_slider.blockSignals(True)
        self.aspect_slider.setValue(int(round(aspect * 100)))
        self.aspect_slider.blockSignals(False)
        self._apply_aspect(aspect)

    def _apply_aspect(self, aspect: float):
        self.state.config.geometry_cross_section_aspect = aspect
        self._queue_geometry()

    def _apply_geometry_params(self):
        cfg = self.state.config
        cfg.geometry_length_mm = float(self.length_box.value())
        cfg.geometry_min_r_mm = float(self.min_r_box.value())
        cfg.geometry_max_r_mm = float(self.max_r_box.value())
        # n_theta must stay even.
        n_theta = int(self.n_theta_box.value())
        if n_theta % 2 != 0:
            n_theta += 1
            self.n_theta_box.blockSignals(True)
            self.n_theta_box.setValue(n_theta)
            self.n_theta_box.blockSignals(False)
        cfg.geometry_n_theta = n_theta
        cfg.geometry_nx = int(self.nx_box.value())
        cfg.audio.hop_ms = float(self.hop_box.value())
        cfg.audio.digital_jitter_sigma = float(self.jitter_box.value())
        cfg.audio.length_smooth_sigma = float(self.length_smooth_box.value())
        cfg.audio.gamma = float(self.gamma_box.value())

        if self.state.audio is not None:
            self.state.recompute_envelopes()
        else:
            # Pre-audio: refresh the placeholder so the sliders have
            # visible effect.
            self._show_placeholder()

    # ------------------------------------------------------------------
    # Appearance update path (instant — no mesh rebuild)
    # ------------------------------------------------------------------

    def _slider(self, value: float) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(int(round(value * 100)))
        s.valueChanged.connect(self._save_pbr_sliders)
        return s

    def _save_pbr_sliders(self):
        # Called by the bump slider only (rough/metal are checkboxes
        # with their own handlers).
        a = self.state.config.appearance
        a.bump_intensity = self.bump.value() / 100.0
        self.preview.set_pbr(bump_intensity=a.bump_intensity)
        self.state.appearance_changed.emit()

    def _rough_toggled(self, checked: bool):
        a = self.state.config.appearance
        a.roughness = 1.0 if checked else 0.0
        self.preview.set_pbr(roughness=a.roughness)
        self.state.appearance_changed.emit()

    def _metal_toggled(self, checked: bool):
        a = self.state.config.appearance
        a.metalness = 1.0 if checked else 0.0
        self.preview.set_pbr(metalness=a.metalness)
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
        self._sync_color_swatch()
        self.state.appearance_changed.emit()

    def _sync_color_swatch(self):
        h = self.state.config.appearance.color_hex
        self.color_swatch.setStyleSheet(
            f"background-color: {h}; border: 1px solid #333; border-radius: 3px;"
        )

    def _pattern_changed(self, text: str):
        self.state.config.appearance.bump_pattern = text
        self.preview.set_pbr(bump_pattern=text)
        self.state.appearance_changed.emit()

    # ------------------------------------------------------------------
    # Background — adjustable, with custom hex, brightness slider, and
    # preset dropdown all wired up.
    # ------------------------------------------------------------------

    def _current_bg_hex(self) -> str:
        cfg = self.state.config
        if cfg.viewport_bg_hex:
            return cfg.viewport_bg_hex
        return BACKGROUND_PRESETS_RGB.get(cfg.appearance.background, "#2e3236")

    def _pick_bg(self):
        c = QColorDialog.getColor(QColor(self._current_bg_hex()), self)
        if c.isValid():
            self._set_bg(c.name(), reset_brightness=True)

    def _bg_hex_changed(self):
        text = self.bg_hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) == 7:
            self._set_bg(text, reset_brightness=True)

    def _set_bg(self, hex_str: str, *, reset_brightness: bool):
        self.state.config.viewport_bg_hex = hex_str
        self.bg_hex_edit.setText(hex_str)
        self._sync_bg_swatch()
        if reset_brightness:
            self.bg_brightness.blockSignals(True)
            self.bg_brightness.setValue(50)
            self.bg_brightness.blockSignals(False)
        self.state.appearance_changed.emit()
        self._apply_background()

    def _bg_brightness_changed(self, value: int):
        # 50 = unchanged; <50 darkens toward black; >50 lightens toward white.
        base = self._current_bg_hex()
        adjusted = _shift_brightness(base, value / 100.0)
        self.preview.set_background(adjusted)
        # Don't write the brightness-shifted colour back to config — the
        # slider is a viewport-only quick adjust on top of the picked
        # base colour.  Picking a new colour resets the slider.

    def _bg_preset_changed(self, name: str):
        self.state.config.appearance.background = name
        # When a preset is picked, clear the custom override so the
        # preset's own hex applies.
        self.state.config.viewport_bg_hex = ""
        if name in BACKGROUND_PRESETS_RGB:
            self.bg_hex_edit.setText(BACKGROUND_PRESETS_RGB[name])
            self._sync_bg_swatch()
        self.bg_brightness.blockSignals(True)
        self.bg_brightness.setValue(50)
        self.bg_brightness.blockSignals(False)
        self.state.appearance_changed.emit()
        self._apply_background()

    def _sync_bg_swatch(self):
        self.bg_swatch.setStyleSheet(
            f"background-color: {self._current_bg_hex()}; "
            "border: 1px solid #333; border-radius: 3px;"
        )

    def _apply_background(self):
        # Honour the brightness slider if it's off centre.
        base = self._current_bg_hex()
        slider = self.bg_brightness.value() if hasattr(self, "bg_brightness") else 50
        shown = base if slider == 50 else _shift_brightness(base, slider / 100.0)
        self.preview.set_background(shown)

    # ------------------------------------------------------------------
    # Mesh / appearance signal handlers
    # ------------------------------------------------------------------

    def _on_mesh(self, mesh):
        a = self.state.config.appearance
        self.preview.set_mesh(
            mesh,
            color_hex=a.color_hex,
            roughness=a.roughness,
            metalness=a.metalness,
            bump_intensity=a.bump_intensity,
            bump_pattern=a.bump_pattern,
        )
        self._apply_background()
        self._maybe_fit()
        self.stats_label.setText(
            f"mesh:  {mesh.triangle_count():,} triangles   ·   "
            f"{mesh.vertex_count():,} vertices"
        )

    def _on_audio_loaded(self, *_):
        # Fresh source → refit on the next mesh paint.
        self._pending_fit = True

    def _maybe_fit(self):
        if self._pending_fit:
            self.preview.fit_view()
            self._pending_fit = False

    def _fit_view_now(self):
        self.preview.fit_view()
        self._pending_fit = False

    def _on_appearance_changed(self):
        a = self.state.config.appearance
        self.preview.set_color(a.color_hex)
        self.preview.set_pbr(
            roughness=a.roughness,
            metalness=a.metalness,
            bump_intensity=a.bump_intensity,
            bump_pattern=a.bump_pattern,
        )
        self._apply_background()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _double(self, value: float, lo: float, hi: float, *,
                suffix: str = "", decimals: int = 1,
                step: float | None = None) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setValue(value)
        if suffix:
            sb.setSuffix(suffix)
        if step is not None:
            sb.setSingleStep(step)
        return sb


# Backwards compatibility for any code still importing GeometryTab.
GeometryTab = DesignTab


# --------------------------------------------------------------------------
# Free helpers
# --------------------------------------------------------------------------

def _is_dark(hex_str: str) -> bool:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return False
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def _shift_brightness(hex_str: str, t: float) -> str:
    """Shift a hex colour toward black (t<0.5) or white (t>0.5).

    t in [0, 1].  0 → fully black, 0.5 → unchanged, 1 → fully white.
    """
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return hex_str
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if t < 0.5:
        k = t / 0.5  # 0..1
        r, g, b = int(r * k), int(g * k), int(b * k)
    else:
        k = (t - 0.5) / 0.5  # 0..1
        r = int(r + (255 - r) * k)
        g = int(g + (255 - g) * k)
        b = int(b + (255 - b) * k)
    return f"#{r:02x}{g:02x}{b:02x}"
