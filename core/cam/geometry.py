from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np


def machining_origin(
    contours: Sequence[np.ndarray], contour_indices: Sequence[int]
) -> tuple[float, float]:
    """Return the pixel X_min and Y_max that map to the G54 datum (X0, Y0)."""
    if not contour_indices:
        raise RuntimeError(
            "Error: No machining contours found after excluding the calibration square."
        )

    all_points = np.vstack(
        [contours[index].reshape(-1, 2) for index in contour_indices]
    )
    x_min = float(np.min(all_points[:, 0]))
    y_max = float(np.max(all_points[:, 1]))
    if not np.all(np.isfinite([x_min, y_max])):
        raise RuntimeError("Error: Calculated machining origin is not finite.")
    return x_min, y_max


def snap_coordinate(
    value: float,
    constraints: Sequence[float],
    tolerance_mm: float = 1.2,
) -> float:
    """Snap a coordinate to the closest matching nominal dimension constraint."""
    for target in constraints:
        if abs(value - target) <= tolerance_mm:
            return float(target)
    return float(value)


def transform_contour(
    contour: np.ndarray,
    scale_factor: float,
    x_min: float,
    y_max: float,
    *,
    snap_constraints_x: Sequence[float] = (),
    snap_constraints_y: Sequence[float] = (),
) -> np.ndarray:
    """Transform pixel contour coordinates to G54 millimeter coordinates."""
    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        raise RuntimeError("Error: Invalid or near-zero scale factor.")
    points = contour.reshape(-1, 2).astype(np.float64)
    transformed = np.empty_like(points)
    # G54 is placed at the bottom-left of the machining-contour bounding box.
    transformed[:, 0] = (points[:, 0] - x_min) / scale_factor
    transformed[:, 1] = (y_max - points[:, 1]) / scale_factor

    if snap_constraints_x:
        transformed[:, 0] = np.array(
            [snap_coordinate(x, snap_constraints_x) for x in transformed[:, 0]],
            dtype=np.float64,
        )
    if snap_constraints_y:
        transformed[:, 1] = np.array(
            [snap_coordinate(y, snap_constraints_y) for y in transformed[:, 1]],
            dtype=np.float64,
        )

    if not np.all(np.isfinite(transformed)):
        raise RuntimeError("Error: Converted contour coordinates are not finite.")
    return transformed


def circle_geometry_mm(
    contour: np.ndarray,
    scale_factor: float,
    x_min: float,
    y_max: float,
    *,
    snap_constraints_x: Sequence[float] = (),
    snap_constraints_y: Sequence[float] = (),
    snap_constraints_r: Sequence[float] = (),
) -> tuple[float, float, float]:
    """Fit an enclosing circle and transform its center/radius to G54 mm with optional snapping."""
    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        raise RuntimeError("Error: Invalid or near-zero scale factor.")
    from core.vision.contours import contour_circularity, fit_circle_ransac

    if contour_circularity(contour) > 0.90:
        (center_x_px, center_y_px), radius_px = cv2.minEnclosingCircle(contour)
    else:
        ransac_fit = fit_circle_ransac(contour)
        if ransac_fit is not None:
            (center_x_px, center_y_px), radius_px = ransac_fit
        else:
            (center_x_px, center_y_px), radius_px = cv2.minEnclosingCircle(contour)

    center_x = (center_x_px - x_min) / scale_factor
    center_y = (y_max - center_y_px) / scale_factor
    radius = radius_px / scale_factor

    if snap_constraints_x:
        center_x = snap_coordinate(center_x, snap_constraints_x)
    if snap_constraints_y:
        center_y = snap_coordinate(center_y, snap_constraints_y)
    if snap_constraints_r:
        radius = snap_coordinate(radius, snap_constraints_r)

    if not np.all(np.isfinite([center_x, center_y, radius])) or radius <= 0:
        raise RuntimeError("Error: Invalid detected circle geometry.")
    return float(center_x), float(center_y), float(radius)


def contour_arc_command(points: np.ndarray) -> str:
    """Preserve contour traversal direction after conversion to machine XY."""
    x_values = points[:, 0]
    y_values = points[:, 1]
    signed_double_area = np.sum(
        x_values * np.roll(y_values, -1) - np.roll(x_values, -1) * y_values
    )
    return "G03" if signed_double_area >= 0 else "G02"
