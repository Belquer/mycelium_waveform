"""tests/test_export.py  v0.1.0"""
from __future__ import annotations

__version__ = "0.1.0"

import json
from pathlib import Path

import numpy as np
import pytest

from src.audio import extract_envelopes
from src.export import export_profile
from src.geometry import GeometryParams
from src.profiles import PROFILES


@pytest.fixture
def fast_params() -> GeometryParams:
    # Smaller resolution keeps the test suite snappy.
    return GeometryParams(nx=120, n_theta=24, length_mm=200.0)


def test_fdm_profile_writes_three_stls(synth_audio, tmp_path, fast_params):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=fast_params.nx)
    out = export_profile(env, fast_params, "FDM_PLASTIC", tmp_path, title="t")
    assert (out / "form.stl").exists()
    assert (out / "form_top.stl").exists()
    assert (out / "form_bottom.stl").exists()
    spec = json.loads((out / "spec.json").read_text())
    assert spec["key"] == "FDM_PLASTIC"
    assert "applied_params" in spec
    assert spec["mesh_stats"]["triangles"] > 0


def test_step_profile_records_step_status(synth_audio, tmp_path, fast_params):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=fast_params.nx)
    out = export_profile(env, fast_params, "SLM_METAL_ALUMINUM", tmp_path, title="t")
    spec = json.loads((out / "spec.json").read_text())
    # STEP either written or NOTE produced.
    assert "step_export" in spec
    if not spec["step_export"]["written"]:
        # The NOTE file must exist on disk.
        assert (Path(spec["step_export"]["path"])).exists()


@pytest.mark.parametrize("key", list(PROFILES.keys()))
def test_every_profile_produces_a_file(synth_audio, tmp_path, fast_params, key):
    """Each profile must produce at least one file plus its spec.json."""
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=fast_params.nx)
    out = export_profile(env, fast_params, key, tmp_path, title="t")
    assert (out / "spec.json").exists()
    spec = json.loads((out / "spec.json").read_text())
    # At least the form.stl is always written (even STEP profiles fall
    # back through the STL path).
    assert (out / "form.stl").exists() or any(f for f in spec["files"])
