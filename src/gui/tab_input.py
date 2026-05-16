"""
voice-to-form  —  src/gui/tab_input.py  v0.1.0

Input tab: load a WAV from disk, optionally record from the mic, show
basic info (duration, peak, sample rate), and a small waveform preview.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel,
    QLineEdit, QPlainTextEdit, QSpinBox, QGroupBox, QMessageBox,
)
import pyqtgraph as pg

from .state import AppState
from ..audio import record_to_wav

print(f"[voice-to-form] tab_input.py v{__version__}", file=sys.stderr)


class _RecorderThread(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, out_path: Path, duration_s: float, sr: int = 22050):
        super().__init__()
        self.out_path = out_path
        self.duration_s = duration_s
        self.sr = sr

    def run(self):
        try:
            record_to_wav(self.out_path, self.duration_s, sr=self.sr)
            self.done.emit(str(self.out_path))
        except Exception as e:
            self.failed.emit(repr(e))


class InputTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._recorder: _RecorderThread | None = None
        self._build_ui()
        state.audio_loaded.connect(self._on_audio_loaded)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Source group ----------------------------------------------------
        src_group = QGroupBox("Source")
        src_layout = QVBoxLayout(src_group)

        row1 = QHBoxLayout()
        self.load_btn = QPushButton("Load WAV…")
        self.load_btn.clicked.connect(self._load_clicked)
        row1.addWidget(self.load_btn)

        self.path_label = QLabel("(no source loaded)")
        self.path_label.setStyleSheet("color: #888")
        row1.addWidget(self.path_label, stretch=1)
        src_layout.addLayout(row1)

        # Mic record row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Record from mic for"))
        self.duration_box = QSpinBox()
        self.duration_box.setRange(1, 30)
        self.duration_box.setValue(3)
        self.duration_box.setSuffix(" s")
        row2.addWidget(self.duration_box)
        self.record_btn = QPushButton("● Record")
        self.record_btn.clicked.connect(self._record_clicked)
        row2.addWidget(self.record_btn)
        row2.addStretch()
        src_layout.addLayout(row2)

        # Info row
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #444")
        src_layout.addWidget(self.info_label)

        layout.addWidget(src_group)

        # Title / notes ---------------------------------------------------
        meta_group = QGroupBox("This form")
        meta_layout = QVBoxLayout(meta_group)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title"))
        self.title_edit = QLineEdit("untitled")
        self.title_edit.textChanged.connect(self._title_changed)
        title_row.addWidget(self.title_edit)
        meta_layout.addLayout(title_row)

        meta_layout.addWidget(QLabel("Notes"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "What is this form? When was it made? Why?"
        )
        self.notes_edit.setMaximumHeight(120)
        self.notes_edit.textChanged.connect(self._notes_changed)
        meta_layout.addWidget(self.notes_edit)

        layout.addWidget(meta_group)

        # Waveform preview ------------------------------------------------
        self.wave_plot = pg.PlotWidget(title="Waveform")
        self.wave_plot.setMaximumHeight(180)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.2)
        self.wave_plot.setLabel("bottom", "samples")
        self.wave_curve = self.wave_plot.plot([], [], pen=pg.mkPen("#444", width=0.6))
        layout.addWidget(self.wave_plot, stretch=1)

    # ------------------------------------------------------------------

    def _load_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load WAV", str(Path.home()), "Audio (*.wav *.aif *.aiff *.flac *.mp3)"
        )
        if not path:
            return
        try:
            self.state.load_source(Path(path))
            self.path_label.setText(path)
            self.path_label.setStyleSheet("color: #222")
        except Exception as e:
            QMessageBox.critical(self, "Load failed", repr(e))

    def _record_clicked(self):
        if self._recorder is not None and self._recorder.isRunning():
            return
        out = Path("examples") / f"recorded_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.record_btn.setEnabled(False)
        self.record_btn.setText("● Recording…")
        self._recorder = _RecorderThread(out, self.duration_box.value())
        self._recorder.done.connect(self._record_done)
        self._recorder.failed.connect(self._record_failed)
        self._recorder.start()

    def _record_done(self, path: str):
        self.record_btn.setEnabled(True)
        self.record_btn.setText("● Record")
        self.state.load_source(Path(path))
        self.path_label.setText(path)
        self.path_label.setStyleSheet("color: #222")

    def _record_failed(self, err: str):
        self.record_btn.setEnabled(True)
        self.record_btn.setText("● Record")
        QMessageBox.critical(self, "Recording failed",
                             f"Could not record audio:\n{err}")

    def _title_changed(self, text: str):
        self.state.config.title = text

    def _notes_changed(self):
        self.state.config.notes = self.notes_edit.toPlainText()

    def _on_audio_loaded(self, y: np.ndarray):
        # Downsample to ~2000 points for the preview plot — drawing 1M samples
        # in pyqtgraph is slow and unreadable.
        if y.size > 2000:
            stride = max(1, y.size // 2000)
            preview = y[::stride]
        else:
            preview = y
        self.wave_curve.setData(np.arange(preview.size), preview)
        sr = self.state.sample_rate or 0
        dur = (y.size / sr) if sr else 0
        peak = float(np.max(np.abs(y))) if y.size else 0.0
        self.info_label.setText(
            f"{dur:.2f} s   ·   sr {sr} Hz   ·   peak {peak:.3f}   ·   {y.size:,} samples"
        )
