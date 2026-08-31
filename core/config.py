from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path


DEFAULT_INPUT_PATH = Path("input") / "input.png"
DEFAULT_OUTPUT_PATH = Path("output") / "output.nc"
DEFAULT_OUTPUT_DIRECTORY = Path("output")
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
DXF_EXTENSION = ".dxf"


@dataclass(frozen=True)
class MachiningConfig:
    """Machining values used to render the Fanuc program."""

    cut_depth: float = -5.0
    plunge_feed: float = 100.0
    cut_feed: float = 300.0
    spindle_speed: int = 1500
    safe_z: float = 50.0
    approach_z: float = 2.0
    tool_number: int = 1
    tool_offset: int = 1
    program_number: int = 1000


@dataclass(frozen=True)
class PipelineResult:
    """Artifacts and conversion metadata produced by one pipeline run."""

    run_directory: Path
    dxf_path: Path
    gcode_path: Path
    entity_count: int
    scale_factor: float | None


def config_from_args(args: argparse.Namespace) -> MachiningConfig:
    """Build a MachiningConfig from parsed command-line arguments."""
    config = MachiningConfig(
        cut_depth=args.cut_depth,
        plunge_feed=args.plunge_feed,
        cut_feed=args.cut_feed,
        spindle_speed=args.spindle_speed,
        safe_z=args.safe_z,
        approach_z=args.approach_z,
        tool_number=args.tool_number,
        tool_offset=args.tool_offset,
        program_number=args.program_number,
    )
    validate_config(config)
    return config


def validate_config(config: MachiningConfig) -> None:
    """Check configuration sanity before starting any conversion."""
    float_fields = (
        ("cut_depth", config.cut_depth),
        ("plunge_feed", config.plunge_feed),
        ("cut_feed", config.cut_feed),
        ("safe_z", config.safe_z),
        ("approach_z", config.approach_z),
    )
    for name, value in float_fields:
        if not math.isfinite(value):
            raise ValueError(f"{name} ({value}) must be a finite number")

    if config.safe_z <= config.approach_z:
        raise ValueError(
            f"safe_z ({config.safe_z}) must be greater than approach_z ({config.approach_z})"
        )
    if config.approach_z <= 0:
        raise ValueError(f"approach_z ({config.approach_z}) must be positive")
    if config.cut_depth >= 0:
        raise ValueError(f"cut_depth ({config.cut_depth}) must be negative")
    if config.plunge_feed <= 0:
        raise ValueError(f"plunge_feed ({config.plunge_feed}) must be positive")
    if config.cut_feed <= 0:
        raise ValueError(f"cut_feed ({config.cut_feed}) must be positive")
    if config.spindle_speed <= 0:
        raise ValueError(f"spindle_speed ({config.spindle_speed}) must be positive")
    if config.tool_number < 1:
        raise ValueError(f"tool_number ({config.tool_number}) must be >= 1")
    if config.tool_offset < 1:
        raise ValueError(f"tool_offset ({config.tool_offset}) must be >= 1")
    if not (1 <= config.program_number <= 9999):
        raise ValueError(
            f"program_number ({config.program_number}) must be between 1 and 9999"
        )
