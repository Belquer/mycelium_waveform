"""
voice-to-form  —  src/gui/tab_input.py  v0.3.0

Input tab: load a WAV from disk OR record from the mic (open-ended:
press once to start, press again to stop), with a picker for the audio
input device + channel.

v0.3.0:
  - High-contrast waveform plot: deep violet curve on a cream
    paper-coloured background, echoing the artist's napkin sketches
    of the form's silhouette.
  - Recorded WAVs land in library/ so the auto-generated examples/
    folder doesn't accumulate clutter.

v0.2.0: toggle record button, input-device + channel pickers.
"""
from __future__ import annotations

__version__ = "0.3.0"

import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel,
    QLineEdit, QPlainTextEdit, QSpinBox, QGroupBox, QMessageBox, QComboBox,
)
import pyqtgraph as pg

from .state import AppState
from ..audio import (
    Recorder, InputDevice, list_input_devices, default_input_device_index,
    write_wav,
)

print(f"[voice-to-form] tab_input.py v{__version__}", file=sys.stderr)


class InputTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._recorder: Optional[Recorder] = None
        self._record_started_at: float = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._update_record_time)
        self._devices: list[InputDevice] = []
        self._build_ui()
        state.audio_loaded.connect(self._on_audio_loaded)

    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- Source group ------------------------------------------------
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

        src_layout.addWidget(_hline())

        # ---- Input device + channel
        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Input device"))
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        dev_row.addWidget(self.device_combo, stretch=1)

        self.refresh_devices_btn = QPushButton("↻")
        self.refresh_devices_btn.setFixedWidth(32)
        self.refresh_devices_btn.setToolTip("Re-scan audio devices")
        self.refresh_devices_btn.clicked.connect(self._refresh_devices)
        dev_row.addWidget(self.refresh_devices_btn)
        src_layout.addLayout(dev_row)

        chan_row = QHBoxLayout()
        chan_row.addWidget(QLabel("Channel"))
        self.channel_box = QSpinBox()
        self.channel_box.setRange(1, 1)
        self.channel_box.setValue(1)
        self.channel_box.valueChanged.connect(self._channel_changed)
        chan_row.addWidget(self.channel_box)
        self.channel_hint = QLabel("(of 1)")
        self.channel_hint.setStyleSheet("color: #888")
        chan_row.addWidget(self.channel_hint)
        chan_row.addStretch()
        src_layout.addLayout(chan_row)

        # ---- Record toggle
        rec_row = QHBoxLayout()
        self.record_btn = QPushButton("● Record")
        self.record_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 8px 16px; }"
        )
        self.record_btn.clicked.connect(self._toggle_record)
        rec_row.addWidget(self.record_btn)

        self.record_time_label = QLabel("")
        self.record_time_label.setStyleSheet(
            "font-family: ui-monospace, Menlo, monospace; color: #555;"
        )
        rec_row.addWidget(self.record_time_label)
        rec_row.addStretch()
        src_layout.addLayout(rec_row)

        # Info row
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #444")
        src_layout.addWidget(self.info_label)

        layout.addWidget(src_group)

        # ---- Meta group --------------------------------------------------
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

        # ---- Waveform preview --------------------------------------------
        # Cream paper background + deep-violet ink: high contrast and a
        # callback to the artist's hand-drawn waveform sketches.
        WAVE_BG = "#f7f3e8"          # warm cream / butcher paper
        WAVE_INK = "#3a1f5d"         # deep ink violet
        WAVE_GRID = "#d8cfb8"        # subtle paper-grid colour
        WAVE_AXIS = "#5a4a35"

        self.wave_plot = pg.PlotWidget(title="Waveform")
        self.wave_plot.setMaximumHeight(180)
        self.wave_plot.setBackground(WAVE_BG)
        self.wave_plot.showGrid(x=True, y=True, alpha=0.35)
        self.wave_plot.setLabel("bottom", "samples", color=WAVE_AXIS)
        # Axis pens — match the ink/paper aesthetic.
        for axis_name in ("bottom", "left", "top", "right"):
            axis = self.wave_plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(WAVE_AXIS, width=0.8))
            axis.setTextPen(pg.mkPen(WAVE_AXIS))
            axis.setGrid(0)
        # Title in deep ink too.
        self.wave_plot.getPlotItem().setTitle("Waveform", color=WAVE_AXIS, size="10pt")
        self.wave_curve = self.wave_plot.plot(
            [], [], pen=pg.mkPen(WAVE_INK, width=1.1),
        )
        layout.addWidget(self.wave_plot, stretch=1)

        # Populate device list now.
        self._refresh_devices()

    # ------------------------------------------------------------------
    # Device picker
    # ------------------------------------------------------------------

    def _refresh_devices(self):
        self._devices = list_input_devices()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        # Index 0 is the system default.
        self.device_combo.addItem("System default", userData=None)
        for d in self._devices:
            self.device_combo.addItem(d.label(), userData=d.index)
        self.device_combo.blockSignals(False)

        # Try to pre-select whatever's already in the config.
        cfg_idx = self.state.config.audio.input_device_index
        self._select_device_by_index(cfg_idx)
        self._channel_changed(self.channel_box.value())

    def _select_device_by_index(self, idx: Optional[int]):
        target = 0
        if idx is not None:
            for i in range(self.device_combo.count()):
                if self.device_combo.itemData(i) == idx:
                    target = i
                    break
        self.device_combo.setCurrentIndex(target)

    def _device_changed(self, _i: int):
        idx = self.device_combo.currentData()
        self.state.config.audio.input_device_index = idx
        # Update channel range to that device's max.
        max_ch = 1
        if idx is not None:
            for d in self._devices:
                if d.index == idx:
                    max_ch = d.max_channels
                    break
        elif self._devices:
            # System default: assume the first listed (typical macOS layout).
            max_ch = self._devices[0].max_channels
        self.channel_box.setRange(1, max(1, max_ch))
        # Preserve the user's stored channel within bounds.
        wanted = max(1, min(self.state.config.audio.input_channel + 1, max_ch))
        self.channel_box.setValue(wanted)
        self.channel_hint.setText(f"(of {max_ch})")

    def _channel_changed(self, value: int):
        # Stored as 0-indexed.
        self.state.config.audio.input_channel = max(0, int(value) - 1)

    # ------------------------------------------------------------------
    # Load / Record
    # ------------------------------------------------------------------

    def _load_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load WAV", str(Path.home()),
            "Audio (*.wav *.aif *.aiff *.flac *.mp3)"
        )
        if not path:
            return
        try:
            self.state.load_source(Path(path))
            self.path_label.setText(path)
            self.path_label.setStyleSheet("color: #222")
        except Exception as e:
            QMessageBox.critical(self, "Load failed", repr(e))

    def _toggle_record(self):
        if self._recorder is None or not self._recorder.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        try:
            audio = self.state.config.audio
            self._recorder = Recorder(
                sr=audio.target_sr,
                device_index=audio.input_device_index,
                channel=audio.input_channel,
            )
            self._recorder.start()
        except Exception as e:
            self._recorder = None
            QMessageBox.critical(
                self, "Could not start recording",
                f"{e!r}\n\nCheck the input device + channel selection.",
            )
            return

        self._record_started_at = time.monotonic()
        self.record_btn.setText("■ Stop")
        self.record_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 8px 16px; "
            "background-color: #b32a1f; color: white; }"
        )
        self._tick.start()
        self._update_record_time()

    def _stop_recording(self):
        if self._recorder is None:
            return
        self._tick.stop()
        try:
            audio = self._recorder.stop()
        except Exception as e:
            QMessageBox.critical(self, "Recording stopped with error",
                                 traceback.format_exc())
            audio = np.zeros(0, dtype=np.float32)
        finally:
            self._recorder = None

        self.record_btn.setText("● Record")
        self.record_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 8px 16px; }"
        )

        if audio.size < int(0.05 * self.state.config.audio.target_sr):
            self.record_time_label.setText("(too short)")
            return

        # Write to disk so the rest of the pipeline (library, reload-on-
        # open) keeps a faithful copy.
        out = Path("examples") / f"recorded_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        try:
            write_wav(out, audio, self.state.config.audio.target_sr)
        except Exception as e:
            QMessageBox.critical(self, "Could not save recording", repr(e))
            return

        try:
            self.state.load_source(out)
            self.path_label.setText(str(out))
            self.path_label.setStyleSheet("color: #222")
        except Exception as e:
            QMessageBox.critical(self, "Loaded recording but pipeline failed",
                                 repr(e))

    def _update_record_time(self):
        elapsed = time.monotonic() - self._record_started_at
        mins, secs = divmod(elapsed, 60.0)
        self.record_time_label.setText(f"● {int(mins):02d}:{secs:04.1f}")

    # ------------------------------------------------------------------

    def _title_changed(self, text: str):
        self.state.config.title = text

    def _notes_changed(self):
        self.state.config.notes = self.notes_edit.toPlainText()

    def _on_audio_loaded(self, y: np.ndarray):
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


def _hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #ddd;")
    return line
