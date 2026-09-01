"""Pydantic schemas for ImageToGCode API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Healthcheck response model."""

    status: str = Field(default="ok", description="Server health status")
    version: str = Field(default="1.0.0", description="API version")
    service: str = Field(default="ImageToGCode CNC API", description="Service name")


class DxfPreviewModel(BaseModel):
    """2D CAD vector geometry for DXF preview rendering."""

    lines: List[Dict[str, List[float]]] = Field(default_factory=list, description="Lines [[x1, y1], [x2, y2]]")
    circles: List[Dict[str, Any]] = Field(default_factory=list, description="Circles {center, radius}")
    arcs: List[Dict[str, Any]] = Field(default_factory=list, description="Arcs {center, radius, start_angle, end_angle}")
    polylines: List[Dict[str, Any]] = Field(default_factory=list, description="Polylines {points, closed}")
    min_x: float = Field(default=0.0, description="Min X in mm")
    max_x: float = Field(default=0.0, description="Max X in mm")
    min_y: float = Field(default=0.0, description="Min Y in mm")
    max_y: float = Field(default=0.0, description="Max Y in mm")
    width_mm: float = Field(default=0.0, description="Bounding envelope width in mm")
    height_mm: float = Field(default=0.0, description="Bounding envelope height in mm")
    entity_count: int = Field(default=0, description="Total entity count")


class ImageAnalysisResponse(BaseModel):
    """Analysis results for source image or DXF CAD file."""

    image_width: int
    image_height: int
    scale_factor: Optional[float] = None
    calibration_bbox_px: Optional[List[int]] = None  # [x, y, w, h]
    machining_bbox_px: Optional[List[int]] = None    # [x1, y1, x2, y2]
    g54_origin_px: Optional[List[float]] = None      # [x, y]
    contour_count: int = 0
    dxf_preview: Optional[DxfPreviewModel] = Field(default=None, description="2D CAD vector preview if input is DXF")


class ToolpathSegmentModel(BaseModel):
    """Single CAD/CAM toolpath move segment for 2D visualizer."""

    kind: str = Field(description="Movement type: 'rapid', 'linear', 'arc_cw', 'arc_ccw'")
    points: List[List[float]] = Field(description="List of [x, y] coordinates in mm")
    feed: float = Field(description="Feed rate in mm/min")
    z_depth: float = Field(default=0.0, description="Target Z depth in mm")


class SimulationTimelineModel(BaseModel):
    """Machining simulation summary metrics."""

    total_time_s: float
    cut_distance_mm: float
    rapid_distance_mm: float
    envelope_width_mm: float
    envelope_height_mm: float
    min_x_mm: float
    max_x_mm: float
    min_y_mm: float
    max_y_mm: float


class ConversionResponse(BaseModel):
    """Full pipeline result containing analysis, toolpath simulation, G-code, and DXF."""

    success: bool = True
    analysis: ImageAnalysisResponse
    segments: List[ToolpathSegmentModel]
    timeline: SimulationTimelineModel
    gcode: str = Field(description="Raw Fanuc profile milling G-code")
    dxf_base64: Optional[str] = Field(default=None, description="Base64-encoded DXF CAD drawing")
    filename_base: str = Field(default="drawing", description="Base filename for downloads")
