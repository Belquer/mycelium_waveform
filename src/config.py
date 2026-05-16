"""
voice-to-form  —  src/config.py  v0.4.0

YAML persistence for per-form configs and the global app settings.

v0.4.0 — default viewport background is now `studio_white` (gallery
look).  The studio_white preset itself is brightened to a true
off-white so it actually reads as "white" rather than light gray.

v0.3.0 — adds `geometry_cross_section_aspect` (vertical-ellipse cross
section) and `viewport_bg_hex` (adjustable viewport background)
threaded through FormConfig.

v0.2.0 added input-device + input-channel fields to AudioParams and
changed the default appearance colour to a brushed-aluminum mid-tone
so the preview is visible against the dark viewport without picking
a colour first.

Per-form config sits inside library/<entry>/config.yaml and records
everything needed to reproduce the form from its source WAV.  Global
settings (recent palette, last-used profile, window pos) live in
~/.voice_to_form/settings.yaml.
"""
from __future__ import annotations

__version__ = "0.4.0"

import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

import yaml

from .geometry import (
    GeometryParams, LENGTH_MM_DEFAULT, MIN_R_MM_DEFAULT, MAX_R_MM_DEFAULT,
    N_THETA_DEFAULT, NX_DEFAULT, CROSS_SECTION_ASPECT_DEFAULT,
)

print(f"[voice-to-form] config.py v{__version__}", file=sys.stderr)


APP_DIR = Path(os.path.expanduser("~/.voice_to_form"))
APP_DIR.mkdir(parents=True, exist_ok=True)
GLOBAL_SETTINGS_PATH = APP_DIR / "settings.yaml"


# --------------------------------------------------------------------------
# Per-form config
# --------------------------------------------------------------------------

# Background preset name → viewport clear-colour hex.  The Appearance
# tab's "Background" dropdown shows these names; the preview reads the
# hex.  v0.2 keeps it simple (solid colours).  Gradient + HDR env-map
# support stays on the v0.3 roadmap.
BACKGROUND_PRESETS_RGB: dict[str, str] = {
    "studio_white":     "#f5f5f5",
    "studio_dark":      "#2e3236",
    "black_void":       "#000000",
    "warm_gallery":     "#3b332b",
    "cool_studio":      "#1f242a",
    "mycology_lab":     "#3a4238",
    "dark_wood_plinth": "#2a201a",
    "dining_table":     "#5b4632",
    "sky":              "#7b9bba",
    "cocoon":           "#473226",
}


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
    # Input device for mic recording.  None = system default.  Integer
    # is a sounddevice device index from list_input_devices().
    input_device_index: Optional[int] = None
    # 0-indexed channel within the chosen device.
    input_channel: int = 0
    # Output device for playback review.  None = system default.
    output_device_index: Optional[int] = None


@dataclass
class AppearanceParams:
    # Default to a mid-tone "brushed aluminum" so the form is visible
    # against the dark viewport before the artist picks a colour.  The
    # original matte-black default rendered as black-on-black.
    color_hex: str = "#a8acb1"
    roughness: float = 0.7
    metalness: float = 0.0
    bump_intensity: float = 0.0
    bump_pattern: str = "smooth"
    # "studio_white" gives the clean gallery / 3D-printing-service look.
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
    geometry_cross_section_aspect: float = CROSS_SECTION_ASPECT_DEFAULT
    appearance: AppearanceParams = field(default_factory=AppearanceParams)
    # Viewport background as an arbitrary hex.  If empty, the named
    # preset in `appearance.background` is used.
    viewport_bg_hex: str = ""
    last_profile_key: str = "FDM_PLASTIC"
    reviewed_overlay: bool = False
    voice_to_form_version: str = "0.3.0"

    def geometry_params(self) -> GeometryParams:
        return GeometryParams(
            length_mm=self.geometry_length_mm,
            min_r_mm=self.geometry_min_r_mm,
            max_r_mm=self.geometry_max_r_mm,
            n_theta=self.geometry_n_theta,
            nx=self.geometry_nx,
            cross_section_aspect=self.geometry_cross_section_aspect,
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
        geometry_cross_section_aspect=d.get(
            "geometry_cross_section_aspect", CROSS_SECTION_ASPECT_DEFAULT,
        ),
        appearance=AppearanceParams(**_filter_kwargs(AppearanceParams, appearance_d)),
        viewport_bg_hex=d.get("viewport_bg_hex", ""),
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
