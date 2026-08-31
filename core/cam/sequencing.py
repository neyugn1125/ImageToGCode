from __future__ import annotations

from typing import Sequence

import numpy as np


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    """Calculate the nesting depth of a contour in OpenCV's RETR_TREE."""
    depth = 0
    parent = int(hierarchy[0, index, 3])
    visited: set[int] = set()
    while parent != -1:
        if parent in visited:
            raise RuntimeError("Error: Detected an invalid loop in the contour hierarchy.")
        visited.add(parent)
        depth += 1
        parent = int(hierarchy[0, parent, 3])
    return depth


def order_contours_child_first(
    contour_indices: Sequence[int], hierarchy: np.ndarray | None
) -> list[int]:
    """Order contours from innermost holes outward to parent perimeters."""
    if hierarchy is None:
        return list(contour_indices)
    # Python's stable sort preserves OpenCV order among contours at equal depth.
    return sorted(
        contour_indices,
        key=lambda index: -contour_depth(index, hierarchy),
    )
