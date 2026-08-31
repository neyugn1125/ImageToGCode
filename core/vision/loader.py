from __future__ import annotations

import struct
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import cv2
import numpy as np

from core.vision.types import ASPECT_RATIO_TOLERANCE


def load_binary_image(image_path: Path) -> np.ndarray:
    """Read a dark-on-white drawing as an inverted binary image."""
    if not image_path.is_file():
        raise RuntimeError(f"Error: Unable to read input image: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Error: Unable to read input image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    return binary


def _read_png_text_chunks(image_path: Path) -> dict[str, str]:
    """Read uncompressed PNG ``tEXt`` metadata without adding a PIL dependency."""
    if image_path.suffix.lower() != ".png":
        return {}
    try:
        payload = image_path.read_bytes()
    except OSError:
        return {}
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return {}

    metadata: dict[str, str] = {}
    offset = 8
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > len(payload):
            break
        chunk_type = payload[offset + 4 : offset + 8]
        if chunk_type == b"tEXt":
            keyword, separator, value = payload[chunk_start:chunk_end].partition(b"\0")
            if separator:
                try:
                    metadata[keyword.decode("latin-1")] = value.decode("latin-1")
                except UnicodeDecodeError:
                    pass
        offset = chunk_end + 4
        if chunk_type == b"IEND":
            break
    return metadata


def diagrams_net_square_size_mm(image_path: Path) -> float | None:
    """Return the largest square size embedded in a diagrams.net PNG export."""
    encoded_graph = _read_png_text_chunks(image_path).get("mxfile")
    if not encoded_graph:
        return None
    try:
        root = ElementTree.fromstring(unquote(encoded_graph))
    except (ElementTree.ParseError, ValueError):
        return None

    square_sizes: list[float] = []
    for cell in root.iter():
        if cell.tag.rsplit("}", 1)[-1] != "mxCell" or cell.get("vertex") != "1":
            continue
        style = cell.get("style", "")
        # The filled 10 x 10 calibration marker is not the part envelope.
        if "fillcolor=#000000" in style.lower():
            continue
        geometry = next(
            (
                child
                for child in cell
                if child.tag.rsplit("}", 1)[-1] == "mxGeometry"
            ),
            None,
        )
        if geometry is None:
            continue
        try:
            width = float(geometry.get("width", "nan"))
            height = float(geometry.get("height", "nan"))
        except ValueError:
            continue
        if (
            np.isfinite(width)
            and np.isfinite(height)
            and width > 0
            and height > 0
            and abs(width / height - 1.0) <= ASPECT_RATIO_TOLERANCE
        ):
            square_sizes.append(max(width, height))
    return max(square_sizes) if square_sizes else None
