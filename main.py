"""
voice-to-form  —  main.py  v0.4.0

GUI entry point.  Also doubles as a tiny CLI:

  python main.py                         launch GUI
  python main.py --cli FILE.wav OUT/     headless: WAV → STL + overlay PNG
  python main.py --version               print versions of every module

The CLI path is what tests, the .command launcher, and headless
benchmarking use.  It bypasses Qt entirely.
"""
from __future__ import annotations

__version__ = "0.1.0"

import argparse
import sys
from pathlib import Path

# Import order matters only for the printed version banner — each
# module prints "modulename vX.Y.Z" on import, so we can see at a
# glance which build is loaded.
print(f"[voice-to-form] main.py v{__version__}", file=sys.stderr)


def _run_gui() -> int:
    # Qt imports are heavy; defer until we know we need them.
    from PyQt6.QtWidgets import QApplication
    from src.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("voice-to-form")
    app.setApplicationVersion(__version__)
    win = MainWindow()
    win.show()
    return app.exec()


def _run_cli(wav_path: Path, out_dir: Path, profile_key: str) -> int:
    from src.audio import load_wav, trim_silence, extract_envelopes
    from src.geometry import GeometryParams, build_mesh
    from src.export import export_profile
    from src.overlay import build_figure, save_png

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading {wav_path}…")
    y, sr = load_wav(wav_path)
    y = trim_silence(y, sr)
    print(f"  {len(y)/sr:.2f} s @ {sr} Hz")

    env = extract_envelopes(y, sr)
    params = GeometryParams()
    mesh = build_mesh(env, params)
    print(f"  mesh: {mesh.triangle_count():,} triangles")

    out = export_profile(env, params, profile_key, out_dir, title=wav_path.stem)
    print(f"  exported → {out}")

    fig = build_figure(y, env, params)
    png = out_dir / "overlay.png"
    save_png(fig, str(png))
    print(f"  overlay → {png}")
    return 0


def _print_versions() -> int:
    # Import everything so each module's banner fires.
    from src import audio, geometry, profiles, export, decimation, overlay, config, library, preview  # noqa: F401
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="voice-to-form")
    p.add_argument("--cli", nargs=2, metavar=("WAV", "OUT_DIR"),
                   help="Run headless: WAV → exports in OUT_DIR.")
    p.add_argument("--profile", default="FDM_PLASTIC",
                   help="Manufacturing profile key (default FDM_PLASTIC).")
    p.add_argument("--version", action="store_true",
                   help="Print module versions and exit.")
    args = p.parse_args()

    if args.version:
        return _print_versions()
    if args.cli:
        return _run_cli(Path(args.cli[0]), Path(args.cli[1]), args.profile)
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
