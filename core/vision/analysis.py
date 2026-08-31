from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.vision.calibration import (
    _validate_scale_reference,
    detect_image_calibration,
    largest_square_contour_extent,
    scale_factor_from_reference,
)
from core.vision.contours import (
    prune_stroke_ring_artifacts,
    smooth_contours,
    stroke_ring_kernel_px,
    valid_contour_indices,
)
from core.vision.dimensions import remove_dimension_annotations_from_binary
from core.vision.loader import diagrams_net_square_size_mm, load_binary_image
from core.vision.types import ImageAnalysisResult, ImageCalibration


def _extract_machining_contours(
    binary: np.ndarray,
    *,
    require_calibration: bool,
    strip_dimensions: bool = False,
) -> tuple[list[np.ndarray], np.ndarray | None, ImageCalibration | None]:
    raw_contours, raw_hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    try:
        calibration = detect_image_calibration(raw_contours, raw_hierarchy, binary)
    except RuntimeError as error:
        if require_calibration or "No 10x10 mm calibration square" not in str(error):
            raise
        calibration = None

    machining_binary = (
        remove_dimension_annotations_from_binary(binary)
        if strip_dimensions
        else binary.copy()
    )
    if calibration is not None:
        cv2.drawContours(
            machining_binary,
            raw_contours,
            calibration.outer_index,
            0,
            thickness=cv2.FILLED,
        )
    contours, hierarchy = cv2.findContours(
        machining_binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    kernel_px = stroke_ring_kernel_px(machining_binary)
    contours, hierarchy = prune_stroke_ring_artifacts(
        contours,
        hierarchy,
        machining_binary.shape,
        kernel_px,
    )
    contours = smooth_contours(contours)
    if not valid_contour_indices(contours):
        raise RuntimeError(
            "Error: No machining contours found after preprocessing the image."
        )
    return contours, hierarchy, calibration


def extract_machining_contours(
    binary: np.ndarray,
    *,
    strip_dimensions: bool = False,
) -> tuple[list[np.ndarray], np.ndarray | None, ImageCalibration | None]:
    """Prepare closed machining contours, optionally without a calibration marker."""
    return _extract_machining_contours(
        binary,
        require_calibration=True,
        strip_dimensions=strip_dimensions,
    )


def analyze_image(
    image_path: Path,
    *,
    strip_dimensions: bool = False,
    reference_width_mm: float | None = None,
    reference_height_mm: float | None = None,
    pixels_per_mm: float | None = None,
) -> ImageAnalysisResult:
    """Analyze image geometries (calibration, envelope, G54 origin) without creating files."""
    _validate_scale_reference(reference_width_mm, reference_height_mm, pixels_per_mm)
    raw_image = cv2.imread(str(image_path))
    if raw_image is None:
        raise RuntimeError(f"Error: Unable to read input image: {image_path}")
    img_h, img_w = raw_image.shape[:2]
    binary = load_binary_image(image_path)

    raw_contours, raw_hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    calibration: ImageCalibration | None = None
    try:
        calibration = detect_image_calibration(raw_contours, raw_hierarchy, binary)
    except RuntimeError:
        calibration = None

    cal_bbox: tuple[int, int, int, int] | None = None
    if calibration is not None:
        cx, cy, cw, ch = cv2.boundingRect(raw_contours[calibration.outer_index])
        cal_bbox = (int(cx), int(cy), int(cw), int(ch))

    try:
        contours, _hierarchy, _ = _extract_machining_contours(
            binary,
            require_calibration=False,
            strip_dimensions=strip_dimensions,
        )
    except RuntimeError:
        contours = []

    valid_indices = valid_contour_indices(contours)

    scale_factor: float | None = None
    if pixels_per_mm is not None and pixels_per_mm > 0:
        scale_factor = pixels_per_mm
    elif (reference_width_mm is not None or reference_height_mm is not None) and valid_indices:
        try:
            scale_factor = scale_factor_from_reference(
                contours,
                valid_indices,
                reference_width_mm,
                reference_height_mm,
            )
        except (RuntimeError, ValueError):
            pass

    if scale_factor is None:
        reference_size_mm = diagrams_net_square_size_mm(image_path)
        if reference_size_mm is not None and valid_indices:
            ref_extent = largest_square_contour_extent(contours, valid_indices)
            if ref_extent is not None and reference_size_mm > 0:
                scale_factor = ref_extent / reference_size_mm

    if scale_factor is None and calibration is not None:
        scale_factor = calibration.scale_factor

    if scale_factor is None and calibration is None:
        from core.cam.correlation import auto_correlate_drawing_scale

        correlated = auto_correlate_drawing_scale(binary)
        if correlated is not None:
            scale_factor, _, _ = correlated
            if not strip_dimensions:
                try:
                    contours, _hierarchy, _ = _extract_machining_contours(
                        binary,
                        require_calibration=False,
                        strip_dimensions=True,
                    )
                    valid_indices = valid_contour_indices(contours)
                except RuntimeError:
                    pass

    g54_origin: tuple[float, float] | None = None
    machining_bbox: tuple[float, float, float, float] | None = None
    if valid_indices:
        try:
            from core.cam.geometry import machining_origin

            x_min, y_max = machining_origin(contours, valid_indices)
            g54_origin = (x_min, y_max)
            all_points = np.vstack([contours[idx].reshape(-1, 2) for idx in valid_indices])
            min_x = float(np.min(all_points[:, 0]))
            min_y = float(np.min(all_points[:, 1]))
            max_x = float(np.max(all_points[:, 0]))
            max_y = float(np.max(all_points[:, 1]))
            machining_bbox = (min_x, min_y, max_x, max_y)
        except RuntimeError:
            pass

    return ImageAnalysisResult(
        image_shape=(img_h, img_w),
        calibration_bbox_px=cal_bbox,
        scale_factor=scale_factor,
        g54_origin_px=g54_origin,
        machining_bbox_px=machining_bbox,
        contour_count=len(valid_indices),
    )
