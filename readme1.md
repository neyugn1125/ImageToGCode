# Image to G-Code

A tool that converts 2D raster images into Fanuc CNC G-code for profile milling. The application supports both a Python CLI and a Windows GUI interface.

> **Warning:** Please simulate or dry-run the program on your CNC controller before running on an actual machine. The software currently does not apply tool radius compensation, kerf compensation, multi-pass depth slicing, or collision checking.

## Features

- Reads PNG, JPG, JPEG, BMP, and TIFF image formats.
- Automatically detects a standard 10 x 10 mm black square calibration reference.
- Calculates scale factor using the formula `SF = width_px / 10.0`.
- Sets G54 origin at the bottom-left corner of the workpiece bounding box.
- Excludes the reference square from the workpiece bounding box and toolpaths.
- Smooths contours using `cv2.approxPolyDP` with a default epsilon of `0.005 * perimeter` to eliminate pixel steps on diagonal edges; the reference square contour is kept intact to maintain accurate calibration.
- Sorts contours hierarchically, machining child contours before parent contours.
- Identifies circular shapes with a circularity metric `> 0.88`.
- Generates two `G02` or `G03` arc commands with relative I/J coordinates matching contour winding direction for circular contours, avoiding interpolation with series of G01 commands.
- Generates `G01` lines for all other contours, closing each contour and retracting after each toolpath.
- Validates machining parameters prior to processing.

## Processing Pipeline

```text
Input Image
    -> Grayscale
    -> Gaussian Blur 5x5
    -> Otsu THRESH_BINARY_INV
    -> RETR_TREE / CHAIN_APPROX_SIMPLE
    -> Contour smoothing
    -> Locate 10 x 10 mm reference square
    -> Calculate scale factor (SF) and G54 origin
    -> Circle recognition vs standard contour detection
    -> Fanuc G-code generation
```

For circular contours, the program uses `cv2.minEnclosingCircle()` to determine the center and radius. Coordinates are converted to millimeters as follows:

```text
X_mm = (X_px - x_min) / SF
Y_mm = (y_max - Y_px) / SF
R_mm = R_px / SF
```

Two 180-degree arc segments use relative I/J vectors from the start point to the arc center. The reference contour does not appear in the generated G-code.

## System Requirements

- Python 3.10 or higher.
- OpenCV-Python.
- NumPy.
- Tkinter (if running the GUI). On Windows, Tkinter is usually included with Python.

## Installation

```bash
git clone <REPOSITORY_URL>
cd cnc
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Image Preparation

Input images should contain:

1. A solid black square aligned parallel to the image axes, representing a 10 x 10 mm physical scale reference.
2. One or more workpiece detail shapes to be machined.
3. A light background with high contrast relative to the shapes.

There must be exactly one square matching the calibration reference requirements. If multiple candidate squares are found, processing stops with an error to avoid selecting an incorrect scale factor. Do not include square details with identical calibration features unless they are distinct from the reference square.

## Running via CLI

Place your image at `input/input.png` and run:

```bash
python run.py
```

The default G-code output will be written to `output/output.nc`.

CLI Arguments:

| Argument | Default | Description |
| --- | ---: | --- |
| `--input` | `input/input.png` | Input image path |
| `--output` | `output/output.nc` | Output G-code file path |
| `--cut-depth` | `-5.0` | Z cutting depth (must be negative) |
| `--plunge-feed` | `100.0` | Plunge feed rate (mm/min) |
| `--cut-feed` | `300.0` | Cutting feed rate (mm/min) |
| `--spindle-speed` | `1500` | Spindle speed (RPM) |
| `--safe-z` | `50.0` | Safe Z height |
| `--approach-z` | `2.0` | Approach Z height |
| `--tool-number` | `1` | Tool number |
| `--tool-offset` | `1` | Tool length offset H |
| `--program-number` | `1000` | Fanuc program number |
| `--strip-dimensions` | off | Strip dimension lines, extension lines, arrows, and numbers before contour detection (see [Stripping Dimension Annotations](#stripping-dimension-annotations)) |

Example specifying custom parameters and output location:

```bash
python run.py --input drawings/part.png --output nc/part.nc --cut-depth -2.5 --cut-feed 250 --spindle-speed 2200
```

## Stripping Dimension Annotations

Technical CAD drawings often include dimension lines, extension lines, arrows, and numerical measurements (e.g., `100`, `Ø10`) overlaying workpiece contours. If contours are traced directly on such images, these annotations might be misidentified as toolpaths or merge into workpiece profiles.

Enable `--strip-dimensions` in the CLI or check "Remove dimension annotations" in the GUI to:

1. Automatically estimate the line stroke thickness of workpiece profiles compared to dimension lines (following ISO 128 conventions, visible outline strokes are drawn thicker than dimension lines), removing all lines thinner than the calculated threshold.
2. Re-merge double-line inner/outer contour pairs that non-filled line drawings leave behind when rendering single-line profiles, ensuring each real geometry feature (outer boundary, inner holes) yields exactly one contour.

This feature works with both solid-filled drawings (like samples in `input/samples/`) and un-filled technical line drawings. Because the threshold is estimated dynamically per image, only enable this when dimension lines are present; turning it on for solid-filled images with small features could accidentally erase fine details. The 10 x 10 mm calibration reference square is always preserved regardless of this setting.

Note: Circular profiles detected from un-filled line strokes might occasionally fall below the circularity threshold (`> 0.88`) due to lower stroke smoothness, resulting in output generated as a series of `G01` lines instead of `G02`/`G03` arcs — the cutting path remains accurate, only the G-code command representation differs.

## Running the GUI Interface

```bash
python app.py
```

In the application window:

1. Click **Browse** next to Input image to select an image file.
2. Select the Output G-code file path.
3. Enter tool and machining parameters.
4. Click **Generate G-Code**.

The GUI features image preview, processing status, and a button to open the output directory. The parent directory of the output file is created automatically upon generation.

## Packaging as Windows EXE

On Windows, open Command Prompt in the project root directory and run:

```bat
build_windows.bat
```

The script installs PyInstaller and produces:

```text
dist/ImageToGCode.exe
```

This single executable file can be copied to other Windows machines without requiring Python. Default paths use `input` and `output` folders adjacent to the executable, and the GUI allows selecting alternative file paths directly.

## Running Tests

```bash
python -m unittest discover -s tests -v
```

The test suite covers calibration, G54 bounding box calculation, child-first contour hierarchy sorting, reference square exclusion, circle recognition, invalid parameter validation, header/footer generation, and smoke tests for `.nc` file output.

## Project Structure

```text
.
├── app.py                  # Tkinter GUI application
├── run.py                  # Processing pipeline and CLI
├── requirements.txt        # Python dependencies
├── build_windows.bat       # Windows executable build script
├── input/input.png         # Default sample image
├── output/output.nc        # Sample generated G-code
└── tests/
    └── test_image_to_gcode.py
```
