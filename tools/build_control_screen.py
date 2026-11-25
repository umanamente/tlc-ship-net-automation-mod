"""Bake the cabinet's centered SETTINGS control for the native CRT material."""

from PIL import Image, ImageDraw

from build_catalog_icon import cook_texture
from build_construction_mesh import geometry


NAME = "T_WinchControlScreen"
SIZE = (1120, 352)  # 16 texels per centimetre on the 70 x 22 cm glass


def screen_image():
    points, _, colors, indices = geometry()
    faces = []
    for start in range(0, len(indices), 3):
        corners = indices[start:start + 3]
        vertices = [points[index] for index in corners]
        # Include the actual button frame and glyphs between the glass and the CRT overlay.
        if all(-39.2 <= x <= 30.8 and 18.5 <= z <= 40.5 and 57.6 < y < 57.76
               for x, y, z in vertices):
            faces.append((sum(y for _, y, _ in vertices), colors[corners[0]], vertices))
    if len({color for _, color, _ in faces}) != 2:
        raise ValueError("Expected the button outline and SETTINGS lettering on the cabinet glass")

    supersample = 3
    scale = 16 * supersample
    canvas = Image.new("L", tuple(size * supersample for size in SIZE), 5)
    draw = ImageDraw.Draw(canvas)
    for _, (blue, green, red), vertices in sorted(faces, key=lambda face: face[0]):
        # SlateUI supplies a neutral signal. The game's terminal material provides its tint.
        linear = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
        srgb = 1.055 * linear ** (1 / 2.4) - 0.055 if linear > 0.0031308 else 12.92 * linear
        polygon = [((x + 39.2) * scale, (40.5 - z) * scale) for x, _, z in vertices]
        draw.polygon(polygon, fill=round(255 * srgb))
    return canvas.resize(SIZE, Image.Resampling.LANCZOS)


def cook(template, output, uassetgui, usmap):
    image = screen_image()
    cook_texture(template, output, uassetgui, usmap, NAME, image, image.size)
