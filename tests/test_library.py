"""tests/test_library.py  v0.1.0"""
from __future__ import annotations

__version__ = "0.1.0"

from pathlib import Path

import pytest

import src.library as lib_mod
from src.library import slugify, new_entry_dir, save_entry, list_entries
from src.config import FormConfig, AudioParams, AppearanceParams, save_form_config, load_form_config


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello_world"
    assert slugify("   leading/trailing   ") == "leading_trailing"
    assert slugify("") == "untitled"


def test_config_round_trip(tmp_path):
    cfg = FormConfig(
        title="multitudes",
        notes="first attempt",
        audio=AudioParams(hop_ms=4.0, gamma=1.0),
        geometry_max_r_mm=35.0,
        appearance=AppearanceParams(color_hex="#b32a1f", roughness=0.4),
    )
    p = tmp_path / "config.yaml"
    save_form_config(cfg, p)
    loaded = load_form_config(p)
    assert loaded.title == "multitudes"
    assert loaded.notes == "first attempt"
    assert loaded.audio.hop_ms == 4.0
    assert loaded.audio.gamma == 1.0
    assert loaded.geometry_max_r_mm == 35.0
    assert loaded.appearance.color_hex == "#b32a1f"
    assert loaded.appearance.roughness == 0.4


def test_library_save_and_list(tmp_path, synth_wav, monkeypatch):
    monkeypatch.setattr(lib_mod, "LIBRARY_ROOT", tmp_path / "lib")
    cfg = FormConfig(title="multitudes")
    entry_dir = new_entry_dir("multitudes")
    save_entry(entry_dir, cfg, Path(synth_wav))

    # source.wav was copied, not referenced.
    assert (entry_dir / "source.wav").exists()
    assert entry_dir.parent == tmp_path / "lib"

    entries = list_entries()
    titles = [e.title for e in entries]
    assert "multitudes" in titles


def test_library_load_round_trip(tmp_path, synth_wav, monkeypatch):
    monkeypatch.setattr(lib_mod, "LIBRARY_ROOT", tmp_path / "lib")
    cfg = FormConfig(title="echo", geometry_length_mm=180.0)
    entry_dir = new_entry_dir("echo")
    save_entry(entry_dir, cfg, Path(synth_wav))

    [entry] = list_entries()
    loaded = entry.load_config()
    assert loaded.title == "echo"
    assert loaded.geometry_length_mm == 180.0
