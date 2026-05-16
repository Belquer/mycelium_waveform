"""
voice-to-form  —  src/gui/main_window.py  v0.3.0

Four-tab QMainWindow (plus Library): Input → Design → Verify → Export.
Geometry and Appearance are combined into a single Design tab so the
artist isn't shuttling between tabs to compare a parameter change
against the colour/finish.

Library view (thumbnail grid) is a v0.4 roadmap item — v0.3 keeps the
plain list view.
"""
from __future__ import annotations

__version__ = "0.3.0"

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QMessageBox, QFileDialog,
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
)

from .state import AppState
from .tab_input import InputTab
from .tab_geometry import DesignTab
from .tab_verify import VerifyTab
from .tab_export import ExportTab
from ..library import list_entries, LibraryEntry
from ..config import load_form_config

print(f"[voice-to-form] gui/main_window.py v{__version__}", file=sys.stderr)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"voice-to-form v{__version__}")
        self.resize(1280, 820)

        self.state = AppState()

        self.tabs = QTabWidget()
        self.tab_input = InputTab(self.state)
        self.tab_design = DesignTab(self.state)
        self.tab_verify = VerifyTab(self.state)
        self.tab_export = ExportTab(self.state)
        self.tab_library = LibraryTab(self._on_library_open)

        self.tabs.addTab(self.tab_input, "1 · Input")
        self.tabs.addTab(self.tab_design, "2 · Design")
        self.tabs.addTab(self.tab_verify, "3 · Verify")
        self.tabs.addTab(self.tab_export, "4 · Export")
        self.tabs.addTab(self.tab_library, "Library")
        self.setCentralWidget(self.tabs)

        self._build_menus()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"voice-to-form v{__version__} — ready")

    # ------------------------------------------------------------------

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")

        open_act = QAction("Open WAV…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self.tab_input._load_clicked)  # noqa: SLF001
        file_menu.addAction(open_act)

        save_act = QAction("Save to Library + Export", self)
        save_act.setShortcut(QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self.tab_export._save_and_export)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = self.menuBar().addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._about)
        help_menu.addAction(about_act)

    def _about(self):
        QMessageBox.information(
            self, "voice-to-form",
            f"voice-to-form v{__version__}\n"
            "Shared-spine elliptical sweep — voice recordings → 3D-printable forms.\n\n"
            "See README.md for the diagnostic overlay rationale and profile guide.",
        )

    # ------------------------------------------------------------------

    def _on_library_open(self, entry: LibraryEntry):
        try:
            cfg = entry.load_config()
            self.state.config = cfg
            self.state.load_source(entry.source_wav)
            self.statusBar().showMessage(f"Opened library entry: {entry.path.name}")
            self.tabs.setCurrentWidget(self.tab_design)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", repr(e))


class LibraryTab(QWidget):
    """Minimal v0.1 library view — list of entries, double-click to open."""

    def __init__(self, on_open):
        super().__init__()
        self.on_open = on_open
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<b>Library</b> — every saved form lives in <code>library/&lt;date&gt;_&lt;slug&gt;/</code>.<br>"
            "Double-click to reopen with its original settings.<br>"
            "<i>Thumbnail grid view planned for v0.2.</i>"
        ))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.list, stretch=1)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for e in list_entries():
            it = QListWidgetItem(f"{e.created_iso}   {e.title}   ·   {e.path.name}")
            it.setData(Qt.ItemDataRole.UserRole, e)
            self.list.addItem(it)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def _double_clicked(self, item: QListWidgetItem):
        entry: LibraryEntry = item.data(Qt.ItemDataRole.UserRole)
        if entry is not None:
            self.on_open(entry)
