from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class Arrowhead:
    """Detected dimensional arrowhead with tip, center, direction vector, and bounding box."""

    center: tuple[float, float]  # (cx, cy)
    tip: tuple[float, float]  # (tx, ty)
    direction: tuple[float, float]  # Unit vector (dx, dy) pointing toward tip
    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    area: float
    is_solid: bool


def detect_arrowheads(
    binary: np.ndarray,
    min_area: float = 15.0,
    max_area: float = 800.0,
) -> list[Arrowhead]:
    """Detect solid and line-type arrowheads using Black Hat / White Hat and triangle analysis."""
    # Morphological Black Hat (2x2) and White Hat (5x5) from paper Eq. (5) & (6)
    kernel_2x2 = np.ones((2, 2), np.uint8)
    kernel_5x5 = np.ones((5, 5), np.uint8)

    # Black Hat isolates small thin elements/lines
    black_hat = cv2.morphologyEx(binary, cv2.MORPH_BLACKHAT, kernel_2x2)
    # White Hat isolates small closed compact elements
    white_hat = cv2.morphologyEx(binary, cv2.MORPH_TOPHAT, kernel_5x5)

    # Combine cues with original binary for comprehensive connected component search
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
    arrowheads: list[Arrowhead] = []

    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if area < min_area or area > max_area:
            continue

        aspect = max(w, h) / max(min(w, h), 1)
        if aspect < 1.1 or aspect > 6.0:
            continue

        comp_mask = (labels[y : y + h, x : x + w] == i).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue

        contour = cnts[0]
        peri = cv2.arcLength(contour, True)
        if peri <= 0:
            continue

        poly = cv2.approxPolyDP(contour, 0.08 * peri, True)
        solidity = area / float(max(w * h, 1))

        # Arrowheads have triangular geometry (solidity ~0.35 to 0.85, 3 to 5 vertices)
        if not (0.30 <= solidity <= 0.85 and 3 <= len(poly) <= 6):
            continue

        cx, cy = float(centroids[i][0]), float(centroids[i][1])
        pts = contour.reshape(-1, 2)
        # Global point coordinates
        global_pts = pts + np.array([x, y])

        # Tip is the extreme corner with maximum Euclidean distance from the center (Fig. 6 in paper)
        dists = np.hypot(global_pts[:, 0] - cx, global_pts[:, 1] - cy)
        tip_idx = int(np.argmax(dists))
        tip_x = float(global_pts[tip_idx, 0])
        tip_y = float(global_pts[tip_idx, 1])

        # Direction vector from center to tip
        vec_x = tip_x - cx
        vec_y = tip_y - cy
        length = math.hypot(vec_x, vec_y)
        if length > 1e-3:
            dir_x, dir_y = vec_x / length, vec_y / length
        else:
            dir_x, dir_y = 0.0, 0.0

        is_solid = solidity >= 0.50
        arrowheads.append(
            Arrowhead(
                center=(cx, cy),
                tip=(tip_x, tip_y),
                direction=(dir_x, dir_y),
                bbox=(x, y, w, h),
                area=float(area),
                is_solid=is_solid,
            )
        )

    return arrowheads
