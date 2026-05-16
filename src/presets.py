"""
voice-to-form  —  src/presets.py  v0.7.0

Design presets — named bundles of geometry + appearance + audio-
smoothing parameters that can be applied to any form.

Built-in presets ship with the app (carbon fibre, polished bronze,
raw PLA, etc.).  User presets live in
``~/.voice_to_form/presets.yaml``.  Looking the two up via
``all_presets()`` returns user entries first; user names override
built-in names of the same string.

The Preset record intentionally does NOT include the source WAV,
title, notes, or export profile — those are per-form metadata.  A
preset is just the "look" you want.
"""
from __future__ import annotations

__version__ = "0.7.0"

import os
import sys
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

import yaml

print(f"[voice-to-form] presets.py v{__version__}", file=sys.stderr)


PRESETS_PATH = Path(os.path.expanduser("~/.voice_to_form/presets.yaml"))


# Sentinel shown in the dropdown when current settings don't match
# any saved preset.
CUSTOM_LABEL = "(custom)"


@dataclass
class Preset:
    name: str = "untitled"
    # Geometry
    length_mm: float = 240.0
    min_r_mm: float = 0.8
    max_r_mm: float = 40.0
    n_theta: int = 96
    nx: int = 700
    cross_section_aspect: float = 0.7
    # Audio smoothing
    hop_ms: float = 3.0
    digital_jitter_sigma: float = 0.4
    length_smooth_sigma: float = 0.6
    gamma: float = 1.0
    # Appearance
    color_hex: str = "#a8acb1"
    roughness: float = 0.7
    metalness: float = 0.0
    bump_intensity: float = 0.0
    bump_pattern: str = "smooth"
    background: str = "studio_white"
    viewport_bg_hex: str = ""


# --------------------------------------------------------------------------
# Built-in presets — shipped with the app, not editable.
# --------------------------------------------------------------------------

BUILTIN_PRESETS: list[Preset] = [
    Preset(name="default"),
    Preset(
        name="polished bronze",
        color_hex="#a76a3a",
        roughness=0.18,
        metalness=0.92,
        bump_intensity=0.05,
        bump_pattern="smooth",
        background="studio_dark",
    ),
    Preset(
        name="raw PLA sculpture",
        color_hex="#f0eee6",
        roughness=0.85,
        metalness=0.0,
        bump_intensity=0.35,
        bump_pattern="layered (FDM)",
        background="studio_white",
    ),
    Preset(
        name="carbon fiber",
        color_hex="#1a1a1a",
        roughness=0.45,
        metalness=0.25,
        bump_intensity=0.55,
        bump_pattern="woven (carbon)",
        background="black_void",
    ),
    Preset(
        name="bead-blasted aluminum",
        color_hex="#a8acb1",
        roughness=0.55,
        metalness=0.78,
        bump_intensity=0.40,
        bump_pattern="beadblasted",
        background="cool_studio",
    ),
    Preset(
        name="mycelium cocoon",
        color_hex="#e8dcc1",
        roughness=0.95,
        metalness=0.0,
        bump_intensity=0.65,
        bump_pattern="mycelium-colonized",
        background="mycology_lab",
    ),
    Preset(
        name="terracotta ember",
        color_hex="#b4583a",
        roughness=0.80,
        metalness=0.05,
        bump_intensity=0.30,
        bump_pattern="porous (SLS)",
        background="warm_gallery",
    ),
    Preset(
        name="brushed titanium",
        color_hex="#bcc1c6",
        roughness=0.35,
        metalness=0.85,
        bump_intensity=0.45,
        bump_pattern="brushed",
        background="studio_dark",
    ),
]


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def load_user_presets() -> list[Preset]:
    """Load user presets from disk.  Returns an empty list if the file
    is missing or unreadable."""
    if not PRESETS_PATH.exists():
        return []
    try:
        raw = yaml.safe_load(PRESETS_PATH.read_text()) or {}
    except Exception as e:
        print(f"[voice-to-form] presets load failed: {e!r}", file=sys.stderr)
        return []
    items = raw.get("presets") or []
    valid_keys = {f.name for f in fields(Preset)}
    out: list[Preset] = []
    for d in items:
        if not isinstance(d, dict):
            continue
        kwargs = {k: v for k, v in d.items() if k in valid_keys}
        try:
            out.append(Preset(**kwargs))
        except Exception as e:
            print(f"[voice-to-form] skipped malformed preset {d!r}: {e!r}",
                  file=sys.stderr)
    return out


def save_user_presets(presets: list[Preset]) -> None:
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"presets": [asdict(p) for p in presets]}
    with open(PRESETS_PATH, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def all_presets() -> list[Preset]:
    """Combined list: built-ins followed by user presets.

    User presets win on name collision — they're shown in place of the
    same-named built-in.
    """
    user = load_user_presets()
    user_names = {p.name for p in user}
    return [p for p in BUILTIN_PRESETS if p.name not in user_names] + user


def save_or_replace(preset: Preset) -> None:
    """Insert or replace by name in the user file.  Built-ins remain
    untouched on disk — replacing a built-in name just hides the
    built-in until the user preset is deleted."""
    users = load_user_presets()
    users = [p for p in users if p.name != preset.name]
    users.append(preset)
    save_user_presets(users)


def delete_user_preset(name: str) -> bool:
    """Remove a user preset.  Returns True iff something was removed.
    Built-ins can't be deleted (they live in code)."""
    users = load_user_presets()
    new = [p for p in users if p.name != name]
    if len(new) == len(users):
        return False
    save_user_presets(new)
    return True


def is_builtin(name: str) -> bool:
    return any(p.name == name for p in BUILTIN_PRESETS)


def user_has(name: str) -> bool:
    return any(p.name == name for p in load_user_presets())
