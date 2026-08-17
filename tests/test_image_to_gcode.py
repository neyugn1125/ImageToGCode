from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from run import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    MULTIPLE_CALIBRATION_ERROR,
    MachiningConfig,
    convert_image_to_gcode,
    detect_calibration,
    extract_contours,
    generate_gcode,
    machining_origin,
    main,
    order_contours_child_first,
    parse_args,
    transform_contour,
    valid_contour_indices,
    validate_config,
)


def write_test_image(path: Path, *, calibration_count: int = 1) -> None:
    image = np.full((320, 400, 3), 255, dtype=np.uint8)
    if calibration_count >= 1:
        cv2.rectangle(image, (20, 20), (69, 69), (0, 0, 0), -1)
    if calibration_count >= 2:
        cv2.rectangle(image, (320, 20), (369, 69), (0, 0, 0), -1)

    cv2.rectangle(image, (100, 80), (300, 260), (0, 0, 0), -1)
    cv2.circle(image, (200, 170), 35, (255, 255, 255), -1)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not create test image: {path}")


class ImageToGcodeTests(unittest.TestCase):
    def test_cli_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(DEFAULT_INPUT_PATH, args.input)
        self.assertEqual(DEFAULT_OUTPUT_PATH, args.output)
        self.assertEqual(-5.0, args.cut_depth)
        self.assertEqual(1500, args.spindle_speed)

    def test_detects_scale_origin_and_child_first_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "drawing.png"
            write_test_image(image_path)
            contours, hierarchy = extract_contours(image_path)
            valid = valid_contour_indices(contours)
            calibration_index, scale_factor = detect_calibration(contours, valid)
            machining = [index for index in valid if index != calibration_index]

            self.assertAlmostEqual(5.0, scale_factor, places=6)
            ordered = order_contours_child_first(machining, hierarchy)
            self.assertIsNotNone(hierarchy)
            self.assertGreater(
                int(hierarchy[0, ordered[0], 3]),
                -1,
                "The internal hole must be emitted before its parent",
            )

            x_min, y_max = machining_origin(contours, machining)
            transformed = [
                transform_contour(contours[index], scale_factor, x_min, y_max)
                for index in machining
            ]
            all_points = np.vstack(transformed)
            self.assertAlmostEqual(0.0, float(np.min(all_points[:, 0])))
            self.assertAlmostEqual(0.0, float(np.min(all_points[:, 1])))

    def test_multiple_calibration_squares_stop_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "ambiguous.png"
            write_test_image(image_path, calibration_count=2)
            contours, _ = extract_contours(image_path)
            valid = valid_contour_indices(contours)

            with self.assertRaisesRegex(
                RuntimeError, f"^{MULTIPLE_CALIBRATION_ERROR}$"
            ):
                detect_calibration(contours, valid)

    def test_missing_calibration_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-calibration.png"
            write_test_image(image_path, calibration_count=0)
            contours, _ = extract_contours(image_path)

            with self.assertRaisesRegex(RuntimeError, "Không tìm thấy ô hiệu chuẩn"):
                detect_calibration(contours, valid_contour_indices(contours))

    def test_unreadable_image_is_an_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Không thể đọc ảnh đầu vào"):
            extract_contours(Path("does-not-exist.png"))

    def test_config_validation(self) -> None:
        config = MachiningConfig()
        invalid_configs = [
            replace(config, cut_depth=0.0),
            replace(config, plunge_feed=0.0),
            replace(config, cut_feed=-1.0),
            replace(config, spindle_speed=0),
            replace(config, tool_number=0),
            replace(config, tool_offset=0),
            replace(config, program_number=0),
            replace(config, safe_z=2.0),
            replace(config, cut_feed=float("nan")),
            replace(config, safe_z=float("inf")),
        ]
        for invalid in invalid_configs:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_config(invalid)

    def test_gcode_header_footer_overrides_and_closed_path(self) -> None:
        contour = np.array([[[10, 20]], [[20, 20]], [[20, 30]]], dtype=np.int32)
        config = MachiningConfig(
            cut_depth=-2.5,
            plunge_feed=80.0,
            cut_feed=250.0,
            spindle_speed=2200,
            safe_z=40.0,
            approach_z=1.5,
            tool_number=3,
            tool_offset=4,
            program_number=1234,
        )
        gcode = generate_gcode([contour], [0], 2.0, 10.0, 30.0, config)

        self.assertTrue(gcode.startswith("O1234 (Profile Milling)\nG21 (Metric)"))
        self.assertIn("T3 M06 (Tool change to T3)", gcode)
        self.assertIn("G43 H4 (Tool length compensation)", gcode)
        self.assertIn("M03 S2200 (Spindle ON, 2200 RPM)", gcode)
        self.assertIn("G01 Z-2.500 F80.000 (Plunge)", gcode)
        self.assertIn("G01 X0.000 Y5.000 F250.000 (Close contour)", gcode)
        self.assertTrue(gcode.endswith("M30 (End of program)\n"))

    def test_end_to_end_smoke_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "drawing.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path)

            result = main(
                [
                    "--input",
                    str(image_path),
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(0, result)
            gcode = output_path.read_text(encoding="ascii")
            self.assertIn("O1000 (Profile Milling)", gcode)
            self.assertNotIn("nan", gcode.lower())
            self.assertNotIn("inf", gcode.lower())
            self.assertNotIn("G02 ", gcode)
            self.assertNotIn("G03 ", gcode)
            self.assertGreaterEqual(gcode.count("(Close contour)"), 2)

    def test_output_parent_directory_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "drawing.png"
            output_path = Path(directory) / "output" / "nested" / "output.nc"
            write_test_image(image_path)

            result = main(
                ["--input", str(image_path), "--output", str(output_path)]
            )

            self.assertEqual(0, result)
            self.assertTrue(output_path.is_file())

    def test_convert_does_not_emit_calibration_contour(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "drawing.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path)

            scale_factor, contour_count = convert_image_to_gcode(
                image_path, output_path, MachiningConfig()
            )

            self.assertEqual(5.0, scale_factor)
            self.assertEqual(2, contour_count)
            self.assertEqual(
                contour_count,
                output_path.read_text(encoding="ascii").count("(Close contour)"),
            )


if __name__ == "__main__":
    unittest.main()
