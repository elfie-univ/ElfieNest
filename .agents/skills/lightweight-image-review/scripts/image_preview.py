"""Read-only source inspection and bounded, non-upscaled JPEG review copies."""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def metadata(path):
    with Image.open(path) as im:
        dimensions, kind = im.size, im.format
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path),
        "dimensions": dimensions,
        "format": kind,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def load_copy(path, crop):
    with Image.open(path) as source:
        source.seek(0)
        image = ImageOps.exif_transpose(source).convert("RGBA")
    if crop:
        left, top, right, bottom = crop
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError("Crop must lie within the EXIF-oriented source image.")
        image = image.crop(crop)
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    return background


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "preview"])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--crop", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM")
    )
    parser.add_argument("--max-edge", type=int, default=1536)
    parser.add_argument("--max-bytes", type=int, default=1400000)
    args = parser.parse_args()
    files = [p.resolve(strict=True) for p in args.files]
    if len(files) > 12:
        parser.error("Choose at most 12 sources for one overview.")
    originals = [metadata(p) for p in files]
    if args.action == "inspect":
        print(json.dumps({"sources": originals}, ensure_ascii=False))
        return
    if not args.out or args.out.suffix.lower() not in (".jpg", ".jpeg"):
        parser.error("preview requires a new --out .jpg file.")
    output = args.out.resolve()
    if output in files or output.exists():
        parser.error("Output must be new and must not overwrite a source.")
    if output.parent in {p.parent for p in files}:
        parser.error("Put previews in a separate output directory.")
    if args.crop and len(files) != 1:
        parser.error("--crop requires exactly one source.")
    if not 128 <= args.max_edge <= 4096 or args.max_bytes < 10000:
        parser.error("Use max-edge 128..4096 and max-bytes >= 10000.")
    images = [load_copy(p, args.crop) for p in files]
    if len(images) == 1:
        canvas = images[0]
    else:
        columns = math.ceil(math.sqrt(len(images)))
        rows = math.ceil(len(images) / columns)
        cell_width = max(64, args.max_edge // columns)
        cell_height = max(64, args.max_edge // rows)
        for image in images:
            image.thumbnail(
                (cell_width - 12, cell_height - 30), Image.Resampling.LANCZOS
            )
        row_heights = [
            max(im.height for im in images[r * columns : (r + 1) * columns]) + 30
            for r in range(rows)
        ]
        canvas = Image.new("RGB", (columns * cell_width, sum(row_heights)), "#eeeeee")
        draw = ImageDraw.Draw(canvas)
        for index, image in enumerate(images):
            x = (index % columns) * cell_width
            y = sum(row_heights[: index // columns])
            canvas.paste(image, (x + (cell_width - image.width) // 2, y + 25))
            draw.text((x + 6, y + 6), str(index + 1), fill="black")
    canvas.thumbnail((args.max_edge, args.max_edge), Image.Resampling.LANCZOS)
    encoded = None
    for _ in range(8):
        data = io.BytesIO()
        canvas.save(data, format="JPEG", quality=82, optimize=True)
        if data.tell() <= args.max_bytes:
            encoded = data.getvalue()
            break
        if min(canvas.size) < 160:
            break
        canvas.thumbnail(
            (int(canvas.width * 0.8), int(canvas.height * 0.8)),
            Image.Resampling.LANCZOS,
        )
    if encoded is None:
        parser.error(
            "Cannot meet byte budget with a useful overview; select fewer images or a crop."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a file appearing after the exists check.
    with output.open("xb") as stream:
        stream.write(encoded)
    print(
        json.dumps(
            {
                "preview": str(output),
                "dimensions": canvas.size,
                "bytes": len(encoded),
                "data_url_bytes_estimate": 23 + 4 * math.ceil(len(encoded) / 3),
                "source_bytes": sum(item["bytes"] for item in originals),
                "crop": args.crop,
                "sources": originals,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
