#!/usr/bin/env python3
"""Convert a dark-on-white 2D drawing image to Fanuc profile G-code."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


CALIBRATION_SIZE_MM = 10.0
ASPECT_RATIO_TOLERANCE = 0.05
MIN_CALIBRATION_SOLIDITY = 0.95
DEFAULT_INPUT_PATH = Path("input") / "input.png"
DEFAULT_OUTPUT_PATH = Path("output") / "output.nc"
MULTIPLE_CALIBRATION_ERROR = (
    "Lỗi: Phát hiện nhiều hơn 1 ô hiệu chuẩn. Vui lòng xóa các hình vuông "
    "trùng lặp hoặc thay đổi hình dáng chi tiết phay để tránh nhầm lẫn"
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
            "Chuyển ảnh bản vẽ 2D nền trắng thành G-code phay biên dạng Fanuc."
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
        raise ValueError("Lỗi: Các tham số số phải là giá trị hữu hạn.")
    if config.cut_depth >= 0:
        raise ValueError("Lỗi: Chiều sâu cắt --cut-depth phải là số âm.")
    if config.plunge_feed <= 0 or config.cut_feed <= 0:
        raise ValueError("Lỗi: Tốc độ chạy dao phải lớn hơn 0.")
    if config.spindle_speed <= 0:
        raise ValueError("Lỗi: Tốc độ trục chính phải lớn hơn 0.")
    if config.tool_number <= 0 or config.tool_offset <= 0:
        raise ValueError("Lỗi: Số dao và offset dao phải lớn hơn 0.")
    if config.program_number <= 0:
        raise ValueError("Lỗi: Số chương trình phải lớn hơn 0.")
    if not config.safe_z > config.approach_z > config.cut_depth:
        raise ValueError(
            "Lỗi: Các cao độ phải thỏa mãn safe-z > approach-z > cut-depth."
        )


def extract_contours(
    image_path: Path,
) -> tuple[list[np.ndarray], np.ndarray | None]:
    if not image_path.is_file():
        raise RuntimeError(f"Lỗi: Không thể đọc ảnh đầu vào: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Lỗi: Không thể đọc ảnh đầu vào: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    return contours, hierarchy


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
        raise RuntimeError("Lỗi: Không tìm thấy ô hiệu chuẩn 10x10 mm.")
    if len(matches) > 1:
        raise RuntimeError(MULTIPLE_CALIBRATION_ERROR)

    calibration_index = matches[0]
    _, _, width, _ = cv2.boundingRect(contours[calibration_index])
    scale_factor = width / CALIBRATION_SIZE_MM
    if not np.isfinite(scale_factor) or scale_factor <= 0:
        raise RuntimeError("Lỗi: Scale Factor của ô hiệu chuẩn không hợp lệ.")
    return calibration_index, scale_factor


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    depth = 0
    parent = int(hierarchy[0, index, 3])
    visited: set[int] = set()
    while parent != -1:
        if parent in visited:
            raise RuntimeError("Lỗi: Phát hiện vòng lặp không hợp lệ trong hierarchy.")
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
            "Lỗi: Không tìm thấy biên dạng gia công sau khi loại ô hiệu chuẩn."
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
        points = transform_contour(
            contours[index], scale_factor, x_min, y_max
        )
        start_x, start_y = points[0]
        lines.extend(
            [
                f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
            ]
        )
        for x_value, y_value in points[1:]:
            lines.append(
                f"G01 X{_format_float(x_value)} "
                f"Y{_format_float(y_value)} F{cut_feed} (Cut)"
            )
        lines.extend(
            [
                f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} "
                f"F{cut_feed} (Close contour)",
                f"G00 Z{safe_z} (Retract)",
            ]
        )

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
    input_path: Path, output_path: Path, config: MachiningConfig
) -> tuple[float, int]:
    validate_config(config)
    contours, hierarchy = extract_contours(input_path)
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
            args.input, args.output, config
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Đã tạo G-code: {args.output}")
    print(f"Scale Factor: {scale_factor:.3f} pixel/mm")
    print(f"Số contour gia công: {contour_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
