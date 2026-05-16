"""
voice-to-form  —  src/preview.py  v0.4.0

3D viewport for the GUI.  Built on pyqtgraph.opengl (which wraps
PyOpenGL) — gives us interactive rotate/zoom for free and keeps the
dependency surface small.

v0.4.0:
  - Default background is a light studio white (matches the new
    AppearanceParams default).
  - **Shift + trackpad scroll** rotates the sculpture around its long
    (X) axis, so trackpad users can spin the form like a rotisserie
    to inspect top/bottom asymmetry without click-dragging the
    camera orbit.

v0.3.0 — adjustable background colour via config.
v0.2.0 — `set_color()` / `set_background()` update live.
"""
from __future__ import annotations

__version__ = "0.4.0"

import sys
from typing import Optional

import numpy as np

from .geometry import Mesh

print(f"[voice-to-form] preview.py v{__version__}", file=sys.stderr)


# How many degrees of long-axis spin per unit of trackpad/wheel
# angleDelta().y().  120 units = one mouse-wheel "click" on most
# systems; on macOS trackpads each pixel reports ~4 units.  0.15 ° /
# unit means a full mouse-wheel notch is 18° and a normal trackpad
# swipe feels like ~30–60° per gesture.  Tune if needed.
SPIN_DEG_PER_UNIT = 0.15


class PreviewWidget:
    """Thin wrapper around pyqtgraph.opengl.GLViewWidget."""

    # Light studio-white default so the viewport doesn't blink dark at
    # startup before the configured background applies.
    DEFAULT_BG_RGB = (245, 245, 245)

    def __init__(self):
        import pyqtgraph.opengl as gl
        self.gl = gl
        self.view = _SpinningGLView(self)
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
        # in v0.4+.
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
    # Long-axis spin (called from _SpinningGLView's wheelEvent override)
    # ----------------------------------------------------------------------

    def spin_long_axis(self, deg: float) -> None:
        """Rotate the displayed mesh by `deg` degrees around the X axis.

        Called from Shift+wheel events.  Acts on the mesh item, not the
        camera, so the orbit / pan controls keep working independently.
        """
        if self._mesh_item is None or deg == 0.0:
            return
        # GLMeshItem.rotate(angle, x, y, z) rotates around the world axis.
        # Since the mesh is centred at origin by set_mesh(), this rotates
        # around the form's centroid — visually the long-axis spin.
        self._mesh_item.rotate(float(deg), 1.0, 0.0, 0.0)

    # ----------------------------------------------------------------------

    def _add_axis(self) -> None:
        try:
            axis = self.gl.GLAxisItem(size=self.gl.Vector(60, 60, 60))
            axis.translate(-120, 0, 0)
            self.view.addItem(axis)
            self._axis_item = axis
        except Exception:
            pass


# --------------------------------------------------------------------------
# GLViewWidget subclass — intercepts Shift+wheel for long-axis rotation
# --------------------------------------------------------------------------

def _make_spinning_view_class():
    """Return the GLViewWidget subclass.

    Lazy import so this module is importable without a Qt display in
    tests / CLI mode.
    """
    import pyqtgraph.opengl as gl
    from PyQt6.QtCore import Qt

    class _SpinningGLView(gl.GLViewWidget):
        def __init__(self, owner: "PreviewWidget"):
            super().__init__()
            self._owner = owner

        def wheelEvent(self, ev):  # noqa: N802 (Qt camelCase override)
            mods = ev.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                ad = ev.angleDelta()
                # Trackpad scroll on macOS reports y deltas; mouse-wheel
                # also fills y.  We use y so vertical swipe → spin.
                delta = ad.y() or ad.x()
                if delta:
                    self._owner.spin_long_axis(delta * SPIN_DEG_PER_UNIT)
                ev.accept()
                return
            super().wheelEvent(ev)

    return _SpinningGLView


# Placeholder until first PreviewWidget is constructed (real class is
# resolved lazily via _make_spinning_view_class()).
class _SpinningGLView:  # type: ignore[no-redef]
    _real_cls = None

    def __new__(cls, owner):
        if cls._real_cls is None:
            cls._real_cls = _make_spinning_view_class()
        return cls._real_cls(owner)


# --------------------------------------------------------------------------
# Hex helpers
# --------------------------------------------------------------------------

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
