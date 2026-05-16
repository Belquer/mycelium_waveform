"""
voice-to-form  —  src/gui/tab_verify.py  v0.1.0

Verify tab — hosts the diagnostic overlay (three stacked plots plus
the numerical peak proportion table) and the "Reviewed" checkbox
that gates Export.

The checkbox is a self-discipline gate (single-user app, not security).
But it does fire AppState.set_overlay_reviewed which the Export tab
listens to, and any change to envelopes / mesh resets it.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel,
    QPlainTextEdit, QSplitter,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from .state import AppState
from ..overlay import build_figure, peak_report

print(f"[voice-to-form] tab_verify.py v{__version__}", file=sys.stderr)


class VerifyTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._canvas: FigureCanvas | None = None
        self._build_ui()

        state.envelopes_changed.connect(lambda *_: self._refresh())
        state.mesh_changed.connect(lambda *_: self._refresh())
        state.overlay_reviewed_changed.connect(self._sync_checkbox)

    def _build_ui(self):
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Diagnostic overlay</b> — check that the form's silhouette tracks the audio."))
        header.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Figure pane
        self._fig_container = QWidget()
        self._fig_layout = QVBoxLayout(self._fig_container)
        self._fig_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(self._fig_container)

        # Side pane: peak report + reviewed checkbox
        side = QWidget()
        slay = QVBoxLayout(side)
        slay.addWidget(QLabel("<b>Peak proportions</b>"))
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setStyleSheet("font-family: ui-monospace, Menlo, monospace;")
        slay.addWidget(self.report_view, stretch=1)

        self.reviewed = QCheckBox("I've reviewed the overlay — proportions look right")
        self.reviewed.stateChanged.connect(self._reviewed_changed)
        slay.addWidget(self.reviewed)

        slay.addWidget(QLabel(
            "<i>This box must be ticked before Export enables.</i>"
        ))

        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([800, 320])

        root.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------

    def _refresh(self):
        if self.state.audio is None or self.state.envelopes is None:
            return
        params = self.state.config.geometry_params()
        fig = build_figure(self.state.audio, self.state.envelopes, params)
        # Swap canvas
        if self._canvas is not None:
            self._fig_layout.removeWidget(self._canvas)
            self._canvas.deleteLater()
        self._canvas = FigureCanvas(fig)
        self._fig_layout.addWidget(self._canvas)

        report = peak_report(self.state.audio, self.state.envelopes)
        self.report_view.setPlainText(report.as_text())
        if report.any_flagged:
            self.report_view.setStyleSheet(
                "font-family: ui-monospace, Menlo, monospace; "
                "background-color: #fff7d6;"
            )
        else:
            self.report_view.setStyleSheet(
                "font-family: ui-monospace, Menlo, monospace;"
            )

    def _reviewed_changed(self, state: int):
        checked = state == Qt.CheckState.Checked.value
        self.state.set_overlay_reviewed(checked)

    def _sync_checkbox(self, value: bool):
        if self.reviewed.isChecked() != value:
            self.reviewed.blockSignals(True)
            self.reviewed.setChecked(value)
            self.reviewed.blockSignals(False)
