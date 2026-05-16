"""
voice-to-form  —  src/gui/tab_input.py  v0.7.2

Input tab: load a WAV from disk OR record from the mic (open-ended:
press once to start, press again to stop), with pickers for the audio
input device + channel + output device.

v0.5.0:
  - Input and Output pickers laid out side-by-side (compact instead
    of a tall vertical stack).
  - Trim-silence toggle exposed in the UI (default OFF) so the
    audio's natural lead-in becomes the form's tapered start.
  - Fixes a bug where the channel spinbox stayed editable on a
    mono device when the device was already the current selection
    (setCurrentIndex was a no-op and our _device_changed handler
    never fired).

v0.4.0:
  - Playback review: Play/Stop toggle that routes the loaded or
    recorded audio to a chosen output device.
  - Mono input devices disable the channel spinbox (no editing when
    there's nothing to pick).

v0.3.0:
  - High-contrast waveform plot: deep violet curve on a cream
    paper-coloured background, echoing the artist's napkin sketches
    of the form's silhouette.

v0.2.0: toggle record button, input-device + channel pickers.
"""
from __future__ import annotations

__version__ = "0.7.2"

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
    QCheckBox, QGridLayout, QSizePolicy,
)
import pyqtgraph as pg

from .state import AppState
from ..audio import (
    Recorder, InputDevice, list_input_devices, default_input_device_index,
    Player, OutputDevice, list_output_devices, default_output_device_index,
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
        self._output_devices: list[OutputDevice] = []

        self._player = Player()
        # Polls the player so the Play button flips back to ▶ when the
        # buffer finishes naturally (the sounddevice finished_callback
        # fires on the audio thread — easier to poll from Qt).
        self._play_poll = QTimer(self)
        self._play_poll.setInterval(150)
        self._play_poll.timeout.connect(self._poll_player)

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

        # ---- Two-column Input | Output -------------------------------
        cols = QHBoxLayout()
        cols.setSpacing(20)

        # Input column ----------
        inp_col = QVBoxLayout()
        inp_header = QLabel("<b>Input</b>")
        inp_col.addWidget(inp_header)

        inp_dev_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        # Make the dropdown not stretch to fit the longest item; ellide
        # long names instead.
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(18)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        inp_dev_row.addWidget(self.device_combo, stretch=1)
        self.refresh_devices_btn = QPushButton("↻")
        self.refresh_devices_btn.setFixedWidth(28)
        self.refresh_devices_btn.setToolTip("Re-scan audio inputs")
        self.refresh_devices_btn.clicked.connect(self._refresh_devices)
        inp_dev_row.addWidget(self.refresh_devices_btn)
        inp_col.addLayout(inp_dev_row)

        chan_row = QHBoxLayout()
        chan_row.addWidget(QLabel("Channel"))
        self.channel_box = QSpinBox()
        self.channel_box.setRange(1, 1)
        self.channel_box.setValue(1)
        self.channel_box.setFixedWidth(60)
        self.channel_box.valueChanged.connect(self._channel_changed)
        chan_row.addWidget(self.channel_box)
        self.channel_hint = QLabel("(of 1)")
        self.channel_hint.setStyleSheet("color: #888")
        chan_row.addWidget(self.channel_hint)
        chan_row.addStretch()
        inp_col.addLayout(chan_row)

        rec_row = QHBoxLayout()
        self.record_btn = QPushButton("● Record")
        self.record_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 6px 12px; }"
        )
        self.record_btn.clicked.connect(self._toggle_record)
        rec_row.addWidget(self.record_btn)
        self.record_time_label = QLabel("")
        self.record_time_label.setStyleSheet(
            "font-family: Menlo, Monaco, monospace; color: #555;"
        )
        rec_row.addWidget(self.record_time_label)
        rec_row.addStretch()
        inp_col.addLayout(rec_row)
        inp_col.addStretch()

        # Output column ----------
        out_col = QVBoxLayout()
        out_col.addWidget(QLabel("<b>Output</b>"))

        out_dev_row = QHBoxLayout()
        self.output_combo = QComboBox()
        self.output_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        self.output_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.output_combo.setMinimumContentsLength(18)
        self.output_combo.currentIndexChanged.connect(self._output_device_changed)
        out_dev_row.addWidget(self.output_combo, stretch=1)
        self.refresh_outputs_btn = QPushButton("↻")
        self.refresh_outputs_btn.setFixedWidth(28)
        self.refresh_outputs_btn.setToolTip("Re-scan audio outputs")
        self.refresh_outputs_btn.clicked.connect(self._refresh_output_devices)
        out_dev_row.addWidget(self.refresh_outputs_btn)
        out_col.addLayout(out_dev_row)

        # Empty filler to line the Play button up with Record button vertically.
        filler = QLabel("")
        filler.setFixedHeight(self.channel_box.sizeHint().height())
        out_col.addWidget(filler)

        play_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 6px 12px; }"
        )
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setEnabled(False)
        play_row.addWidget(self.play_btn)
        play_row.addStretch()
        out_col.addLayout(play_row)
        out_col.addStretch()

        cols.addLayout(inp_col, stretch=1)
        cols.addLayout(out_col, stretch=1)
        src_layout.addLayout(cols)

        # ---- Trim toggle (full-width, below the two columns) ----------
        trim_row = QHBoxLayout()
        self.trim_check = QCheckBox("Trim leading/trailing silence")
        self.trim_check.setToolTip(
            "When OFF (default), the recording's natural lead-in/fade-out "
            "becomes the form's tapered ends.  Turn ON to strip dead air."
        )
        self.trim_check.setChecked(self.state.config.audio.trim_silence_enabled)
        self.trim_check.toggled.connect(self._trim_toggled)
        trim_row.addWidget(self.trim_check)
        trim_row.addStretch()
        src_layout.addLayout(trim_row)

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

        # Populate device lists now.
        self._refresh_devices()
        self._refresh_output_devices()

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
        # setCurrentIndex doesn't fire signals if the index didn't
        # change (e.g. it was already 0 for "System default" after the
        # addItem loop).  Call the handler explicitly so the channel
        # spinbox's enabled state is correct on first load.
        self._device_changed(self.device_combo.currentIndex())
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
        # Mono interfaces have nothing to pick — disable the spinbox.
        mono = (max_ch <= 1)
        self.channel_box.setEnabled(not mono)
        self.channel_box.setToolTip(
            "Only one input channel on this device." if mono else ""
        )

    def _channel_changed(self, value: int):
        # Stored as 0-indexed.
        self.state.config.audio.input_channel = max(0, int(value) - 1)

    def _trim_toggled(self, checked: bool):
        self.state.config.audio.trim_silence_enabled = bool(checked)
        # If audio is already loaded, re-run the pipeline so the
        # taper-vs-trim choice takes effect immediately.
        if self.state.source_wav is not None:
            try:
                self.state.load_source(self.state.source_wav)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Output device picker + playback
    # ------------------------------------------------------------------

    def _refresh_output_devices(self):
        self._output_devices = list_output_devices()
        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        self.output_combo.addItem("System default", userData=None)
        for d in self._output_devices:
            self.output_combo.addItem(d.label(), userData=d.index)
        self.output_combo.blockSignals(False)

        cfg_idx = self.state.config.audio.output_device_index
        target = 0
        if cfg_idx is not None:
            for i in range(self.output_combo.count()):
                if self.output_combo.itemData(i) == cfg_idx:
                    target = i
                    break
        self.output_combo.setCurrentIndex(target)
        # Same no-op-signal gotcha as the input combo — call directly.
        self._output_device_changed(self.output_combo.currentIndex())

    def _output_device_changed(self, _i: int):
        idx = self.output_combo.currentData()
        self.state.config.audio.output_device_index = idx
        # If we're currently playing, restart on the new device.
        if self._player.is_playing and self.state.audio is not None:
            sr = self.state.sample_rate or 22050
            self._player.play(self.state.audio, sr, device_index=idx)

    def _toggle_play(self):
        if self._player.is_playing:
            self._player.stop()
            self._update_play_button(False)
            return
        if self.state.audio is None:
            return
        # Stop recording first if it's running — they share hardware
        # routing in some setups, and the user obviously wants to
        # listen now.
        if self._recorder is not None and self._recorder.is_recording:
            self._stop_recording()
        try:
            self._player.play(
                self.state.audio,
                self.state.sample_rate or 22050,
                device_index=self.state.config.audio.output_device_index,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Playback failed",
                f"{e!r}\n\nCheck the output device selection.",
            )
            return
        self._update_play_button(True)
        self._play_poll.start()

    def _poll_player(self):
        if not self._player.is_playing:
            self._play_poll.stop()
            self._update_play_button(False)

    def _update_play_button(self, playing: bool):
        if playing:
            self.play_btn.setText("■ Stop")
            self.play_btn.setStyleSheet(
                "QPushButton { font-weight: bold; padding: 8px 16px; "
                "background-color: #285c3a; color: white; }"
            )
        else:
            self.play_btn.setText("▶ Play")
            self.play_btn.setStyleSheet(
                "QPushButton { font-weight: bold; padding: 8px 16px; }"
            )

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
        # Stop playback first — recording while playing usually feeds
        # the speakers back into the mic.
        if self._player.is_playing:
            self._player.stop()
            self._play_poll.stop()
            self._update_play_button(False)
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
        # Audio is available now — enable playback.
        self.play_btn.setEnabled(y.size > 0)
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
