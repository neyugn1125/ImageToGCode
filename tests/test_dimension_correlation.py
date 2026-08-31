from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from core.cam.correlation import auto_correlate_drawing_scale
from core.config import MachiningConfig
from core.pipeline import convert_image_to_gcode
from core.vision import (
    detect_arrowheads,
    detect_dimension_texts,
    detect_lines_and_corners,
    load_binary_image,
)


class DimensionCorrelationTests(unittest.TestCase):
    def test_arrowhead_detection_on_image_png(self) -> None:
        img_path = Path("input/image.png")
        if not img_path.is_file():
            self.skipTest("input/image.png not found")

        binary = load_binary_image(img_path)
        arrowheads = detect_arrowheads(binary)
        self.assertGreaterEqual(len(arrowheads), 4)

        for arrow in arrowheads:
            self.assertIsInstance(arrow.center, tuple)
            self.assertIsInstance(arrow.tip, tuple)
            self.assertIsInstance(arrow.direction, tuple)
            # Direction vector should be normalized
            norm = np.hypot(arrow.direction[0], arrow.direction[1])
            self.assertAlmostEqual(1.0, norm, places=1)

    def test_text_detection_on_image_png(self) -> None:
        img_path = Path("input/image.png")
        if not img_path.is_file():
            self.skipTest("input/image.png not found")

        binary = load_binary_image(img_path)
        texts = detect_dimension_texts(binary)
        self.assertGreaterEqual(len(texts), 4)

        # Check that we found numeric values
        values = [t.value for t in texts if t.value is not None]
        self.assertGreater(len(values), 0)

    def test_line_and_corner_detection(self) -> None:
        img_path = Path("input/image.png")
        if not img_path.is_file():
            self.skipTest("input/image.png not found")

        binary = load_binary_image(img_path)
        lines, corners = detect_lines_and_corners(binary)
        self.assertGreater(len(lines), 5)
        self.assertGreater(len(corners), 4)

    def test_auto_correlate_scale_and_convert_image_png(self) -> None:
        img_path = Path("input/image.png")
        if not img_path.is_file():
            self.skipTest("input/image.png not found")

        binary = load_binary_image(img_path)
        result = auto_correlate_drawing_scale(binary, nominal_dimension_mm=100.0)
        self.assertIsNotNone(result)
        scale_factor, width_mm, height_mm = result
        self.assertAlmostEqual(4.8, scale_factor, delta=0.2)
        self.assertEqual(100.0, width_mm)
        self.assertEqual(100.0, height_mm)

        with tempfile.TemporaryDirectory() as td:
            out_nc = Path(td) / "image.nc"
            scale, entity_count = convert_image_to_gcode(
                img_path,
                out_nc,
                MachiningConfig(),
                reference_width_mm=100.0,
                reference_height_mm=100.0,
                strip_dimensions=True,
            )
            self.assertAlmostEqual(4.8, scale, delta=0.2)
            self.assertEqual(4, entity_count)  # 1 outer plate + 3 holes
            self.assertTrue(out_nc.is_file())


if __name__ == "__main__":
    unittest.main()
