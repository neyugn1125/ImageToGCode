from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import cv2
import ezdxf
import numpy as np
from ezdxf import units

from run import (
    MachiningConfig,
    detect_hollow_calibration,
    dxf_to_gcode,
    image_to_dxf,
    process_input,
)


def square_contour(x: int, y: int, side: int) -> np.ndarray:
    return np.array(
        [
            [[x, y]],
            [[x + side, y]],
            [[x + side, y + side]],
            [[x, y + side]],
        ],
        dtype=np.int32,
    )


def write_hollow_calibration_image(path: Path) -> None:
    image = np.full((340, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 260), (70, 310), (0, 0, 0), thickness=6)
    cv2.rectangle(image, (130, 60), (350, 230), (0, 0, 0), thickness=-1)
    cv2.circle(image, (240, 145), 35, (255, 255, 255), thickness=-1)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not create test image: {path}")


class DxfPipelineTests(unittest.TestCase):
    def test_hollow_calibration_uses_bottom_left_and_stroke_centerline(self) -> None:
        contours = [
            square_contour(200, 20, 50),
            square_contour(205, 25, 40),
            square_contour(20, 200, 60),
            square_contour(25, 205, 50),
        ]
        hierarchy = np.array(
            [
                [
                    [2, -1, 1, -1],
                    [-1, -1, -1, 0],
                    [-1, 0, 3, -1],
                    [-1, -1, -1, 2],
                ]
            ],
            dtype=np.int32,
        )

        calibration = detect_hollow_calibration(contours, hierarchy)

        self.assertEqual(2, calibration.outer_index)
        self.assertEqual((2, 3), calibration.excluded_indices)
        # cv2.boundingRect includes both endpoint pixels: (61 + 51) / 2 / 10.
        self.assertAlmostEqual(5.6, calibration.scale_factor)

    def test_image_stage_exports_mm_circle_and_closed_polyline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "part.png"
            dxf_path = Path(directory) / "part.dxf"
            write_hollow_calibration_image(image_path)

            scale_factor, entity_count = image_to_dxf(image_path, dxf_path)
            document = ezdxf.readfile(dxf_path)
            entities = list(document.modelspace())

            self.assertAlmostEqual(5.0, scale_factor, delta=0.2)
            self.assertEqual(units.MM, document.units)
            self.assertEqual(2, entity_count)
            self.assertEqual(
                {"CIRCLE", "LWPOLYLINE"},
                {entity.dxftype() for entity in entities},
            )
            polyline = next(e for e in entities if e.dxftype() == "LWPOLYLINE")
            self.assertTrue(polyline.closed)

    def test_dxf_post_processor_splits_circle_and_closes_polyline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dxf_path = Path(directory) / "profile.dxf"
            output_path = Path(directory) / "profile.nc"
            document = ezdxf.new("R2010")
            document.units = units.MM
            modelspace = document.modelspace()
            modelspace.add_circle((10.0, 20.0), 5.0)
            modelspace.add_lwpolyline(
                [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)],
                close=False,
            )
            document.saveas(dxf_path)

            entity_count = dxf_to_gcode(
                dxf_path,
                output_path,
                MachiningConfig(),
            )
            gcode = output_path.read_text(encoding="ascii")
            arc_lines = [
                line for line in gcode.splitlines() if line.startswith("G02 ")
            ]

            self.assertEqual(2, entity_count)
            self.assertEqual(2, len(arc_lines))
            self.assertIn("X5.000 Y20.000 I-5.000 J0.000", arc_lines[0])
            self.assertIn("X15.000 Y20.000 I5.000 J0.000", arc_lines[1])
            self.assertIn(
                "G01 X0.000 Y0.000 F300.000 (Close contour)",
                gcode,
            )
            self.assertEqual(2, gcode.count("(Retract)"))
            self.assertTrue(gcode.endswith("M30 (End of program)\n"))

    def test_direct_dxf_input_is_copied_into_unique_run_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "fixture.dxf"
            output_root = Path(directory) / "output"
            document = ezdxf.new("R2010")
            document.units = units.MM
            document.modelspace().add_circle((5.0, 5.0), 2.0)
            document.saveas(source_path)
            source_bytes = source_path.read_bytes()
            timestamp = datetime(2026, 8, 23, 12, 34, 56)

            first = process_input(
                source_path,
                output_root,
                MachiningConfig(),
                timestamp=timestamp,
            )
            second = process_input(
                source_path,
                output_root,
                MachiningConfig(),
                timestamp=timestamp,
            )

            self.assertEqual("fixture_20260823_123456", first.run_directory.name)
            self.assertEqual("fixture_20260823_123456_2", second.run_directory.name)
            self.assertEqual(source_bytes, first.dxf_path.read_bytes())
            self.assertTrue(first.gcode_path.is_file())
            self.assertIsNone(first.scale_factor)
            self.assertEqual(1, first.entity_count)

    def test_extract_dxf_preview_geometry(self) -> None:
        from core.dxf import extract_dxf_preview_geometry

        document = ezdxf.new("R2010")
        document.units = units.MM
        msp = document.modelspace()
        msp.add_line((0.0, 0.0), (50.0, 0.0))
        msp.add_circle((25.0, 25.0), 10.0)
        msp.add_arc((25.0, 25.0), 5.0, 0.0, 180.0)
        msp.add_lwpolyline([(0, 0), (10, 10), (20, 0)], close=True)

        preview = extract_dxf_preview_geometry(document)
        self.assertEqual(4, preview.entity_count)
        self.assertEqual(1, len(preview.lines))
        self.assertEqual(1, len(preview.circles))
        self.assertEqual(1, len(preview.arcs))
        self.assertEqual(1, len(preview.polylines))
        self.assertGreater(preview.width_mm, 0)
        self.assertGreater(preview.height_mm, 0)
        p_dict = preview.to_dict()
        self.assertIn("lines", p_dict)
        self.assertIn("circles", p_dict)
        self.assertIn("arcs", p_dict)
        self.assertIn("polylines", p_dict)


if __name__ == "__main__":
    unittest.main()

