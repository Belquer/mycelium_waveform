"""
voice-to-form  —  src/preview.py  v0.6.2

3D viewport for the GUI.

v0.6.2 — robust shader fallback.  If the custom GLSL fails to compile
on the user's driver (Apple Silicon + Core profile can be picky about
compat-profile constructs), GLMeshItem creation falls back to
pyqtgraph's built-in `shaded` shader so the mesh still renders.
Set `VOICE_TO_FORM_DISABLE_PBR=1` in the environment to force the
fallback unconditionally.

v0.6.0 — registers a custom GLSL shader (`voice_to_form_pbr`) so the
Surface sliders on the Design tab actually affect the render:

  * Ambient + wrap diffuse make the base colour visible across the
    whole form — no more black-on-black for dark mesh colours.
  * Roughness controls specular tightness (low = sharp glossy hot-
    spot, high = broad matte).
  * Metalness tints the specular by the base colour and damps the
    diffuse contribution (rough approximation, not full Cook-Torrance).
  * Bump intensity perturbs the surface normal in the fragment
    shader.
  * Bump pattern picks the noise function (smooth / sandblasted /
    beadblasted / brushed / layered-FDM / porous / woven /
    mycelium-colonized).

`set_pbr()` writes the uniforms directly on the registered
ShaderProgram and requests a redraw — uniforms re-bind on the next
paint.

v0.4.0:
  - Shift + trackpad scroll spins the displayed mesh around its X
    axis (long-axis "rotisserie" view).
  - Light-coloured DEFAULT_BG so the viewport doesn't blink dark at
    startup.
"""
from __future__ import annotations

__version__ = "0.6.2"

import os
import sys
from typing import Optional

import numpy as np

from .geometry import Mesh

print(f"[voice-to-form] preview.py v{__version__}", file=sys.stderr)


# How many degrees of long-axis spin per unit of trackpad/wheel
# angleDelta().y().
SPIN_DEG_PER_UNIT = 0.15


# Bump-pattern → integer the fragment shader switches on.  Kept here so
# the GUI and the shader stay in lock-step.
BUMP_PATTERN_INDEX: dict[str, int] = {
    "smooth": 0,
    "sandblasted": 1,
    "beadblasted": 2,
    "brushed": 3,
    "layered (FDM)": 4,
    "porous (SLS)": 5,
    "woven (carbon)": 6,
    "mycelium-colonized": 7,
}


# --------------------------------------------------------------------------
# Custom GLSL — phong-ish with bump perturbation
# --------------------------------------------------------------------------
# Kept to GLSL 1.20 / compatibility profile because that's what pyqtgraph's
# fixed-pipeline pipeline expects (gl_NormalMatrix, gl_Color, ftransform).

_VERTEX_SRC = """
varying vec3 v_normal;
varying vec3 v_view_pos;
varying vec3 v_obj_pos;

void main() {
    v_normal = normalize(gl_NormalMatrix * gl_Normal);
    vec4 mv = gl_ModelViewMatrix * gl_Vertex;
    v_view_pos = mv.xyz;
    v_obj_pos = gl_Vertex.xyz;
    gl_FrontColor = gl_Color;
    gl_BackColor = gl_Color;
    gl_Position = ftransform();
}
"""

_FRAGMENT_SRC = """
uniform float u_roughness;
uniform float u_metalness;
uniform float u_bump_intensity;
uniform int   u_bump_pattern;
uniform float u_ambient;

varying vec3 v_normal;
varying vec3 v_view_pos;
varying vec3 v_obj_pos;

float hash11(float n) {
    return fract(sin(n) * 43758.5453);
}
float hash13(vec3 p) {
    return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453);
}

float value_noise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash13(i + vec3(0.0, 0.0, 0.0));
    float n100 = hash13(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash13(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash13(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash13(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash13(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash13(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash13(i + vec3(1.0, 1.0, 1.0));
    float nx00 = mix(n000, n100, f.x);
    float nx10 = mix(n010, n110, f.x);
    float nx01 = mix(n001, n101, f.x);
    float nx11 = mix(n011, n111, f.x);
    float nxy0 = mix(nx00, nx10, f.y);
    float nxy1 = mix(nx01, nx11, f.y);
    return mix(nxy0, nxy1, f.z);
}

vec3 perturb_normal(vec3 N, vec3 P, int pattern, float intensity) {
    if (pattern == 0 || intensity <= 0.0001) return N;
    vec3 dN = vec3(0.0);

    if (pattern == 1) {
        // sandblasted — high-freq random
        dN = vec3(
            value_noise(P * 8.0) - 0.5,
            value_noise(P * 8.0 + vec3(17.0)) - 0.5,
            value_noise(P * 8.0 + vec3(31.0)) - 0.5
        );
    } else if (pattern == 2) {
        // beadblasted — finer & rounder
        dN = vec3(
            value_noise(P * 18.0) - 0.5,
            value_noise(P * 18.0 + vec3(11.0)) - 0.5,
            value_noise(P * 18.0 + vec3(23.0)) - 0.5
        ) * 0.7;
    } else if (pattern == 3) {
        // brushed — directional (along the form's X)
        float s = sin(P.y * 70.0 + value_noise(P * 0.5) * 6.0) * 0.5;
        dN = vec3(0.0, s, 0.0);
    } else if (pattern == 4) {
        // layered FDM — horizontal print lines along Y
        float layer = sin(P.y * 12.0) * 0.5;
        dN = vec3(0.0, layer, 0.0);
    } else if (pattern == 5) {
        // porous — large lo-freq pits
        dN = vec3(
            value_noise(P * 3.0) - 0.5,
            value_noise(P * 3.0 + vec3(7.0)) - 0.5,
            value_noise(P * 3.0 + vec3(13.0)) - 0.5
        );
    } else if (pattern == 6) {
        // woven — crossing sine grid
        dN = vec3(
            sin(P.x * 14.0) * 0.4,
            sin(P.z * 14.0) * 0.4,
            0.0
        );
    } else if (pattern == 7) {
        // mycelium-colonized — fractal noise
        float n = value_noise(P * 2.0)
                + 0.5 * value_noise(P * 4.0)
                + 0.25 * value_noise(P * 8.0);
        dN = vec3(
            value_noise(P * 2.0 + vec3(0.0, 0.0, n)) - 0.5,
            value_noise(P * 2.0 + vec3(0.0, n, 0.0)) - 0.5,
            value_noise(P * 2.0 + vec3(n, 0.0, 0.0)) - 0.5
        );
    }
    return normalize(N + dN * intensity * 0.6);
}

void main() {
    vec3 N = normalize(v_normal);
    N = perturb_normal(N, v_obj_pos * 0.025, u_bump_pattern, u_bump_intensity);

    // Fixed key light in view space — feels stable as the user orbits.
    vec3 L = normalize(vec3(0.35, 0.55, 0.75));
    vec3 V = normalize(-v_view_pos);
    vec3 H = normalize(L + V);

    float NdotL = max(dot(N, L), 0.0);
    // Wrap diffuse: shadowed side keeps some colour, never pitch black.
    float wrap = (NdotL + 0.35) / 1.35;

    float NdotH = max(dot(N, H), 0.0);
    // Roughness → specular exponent (sharp ↔ broad).
    float shininess = mix(4.0, 256.0, 1.0 - clamp(u_roughness, 0.0, 1.0));
    float spec = pow(NdotH, shininess);
    // High roughness damps the highlight; low roughness keeps it punchy.
    spec *= mix(1.0, 0.05, clamp(u_roughness, 0.0, 1.0));

    vec3 base = gl_Color.rgb;
    // Metals tint the specular with the base colour; dielectrics get white spec.
    vec3 spec_tint = mix(vec3(1.0), base, clamp(u_metalness, 0.0, 1.0));
    // Metals shed diffuse — most of their reflection is specular.
    vec3 diffuse_color = mix(base, base * 0.15, clamp(u_metalness, 0.0, 1.0));

    vec3 color = u_ambient * base
               + wrap * diffuse_color
               + spec * spec_tint;
    gl_FragColor = vec4(color, gl_Color.a);
}
"""


_PBR_SHADER_NAME = "voice_to_form_pbr"


def _register_pbr_shader():
    """Register the custom shader on pyqtgraph's global Shaders list (idempotent)."""
    import pyqtgraph.opengl.shaders as shaders
    for sp in shaders.Shaders:
        if getattr(sp, "name", None) == _PBR_SHADER_NAME:
            return sp
    sp = shaders.ShaderProgram(
        _PBR_SHADER_NAME,
        [
            shaders.VertexShader(_VERTEX_SRC),
            shaders.FragmentShader(_FRAGMENT_SRC),
        ],
        uniforms={
            "u_roughness": 0.5,
            "u_metalness": 0.0,
            "u_bump_intensity": 0.0,
            "u_bump_pattern": 0,
            "u_ambient": 0.25,
        },
    )
    shaders.Shaders.append(sp)
    return sp


# --------------------------------------------------------------------------
# PreviewWidget
# --------------------------------------------------------------------------

class PreviewWidget:
    """Thin wrapper around pyqtgraph.opengl.GLViewWidget."""

    DEFAULT_BG_RGB = (245, 245, 245)

    def __init__(self):
        import pyqtgraph.opengl as gl
        self.gl = gl

        # Custom shader is optional — if registration throws (no GL
        # context yet on some platforms) or VOICE_TO_FORM_DISABLE_PBR
        # is set, fall back to pyqtgraph's built-in 'shaded'.  We
        # don't know if the shader actually *compiles* until first
        # paint, so set_mesh also has a try/except below.
        self._pbr_shader = None
        self._use_pbr = not os.environ.get("VOICE_TO_FORM_DISABLE_PBR")
        if self._use_pbr:
            try:
                self._pbr_shader = _register_pbr_shader()
            except Exception as e:
                print(f"[voice-to-form] PBR shader registration failed: "
                      f"{e!r}; falling back to 'shaded'", file=sys.stderr)
                self._use_pbr = False

        self.view = _SpinningGLView(self)
        self.view.setBackgroundColor(self.DEFAULT_BG_RGB)
        self.view.setCameraPosition(distance=380, elevation=12, azimuth=45)

        self._mesh_item = None
        self._axis_item = None
        self._add_axis()

    @property
    def shader_name(self) -> str:
        return _PBR_SHADER_NAME if self._use_pbr else "shaded"

    def widget(self):
        return self.view

    # ----------------------------------------------------------------------

    def set_mesh(
        self,
        mesh: Mesh,
        color_hex: str = "#a8acb1",
        roughness: float = 0.5,
        metalness: float = 0.0,
        bump_intensity: float = 0.0,
        bump_pattern: int | str = 0,
    ) -> None:
        verts = mesh.vertices.astype(np.float32)
        faces = mesh.faces.astype(np.int32)
        center = verts.mean(axis=0)
        verts = verts - center

        color = _hex_to_rgba(color_hex)

        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None

        mesh_data = self.gl.MeshData(vertexes=verts, faces=faces)
        try:
            self._mesh_item = self.gl.GLMeshItem(
                meshdata=mesh_data,
                smooth=True,
                color=color,
                shader=self.shader_name,
                glOptions="opaque",
            )
            self.view.addItem(self._mesh_item)
        except Exception as e:
            # Custom shader didn't take.  Retry with the built-in
            # 'shaded' so the mesh actually renders.
            print(
                f"[voice-to-form] shader '{self.shader_name}' failed "
                f"({e!r}); retrying with 'shaded'", file=sys.stderr,
            )
            self._use_pbr = False
            self._mesh_item = self.gl.GLMeshItem(
                meshdata=mesh_data,
                smooth=True,
                color=color,
                shader="shaded",
                glOptions="opaque",
            )
            self.view.addItem(self._mesh_item)

        # Apply the appearance state to the freshly-registered mesh.
        # Safe even when we fell back to 'shaded' — set_pbr just
        # updates the PBR uniforms in case the custom shader is in
        # play; 'shaded' ignores them.
        self.set_pbr(
            roughness=roughness,
            metalness=metalness,
            bump_intensity=bump_intensity,
            bump_pattern=bump_pattern,
        )

        extents = verts.max(axis=0) - verts.min(axis=0)
        diag = float(np.linalg.norm(extents))
        self.view.setCameraPosition(distance=max(300.0, diag * 1.4))

    def clear(self) -> None:
        if self._mesh_item is not None:
            self.view.removeItem(self._mesh_item)
            self._mesh_item = None

    # ----------------------------------------------------------------------

    def set_color(self, color_hex: str) -> None:
        if self._mesh_item is None:
            return
        rgba = _hex_to_rgba(color_hex)
        try:
            self._mesh_item.setColor(rgba)
        except Exception:
            self._mesh_item.opts["color"] = rgba
            self._mesh_item.update()

    def set_background(self, color_hex: str) -> None:
        r, g, b = _hex_to_rgb_255(color_hex)
        self.view.setBackgroundColor((r, g, b))

    def set_pbr(
        self,
        roughness: float | None = None,
        metalness: float | None = None,
        bump_intensity: float | None = None,
        bump_pattern: int | str | None = None,
    ) -> None:
        """Update PBR uniforms on the shared shader.

        No-op when the fallback 'shaded' shader is in play — those
        uniforms don't exist there.  The uniforms re-bind on the next
        paint; we also poke an update() so the redraw happens promptly.
        """
        if self._pbr_shader is not None:
            u = self._pbr_shader.uniforms
            if roughness is not None:
                u["u_roughness"] = float(roughness)
            if metalness is not None:
                u["u_metalness"] = float(metalness)
            if bump_intensity is not None:
                u["u_bump_intensity"] = float(bump_intensity)
            if bump_pattern is not None:
                if isinstance(bump_pattern, str):
                    bump_pattern = BUMP_PATTERN_INDEX.get(bump_pattern, 0)
                u["u_bump_pattern"] = int(bump_pattern)
        if self._mesh_item is not None:
            try:
                self._mesh_item.update()
            except Exception:
                pass
        try:
            self.view.update()
        except Exception:
            pass

    # ----------------------------------------------------------------------

    def spin_long_axis(self, deg: float) -> None:
        if self._mesh_item is None or deg == 0.0:
            return
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
    import pyqtgraph.opengl as gl
    from PyQt6.QtCore import Qt

    class _SpinningGLView(gl.GLViewWidget):
        def __init__(self, owner: "PreviewWidget"):
            super().__init__()
            self._owner = owner

        def wheelEvent(self, ev):  # noqa: N802
            mods = ev.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                ad = ev.angleDelta()
                delta = ad.y() or ad.x()
                if delta:
                    self._owner.spin_long_axis(delta * SPIN_DEG_PER_UNIT)
                ev.accept()
                return
            super().wheelEvent(ev)

    return _SpinningGLView


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
