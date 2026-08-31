from __future__ import annotations

import math
from typing import Sequence

import ezdxf
import numpy as np

from core.cam.geometry import (
    circle_geometry_mm,
    contour_arc_command,
    transform_contour,
)
from core.config import MachiningConfig, validate_config
from core.dxf.reader import _dxf_unit_scale_to_mm, _validated_xy
from core.vision.contours import is_ideal_circle


def _format_float(value: float) -> str:
    if abs(value) < 0.0005:
        value = 0.0
    return f"{value:.3f}"


def _fanuc_header(config: MachiningConfig) -> list[str]:
    safe_z = _format_float(config.safe_z)
    return [
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


def _fanuc_footer(config: MachiningConfig) -> list[str]:
    safe_z = _format_float(config.safe_z)
    return [
        f"G00 Z{safe_z}",
        "G28 X0 Y0 (Return to reference point)",
        "M09 (Coolant OFF)",
        "M05 (Spindle OFF)",
        "M30 (End of program)",
    ]


def generate_gcode(
    contours: Sequence[np.ndarray],
    ordered_indices: Sequence[int],
    scale_factor: float,
    x_min: float,
    y_max: float,
    config: MachiningConfig,
) -> str:
    """Generate Fanuc G-code from ordered image contours."""
    safe_z = _format_float(config.safe_z)
    approach_z = _format_float(config.approach_z)
    cut_depth = _format_float(config.cut_depth)
    plunge_feed = _format_float(config.plunge_feed)
    cut_feed = _format_float(config.cut_feed)

    lines = _fanuc_header(config)

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
            arc_command = contour_arc_command(points)
            opposite_x = center_x - radius
            lines.extend(
                [
                    f"{arc_command} X{_format_float(opposite_x)} "
                    f"Y{_format_float(center_y)} I{_format_float(-radius)} "
                    f"J0.000 F{cut_feed} (Circle half 1)",
                    f"{arc_command} X{_format_float(start_x)} "
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

    lines.extend(_fanuc_footer(config))
    return "\n".join(lines) + "\n"


def generate_gcode_from_dxf(
    document: ezdxf.document.Drawing,
    config: MachiningConfig,
) -> tuple[str, int]:
    """Render supported modelspace entities as Fanuc profile toolpaths."""
    validate_config(config)
    scale_to_mm = _dxf_unit_scale_to_mm(document)
    safe_z = _format_float(config.safe_z)
    approach_z = _format_float(config.approach_z)
    cut_depth = _format_float(config.cut_depth)
    plunge_feed = _format_float(config.plunge_feed)
    cut_feed = _format_float(config.cut_feed)
    lines = _fanuc_header(config)
    entity_count = 0

    for entity in document.modelspace():
        entity_type = entity.dxftype()
        if entity_type == "CIRCLE":
            center_x, center_y = _validated_xy(
                entity.dxf.center.x * scale_to_mm,
                entity.dxf.center.y * scale_to_mm,
            )
            radius = float(entity.dxf.radius) * scale_to_mm
            if not math.isfinite(radius) or radius <= 0:
                raise RuntimeError("Error: DXF CIRCLE has an invalid radius.")

            start_x = center_x + radius
            opposite_x = center_x - radius
            lines.extend(
                [
                    f"G00 X{_format_float(start_x)} Y{_format_float(center_y)}",
                    f"G00 Z{approach_z}",
                    f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
                    f"G02 X{_format_float(opposite_x)} "
                    f"Y{_format_float(center_y)} I{_format_float(-radius)} "
                    f"J0.000 F{cut_feed} (Circle half 1)",
                    f"G02 X{_format_float(start_x)} "
                    f"Y{_format_float(center_y)} I{_format_float(radius)} "
                    f"J0.000 F{cut_feed} (Close contour)",
                    f"G00 Z{safe_z} (Retract)",
                ]
            )
            entity_count += 1
            continue

        if entity_type != "LWPOLYLINE":
            continue

        points = [
            _validated_xy(x * scale_to_mm, y * scale_to_mm)
            for x, y in entity.get_points("xy")
        ]
        if len(points) > 1 and np.allclose(points[-1], points[0], atol=1e-9):
            points.pop()
        if len(points) < 2:
            raise RuntimeError(
                "Error: DXF LWPOLYLINE must contain at least two distinct vertices."
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
        entity_count += 1

    if entity_count == 0:
        raise RuntimeError(
            "Error: DXF contains no supported CIRCLE or LWPOLYLINE entities."
        )
    lines.extend(_fanuc_footer(config))
    return "\n".join(lines) + "\n", entity_count
