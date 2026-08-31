from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import ezdxf
import numpy as np

import core
from core.cam import (
    circle_geometry_mm,
    contour_arc_command,
    contour_depth,
    machining_origin,
    order_contours_child_first,
    transform_contour,
)
from core.config import MachiningConfig, validate_config
from core.dxf import _dxf_unit_scale_to_mm, _validated_xy, image_to_dxf
from core.pipeline import convert_image_to_gcode, dxf_to_gcode
from core.post import (
    Frame,
    Segment,
    build_sim_timeline,
    generate_gcode,
    generate_gcode_from_dxf,
    parse_toolpath_segments,
    sim_state_at_time,
    traveled_points,
)
from core.vision import (
    ImageAnalysisResult,
    ImageCalibration,
    analyze_image,
    contour_circularity,
    detect_calibration,
    detect_hollow_calibration,
    extract_contours,
    is_ideal_circle,
    load_binary_image,
)


class DomainModulesTests(unittest.TestCase):
    def test_top_level_package_exports(self) -> None:
        self.assertTrue(hasattr(core, "vision"))
        self.assertTrue(hasattr(core, "cam"))
        self.assertTrue(hasattr(core, "dxf"))
        self.assertTrue(hasattr(core, "post"))
        self.assertTrue(hasattr(core, "MachiningConfig"))
        self.assertTrue(hasattr(core, "convert_image_to_gcode"))

    def test_cam_geometry_and_sequencing(self) -> None:
        contour = np.array([[[10, 10]], [[30, 10]], [[30, 30]], [[10, 30]]], dtype=np.int32)
        x_min, y_max = machining_origin([contour], [0])
        self.assertEqual(10.0, x_min)
        self.assertEqual(30.0, y_max)

        transformed = transform_contour(contour, scale_factor=2.0, x_min=x_min, y_max=y_max)
        self.assertEqual(4, len(transformed))
        self.assertEqual(0.0, transformed[0, 0])
        self.assertEqual(10.0, transformed[0, 1])

        hierarchy = np.array([[[-1, -1, 1, -1], [-1, -1, -1, 0]]], dtype=np.int32)
        self.assertEqual(0, contour_depth(0, hierarchy))
        self.assertEqual(1, contour_depth(1, hierarchy))
        ordered = order_contours_child_first([0, 1], hierarchy)
        self.assertEqual([1, 0], ordered)

    def test_post_gcode_and_sim_parser(self) -> None:
        gcode = (
            "O1000\n"
            "G00 X0.0 Y0.0\n"
            "G01 X10.0 Y0.0 F300.0\n"
            "G02 X20.0 Y0.0 I5.0 J0.0 F300.0\n"
        )
        segments = parse_toolpath_segments(gcode)
        self.assertEqual(3, len(segments))
        self.assertEqual("rapid", segments[0].kind)
        self.assertEqual("linear", segments[1].kind)
        self.assertEqual("arc_cw", segments[2].kind)

        frames, total_time, cut_dist, rap_dist = build_sim_timeline(segments)
        self.assertGreater(total_time, 0.0)
        self.assertGreater(len(frames), 3)

        x, y, z, kind, feed = sim_state_at_time(frames, total_time * 0.5)
        self.assertIsInstance(x, float)
        self.assertIsInstance(y, float)

        trail = traveled_points(frames, total_time * 0.5)
        self.assertGreaterEqual(len(trail), 1)

    def test_end_to_end_pipeline_with_sample_image(self) -> None:
        sample_path = Path("input/1.png")
        if not sample_path.is_file():
            self.skipTest("input/1.png not found")

        with tempfile.TemporaryDirectory() as temp_dir:
            dxf_out = Path(temp_dir) / "test.dxf"
            nc_out = Path(temp_dir) / "test.nc"
            config = MachiningConfig()

            scale_factor, count = image_to_dxf(sample_path, dxf_out)
            self.assertGreater(scale_factor, 0.0)
            self.assertGreater(count, 0)
            self.assertTrue(dxf_out.is_file())

            entities = dxf_to_gcode(dxf_out, nc_out, config)
            self.assertEqual(count, entities)
            self.assertTrue(nc_out.is_file())
            self.assertIn("O1000", nc_out.read_text())


if __name__ == "__main__":
    unittest.main()
