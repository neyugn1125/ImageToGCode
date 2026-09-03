from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import cv2
import ezdxf
import numpy as np

from core.cam.geometry import (
    circle_geometry_mm,
    contour_arc_command,
    ensure_contour_winding,
    offset_polygon,
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


def _classify_contours(
    contours: Sequence[np.ndarray],
    ordered_indices: Sequence[int],
    scale_factor: float,
    x_min: float,
    y_max: float,
) -> dict[int, bool]:
    """Determine whether each ordered contour is an inner hole (True) or outer boundary (False)."""
    polys: list[tuple[int, np.ndarray, float]] = []
    for idx in ordered_indices:
        c = contours[idx]
        pts = transform_contour(c, scale_factor, x_min, y_max).astype(np.float32)
        area = abs(float(cv2.contourArea(pts)))
        polys.append((idx, pts, area))

    result: dict[int, bool] = {}
    for i, (idx_i, pts_i, area_i) in enumerate(polys):
        containers = 0
        for j, (idx_j, pts_j, area_j) in enumerate(polys):
            if i == j or area_j <= area_i:
                continue
            cnt_j = pts_j.reshape(-1, 1, 2)
            # Check if all vertices of pts_i lie inside pts_j
            is_inside = True
            for pt in pts_i:
                if cv2.pointPolygonTest(cnt_j, (float(pt[0]), float(pt[1])), False) < 0:
                    is_inside = False
                    break
            if is_inside:
                containers += 1
        result[idx_i] = (containers % 2 == 1)
    return result


@dataclass
class DxfSegment:
    """A directed segment (linear or circular arc) in millimeters."""

    kind: str  # "LINE" or "ARC"
    start: tuple[float, float]
    end: tuple[float, float]
    center: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    is_ccw: bool = True
    from_single_poly: bool = False

    def reversed(self) -> DxfSegment:
        """Return a reversed segment."""
        if self.kind == "LINE":
            return DxfSegment(
                "LINE",
                self.end,
                self.start,
                from_single_poly=self.from_single_poly,
            )
        return DxfSegment(
            "ARC",
            self.end,
            self.start,
            center=self.center,
            radius=self.radius,
            is_ccw=not self.is_ccw,
            from_single_poly=self.from_single_poly,
        )

    def to_points(self, step_deg: float = 3.0) -> list[tuple[float, float]]:
        """Sample the segment into 2D points."""
        if self.kind == "LINE":
            return [self.start, self.end]
        cx, cy = self.center
        a1 = math.atan2(self.start[1] - cy, self.start[0] - cx)
        a2 = math.atan2(self.end[1] - cy, self.end[0] - cx)
        if self.is_ccw:
            if a2 <= a1:
                a2 += 2.0 * math.pi
        else:
            if a2 >= a1:
                a2 -= 2.0 * math.pi
        total_angle = abs(a2 - a1)
        n_steps = max(6, int(math.degrees(total_angle) / step_deg))
        angles = np.linspace(a1, a2, n_steps + 1)
        return [(float(cx + self.radius * math.cos(a)), float(cy + self.radius * math.sin(a))) for a in angles]


@dataclass
class DxfChain:
    """A sequence of connected DxfSegments forming a profile."""

    segments: list[DxfSegment]
    is_naturally_closed: bool
    force_close: bool
    is_inner: bool = False

    @property
    def is_closed(self) -> bool:
        return self.is_naturally_closed or self.force_close

    def to_points(self, step_deg: float = 3.0) -> list[tuple[float, float]]:
        """Discretize the entire chain into a sequence of points."""
        pts: list[tuple[float, float]] = []
        for seg in self.segments:
            seg_pts = seg.to_points(step_deg)
            if not pts:
                pts.extend(seg_pts)
            else:
                pts.extend(seg_pts[1:])
        return pts


def _chain_dxf_entities(
    document: ezdxf.document.Drawing,
    scale_to_mm: float = 1.0,
    tol: float = 0.1,
) -> tuple[list[tuple[tuple[float, float], float, bool]], list[DxfChain]]:
    """Decompose and chain DXF entities into circles and continuous profile chains."""
    raw_segments: list[DxfSegment] = []
    closed_chains: list[DxfChain] = []
    circle_data: list[tuple[tuple[float, float], float]] = []

    def pt_dist(p1: tuple[float, float], p2: tuple[float, float]) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    for entity in document.modelspace():
        etype = entity.dxftype()
        if etype == "CIRCLE":
            cx, cy = _validated_xy(
                entity.dxf.center.x * scale_to_mm,
                entity.dxf.center.y * scale_to_mm,
            )
            r = float(entity.dxf.radius) * scale_to_mm
            if math.isfinite(r) and r > 0:
                circle_data.append(((cx, cy), r))
        elif etype == "LINE":
            p1 = _validated_xy(entity.dxf.start.x * scale_to_mm, entity.dxf.start.y * scale_to_mm)
            p2 = _validated_xy(entity.dxf.end.x * scale_to_mm, entity.dxf.end.y * scale_to_mm)
            if pt_dist(p1, p2) > 1e-5:
                raw_segments.append(DxfSegment("LINE", p1, p2))
        elif etype == "ARC":
            cx, cy = _validated_xy(entity.dxf.center.x * scale_to_mm, entity.dxf.center.y * scale_to_mm)
            r = float(entity.dxf.radius) * scale_to_mm
            sa = math.radians(float(entity.dxf.start_angle))
            ea = math.radians(float(entity.dxf.end_angle))
            p1 = (cx + r * math.cos(sa), cy + r * math.sin(sa))
            p2 = (cx + r * math.cos(ea), cy + r * math.sin(ea))
            if math.isfinite(r) and r > 0:
                raw_segments.append(DxfSegment("ARC", p1, p2, center=(cx, cy), radius=r, is_ccw=True))
        elif etype in ("LWPOLYLINE", "POLYLINE"):
            pts = [
                _validated_xy(x * scale_to_mm, y * scale_to_mm)
                for x, y in entity.get_points("xy")
            ]
            if len(pts) > 1 and pt_dist(pts[0], pts[-1]) < 1e-5:
                pts = pts[:-1]
            is_poly_closed = getattr(entity, "is_closed", False) or (len(pts) > 1 and pt_dist(pts[0], pts[-1]) < 1e-5)
            if is_poly_closed and len(pts) >= 3:
                chain_segs = [
                    DxfSegment("LINE", pts[i], pts[(i + 1) % len(pts)], from_single_poly=True)
                    for i in range(len(pts))
                ]
                closed_chains.append(DxfChain(chain_segs, is_naturally_closed=True, force_close=True))
            else:
                for i in range(len(pts) - 1):
                    p1 = pts[i]
                    p2 = pts[i + 1]
                    if pt_dist(p1, p2) > 1e-5:
                        raw_segments.append(DxfSegment("LINE", p1, p2, from_single_poly=True))

    rem = list(raw_segments)
    all_chains: list[DxfChain] = list(closed_chains)

    while rem:
        chain_segs = [rem.pop(0)]
        changed = True
        while changed:
            changed = False
            if len(chain_segs) > 1 and pt_dist(chain_segs[0].start, chain_segs[-1].end) < tol:
                break
            end_pt = chain_segs[-1].end
            start_pt = chain_segs[0].start

            best_i: int | None = None
            rev = False
            for i, s in enumerate(rem):
                if pt_dist(s.start, end_pt) < tol:
                    best_i = i
                    rev = False
                    break
                if pt_dist(s.end, end_pt) < tol:
                    best_i = i
                    rev = True
                    break
            if best_i is not None:
                s = rem.pop(best_i)
                chain_segs.append(s.reversed() if rev else s)
                changed = True
                continue

            for i, s in enumerate(rem):
                if pt_dist(s.end, start_pt) < tol:
                    best_i = i
                    rev = False
                    break
                if pt_dist(s.start, start_pt) < tol:
                    best_i = i
                    rev = True
                    break
            if best_i is not None:
                s = rem.pop(best_i)
                chain_segs.insert(0, s.reversed() if rev else s)
                changed = True

        is_naturally_closed = len(chain_segs) > 1 and pt_dist(chain_segs[0].start, chain_segs[-1].end) < tol
        force_close = is_naturally_closed or (len(chain_segs) >= 2 and all(s.from_single_poly for s in chain_segs))
        all_chains.append(DxfChain(chain_segs, is_naturally_closed=is_naturally_closed, force_close=force_close))

    # Calculate areas and bounding polygons for classification
    polygons: list[tuple[int, np.ndarray, float]] = []
    for idx, chain in enumerate(all_chains):
        pts = chain.to_points()
        if len(pts) >= 3:
            np_pts = np.array(pts, dtype=np.float32)
            area = abs(float(cv2.contourArea(np_pts)))
            polygons.append((idx, np_pts, area))

    # Classify chains
    for i, (idx_i, poly_i, area_i) in enumerate(polygons):
        containers = 0
        for j, (idx_j, poly_j, area_j) in enumerate(polygons):
            if i == j or area_j <= area_i:
                continue
            cnt_j = poly_j.reshape(-1, 1, 2)
            is_inside = True
            for pt in poly_i:
                if cv2.pointPolygonTest(cnt_j, (float(pt[0]), float(pt[1])), False) < 0:
                    is_inside = False
                    break
            if is_inside:
                containers += 1
        all_chains[idx_i].is_inner = (containers % 2 == 1)

    # Classify circles
    classified_circles: list[tuple[tuple[float, float], float, bool]] = []
    for center, r in circle_data:
        containers = 0
        for _, poly, _ in polygons:
            cnt = poly.reshape(-1, 1, 2)
            if cv2.pointPolygonTest(cnt, center, False) > 0:
                containers += 1
        classified_circles.append((center, r, containers % 2 == 1))

    # Sort chains: inner features first, outer boundaries last
    all_chains.sort(key=lambda c: 0 if c.is_inner else 1)

    return classified_circles, all_chains


def _emit_polyline_toolpath(
    points: Sequence[tuple[float, float]] | np.ndarray,
    is_inner: bool,
    config: MachiningConfig,
    approach_z: str,
    cut_depth: str,
    safe_z: str,
    plunge_feed: str,
    cut_feed: str,
) -> list[str]:
    comp_mode = config.cutter_comp.upper() if config.cutter_comp else "CAM"
    is_cam = comp_mode == "CAM"
    use_controller_comp = comp_mode in ("G41", "G42")
    raw_pts = [(float(x), float(y)) for x, y in points]

    if is_cam and len(raw_pts) >= 3 and config.tool_diameter > 0:
        # Option 1: CAM Computer Offset (Direct Tool Centerline Coordinates)
        tool_radius = config.tool_diameter / 2.0
        offset_dist = -tool_radius if is_inner else tool_radius
        cut_pts = offset_polygon(raw_pts, offset_dist)
    else:
        cut_pts = raw_pts

    if not use_controller_comp:
        start_x, start_y = cut_pts[0]
        lines = [
            f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
            f"G00 Z{approach_z}",
            f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
        ]
        for x, y in cut_pts[1:]:
            lines.append(f"G01 X{_format_float(x)} Y{_format_float(y)} F{cut_feed} (Cut)")
        if len(cut_pts) >= 3:
            lines.append(
                f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} F{cut_feed} (Close contour)"
            )
        lines.append(f"G00 Z{safe_z} (Retract)")
        return lines

    # For closed contour with G41/G42:
    # 1. Ensure correct winding direction (CW for outer with G41, CCW for inner with G41)
    pts = ensure_contour_winding(raw_pts, is_inner=is_inner, comp_mode=comp_mode)
    p0 = np.array(pts[0], dtype=np.float64)
    p1 = np.array(pts[1], dtype=np.float64)
    edge_vec = p1 - p0
    edge_len = float(np.linalg.norm(edge_vec))
    if edge_len < 1e-6:
        unit_v = np.array([1.0, 0.0])
    else:
        unit_v = edge_vec / edge_len

    # Normal pointing towards cutter offset side (outside for outer boundary, inside for pocket):
    if comp_mode == "G41":
        normal = np.array([-unit_v[1], unit_v[0]])
    else:
        normal = np.array([unit_v[1], -unit_v[0]])

    mid = (p0 + p1) * 0.5
    lead_dist = max(2.0, min(5.0, config.tool_diameter * 0.75))
    p_lead = mid + normal * lead_dist

    lines = [
        f"G00 X{_format_float(p_lead[0])} Y{_format_float(p_lead[1])}",
        f"G00 Z{approach_z}",
        f"G01 Z{cut_depth} F{plunge_feed} (Plunge in free air)",
        f"G01 {comp_mode} D{config.cutter_offset_d} X{_format_float(mid[0])} Y{_format_float(mid[1])} F{cut_feed} (Lead-in with {comp_mode})",
        f"G01 X{_format_float(pts[1][0])} Y{_format_float(pts[1][1])} F{cut_feed} (Cut)",
    ]
    for x, y in pts[2:]:
        lines.append(f"G01 X{_format_float(x)} Y{_format_float(y)} F{cut_feed} (Cut)")
    lines.extend(
        [
            f"G01 X{_format_float(pts[0][0])} Y{_format_float(pts[0][1])} F{cut_feed} (Cut)",
            f"G01 X{_format_float(mid[0])} Y{_format_float(mid[1])} F{cut_feed} (Close to midpoint)",
            f"G01 G40 X{_format_float(p_lead[0])} Y{_format_float(p_lead[1])} F{cut_feed} (Lead-out with G40)",
            f"G00 Z{safe_z} (Retract in free air)",
        ]
    )
    return lines


def _emit_circle_toolpath(
    center_x: float,
    center_y: float,
    radius: float,
    is_inner: bool,
    config: MachiningConfig,
    approach_z: str,
    cut_depth: str,
    safe_z: str,
    plunge_feed: str,
    cut_feed: str,
    nominal_arc_cmd: str = "G02",
) -> list[str]:
    comp_mode = config.cutter_comp.upper() if config.cutter_comp else "CAM"
    is_cam = comp_mode == "CAM"
    use_controller_comp = comp_mode in ("G41", "G42")

    if is_cam and config.tool_diameter > 0:
        # Option 1: CAM Computer Offset for Circles (Flawless tool centerline circle)
        tool_radius = config.tool_diameter / 2.0
        if is_inner:
            if tool_radius >= radius:
                # Tool diameter >= hole diameter: plunge at center and retract
                lines = [
                    f"G00 X{_format_float(center_x)} Y{_format_float(center_y)}",
                    f"G00 Z{approach_z}",
                    f"G01 Z{cut_depth} F{plunge_feed} (Plunge at center - tool D{config.tool_diameter:.1f} >= hole D{2*radius:.1f})",
                    f"G00 Z{safe_z} (Retract)",
                ]
                return lines
            r_cut = radius - tool_radius
            start_x = center_x + r_cut
            opposite_x = center_x - r_cut
            lines = [
                f"G00 X{_format_float(center_x)} Y{_format_float(center_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge at center)",
                f"G01 X{_format_float(start_x)} Y{_format_float(center_y)} F{cut_feed} (Move to cut radius)",
                f"G03 X{_format_float(opposite_x)} Y{_format_float(center_y)} I{_format_float(-r_cut)} J0.000 F{cut_feed} (Circle half 1)",
                f"G03 X{_format_float(start_x)} Y{_format_float(center_y)} I{_format_float(r_cut)} J0.000 F{cut_feed} (Close contour)",
                f"G01 X{_format_float(center_x)} Y{_format_float(center_y)} F{cut_feed} (Return to center)",
                f"G00 Z{safe_z} (Retract)",
            ]
            return lines
        else:
            # Outer boss / cylinder:
            r_cut = radius + tool_radius
            start_x = center_x + r_cut
            opposite_x = center_x - radius  # wait: opposite_x is center_x - r_cut!
            opposite_x = center_x - r_cut
            lead_dist = max(2.0, min(5.0, config.tool_diameter * 0.75))
            p_lead_x = start_x + lead_dist
            lines = [
                f"G00 X{_format_float(p_lead_x)} Y{_format_float(center_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge in free air)",
                f"G01 X{_format_float(start_x)} Y{_format_float(center_y)} F{cut_feed} (Move to cut radius)",
                f"G02 X{_format_float(opposite_x)} Y{_format_float(center_y)} I{_format_float(-r_cut)} J0.000 F{cut_feed} (Circle half 1)",
                f"G02 X{_format_float(start_x)} Y{_format_float(center_y)} I{_format_float(r_cut)} J0.000 F{cut_feed} (Close contour)",
                f"G01 X{_format_float(p_lead_x)} Y{_format_float(center_y)} F{cut_feed} (Exit to free air)",
                f"G00 Z{safe_z} (Retract in free air)",
            ]
            return lines

    if not use_controller_comp:
        # G40: Direct nominal circular machining without compensation
        start_x = center_x + radius
        opposite_x = center_x - radius
        lines = [
            f"G00 X{_format_float(start_x)} Y{_format_float(center_y)}",
            f"G00 Z{approach_z}",
            f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
            f"{nominal_arc_cmd} X{_format_float(opposite_x)} Y{_format_float(center_y)} I{_format_float(-radius)} J0.000 F{cut_feed} (Circle half 1)",
            f"{nominal_arc_cmd} X{_format_float(start_x)} Y{_format_float(center_y)} I{_format_float(radius)} J0.000 F{cut_feed} (Close contour)",
            f"G00 Z{safe_z} (Retract)",
        ]
        return lines

    arc_cmd = (
        ("G03" if is_inner else "G02")
        if comp_mode == "G41"
        else ("G02" if is_inner else "G03")
    )
    lead_dist = max(2.0, min(5.0, config.tool_diameter * 0.75))

    if is_inner:
        # Inner hole: Plunge at center, lead to perimeter, cut circle, return to center
        start_x = center_x + radius
        opposite_x = center_x - radius
        lines = [
            f"G00 X{_format_float(center_x)} Y{_format_float(center_y)}",
            f"G00 Z{approach_z}",
            f"G01 Z{cut_depth} F{plunge_feed} (Plunge at center)",
            f"G01 {comp_mode} D{config.cutter_offset_d} X{_format_float(start_x)} Y{_format_float(center_y)} F{cut_feed} (Lead-in with {comp_mode})",
            f"{arc_cmd} X{_format_float(opposite_x)} Y{_format_float(center_y)} I{_format_float(-radius)} J0.000 F{cut_feed} (Circle half 1)",
            f"{arc_cmd} X{_format_float(start_x)} Y{_format_float(center_y)} I{_format_float(radius)} J0.000 F{cut_feed} (Circle half 2)",
            f"G01 G40 X{_format_float(center_x)} Y{_format_float(center_y)} F{cut_feed} (Lead-out to center)",
            f"G00 Z{safe_z} (Retract in free air)",
        ]
        return lines
    else:
        # Outer boss / cylinder: Plunge outside, lead to perimeter, cut circle, lead-out
        p_lead_x = center_x + radius + lead_dist
        p_lead_y = center_y
        start_x = center_x + radius
        opposite_x = center_x - radius
        lines = [
            f"G00 X{_format_float(p_lead_x)} Y{_format_float(p_lead_y)}",
            f"G00 Z{approach_z}",
            f"G01 Z{cut_depth} F{plunge_feed} (Plunge in free air)",
            f"G01 {comp_mode} D{config.cutter_offset_d} X{_format_float(start_x)} Y{_format_float(center_y)} F{cut_feed} (Lead-in with {comp_mode})",
            f"{arc_cmd} X{_format_float(opposite_x)} Y{_format_float(center_y)} I{_format_float(-radius)} J0.000 F{cut_feed} (Circle half 1)",
            f"{arc_cmd} X{_format_float(start_x)} Y{_format_float(center_y)} I{_format_float(radius)} J0.000 F{cut_feed} (Circle half 2)",
            f"G01 G40 X{_format_float(p_lead_x)} Y{_format_float(p_lead_y)} F{cut_feed} (Lead-out with G40)",
            f"G00 Z{safe_z} (Retract in free air)",
        ]
        return lines


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
    inner_map = _classify_contours(contours, ordered_indices, scale_factor, x_min, y_max)

    for index in ordered_indices:
        contour = contours[index]
        points = transform_contour(contour, scale_factor, x_min, y_max)
        ideal_circle = is_ideal_circle(contour)
        is_inner = inner_map.get(index, False)

        if ideal_circle:
            center_x, center_y, radius = circle_geometry_mm(
                contour, scale_factor, x_min, y_max
            )
            lines.extend(
                _emit_circle_toolpath(
                    center_x=center_x,
                    center_y=center_y,
                    radius=radius,
                    is_inner=is_inner,
                    config=config,
                    approach_z=approach_z,
                    cut_depth=cut_depth,
                    safe_z=safe_z,
                    plunge_feed=plunge_feed,
                    cut_feed=cut_feed,
                    nominal_arc_cmd=contour_arc_command(points),
                )
            )
        else:
            lines.extend(
                _emit_polyline_toolpath(
                    points,
                    is_inner=is_inner,
                    config=config,
                    approach_z=approach_z,
                    cut_depth=cut_depth,
                    safe_z=safe_z,
                    plunge_feed=plunge_feed,
                    cut_feed=cut_feed,
                )
            )

    lines.extend(_fanuc_footer(config))
    return "\n".join(lines) + "\n"


def _line_line_intersection(
    p1: tuple[float, float],
    u1: tuple[float, float],
    p2: tuple[float, float],
    u2: tuple[float, float],
) -> tuple[float, float]:
    det = u1[0] * (-u2[1]) - u1[1] * (-u2[0])
    if abs(det) < 1e-9:
        return p2
    dp = (p2[0] - p1[0], p2[1] - p1[1])
    t1 = (dp[0] * (-u2[1]) - dp[1] * (-u2[0])) / det
    return (p1[0] + t1 * u1[0], p1[1] + t1 * u1[1])


def _line_circle_intersection(
    p_line: tuple[float, float],
    u_line: tuple[float, float],
    center: tuple[float, float],
    radius: float,
    near_pt: tuple[float, float],
) -> tuple[float, float]:
    dx = p_line[0] - center[0]
    dy = p_line[1] - center[1]
    b = 2.0 * (dx * u_line[0] + dy * u_line[1])
    c = dx * dx + dy * dy - radius * radius
    disc = b * b - 4.0 * c
    if disc < 0:
        t = -b / 2.0
        return (p_line[0] + t * u_line[0], p_line[1] + t * u_line[1])
    sq = math.sqrt(disc)
    t1 = (-b - sq) / 2.0
    t2 = (-b + sq) / 2.0
    pt1 = (p_line[0] + t1 * u_line[0], p_line[1] + t1 * u_line[1])
    pt2 = (p_line[0] + t2 * u_line[0], p_line[1] + t2 * u_line[1])
    d1 = math.hypot(pt1[0] - near_pt[0], pt1[1] - near_pt[1])
    d2 = math.hypot(pt2[0] - near_pt[0], pt2[1] - near_pt[1])
    return pt1 if d1 < d2 else pt2


def _offset_chain_analytically(
    chain: DxfChain,
    tool_radius: float,
) -> list[DxfSegment] | None:
    """Offset a closed chain of LINE and ARC segments analytically, preserving exact arcs."""
    n = len(chain.segments)
    if n == 0:
        return None

    try:
        poly_pts = chain.to_points(step_deg=10.0)
        area = 0.0
        for i in range(len(poly_pts)):
            p1 = poly_pts[i]
            p2 = poly_pts[(i + 1) % len(poly_pts)]
            area += (p1[0] * p2[1] - p2[0] * p1[1])
        is_ccw = area > 0

        d_eff = -tool_radius if chain.is_inner else tool_radius

        offset_info: list[tuple[str, tuple[float, float], tuple[float, float] | float, DxfSegment]] = []
        for s in chain.segments:
            if s.kind == "LINE":
                dx = s.end[0] - s.start[0]
                dy = s.end[1] - s.start[1]
                L = math.hypot(dx, dy)
                ux, uy = (dx / L, dy / L) if L > 1e-9 else (1.0, 0.0)
                nx, ny = (uy, -ux) if is_ccw else (-uy, ux)
                shift = (d_eff * nx, d_eff * ny)
                p_line = (s.start[0] + shift[0], s.start[1] + shift[1])
                offset_info.append(("LINE", p_line, (ux, uy), s))
            else:
                cx, cy = s.center
                a_start = math.atan2(s.start[1] - cy, s.start[0] - cx)
                a_end = math.atan2(s.end[1] - cy, s.end[0] - cx)
                if s.is_ccw and a_end <= a_start:
                    a_end += 2.0 * math.pi
                elif not s.is_ccw and a_end >= a_start:
                    a_end -= 2.0 * math.pi
                a_mid = (a_start + a_end) / 2.0
                r_mid = (math.cos(a_mid), math.sin(a_mid))
                t_mid = (-math.sin(a_mid), math.cos(a_mid)) if s.is_ccw else (math.sin(a_mid), -math.cos(a_mid))
                n_out_mid = (t_mid[1], -t_mid[0]) if is_ccw else (-t_mid[1], t_mid[0])
                is_convex = (r_mid[0] * n_out_mid[0] + r_mid[1] * n_out_mid[1]) > 0
                r_prime = max(0.1, s.radius + d_eff if is_convex else s.radius - d_eff)
                offset_info.append(("ARC", (cx, cy), r_prime, s))

        new_vertices: list[tuple[float, float]] = []
        for i in range(n):
            curr_info = offset_info[i]
            next_info = offset_info[(i + 1) % n]
            orig_junction = chain.segments[i].end

            if curr_info[0] == "LINE" and next_info[0] == "LINE":
                v = _line_line_intersection(curr_info[1], curr_info[2], next_info[1], next_info[2])  # type: ignore[arg-type]
            elif curr_info[0] == "LINE" and next_info[0] == "ARC":
                v = _line_circle_intersection(curr_info[1], curr_info[2], next_info[1], float(next_info[2]), orig_junction)  # type: ignore[arg-type]
            elif curr_info[0] == "ARC" and next_info[0] == "LINE":
                v = _line_circle_intersection(next_info[1], next_info[2], curr_info[1], float(curr_info[2]), orig_junction)  # type: ignore[arg-type]
            else:
                v = orig_junction
            new_vertices.append(v)

        res_segments: list[DxfSegment] = []
        for i in range(n):
            v_start = new_vertices[(i - 1) % n]
            v_end = new_vertices[i]
            s_orig = chain.segments[i]
            if s_orig.kind == "LINE":
                res_segments.append(DxfSegment("LINE", v_start, v_end))
            else:
                cx, cy = s_orig.center
                r_prime = float(offset_info[i][2])
                res_segments.append(DxfSegment("ARC", v_start, v_end, center=(cx, cy), radius=r_prime, is_ccw=s_orig.is_ccw))
        return res_segments
    except Exception:
        return None


def _emit_chained_toolpath(
    chain: DxfChain,
    config: MachiningConfig,
    approach_z: str,
    cut_depth: str,
    safe_z: str,
    plunge_feed: str,
    cut_feed: str,
) -> list[str]:
    """Emit G-code for a chained sequence of linear and circular arc segments."""
    comp_mode = config.cutter_comp.upper() if config.cutter_comp else "G40"
    is_cam = comp_mode == "CAM"
    use_controller_comp = comp_mode in ("G41", "G42")

    # Option 1: CAM Direct Offset on closed profiles preserving exact G02/G03 arcs
    if is_cam and chain.is_closed and config.tool_diameter > 0:
        tool_radius = config.tool_diameter / 2.0
        analytic_segs = _offset_chain_analytically(chain, tool_radius)
        if analytic_segs:
            start_x, start_y = analytic_segs[0].start
            lines = [
                f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
            ]
            for idx, seg in enumerate(analytic_segs):
                is_last = (idx == len(analytic_segs) - 1)
                tag = "(Close contour)" if is_last else ("(Cut line)" if seg.kind == "LINE" else "(Arc)")
                if seg.kind == "LINE":
                    lines.append(f"G01 X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} F{cut_feed} {tag}")
                else:
                    cmd = "G03" if seg.is_ccw else "G02"
                    i_val = seg.center[0] - seg.start[0]
                    j_val = seg.center[1] - seg.start[1]
                    lines.append(f"{cmd} X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} I{_format_float(i_val)} J{_format_float(j_val)} F{cut_feed} {tag}")
            lines.append(f"G00 Z{safe_z} (Retract)")
            return lines

        # Fallback to polygon offset if analytic offset fails
        raw_pts = chain.to_points(step_deg=3.0)
        if len(raw_pts) >= 3:
            offset_dist = -tool_radius if chain.is_inner else tool_radius
            cut_pts = offset_polygon(raw_pts, offset_dist)
            start_x, start_y = cut_pts[0]
            lines = [
                f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
                f"G00 Z{approach_z}",
                f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
            ]
            for x, y in cut_pts[1:]:
                lines.append(f"G01 X{_format_float(x)} Y{_format_float(y)} F{cut_feed} (Cut)")
            lines.append(f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} F{cut_feed} (Close contour)")
            lines.append(f"G00 Z{safe_z} (Retract)")
            return lines

    start_x, start_y = chain.segments[0].start

    if use_controller_comp:
        lead_dist = max(2.0, min(5.0, config.tool_diameter * 0.75))
        first_seg = chain.segments[0]
        dx = first_seg.end[0] - first_seg.start[0]
        dy = first_seg.end[1] - first_seg.start[1]
        seg_len = math.hypot(dx, dy)
        ux, uy = (dx / seg_len, dy / seg_len) if seg_len > 1e-6 else (1.0, 0.0)
        p_lead_x = start_x - ux * lead_dist
        p_lead_y = start_y - uy * lead_dist

        lines = [
            f"G00 X{_format_float(p_lead_x)} Y{_format_float(p_lead_y)}",
            f"G00 Z{approach_z}",
            f"G01 Z{cut_depth} F{plunge_feed} (Plunge in free air)",
            f"G01 {comp_mode} D{config.cutter_offset_d} X{_format_float(start_x)} Y{_format_float(start_y)} F{cut_feed} (Lead-in with {comp_mode})",
        ]
        for idx, seg in enumerate(chain.segments):
            is_last = (idx == len(chain.segments) - 1)
            tag = "(Close contour)" if (is_last and chain.is_closed) else ("(Cut line)" if seg.kind == "LINE" else "(Arc)")
            if seg.kind == "LINE":
                lines.append(f"G01 X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} F{cut_feed} {tag}")
            else:
                cmd = "G03" if seg.is_ccw else "G02"
                i_val = seg.center[0] - seg.start[0]
                j_val = seg.center[1] - seg.start[1]
                lines.append(f"{cmd} X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} I{_format_float(i_val)} J{_format_float(j_val)} F{cut_feed} {tag}")

        if chain.force_close and not chain.is_naturally_closed:
            lines.append(f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} F{cut_feed} (Close contour)")

        last_seg = chain.segments[-1]
        ldx = last_seg.end[0] - last_seg.start[0]
        ldy = last_seg.end[1] - last_seg.start[1]
        l_len = math.hypot(ldx, ldy)
        lux, luy = (ldx / l_len, ldy / l_len) if l_len > 1e-6 else (1.0, 0.0)
        p_exit_x = last_seg.end[0] + lux * lead_dist
        p_exit_y = last_seg.end[1] + luy * lead_dist
        lines.append(f"G01 G40 X{_format_float(p_exit_x)} Y{_format_float(p_exit_y)} F{cut_feed} (Lead-out with G40)")
        lines.append(f"G00 Z{safe_z} (Retract)")
        return lines

    # Nominal G40
    lines = [
        f"G00 X{_format_float(start_x)} Y{_format_float(start_y)}",
        f"G00 Z{approach_z}",
        f"G01 Z{cut_depth} F{plunge_feed} (Plunge)",
    ]
    for idx, seg in enumerate(chain.segments):
        is_last = (idx == len(chain.segments) - 1)
        tag = "(Close contour)" if (is_last and chain.is_closed) else ("(Cut line)" if seg.kind == "LINE" else "(Arc)")
        if seg.kind == "LINE":
            lines.append(f"G01 X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} F{cut_feed} {tag}")
        else:
            cmd = "G03" if seg.is_ccw else "G02"
            i_val = seg.center[0] - seg.start[0]
            j_val = seg.center[1] - seg.start[1]
            lines.append(f"{cmd} X{_format_float(seg.end[0])} Y{_format_float(seg.end[1])} I{_format_float(i_val)} J{_format_float(j_val)} F{cut_feed} {tag}")

    if chain.force_close and not chain.is_naturally_closed:
        lines.append(f"G01 X{_format_float(start_x)} Y{_format_float(start_y)} F{cut_feed} (Close contour)")

    lines.append(f"G00 Z{safe_z} (Retract)")
    return lines


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

    circles, chains = _chain_dxf_entities(document, scale_to_mm)

    if not circles and not chains:
        raise RuntimeError(
            "Error: DXF contains no supported CIRCLE, LWPOLYLINE, LINE, or ARC entities."
        )

    # 1. Emit inner circles first, then outer circles
    sorted_circles = sorted(circles, key=lambda c: 0 if c[2] else 1)
    for (cx, cy), radius, is_inner in sorted_circles:
        lines.extend(
            _emit_circle_toolpath(
                center_x=cx,
                center_y=cy,
                radius=radius,
                is_inner=is_inner,
                config=config,
                approach_z=approach_z,
                cut_depth=cut_depth,
                safe_z=safe_z,
                plunge_feed=plunge_feed,
                cut_feed=cut_feed,
            )
        )

    # 2. Emit chained profile contours (inner pockets/slots first, outer boundary last)
    for chain in chains:
        lines.extend(
            _emit_chained_toolpath(
                chain=chain,
                config=config,
                approach_z=approach_z,
                cut_depth=cut_depth,
                safe_z=safe_z,
                plunge_feed=plunge_feed,
                cut_feed=cut_feed,
            )
        )

    entity_count = len(circles) + len(chains)
    lines.extend(_fanuc_footer(config))
    return "\n".join(lines) + "\n", entity_count
