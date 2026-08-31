from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from core.vision.types import (
    CIRCULARITY_THRESHOLD,
    CONTOUR_SMOOTHING_EPSILON_RATIO,
    CURVE_CONTOUR_MIN_VERTICES,
    CURVE_SMOOTHING_MAX_EPSILON_PX,
    MAX_STROKE_RING_KERNEL_PX,
    STROKE_RING_EROSION_RADIUS_FACTOR,
)


def _stroke_ridge_radii(binary: np.ndarray) -> np.ndarray:
    """Half-width (distance-to-background) sampled at skeleton ridge pixels."""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dilated = cv2.dilate(dist, np.ones((3, 3), np.float32))
    ridge = (dist >= dilated - 1e-6) & (dist > 0)
    return dist[ridge]


def stroke_ring_kernel_px(binary: np.ndarray) -> int:
    """Estimate a kernel size for identifying the two edges of drawn strokes."""
    radii = _stroke_ridge_radii(binary)
    if radii.size == 0:
        return 2
    if float(np.max(radii)) > 12.0:
        return 2
    scaled = np.clip(radii / max(radii.max(), 1e-6) * 255, 0, 255).astype(np.uint8)
    threshold_scaled, _ = cv2.threshold(
        scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    threshold_radius = threshold_scaled / 255.0 * radii.max()
    return min(
        MAX_STROKE_RING_KERNEL_PX,
        max(2, int(round(threshold_radius * 2)) + 1),
    )


def _contour_pair_masks(
    parent_contour: np.ndarray,
    child_contour: np.ndarray,
    image_shape: tuple[int, int],
    pad: int,
) -> tuple[np.ndarray, np.ndarray]:
    x, y, w, h = cv2.boundingRect(parent_contour)
    x0, y0 = max(x - pad, 0), max(y - pad, 0)
    x1 = min(x + w + pad, image_shape[1])
    y1 = min(y + h + pad, image_shape[0])
    offset = (-x0, -y0)
    crop_shape = (max(y1 - y0, 1), max(x1 - x0, 1))
    parent_mask = np.zeros(crop_shape, dtype=np.uint8)
    cv2.drawContours(
        parent_mask, [parent_contour], -1, 255, thickness=cv2.FILLED, offset=offset
    )
    child_mask = np.zeros(crop_shape, dtype=np.uint8)
    cv2.drawContours(
        child_mask, [child_contour], -1, 255, thickness=cv2.FILLED, offset=offset
    )
    return parent_mask, child_mask


def _is_stroke_ring(
    parent_contour: np.ndarray,
    child_contour: np.ndarray,
    image_shape: tuple[int, int],
    kernel_px: int,
) -> bool:
    parent_mask, child_mask = _contour_pair_masks(
        parent_contour, child_contour, image_shape, kernel_px + 2
    )
    wall = cv2.bitwise_and(parent_mask, cv2.bitwise_not(child_mask))
    erosion_radius = kernel_px * STROKE_RING_EROSION_RADIUS_FACTOR
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (erosion_radius * 2 + 1, erosion_radius * 2 + 1)
    )
    eroded_wall = cv2.erode(wall, kernel)
    return cv2.countNonZero(eroded_wall) == 0


def prune_stroke_ring_artifacts(
    contours: list[np.ndarray],
    hierarchy: np.ndarray | None,
    image_shape: tuple[int, int],
    kernel_px: int,
    min_residue_area: float = 0.0,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Collapse redundant inner/outer edges of a single drawn stroke."""
    if hierarchy is None:
        return list(contours), np.empty((1, 0, 4), dtype=np.int32)
    if hierarchy.ndim != 3 or hierarchy.shape != (1, len(contours), 4):
        raise RuntimeError("Error: Invalid contour hierarchy shape.")

    active = {
        index
        for index, contour in enumerate(contours)
        if len(contour) >= 3 and cv2.contourArea(contour) > 0
    }

    def active_parent(index: int) -> int:
        parent = int(hierarchy[0, index, 3])
        visited: set[int] = set()
        while parent != -1 and parent not in active:
            if parent in visited:
                raise RuntimeError(
                    "Error: Detected an invalid loop in the contour hierarchy."
                )
            visited.add(parent)
            parent = int(hierarchy[0, parent, 3])
        return parent

    changed = True
    while changed:
        changed = False
        for index, contour in enumerate(contours):
            if index not in active or len(contour) < 3:
                continue
            parent = active_parent(index)
            is_residue = (
                min_residue_area > 0
                and cv2.contourArea(contour) < min_residue_area
            )
            is_ring = (
                not is_residue
                and parent != -1
                and _is_stroke_ring(contours[parent], contour, image_shape, kernel_px)
            )
            if is_residue or is_ring:
                active.remove(index)
                changed = True

    kept_indices = [index for index in range(len(contours)) if index in active]
    old_to_new = {old: new for new, old in enumerate(kept_indices)}
    rebuilt = np.full((1, len(kept_indices), 4), -1, dtype=np.int32)
    sibling_groups: dict[int, list[int]] = {}
    for old_index in kept_indices:
        new_index = old_to_new[old_index]
        parent = active_parent(old_index)
        new_parent = -1 if parent == -1 else old_to_new[parent]
        rebuilt[0, new_index, 3] = new_parent
        sibling_groups.setdefault(new_parent, []).append(new_index)

    for parent, siblings in sibling_groups.items():
        for position, child in enumerate(siblings):
            rebuilt[0, child, 0] = (
                siblings[position + 1] if position + 1 < len(siblings) else -1
            )
            rebuilt[0, child, 1] = siblings[position - 1] if position else -1
        if parent != -1 and siblings:
            rebuilt[0, parent, 2] = siblings[0]

    return [contours[index] for index in kept_indices], rebuilt


def valid_contour_indices(contours: Sequence[np.ndarray]) -> list[int]:
    return [
        index
        for index, contour in enumerate(contours)
        if len(contour) >= 3 and cv2.contourArea(contour) > 0
    ]


def contour_black_ratio(contour: np.ndarray, binary: np.ndarray) -> float:
    """Return the foreground-pixel ratio enclosed by ``contour``."""
    if binary.ndim != 2:
        raise ValueError("Error: Black-ratio input must be a 2D binary image.")

    x, y, width, height = cv2.boundingRect(contour)
    if width <= 0 or height <= 0:
        return 0.0
    if (
        x < 0
        or y < 0
        or x + width > binary.shape[1]
        or y + height > binary.shape[0]
    ):
        return 0.0

    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.drawContours(
        mask,
        [contour],
        -1,
        255,
        thickness=cv2.FILLED,
        offset=(-x, -y),
    )
    enclosed_pixels = cv2.countNonZero(mask)
    if enclosed_pixels == 0:
        return 0.0

    foreground = cv2.bitwise_and(binary[y : y + height, x : x + width], mask)
    return cv2.countNonZero(foreground) / float(enclosed_pixels)


def contour_circularity(contour: np.ndarray) -> float:
    """Return 4*pi*A/P^2, where 1.0 is an ideal mathematical circle."""
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return 0.0
    area = abs(cv2.contourArea(contour))
    return float((4.0 * math.pi * area) / (perimeter * perimeter))


def fit_circle_ransac(
    contour: np.ndarray,
    max_iterations: int = 150,
    threshold_px: float = 2.5,
    min_inlier_ratio: float = 0.70,
) -> tuple[tuple[float, float], float] | None:
    """Fit a circle using RANSAC to handle circles with leader line arrows or crosshairs."""
    pts = contour.reshape(-1, 2).astype(np.float64)
    n = len(pts)
    if n < 5:
        return None

    best_inliers = 0
    best_circle: tuple[tuple[float, float], float] | None = None

    # Deterministic seed for reproducible testing
    rng = np.random.RandomState(42)

    for _ in range(max_iterations):
        idx = rng.choice(n, 3, replace=False)
        p1, p2, p3 = pts[idx[0]], pts[idx[1]], pts[idx[2]]

        temp = p2[0] ** 2 + p2[1] ** 2
        bc = (p1[0] ** 2 + p1[1] ** 2 - temp) / 2.0
        cd = (temp - p3[0] ** 2 - p3[1] ** 2) / 2.0
        det = (p1[0] - p2[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p2[1])
        if abs(det) < 1e-6:
            continue

        cx = (bc * (p2[1] - p3[1]) - cd * (p1[1] - p2[1])) / det
        cy = ((p1[0] - p2[0]) * cd - (p2[0] - p3[0]) * bc) / det
        radius = math.hypot(cx - p1[0], cy - p1[1])

        if radius < 5.0 or radius > 600.0:
            continue

        dists = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - radius)
        inliers = int(np.sum(dists <= threshold_px))

        if inliers > best_inliers:
            best_inliers = inliers
            best_circle = ((float(cx), float(cy)), float(radius))

    if best_circle is None:
        return None

    if (best_inliers / float(n)) >= min_inlier_ratio:
        return best_circle
    return None


def is_ideal_circle(
    contour: np.ndarray, threshold: float = CIRCULARITY_THRESHOLD
) -> bool:
    if len(contour) < 5:
        return False
    if contour_circularity(contour) > threshold:
        return True
    return fit_circle_ransac(contour) is not None


def smooth_contours(
    contours: Sequence[np.ndarray],
    epsilon_ratio: float = CONTOUR_SMOOTHING_EPSILON_RATIO,
    preserve_indices: Sequence[int] = (),
) -> list[np.ndarray]:
    """Reduce raster stair-stepping while retaining the original contour shape."""
    smoothed_contours: list[np.ndarray] = []
    preserved = set(preserve_indices)
    for index, contour in enumerate(contours):
        if index in preserved:
            smoothed_contours.append(contour)
            continue
        if len(contour) < 3:
            smoothed_contours.append(contour)
            continue
        epsilon = epsilon_ratio * cv2.arcLength(contour, True)
        approx_contour = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx_contour) >= CURVE_CONTOUR_MIN_VERTICES:
            epsilon = min(epsilon, CURVE_SMOOTHING_MAX_EPSILON_PX)
            approx_contour = cv2.approxPolyDP(contour, epsilon, True)
        smoothed_contours.append(approx_contour)
    return smoothed_contours


def extract_contours(
    image_path: Path,
    strip_dimensions: bool = False,
) -> tuple[list[np.ndarray], np.ndarray | None]:
    from core.vision.dimensions import remove_dimension_annotations_from_binary
    from core.vision.loader import load_binary_image

    binary = load_binary_image(image_path)
    if strip_dimensions:
        binary = remove_dimension_annotations_from_binary(binary)
    return _extract_contours_from_binary(binary)


def _extract_contours_from_binary(
    binary: np.ndarray,
) -> tuple[list[np.ndarray], np.ndarray | None]:
    from core.vision.calibration import detect_calibration, is_calibration_square

    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    valid_indices = valid_contour_indices(contours)
    try:
        calibration_index, _ = detect_calibration(
            contours, valid_indices, binary=binary
        )
    except RuntimeError:
        pass
    else:
        sample_binary = binary.copy()
        cv2.drawContours(
            sample_binary,
            contours,
            calibration_index,
            0,
            thickness=cv2.FILLED,
        )
        kernel_px = stroke_ring_kernel_px(sample_binary)
        contours, hierarchy = prune_stroke_ring_artifacts(
            contours,
            hierarchy,
            binary.shape,
            kernel_px,
        )

    calibration_candidates = [
        index
        for index, contour in enumerate(contours)
        if len(contour) >= 3
        and cv2.contourArea(contour) > 0
        and is_calibration_square(contour, binary=binary)
    ]
    contours = smooth_contours(contours, preserve_indices=calibration_candidates)
    return contours, hierarchy
