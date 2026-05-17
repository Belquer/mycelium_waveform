"""
voice-to-form  —  src/preview.py  v0.7.7

3D viewport for the GUI.

v0.7.7 — fix "Metal makes it black".  v0.7.5 used Fresnel to damp
diffuse for energy conservation, but without an environment map
(no IBL) metals went nearly pitch-black: there was nothing to
fill the diffuse void.  Now metals get:
  - a 2.5× ambient boost so the base colour stays visible,
  - a cheap hemisphere-gradient "fake env reflection" tinted by
    the base — sky above, ground below,
  - no Fresnel damping on diffuse (drop the
    (1 - fresnel) factor that was the main culprit).
Dielectrics are unchanged.

v0.7.5 — Fresnel-Schlick edge term.

v0.7.3 — set_mesh no longer auto-fits the camera every call.
Previous behaviour: every parameter tweak rebuilt the mesh and
reset the camera distance, which made Length (and audio
smoothing) appear to do nothing — the form just grew/shrank and
the camera scaled to keep visible size constant.  Now set_mesh
preserves the camera state; the caller decides when to refit
via the new `fit_view()` method.

v0.7.1 — fixes the silent "no mesh rendered" failure on macOS.
The custom shader was using legacy GLSL builtins (gl_Vertex,
gl_NormalMatrix, ftransform, gl_Color, gl_FrontColor) which
don't exist in a Core OpenGL profile.  pyqtgraph's GLMeshItem
binds vertex data via the modern `a_position` / `a_normal` /
`a_color` attributes and `u_mvp` / `u_normal` uniforms, and that's
what the actual built-in 'shaded' shader uses.  Rewriting to the
same pattern fixes rendering across macOS / Apple Silicon's
default profile.

v0.6.3 — fixed the ShaderProgram API misuse.  pyqtgraph stores
uniforms in `uniformData` and only supports glUniform1fv at bind
time, so:
  - Uniform values must be passed as 1-element lists (or any
    iterable with `len`), not bare scalars.
  - All uniforms must be floats — `int` uniforms can't be set.
    u_bump_pattern is a float and cast inside the shader.
  - We use `shader[name] = [value]` (which calls setUniformData)
    instead of writing to a `.uniforms` dict.

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

__version__ = "0.7.7"

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
# Custom GLSL — modern-attribute Phong-ish with bump perturbation
# --------------------------------------------------------------------------
# pyqtgraph 0.13's GLMeshItem feeds vertex data via the attributes
# `a_position` / `a_normal` / `a_color` and the uniforms `u_mvp` /
# `u_normal`.  Using `gl_Vertex` / `gl_NormalMatrix` / `gl_Color`
# (legacy / compat-profile builtins) renders blank on macOS's default
# Core profile.  Stick to the modern names.

_VERTEX_SRC = """
uniform mat4 u_mvp;
uniform mat3 u_normal;

attribute vec4 a_position;
attribute vec3 a_normal;
attribute vec4 a_color;

varying vec4 v_color;
varying vec3 v_normal_view;
varying vec3 v_obj_pos;

void main() {
    v_normal_view = normalize(u_normal * a_normal);
    v_color = a_color;
    v_obj_pos = a_position.xyz;
    gl_Position = u_mvp * a_position;
}
"""

_FRAGMENT_SRC = """
#ifdef GL_ES
precision mediump float;
#endif

uniform float u_roughness;
uniform float u_metalness;
uniform float u_bump_intensity;
uniform float u_bump_pattern;
uniform float u_ambient;

varying vec4 v_color;
varying vec3 v_normal_view;
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
    vec3 N = normalize(v_normal_view);
    // u_bump_pattern is float (pyqtgraph only sets uniforms via
    // glUniform1fv); cast to int locally for the switch.
    N = perturb_normal(N, v_obj_pos * 0.025,
                       int(u_bump_pattern + 0.5),
                       u_bump_intensity);

    // Both N and L are in view space (u_normal transforms a_normal
    // into view).  In view space the viewer looks down -Z and the
    // forward direction toward the camera is +Z.
    vec3 L = normalize(vec3(0.35, 0.55, 0.75));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(L + V);

    float NdotL = max(dot(N, L), 0.0);
    float NdotV = max(dot(N, V), 0.0);
    float NdotH = max(dot(N, H), 0.0);

    float r = clamp(u_roughness, 0.0, 1.0);
    float m = clamp(u_metalness, 0.0, 1.0);

    // Wrap diffuse: shadowed side keeps some colour, never pitch black.
    float wrap = (NdotL + 0.35) / 1.35;

    // Roughness → specular exponent (sharp ↔ broad).  Wider range +
    // bigger gain at low roughness so the "mirror" toggle reads as
    // a real mirror, not a polite gloss.
    float shininess = mix(8.0, 512.0, 1.0 - r);
    float spec_pow = pow(NdotH, shininess);
    float spec_gain = mix(4.0, 0.05, r);
    float spec = spec_pow * spec_gain;

    vec3 base = v_color.rgb;

    // Fresnel-Schlick: dielectrics reflect ~4% at normal incidence,
    // metals reflect their base colour.  At glancing angles both
    // reflect ~100% — that's the "edge glow" you see on chrome.
    vec3 F0 = mix(vec3(0.04), base, m);
    vec3 fresnel = F0 + (vec3(1.0) - F0) * pow(1.0 - NdotV, 5.0);

    // Specular colour = Fresnel response × highlight intensity.
    vec3 spec_color = fresnel * spec;

    // Diffuse: metals shed most diffuse but not all (no IBL means
    // we have nothing to fill the void if we kill it completely).
    vec3 diffuse_color = mix(base, base * 0.20, m);

    // Ambient + hemisphere fake-environment for metals.  Without an
    // environment map a metal would render almost pitch-black under
    // our single key light — there's nothing for it to reflect.
    // Cheap fix: boost ambient and add a sky/ground gradient tinted
    // by the base colour, both scaled by metalness.  Dielectrics
    // get neither (their look is unchanged from v0.7.5).
    vec3 sky    = vec3(0.85, 0.90, 1.00);
    vec3 ground = vec3(0.25, 0.22, 0.18);
    float hemi  = N.y * 0.5 + 0.5;
    vec3 hemi_color = mix(ground, sky, hemi);
    vec3 ambient_term = u_ambient * base * mix(1.0, 2.5, m);
    vec3 env_term     = hemi_color * base * mix(0.0, 0.5, m);

    vec3 color = ambient_term
               + wrap * diffuse_color
               + spec_color
               + env_term;
    gl_FragColor = vec4(color, v_color.a);
}
"""


_PBR_SHADER_NAME = "voice_to_form_pbr"


def _register_pbr_shader():
    """Register the custom shader on pyqtgraph's global Shaders list (idempotent).

    pyqtgraph 0.13 stores uniforms in `uniformData` and only ever
    sets them with glUniform1fv at bind time — so every value must
    be an iterable of floats (1-element list is fine for scalars).
    """
    import pyqtgraph.opengl.shaders as shaders
    # pyqtgraph keeps a name registry in ShaderProgram.names — check
    # there before scanning the active Shaders list.
    existing = getattr(shaders.ShaderProgram, "names", {}).get(_PBR_SHADER_NAME)
    if existing is not None:
        return existing
    sp = shaders.ShaderProgram(
        _PBR_SHADER_NAME,
        [
            shaders.VertexShader(_VERTEX_SRC),
            shaders.FragmentShader(_FRAGMENT_SRC),
        ],
        uniforms={
            "u_roughness": [0.5],
            "u_metalness": [0.0],
            "u_bump_intensity": [0.0],
            "u_bump_pattern": [0.0],
            "u_ambient": [0.25],
        },
    )
    # Append to the active list too — GLMeshItem looks shaders up by
    # name from there.
    if hasattr(shaders, "Shaders") and sp not in shaders.Shaders:
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
        # Cached recentred vertices so `fit_view()` can refit without
        # the caller having to hand us the mesh again.
        self._last_verts: Optional[np.ndarray] = None
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

        # Cache verts so `fit_view()` can refit without rebuilding the
        # mesh.  We intentionally do NOT touch the camera here —
        # parameter sliders should change the *form* on screen, not
        # cancel the user's zoom.  Caller (DesignTab) calls fit_view()
        # at the moments where refit is wanted (first show, fresh
        # audio load, explicit user request).
        self._last_verts = verts

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
        uniforms don't exist there.  Values are wrapped in 1-element
        lists because pyqtgraph's only uniform setter is glUniform1fv.
        """
        sp = self._pbr_shader
        if sp is not None:
            if roughness is not None:
                sp["u_roughness"] = [float(roughness)]
            if metalness is not None:
                sp["u_metalness"] = [float(metalness)]
            if bump_intensity is not None:
                sp["u_bump_intensity"] = [float(bump_intensity)]
            if bump_pattern is not None:
                if isinstance(bump_pattern, str):
                    bump_pattern = BUMP_PATTERN_INDEX.get(bump_pattern, 0)
                sp["u_bump_pattern"] = [float(bump_pattern)]
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

    def fit_view(self) -> None:
        """Reframe the camera to fit the current mesh's extents."""
        verts = self._last_verts
        if verts is None or verts.size == 0:
            return
        extents = verts.max(axis=0) - verts.min(axis=0)
        diag = float(np.linalg.norm(extents))
        self.view.setCameraPosition(distance=max(300.0, diag * 1.4))

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
