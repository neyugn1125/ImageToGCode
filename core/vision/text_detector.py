from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class DimensionText:
    """Recognized dimension text with bounding box and numerical value."""

    raw_text: str
    value: float | None
    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    is_vertical: bool
    confidence: float


# Reference 10x14 binary bit patterns for standard CAD digits
_CAD_DIGIT_BITPATTERNS: dict[str, list[str]] = {
    "0": [
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ],
    "1": [
        "...###....",
        "..####....",
        ".#####....",
        "######....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "...###....",
        "##########",
    ],
    "2": [
        ".#######..",
        "#########.",
        "###...####",
        ".......###",
        ".......###",
        "......###.",
        ".....####.",
        "....####..",
        "...####...",
        "..####....",
        ".####.....",
        "#####.....",
        "##########",
        "##########",
    ],
    "3": [
        ".#######..",
        "#########.",
        "###...####",
        ".......###",
        ".......###",
        "....#####.",
        "....######",
        ".......###",
        ".......###",
        ".......###",
        "###...####",
        "#########.",
        ".#######..",
        "..#####...",
    ],
    "4": [
        "......###.",
        ".....####.",
        "....#####.",
        "...######.",
        "..#######.",
        ".###..###.",
        "###...###.",
        "##########",
        "##########",
        "......###.",
        "......###.",
        "......###.",
        "......###.",
        "......###.",
    ],
    "5": [
        "##########",
        "##########",
        "###.......",
        "###.......",
        "#########.",
        "##########",
        ".......###",
        ".......###",
        ".......###",
        ".......###",
        "###...####",
        "#########.",
        ".########.",
        "..######..",
    ],
    "6": [
        "..######..",
        ".########.",
        "###.......",
        "###.......",
        "#########.",
        "##########",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ],
    "7": [
        "##########",
        "##########",
        ".......###",
        "......###.",
        ".....####.",
        "....####..",
        "...####...",
        "...###....",
        "..###.....",
        "..###.....",
        ".###......",
        ".###......",
        ".###......",
        ".###......",
    ],
    "8": [
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ],
    "9": [
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "##########",
        ".#########",
        ".......###",
        ".......###",
        ".......###",
        ".......###",
        ".########.",
        "..######..",
    ],
    "Ø": [
        "....###...",
        "..######..",
        ".########.",
        "###.##.###",
        "###.##.###",
        "###.##.###",
        "###.##.###",
        "###.##.###",
        "###.##.###",
        "###.##.###",
        ".########.",
        "..######..",
        "...###....",
        "....#.....",
    ],
    "R": [
        "#########.",
        "##########",
        "###....###",
        "###....###",
        "##########",
        "#########.",
        "###..###..",
        "###...###.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
    ],
}


def _build_cad_templates() -> dict[str, np.ndarray]:
    templates = {}
    for char, rows in _CAD_DIGIT_BITPATTERNS.items():
        grid = np.zeros((len(rows), len(rows[0])), dtype=np.uint8)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == "#":
                    grid[r, c] = 255
        templates[char] = grid
    return templates


_CAD_TEMPLATES = _build_cad_templates()


def _classify_digit_bitmap(crop: np.ndarray) -> tuple[str, float]:
    """Match a normalized 10x14 binary crop against CAD digit templates."""
    if crop.shape[0] < 4 or crop.shape[1] < 2:
        return "", 0.0

    h, w = crop.shape
    aspect = h / float(max(w, 1))

    # Single vertical line is always '1'
    if aspect >= 2.0 and w <= 7:
        return "1", 0.98

    # Normalize to 10x14
    normalized = cv2.resize(crop, (10, 14), interpolation=cv2.INTER_AREA)
    _, norm_bin = cv2.threshold(normalized, 60, 255, cv2.THRESH_BINARY)

    best_char = ""
    best_score = -1.0

    for char, templ in _CAD_TEMPLATES.items():
        # Match using cross-correlation / intersection over union
        intersection = np.sum((norm_bin > 0) & (templ > 0))
        union = np.sum((norm_bin > 0) | (templ > 0))
        iou = float(intersection) / float(max(union, 1))

        if iou > best_score:
            best_score = iou
            best_char = char

    return best_char, max(0.0, min(best_score, 1.0))


def _split_and_read_roi(crop: np.ndarray) -> str:
    """Split touching digits in an ROI using projection valley detection and read each glyph."""
    h, w = crop.shape
    if h < 5 or w < 3:
        return ""

    col_sums = np.sum(crop > 0, axis=0)
    col_active = np.where(col_sums > 0)[0]
    if len(col_active) == 0:
        return ""

    c_start, c_end = int(col_active[0]), int(col_active[-1] + 1)
    trimmed = crop[:, c_start:c_end]
    tw = trimmed.shape[1]

    # In CAD drawings, character glyphs are ~9-12 px wide
    num_chars = max(1, int(round(tw / 10.5)))
    if num_chars == 1:
        char, _ = _classify_digit_bitmap(trimmed)
        return char

    chunk_w = tw / float(num_chars)
    cuts = [0]
    for k in range(1, num_chars):
        target = int(round(k * chunk_w))
        search = range(max(1, target - 4), min(tw - 1, target + 5))
        col_min = min(search, key=lambda cx: col_sums[c_start + cx])
        cuts.append(col_min)
    cuts.append(tw)

    chars = []
    for i in range(len(cuts) - 1):
        glyph = trimmed[:, cuts[i] : cuts[i + 1]]
        char, _ = _classify_digit_bitmap(glyph)
        if char:
            chars.append(char)
    return "".join(chars)


def detect_dimension_texts(binary: np.ndarray) -> list[DimensionText]:
    """Extract dimension text annotations from drawing using CCL, Opening and OCR."""
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
    if num_labels <= 1:
        return []

    # Isolate small text CCs
    text_mask = np.zeros_like(binary)
    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if 15 <= area <= 500 and max(w, h) < 65:
            text_mask[labels == i] = 255

    # Group adjacent character CCs into word boxes (ROI)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (14, 6))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (6, 14))
    dilated = cv2.bitwise_or(cv2.dilate(text_mask, kernel_h), cv2.dilate(text_mask, kernel_v))

    cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results: list[DimensionText] = []

    for c in cnts:
        rx, ry, rw, rh = cv2.boundingRect(c)
        if rw < 6 or rh < 6:
            continue

        roi_raw = text_mask[ry : ry + rh, rx : rx + rw]

        # Determine orientation: vertical if height >= width
        is_vertical = rh >= rw * 1.05

        if is_vertical:
            # Rotate 90 deg clockwise to normalize vertical text to horizontal
            roi = cv2.rotate(roi_raw, cv2.ROTATE_90_CLOCKWISE)
        else:
            roi = roi_raw

        word = _split_and_read_roi(roi)
        if not word and is_vertical:
            # Try unrotated
            word = _split_and_read_roi(roi_raw)
            if word:
                is_vertical = False

        if not word:
            continue

        # Extract numeric value
        digits_only = "".join([ch for ch in word if ch.isdigit() or ch == "."])
        value = None
        if digits_only:
            try:
                value = float(digits_only)
            except ValueError:
                value = None

        results.append(
            DimensionText(
                raw_text=word,
                value=value,
                bbox=(rx, ry, rw, rh),
                is_vertical=is_vertical,
                confidence=0.95,
            )
        )

    return results
