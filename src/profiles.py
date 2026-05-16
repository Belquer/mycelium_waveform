"""
voice-to-form  —  src/profiles.py  v0.1.0

Manufacturing output profiles.  Each profile applies parameter
overrides on top of the default geometry, picks export format(s),
optional decimation target, and produces a JSON sidecar spec sheet.

Adding a new profile: append a Profile entry to PROFILES.  The GUI
dropdown is generated from this dict.
"""
from __future__ import annotations

__version__ = "0.1.0"

import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

print(f"[voice-to-form] profiles.py v{__version__}", file=sys.stderr)


@dataclass
class Profile:
    key: str                                 # internal id, matches dict key
    label: str                               # GUI dropdown text
    family: str                              # FDM / SLA / SLS / SLM / CNC / MOLD / SPECIAL
    min_r_mm: float                          # overrides the geometry MIN_R
    decimate_to: Optional[float] = None      # fraction of triangles to keep (None = no decimation)
    formats: tuple[str, ...] = ("stl",)      # export formats, in priority order
    split_halves: bool = False               # also export top/bottom halves
    add_draft_angle_deg: Optional[float] = None
    add_sprue: bool = False
    add_pour_channels: bool = False
    invert_to_cavity: bool = False
    scale_factor: float = 1.0
    services: tuple[str, ...] = ()
    notes: str = ""
    suggested_finish: str = ""
    est_cost_usd: tuple[float, float] = (0.0, 0.0)  # (low, high) ballpark, see README

    def as_sidecar(self) -> dict:
        d = asdict(self)
        d["sidecar_schema_version"] = "0.1.0"
        return d


# Order is the order shown in the GUI dropdown.
PROFILES: dict[str, Profile] = {
    "FDM_PLASTIC": Profile(
        key="FDM_PLASTIC",
        label="FDM Plastic (PLA/PETG, home printer)",
        family="FDM",
        min_r_mm=0.8,
        formats=("stl",),
        split_halves=True,
        notes=(
            "Layer height 0.16 mm; 15% infill. Glue halves with PVA or "
            "cyanoacrylate. Halves are exported flat-base-down so you "
            "can print without supports."
        ),
        suggested_finish="raw PLA, optional sanding 220→400→600",
        est_cost_usd=(2.0, 8.0),
    ),
    "SLA_RESIN": Profile(
        key="SLA_RESIN",
        label="SLA Resin (Form 3 / Saturn / Mars)",
        family="SLA",
        min_r_mm=0.5,
        formats=("stl",),
        notes="Best surface finish of home options. Brittle, photoreactive. UV-cure post-print.",
        suggested_finish="raw cured resin or primer+paint",
        est_cost_usd=(8.0, 30.0),
    ),
    "SLS_NYLON": Profile(
        key="SLS_NYLON",
        label="SLS Nylon (PA12 white)",
        family="SLS",
        min_r_mm=1.0,
        formats=("stl",),
        services=("Shapeways", "Sculpteo", "JLCPCB"),
        notes="Minimum wall 1 mm. Dye-able post-print.",
        suggested_finish="dyed or natural matte",
        est_cost_usd=(40.0, 110.0),
    ),
    "SLS_CARBON_FIBER": Profile(
        key="SLS_CARBON_FIBER",
        label="SLS Carbon Fiber (PA-CF charcoal)",
        family="SLS",
        min_r_mm=1.2,
        formats=("stl",),
        services=("Shapeways", "Sculpteo", "Hubs"),
        notes=(
            "Chopped carbon fiber in PA12. Granular matte black, high "
            "stiffness, ~30% lighter than nylon alone."
        ),
        suggested_finish="raw matte black",
        est_cost_usd=(120.0, 280.0),
    ),
    "SLM_METAL_ALUMINUM": Profile(
        key="SLM_METAL_ALUMINUM",
        label="SLM Aluminum (6061 / AlSi10Mg)",
        family="SLM",
        min_r_mm=1.5,
        decimate_to=0.55,
        formats=("stl", "step"),
        services=("Hyperforge3D", "Xometry", "Hubs metal"),
        notes="Minimum wall 1 mm. Support structures required during print.",
        suggested_finish="sandblasted",
        est_cost_usd=(300.0, 900.0),
    ),
    "SLM_METAL_STAINLESS": Profile(
        key="SLM_METAL_STAINLESS",
        label="SLM Stainless Steel (316L)",
        family="SLM",
        min_r_mm=1.5,
        decimate_to=0.55,
        formats=("stl", "step"),
        services=("Hyperforge3D", "Xometry"),
        notes="Heavy (~1.2 kg at defaults). Expensive.",
        suggested_finish="brushed or sandblasted",
        est_cost_usd=(500.0, 1400.0),
    ),
    "SLM_METAL_TITANIUM": Profile(
        key="SLM_METAL_TITANIUM",
        label="SLM Titanium (Ti-6Al-4V)",
        family="SLM",
        min_r_mm=1.5,
        decimate_to=0.55,
        formats=("stl", "step"),
        services=("Hyperforge3D", "Xometry"),
        notes="Aerospace material. Beautiful. Very expensive.",
        suggested_finish="anodised or polished",
        est_cost_usd=(1200.0, 3500.0),
    ),
    "SLM_METAL_BRONZE": Profile(
        key="SLM_METAL_BRONZE",
        label="SLM Bronze",
        family="SLM",
        min_r_mm=1.5,
        decimate_to=0.55,
        formats=("stl", "step"),
        services=("Shapeways bronze", "Xometry"),
        notes="Warm patina, polishable, heavy.",
        suggested_finish="hand-polished + patina",
        est_cost_usd=(400.0, 1200.0),
    ),
    "CNC_ALUMINUM": Profile(
        key="CNC_ALUMINUM",
        label="CNC Aluminum (5-axis)",
        family="CNC",
        min_r_mm=3.0,
        decimate_to=0.25,
        formats=("step", "stl"),
        services=("Xometry CNC", "Hubs CNC"),
        notes="Organic geometry requires 5-axis. Expensive vs additive.",
        suggested_finish="bead-blasted or brushed",
        est_cost_usd=(600.0, 1800.0),
    ),
    "INJECTION_MOLD": Profile(
        key="INJECTION_MOLD",
        label="Injection Mold (production 100+)",
        family="MOLD",
        min_r_mm=2.0,
        decimate_to=0.30,
        formats=("step",),
        add_draft_angle_deg=1.5,
        notes=(
            "Tooling cost $5000-15000. Only for high-volume runs. "
            "1.5° draft added to walls; soften sharp transitions with "
            "fillets before tooling."
        ),
        est_cost_usd=(5000.0, 15000.0),
    ),
    "PAPER_MACHE_MOLD": Profile(
        key="PAPER_MACHE_MOLD",
        label="Paper-Mâché Mold (mycelium workflow)",
        family="SPECIAL",
        min_r_mm=0.8,
        formats=("stl",),
        invert_to_cavity=True,
        add_pour_channels=True,
        notes=(
            "Negative cavity inside a surrounding block, with pour "
            "channel and air vents. Pour paper pulp into the cavity, "
            "press, dry, demould. Resulting paper form is the substrate "
            "mycelium colonises."
        ),
        suggested_finish="raw paper (substrate for mycelium)",
        est_cost_usd=(2.0, 8.0),
    ),
    "CASTING_PATTERN": Profile(
        key="CASTING_PATTERN",
        label="Casting Pattern (lost-wax bronze)",
        family="SPECIAL",
        min_r_mm=1.5,
        formats=("stl",),
        add_sprue=True,
        scale_factor=1.02,
        notes=(
            "Positive form scaled 2% larger to compensate bronze "
            "shrinkage. Sprue + runners attached. Send to a foundry; "
            "bronze casting at this scale runs $400-1500."
        ),
        suggested_finish="bronze, hand-patinated",
        est_cost_usd=(400.0, 1500.0),
    ),
}


def get(key: str) -> Profile:
    if key not in PROFILES:
        raise KeyError(
            f"Unknown profile {key!r}.  Known: {sorted(PROFILES.keys())}"
        )
    return PROFILES[key]


def list_keys() -> list[str]:
    return list(PROFILES.keys())
