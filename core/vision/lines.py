from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class LineSegment:
    """Detected 2D line segment in image coordinates."""

    start: tuple[float, float]  # (x1, y1)
    end: tuple[float, float]  # (x2, y2)
    length: float
    is_horizontal: bool
    is_vertical: bool
    thickness: float


def detect_lines_and_corners(
    binary: np.ndarray,
    min_length: float = 15.0,
    corner_quality: float = 0.02,
) -> tuple[list[LineSegment], list[tuple[float, float]]]:
    """Detect line segments and Harris corners as described in paper Eq. (9) to (12)."""
    # Harris corners (Eq. 9-10 in paper)
    corners_raw = cv2.goodFeaturesToTrack(
        binary,
        maxCorners=100,
        qualityLevel=corner_quality,
        minDistance=10,
        useHarrisDetector=True,
        k=0.04,
    )
    corners: list[tuple[float, float]] = []
    if corners_raw is not None:
        corners = [(float(pt[0, 0]), float(pt[0, 1])) for pt in corners_raw]

    # Morphological line separation (Horizontal & Vertical kernels)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 20))
    lines_h_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
    lines_v_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_v)

    line_segments: list[LineSegment] = []

    # Hough Lines on horizontal mask
    h_lines = cv2.HoughLinesP(
        lines_h_mask,
        rho=1,
        theta=np.pi / 180,
        threshold=30,
        minLineLength=int(min_length),
        maxLineGap=12,
    )
    if h_lines is not None:
        for line in h_lines:
            x1, y1, x2, y2 = line[0]
            length = math.hypot(x2 - x1, y2 - y1)
            if length >= min_length:
                line_segments.append(
                    LineSegment(
                        start=(float(min(x1, x2)), float(y1)),
                        end=(float(max(x1, x2)), float(y2)),
                        length=float(length),
                        is_horizontal=True,
                        is_vertical=False,
                        thickness=1.5,
                    )
                )

    # Hough Lines on vertical mask
    v_lines = cv2.HoughLinesP(
        lines_v_mask,
        rho=1,
        theta=np.pi / 180,
        threshold=30,
        minLineLength=int(min_length),
        maxLineGap=12,
    )
    if v_lines is not None:
        for line in v_lines:
            x1, y1, x2, y2 = line[0]
            length = math.hypot(x2 - x1, y2 - y1)
            if length >= min_length:
                line_segments.append(
                    LineSegment(
                        start=(float(x1), float(min(y1, y2))),
                        end=(float(x2), float(max(y1, y2))),
                        length=float(length),
                        is_horizontal=False,
                        is_vertical=True,
                        thickness=1.5,
                    )
                )

    return line_segments, corners
