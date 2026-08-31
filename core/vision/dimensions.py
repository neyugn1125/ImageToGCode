from __future__ import annotations

import cv2
import numpy as np

from core.vision.calibration import detect_image_calibration
from core.vision.contours import _stroke_ridge_radii
from core.vision.types import (
    MAX_DIMENSION_OPEN_KERNEL_PX,
    MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR,
    ImageCalibration,
)


def dimension_stroke_kernel_px(binary: np.ndarray) -> int:
    """Estimate the opening size that removes thin drafting annotations."""
    radii = _stroke_ridge_radii(binary)
    if radii.size == 0:
        return 2
    scaled = np.clip(radii / max(radii.max(), 1e-6) * 255, 0, 255).astype(np.uint8)
    threshold_scaled, _ = cv2.threshold(
        scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    threshold_radius = threshold_scaled / 255.0 * radii.max()
    return min(
        MAX_DIMENSION_OPEN_KERNEL_PX,
        max(2, int(round(threshold_radius * 2)) + 1),
    )


def remove_dimension_annotations(binary: np.ndarray, kernel_px: int) -> np.ndarray:
    """Remove strokes thinner than the detected part-outline strokes."""
    kernel_px = max(2, int(kernel_px))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_px, kernel_px)
    )
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)


def remove_dimension_annotations_from_binary(binary: np.ndarray) -> np.ndarray:
    """Strip annotations while preserving a detected calibration marker."""
    raw_contours, raw_hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    calibration: ImageCalibration | None = None
    try:
        calibration = detect_image_calibration(raw_contours, raw_hierarchy, binary)
    except RuntimeError as error:
        if "No 10x10 mm calibration square" not in str(error):
            raise

    sample_binary = binary.copy()
    if calibration is not None:
        cv2.drawContours(
            sample_binary,
            raw_contours,
            calibration.outer_index,
            0,
            thickness=cv2.FILLED,
        )
    kernel_px = dimension_stroke_kernel_px(sample_binary)
    cleaned = remove_dimension_annotations(binary, kernel_px)
    contours, hierarchy = cv2.findContours(
        cleaned, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    min_residue_area = (kernel_px**2) * MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR
    annotation_short_side = max(8, 2 * kernel_px)
    for index, contour in enumerate(contours):
        _x, _y, width, height = cv2.boundingRect(contour)
        short_side = min(width, height)
        long_side = max(width, height)
        dimension_like = (
            short_side > 0
            and short_side <= annotation_short_side
            and long_side / short_side >= 12.0
            and int(hierarchy[0, index, 3]) == -1
        )
        residue = cv2.contourArea(contour) < min_residue_area
        if residue or dimension_like:
            cv2.drawContours(cleaned, [contour], -1, 0, thickness=cv2.FILLED)

    root_indices = [
        index
        for index, contour in enumerate(contours)
        if int(hierarchy[0, index, 3]) == -1 and cv2.contourArea(contour) > 0
    ]
    if root_indices:
        primary = max(root_indices, key=lambda index: cv2.contourArea(contours[index]))
        primary_area = cv2.contourArea(contours[primary])
        secondary_area = max(
            (cv2.contourArea(contours[index]) for index in root_indices if index != primary),
            default=0.0,
        )
        has_children = int(hierarchy[0, primary, 2]) != -1
        if has_children and primary_area >= 10.0 * max(secondary_area, 1.0):
            primary_x, primary_y, primary_width, primary_height = cv2.boundingRect(
                contours[primary]
            )
            primary_right = primary_x + primary_width
            primary_bottom = primary_y + primary_height
            for index in root_indices:
                if index == primary:
                    continue
                x, y, width, height = cv2.boundingRect(contours[index])
                inside_primary = (
                    x >= primary_x
                    and y >= primary_y
                    and x + width <= primary_right
                    and y + height <= primary_bottom
                )
                if not inside_primary:
                    cv2.drawContours(cleaned, [contours[index]], -1, 0, thickness=cv2.FILLED)
    return cleaned
