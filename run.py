#!/usr/bin/env python3
"""Convert a dark-on-white 2D drawing image to Fanuc profile G-code."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


CALIBRATION_SIZE_MM = 10.0
ASPECT_RATIO_TOLERANCE = 0.05
MIN_CALIBRATION_SOLIDITY = 0.95
CIRCULARITY_THRESHOLD = 0.88
CONTOUR_SMOOTHING_EPSILON_RATIO = 0.001
DEFAULT_INPUT_PATH = Path("input") / "input.png"
DEFAULT_OUTPUT_PATH = Path("output") / "output.nc"
MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR = 16
MULTIPLE_CALIBRATION_ERROR = (
    "Error: Detected more than 1 calibration square. Please remove the "
    "duplicate squares or change the part geometry to avoid ambiguity."
)


@dataclass(frozen=True)
class MachiningConfig:
    """Machining values used to render the Fanuc program."""

    cut_depth: float = -5.0
    plunge_feed: float = 100.0
    cut_feed: float = 300.0
    spindle_speed: int = 1500
    safe_z: float = 50.0
    approach_z: float = 2.0
    tool_number: int = 1
    tool_offset: int = 1
    program_number: int = 1000


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a white-background 2D drawing image into Fanuc profile "
            "milling G-code."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--cut-depth", type=float, default=-5.0)
    parser.add_argument("--plunge-feed", type=float, default=100.0)
    parser.add_argument("--cut-feed", type=float, default=300.0)
    parser.add_argument("--spindle-speed", type=int, default=1500)
    parser.add_argument("--safe-z", type=float, default=50.0)
    parser.add_argument("--approach-z", type=float, default=2.0)
    parser.add_argument("--tool-number", type=int, default=1)
    parser.add_argument("--tool-offset", type=int, default=1)
    parser.add_argument("--program-number", type=int, default=1000)
    parser.add_argument(
        "--strip-dimensions",
        action="store_true",
        help=(
            "Remove dimension lines, extension lines, arrows and text that are "
            "thinner than the part outline before extracting contours."
        ),
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> MachiningConfig:
    return MachiningConfig(
        cut_depth=args.cut_depth,
        plunge_feed=args.plunge_feed,
        cut_feed=args.cut_feed,
        spindle_speed=args.spindle_speed,
        safe_z=args.safe_z,
        approach_z=args.approach_z,
        tool_number=args.tool_number,
        tool_offset=args.tool_offset,
        program_number=args.program_number,
    )


def validate_config(config: MachiningConfig) -> None:
    numeric_values = (
        config.cut_depth,
        config.plunge_feed,
        config.cut_feed,
        config.safe_z,
        config.approach_z,
    )
    if not all(np.isfinite(value) for value in numeric_values):
        raise ValueError("Error: Numeric parameters must be finite values.")
    if config.cut_depth >= 0:
        raise ValueError("Error: --cut-depth must be a negative number.")
    if config.plunge_feed <= 0 or config.cut_feed <= 0:
        raise ValueError("Error: Feed rates must be greater than 0.")
    if config.spindle_speed <= 0:
        raise ValueError("Error: Spindle speed must be greater than 0.")
    if config.tool_number <= 0 or config.tool_offset <= 0:
        raise ValueError("Error: Tool number and tool offset must be greater than 0.")
    if config.program_number <= 0:
        raise ValueError("Error: Program number must be greater than 0.")
    if not config.safe_z > config.approach_z > config.cut_depth:
        raise ValueError(
            "Error: Heights must satisfy safe-z > approach-z > cut-depth."
        )


def extract_contours(
    image_path: Path,
    strip_dimensions: bool = False,
) -> tuple[list[np.ndarray], np.ndarray | None]:
    if not image_path.is_file():
        raise RuntimeError(f"Error: Unable to read input image: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Error: Unable to read input image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    if strip_dimensions:
        # The calibration square is solid, so its own stroke "width" (half its
        # side length) is far larger than either annotation or outline
        # strokes; left in, it skews the Otsu split away from the boundary we
        # actually want. Exclude it from the sample, not from the strip pass.
        raw_contours, _ = cv2.findContours(
            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        raw_valid = valid_contour_indices(raw_contours)
        calibration_index, _ = detect_calibration(raw_contours, raw_valid)
        sample_binary = binary.copy()
        cv2.drawContours(
            sample_binary, raw_contours, calibration_index, 0, thickness=cv2.FILLED
        )
        kernel_px = dimension_stroke_kernel_px(sample_binary)
        cleaned = remove_dimension_annotations(binary, kernel_px)
        contours, hierarchy = cv2.findContours(
            cleaned, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        min_residue_area = (kernel_px**2) * MIN_DIMENSION_RESIDUE_AREA_PX_FACTOR
        contours = prune_stroke_ring_artifacts(
            contours, hierarchy, cleaned.shape, kernel_px, min_residue_area
        )
    else:
        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

    contours = smooth_contours(contours)
    return contours, hierarchy


def smooth_contours(
    contours: Sequence[np.ndarray],
    epsilon_ratio: float = CONTOUR_SMOOTHING_EPSILON_RATIO,
) -> list[np.ndarray]:
    """Reduce raster stair-stepping while retaining the original contour shape."""
    smoothed_contours: list[np.ndarray] = []
    for contour in contours:
        if len(contour) < 3:
            # Degenerate placeholder left by prune_stroke_ring_artifacts, or a
            # stray raster speck; valid_contour_indices() filters these out.
            smoothed_contours.append(contour)
            continue
        # 0.1% of the perimeter preserves curves while removing small pixel steps.
        epsilon = epsilon_ratio * cv2.arcLength(contour, True)
        approx_contour = cv2.approxPolyDP(contour, epsilon, True)
        smoothed_contours.append(approx_contour)
    return smoothed_contours


def _stroke_ridge_radii(binary: np.ndarray) -> np.ndarray:
    """Half-width (distance-to-background) sampled at skeleton ridge pixels,
    one representative value per stroke rather than per pixel, so long thin
    lines don't dominate a per-pixel histogram over short thick ones."""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dilated = cv2.dilate(dist, np.ones((3, 3), np.float32))
    ridge = (dist >= dilated - 1e-6) & (dist > 0)
    return dist[ridge]


def dimension_stroke_kernel_px(binary: np.ndarray) -> int:
    """Pick a structuring-element size that separates thin dimension/extension
    lines, arrows and text from the thicker part-outline strokes, using the
    drawing's own stroke half-width distribution (ISO drafting convention:
    visible outlines are drawn noticeably thicker than annotation lines)."""
    radii = _stroke_ridge_radii(binary)
    if radii.size == 0:
        return 2
    scaled = np.clip(radii / max(radii.max(), 1e-6) * 255, 0, 255).astype(np.uint8)
    threshold_scaled, _ = cv2.threshold(
        scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    threshold_radius = threshold_scaled / 255.0 * radii.max()
    # +1px margin: the Otsu split sits right at the annotation stroke's own
    # width, which isn't quite enough to fully erase it.
    return max(2, int(round(threshold_radius * 2)) + 1)


def remove_dimension_annotations(binary: np.ndarray, kernel_px: int) -> np.ndarray:
    """Strip dimension lines, extension lines, arrowheads and text that are
    thinner than the part outline strokes, leaving only the part geometry."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)


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
    """True if `child` is just the inner edge of the same drawn stroke as
    `parent` (an unfilled outline's line thickness), rather than a real
    material wall around a genuine hole."""
    parent_mask, child_mask = _contour_pair_masks(
        parent_contour, child_contour, image_shape, kernel_px + 2
    )
    wall = cv2.bitwise_and(parent_mask, cv2.bitwise_not(child_mask))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_px * 2 + 1, kernel_px * 2 + 1)
    )
    eroded_wall = cv2.erode(wall, kernel)
    return cv2.countNonZero(eroded_wall) == 0


def prune_stroke_ring_artifacts(
    contours: list[np.ndarray],
    hierarchy: np.ndarray | None,
    image_shape: tuple[int, int],
    kernel_px: int,
    min_residue_area: float,
) -> list[np.ndarray]:
    """Collapse redundant inner/outer edges of a single drawn stroke (typical
    of unfilled, outline-style CAD line art) and drop tiny leftover specks
    from stripped annotations, so each real feature keeps exactly one
    contour and the material/void depth alternation the rest of the
    pipeline relies on is restored."""
    if hierarchy is None or not contours:
        return list(contours)

    pruned = list(contours)
    excluded: set[int] = set()
    changed = True
    while changed:
        changed = False
        for index, contour in enumerate(pruned):
            if index in excluded or len(contour) < 3:
                continue
            parent = int(hierarchy[0, index, 3])
            while parent in excluded:
                parent = int(hierarchy[0, parent, 3])
            area = cv2.contourArea(contour)
            is_residue = area < min_residue_area
            is_ring = (
                not is_residue
                and parent != -1
                and _is_stroke_ring(pruned[parent], contour, image_shape, kernel_px)
            )
            if is_residue or is_ring:
                for child_index in range(len(pruned)):
                    if (
                        child_index not in excluded
                        and int(hierarchy[0, child_index, 3]) == index
                    ):
                        hierarchy[0, child_index, 3] = parent
                excluded.add(index)
                pruned[index] = np.empty((0, 1, 2), dtype=contour.dtype)
                changed = True
    return pruned


def valid_contour_indices(contours: Sequence[np.ndarray]) -> list[int]:
    return [
        index
        for index, contour in enumerate(contours)
        if len(contour) >= 3 and cv2.contourArea(contour) > 0
    ]


def is_calibration_square(contour: np.ndarray) -> bool:
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

    # A solid, axis-aligned square nearly fills its bounding rectangle.
    solidity = cv2.contourArea(contour) / float(width * height)
    return solidity >= MIN_CALIBRATION_SOLIDITY


def detect_calibration(
    contours: Sequence[np.ndarray], candidate_indices: Sequence[int]
) -> tuple[int, float]:
    matches = [
        index
        for index in candidate_indices
        if is_calibration_square(contours[index])
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


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    depth = 0
    parent = int(hierarchy[0, index, 3])
    visited: set[int] = set()
    while parent != -1:
        if parent in visited:
            raise RuntimeError("Error: Detected an invalid loop in the contour hierarchy.")
        visited.add(parent)
        depth += 1
        parent = int(hierarchy[0, parent, 3])
    return depth


def order_contours_child_first(
    contour_indices: Sequence[int], hierarchy: np.ndarray | None
) -> list[int]:
    if hierarchy is None:
        return list(contour_indices)
    # Python's stable sort preserves OpenCV order among contours at equal depth.
    return sorted(
        contour_indices,
        key=lambda index: -contour_depth(index, hierarchy),
    )


def machining_origin(
    contours: Sequence[np.ndarray], contour_indices: Sequence[int]
) -> tuple[float, float]:
    if not contour_indices:
        raise RuntimeError(
            "Error: No machining contours found after excluding the calibration square."
        )

    all_points = np.vstack(
        [contours[index].reshape(-1, 2) for index in contour_indices]
    )
    x_min = float(np.min(all_points[:, 0]))
    y_max = float(np.max(all_points[:, 1]))
    return x_min, y_max


def transform_contour(
    contour: np.ndarray, scale_factor: float, x_min: float, y_max: float
) -> np.ndarray:
    points = contour.reshape(-1, 2).astype(np.float64)
    transformed = np.empty_like(points)
    # G54 is placed at the bottom-left of the machining-contour bounding box.
    transformed[:, 0] = (points[:, 0] - x_min) / scale_factor
    transformed[:, 1] = (y_max - points[:, 1]) / scale_factor
    return transformed


def contour_circularity(contour: np.ndarray) -> float:
    """Return 4*pi*A/P^2, where 1.0 is an ideal mathematical circle."""
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return 0.0
    area = abs(cv2.contourArea(contour))
    return float((4.0 * math.pi * area) / (perimeter * perimeter))


def is_ideal_circle(
    contour: np.ndarray, threshold: float = CIRCULARITY_THRESHOLD
) -> bool:
    return contour_circularity(contour) > threshold


def circle_geometry_mm(
    contour: np.ndarray, scale_factor: float, x_min: float, y_max: float
) -> tuple[float, float, float]:
    """Fit an enclosing circle and transform its center/radius to G54 mm."""
    (center_x_px, center_y_px), radius_px = cv2.minEnclosingCircle(contour)
    center_x = (center_x_px - x_min) / scale_factor
    center_y = (y_max - center_y_px) / scale_factor
    radius = radius_px / scale_factor
    if not np.all(np.isfinite([center_x, center_y, radius])) or radius <= 0:
        raise RuntimeError("Error: Invalid detected circle geometry.")
    return float(center_x), float(center_y), float(radius)


def _format_float(value: float) -> str:
    # Avoid emitting confusing negative zero after coordinate conversion.
    if abs(value) < 0.0005:
        value = 0.0
    return f"{value:.3f}"


def generate_gcode(
    contours: Sequence[np.ndarray],
    ordered_indices: Sequence[int],
    scale_factor: float,
    x_min: float,
    y_max: float,
    config: MachiningConfig,
) -> str:
    safe_z = _format_float(config.safe_z)
    approach_z = _format_float(config.approach_z)
    cut_depth = _format_float(config.cut_depth)
    plunge_feed = _format_float(config.plunge_feed)
    cut_feed = _format_float(config.cut_feed)

    lines = [
        f"O{config.program_number} (Profile Milling)",
        "G21 (Metric)",
        "G90 (Absolute positioning)",
        "G54 (Workpiece coordinate system)",
        f"G00 Z{safe_z} (Safe Z)",
        f"T{config.tool_number} M06 (Tool change to T{config.tool_number})",
        f"G43 H{config.tool_offset} (Tool length compensation)",
        (
            f"M03 S{config.spindle_speed} "
            f"(Spindle ON, {config.spindle_speed} RPM)"
        ),
        "M08 (Coolant ON)",
    ]

    for index in ordered_indices:
        contour = contours[index]
        points = transform_contour(contour, scale_factor, x_min, y_max)
        ideal_circle = is_ideal_circle(contour)
        if ideal_circle:
            center_x, center_y, radius = circle_geometry_mm(
                contour, scale_factor, x_min, y_max
            )
            start_x = center_x + radius
            start_y = center_y
        else:
            start_x, start_y = points[0]
        lines.extend(
            [
                f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
            ]
        )
        if ideal_circle:
            opposite_x = center_x - radius
            lines.extend(
                [
                    f"G02 X{_format_float(opposite_x)} "
                    f"Y{_format_float(center_y)} I{_format_float(-radius)} "
                    f"J0.000 F{cut_feed} (Circle half 1)",
                    f"G02 X{_format_float(start_x)} "
                    f"Y{_format_float(start_y)} I{_format_float(radius)} "
                    f"J0.000 F{cut_feed} (Close contour)",
                ]
            )
        else:
            for x_value, y_value in points[1:]:
                lines.append(
                    f"G01 X{_format_float(x_value)} "
                    f"Y{_format_float(y_value)} F{cut_feed} (Cut)"
                )
            lines.append(
                f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} "
                f"F{cut_feed} (Close contour)"
            )
        lines.append(f"G00 Z{safe_z} (Retract)")

    lines.extend(
        [
            f"G00 Z{safe_z}",
            "G28 X0 Y0 (Return to reference point)",
            "M09 (Coolant OFF)",
            "M05 (Spindle OFF)",
            "M30 (End of program)",
        ]
    )
    return "\n".join(lines) + "\n"


def convert_image_to_gcode(
    input_path: Path,
    output_path: Path,
    config: MachiningConfig,
    strip_dimensions: bool = False,
) -> tuple[float, int]:
    validate_config(config)
    contours, hierarchy = extract_contours(input_path, strip_dimensions=strip_dimensions)
    valid_indices = valid_contour_indices(contours)
    calibration_index, scale_factor = detect_calibration(
        contours, valid_indices
    )
    machining_indices = [
        index for index in valid_indices if index != calibration_index
    ]
    x_min, y_max = machining_origin(contours, machining_indices)
    ordered_indices = order_contours_child_first(machining_indices, hierarchy)
    gcode = generate_gcode(
        contours,
        ordered_indices,
        scale_factor,
        x_min,
        y_max,
        config,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gcode, encoding="ascii")
    return scale_factor, len(ordered_indices)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = config_from_args(args)
        scale_factor, contour_count = convert_image_to_gcode(
            args.input, args.output, config, strip_dimensions=args.strip_dimensions
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Generated G-code: {args.output}")
    print(f"Scale Factor: {scale_factor:.3f} pixel/mm")
    print(f"Machining contours: {contour_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
