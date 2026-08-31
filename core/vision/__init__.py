from __future__ import annotations

from core.vision.analysis import (
    analyze_image,
    extract_machining_contours,
)
from core.vision.arrows import (
    Arrowhead,
    detect_arrowheads,
)
from core.vision.calibration import (
    detect_calibration,
    detect_hollow_calibration,
    detect_image_calibration,
    is_calibration_square,
    largest_square_contour_extent,
    machining_extent_px,
    scale_factor_from_reference,
)
from core.vision.contours import (
    contour_black_ratio,
    contour_circularity,
    extract_contours,
    is_ideal_circle,
    prune_stroke_ring_artifacts,
    smooth_contours,
    stroke_ring_kernel_px,
    valid_contour_indices,
)
from core.vision.dimensions import (
    dimension_stroke_kernel_px,
    remove_dimension_annotations,
    remove_dimension_annotations_from_binary,
)
from core.vision.lines import (
    LineSegment,
    detect_lines_and_corners,
)
from core.vision.loader import (
    diagrams_net_square_size_mm,
    load_binary_image,
)
from core.vision.text_detector import (
    DimensionText,
    detect_dimension_texts,
)
from core.vision.types import (
    ASPECT_RATIO_TOLERANCE,
    CALIBRATION_SIZE_MM,
    CIRCULARITY_THRESHOLD,
    CONTOUR_SMOOTHING_EPSILON_RATIO,
    CURVE_CONTOUR_MIN_VERTICES,
    CURVE_SMOOTHING_MAX_EPSILON_PX,
    MAX_DIMENSION_OPEN_KERNEL_PX,
    MAX_STROKE_RING_KERNEL_PX,
    MIN_CALIBRATION_BLACK_RATIO,
    MIN_CALIBRATION_SOLIDITY,
    MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR,
    MULTIPLE_CALIBRATION_ERROR,
    SCALE_REFERENCE_ERROR,
    STROKE_RING_EROSION_RADIUS_FACTOR,
    ImageAnalysisResult,
    ImageCalibration,
)


__all__ = [
    "ASPECT_RATIO_TOLERANCE",
    "Arrowhead",
    "CALIBRATION_SIZE_MM",
    "CIRCULARITY_THRESHOLD",
    "CONTOUR_SMOOTHING_EPSILON_RATIO",
    "CURVE_CONTOUR_MIN_VERTICES",
    "CURVE_SMOOTHING_MAX_EPSILON_PX",
    "DimensionText",
    "ImageAnalysisResult",
    "ImageCalibration",
    "LineSegment",
    "MAX_DIMENSION_OPEN_KERNEL_PX",
    "MAX_STROKE_RING_KERNEL_PX",
    "MIN_CALIBRATION_BLACK_RATIO",
    "MIN_CALIBRATION_SOLIDITY",
    "MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR",
    "MULTIPLE_CALIBRATION_ERROR",
    "SCALE_REFERENCE_ERROR",
    "STROKE_RING_EROSION_RADIUS_FACTOR",
    "analyze_image",
    "contour_black_ratio",
    "contour_circularity",
    "detect_arrowheads",
    "detect_calibration",
    "detect_dimension_texts",
    "detect_hollow_calibration",
    "detect_image_calibration",
    "detect_lines_and_corners",
    "diagrams_net_square_size_mm",
    "dimension_stroke_kernel_px",
    "extract_contours",
    "extract_machining_contours",
    "is_calibration_square",
    "is_ideal_circle",
    "largest_square_contour_extent",
    "load_binary_image",
    "machining_extent_px",
    "prune_stroke_ring_artifacts",
    "remove_dimension_annotations",
    "remove_dimension_annotations_from_binary",
    "scale_factor_from_reference",
    "smooth_contours",
    "stroke_ring_kernel_px",
    "valid_contour_indices",
]
