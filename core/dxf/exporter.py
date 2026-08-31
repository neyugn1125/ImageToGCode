from __future__ import annotations

from pathlib import Path

import ezdxf
import numpy as np
from ezdxf import units

from core.cam.geometry import (
    circle_geometry_mm,
    machining_origin,
    transform_contour,
)
from core.cam.sequencing import order_contours_child_first
from core.vision.analysis import _extract_machining_contours
from core.vision.calibration import (
    _validate_scale_reference,
    largest_square_contour_extent,
    scale_factor_from_reference,
)
from core.vision.contours import (
    is_ideal_circle,
    valid_contour_indices,
)
from core.vision.loader import (
    diagrams_net_square_size_mm,
    load_binary_image,
)
from core.vision.types import SCALE_REFERENCE_ERROR


def image_to_dxf(
    input_path: Path,
    dxf_path: Path,
    *,
    reference_width_mm: float | None = None,
    reference_height_mm: float | None = None,
    pixels_per_mm: float | None = None,
    strip_dimensions: bool = False,
) -> tuple[float, int]:
    """Vectorize an image and save millimeter geometry as a DXF document."""
    _validate_scale_reference(
        reference_width_mm,
        reference_height_mm,
        pixels_per_mm,
    )
    binary = load_binary_image(input_path)
    contours, hierarchy, calibration = _extract_machining_contours(
        binary,
        require_calibration=False,
        strip_dimensions=strip_dimensions,
    )
    valid_indices = valid_contour_indices(contours)
    reference_size_mm = diagrams_net_square_size_mm(input_path)
    if pixels_per_mm is not None:
        scale_factor = pixels_per_mm
    elif reference_width_mm is not None or reference_height_mm is not None:
        scale_factor = scale_factor_from_reference(
            contours,
            valid_indices,
            reference_width_mm,
            reference_height_mm,
        )
    elif reference_size_mm is not None:
        reference_extent_px = largest_square_contour_extent(contours, valid_indices)
        if reference_extent_px is None:
            raise RuntimeError(
                "Error: Embedded vector dimensions were found, but no square "
                "machining envelope could be detected."
            )
        scale_factor = reference_extent_px / reference_size_mm
    elif calibration is not None:
        scale_factor = calibration.scale_factor
    else:
        from core.cam.correlation import auto_correlate_drawing_scale

        correlated = auto_correlate_drawing_scale(binary)
        if correlated is not None:
            scale_factor, _, _ = correlated
            # If dimensions were not stripped, re-extract with strip_dimensions=True
            if not strip_dimensions:
                contours, hierarchy, _ = _extract_machining_contours(
                    binary,
                    require_calibration=False,
                    strip_dimensions=True,
                )
                valid_indices = valid_contour_indices(contours)
        else:
            raise RuntimeError(SCALE_REFERENCE_ERROR)
    if not np.isfinite(scale_factor) or scale_factor <= 1e-6:
        raise RuntimeError("Error: Invalid or near-zero scale factor.")
    x_min, y_max = machining_origin(contours, valid_indices)
    ordered_indices = order_contours_child_first(valid_indices, hierarchy)

    document = ezdxf.new("R2010")
    document.units = units.MM
    document.header["$MEASUREMENT"] = 1
    modelspace = document.modelspace()
    from core.cam.correlation import extract_drawing_coordinate_constraints

    cx_c, cy_c, cr_c = extract_drawing_coordinate_constraints(binary)

    for index in ordered_indices:
        contour = contours[index]
        if is_ideal_circle(contour):
            center_x, center_y, radius = circle_geometry_mm(
                contour,
                scale_factor,
                x_min,
                y_max,
                snap_constraints_x=cx_c,
                snap_constraints_y=cy_c,
                snap_constraints_r=cr_c,
            )
            modelspace.add_circle((center_x, center_y), radius)
            continue

        points = transform_contour(
            contour,
            scale_factor,
            x_min,
            y_max,
            snap_constraints_x=cx_c,
            snap_constraints_y=cy_c,
        )
        modelspace.add_lwpolyline(
            [(float(x), float(y)) for x, y in points],
            close=True,
        )

    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(dxf_path)
    return scale_factor, len(ordered_indices)
