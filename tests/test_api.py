"""Unit and integration tests for the ImageToGCode FastAPI Serverless Backend."""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.index import app


SAMPLE_DIR = Path(__file__).resolve().parent.parent / "input" / "samples"
SAMPLE_PLATE = SAMPLE_DIR / "01_plate_bosses.png"


class TestApiEndpoints(unittest.TestCase):
    """Test suite for FastAPI endpoints."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertIn("service", data)

    def test_analyze_sample_image(self) -> None:
        self.assertTrue(SAMPLE_PLATE.is_file(), f"Sample image not found: {SAMPLE_PLATE}")
        with open(SAMPLE_PLATE, "rb") as f:
            response = self.client.post(
                "/api/analyze",
                files={"image": ("01_plate_bosses.png", f, "image/png")},
                data={"strip_dimensions": "false"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["image_width"], 0)
        self.assertGreater(data["image_height"], 0)
        self.assertIsNotNone(data["scale_factor"])
        self.assertGreater(data["scale_factor"], 0)
        self.assertIsNotNone(data["g54_origin_px"])
        self.assertGreater(data["contour_count"], 0)

    def test_analyze_invalid_extension(self) -> None:
        response = self.client.post(
            "/api/analyze",
            files={"image": ("test.txt", b"not an image", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_convert_sample_image(self) -> None:
        self.assertTrue(SAMPLE_PLATE.is_file(), f"Sample image not found: {SAMPLE_PLATE}")
        with open(SAMPLE_PLATE, "rb") as f:
            response = self.client.post(
                "/api/convert",
                files={"image": ("01_plate_bosses.png", f, "image/png")},
                data={
                    "cut_depth": "-4.5",
                    "plunge_feed": "120.0",
                    "cut_feed": "350.0",
                    "spindle_speed": "1800",
                    "safe_z": "45.0",
                    "approach_z": "3.0",
                    "tool_diameter": "4.0",
                    "tool_number": "2",
                    "tool_offset": "2",
                    "program_number": "2000",
                    "strip_dimensions": "false",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename_base"], "01_plate_bosses")

        # G-Code validation
        gcode = data["gcode"]
        self.assertIn("O2000", gcode)
        self.assertIn("M03 S1800", gcode)
        self.assertIn("T2 M06", gcode)
        self.assertIn("G43 H2", gcode)
        self.assertIn("Z45.000", gcode)
        self.assertIn("G01 Z-4.500 F120.000", gcode)
        self.assertIn("F350.000", gcode)
        self.assertIn("M30", gcode)

        # Toolpath Segments validation
        segments = data["segments"]
        self.assertGreater(len(segments), 0)
        first_segment = segments[0]
        self.assertIn("kind", first_segment)
        self.assertIn("points", first_segment)
        self.assertIn("feed", first_segment)
        self.assertIn("z_depth", first_segment)

        # Timeline validation
        timeline = data["timeline"]
        self.assertGreater(timeline["total_time_s"], 0)
        self.assertGreater(timeline["cut_distance_mm"], 0)
        self.assertGreater(timeline["envelope_width_mm"], 0)
        self.assertGreater(timeline["envelope_height_mm"], 0)

        # DXF validation
        dxf_b64 = data["dxf_base64"]
        self.assertIsNotNone(dxf_b64)
        dxf_raw = base64.b64decode(dxf_b64).decode("latin-1", errors="ignore")
        self.assertIn("SECTION", dxf_raw)
        self.assertIn("ENTITIES", dxf_raw)

    def test_convert_invalid_config(self) -> None:
        with open(SAMPLE_PLATE, "rb") as f:
            response = self.client.post(
                "/api/convert",
                files={"image": ("01_plate_bosses.png", f, "image/png")},
                data={
                    "safe_z": "1.0",
                    "approach_z": "5.0",  # Invalid: safe_z <= approach_z
                },
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("safe_z", response.json()["detail"].lower())

    def test_convert_empty_image(self) -> None:
        response = self.client.post(
            "/api/convert",
            files={"image": ("empty.png", b"", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_direct_dxf_analyze_and_convert(self) -> None:
        import ezdxf
        from ezdxf import units

        doc = ezdxf.new("R2010")
        doc.units = units.MM
        msp = doc.modelspace()
        msp.add_circle((10.0, 10.0), 5.0)
        msp.add_lwpolyline([(0, 0), (20, 0), (20, 20), (0, 20)], close=True)

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            doc.saveas(tmp.name)
            dxf_bytes = Path(tmp.name).read_bytes()

        try:
            # 1. Test Analyze
            resp_analyze = self.client.post(
                "/api/analyze",
                files={"image": ("test_part.dxf", dxf_bytes, "application/dxf")},
            )
            self.assertEqual(resp_analyze.status_code, 200)
            data_analyze = resp_analyze.json()
            self.assertEqual(data_analyze["contour_count"], 2)
            self.assertEqual(data_analyze["scale_factor"], 1.0)
            self.assertIsNotNone(data_analyze["dxf_preview"])
            self.assertEqual(len(data_analyze["dxf_preview"]["circles"]), 1)
            self.assertEqual(len(data_analyze["dxf_preview"]["polylines"]), 1)

            # 2. Test Convert
            resp_convert = self.client.post(
                "/api/convert",
                files={"image": ("test_part.dxf", dxf_bytes, "application/dxf")},
                data={
                    "cut_depth": "-3.0",
                    "cut_feed": "250.0",
                    "safe_z": "30.0",
                    "approach_z": "2.0",
                },
            )
            self.assertEqual(resp_convert.status_code, 200)
            data_convert = resp_convert.json()
            self.assertTrue(data_convert["success"])
            self.assertTrue("G02" in data_convert["gcode"] or "G03" in data_convert["gcode"])
            self.assertIn("G01", data_convert["gcode"])
            self.assertGreater(len(data_convert["segments"]), 0)
            self.assertEqual(data_convert["filename_base"], "test_part")
            self.assertIsNotNone(data_convert["analysis"]["dxf_preview"])
        finally:
            try:
                Path(tmp.name).unlink()
            except OSError:
                pass

    def test_api_cutter_radius_compensation(self) -> None:
        client = TestClient(app)
        img_bytes = SAMPLE_PLATE.read_bytes()
        
        # Test G41 with offset D2
        resp_g41 = client.post(
            "/api/convert",
            files={"image": ("test.png", img_bytes, "image/png")},
            data={"cutter_comp": "G41", "cutter_offset_d": "2"},
        )
        self.assertEqual(resp_g41.status_code, 200)
        gcode_g41 = resp_g41.json()["gcode"]
        self.assertIn("G41 D2", gcode_g41)
        self.assertIn("G40", gcode_g41)

        # Test G42 with offset D3
        resp_g42 = client.post(
            "/api/convert",
            files={"image": ("test.png", img_bytes, "image/png")},
            data={"cutter_comp": "G42", "cutter_offset_d": "3"},
        )
        self.assertEqual(resp_g42.status_code, 200)
        gcode_g42 = resp_g42.json()["gcode"]
        self.assertIn("G42 D3", gcode_g42)
        self.assertIn("G40", gcode_g42)

        # Test G40 (no comp)
        resp_g40 = client.post(
            "/api/convert",
            files={"image": ("test.png", img_bytes, "image/png")},
            data={"cutter_comp": "G40"},
        )
        self.assertEqual(resp_g40.status_code, 200)
        gcode_g40 = resp_g40.json()["gcode"]
        self.assertNotIn("G41", gcode_g40)
        self.assertNotIn("G42", gcode_g40)


if __name__ == "__main__":
    unittest.main()

