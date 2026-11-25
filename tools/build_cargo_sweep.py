"""Bake the brightness envelope sampled by the socket material's GPU panner."""
from PIL import Image

from build_catalog_icon import cook_texture


NAME = "T_WinchCargoSweep"
SIZE = (512, 256)
LED_COLUMNS = 42
TRAIL_CELLS = 5
FRONT_CELLS = 1
ROW_HEIGHT = 4


def sweep_image():
    width, height = SIZE
    image = Image.new("RGBA", SIZE)
    for columns in range(1, LED_COLUMNS + 1):
        period = columns + TRAIL_CELLS + FRONT_CELLS
        row = []
        for x in range(width):
            distance = period * (x + 0.5) / width
            if distance <= TRAIL_CELLS:
                brightness = (distance / TRAIL_CELLS) ** 1.6
            else:
                front = max(0, 1 - (distance - TRAIL_CELLS) / FRONT_CELLS)
                brightness = front * front * (3 - 2 * front)
            alpha = round(255 * brightness)
            # RGB is stored in sRGB and alpha is stored linearly.
            srgb = 1.055 * brightness ** (1 / 2.4) - 0.055 if brightness > 0.0031308 else 12.92 * brightness
            color = round(255 * srgb)
            row.append((color, color, color, alpha))
        tile = Image.new("RGBA", (width, ROW_HEIGHT))
        tile.putdata(row * ROW_HEIGHT)
        image.paste(tile, (0, (columns - 1) * ROW_HEIGHT))
    return image


def cook(template, output, uassetgui, usmap):
    cook_texture(template, output, uassetgui, usmap, NAME, sweep_image(), SIZE)
