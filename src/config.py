"""
voice-to-form  —  src/config.py  v0.1.0

YAML persistence for per-form configs and the global app settings.

Per-form config sits inside library/<entry>/config.yaml and records
everything needed to reproduce the form from its source WAV.  Global
settings (recent palette, last-used profile, window pos) live in
~/.voice_to_form/settings.yaml.
"""
from __future__ import annotations

__version__ = "0.1.0"

import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

import yaml

from .geometry import GeometryParams, LENGTH_MM_DEFAULT, MIN_R_MM_DEFAULT, MAX_R_MM_DEFAULT, N_THETA_DEFAULT, NX_DEFAULT

print(f"[voice-to-form] config.py v{__version__}", file=sys.stderr)


APP_DIR = Path(os.path.expanduser("~/.voice_to_form"))
APP_DIR.mkdir(parents=True, exist_ok=True)
GLOBAL_SETTINGS_PATH = APP_DIR / "settings.yaml"


# --------------------------------------------------------------------------
# Per-form config
# --------------------------------------------------------------------------

DEFAULT_PALETTE = [
    {"name": "matte black",        "hex": "#1a1a1a"},
    {"name": "warm bronze",        "hex": "#a76a3a"},
    {"name": "brushed aluminum",   "hex": "#a8acb1"},
    {"name": "raw PLA white",      "hex": "#f0eee6"},
    {"name": "deep charcoal",      "hex": "#2c2d31"},
    {"name": "terracotta clay",    "hex": "#b4583a"},
    {"name": "mycelium cream",     "hex": "#e8dcc1"},
    # Artist's project palette
    {"name": "void black",         "hex": "#000000"},
    {"name": "ember red",          "hex": "#b32a1f"},
    {"name": "violet",             "hex": "#5e2a8a"},
    {"name": "saffron",            "hex": "#e89a1a"},
    {"name": "teal",               "hex": "#1f7a82"},
]


@dataclass
class AudioParams:
    hop_ms: float = 3.0
    nx: int = NX_DEFAULT
    target_sr: int = 22050
    trim_top_db: float = 30.0
    digital_jitter_sigma: float = 0.4
    length_smooth_sigma: float = 0.6
    gamma: float = 1.0


@dataclass
class AppearanceParams:
    color_hex: str = "#1a1a1a"
    roughness: float = 0.7
    metalness: float = 0.0
    bump_intensity: float = 0.0
    bump_pattern: str = "smooth"
    background: str = "studio_white"
    light_temp_k: int = 5200
    light_rig_rotation_deg: float = 0.0
    raking_light: bool = False


@dataclass
class FormConfig:
    title: str = "untitled"
    notes: str = ""
    source_wav_relpath: str = "source.wav"
    audio: AudioParams = field(default_factory=AudioParams)
    geometry_length_mm: float = LENGTH_MM_DEFAULT
    geometry_min_r_mm: float = MIN_R_MM_DEFAULT
    geometry_max_r_mm: float = MAX_R_MM_DEFAULT
    geometry_n_theta: int = N_THETA_DEFAULT
    geometry_nx: int = NX_DEFAULT
    appearance: AppearanceParams = field(default_factory=AppearanceParams)
    last_profile_key: str = "FDM_PLASTIC"
    reviewed_overlay: bool = False
    voice_to_form_version: str = "0.1.0"

    def geometry_params(self) -> GeometryParams:
        return GeometryParams(
            length_mm=self.geometry_length_mm,
            min_r_mm=self.geometry_min_r_mm,
            max_r_mm=self.geometry_max_r_mm,
            n_theta=self.geometry_n_theta,
            nx=self.geometry_nx,
        )


def save_form_config(cfg: FormConfig, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(_dataclass_to_dict(cfg), f, sort_keys=False)
    return path


def load_form_config(path: str | Path) -> FormConfig:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return _dict_to_form_config(raw)


def _dataclass_to_dict(obj) -> dict:
    """Recursive asdict that descends into our small dataclasses only."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _dataclass_to_dict(v) for k, v in asdict(obj).items()}
    return obj


def _dict_to_form_config(d: dict) -> FormConfig:
    audio_d = d.get("audio", {}) or {}
    appearance_d = d.get("appearance", {}) or {}
    return FormConfig(
        title=d.get("title", "untitled"),
        notes=d.get("notes", ""),
        source_wav_relpath=d.get("source_wav_relpath", "source.wav"),
        audio=AudioParams(**_filter_kwargs(AudioParams, audio_d)),
        geometry_length_mm=d.get("geometry_length_mm", LENGTH_MM_DEFAULT),
        geometry_min_r_mm=d.get("geometry_min_r_mm", MIN_R_MM_DEFAULT),
        geometry_max_r_mm=d.get("geometry_max_r_mm", MAX_R_MM_DEFAULT),
        geometry_n_theta=d.get("geometry_n_theta", N_THETA_DEFAULT),
        geometry_nx=d.get("geometry_nx", NX_DEFAULT),
        appearance=AppearanceParams(**_filter_kwargs(AppearanceParams, appearance_d)),
        last_profile_key=d.get("last_profile_key", "FDM_PLASTIC"),
        reviewed_overlay=d.get("reviewed_overlay", False),
        voice_to_form_version=d.get("voice_to_form_version", "0.1.0"),
    )


def _filter_kwargs(cls, d: dict) -> dict:
    """Drop keys not in the dataclass — keeps load forward-compatible."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in names}


# --------------------------------------------------------------------------
# Global settings
# --------------------------------------------------------------------------

@dataclass
class GlobalSettings:
    last_library_open: Optional[str] = None
    custom_palette: list[dict] = field(default_factory=list)
    last_profile_key: str = "FDM_PLASTIC"
    window_geometry_b64: Optional[str] = None  # opaque, written by Qt saveGeometry()


def load_global_settings() -> GlobalSettings:
    if not GLOBAL_SETTINGS_PATH.exists():
        return GlobalSettings()
    try:
        raw = yaml.safe_load(GLOBAL_SETTINGS_PATH.read_text()) or {}
        return GlobalSettings(**_filter_kwargs(GlobalSettings, raw))
    except Exception as e:
        print(f"[voice-to-form] settings load failed: {e!r}; using defaults", file=sys.stderr)
        return GlobalSettings()


def save_global_settings(s: GlobalSettings) -> None:
    with open(GLOBAL_SETTINGS_PATH, "w") as f:
        yaml.safe_dump(asdict(s), f, sort_keys=False)
