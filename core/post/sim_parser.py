from __future__ import annotations

import bisect
import math
import re
from typing import NamedTuple


Point = tuple[float, float]
_GCODE_WORD_RE = re.compile(r"([A-Z])(-?\d+(?:\.\d+)?)")
RAPID_DISPLAY_FEED = 3000.0


class Segment(NamedTuple):
    kind: str  # "rapid" | "linear" | "arc_cw" | "arc_ccw"
    points: list[Point]
    feed: float
    z_depth: float = 0.0


class Frame(NamedTuple):
    time: float
    x: float
    y: float
    z: float
    kind: str
    feed: float


def _strip_gcode_comment(line: str) -> str:
    return line.split("(", 1)[0].strip()


def _arc_points(
    start: Point,
    end: Point,
    offset_i: float,
    offset_j: float,
    clockwise: bool,
    segments: int = 32,
) -> list[Point]:
    center_x = start[0] + offset_i
    center_y = start[1] + offset_j
    radius = math.hypot(start[0] - center_x, start[1] - center_y)
    if radius <= 1e-9:
        return [start, end]

    start_angle = math.atan2(start[1] - center_y, start[0] - center_x)
    end_angle = math.atan2(end[1] - center_y, end[0] - center_x)
    if clockwise:
        while end_angle > start_angle:
            end_angle -= 2 * math.pi
    else:
        while end_angle < start_angle:
            end_angle += 2 * math.pi

    return [
        (
            center_x + radius * math.cos(start_angle + (end_angle - start_angle) * step / segments),
            center_y + radius * math.sin(start_angle + (end_angle - start_angle) * step / segments),
        )
        for step in range(segments + 1)
    ]


def parse_toolpath_segments(gcode_text: str) -> list[Segment]:
    """Extract rapid/linear/arc XY moves and Z depths from generated G-code, in machine mm."""
    segments: list[Segment] = []
    x = y = z = 0.0
    motion_mode: int | None = None
    feed_rate = 0.0
    for raw_line in gcode_text.splitlines():
        line = _strip_gcode_comment(raw_line)
        if not line:
            continue
        words = dict(_GCODE_WORD_RE.findall(line))
        if "G" in words:
            g_value = int(float(words["G"]))
            if g_value in (0, 1, 2, 3):
                motion_mode = g_value
        if "F" in words:
            feed_rate = float(words["F"])
        if "Z" in words:
            z = float(words["Z"])

        new_x = float(words["X"]) if "X" in words else x
        new_y = float(words["Y"]) if "Y" in words else y
        if motion_mode is None or ("X" not in words and "Y" not in words):
            x, y = new_x, new_y
            continue

        if motion_mode == 0:
            segments.append(Segment("rapid", [(x, y), (new_x, new_y)], 0.0, z))
        elif motion_mode == 1:
            segments.append(Segment("linear", [(x, y), (new_x, new_y)], feed_rate, z))
        else:
            offset_i = float(words["I"]) if "I" in words else 0.0
            offset_j = float(words["J"]) if "J" in words else 0.0
            points = _arc_points((x, y), (new_x, new_y), offset_i, offset_j, motion_mode == 2)
            kind = "arc_cw" if motion_mode == 2 else "arc_ccw"
            segments.append(Segment(kind, points, feed_rate, z))
        x, y = new_x, new_y
    return segments


def build_sim_timeline(segments: list[Segment]) -> tuple[list[Frame], float, float, float]:
    """Unroll segments into a time-stamped animation timeline.

    Returns (frames, total_time_seconds, cut_distance_mm, rapid_distance_mm).
    """
    if not segments:
        return [], 0.0, 0.0, 0.0

    first_x, first_y = segments[0].points[0]
    first_z = segments[0].z_depth
    frames: list[Frame] = [Frame(0.0, first_x, first_y, first_z, "idle", 0.0)]
    elapsed = 0.0
    cut_distance = 0.0
    rapid_distance = 0.0
    for segment in segments:
        feed = segment.feed if segment.feed > 0 else RAPID_DISPLAY_FEED
        for start_point, end_point in zip(segment.points, segment.points[1:]):
            distance = math.hypot(
                end_point[0] - start_point[0], end_point[1] - start_point[1]
            )
            if segment.kind == "rapid":
                rapid_distance += distance
            else:
                cut_distance += distance
            elapsed += (distance / feed) * 60.0
            frames.append(Frame(elapsed, end_point[0], end_point[1], segment.z_depth, segment.kind, segment.feed))
    return frames, elapsed, cut_distance, rapid_distance


def sim_state_at_time(frames: list[Frame], moment: float) -> tuple[float, float, float, str, float]:
    """Interpolate tool position (x, y, z)/kind/feed at a point in the animation timeline."""
    if not frames:
        return 0.0, 0.0, 0.0, "idle", 0.0
    if moment <= frames[0].time:
        frame = frames[0]
        return frame.x, frame.y, frame.z, frame.kind, frame.feed
    if moment >= frames[-1].time:
        frame = frames[-1]
        return frame.x, frame.y, frame.z, frame.kind, frame.feed

    times = [frame.time for frame in frames]
    index = min(max(bisect.bisect_right(times, moment), 1), len(frames) - 1)
    previous_frame, next_frame = frames[index - 1], frames[index]
    span = next_frame.time - previous_frame.time
    fraction = (moment - previous_frame.time) / span if span > 0 else 0.0
    x = previous_frame.x + (next_frame.x - previous_frame.x) * fraction
    y = previous_frame.y + (next_frame.y - previous_frame.y) * fraction
    z = previous_frame.z + (next_frame.z - previous_frame.z) * fraction
    return x, y, z, next_frame.kind, next_frame.feed


def traveled_points(frames: list[Frame], moment: float) -> list[Point]:
    """Return the polyline already traveled up to `moment`, for the progress trail."""
    points = [(frame.x, frame.y) for frame in frames if frame.time <= moment]
    x, y, _z, _kind, _feed = sim_state_at_time(frames, moment)
    if not points or math.hypot(points[-1][0] - x, points[-1][1] - y) > 1e-3:
        points.append((x, y))
    return points
