"""Generate Windows tray PNG and multi-resolution ICO from the approved CLI pig.

The reviewed pixel-art source is versioned at branding/pig-terminal.png.
No geometry redraw, recoloring, or network access occurs during the build.
"""
from __future__ import annotations
from pathlib import Path

from PIL import Image

SOURCE_FILE = Path(__file__).resolve().parent.parent / "branding" / "pig-terminal.png"
ICON_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32),
              (48, 48), (64, 64), (128, 128), (256, 256)]


def generate(output_dir: Path | None = None) -> tuple[Path, Path]:
    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(f"Approved CLI pig icon source is missing: {SOURCE_FILE}")

    folder = output_dir or (Path(__file__).resolve().parent.parent / "assets")
    folder.mkdir(parents=True, exist_ok=True)

    with Image.open(SOURCE_FILE) as source:
        icon = source.convert("RGBA")
    if icon.size != (256, 256):
        icon = icon.resize((256, 256), Image.Resampling.NEAREST)

    png_path = folder / "lkh-mcp.png"
    ico_path = folder / "lkh-mcp.ico"
    icon.save(png_path, format="PNG", optimize=True)
    icon.save(ico_path, format="ICO", sizes=ICON_SIZES)
    return png_path, ico_path


if __name__ == "__main__":
    png, ico = generate()
    print(f"Tray PNG: {png}")
    print(f"Windows EXE ICO: {ico}")
