from __future__ import annotations

import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from run import (
    CIRCULARITY_THRESHOLD,
    CONTOUR_SMOOTHING_EPSILON_RATIO,
    CURVE_SMOOTHING_MAX_EPSILON_PX,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_DIRECTORY,
    MIN_CALIBRATION_BLACK_RATIO,
    MULTIPLE_CALIBRATION_ERROR,
    SCALE_REFERENCE_ERROR,
    MachiningConfig,
    circle_geometry_mm,
    contour_black_ratio,
    contour_circularity,
    convert_image_to_gcode,
    detect_calibration,
    extract_contours,
    generate_gcode,
    is_calibration_square,
    is_ideal_circle,
    load_binary_image,
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


def write_reference_and_outline_square_image(path: Path) -> None:
    """A filled reference marker beside square outline machining geometry."""
    image = np.full((320, 420, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (69, 69), (0, 0, 0), -1)
    cv2.rectangle(image, (140, 80), (320, 260), (0, 0, 0), thickness=6)
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


def make_ellipse_contour(
    center: tuple[float, float] = (150.0, 100.0),
    axes: tuple[float, float] = (120.0, 45.0),
) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)
    points = np.column_stack(
        (
            center[0] + axes[0] * np.cos(angles),
            center[1] + axes[1] * np.sin(angles),
        )
    )
    return np.rint(points).astype(np.int32).reshape(-1, 1, 2)


def make_semicircle_contour(
    center: tuple[float, float] = (100.0, 100.0), radius: float = 80.0
) -> np.ndarray:
    angles = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 361)
    arc_points = np.column_stack(
        (
            center[0] + radius * np.cos(angles),
            center[1] + radius * np.sin(angles),
        )
    )
    return np.rint(arc_points).astype(np.int32).reshape(-1, 1, 2)


class ImageToGcodeTests(unittest.TestCase):
    def test_cli_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(DEFAULT_INPUT_PATH, args.input)
        self.assertEqual(DEFAULT_OUTPUT_DIRECTORY, args.output_dir)
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
            min(
                CONTOUR_SMOOTHING_EPSILON_RATIO * cv2.arcLength(contour, True),
                CURVE_SMOOTHING_MAX_EPSILON_PX,
            ),
            True,
        )

        smoothed = smooth_contours([contour])

        self.assertEqual(1, len(smoothed))
        np.testing.assert_array_equal(expected, smoothed[0])
        self.assertLessEqual(len(smoothed[0]), len(contour))

    def test_long_ellipse_uses_pixel_capped_smoothing(self) -> None:
        contour = make_ellipse_contour()
        uncapped = cv2.approxPolyDP(
            contour,
            CONTOUR_SMOOTHING_EPSILON_RATIO * cv2.arcLength(contour, True),
            True,
        )
        expected = cv2.approxPolyDP(
            contour,
            CURVE_SMOOTHING_MAX_EPSILON_PX,
            True,
        )

        smoothed = smooth_contours([contour])[0]

        np.testing.assert_array_equal(expected, smoothed)
        self.assertGreater(len(smoothed), len(uncapped))

    def test_semicircle_uses_pixel_capped_smoothing(self) -> None:
        contour = make_semicircle_contour()
        uncapped = cv2.approxPolyDP(
            contour,
            CONTOUR_SMOOTHING_EPSILON_RATIO * cv2.arcLength(contour, True),
            True,
        )
        expected = cv2.approxPolyDP(
            contour,
            CURVE_SMOOTHING_MAX_EPSILON_PX,
            True,
        )

        smoothed = smooth_contours([contour])[0]

        np.testing.assert_array_equal(expected, smoothed)
        self.assertGreater(len(smoothed), len(uncapped))

    def test_bracket_tab_smooths_rasterized_triangle(self) -> None:
        image_path = Path("input/samples/06_bracket_tab.png")
        if not image_path.exists():
            self.skipTest(f"{image_path} not found")

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
            contours, hierarchy, (120, 120), kernel_px=2
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

    def test_black_ratio_distinguishes_reference_from_square_outline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "square-outline.png"
            output_path = Path(directory) / "output.nc"
            write_reference_and_outline_square_image(image_path)

            binary = load_binary_image(image_path)
            contours, _ = extract_contours(image_path)
            valid = valid_contour_indices(contours)
            geometric_squares = [
                index for index in valid if is_calibration_square(contours[index])
            ]
            calibration_index, scale_factor = detect_calibration(
                contours, valid, binary=binary
            )

            # The reference marker and the retained edge of the outlined
            # square remain; the redundant inner stroke edge is collapsed.
            self.assertGreaterEqual(len(geometric_squares), 2)
            self.assertAlmostEqual(5.0, scale_factor, places=6)
            self.assertGreaterEqual(
                contour_black_ratio(contours[calibration_index], binary),
                MIN_CALIBRATION_BLACK_RATIO,
            )
            for index in geometric_squares:
                if index != calibration_index:
                    self.assertLess(
                        contour_black_ratio(contours[index], binary),
                        MIN_CALIBRATION_BLACK_RATIO,
                    )

            converted_scale, contour_count = convert_image_to_gcode(
                image_path, output_path, MachiningConfig()
            )
            self.assertAlmostEqual(5.0, converted_scale, places=6)
            self.assertEqual(1, contour_count)

    def test_missing_calibration_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-calibration.png"
            write_test_image(image_path, calibration_count=0)
            contours, _ = extract_contours(image_path)

            with self.assertRaisesRegex(RuntimeError, "No 10x10 mm calibration square"):
                detect_calibration(contours, valid_contour_indices(contours))

    def test_no_metadata_image_accepts_explicit_reference_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-metadata.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path, calibration_count=0)

            scale_factor, contour_count = convert_image_to_gcode(
                image_path,
                output_path,
                MachiningConfig(),
                reference_width_mm=40.0,
                reference_height_mm=36.0,
            )

            self.assertAlmostEqual(5.0, scale_factor, places=6)
            self.assertEqual(2, contour_count)
            self.assertTrue(output_path.is_file())
            gcode = output_path.read_text(encoding="ascii")
            self.assertNotIn("nan", gcode.lower())
            self.assertNotIn("inf", gcode.lower())

    def test_no_metadata_image_accepts_explicit_pixels_per_mm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-metadata.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path, calibration_count=0)

            scale_factor, _contour_count = convert_image_to_gcode(
                image_path,
                output_path,
                MachiningConfig(),
                pixels_per_mm=5.0,
            )

            self.assertAlmostEqual(5.0, scale_factor, places=6)
            self.assertTrue(output_path.is_file())

    def test_no_metadata_image_without_reference_fails_before_gcode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-metadata.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path, calibration_count=0)

            with self.assertRaisesRegex(RuntimeError, SCALE_REFERENCE_ERROR):
                convert_image_to_gcode(image_path, output_path, MachiningConfig())

            self.assertFalse(output_path.exists())

    def test_scale_reference_dimensions_must_match_one_uniform_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "no-metadata.png"
            output_path = Path(directory) / "output.nc"
            write_test_image(image_path, calibration_count=0)

            with self.assertRaisesRegex(RuntimeError, "scale differs by more than 5%"):
                convert_image_to_gcode(
                    image_path,
                    output_path,
                    MachiningConfig(),
                    reference_width_mm=40.0,
                    reference_height_mm=30.0,
                )

            self.assertFalse(output_path.exists())

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
            output_root = Path(directory) / "output"
            write_test_image(image_path)

            result = main(
                [
                    "--input",
                    str(image_path),
                    "--output-dir",
                    str(output_root),
                ]
            )

            self.assertEqual(0, result)
            run_directories = list(output_root.glob("drawing_*"))
            self.assertEqual(1, len(run_directories))
            output_path = run_directories[0] / "drawing.nc"
            self.assertTrue((run_directories[0] / "drawing.dxf").is_file())
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
            output_root = Path(directory) / "output" / "nested"
            write_test_image(image_path)

            result = main(
                ["--input", str(image_path), "--output", str(output_root)]
            )

            self.assertEqual(0, result)
            self.assertEqual(1, len(list(output_root.glob("drawing_*/drawing.nc"))))

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

    def test_thick_outline_drawing_collapses_each_pair_of_stroke_edges(self) -> None:
        image_path = Path("input/3.png")
        if not image_path.exists():
            self.skipTest(f"{image_path} not found")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "3.nc"

            scale_factor, contour_count = convert_image_to_gcode(
                image_path, output_path, MachiningConfig()
            )

            self.assertAlmostEqual(16.54, scale_factor, places=6)
            self.assertEqual(3, contour_count)  # outer square + diamond + circle
            self.assertEqual(3, output_path.read_text(encoding="ascii").count("(Retract)"))

    def test_analyze_image_returns_metadata(self) -> None:
        from run import analyze_image
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "drawing.png"
            write_test_image(image_path)

            analysis = analyze_image(image_path)
            self.assertEqual((320, 400), analysis.image_shape)
            self.assertIsNotNone(analysis.scale_factor)
            self.assertAlmostEqual(5.0, analysis.scale_factor)
            self.assertIsNotNone(analysis.calibration_bbox_px)
            self.assertIsNotNone(analysis.g54_origin_px)
            self.assertEqual(2, analysis.contour_count)

    def test_app_parse_toolpath_and_sim_timeline(self) -> None:
        from app import parse_toolpath_segments, build_sim_timeline, sim_state_at_time
        sample_gcode = """
        G90 G21
        G00 X10.0 Y20.0 Z50.0
        G01 Z-5.0 F100.0
        G01 X30.0 Y20.0 F300.0
        G02 X30.0 Y40.0 I0.0 J10.0 F300.0
        G00 Z50.0
        """
        segments = parse_toolpath_segments(sample_gcode)
        self.assertGreaterEqual(len(segments), 3)
        frames, total_time, cut_dist, rapid_dist = build_sim_timeline(segments)
        self.assertGreater(total_time, 0.0)
        self.assertGreater(cut_dist, 0.0)
        self.assertGreater(rapid_dist, 0.0)

        x, y, z, kind, feed = sim_state_at_time(frames, total_time / 2.0)
        self.assertTrue(math.isfinite(x))
        self.assertTrue(math.isfinite(y))
        self.assertTrue(math.isfinite(z))


if __name__ == "__main__":
    unittest.main()
