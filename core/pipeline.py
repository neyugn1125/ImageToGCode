from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import ezdxf

from core.config import (
    DEFAULT_OUTPUT_DIRECTORY,
    DXF_EXTENSION,
    IMAGE_EXTENSIONS,
    MachiningConfig,
    PipelineResult,
    validate_config,
)
from core.dxf.exporter import image_to_dxf
from core.post.fanuc import generate_gcode_from_dxf


def dxf_to_gcode(
    dxf_path: Path,
    output_path: Path,
    config: MachiningConfig,
) -> int:
    """Read a DXF file and write Fanuc-compatible G-code."""
    if not dxf_path.is_file():
        raise RuntimeError(f"Error: Unable to read input DXF: {dxf_path}")
    try:
        document = ezdxf.readfile(dxf_path)
    except (OSError, ezdxf.DXFError) as error:
        raise RuntimeError(f"Error: Unable to read input DXF: {dxf_path}") from error

    gcode, entity_count = generate_gcode_from_dxf(document, config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gcode, encoding="ascii")
    return entity_count


def convert_image_to_gcode(
    input_path: Path,
    output_path: Path,
    config: MachiningConfig,
    *,
    reference_width_mm: float | None = None,
    reference_height_mm: float | None = None,
    pixels_per_mm: float | None = None,
    strip_dimensions: bool = False,
) -> tuple[float, int]:
    """Compatibility wrapper that runs the image -> DXF -> G-code stages."""
    validate_config(config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_path.stem}_dxf_",
        dir=output_path.parent,
    ) as temporary_directory:
        temporary_dxf = Path(temporary_directory) / f"{input_path.stem}.dxf"
        scale_factor, contour_count = image_to_dxf(
            input_path,
            temporary_dxf,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
            strip_dimensions=strip_dimensions,
        )
        converted_count = dxf_to_gcode(temporary_dxf, output_path, config)
    if converted_count != contour_count:
        raise RuntimeError("Error: DXF entity count changed between pipeline stages.")
    return scale_factor, contour_count


def create_run_directory(
    input_path: Path,
    output_root: Path = DEFAULT_OUTPUT_DIRECTORY,
    timestamp: datetime | None = None,
) -> Path:
    """Atomically create a unique ``<filename>_<timestamp>`` run directory."""
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp_text = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    base_name = f"{input_path.stem}_{timestamp_text}"
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"_{counter}"
        candidate = output_root / f"{base_name}{suffix}"
        try:
            candidate.mkdir()
        except FileExistsError:
            counter += 1
            continue
        return candidate


def process_input(
    input_path: Path,
    output_root: Path,
    config: MachiningConfig,
    *,
    timestamp: datetime | None = None,
    reference_width_mm: float | None = None,
    reference_height_mm: float | None = None,
    pixels_per_mm: float | None = None,
    strip_dimensions: bool = False,
) -> PipelineResult:
    """Run image or DXF input through the persistent two-stage workflow."""
    validate_config(config)
    input_path = input_path.expanduser()
    if not input_path.is_file():
        raise RuntimeError(f"Error: Input file not found: {input_path}")
    extension = input_path.suffix.lower()
    if extension not in IMAGE_EXTENSIONS and extension != DXF_EXTENSION:
        allowed = ", ".join(sorted((*IMAGE_EXTENSIONS, DXF_EXTENSION)))
        raise ValueError(
            f"Error: Unsupported input type '{extension or '(none)'}'. "
            f"Allowed extensions: {allowed}."
        )

    run_directory = create_run_directory(input_path, output_root, timestamp)
    dxf_path = run_directory / f"{input_path.stem}.dxf"
    gcode_path = run_directory / f"{input_path.stem}.nc"
    scale_factor: float | None = None
    if extension == DXF_EXTENSION:
        shutil.copy2(input_path, dxf_path)
    else:
        scale_factor, _contour_count = image_to_dxf(
            input_path,
            dxf_path,
            reference_width_mm=reference_width_mm,
            reference_height_mm=reference_height_mm,
            pixels_per_mm=pixels_per_mm,
            strip_dimensions=strip_dimensions,
        )

    entity_count = dxf_to_gcode(dxf_path, gcode_path, config)
    return PipelineResult(
        run_directory=run_directory,
        dxf_path=dxf_path,
        gcode_path=gcode_path,
        entity_count=entity_count,
        scale_factor=scale_factor,
    )
