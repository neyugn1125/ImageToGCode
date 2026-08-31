from __future__ import annotations

import math

import ezdxf
from ezdxf import units


def _dxf_unit_scale_to_mm(document: ezdxf.document.Drawing) -> float:
    """Return the factor that maps the DXF's declared units to millimeters."""
    source_units = int(document.units)
    if source_units in (0, units.MM):
        return 1.0
    try:
        factor = float(units.conversion_factor(source_units, units.MM))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError(
            f"Error: Unsupported DXF unit code: {source_units}."
        ) from error
    if not math.isfinite(factor) or factor <= 0:
        raise RuntimeError(f"Error: Invalid DXF unit code: {source_units}.")
    return factor


def _validated_xy(x_value: float, y_value: float) -> tuple[float, float]:
    x = float(x_value)
    y = float(y_value)
    if not math.isfinite(x) or not math.isfinite(y):
        raise RuntimeError("Error: DXF entity contains non-finite coordinates.")
    return x, y
