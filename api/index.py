"""FastAPI Serverless Application for ImageToGCode."""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Configure read-only serverless environment cache paths (e.g. AWS Lambda on Vercel)
os.environ["EZDXF_DISABLE_CONFIG_FILE"] = "1"
os.environ["XDG_CACHE_HOME"] = "/tmp"
os.environ["EZDXF_CACHE_DIRECTORY"] = "/tmp/.cache/ezdxf"
os.environ["MPLCONFIGDIR"] = "/tmp/.matplotlib"

# Ensure project root is in sys.path when running in serverless environments
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    ConversionResponse,
    HealthResponse,
    ImageAnalysisResponse,
    SimulationTimelineModel,
    ToolpathSegmentModel,
)
from core.config import MachiningConfig, validate_config
from core.dxf import image_to_dxf
from core.pipeline import convert_image_to_gcode
from core.post import build_sim_timeline, parse_toolpath_segments
from core.vision import analyze_image


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

app = FastAPI(
    title="Image to G-Code API",
    description="Serverless API for 2D CNC contour milling and CAD/CAM simulation",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Enable CORS for all origins (supports local development and Vercel deployments)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def normalize_vercel_paths(request: Request, call_next):
    """Normalize paths if Vercel serverless forwards internal function path."""
    path = request.scope.get("path", "")
    if path == "/api/index.py":
        request.scope["path"] = "/api"
    elif path.startswith("/api/index.py/"):
        request.scope["path"] = path.replace("/api/index.py", "/api", 1)
    return await call_next(request)


def _validate_image_file(file: UploadFile) -> str:
    """Validate uploaded file extension and return clean suffix."""
    filename = file.filename or "input.png"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported image type: '{suffix or '(no extension)'}'. "
                f"Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return suffix


def _save_upload_to_temp(file_bytes: bytes, suffix: str) -> Path:
    """Save raw upload bytes to a temporary file and verify it can be read by OpenCV."""
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image file is empty.",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    # Verify image integrity
    img = cv2.imread(str(tmp_path))
    if img is None:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image or is corrupted.",
        )

    return tmp_path


# Define API Router to handle both `/api/...` and `...` prefixes transparently
api_router = APIRouter()


@api_router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Return API health and service metadata."""
    return HealthResponse()


@api_router.post("/analyze", response_model=ImageAnalysisResponse, tags=["Vision"])
async def analyze_uploaded_image(
    image: UploadFile = File(..., description="Source CAD/drawing image"),
    strip_dimensions: bool = Form(default=False, description="Filter dimension lines/text"),
    reference_width_mm: Optional[float] = Form(default=None, description="Known width in mm"),
    reference_height_mm: Optional[float] = Form(default=None, description="Known height in mm"),
    pixels_per_mm: Optional[float] = Form(default=None, description="Explicit scale (px/mm)"),
) -> ImageAnalysisResponse:
    """Inspect and calibrate uploaded drawing image without generating G-code."""
    suffix = _validate_image_file(image)
    file_bytes = await image.read()
    temp_img_path = _save_upload_to_temp(file_bytes, suffix)

    try:
        analysis = analyze_image(
            temp_img_path,
            strip_dimensions=strip_dimensions,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
        )

        h, w = analysis.image_shape
        return ImageAnalysisResponse(
            image_width=w,
            image_height=h,
            scale_factor=analysis.scale_factor,
            calibration_bbox_px=list(analysis.calibration_bbox_px) if analysis.calibration_bbox_px else None,
            machining_bbox_px=list(analysis.machining_bbox_px) if analysis.machining_bbox_px else None,
            g54_origin_px=[float(analysis.g54_origin_px[0]), float(analysis.g54_origin_px[1])] if analysis.g54_origin_px else None,
            contour_count=analysis.contour_count,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    finally:
        try:
            temp_img_path.unlink()
        except OSError:
            pass


@api_router.post("/convert", response_model=ConversionResponse, tags=["CAM & Post-Processor"])
async def convert_image(
    image: UploadFile = File(..., description="Source CAD/drawing image"),
    cut_depth: float = Form(default=-5.0, description="Target cut depth Z (mm)"),
    plunge_feed: float = Form(default=100.0, description="Plunge feed rate (mm/min)"),
    cut_feed: float = Form(default=300.0, description="Cutting feed rate (mm/min)"),
    spindle_speed: int = Form(default=1500, description="Spindle RPM"),
    safe_z: float = Form(default=50.0, description="Retract clearance Z (mm)"),
    approach_z: float = Form(default=2.0, description="Rapid approach Z (mm)"),
    tool_diameter: float = Form(default=3.0, description="Cutter diameter Ø (mm)"),
    tool_number: int = Form(default=1, description="Tool number"),
    tool_offset: int = Form(default=1, description="Tool length offset H"),
    program_number: int = Form(default=1000, description="Program number O"),
    strip_dimensions: bool = Form(default=False, description="Remove dimension lines"),
    reference_width_mm: Optional[float] = Form(default=None, description="Known width in mm"),
    reference_height_mm: Optional[float] = Form(default=None, description="Known height in mm"),
    pixels_per_mm: Optional[float] = Form(default=None, description="Scale factor px/mm"),
) -> ConversionResponse:
    """Execute full pipeline: vision analysis -> CAM sequencing -> Fanuc G-code + DXF."""
    suffix = _validate_image_file(image)
    file_bytes = await image.read()
    temp_img_path = _save_upload_to_temp(file_bytes, suffix)

    # Validate machining configuration
    try:
        config = MachiningConfig(
            cut_depth=cut_depth,
            plunge_feed=plunge_feed,
            cut_feed=cut_feed,
            spindle_speed=spindle_speed,
            safe_z=safe_z,
            approach_z=approach_z,
            tool_number=tool_number,
            tool_offset=tool_offset,
            program_number=program_number,
        )
        validate_config(config)
    except ValueError as error:
        try:
            temp_img_path.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    temp_nc_path: Optional[Path] = None
    temp_dxf_path: Optional[Path] = None

    try:
        # 1. Run vision analysis
        analysis = analyze_image(
            temp_img_path,
            strip_dimensions=strip_dimensions,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
        )

        # 2. Generate G-code
        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp_nc:
            temp_nc_path = Path(tmp_nc.name)

        scale_factor, _contour_count = convert_image_to_gcode(
            temp_img_path,
            temp_nc_path,
            config,
            strip_dimensions=strip_dimensions,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
        )

        gcode_content = temp_nc_path.read_text(encoding="ascii")

        # 3. Generate DXF drawing
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp_dxf:
            temp_dxf_path = Path(tmp_dxf.name)

        image_to_dxf(
            temp_img_path,
            temp_dxf_path,
            strip_dimensions=strip_dimensions,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
        )
        dxf_bytes = temp_dxf_path.read_bytes()
        dxf_base64 = base64.b64encode(dxf_bytes).decode("ascii")

        # 4. Parse simulation segments
        segments = parse_toolpath_segments(gcode_content)
        _frames, total_time, cut_dist, rapid_dist = build_sim_timeline(segments)

        all_points = [point for segment in segments for point in segment.points]
        min_x = min((pt[0] for pt in all_points), default=0.0)
        max_x = max((pt[0] for pt in all_points), default=0.0)
        min_y = min((pt[1] for pt in all_points), default=0.0)
        max_y = max((pt[1] for pt in all_points), default=0.0)

        segment_models = [
            ToolpathSegmentModel(
                kind=seg.kind,
                points=[[float(pt[0]), float(pt[1])] for pt in seg.points],
                feed=float(seg.feed),
                z_depth=float(seg.z_depth),
            )
            for seg in segments
        ]

        filename_base = Path(image.filename or "drawing").stem

        h, w = analysis.image_shape
        return ConversionResponse(
            success=True,
            analysis=ImageAnalysisResponse(
                image_width=w,
                image_height=h,
                scale_factor=scale_factor,
                calibration_bbox_px=list(analysis.calibration_bbox_px) if analysis.calibration_bbox_px else None,
                machining_bbox_px=list(analysis.machining_bbox_px) if analysis.machining_bbox_px else None,
                g54_origin_px=[float(analysis.g54_origin_px[0]), float(analysis.g54_origin_px[1])] if analysis.g54_origin_px else None,
                contour_count=analysis.contour_count,
            ),
            segments=segment_models,
            timeline=SimulationTimelineModel(
                total_time_s=round(total_time, 2),
                cut_distance_mm=round(cut_dist, 2),
                rapid_distance_mm=round(rapid_dist, 2),
                envelope_width_mm=round(max_x - min_x, 2),
                envelope_height_mm=round(max_y - min_y, 2),
                min_x_mm=round(min_x, 2),
                max_x_mm=round(max_x, 2),
                min_y_mm=round(min_y, 2),
                max_y_mm=round(max_y, 2),
            ),
            gcode=gcode_content,
            dxf_base64=dxf_base64,
            filename_base=filename_base,
        )

    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    finally:
        for p in (temp_img_path, temp_nc_path, temp_dxf_path):
            if p is not None:
                try:
                    p.unlink()
                except OSError:
                    pass


# Mount API Router under both `/api` and root `/` so all Vercel rewrite patterns work seamlessly
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="", include_in_schema=False)
app.include_router(api_router, prefix="/api/index.py", include_in_schema=False)

# Mount static files from public/ to serve frontend on / when running locally or on server
PUBLIC_DIR = PROJECT_ROOT / "public"
if PUBLIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="static")
