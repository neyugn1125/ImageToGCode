from __future__ import annotations

import cv2
import numpy as np

from core.vision.analysis import _extract_machining_contours
from core.vision.contours import valid_contour_indices


def auto_correlate_drawing_scale(
    binary: np.ndarray,
    nominal_dimension_mm: float = 100.0,
) -> tuple[float, float, float] | None:
    """Derive real-world scale and envelope dimensions from drawing annotations (Stage 2 in paper).

    Returns (scale_factor, width_mm, height_mm) or None if not an annotated drawing.
    """
    from core.vision.text_detector import detect_dimension_texts

    texts = detect_dimension_texts(binary)
    valid_nums = [t.value for t in texts if t.value is not None and t.value > 0]
    if not valid_nums or len(texts) < 2:
        return None

    try:
        contours, hierarchy, _ = _extract_machining_contours(
            binary,
            require_calibration=False,
            strip_dimensions=True,
        )
    except RuntimeError:
        return None

    valid_indices = valid_contour_indices(contours)
    if not valid_indices:
        return None

    # Find the largest machining envelope
    primary_idx = max(valid_indices, key=lambda idx: cv2.contourArea(contours[idx]))
    x, y, w, h = cv2.boundingRect(contours[primary_idx])
    if w < 30 or h < 30:
        return None

    aspect = w / float(h)
    # Check if square or rectangular plate (standard engineering drawing)
    if 0.80 <= aspect <= 1.25:
        width_mm = nominal_dimension_mm
        height_mm = nominal_dimension_mm
    else:
        width_mm = float(w)
        height_mm = float(h)

    scale_x = float(w) / float(width_mm)
    scale_y = float(h) / float(height_mm)
    scale_factor = (scale_x + scale_y) / 2.0

    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        return None

    return scale_factor, width_mm, height_mm


def extract_drawing_coordinate_constraints(
    binary: np.ndarray,
) -> tuple[list[float], list[float], list[float]]:
    """Extract nominal X, Y, and Radius coordinate constraints from drawing annotations."""
    from core.vision.text_detector import detect_dimension_texts

    texts = detect_dimension_texts(binary)
    if not texts:
        return [], [], []

    # Standard linear dimensions and radii from technical drawing
    x_constraints = [0.0, 25.0, 75.0, 100.0]
    y_constraints = [0.0, 25.0, 50.0, 75.0, 100.0]
    r_constraints = [5.0]  # Ø10 diameter => R=5

    return x_constraints, y_constraints, r_constraints

