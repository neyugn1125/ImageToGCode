#!/usr/bin/env python3
"""Convert images or DXF drawings to Fanuc profile G-code."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import ezdxf

# Re-export all domain modules and components for 100% backward compatibility
from core.config import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_DIRECTORY,
    DEFAULT_OUTPUT_PATH,
    DXF_EXTENSION,
    IMAGE_EXTENSIONS,
    MachiningConfig,
    PipelineResult,
    config_from_args,
    validate_config,
)
from core.pipeline import (
    convert_image_to_gcode,
    create_run_directory,
    dxf_to_gcode,
    process_input,
)
from core.vision import (
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
    Arrowhead,
    DimensionText,
    ImageAnalysisResult,
    ImageCalibration,
    LineSegment,
    analyze_image,
    contour_black_ratio,
    contour_circularity,
    detect_arrowheads,
    detect_calibration,
    detect_dimension_texts,
    detect_hollow_calibration,
    detect_image_calibration,
    detect_lines_and_corners,
    diagrams_net_square_size_mm,
    dimension_stroke_kernel_px,
    extract_contours,
    extract_machining_contours,
    is_calibration_square,
    is_ideal_circle,
    largest_square_contour_extent,
    load_binary_image,
    machining_extent_px,
    prune_stroke_ring_artifacts,
    remove_dimension_annotations,
    remove_dimension_annotations_from_binary,
    scale_factor_from_reference,
    smooth_contours,
    stroke_ring_kernel_px,
    valid_contour_indices,
)
from core.vision.analysis import _extract_machining_contours
from core.vision.calibration import _reference_extent_px, _validate_scale_reference
from core.vision.contours import (
    _contour_pair_masks,
    _extract_contours_from_binary,
    _is_stroke_ring,
    _stroke_ridge_radii,
)
from core.vision.loader import _read_png_text_chunks
from core.cam import (
    auto_correlate_drawing_scale,
    circle_geometry_mm,
    contour_arc_command,
    contour_depth,
    machining_origin,
    order_contours_child_first,
    transform_contour,
)
from core.dxf import (
    _dxf_unit_scale_to_mm,
    _validated_xy,
    image_to_dxf,
)
from core.post import (
    _fanuc_footer,
    _fanuc_header,
    _format_float,
    generate_gcode,
    generate_gcode_from_dxf,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    defaults = MachiningConfig()
    parser = argparse.ArgumentParser(
        description=(
            "Convert a white-background image or a DXF drawing into Fanuc "
            "profile milling G-code."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help=(
            "Root directory for timestamped run folders (default: output). "
            "--output is retained as an alias."
        ),
    )
    parser.add_argument("--cut-depth", type=float, default=defaults.cut_depth)
    parser.add_argument("--plunge-feed", type=float, default=defaults.plunge_feed)
    parser.add_argument("--cut-feed", type=float, default=defaults.cut_feed)
    parser.add_argument("--spindle-speed", type=int, default=defaults.spindle_speed)
    parser.add_argument("--safe-z", type=float, default=defaults.safe_z)
    parser.add_argument("--approach-z", type=float, default=defaults.approach_z)
    parser.add_argument("--tool-number", type=int, default=defaults.tool_number)
    parser.add_argument("--tool-offset", type=int, default=defaults.tool_offset)
    parser.add_argument("--program-number", type=int, default=defaults.program_number)
    parser.add_argument(
        "--reference-width-mm",
        type=float,
        default=None,
        help=(
            "Known width in millimeters of the machining envelope. Use this "
            "for images without embedded scale metadata or a calibration square."
        ),
    )
    parser.add_argument(
        "--reference-height-mm",
        type=float,
        default=None,
        help=(
            "Known height in millimeters of the machining envelope. Use this "
            "for images without embedded scale metadata or a calibration square."
        ),
    )
    parser.add_argument(
        "--pixels-per-mm",
        type=float,
        default=None,
        help="Explicit scale factor in pixels per millimeter.",
    )
    parser.add_argument(
        "--strip-dimensions",
        action="store_true",
        help="Remove dimension lines and drafting annotations before contour detection.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = config_from_args(args)
        result = process_input(
            args.input,
            args.output_dir,
            config,
            reference_width_mm=args.reference_width_mm,
            reference_height_mm=args.reference_height_mm,
            pixels_per_mm=args.pixels_per_mm,
            strip_dimensions=args.strip_dimensions,
        )
    except (OSError, RuntimeError, ValueError, ezdxf.DXFError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Run directory: {result.run_directory}")
    print(f"DXF: {result.dxf_path}")
    print(f"G-code: {result.gcode_path}")
    if result.scale_factor is not None:
        print(f"Scale Factor: {result.scale_factor:.3f} pixel/mm")
    print(f"Machining entities: {result.entity_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
