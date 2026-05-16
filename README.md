# voice-to-form

A macOS desktop app that turns short voice recordings into 3D-printable
sculptural objects.  Single-user tool for one artist's sculptural
practice (the mycelium-waveform project).

Version: **v0.3.0** — vertical-ellipse cross-section (asymmetry preserved),
combined Design tab, adjustable viewport background, high-contrast
waveform plot.

> _Every source file prints its own version on import, so the boot log
> shows exactly which build is running. See "Versioning" at the
> bottom._

---

## What it does

Audio in → mesh out.  Each WAV becomes a closed, watertight sculptural
form built from a **shared-spine elliptical sweep**:

- For each x along the form's length we build a vertical half-ellipse
  for the top and one for the bottom.
- Top and bottom have **different** vertical radii (the positive vs
  negative peaks of the waveform).
- Top and bottom **share** their horizontal radius (the average of the
  two verticals).

The shared horizontal is the architectural commitment that kills every
"looks like a table leg" and "looks like two pieces stuck together"
failure mode from the development log.  Do not change it.

**Cross-section aspect (v0.3+).**  The horizontal radius is multiplied
by a tunable aspect ratio so the cross-section can be a portrait
ellipse rather than a near-circle.  Default `aspect = 0.7` gives a
~1.4× taller-than-wide cross-section — matching the
"front-view-is-a-vertical-oval" sketches.  Top/bottom asymmetry is
preserved (top still uses `top_r_v`, bottom uses `bottom_r_v`); only
the shared horizontal width is squeezed.  Clamped to `min_r_mm` so
quiet passages never drop below the manufacturable wall thickness.

  - `aspect = 1.0` → v0.1 behaviour (near-circular when top ≈ bottom)
  - `aspect = 0.7` → portrait ellipse (default)
  - `aspect = 0.4` → very tall vertical ellipse
  - `aspect = 1.5` → flattened / squashed

---

## Quick install (macOS)

```bash
# 1. Clone
cd ~/CODE/GitHub
git clone https://github.com/Belquer/mycelium_waveform.git
cd mycelium_waveform

# 2. Python 3.11 or 3.12 (not 3.14 — most science wheels don't ship for it yet)
brew install python@3.12

# 3. Venv + deps
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `open3d` fails to install (Apple Silicon + Python 3.13+), comment
it out — decimation falls back to `trimesh.simplify_quadric_decimation`
automatically and prints a warning.

---

## Hello world (record → STL → preview)

**Double-click `voice-to-form.command`.**  First run installs the venv
and requirements (one-time, 2–5 min).  Every run after that just opens
the app.

In the GUI:

1. **Input** tab → pick your **Input device** (e.g. your audio
   interface) and **Channel**, then click **● Record**.  Press
   **■ Stop** when you're done — recording is open-ended, no fixed
   duration.  Waveform plot is deep-violet ink on cream paper, echoing
   the napkin sketches.  (Or `Load WAV…` to use an existing file.)
2. **Design** tab → geometry + appearance combined.  Scrollable
   controls on the left (dimensions, cross-section aspect, surface,
   adjustable viewport background, advanced smoothing); live 3D
   preview on the right.  All changes update instantly — no tab
   switching to compare a length tweak against a colour change.
3. **Verify** tab → check the three-stack overlay; tick "Reviewed".
4. **Export** tab → pick `FDM Plastic` → `Save to library + Export`.

A new entry appears in `library/<date>_<title>/` containing
`source.wav`, `config.yaml`, `preview.png`, and
`exports/FDM_PLASTIC/{form.stl, form_top.stl, form_bottom.stl, spec.json}`.

### Headless / CI

```bash
source .venv/bin/activate
python main.py --cli examples/multitudes.wav out/ --profile FDM_PLASTIC
```

### One-button launcher

- **`voice-to-form.command`** (double-click).  On first run it
  creates the `.venv`, installs requirements, then launches.  Every
  subsequent run just launches.  Terminal stays open on error.

---

## Manufacturing profiles

| Key | Material | Min radius | Format | Indicative cost |
|---|---|---|---|---|
| `FDM_PLASTIC` | PLA / PETG home print | 0.8 mm | STL (+ halves) | $2–8 |
| `SLA_RESIN` | Resin (Form 3 / Saturn) | 0.5 mm | STL | $8–30 |
| `SLS_NYLON` | PA12 white (Shapeways / Sculpteo) | 1.0 mm | STL | $40–110 |
| `SLS_CARBON_FIBER` | PA-CF charcoal (Shapeways / Hubs) | 1.2 mm | STL | $120–280 |
| `SLM_METAL_ALUMINUM` | 6061 / AlSi10Mg (Hyperforge3D / Xometry) | 1.5 mm | STL + STEP* | $300–900 |
| `SLM_METAL_STAINLESS` | 316L | 1.5 mm | STL + STEP* | $500–1400 |
| `SLM_METAL_TITANIUM` | Ti-6Al-4V | 1.5 mm | STL + STEP* | $1200–3500 |
| `SLM_METAL_BRONZE` | Bronze (Shapeways / Xometry) | 1.5 mm | STL + STEP* | $400–1200 |
| `CNC_ALUMINUM` | 5-axis CNC | 3.0 mm | STEP + STL | $600–1800 |
| `INJECTION_MOLD` | Production tooling (100+) | 2.0 mm | STEP | $5k–15k tooling |
| `PAPER_MACHE_MOLD` | Mycelium substrate workflow | 0.8 mm | STL (cavity) | $2–8 |
| `CASTING_PATTERN` | Lost-wax bronze | 1.5 mm | STL (+2% shrink) | $400–1500 |

\* STEP export in v0.1 is best-effort.  Without a STEP writer
installed, the export drops a `form.step.NOTE.txt` with manual
instructions (FreeCAD: Part workbench → Convert to solid → Export).
Most metal-SLM services accept STL for organic forms anyway.

Each export writes a `spec.json` sidecar with material notes,
suggested service, finish, and the parameters that were actually
applied.

### v0.1 stubs

These profile flags are **recorded in the sidecar but not yet applied
as geometry**.  They're documented stubs:

- `add_draft_angle_deg` (INJECTION_MOLD)
- `add_sprue` (CASTING_PATTERN)
- `add_pour_channels` (PAPER_MACHE_MOLD)
- `invert_to_cavity` (PAPER_MACHE_MOLD)

The base STL is still produced so the artist isn't blocked from
prototyping while those land in v0.2.

---

## The diagnostic overlay (why it exists)

The Verify tab shows three stacked plots:

1. **Original audio**, with the y-axis scaled to the form's mm.
2. **Form's side silhouette** — `top_r_v` above zero, `-bottom_r_v`
   below.
3. **Direct overlay** — the audio (semi-transparent purple) under the
   form's top and bottom envelopes (red).

Plus a numerical peak-proportion table:

```
Peak 1:  audio rel 1.00   form rel 0.97   Δ -0.03
Peak 2:  audio rel 0.62   form rel 0.65   Δ +0.03
Peak 3:  audio rel 0.41   form rel 0.39   Δ -0.02
```

If any peak disagrees by more than 10 % the table flips to a yellow
warning.

This is the diagnostic that caught proportion errors during
development.  Export is gated on the artist ticking **"I've reviewed
the overlay"** — a self-discipline gate, not a security boundary.  Any
change to envelopes or geometry resets the tick.

---

## Library

```
library/
  2026-05-16_multitudes/
    source.wav          ← copy of input (not a reference)
    config.yaml         ← every parameter
    preview.png         ← diagnostic overlay snapshot
    exports/
      FDM_PLASTIC/
        form.stl
        form_top.stl
        form_bottom.stl
        spec.json
```

The Library tab lists all past entries; double-click to reopen with
its original settings.  v0.1 ships a plain list view; the thumbnail
grid is planned for v0.2.

---

## Tests

```bash
source .venv/bin/activate
pip install pytest
pytest -q
```

Covers:

- WAV loading at multiple sample rates
- Envelope extraction shape + joint normalisation + top/bottom
  asymmetry preserved
- Mesh generation: vertex/face count, watertightness via trimesh,
  outward normals, shared horizontal radius
- Every export profile produces a file + spec.json
- Library save/load round-trip

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Form looks like a table leg | Symmetric architecture | Use shared-spine (this app already does — make sure you're not calling `build_mesh` with `abs(samples)` derived envelopes) |
| I see a seam line down y=0 | Mesh closure topology | Shared-spine has no seam by construction; if you see one, `n_theta` is odd — must be even |
| Silences are too thick | `min_r_mm` too high or `hop_ms` too small | Bump hop or drop min_r |
| Loud peaks exaggerated | `gamma > 1.0` | Set γ = 1.0 (default) |
| Surface looks faceted | Too few samples | Raise `n_theta` (96 default) or `nx` (700 default) |
| STL too large to upload | Service portal limit | Pick an SLM/CNC profile — they decimate to 25–55 % |
| Form looks like two pieces stuck together | Top and bottom have independent horizontal widths | Don't — `shared_r_h = (top_r_v + bottom_r_v) / 2` is the architectural commitment |
| Top and bottom too similar | Using `abs(samples).max()` for both | Use positive-only and negative-only peaks separately (this is what `extract_envelopes` does) |

---

## Layout

```
.
├── main.py                  GUI entry / CLI
├── requirements.txt
├── run.command              double-click launcher
├── setup.command            double-click venv + pip install
├── src/
│   ├── audio.py             load + envelope extraction
│   ├── geometry.py          shared-spine mesh builder
│   ├── decimation.py        open3d / trimesh quadric decimation
│   ├── export.py            STL / STEP / sidecar JSON
│   ├── profiles.py          12 manufacturing profiles
│   ├── overlay.py           3-stack diagnostic figure + peak report
│   ├── preview.py           pyqtgraph.opengl viewport
│   ├── config.py            YAML persistence
│   ├── library.py           per-form library entries
│   └── gui/
│       ├── state.py         AppState (Qt signals)
│       ├── main_window.py
│       ├── tab_input.py
│       ├── tab_geometry.py
│       ├── tab_appearance.py
│       ├── tab_verify.py
│       └── tab_export.py
├── tests/
│   ├── conftest.py          synthetic WAV fixtures
│   ├── test_audio.py
│   ├── test_geometry.py
│   ├── test_overlay.py
│   ├── test_export.py
│   └── test_library.py
├── examples/                place sample WAVs here
└── library/                 saved forms (per-entry directories)
```

---

## Versioning

Per the project rules: every source file carries a semantic version
and prints it on import.  Current file versions:

```
main.py                       v0.3.0   (--version banner)
src/audio.py                  v0.2.0   (Recorder, list_input_devices)
src/geometry.py               v0.3.0   (cross_section_aspect)
src/profiles.py               v0.1.0
src/export.py                 v0.1.0
src/decimation.py             v0.1.0
src/overlay.py                v0.1.0
src/config.py                 v0.3.0   (aspect + viewport_bg_hex)
src/library.py                v0.1.0
src/preview.py                v0.2.0   (set_color/set_background live)
src/gui/state.py              v0.2.0   (appearance_changed signal)
src/gui/main_window.py        v0.3.0   (4-tab layout, Design combined)
src/gui/tab_input.py          v0.3.0   (cream/violet waveform plot)
src/gui/tab_geometry.py       v0.3.0   (Design tab: geometry+appearance)
src/gui/tab_verify.py         v0.1.0
src/gui/tab_export.py         v0.1.0
voice-to-form.command         v0.2.0   (combined setup+run)
```

`src/gui/tab_appearance.py` is removed in v0.3.0; its controls live in
the Design tab now.

Bumps:

- **MAJOR** — breaking API or geometry algorithm change
- **MINOR** — new feature, new profile, new tunable
- **PATCH** — fixes that don't change behaviour

Run `python main.py --version` to print every module's banner.

---

## Version history

**v0.3.0:**

- `cross_section_aspect` parameter for vertical-ellipse cross sections
  (default 0.7 — ~1.4× taller than wide).  Asymmetric top/bottom is
  preserved; only the horizontal width is squeezed.
- Geometry + Appearance combined into a single **Design** tab (4 tabs
  total: Input → Design → Verify → Export).
- Adjustable viewport background — colour-picker, hex entry,
  brightness slider, and named presets all on the Design tab.
- High-contrast waveform plot — deep-violet curve on cream paper.

**v0.2.0:**

- One-click launcher (`voice-to-form.command`) — setup + run combined.
- Open-ended press-to-start / press-to-stop recording.
- Audio input device + channel selection for multi-input interfaces.
- Live appearance preview (colour/background updates instantly).
- Brighter default mesh colour + mid-dark viewport background.

## Coming in v0.4+

- PBR procedural normal maps for the appearance bump-pattern dropdown
  (the slider state is already saved in config — only the renderer
  needs to catch up)
- Mycelium-colonisation simulation in preview (procedural noise growth
  with adjustable coverage %)
- Library thumbnail grid
- Batch mode: folder of WAVs → STLs for all
- Comparison view (two forms side-by-side)
- Animation export (rotating MP4 / GIF)
- Real geometry mods for the stub profile flags (draft angle, sprue,
  pour channels, cavity inversion)
