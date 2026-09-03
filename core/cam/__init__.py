from __future__ import annotations

from core.cam.correlation import (
    auto_correlate_drawing_scale,
)
from core.cam.geometry import (
    circle_geometry_mm,
    contour_arc_command,
    ensure_contour_winding,
    machining_origin,
    offset_polygon,
    transform_contour,
)
from core.cam.sequencing import (
    contour_depth,
    order_contours_child_first,
)


__all__ = [
    "auto_correlate_drawing_scale",
    "circle_geometry_mm",
    "contour_arc_command",
    "contour_depth",
    "ensure_contour_winding",
    "machining_origin",
    "offset_polygon",
    "order_contours_child_first",
    "transform_contour",
]
