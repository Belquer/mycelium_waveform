"""tests/test_geometry.py  v0.3.0"""
from __future__ import annotations

__version__ = "0.3.0"

import numpy as np
import pytest

from src.audio import extract_envelopes
from src.geometry import (
    GeometryParams, build_mesh, build_half_mesh,
    is_watertight, signed_volume,
)


def _params(nx=200, n_theta=32, aspect=1.0):
    return GeometryParams(nx=nx, n_theta=n_theta, length_mm=200.0,
                          min_r_mm=0.8, max_r_mm=40.0,
                          cross_section_aspect=aspect)


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


def test_cross_section_aspect_compresses_horizontal(synth_audio):
    """aspect < 1 squeezes the cross-section's z-extent; vertical stays put."""
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=200)

    m1 = build_mesh(env, _params(aspect=1.0))
    m07 = build_mesh(env, _params(aspect=0.7))

    p = _params()  # nx=200, n_theta=32
    v1 = m1.vertices[: p.nx * p.n_theta].reshape(p.nx, p.n_theta, 3)
    v07 = m07.vertices[: p.nx * p.n_theta].reshape(p.nx, p.n_theta, 3)

    # Vertical extent (y) is governed by top_r_v / bottom_r_v alone — must
    # be unchanged across aspects.
    np.testing.assert_allclose(v1[:, :, 1], v07[:, :, 1], atol=1e-3)

    # Horizontal extent (z) shrinks roughly proportionally, except where
    # the min_r_mm clamp kicks in for very quiet passages.
    z_max_1 = np.abs(v1[:, :, 2]).max(axis=1)
    z_max_07 = np.abs(v07[:, :, 2]).max(axis=1)
    # On the loudest cross-section the ratio should be very close to 0.7.
    loud_ix = int(np.argmax(z_max_1))
    assert 0.6 < z_max_07[loud_ix] / z_max_1[loud_ix] < 0.8


def test_aspect_preserves_watertightness(synth_audio):
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=200)
    for aspect in (0.3, 0.7, 1.0, 1.4):
        m = build_mesh(env, _params(aspect=aspect))
        assert is_watertight(m), f"aspect={aspect} broke watertightness"
        assert signed_volume(m) > 0


def test_aspect_clamps_to_min_r(synth_audio):
    """Even with a tiny aspect, no feature drops below min_r_mm."""
    y, sr = synth_audio
    env = extract_envelopes(y, sr, nx=200)
    p = _params(aspect=0.2)
    p_with_floor = GeometryParams(
        nx=p.nx, n_theta=p.n_theta, length_mm=p.length_mm,
        min_r_mm=5.0, max_r_mm=40.0, cross_section_aspect=0.2,
    )
    mesh = build_mesh(env, p_with_floor)
    ring = mesh.vertices[: p_with_floor.nx * p_with_floor.n_theta]
    z = np.abs(ring[:, 2])
    # No |z| value should be below the min_r floor on the equator.
    # The equator is theta = 0 and theta = π — pick those columns.
    verts = ring.reshape(p_with_floor.nx, p_with_floor.n_theta, 3)
    equator_z = np.abs(verts[:, [0, p_with_floor.n_theta // 2], 2])
    assert equator_z.min() >= p_with_floor.min_r_mm - 1e-3


def test_invalid_aspect_rejected():
    with pytest.raises(ValueError):
        GeometryParams(cross_section_aspect=0.0)
    with pytest.raises(ValueError):
        GeometryParams(cross_section_aspect=10.0)


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
