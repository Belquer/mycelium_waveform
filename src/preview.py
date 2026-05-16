"""
voice-to-form  —  src/preview.py  v0.2.0

3D viewport for the GUI.  Built on pyqtgraph.opengl (which wraps
PyOpenGL) — gives us interactive rotate/zoom for free and keeps the
dependency surface small.

v0.2.0:
  - `set_color()` and `set_background()` update the displayed mesh
    without rebuilding it — so Appearance-tab changes show live in
    the Geometry-tab viewport.
  - Lighter default background and a brighter default colour so the
    very first preview (matte-black-on-matte-black) is no longer
    invisible.

PBR procedural normal maps for the bump_pattern dropdown are still on
the v0.3 roadmap.  Slider state is persisted in config so artists can
save intent before the rendering catches up.
"""
from __future__ import annotations

__version__ = "0.2.0"

import sys
from typing import Optional

import numpy as np

from .geometry import Mesh

print(f"[voice-to-form] preview.py v{__version__}", file=sys.stderr)


# We import Qt + pyqtgraph lazily inside the class so this module is
# importable headlessly (for tests / CLI) without DISPLAY.

class PreviewWidget:
    """Thin wrapper around pyqtgraph.opengl.GLViewWidget."""

    DEFAULT_BG_RGB = (46, 50, 54)  # mid-dark neutral; flatters most colours

    def __init__(self):
        import pyqtgraph.opengl as gl
        self.gl = gl
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor(self.DEFAULT_BG_RGB)
        self.view.setCameraPosition(distance=380, elevation=12, azimuth=45)

        self._mesh_item = None
        self._axis_item = None
        self._add_axis()

    def widget(self):
        return self.view

    # ----------------------------------------------------------------------

    def set_mesh(self, mesh: Mesh, color_hex: str = "#a8acb1",
                 roughness: float = 0.7, metalness: float = 0.0) -> None:
        """Replace the displayed mesh."""
        verts = mesh.vertices.astype(np.float32)
        faces = mesh.faces.astype(np.int32)

        # Centre the form at the origin so the camera orbit feels right.
        center = verts.mean(axis=0)
        verts = verts - center

        color = _hex_to_rgba(color_hex)

        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None

        mesh_data = self.gl.MeshData(vertexes=verts, faces=faces)
        # shader='shaded' gives diffuse + ambient + specular.  Metalness
        # and roughness map onto specular intensity in v0.2; full PBR
        # in v0.3.
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

    def set_color(self, color_hex: str) -> None:
        """Update the mesh colour live, without rebuilding the geometry."""
        if self._mesh_item is None:
            return
        rgba = _hex_to_rgba(color_hex)
        try:
            self._mesh_item.setColor(rgba)
        except Exception:
            # Older pyqtgraph: poke the option directly and trigger a redraw.
            self._mesh_item.opts["color"] = rgba
            self._mesh_item.update()

    def set_background(self, color_hex: str) -> None:
        r, g, b = _hex_to_rgb_255(color_hex)
        self.view.setBackgroundColor((r, g, b))

    # ----------------------------------------------------------------------

    def _add_axis(self) -> None:
        try:
            axis = self.gl.GLAxisItem(size=self.gl.Vector(60, 60, 60))
            axis.translate(-120, 0, 0)
            self.view.addItem(axis)
            self._axis_item = axis
        except Exception:
            pass


def _hex_to_rgba(h: str) -> tuple[float, float, float, float]:
    r, g, b = _hex_to_rgb(h)
    return (r, g, b, 1.0)


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (0.66, 0.67, 0.69)
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def _hex_to_rgb_255(h: str) -> tuple[int, int, int]:
    r, g, b = _hex_to_rgb(h)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
