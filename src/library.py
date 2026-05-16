"""
voice-to-form  —  src/library.py  v0.1.0

Library layout — one folder per form, named <YYYY-MM-DD>_<slug>.

  library/
    2026-05-16_multitudes/
      source.wav            ← copy of the input (not a reference)
      config.yaml           ← FormConfig
      preview.png           ← latest diagnostic overlay
      thumb.png             ← small render for grid (optional, v0.2)
      exports/
        FDM_PLASTIC/
          form.stl
          form_top.stl
          form_bottom.stl
          spec.json

Source WAV is COPIED in, not referenced — the original may move or be
deleted and the library must keep working.
"""
from __future__ import annotations

__version__ = "0.1.0"

import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import FormConfig, save_form_config, load_form_config

print(f"[voice-to-form] library.py v{__version__}", file=sys.stderr)


LIBRARY_ROOT = Path(__file__).resolve().parent.parent / "library"


@dataclass
class LibraryEntry:
    path: Path
    title: str
    created_iso: str
    config_path: Path
    source_wav: Path
    preview_png: Optional[Path]
    exports_dir: Path

    def load_config(self) -> FormConfig:
        return load_form_config(self.config_path)


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_")
    return s or "untitled"


def new_entry_dir(title: str, when: Optional[str] = None) -> Path:
    """Create and return a fresh library entry directory."""
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    date = when or time.strftime("%Y-%m-%d")
    base = f"{date}_{slugify(title)}"
    candidate = LIBRARY_ROOT / base
    i = 2
    while candidate.exists():
        candidate = LIBRARY_ROOT / f"{base}_{i}"
        i += 1
    candidate.mkdir(parents=True)
    (candidate / "exports").mkdir()
    return candidate


def save_entry(
    entry_dir: Path,
    cfg: FormConfig,
    source_wav: Path,
    preview_png: Optional[Path] = None,
) -> LibraryEntry:
    """Copy the source WAV into the entry, write config, return entry handle."""
    entry_dir = Path(entry_dir)
    dest_wav = entry_dir / "source.wav"
    if source_wav.resolve() != dest_wav.resolve():
        shutil.copy2(source_wav, dest_wav)
    cfg.source_wav_relpath = "source.wav"
    save_form_config(cfg, entry_dir / "config.yaml")
    if preview_png is not None and preview_png.exists():
        shutil.copy2(preview_png, entry_dir / "preview.png")
    return _to_entry(entry_dir)


# --------------------------------------------------------------------------
# Listing / loading
# --------------------------------------------------------------------------

def list_entries() -> list[LibraryEntry]:
    if not LIBRARY_ROOT.exists():
        return []
    entries: list[LibraryEntry] = []
    for child in sorted(LIBRARY_ROOT.iterdir(), reverse=True):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not (child / "config.yaml").exists():
            continue
        entries.append(_to_entry(child))
    return entries


def _to_entry(entry_dir: Path) -> LibraryEntry:
    cfg_path = entry_dir / "config.yaml"
    cfg = load_form_config(cfg_path) if cfg_path.exists() else FormConfig()
    return LibraryEntry(
        path=entry_dir,
        title=cfg.title,
        created_iso=_parse_date_from_name(entry_dir.name),
        config_path=cfg_path,
        source_wav=entry_dir / cfg.source_wav_relpath,
        preview_png=(entry_dir / "preview.png") if (entry_dir / "preview.png").exists() else None,
        exports_dir=entry_dir / "exports",
    )


def _parse_date_from_name(name: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""
