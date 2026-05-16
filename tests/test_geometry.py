"""tests/test_geometry.py  v0.1.0"""
from __future__ import annotations

__version__ = "0.1.0"

import numpy as np
import pytest

from src.audio import extract_envelopes
from src.geometry import (
    GeometryParams, build_mesh, build_half_mesh,
    is_watertight, signed_volume,
)


def _params(nx=200, n_theta=32):
    return GeometryParams(nx=nx, n_theta=n_theta, length_mm=200.0,
                          min_r_mm=0.8, max_r_mm=40.0)


def test_n_theta_must_be_even():
    with pytest.raises(ValueError):
        GeometryParams(n_theta=33)


def test_build_mesh_shape(synth_audio):
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    mesh = build_mesh(env, p)
    # nx * n_theta ring verts plus 2 end-cap centres
    assert mesh.vertices.shape == (p.nx * p.n_theta + 2, 3)
    # Side quads + 2 fans
    expected = 2 * (p.nx - 1) * p.n_theta + 2 * p.n_theta
    assert mesh.faces.shape == (expected, 3)


def test_full_mesh_is_watertight(synth_audio):
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    mesh = build_mesh(env, p)
    assert is_watertight(mesh), "shared-spine mesh must be watertight"


def test_full_mesh_normals_outward(synth_audio):
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    mesh = build_mesh(env, p)
    # Positive signed volume means outward winding.
    assert signed_volume(mesh) > 0, "mesh winding produces negative volume — flip face order"


def test_half_meshes_normals_outward(synth_audio):
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    assert signed_volume(build_half_mesh(env, p, "top")) > 0
    assert signed_volume(build_half_mesh(env, p, "bottom")) > 0


def test_half_meshes_are_watertight(synth_audio):
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    top = build_half_mesh(env, p, "top")
    bot = build_half_mesh(env, p, "bottom")
    assert is_watertight(top), "top-half mesh must be watertight"
    assert is_watertight(bot), "bottom-half mesh must be watertight"


def test_top_and_bottom_share_horizontal_width(synth_audio):
    """The diagnostic that catches the 'two pieces stuck together' bug:
    at every x, the z-extent of the top half must equal the z-extent of
    the bottom half (within floating point).
    """
    y, sr = synth_audio
    p = _params()
    env = extract_envelopes(y, sr, nx=p.nx)
    mesh = build_mesh(env, p)

    verts = mesh.vertices[: p.nx * p.n_theta].reshape(p.nx, p.n_theta, 3)
    half = p.n_theta // 2

    top_z = verts[:, :half, 2]
    bot_z = verts[:, half:, 2]
    # Same z-range per cross-section means same horizontal width.
    np.testing.assert_allclose(
        top_z.max(axis=1), bot_z.max(axis=1), atol=1e-4,
        err_msg="top and bottom must share horizontal radius",
    )
    np.testing.assert_allclose(
        top_z.min(axis=1), bot_z.min(axis=1), atol=1e-4,
    )


def test_min_max_radius_respected(synth_audio):
    y, sr = synth_audio
    p = GeometryParams(nx=200, n_theta=32, length_mm=200.0,
                       min_r_mm=2.0, max_r_mm=15.0)
    env = extract_envelopes(y, sr, nx=p.nx)
    mesh = build_mesh(env, p)

    # All non-cap vertices' radial distance from the x-axis must lie
    # within [min_r, max_r] (with a tiny epsilon for end-cap centres).
    ring = mesh.vertices[: p.nx * p.n_theta]
    radial = np.sqrt(ring[:, 1] ** 2 + ring[:, 2] ** 2)
    assert radial.min() >= p.min_r_mm - 1e-3
    assert radial.max() <= p.max_r_mm + 1e-3


def test_envelopes_nx_mismatch_errors():
    from src.audio import Envelopes
    env = Envelopes(
        top=np.zeros(100, dtype=np.float32),
        bottom=np.zeros(100, dtype=np.float32),
        rms=np.zeros(100, dtype=np.float32),
        sample_rate=22050, duration_s=1.0, hop_ms=3.0, nx=100,
    )
    p = GeometryParams(nx=200)
    with pytest.raises(ValueError):
        build_mesh(env, p)
