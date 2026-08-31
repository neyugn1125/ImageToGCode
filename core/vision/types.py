from __future__ import annotations

from dataclasses import dataclass


CALIBRATION_SIZE_MM = 10.0
ASPECT_RATIO_TOLERANCE = 0.05
MIN_CALIBRATION_SOLIDITY = 0.95
MIN_CALIBRATION_BLACK_RATIO = 0.75
CIRCULARITY_THRESHOLD = 0.88
CONTOUR_SMOOTHING_EPSILON_RATIO = 0.005
CURVE_SMOOTHING_MAX_EPSILON_PX = 1.0
CURVE_CONTOUR_MIN_VERTICES = 8
STROKE_RING_EROSION_RADIUS_FACTOR = 2
MAX_STROKE_RING_KERNEL_PX = 7
MAX_DIMENSION_OPEN_KERNEL_PX = 7
MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR = 16

MULTIPLE_CALIBRATION_ERROR = (
    "Error: Detected more than 1 calibration square. Please remove the "
    "duplicate squares or change the part geometry to avoid ambiguity."
)
SCALE_REFERENCE_ERROR = (
    "Error: Unable to determine physical scale. Provide "
    "--reference-width-mm/--reference-height-mm, --pixels-per-mm, "
    "or add a 10x10 mm calibration square."
)


@dataclass(frozen=True)
class ImageCalibration:
    """Calibration geometry found in the source raster image."""

    outer_index: int
    excluded_indices: tuple[int, ...]
    scale_factor: float


@dataclass(frozen=True)
class ImageAnalysisResult:
    """Detection and coordinate metadata extracted from an input image."""

    image_shape: tuple[int, int]
    calibration_bbox_px: tuple[int, int, int, int] | None
    scale_factor: float | None
    g54_origin_px: tuple[float, float] | None
    machining_bbox_px: tuple[float, float, float, float] | None
    contour_count: int
