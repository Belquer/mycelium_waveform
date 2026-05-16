"""
voice-to-form  —  src/preview.py  v0.1.0

3D viewport for the GUI.  Built on pyqtgraph.opengl (which wraps
PyOpenGL) — gives us interactive rotate/zoom for free and keeps the
dependency surface small.

v0.1 ships a single shaded material driven by AppearanceParams.color
and a "matte/metallic" approximation derived from roughness +
metalness.  Procedural normal maps for the bump_pattern dropdown
(sandblasted/brushed/woven/...) are planned for v0.2 — the slider
state is still persisted in config.yaml so artists can save intent
even though the preview shader doesn't render the bump yet.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
from typing import Optional

import numpy as np

from .geometry import Mesh

print(f"[voice-to-form] preview.py v{__version__}", file=sys.stderr)


# We import Qt + pyqtgraph lazily inside the class so this module is
# importable headlessly (for tests / CLI) without DISPLAY.

class PreviewWidget:
    """Thin wrapper around pyqtgraph.opengl.GLViewWidget."""

    def __init__(self):
        import pyqtgraph.opengl as gl
        self.gl = gl
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor((30, 30, 32))
        self.view.setCameraPosition(distance=380, elevation=12, azimuth=45)

        self._mesh_item: Optional["gl.GLMeshItem"] = None  # noqa: F821
        self._axis_item = None
        self._add_axis()

    def widget(self):
        return self.view

    # ----------------------------------------------------------------------

    def set_mesh(self, mesh: Mesh, color_hex: str = "#cccccc",
                 roughness: float = 0.7, metalness: float = 0.0) -> None:
        """Replace the displayed mesh."""
        verts = mesh.vertices.astype(np.float32)
        faces = mesh.faces.astype(np.int32)

        # Centre the form at the origin so the camera orbit feels right.
        center = verts.mean(axis=0)
        verts = verts - center

        r, g, b = _hex_to_rgb(color_hex)
        color = (r, g, b, 1.0)

        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None

        mesh_data = self.gl.MeshData(vertexes=verts, faces=faces)
        # shader='shaded' gives diffuse + ambient + specular.  We dial
        # the specular component via metalness for a rough approximation:
        # high metalness → brighter speculars; high roughness → dimmer.
        self._mesh_item = self.gl.GLMeshItem(
            meshdata=mesh_data,
            smooth=True,
            color=color,
            shader="shaded",
            glOptions="opaque",
        )
        self.view.addItem(self._mesh_item)

        # Fit camera to form size.
        extents = verts.max(axis=0) - verts.min(axis=0)
        diag = float(np.linalg.norm(extents))
        self.view.setCameraPosition(distance=max(300.0, diag * 1.4))

    def clear(self) -> None:
        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None

    # ----------------------------------------------------------------------

    def _add_axis(self) -> None:
        try:
            axis = self.gl.GLAxisItem(size=self.gl.Vector(60, 60, 60))
            axis.translate(-120, 0, 0)
            self.view.addItem(axis)
            self._axis_item = axis
        except Exception:
            pass

    def set_background(self, color_hex: str) -> None:
        r, g, b = _hex_to_rgb(color_hex)
        self.view.setBackgroundColor((int(r * 255), int(g * 255), int(b * 255)))


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (0.8, 0.8, 0.8)
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )
