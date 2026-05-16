"""
voice-to-form  —  src/export.py  v0.1.0

Export dispatch — turns a (mesh, profile) into a folder of files:

  <out>/<profile.key>/
    form.stl                  always
    form_top.stl              if profile.split_halves
    form_bottom.stl           if profile.split_halves
    form.step                 if profile.formats contains "step"
                              (best-effort; falls back to a note if no
                              STEP writer is available)
    spec.json                 profile sidecar + applied parameters

The advanced profile flags (add_draft_angle_deg, add_sprue,
invert_to_cavity) are recorded in the sidecar but not yet implemented
as geometry modifications in v0.1 — they're documented stubs with
clear TODOs.  The base STL is still written so the artist isn't
blocked from prototyping.
"""
from __future__ import annotations

__version__ = "0.1.0"

import json
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

from .audio import Envelopes
from .geometry import GeometryParams, Mesh, build_mesh, build_half_mesh
from .profiles import Profile, get as get_profile
from . import decimation

print(f"[voice-to-form] export.py v{__version__}", file=sys.stderr)


def export_profile(
    envelopes: Envelopes,
    params: GeometryParams,
    profile_key: str,
    out_dir: str | Path,
    title: str = "form",
) -> Path:
    """Run the full export pipeline for one profile.  Returns the output dir."""
    profile = get_profile(profile_key)

    # Profile may override geometry's min_r.  Other params unchanged.
    p = GeometryParams(
        length_mm=params.length_mm,
        min_r_mm=profile.min_r_mm,
        max_r_mm=params.max_r_mm,
        n_theta=params.n_theta,
        nx=params.nx,
    )

    mesh = build_mesh(envelopes, p)

    if profile.scale_factor != 1.0:
        mesh = _scaled(mesh, profile.scale_factor)

    if profile.decimate_to is not None:
        mesh = decimation.decimate(mesh, profile.decimate_to)

    out_dir = Path(out_dir) / profile.key
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    written.append(str(_write_stl(mesh, out_dir / "form.stl")))

    if profile.split_halves:
        top_half = build_half_mesh(envelopes, p, "top")
        bot_half = build_half_mesh(envelopes, p, "bottom")
        if profile.scale_factor != 1.0:
            top_half = _scaled(top_half, profile.scale_factor)
            bot_half = _scaled(bot_half, profile.scale_factor)
        written.append(str(_write_stl(top_half, out_dir / "form_top.stl")))
        written.append(str(_write_stl(bot_half, out_dir / "form_bottom.stl")))

    step_status = None
    if "step" in profile.formats:
        step_status = _try_write_step(mesh, out_dir / "form.step")
        if step_status["written"]:
            written.append(step_status["path"])

    sidecar = profile.as_sidecar()
    sidecar.update({
        "title": title,
        "applied_params": {
            "length_mm": p.length_mm,
            "min_r_mm": p.min_r_mm,
            "max_r_mm": p.max_r_mm,
            "n_theta": p.n_theta,
            "nx": p.nx,
        },
        "mesh_stats": {
            "triangles": mesh.triangle_count(),
            "vertices": mesh.vertex_count(),
        },
        "files": written,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "voice_to_form_version": "0.1.0",
        "stubs": _stub_notes(profile),
    })
    if step_status is not None:
        sidecar["step_export"] = step_status

    with open(out_dir / "spec.json", "w") as f:
        json.dump(sidecar, f, indent=2)

    return out_dir


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

def _write_stl(mesh: Mesh, path: Path) -> Path:
    from stl import mesh as numpy_stl_mesh
    data = np.zeros(mesh.faces.shape[0], dtype=numpy_stl_mesh.Mesh.dtype)
    for i, tri in enumerate(mesh.faces):
        for j in range(3):
            data["vectors"][i][j] = mesh.vertices[tri[j]]
    m = numpy_stl_mesh.Mesh(data, remove_empty_areas=False)
    m.save(str(path))
    return path


def _try_write_step(mesh: Mesh, path: Path) -> dict:
    """Best-effort STEP export.

    Neither trimesh nor numpy-stl ship a STEP writer.  v0.1 doesn't
    pretend to convert a tessellated mesh into a true B-rep — that's
    a CAD-grade operation.  Instead we write a sibling .step.NOTE
    explaining the manual route (FreeCAD: Part workbench → 'Convert
    to solid' → export STEP).  This keeps the export pipeline honest:
    the artist knows the STEP wasn't produced and what to do.
    """
    note = (
        "STEP export not produced.\n\n"
        "voice-to-form v0.1 doesn't ship a tessellation→B-rep STEP "
        "converter (that's a CAD-grade operation).  To get a STEP for "
        "this form:\n"
        "  1. Open form.stl in FreeCAD.\n"
        "  2. Switch to the Part workbench.\n"
        "  3. Select the mesh → Part → 'Convert to solid'.\n"
        "  4. Export → STEP (.step).\n\n"
        "Most metal-SLM and CNC services accept STL for organic forms\n"
        "like these and only require STEP when subtractive tolerances\n"
        "matter — ask first before round-tripping through CAD.\n"
    )
    note_path = path.with_suffix(path.suffix + ".NOTE.txt")
    note_path.write_text(note)
    return {"written": False, "path": str(note_path), "backend": "none"}


def _scaled(mesh: Mesh, factor: float) -> Mesh:
    return Mesh(
        vertices=(mesh.vertices * factor).astype(np.float32),
        faces=mesh.faces,
        label=mesh.label + f"_x{factor:.3f}",
        meta={**mesh.meta, "scale_factor": factor},
    )


def _stub_notes(profile: Profile) -> dict:
    """Document profile flags that are recorded but not yet applied as geometry."""
    out: dict[str, str] = {}
    if profile.add_draft_angle_deg is not None:
        out["add_draft_angle_deg"] = (
            f"Recorded ({profile.add_draft_angle_deg}°). Not yet applied to "
            "the exported mesh in v0.1; add draft in your mould-prep CAD step."
        )
    if profile.add_sprue:
        out["add_sprue"] = (
            "Recorded. Sprue/runner attachment not yet generated in v0.1; "
            "the foundry's engineer will normally add these from your STL."
        )
    if profile.add_pour_channels:
        out["add_pour_channels"] = (
            "Recorded. Pour/vent channels not yet generated in v0.1."
        )
    if profile.invert_to_cavity:
        out["invert_to_cavity"] = (
            "Recorded. Negative-cavity-in-block generation deferred to v0.2; "
            "current STL is the positive form. Subtract it from a block in "
            "Fusion/Blender for now."
        )
    return out
