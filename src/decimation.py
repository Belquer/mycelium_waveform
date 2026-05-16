"""
voice-to-form  —  src/decimation.py  v0.1.0

Quadric-decimation wrappers.  Tries open3d first (fast and good
quality), falls back to trimesh if open3d isn't installed.

Used by the SLM/CNC/INJECTION profiles to bring upload-blob size down
into the few-MB range for online service portals.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys

import numpy as np

from .geometry import Mesh

print(f"[voice-to-form] decimation.py v{__version__}", file=sys.stderr)


def decimate(mesh: Mesh, target_fraction: float) -> Mesh:
    """Return a Mesh with roughly target_fraction of the input triangles.

    target_fraction in (0, 1].  0.55 means "keep 55%".
    """
    if not (0.0 < target_fraction <= 1.0):
        raise ValueError(f"target_fraction must be in (0,1], got {target_fraction}")
    if target_fraction >= 0.999:
        return mesh

    target_triangles = max(64, int(mesh.triangle_count() * target_fraction))

    # Prefer open3d — quadric decimation is well-tuned there.
    try:
        return _decimate_open3d(mesh, target_triangles)
    except Exception as e:
        print(f"[voice-to-form] decimation: open3d unavailable ({e!r}); falling back to trimesh", file=sys.stderr)
        return _decimate_trimesh(mesh, target_triangles)


def _decimate_open3d(mesh: Mesh, target_triangles: int) -> Mesh:
    import open3d as o3d
    o3 = o3d.geometry.TriangleMesh(
        vertices=o3d.utility.Vector3dVector(mesh.vertices.astype(np.float64)),
        triangles=o3d.utility.Vector3iVector(mesh.faces.astype(np.int32)),
    )
    out = o3.simplify_quadric_decimation(target_number_of_triangles=target_triangles)
    out.remove_unreferenced_vertices()
    verts = np.asarray(out.vertices, dtype=np.float32)
    faces = np.asarray(out.triangles, dtype=np.int32)
    return Mesh(vertices=verts, faces=faces, label=mesh.label + "_decimated",
                meta={**mesh.meta, "decimated_to": target_triangles})


def _decimate_trimesh(mesh: Mesh, target_triangles: int) -> Mesh:
    import trimesh
    tm = trimesh.Trimesh(
        vertices=mesh.vertices.astype(np.float64),
        faces=mesh.faces.astype(np.int64),
        process=False,
    )
    try:
        simp = tm.simplify_quadric_decimation(target_triangles)
    except Exception as e:
        # Some trimesh installs need a fast-simplification backend.
        # If it really can't run, return the input unchanged with a warning.
        print(f"[voice-to-form] decimation: trimesh fallback failed ({e!r}); returning input mesh", file=sys.stderr)
        return mesh
    return Mesh(
        vertices=np.asarray(simp.vertices, dtype=np.float32),
        faces=np.asarray(simp.faces, dtype=np.int32),
        label=mesh.label + "_decimated",
        meta={**mesh.meta, "decimated_to": target_triangles},
    )
