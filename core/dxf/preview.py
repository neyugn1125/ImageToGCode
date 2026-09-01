"""2D CAD geometry extraction for DXF preview rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

import ezdxf

from core.dxf.reader import _dxf_unit_scale_to_mm, _validated_xy


@dataclass
class DxfPreviewData:
    """Structured 2D vector geometry for DXF drawing preview."""

    lines: List[Dict[str, List[float]]] = field(default_factory=list)
    circles: List[Dict[str, Any]] = field(default_factory=list)
    arcs: List[Dict[str, Any]] = field(default_factory=list)
    polylines: List[Dict[str, Any]] = field(default_factory=list)
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    entity_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert preview data to dictionary suitable for JSON serialization."""
        return {
            "lines": self.lines,
            "circles": self.circles,
            "arcs": self.arcs,
            "polylines": self.polylines,
            "min_x": round(self.min_x, 3),
            "max_x": round(self.max_x, 3),
            "min_y": round(self.min_y, 3),
            "max_y": round(self.max_y, 3),
            "width_mm": round(self.width_mm, 3),
            "height_mm": round(self.height_mm, 3),
            "entity_count": self.entity_count,
        }


def extract_dxf_preview_geometry(document: ezdxf.document.Drawing) -> DxfPreviewData:
    """Extract all 2D vector geometry from a DXF document in millimeters."""
    scale_to_mm = _dxf_unit_scale_to_mm(document)
    xs: List[float] = []
    ys: List[float] = []

    lines: List[Dict[str, List[float]]] = []
    circles: List[Dict[str, Any]] = []
    arcs: List[Dict[str, Any]] = []
    polylines: List[Dict[str, Any]] = []
    entity_count = 0

    for entity in document.modelspace():
        etype = entity.dxftype()

        if etype == "LINE":
            sx, sy = _validated_xy(
                entity.dxf.start.x * scale_to_mm,
                entity.dxf.start.y * scale_to_mm,
            )
            ex, ey = _validated_xy(
                entity.dxf.end.x * scale_to_mm,
                entity.dxf.end.y * scale_to_mm,
            )
            lines.append({"start": [sx, sy], "end": [ex, ey]})
            xs.extend([sx, ex])
            ys.extend([sy, ey])
            entity_count += 1

        elif etype == "CIRCLE":
            cx, cy = _validated_xy(
                entity.dxf.center.x * scale_to_mm,
                entity.dxf.center.y * scale_to_mm,
            )
            radius = float(entity.dxf.radius) * scale_to_mm
            if math.isfinite(radius) and radius > 0:
                circles.append({"center": [cx, cy], "radius": radius})
                xs.extend([cx - radius, cx + radius])
                ys.extend([cy - radius, cy + radius])
                entity_count += 1

        elif etype == "ARC":
            cx, cy = _validated_xy(
                entity.dxf.center.x * scale_to_mm,
                entity.dxf.center.y * scale_to_mm,
            )
            radius = float(entity.dxf.radius) * scale_to_mm
            start_angle = float(entity.dxf.start_angle)
            end_angle = float(entity.dxf.end_angle)
            if math.isfinite(radius) and radius > 0:
                arcs.append({
                    "center": [cx, cy],
                    "radius": radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                })
                # Approximate bounding box points from arc
                rad_start = math.radians(start_angle)
                rad_end = math.radians(end_angle)
                sx = cx + radius * math.cos(rad_start)
                sy = cy + radius * math.sin(rad_start)
                ex = cx + radius * math.cos(rad_end)
                ey = cy + radius * math.sin(rad_end)
                xs.extend([sx, ex, cx - radius, cx + radius])
                ys.extend([sy, ey, cy - radius, cy + radius])
                entity_count += 1

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            raw_points = entity.get_points("xy")
            pts: List[List[float]] = []
            for x, y in raw_points:
                px, py = _validated_xy(x * scale_to_mm, y * scale_to_mm)
                pts.append([px, py])
                xs.append(px)
                ys.append(py)

            if len(pts) >= 2:
                is_closed = bool(getattr(entity, "closed", False))
                polylines.append({"points": pts, "closed": is_closed})
                entity_count += 1

    min_x = min(xs, default=0.0)
    max_x = max(xs, default=0.0)
    min_y = min(ys, default=0.0)
    max_y = max(ys, default=0.0)
    width_mm = max(0.0, max_x - min_x)
    height_mm = max(0.0, max_y - min_y)

    return DxfPreviewData(
        lines=lines,
        circles=circles,
        arcs=arcs,
        polylines=polylines,
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        width_mm=width_mm,
        height_mm=height_mm,
        entity_count=entity_count,
    )

