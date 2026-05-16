"""
voice-to-form  —  src/gui/tab_export.py  v0.1.0

Export tab — pick a manufacturing profile, save to the library, run
the export.  Disabled until the Verify tab's "reviewed" checkbox is
ticked.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QPlainTextEdit, QFileDialog, QMessageBox, QGroupBox,
)

from .state import AppState
from ..profiles import PROFILES, get as get_profile
from ..export import export_profile
from ..library import new_entry_dir, save_entry
from ..overlay import build_figure, save_png

print(f"[voice-to-form] tab_export.py v{__version__}", file=sys.stderr)


class ExportTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._build_ui()
        state.overlay_reviewed_changed.connect(self._update_gate)
        state.mesh_changed.connect(lambda *_: self._update_gate(self.state.config.reviewed_overlay))
        self._update_gate(False)

    def _build_ui(self):
        root = QVBoxLayout(self)

        profile_group = QGroupBox("Manufacturing profile")
        pl = QVBoxLayout(profile_group)
        self.profile_combo = QComboBox()
        for key, prof in PROFILES.items():
            self.profile_combo.addItem(prof.label, userData=key)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        pl.addWidget(self.profile_combo)

        self.profile_notes = QPlainTextEdit()
        self.profile_notes.setReadOnly(True)
        self.profile_notes.setMaximumHeight(150)
        pl.addWidget(self.profile_notes)
        root.addWidget(profile_group)

        # Buttons
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save to library + Export")
        self.save_btn.setToolTip(
            "Copies the WAV into library/, writes config + diagnostic PNG, "
            "then runs the export for the selected profile."
        )
        self.save_btn.clicked.connect(self._save_and_export)
        btn_row.addWidget(self.save_btn)

        self.export_only_btn = QPushButton("Export to folder…")
        self.export_only_btn.setToolTip("Run the export without touching the library.")
        self.export_only_btn.clicked.connect(self._export_to_folder)
        btn_row.addWidget(self.export_only_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.gate_label = QLabel()
        self.gate_label.setWordWrap(True)
        root.addWidget(self.gate_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: ui-monospace, Menlo, monospace;")
        root.addWidget(self.log, stretch=1)

        # Initial state
        self._profile_changed(0)

    # ------------------------------------------------------------------

    def _profile_changed(self, _idx: int):
        key = self.profile_combo.currentData()
        if not key:
            return
        prof = get_profile(key)
        self.state.config.last_profile_key = key
        text = (
            f"family: {prof.family}\n"
            f"formats: {', '.join(prof.formats)}\n"
            f"min radius override: {prof.min_r_mm} mm\n"
            + (f"decimate to: {int(prof.decimate_to*100)}%\n" if prof.decimate_to else "")
            + (f"split halves: yes\n" if prof.split_halves else "")
            + (f"services: {', '.join(prof.services)}\n" if prof.services else "")
            + (f"finish: {prof.suggested_finish}\n" if prof.suggested_finish else "")
            + f"est cost: ${prof.est_cost_usd[0]:.0f}–${prof.est_cost_usd[1]:.0f}\n"
            f"\n{prof.notes}"
        )
        self.profile_notes.setPlainText(text)

    def _update_gate(self, reviewed: bool):
        can = (
            reviewed and
            self.state.mesh is not None and
            self.state.audio is not None
        )
        self.save_btn.setEnabled(can)
        self.export_only_btn.setEnabled(can)
        if can:
            self.gate_label.setText("✓ Ready to export.")
            self.gate_label.setStyleSheet("color: #285c3a;")
        elif self.state.mesh is None:
            self.gate_label.setText("Load a WAV first.")
            self.gate_label.setStyleSheet("color: #555;")
        elif not reviewed:
            self.gate_label.setText(
                "Open the Verify tab, check the overlay matches the audio, "
                "and tick \"I've reviewed the overlay\" to enable export."
            )
            self.gate_label.setStyleSheet("color: #a26b00;")

    # ------------------------------------------------------------------

    def _save_and_export(self):
        if self.state.source_wav is None:
            QMessageBox.warning(self, "No source", "Load a WAV first.")
            return
        key = self.profile_combo.currentData()
        try:
            entry_dir = new_entry_dir(self.state.config.title or "untitled")
            self._log(f"library entry → {entry_dir}")

            # Save diagnostic overlay PNG alongside.
            fig = build_figure(self.state.audio, self.state.envelopes,
                               self.state.config.geometry_params())
            png_path = entry_dir / "preview.png"
            save_png(fig, str(png_path))

            save_entry(entry_dir, self.state.config, self.state.source_wav,
                       preview_png=png_path)

            out = export_profile(
                self.state.envelopes,
                self.state.config.geometry_params(),
                key,
                entry_dir / "exports",
                title=self.state.config.title,
            )
            self._log(f"export → {out}")
            QMessageBox.information(self, "Done",
                                    f"Saved to library.\n\nExports in:\n{out}")
        except Exception as e:
            self._log("ERROR: " + traceback.format_exc())
            QMessageBox.critical(self, "Export failed", repr(e))

    def _export_to_folder(self):
        key = self.profile_combo.currentData()
        directory = QFileDialog.getExistingDirectory(self, "Choose output folder",
                                                     str(Path.home()))
        if not directory:
            return
        try:
            out = export_profile(
                self.state.envelopes,
                self.state.config.geometry_params(),
                key,
                Path(directory),
                title=self.state.config.title,
            )
            self._log(f"export → {out}")
            QMessageBox.information(self, "Done", f"Exports in:\n{out}")
        except Exception as e:
            self._log("ERROR: " + traceback.format_exc())
            QMessageBox.critical(self, "Export failed", repr(e))

    def _log(self, msg: str):
        self.log.appendPlainText(msg)
