"""
voice-to-form  —  src/geometry.py  v0.3.0

Shared-spine elliptical sweep — the load-bearing geometric architecture.

For each x position along the form's length, we build a closed ring
made of two half-ellipses:

  - upper half (theta ∈ [0, π]):     vertical radius = top_r_v[i]
  - lower half (theta ∈ [π, 2π]):    vertical radius = bottom_r_v[i]
  - horizontal radius (z-axis):      shared between both halves
                                     = aspect · (top_r_v[i] + bottom_r_v[i]) / 2

The shared horizontal radius is the architectural commitment that
killed every "looks like two halves stuck together" failure during
development.  Do not "improve" it by giving the top and bottom their
own independent horizontal radii — you will regenerate the seam.

v0.3.0 — `cross_section_aspect` controls how flat the horizontal
radius is relative to the vertical mean.  aspect=1.0 reproduces the
v0.1 behaviour (horizontal ≈ vertical mean → near-circular cross
section when top ≈ bottom).  aspect=0.7 (the new default) compresses
the horizontal so the cross-section is a vertical ellipse —
asymmetric top/bottom is preserved in the silhouette while the front
view shows a taller-than-wide oval.  Clamped to min_r_mm so quiet
passages still meet the per-profile minimum wall thickness.

The ring has continuous theta from 0 to 2π.  The vertex at theta=π
has y = r_v * sin(π) = 0 regardless of which r_v applies, so the
top→bottom switch at theta=π is exact and seamless.  Same for the
theta=0 / theta=2π identification.

We produce a single watertight mesh for preview/full-form export, and
optionally two half-meshes (top, bottom), each with a flat base at
y=0, for printing each half flat-side-down without supports.
"""
from __future__ import annotations

__version__ = "0.3.0"

import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .audio import Envelopes

print(f"[voice-to-form] geometry.py v{__version__}", file=sys.stderr)


# Defaults from the README.  Material-dependent overrides live in profiles.py.
LENGTH_MM_DEFAULT = 240.0
MIN_R_MM_DEFAULT = 0.8
MAX_R_MM_DEFAULT = 40.0
N_THETA_DEFAULT = 96
NX_DEFAULT = 700
# Default horizontal-to-vertical aspect.  0.7 → cross-section ~1.4× taller
# than wide when top ≈ bottom (matches the user's reference sketch).
CROSS_SECTION_ASPECT_DEFAULT = 0.7


@dataclass
class GeometryParams:
    length_mm: float = LENGTH_MM_DEFAULT
    min_r_mm: float = MIN_R_MM_DEFAULT
    max_r_mm: float = MAX_R_MM_DEFAULT
    n_theta: int = N_THETA_DEFAULT
    nx: int = NX_DEFAULT
    # Horizontal radius as a fraction of the per-cross-section mean
    # vertical radius.  See module docstring.  1.0 = v0.1 behaviour.
    cross_section_aspect: float = CROSS_SECTION_ASPECT_DEFAULT

    def __post_init__(self) -> None:
        # N_THETA must be even so theta=π lands exactly on a vertex —
        # otherwise the top/bottom switch happens mid-edge and you can
        # get a tiny ridge along y=0.
        if self.n_theta % 2 != 0:
            raise ValueError(f"n_theta must be even, got {self.n_theta}")
        if self.n_theta < 8:
            raise ValueError(f"n_theta must be >= 8, got {self.n_theta}")
        if self.min_r_mm <= 0:
            raise ValueError("min_r_mm must be > 0")
        if self.max_r_mm <= self.min_r_mm:
            raise ValueError("max_r_mm must be > min_r_mm")
        if not (0.1 <= self.cross_section_aspect <= 2.0):
            raise ValueError(
                f"cross_section_aspect must be in [0.1, 2.0], "
                f"got {self.cross_section_aspect}"
            )


@dataclass
class Mesh:
    """Plain triangle mesh.

    vertices: (V, 3) float32
    faces:    (F, 3) int32, CCW outward
    """
    vertices: np.ndarray
    faces: np.ndarray
    label: str = "form"
    meta: dict = field(default_factory=dict)

    def triangle_count(self) -> int:
        return int(self.faces.shape[0])

    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def build_mesh(envelopes: Envelopes, params: GeometryParams) -> Mesh:
    """Build the full closed dual-half-ellipse sweep.

    Returns a watertight mesh covering theta ∈ [0, 2π], end-capped at
    x=0 and x=LENGTH.
    """
    top_r_v, bottom_r_v, shared_r_h, xs = _radii(envelopes, params)

    n_theta = params.n_theta
    nx = params.nx

    # theta samples — N_THETA evenly spaced around the ring.  Index
    # n_theta/2 lands at theta=π so the top/bottom switch is exact.
    theta = np.linspace(0.0, 2.0 * np.pi, num=n_theta, endpoint=False)
    sin_t = np.sin(theta)
    cos_t = np.cos(theta)

    # Per-vertex r_v: top_r_v for indices [0, n_theta/2),
    # bottom_r_v for indices [n_theta/2, n_theta).
    half = n_theta // 2
    r_v_per_theta = np.zeros((nx, n_theta), dtype=np.float32)
    r_v_per_theta[:, :half] = top_r_v[:, None]
    r_v_per_theta[:, half:] = bottom_r_v[:, None]

    # Vertices
    Xs = np.repeat(xs[:, None], n_theta, axis=1)                      # (nx, n_theta)
    Ys = r_v_per_theta * sin_t[None, :]                               # (nx, n_theta)
    Zs = shared_r_h[:, None] * cos_t[None, :]                         # (nx, n_theta)
    ring_vertices = np.stack([Xs, Ys, Zs], axis=-1).reshape(-1, 3)    # (nx*n_theta, 3)

    # End-cap centres
    cap_start = np.array([xs[0], 0.0, 0.0], dtype=np.float32)
    cap_end = np.array([xs[-1], 0.0, 0.0], dtype=np.float32)
    vertices = np.concatenate(
        [ring_vertices.astype(np.float32),
         cap_start[None, :], cap_end[None, :]],
        axis=0,
    )
    idx_cap_start = nx * n_theta
    idx_cap_end = nx * n_theta + 1

    faces = []

    # Side quads — between adjacent ix and adjacent theta (with wrap).
    # CCW from outside: (ix, it), (ix+1, it), (ix+1, it+1), (ix, it+1).
    for ix in range(nx - 1):
        base = ix * n_theta
        nxt = (ix + 1) * n_theta
        for it in range(n_theta):
            it1 = (it + 1) % n_theta
            a = base + it
            b = nxt + it
            c = nxt + it1
            d = base + it1
            faces.append((a, b, c))
            faces.append((a, c, d))

    # Start cap at ix=0 — outward normal in -x direction.
    # Fan from cap_start, triangles (center, v_a, v_b) with theta_a < theta_b.
    for it in range(n_theta):
        it1 = (it + 1) % n_theta
        a = it
        b = it1
        faces.append((idx_cap_start, a, b))

    # End cap at ix=NX-1 — outward normal in +x direction.
    # Reverse winding.
    last_ring = (nx - 1) * n_theta
    for it in range(n_theta):
        it1 = (it + 1) % n_theta
        a = last_ring + it
        b = last_ring + it1
        faces.append((idx_cap_end, b, a))

    faces_np = np.asarray(faces, dtype=np.int32)
    return Mesh(
        vertices=vertices,
        faces=faces_np,
        label="form_full",
        meta={
            "length_mm": params.length_mm,
            "min_r_mm": params.min_r_mm,
            "max_r_mm": params.max_r_mm,
            "n_theta": params.n_theta,
            "nx": params.nx,
            "cross_section_aspect": params.cross_section_aspect,
        },
    )


def build_half_mesh(
    envelopes: Envelopes,
    params: GeometryParams,
    which: str,
) -> Mesh:
    """Build one half (top or bottom) as a watertight mesh with a flat base.

    For FDM_PLASTIC profile: print each half flat-base-down without supports,
    glue together along the base.
    """
    if which not in ("top", "bottom"):
        raise ValueError("which must be 'top' or 'bottom'")

    top_r_v, bottom_r_v, shared_r_h, xs = _radii(envelopes, params)
    r_v = top_r_v if which == "top" else bottom_r_v
    sign = 1.0 if which == "top" else -1.0

    n_theta = params.n_theta
    nx = params.nx
    half = n_theta // 2 + 1  # inclusive of theta=0 and theta=π

    # theta in [0, π] inclusive for the top; for the bottom we mirror
    # via the sign on y, so theta semantics are the same.
    theta = np.linspace(0.0, np.pi, num=half)
    sin_t = np.sin(theta)
    cos_t = np.cos(theta)

    Xs = np.repeat(xs[:, None], half, axis=1)
    Ys = sign * r_v[:, None] * sin_t[None, :]
    Zs = shared_r_h[:, None] * cos_t[None, :]
    dome_vertices = np.stack([Xs, Ys, Zs], axis=-1).reshape(-1, 3).astype(np.float32)

    # Half-disc end caps don't need a separate centre vertex — fanning
    # from the theta=0 vertex of the boundary ring keeps the diametral
    # chord (theta=0 → theta=π edge) shared with the base strip, which
    # is what makes the half mesh watertight.
    vertices = dome_vertices

    faces: list[tuple[int, int, int]] = []

    # Dome quads
    for ix in range(nx - 1):
        base = ix * half
        nxtb = (ix + 1) * half
        for it in range(half - 1):
            a = base + it
            b = nxtb + it
            c = nxtb + it + 1
            d = base + it + 1
            if which == "top":
                faces.append((a, b, c))
                faces.append((a, c, d))
            else:
                # Mirroring flips outward normal; reverse winding.
                faces.append((a, c, b))
                faces.append((a, d, c))

    # Flat base strip at y=0
    # The base connects, at each ix, the dome's theta=0 vertex (z=+r_h)
    # to its theta=π vertex (z=-r_h).  Outward normal for top is -y;
    # for bottom is +y.
    for ix in range(nx - 1):
        base = ix * half
        nxtb = (ix + 1) * half
        a = base                  # theta=0 at ix
        b = base + (half - 1)     # theta=π at ix
        c = nxtb + (half - 1)     # theta=π at ix+1
        d = nxtb                  # theta=0  at ix+1
        if which == "top":
            faces.append((a, b, c))
            faces.append((a, c, d))
        else:
            faces.append((a, c, b))
            faces.append((a, d, c))

    # End caps — half-discs triangulated as a fan from the theta=0
    # vertex of each end's boundary ring.  That choice keeps the
    # diametral chord (theta=0 ↔ theta=π) shared with the base strip.
    #
    # Start cap at ix=0 — outward -x (top) or +x-flipped via reverse winding (bottom).
    base_left = 0
    apex_left = base_left  # the theta=0 vertex at ix=0
    for it in range(1, half - 1):
        a = apex_left
        b = apex_left + it
        c = apex_left + it + 1
        if which == "top":
            faces.append((a, b, c))
        else:
            faces.append((a, c, b))

    # End cap at ix=NX-1 — outward +x.
    base_right = (nx - 1) * half
    apex_right = base_right
    for it in range(1, half - 1):
        a = apex_right
        b = apex_right + it
        c = apex_right + it + 1
        if which == "top":
            faces.append((a, c, b))
        else:
            faces.append((a, b, c))

    faces_np = np.asarray(faces, dtype=np.int32)
    return Mesh(
        vertices=vertices,
        faces=faces_np,
        label=f"form_{which}",
        meta={
            "length_mm": params.length_mm,
            "min_r_mm": params.min_r_mm,
            "max_r_mm": params.max_r_mm,
            "n_theta": params.n_theta,
            "nx": params.nx,
            "cross_section_aspect": params.cross_section_aspect,
            "half": which,
        },
    )


def silhouette(envelopes: Envelopes, params: GeometryParams):
    """Return (xs, top_r_v_mm, bottom_r_v_mm) for the diagnostic overlay.

    These are the actual radii the mesh uses, expressed in mm — so the
    overlay's middle plot is literally the form's side profile.
    """
    top_r_v, bottom_r_v, _shared_r_h, xs = _radii(envelopes, params)
    return xs, top_r_v, bottom_r_v


# --------------------------------------------------------------------------
# Internal
# --------------------------------------------------------------------------

def _radii(envelopes: Envelopes, params: GeometryParams):
    """Compute the three radius arrays used by every builder."""
    if envelopes.nx != params.nx:
        raise ValueError(
            f"envelopes.nx={envelopes.nx} but params.nx={params.nx}; "
            "re-extract envelopes at the requested resolution."
        )
    top_r_v = (params.min_r_mm + envelopes.top * (params.max_r_mm - params.min_r_mm)).astype(np.float32)
    bottom_r_v = (params.min_r_mm + envelopes.bottom * (params.max_r_mm - params.min_r_mm)).astype(np.float32)
    mean_r = (top_r_v + bottom_r_v) * 0.5
    # Compress (or stretch) horizontal radius by aspect.  Clamp to
    # min_r_mm so a slim aspect doesn't drive quiet passages below the
    # manufacturable wall thickness.
    shared_r_h = np.maximum(
        params.cross_section_aspect * mean_r,
        params.min_r_mm,
    ).astype(np.float32)
    xs = np.linspace(0.0, params.length_mm, num=params.nx, dtype=np.float32)
    return top_r_v, bottom_r_v, shared_r_h, xs


# --------------------------------------------------------------------------
# Trimesh interop
# --------------------------------------------------------------------------

def to_trimesh(mesh: Mesh):
    """Wrap our Mesh in a trimesh.Trimesh (lazy import)."""
    import trimesh
    return trimesh.Trimesh(
        vertices=mesh.vertices.astype(np.float64, copy=False),
        faces=mesh.faces.astype(np.int64, copy=False),
        process=False,
    )


def is_watertight(mesh: Mesh) -> bool:
    """True iff every edge is shared by exactly two triangles.

    Pure-python check so tests don't need trimesh installed.  We
    sort each triangle's three edges and count multiplicities — a
    watertight closed surface has every edge exactly twice.
    """
    edge_count: dict[tuple[int, int], int] = {}
    for tri in mesh.faces:
        for i in range(3):
            a = int(tri[i])
            b = int(tri[(i + 1) % 3])
            key = (a, b) if a < b else (b, a)
            edge_count[key] = edge_count.get(key, 0) + 1
    return all(c == 2 for c in edge_count.values())


def signed_volume(mesh: Mesh) -> float:
    """Signed volume (positive iff outward winding).  Used in tests."""
    V = mesh.vertices.astype(np.float64, copy=False)
    F = mesh.faces
    vol = 0.0
    for tri in F:
        a, b, c = V[tri[0]], V[tri[1]], V[tri[2]]
        vol += float(np.dot(a, np.cross(b, c))) / 6.0
    return vol
