from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from core.vision.contours import contour_black_ratio, valid_contour_indices
from core.vision.types import (
    ASPECT_RATIO_TOLERANCE,
    CALIBRATION_SIZE_MM,
    MIN_CALIBRATION_BLACK_RATIO,
    MIN_CALIBRATION_SOLIDITY,
    MULTIPLE_CALIBRATION_ERROR,
    ImageCalibration,
)


def is_calibration_square(
    contour: np.ndarray,
    binary: np.ndarray | None = None,
) -> bool:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return False

    polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    if len(polygon) != 4 or not cv2.isContourConvex(polygon):
        return False

    _, _, width, height = cv2.boundingRect(contour)
    if width <= 0 or height <= 0:
        return False

    aspect_ratio = width / height
    if abs(aspect_ratio - 1.0) > ASPECT_RATIO_TOLERANCE:
        return False

    solidity = cv2.contourArea(contour) / float(width * height)
    if solidity < MIN_CALIBRATION_SOLIDITY:
        return False
    return (
        binary is None
        or contour_black_ratio(contour, binary) >= MIN_CALIBRATION_BLACK_RATIO
    )


def detect_calibration(
    contours: Sequence[np.ndarray],
    candidate_indices: Sequence[int],
    *,
    binary: np.ndarray | None = None,
) -> tuple[int, float]:
    matches = [
        index
        for index in candidate_indices
        if is_calibration_square(contours[index], binary=binary)
    ]
    if not matches:
        raise RuntimeError("Error: No 10x10 mm calibration square found.")
    if len(matches) > 1:
        raise RuntimeError(MULTIPLE_CALIBRATION_ERROR)

    calibration_index = matches[0]
    _, _, width, _ = cv2.boundingRect(contours[calibration_index])
    scale_factor = width / CALIBRATION_SIZE_MM
    if not np.isfinite(scale_factor) or scale_factor <= 0:
        raise RuntimeError("Error: Invalid calibration square scale factor.")
    return calibration_index, scale_factor


def detect_hollow_calibration(
    contours: Sequence[np.ndarray],
    hierarchy: np.ndarray | None,
    candidate_indices: Sequence[int] | None = None,
) -> ImageCalibration:
    """Find the bottom-left hollow square and derive its centerline scale."""
    if hierarchy is None or hierarchy.shape != (1, len(contours), 4):
        raise RuntimeError("Error: No hollow 10x10 mm calibration square found.")

    valid = set(
        candidate_indices
        if candidate_indices is not None
        else valid_contour_indices(contours)
    )
    matches: list[tuple[float, int, int, float]] = []
    for outer_index in sorted(valid):
        if int(hierarchy[0, outer_index, 3]) != -1:
            continue
        outer = contours[outer_index]
        if not is_calibration_square(outer):
            continue

        outer_x, outer_y, outer_width, outer_height = cv2.boundingRect(outer)
        child_index = int(hierarchy[0, outer_index, 2])
        while child_index != -1:
            if child_index in valid:
                inner = contours[child_index]
                if is_calibration_square(inner):
                    inner_x, inner_y, inner_width, inner_height = cv2.boundingRect(
                        inner
                    )
                    center_delta_x = abs(
                        (outer_x + outer_width / 2.0)
                        - (inner_x + inner_width / 2.0)
                    )
                    center_delta_y = abs(
                        (outer_y + outer_height / 2.0)
                        - (inner_y + inner_height / 2.0)
                    )
                    center_tolerance = max(2.0, outer_width * 0.08)
                    nested = (
                        0 < inner_width < outer_width
                        and 0 < inner_height < outer_height
                        and center_delta_x <= center_tolerance
                        and center_delta_y <= center_tolerance
                    )
                    if nested:
                        w_outer = float(outer_width)
                        w_inner = float(inner_width)
                        true_width_px = (w_outer + w_inner) / 2.0
                        score = float(outer_x - outer_y)
                        matches.append(
                            (score, outer_index, child_index, true_width_px)
                        )
            child_index = int(hierarchy[0, child_index, 0])

    if not matches:
        raise RuntimeError("Error: No hollow 10x10 mm calibration square found.")

    _score, outer_index, inner_index, true_width_px = min(
        matches, key=lambda match: (match[0], match[1], match[2])
    )
    scale_factor = true_width_px / CALIBRATION_SIZE_MM
    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        raise RuntimeError("Error: Invalid calibration square scale factor.")
    return ImageCalibration(
        outer_index=outer_index,
        excluded_indices=(outer_index, inner_index),
        scale_factor=scale_factor,
    )


def detect_image_calibration(
    contours: Sequence[np.ndarray],
    hierarchy: np.ndarray | None,
    binary: np.ndarray,
) -> ImageCalibration:
    """Select the bottom-left calibration marker from hollow/legacy forms."""
    valid_indices = valid_contour_indices(contours)
    hollow_calibration: ImageCalibration | None = None
    try:
        hollow_calibration = detect_hollow_calibration(
            contours,
            hierarchy,
            valid_indices,
        )
    except RuntimeError as hollow_error:
        if "No hollow" not in str(hollow_error):
            raise

    if hollow_calibration is None:
        calibration_index, scale_factor = detect_calibration(
            contours,
            valid_indices,
            binary=binary,
        )
        return ImageCalibration(
            outer_index=calibration_index,
            excluded_indices=(calibration_index,),
            scale_factor=scale_factor,
        )

    candidates = [hollow_calibration]
    for index in valid_indices:
        if not is_calibration_square(contours[index], binary=binary):
            continue
        _x, _y, width, _height = cv2.boundingRect(contours[index])
        candidates.append(
            ImageCalibration(
                outer_index=index,
                excluded_indices=(index,),
                scale_factor=width / CALIBRATION_SIZE_MM,
            )
        )

    def bottom_left_score(calibration: ImageCalibration) -> tuple[int, int]:
        x_value, y_value, _width, _height = cv2.boundingRect(
            contours[calibration.outer_index]
        )
        return x_value - y_value, calibration.outer_index

    return min(candidates, key=bottom_left_score)


def largest_square_contour_extent(
    contours: Sequence[np.ndarray], contour_indices: Sequence[int]
) -> float | None:
    """Return the pixel extent of the largest near-square machining contour."""
    candidates: list[float] = []
    for index in contour_indices:
        contour = contours[index]
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = contour.reshape(-1, 2)
        width = float(np.max(points[:, 0]) - np.min(points[:, 0]))
        height = float(np.max(points[:, 1]) - np.min(points[:, 1]))
        if width <= 0 or height <= 0 or abs(width / height - 1.0) > ASPECT_RATIO_TOLERANCE:
            continue
        candidates.append(max(width, height))
    return max(candidates) if candidates else None


def _validate_scale_reference(
    reference_width_mm: float | None,
    reference_height_mm: float | None,
    pixels_per_mm: float | None,
) -> None:
    values = (
        ("reference width", reference_width_mm),
        ("reference height", reference_height_mm),
        ("pixels-per-mm", pixels_per_mm),
    )
    for label, value in values:
        if value is not None and (not np.isfinite(value) or value <= 0):
            raise ValueError(f"Error: {label} must be a finite number greater than 0.")
    if pixels_per_mm is not None and (
        reference_width_mm is not None or reference_height_mm is not None
    ):
        raise ValueError(
            "Error: --pixels-per-mm cannot be combined with reference dimensions."
        )


def machining_extent_px(
    contours: Sequence[np.ndarray], contour_indices: Sequence[int]
) -> tuple[float, float]:
    """Return the X/Y pixel envelope of the contours used for machining."""
    if not contour_indices:
        raise RuntimeError("Error: No machining contours found.")
    points = np.vstack([contours[index].reshape(-1, 2) for index in contour_indices])
    width = float(np.max(points[:, 0]) - np.min(points[:, 0]))
    height = float(np.max(points[:, 1]) - np.min(points[:, 1]))
    if width <= 0 or height <= 0:
        raise RuntimeError("Error: Machining contours have an invalid pixel extent.")
    return width, height


def _reference_extent_px(
    contours: Sequence[np.ndarray],
    contour_indices: Sequence[int],
    reference_width_mm: float | None,
    reference_height_mm: float | None,
) -> tuple[float, float]:
    """Choose a matching outer contour when both reference dimensions exist."""
    if reference_width_mm is None or reference_height_mm is None:
        return machining_extent_px(contours, contour_indices)

    target_aspect = reference_width_mm / reference_height_mm
    candidates: list[tuple[float, float, float]] = []
    for index in contour_indices:
        _x, _y, width, height = cv2.boundingRect(contours[index])
        if width <= 0 or height <= 0:
            continue
        aspect = width / height
        if abs(aspect / target_aspect - 1.0) <= ASPECT_RATIO_TOLERANCE:
            candidates.append((float(width * height), float(width - 1), float(height - 1)))
    if candidates:
        _area, width, height = max(candidates)
        return width, height
    return machining_extent_px(contours, contour_indices)


def scale_factor_from_reference(
    contours: Sequence[np.ndarray],
    contour_indices: Sequence[int],
    reference_width_mm: float | None,
    reference_height_mm: float | None,
) -> float:
    """Derive one uniform pixel/mm scale from a known machining envelope."""
    _validate_scale_reference(reference_width_mm, reference_height_mm, None)
    if reference_width_mm is None and reference_height_mm is None:
        raise ValueError(
            "Error: At least one reference dimension is required to derive scale."
        )

    pixel_width, pixel_height = _reference_extent_px(
        contours,
        contour_indices,
        reference_width_mm,
        reference_height_mm,
    )
    ratios: list[float] = []
    if reference_width_mm is not None:
        ratios.append(pixel_width / reference_width_mm)
    if reference_height_mm is not None:
        ratios.append(pixel_height / reference_height_mm)
    if len(ratios) == 2:
        mismatch = abs(ratios[0] - ratios[1]) / max(ratios)
        if mismatch > ASPECT_RATIO_TOLERANCE:
            raise RuntimeError(
                "Error: Reference dimensions do not match the detected machining "
                "envelope (scale differs by more than 5%)."
            )
    scale_factor = sum(ratios) / len(ratios)
    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        raise RuntimeError("Error: Invalid reference scale factor.")
    return scale_factor
