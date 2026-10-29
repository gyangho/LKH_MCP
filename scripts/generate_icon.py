"""Generate the LKH MCP cyan/indigo hexagonal M icon for tray and Windows EXE.

Inspired by the provided icon image; all shapes are vector-drawn using Pillow,
no fonts, external assets or network requests required.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def generate(output_dir: Path | None = None) -> tuple[Path, Path]:
    folder = output_dir or (Path(__file__).resolve().parent.parent / "assets")
    folder.mkdir(parents=True, exist_ok=True)
    zoom, side = 4, 256
    def points(values):
        return [(round(x * zoom), round(y * zoom)) for x, y in values]
    image = Image.new("RGBA", (side * zoom, side * zoom))
    shadow = Image.new("RGBA", image.size)
    sh = ImageDraw.Draw(shadow)
    outline = [(128, 18), (222, 72), (222, 183), (128, 238),
               (34, 183), (34, 72)]
    sh.polygon(points(outline), fill=(5, 21, 76, 135))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6 * zoom))
    image.alpha_composite(shadow)
    d = ImageDraw.Draw(image)
    def face(vertices, fill):
        d.polygon(points(vertices), fill=fill)
    face(outline, "#1554de")
    face([(128, 18), (222, 72), (128, 126), (34, 72)], "#0ecafb")
    face([(34, 72), (128, 126), (128, 238), (34, 183)], "#1477ec")
    face([(128, 126), (222, 72), (222, 183), (128, 238)], "#4b35e8")
    face([(128, 18), (222, 72), (128, 126)], "#078df8")
    face([(128, 126), (222, 183), (128, 238)], "#2e26c6")
    # White M-shaped prism; designed to remain legible at 16 px.
    face([(59, 98), (80, 86), (128, 116), (176, 86),
          (197, 98), (197, 174), (175, 186), (175, 121),
          (139, 146), (139, 194), (117, 194), (117, 146),
          (81, 121), (81, 186), (59, 174)], "#f6fdff")
    face([(59, 98), (80, 86), (128, 116), (117, 135)], "#bdf3ff")
    face([(139, 146), (175, 121), (175, 144), (139, 170)], "#c0d2ff")
    face([(117, 146), (139, 146), (139, 194), (117, 182)], "#d9e5ff")
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    png_path = folder / "lkh-mcp.png"
    ico_path = folder / "lkh-mcp.ico"
    image.save(png_path)
    image.save(ico_path, format="ICO",
               sizes=[(16, 16), (20, 20), (24, 24), (32, 32),
                      (48, 48), (64, 64), (128, 128), (256, 256)])
    return png_path, ico_path


if __name__ == "__main__":
    png, ico = generate()
    print(f"Generated {png}")
    print(f"Generated {ico}")
