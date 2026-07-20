"""把狐狸 Shape Key 预览整理成可直接比较的联系表。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps


CHARACTERS_ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = CHARACTERS_ROOT / "fox/source/previews/morph_prototype"
OUTPUT = PREVIEWS / "contact_sheets"
CELL = 384
LABEL_HEIGHT = 42
BACKGROUND = (26, 29, 34)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


TITLE_FONT = font(24)
LABEL_FONT = font(20)


def load(name: str) -> Image.Image:
    return Image.open(PREVIEWS / name).convert("RGB")


def labeled(image: Image.Image, label: str) -> Image.Image:
    canvas = Image.new("RGB", (CELL, CELL + LABEL_HEIGHT), BACKGROUND)
    canvas.paste(image.resize((CELL, CELL), Image.Resampling.LANCZOS), (0, LABEL_HEIGHT))
    draw = ImageDraw.Draw(canvas)
    bounds = draw.textbbox((0, 0), label, font=LABEL_FONT)
    x = (CELL - (bounds[2] - bounds[0])) // 2
    draw.text((x, 9), label, fill=(235, 237, 240), font=LABEL_FONT)
    return canvas


def sheet(rows: list[tuple[str, list[tuple[str, str]]]], output_name: str) -> None:
    width = 3 * CELL
    row_height = CELL + LABEL_HEIGHT + 38
    canvas = Image.new("RGB", (width, len(rows) * row_height), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for row_index, (title, cells) in enumerate(rows):
        y = row_index * row_height
        draw.text((16, y + 6), title, fill=(255, 202, 120), font=TITLE_FONT)
        for column, (filename, label) in enumerate(cells):
            canvas.paste(labeled(load(filename), label), (column * CELL, y + 38))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT / output_name)


def difference_score(variant: Image.Image, basis: Image.Image) -> float:
    difference = ImageChops.difference(variant, basis)
    histogram = difference.histogram()
    squared = sum((index % 256) ** 2 * count for index, count in enumerate(histogram))
    return math.sqrt(squared / (variant.width * variant.height * 3.0))


def difference_sheet() -> None:
    basis_front = load("Basis__head_front.png")
    families = (
        "Face_SkullWidth",
        "Face_CheekFullness",
        "Face_EyeSocketSize",
    )
    canvas = Image.new("RGB", (2 * CELL, len(families) * (CELL + LABEL_HEIGHT)), BACKGROUND)
    for row, family in enumerate(families):
        for column, suffix in enumerate(("Neg", "Pos")):
            image = load(f"{family}_{suffix}__head_front.png")
            difference = ImageChops.difference(image, basis_front)
            difference = ImageOps.autocontrast(difference)
            difference = ImageEnhance.Contrast(difference).enhance(1.6)
            score = difference_score(image, basis_front)
            cell = labeled(difference, f"{family} {suffix} diff RMS={score:.2f}")
            canvas.paste(cell, (column * CELL, row * (CELL + LABEL_HEIGHT)))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT / "fox_morph_difference_maps.png")


def main() -> None:
    face_rows = []
    for title, family in (
        ("Skull width", "Face_SkullWidth"),
        ("Cheek fullness", "Face_CheekFullness"),
        ("Eye socket size", "Face_EyeSocketSize"),
    ):
        face_rows.append(
            (
                title,
                [
                    (f"{family}_Neg__head_front.png", "Negative 1.0"),
                    ("Basis__head_front.png", "Neutral"),
                    (f"{family}_Pos__head_front.png", "Positive 1.0"),
                ],
            )
        )
    sheet(face_rows, "fox_face_morphs.png")

    body_rows = []
    for title, family, view in (
        ("Belly depth - front", "Body_BellyDepth", "front"),
        ("Belly depth - side", "Body_BellyDepth", "side"),
        ("Arm thickness - front", "Body_ArmThickness", "front"),
        ("Arm thickness - side", "Body_ArmThickness", "side"),
        ("Muzzle length - side", "Face_MuzzleLength", "side"),
    ):
        body_rows.append(
            (
                title,
                [
                    (f"{family}_Neg__{view}.png", "Negative 1.0"),
                    (f"Basis__{view}.png", "Neutral"),
                    (f"{family}_Pos__{view}.png", "Positive 1.0"),
                ],
            )
        )
    sheet(body_rows, "fox_body_and_muzzle_morphs.png")

    sheet(
        [
            (
                "Combined body",
                [
                    ("Combined_Lean__front.png", "Lean preset"),
                    ("Basis__front.png", "Neutral"),
                    ("Combined_Round__front.png", "Round preset"),
                ],
            ),
            (
                "Combined face",
                [
                    ("Combined_Lean__head_front.png", "Lean preset"),
                    ("Basis__head_front.png", "Neutral"),
                    ("Combined_Round__head_front.png", "Round preset"),
                ],
            ),
        ],
        "fox_combined_morphs.png",
    )
    difference_sheet()


if __name__ == "__main__":
    main()
