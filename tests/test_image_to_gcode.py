from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from run import (
    CIRCULARITY_THRESHOLD,
    CONTOUR_SMOOTHING_EPSILON_RATIO,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    MULTIPLE_CALIBRATION_ERROR,
    MachiningConfig,
    circle_geometry_mm,
    contour_circularity,
    convert_image_to_gcode,
    detect_calibration,
    extract_contours,
    generate_gcode,
    is_ideal_circle,
    machining_origin,
    main,
    order_contours_child_first,
    parse_args,
    prune_stroke_ring_artifacts,
    smooth_contours,
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


def write_dimensioned_test_image(path: Path) -> None:
    """A part drawn as unfilled outline strokes (not solid fills), with thin
    dimension/extension lines and text overlaid -- one extension line touches
    the part outline directly, mirroring real CAD-exported drawings."""
    image = np.full((360, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (69, 69), (0, 0, 0), -1)  # 10x10 mm calibration square
    cv2.rectangle(image, (100, 80), (300, 260), (0, 0, 0), thickness=6)  # outline part
    cv2.circle(image, (200, 170), 35, (0, 0, 0), thickness=6)  # outline hole
    cv2.line(image, (100, 20), (100, 79), (0, 0, 0), thickness=2)  # extension line touching the outline
    cv2.line(image, (60, 300), (340, 300), (0, 0, 0), thickness=2)  # dimension line
    cv2.putText(
        image, "200", (170, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA
    )
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not create test image: {path}")


def write_filled_dimension_extension_image(path: Path) -> None:
    """A filled plate with an extension line joined to its left boundary."""
    image = np.full((360, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (69, 69), (0, 0, 0), -1)
    cv2.rectangle(image, (100, 80), (300, 260), (0, 0, 0), -1)
    cv2.circle(image, (200, 170), 35, (255, 255, 255), -1)
    # Three pixels is a common result after anti-aliased source artwork is
    # thresholded; it must still be treated as an annotation, not part stock.
    cv2.line(image, (100, 20), (100, 79), (0, 0, 0), 3)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not create test image: {path}")


def make_circle_contour(
    center: tuple[float, float] = (50.0, 50.0), radius: float = 20.0
) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * np.pi, 72, endpoint=False)
    points = np.column_stack(
        (
            center[0] + radius * np.cos(angles),
            center[1] + radius * np.sin(angles),
        )
    )
    return np.rint(points).astype(np.int32).reshape(-1, 1, 2)


class ImageToGcodeTests(unittest.TestCase):
    def test_cli_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(DEFAULT_INPUT_PATH, args.input)
        self.assertEqual(DEFAULT_OUTPUT_PATH, args.output)
        self.assertEqual(-5.0, args.cut_depth)
        self.assertEqual(1500, args.spindle_speed)

    def test_shape_recognition_classifies_circle_but_not_rectangle(self) -> None:
        circle = make_circle_contour()
        rectangle = np.array(
            [[[0, 0]], [[80, 0]], [[80, 30]], [[0, 30]]], dtype=np.int32
        )

        self.assertGreaterEqual(contour_circularity(circle), CIRCULARITY_THRESHOLD)
        self.assertTrue(is_ideal_circle(circle))
        self.assertLess(contour_circularity(rectangle), CIRCULARITY_THRESHOLD)
        self.assertFalse(is_ideal_circle(rectangle))

    def test_contour_smoothing_uses_configured_epsilon(self) -> None:
        contour = make_circle_contour(radius=40.0)
        expected = cv2.approxPolyDP(
            contour,
            CONTOUR_SMOOTHING_EPSILON_RATIO * cv2.arcLength(contour, True),
            True,
        )

        smoothed = smooth_contours([contour])

        self.assertEqual(1, len(smoothed))
        np.testing.assert_array_equal(expected, smoothed[0])
        self.assertLessEqual(len(smoothed[0]), len(contour))

    def test_bracket_tab_smooths_rasterized_triangle(self) -> None:
        image_path = Path("input/samples/06_bracket_tab.png")

        contours, _ = extract_contours(image_path)
        valid = valid_contour_indices(contours)
        calibration_index, _ = detect_calibration(contours, valid)
        machining = [index for index in valid if index != calibration_index]
        triangle_index = min(
            machining, key=lambda index: contour_circularity(contours[index])
        )

        # The source triangle has raster stair steps, but its toolpath should
        # contain the three intended vertices rather than every pixel step.
        self.assertEqual(3, len(contours[triangle_index]))

    def test_ideal_circle_uses_two_half_circle_ij_arcs(self) -> None:
        circle = make_circle_contour(center=(50.0, 60.0), radius=20.0)
        center_x, center_y, radius = circle_geometry_mm(
            circle, scale_factor=2.0, x_min=10.0, y_max=100.0
        )
        expected_radius = cv2.minEnclosingCircle(circle)[1] / 2.0
        self.assertAlmostEqual(20.0, center_x, places=3)
        self.assertAlmostEqual(20.0, center_y, places=3)
        self.assertAlmostEqual(expected_radius, radius, places=6)

        gcode = generate_gcode(
            [circle],
            [0],
            scale_factor=2.0,
            x_min=10.0,
            y_max=100.0,
            config=MachiningConfig(),
        )
        arc_lines = [
            line for line in gcode.splitlines() if line.startswith(("G02 ", "G03 "))
        ]
        self.assertEqual(2, len(arc_lines))
        self.assertTrue(all(line.startswith("G02 ") for line in arc_lines))
        self.assertIn(f"I-{expected_radius:.3f} J0.000", arc_lines[0])
        self.assertIn(f"I{expected_radius:.3f} J0.000", arc_lines[1])
        self.assertNotIn("G01 X", gcode)

    def test_circle_arc_direction_follows_g54_winding(self) -> None:
        circle = make_circle_contour(center=(50.0, 60.0), radius=20.0)[::-1]

        gcode = generate_gcode(
            [circle], [0], scale_factor=2.0, x_min=10.0, y_max=100.0,
            config=MachiningConfig(),
        )

        arc_lines = [
            line for line in gcode.splitlines() if line.startswith(("G02 ", "G03 "))
        ]
        self.assertEqual(2, len(arc_lines))
        self.assertTrue(all(line.startswith("G03 ") for line in arc_lines))

    def test_scale_factor_guards_reject_zero_and_nonfinite_values(self) -> None:
        contour = make_circle_contour()
        for scale_factor in (0.0, 1e-7, float("nan"), float("inf")):
            with self.subTest(scale_factor=scale_factor):
                with self.assertRaisesRegex(
                    RuntimeError, "Invalid or near-zero scale factor"
                ):
                    transform_contour(contour, scale_factor, 0.0, 100.0)
                with self.assertRaisesRegex(
                    RuntimeError, "Invalid or near-zero scale factor"
                ):
                    circle_geometry_mm(contour, scale_factor, 0.0, 100.0)

    def test_prune_rebuilds_contours_and_hierarchy_indices(self) -> None:
        outer = np.array(
            [[[0, 0]], [[100, 0]], [[100, 100]], [[0, 100]]], dtype=np.int32
        )
        invalid_parent = np.array([[[10, 10]], [[11, 11]]], dtype=np.int32)
        child = np.array(
            [[[20, 20]], [[40, 20]], [[40, 40]], [[20, 40]]], dtype=np.int32
        )
        contours = [outer, invalid_parent, child]
        hierarchy = np.array(
            [[[-1, -1, 1, -1], [2, -1, -1, 0], [-1, 1, -1, 1]]],
            dtype=np.int32,
        )

        rebuilt_contours, rebuilt_hierarchy = prune_stroke_ring_artifacts(
            contours, hierarchy, (120, 120), kernel_px=2, min_residue_area=0.0
        )

        self.assertEqual(2, len(rebuilt_contours))
        self.assertEqual((1, 2, 4), rebuilt_hierarchy.shape)
        self.assertEqual(0, int(rebuilt_hierarchy[0, 1, 3]))
        self.assertEqual(-1, int(rebuilt_hierarchy[0, 0, 3]))
        self.assertEqual(1, int(rebuilt_hierarchy[0, 0, 2]))

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

            with self.assertRaisesRegex(RuntimeError, "No 10x10 mm calibration square"):
                detect_calibration(contours, valid_contour_indices(contours))

    def test_unreadable_image_is_an_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unable to read input image"):
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
            arc_lines = [
                line
                for line in gcode.splitlines()
                if line.startswith(("G02 ", "G03 "))
            ]
            self.assertEqual(2, len(arc_lines))
            self.assertTrue(all(" I" in line and " J" in line for line in arc_lines))
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

    def test_strip_dimensions_removes_annotations_and_collapses_outline_rings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "dimensioned.png"
            output_path = Path(directory) / "output.nc"
            write_dimensioned_test_image(image_path)

            # Without stripping, the dimension line/text/touching extension
            # line are all traced as bogus extra machining contours.
            _, unstripped_contour_count = convert_image_to_gcode(
                image_path, output_path, MachiningConfig()
            )
            self.assertGreater(unstripped_contour_count, 2)

            scale_factor, contour_count = convert_image_to_gcode(
                image_path, output_path, MachiningConfig(), strip_dimensions=True
            )

            self.assertAlmostEqual(5.0, scale_factor, places=6)
            self.assertEqual(2, contour_count)  # part outline + the one hole
            gcode = output_path.read_text(encoding="ascii")
            self.assertEqual(2, gcode.count("(Close contour)"))

    def test_gold_drawing_strips_dimensions_to_part_contours(self) -> None:
        """The repository's dimensioned reference drawing keeps only the
        outer profile and its three real slot contours."""
        image_path = Path("input/gold.png")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "gold.nc"
            scale_factor, contour_count = convert_image_to_gcode(
                image_path,
                output_path,
                MachiningConfig(),
                strip_dimensions=True,
            )

            self.assertAlmostEqual(4.9, scale_factor, places=6)
            self.assertEqual(4, contour_count)
            gcode = output_path.read_text(encoding="ascii")
            self.assertEqual(4, gcode.count("(Close contour)"))
            self.assertNotIn("nan", gcode.lower())
            self.assertNotIn("inf", gcode.lower())

    def test_strip_dimensions_removes_extension_joined_to_filled_part(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "filled-extension.png"
            write_filled_dimension_extension_image(image_path)

            contours, _ = extract_contours(image_path, strip_dimensions=True)
            valid = valid_contour_indices(contours)
            calibration_index, _ = detect_calibration(contours, valid)
            machining = [index for index in valid if index != calibration_index]
            outer = max(machining, key=lambda index: cv2.contourArea(contours[index]))
            _x, y, _width, height = cv2.boundingRect(contours[outer])

            # The line starts at y=20 and touches the plate at y=80.  It must
            # not enlarge the machining contour beyond the filled rectangle.
            self.assertGreaterEqual(y, 78)
            self.assertLessEqual(y + height, 264)
            self.assertEqual(2, len(machining))


if __name__ == "__main__":
    unittest.main()
