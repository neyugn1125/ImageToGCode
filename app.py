#!/usr/bin/env python3
"""Windows-friendly GUI entry point for the Image to G-Code converter."""

from __future__ import annotations

import base64
import bisect
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, NamedTuple

import cv2

from run import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    MachiningConfig,
    convert_image_to_gcode,
    validate_config,
)


WINDOW_BACKGROUND = "#f3f3f3"
PANEL_BACKGROUND = "#ffffff"
TEXT_COLOR = "#1f1f1f"
MUTED_COLOR = "#5f6368"
ACCENT_COLOR = "#0067c0"
SUCCESS_COLOR = "#107c10"
ERROR_COLOR = "#c42b1c"

SIM_RAPID_COLOR = "#9aa0a6"
SIM_LINEAR_COLOR = "#1e8e3e"
SIM_ARC_CW_COLOR = "#1a73e8"
SIM_ARC_CCW_COLOR = "#d93025"
SIM_TRAVELED_COLOR = "#ff8c00"
SIM_TOOL_COLOR = "#202124"
SIM_TICK_MS = 40
# G00 rapids don't carry a feed rate; this is a display-only pacing assumption
# used purely to animate rapids at a plausible speed relative to cutting moves.
RAPID_DISPLAY_FEED = 3000.0


APP_DIRECTORY = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
GUI_DEFAULT_INPUT_PATH = APP_DIRECTORY / DEFAULT_INPUT_PATH
GUI_DEFAULT_OUTPUT_PATH = APP_DIRECTORY / DEFAULT_OUTPUT_PATH
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

_GCODE_WORD_RE = re.compile(r"([A-Z])(-?\d+(?:\.\d+)?)")

Point = tuple[float, float]


class Segment(NamedTuple):
    kind: str  # "rapid" | "linear" | "arc_cw" | "arc_ccw"
    points: list[Point]
    feed: float


class Frame(NamedTuple):
    time: float
    x: float
    y: float
    kind: str
    feed: float


def _strip_gcode_comment(line: str) -> str:
    return line.split("(", 1)[0].strip()


def _arc_points(
    start: Point,
    end: Point,
    offset_i: float,
    offset_j: float,
    clockwise: bool,
    segments: int = 32,
) -> list[Point]:
    center_x = start[0] + offset_i
    center_y = start[1] + offset_j
    radius = math.hypot(start[0] - center_x, start[1] - center_y)
    if radius <= 1e-9:
        return [start, end]

    start_angle = math.atan2(start[1] - center_y, start[0] - center_x)
    end_angle = math.atan2(end[1] - center_y, end[0] - center_x)
    if clockwise:
        while end_angle > start_angle:
            end_angle -= 2 * math.pi
    else:
        while end_angle < start_angle:
            end_angle += 2 * math.pi

    return [
        (
            center_x + radius * math.cos(start_angle + (end_angle - start_angle) * step / segments),
            center_y + radius * math.sin(start_angle + (end_angle - start_angle) * step / segments),
        )
        for step in range(segments + 1)
    ]


def parse_toolpath_segments(gcode_text: str) -> list[Segment]:
    """Extract rapid/linear/arc XY moves from generated G-code, in machine mm."""
    segments: list[Segment] = []
    x = y = 0.0
    motion_mode: int | None = None
    feed_rate = 0.0
    for raw_line in gcode_text.splitlines():
        line = _strip_gcode_comment(raw_line)
        if not line:
            continue
        words = dict(_GCODE_WORD_RE.findall(line))
        if "G" in words:
            g_value = int(float(words["G"]))
            if g_value in (0, 1, 2, 3):
                motion_mode = g_value
        if "F" in words:
            feed_rate = float(words["F"])

        new_x = float(words["X"]) if "X" in words else x
        new_y = float(words["Y"]) if "Y" in words else y
        if motion_mode is None or ("X" not in words and "Y" not in words):
            x, y = new_x, new_y
            continue

        if motion_mode == 0:
            segments.append(Segment("rapid", [(x, y), (new_x, new_y)], 0.0))
        elif motion_mode == 1:
            segments.append(Segment("linear", [(x, y), (new_x, new_y)], feed_rate))
        else:
            offset_i = float(words["I"]) if "I" in words else 0.0
            offset_j = float(words["J"]) if "J" in words else 0.0
            points = _arc_points((x, y), (new_x, new_y), offset_i, offset_j, motion_mode == 2)
            kind = "arc_cw" if motion_mode == 2 else "arc_ccw"
            segments.append(Segment(kind, points, feed_rate))
        x, y = new_x, new_y
    return segments


def build_sim_timeline(segments: list[Segment]) -> tuple[list[Frame], float, float, float]:
    """Unroll segments into a time-stamped animation timeline.

    Returns (frames, total_time_seconds, cut_distance_mm, rapid_distance_mm).
    """
    if not segments:
        return [], 0.0, 0.0, 0.0

    first_x, first_y = segments[0].points[0]
    frames: list[Frame] = [Frame(0.0, first_x, first_y, "idle", 0.0)]
    elapsed = 0.0
    cut_distance = 0.0
    rapid_distance = 0.0
    for segment in segments:
        feed = segment.feed if segment.feed > 0 else RAPID_DISPLAY_FEED
        for start_point, end_point in zip(segment.points, segment.points[1:]):
            distance = math.hypot(
                end_point[0] - start_point[0], end_point[1] - start_point[1]
            )
            if segment.kind == "rapid":
                rapid_distance += distance
            else:
                cut_distance += distance
            elapsed += (distance / feed) * 60.0
            frames.append(Frame(elapsed, end_point[0], end_point[1], segment.kind, segment.feed))
    return frames, elapsed, cut_distance, rapid_distance


def sim_state_at_time(frames: list[Frame], moment: float) -> tuple[float, float, str, float]:
    """Interpolate tool position/kind/feed at a point in the animation timeline."""
    if not frames:
        return 0.0, 0.0, "idle", 0.0
    if moment <= frames[0].time:
        frame = frames[0]
        return frame.x, frame.y, frame.kind, frame.feed
    if moment >= frames[-1].time:
        frame = frames[-1]
        return frame.x, frame.y, frame.kind, frame.feed

    times = [frame.time for frame in frames]
    index = min(max(bisect.bisect_right(times, moment), 1), len(frames) - 1)
    previous_frame, next_frame = frames[index - 1], frames[index]
    span = next_frame.time - previous_frame.time
    fraction = (moment - previous_frame.time) / span if span > 0 else 0.0
    x = previous_frame.x + (next_frame.x - previous_frame.x) * fraction
    y = previous_frame.y + (next_frame.y - previous_frame.y) * fraction
    return x, y, next_frame.kind, next_frame.feed


def traveled_points(frames: list[Frame], moment: float) -> list[Point]:
    """Return the polyline already traveled up to `moment`, for the progress trail."""
    points = [(frame.x, frame.y) for frame in frames if frame.time <= moment]
    x, y, _kind, _feed = sim_state_at_time(frames, moment)
    if not points or points[-1] != (x, y):
        points.append((x, y))
    return points


class ImageToGCodeApp(ttk.Frame):
    """Desktop interface around the existing conversion pipeline."""

    def __init__(self, root: tk.Tk) -> None:
        root.title("Image to G-Code | Fanuc CNC")
        root.geometry("1120x920")
        root.minsize(960, 780)
        root.configure(bg=WINDOW_BACKGROUND)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self._outer_canvas = tk.Canvas(
            root, background=WINDOW_BACKGROUND, highlightthickness=0
        )
        self._outer_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            root, orient="vertical", command=self._outer_canvas.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._outer_canvas.configure(yscrollcommand=scrollbar.set)

        super().__init__(self._outer_canvas, padding=(24, 20))
        self.root = root
        self._canvas_window = self._outer_canvas.create_window(
            (0, 0), window=self, anchor="nw"
        )
        self.bind("<Configure>", self._on_content_configure)
        self._outer_canvas.bind("<Configure>", self._on_outer_canvas_configure)
        self._outer_canvas.bind("<Enter>", self._bind_mousewheel)
        self._outer_canvas.bind("<Leave>", self._unbind_mousewheel)

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.preview_photo: tk.PhotoImage | None = None
        self.running = False
        self._current_preview_path: Path | None = None
        self._current_segments: list[Segment] | None = None
        self._preview_resize_job: str | None = None
        self._sim_resize_job: str | None = None
        self._sim_scale = 1.0
        self._sim_base_scale = 1.0
        self._sim_offset_x = 0.0
        self._sim_offset_y = 0.0
        self._sim_drag_last: tuple[int, int] | None = None

        self._sim_frames: list[Frame] = []
        self._sim_total_time = 0.0
        self._sim_cut_distance = 0.0
        self._sim_rapid_distance = 0.0
        self._sim_current_time = 0.0
        self._sim_playing = False
        self._sim_after_id: str | None = None
        self._sim_last_tick = 0.0
        self._sim_syncing_progress = False

        self.input_var = tk.StringVar(value=str(GUI_DEFAULT_INPUT_PATH))
        self.output_var = tk.StringVar(value=str(GUI_DEFAULT_OUTPUT_PATH))
        self.status_var = tk.StringVar(value="Ready")
        self.preview_info_var = tk.StringVar(value="Select an image to preview")
        self.sim_info_var = tk.StringVar(value="No simulation yet")
        self.sim_readout_var = tk.StringVar(value="")
        self.sim_speed_var = tk.DoubleVar(value=5.0)
        self.sim_progress_var = tk.DoubleVar(value=0.0)
        self.cut_depth_var = tk.StringVar(value="-5.0")
        self.plunge_feed_var = tk.StringVar(value="100.0")
        self.cut_feed_var = tk.StringVar(value="300.0")
        self.spindle_speed_var = tk.StringVar(value="1500")
        self.safe_z_var = tk.StringVar(value="50.0")
        self.approach_z_var = tk.StringVar(value="2.0")
        self.tool_number_var = tk.StringVar(value="1")
        self.tool_offset_var = tk.StringVar(value="1")
        self.program_number_var = tk.StringVar(value="1000")
        self.strip_dimensions_var = tk.BooleanVar(value=False)

        self._configure_styles()
        self._build_ui()
        self._load_preview(Path(self.input_var.get()))
        self.root.after(100, self._poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _on_content_configure(self, _event: tk.Event) -> None:
        self._outer_canvas.configure(scrollregion=self._outer_canvas.bbox("all"))

    def _on_outer_canvas_configure(self, event: tk.Event) -> None:
        self._outer_canvas.itemconfigure(self._canvas_window, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self._outer_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._outer_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._outer_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self._outer_canvas.unbind_all("<MouseWheel>")
        self._outer_canvas.unbind_all("<Button-4>")
        self._outer_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:
            self._outer_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._outer_canvas.yview_scroll(1, "units")
        else:
            self._outer_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=WINDOW_BACKGROUND)
        style.configure("Panel.TLabelframe", background=PANEL_BACKGROUND)
        style.configure(
            "Panel.TLabelframe.Label",
            background=PANEL_BACKGROUND,
            foreground=TEXT_COLOR,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("TLabel", background=WINDOW_BACKGROUND, foreground=TEXT_COLOR)
        style.configure(
            "Title.TLabel",
            background=WINDOW_BACKGROUND,
            foreground=TEXT_COLOR,
            font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=WINDOW_BACKGROUND,
            foreground=MUTED_COLOR,
            font=("Segoe UI", 10),
        )
        style.configure("Panel.TLabel", background=PANEL_BACKGROUND, foreground=TEXT_COLOR)
        style.configure("Muted.Panel.TLabel", background=PANEL_BACKGROUND, foreground=MUTED_COLOR)
        style.configure("Panel.TCheckbutton", background=PANEL_BACKGROUND, foreground=TEXT_COLOR)
        style.configure("TEntry", padding=(7, 5))
        style.configure("TButton", padding=(12, 6), font=("Segoe UI", 10))
        style.configure(
            "Accent.TButton",
            background=ACCENT_COLOR,
            foreground="white",
            padding=(18, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#005a9e")])
        style.configure("Status.TLabel", background=WINDOW_BACKGROUND, foreground=MUTED_COLOR)
        style.configure(
            "Success.Status.TLabel",
            background=WINDOW_BACKGROUND,
            foreground=SUCCESS_COLOR,
        )
        style.configure(
            "Error.Status.TLabel",
            background=WINDOW_BACKGROUND,
            foreground=ERROR_COLOR,
        )

    def _build_ui(self) -> None:
        # Layout: narrow form column on the left (Files, Machining parameters,
        # actions); a tall stack of Preview (compact) over Toolpath Simulation
        # (large) on the right, since the simulation view with its playback
        # controls is the panel used the most once G-code exists.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="Image to G-Code", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Fanuc profile milling with automatic 10 x 10 mm calibration",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=3)
        content.rowconfigure(0, weight=1)

        left_column = ttk.Frame(content, style="TFrame")
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_column.columnconfigure(0, weight=1)
        left_column.rowconfigure(1, weight=1)

        paths_panel = ttk.LabelFrame(
            left_column, text="Files", style="Panel.TLabelframe", padding=16
        )
        paths_panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        paths_panel.columnconfigure(1, weight=1)
        self.input_browse_button = self._path_row(
            paths_panel,
            0,
            "Input image",
            self.input_var,
            self._choose_input,
        )
        self.output_browse_button = self._path_row(
            paths_panel,
            1,
            "Output G-code",
            self.output_var,
            self._choose_output,
        )

        self.strip_dimensions_check = ttk.Checkbutton(
            paths_panel,
            text="Remove dimension annotations (lines/arrows/text) before tracing",
            variable=self.strip_dimensions_var,
            style="Panel.TCheckbutton",
        )
        self.strip_dimensions_check.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )

        settings = ttk.LabelFrame(
            left_column, text="Machining parameters", style="Panel.TLabelframe", padding=16
        )
        settings.grid(row=1, column=0, sticky="new", pady=(0, 12))
        settings.columnconfigure(0, weight=1)
        fields: list[tuple[str, tk.StringVar]] = [
            ("Cut depth Z (mm)", self.cut_depth_var),
            ("Plunge feed (mm/min)", self.plunge_feed_var),
            ("Cut feed (mm/min)", self.cut_feed_var),
            ("Spindle RPM", self.spindle_speed_var),
            ("Safe Z (mm)", self.safe_z_var),
            ("Approach Z (mm)", self.approach_z_var),
            ("Tool number", self.tool_number_var),
            ("Tool offset H", self.tool_offset_var),
            ("Program number O", self.program_number_var),
        ]
        for index, (label, variable) in enumerate(fields):
            cell = ttk.Frame(settings, style="TFrame")
            cell.grid(row=index, column=0, sticky="ew", pady=3)
            cell.columnconfigure(1, weight=1)
            ttk.Label(cell, text=label).grid(row=0, column=0, sticky="w")
            ttk.Entry(cell, textvariable=variable, width=12).grid(
                row=0, column=1, sticky="e"
            )

        button_row = ttk.Frame(left_column, style="TFrame")
        button_row.grid(row=2, column=0, sticky="sew")
        self.generate_button = ttk.Button(
            button_row,
            text="Generate G-Code",
            style="Accent.TButton",
            command=self._start_conversion,
        )
        self.generate_button.pack(fill="x")
        self.reset_button = ttk.Button(
            button_row, text="Reset", command=self._reset_defaults
        )
        self.reset_button.pack(fill="x", pady=(8, 0))
        self.open_output_button = ttk.Button(
            button_row, text="Open output folder", command=self._open_output_folder
        )
        self.open_output_button.pack(fill="x", pady=(8, 0))

        right_panel = ttk.Frame(content, style="TFrame")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=2)

        preview_panel = ttk.LabelFrame(
            right_panel, text="Preview", style="Panel.TLabelframe", padding=12
        )
        preview_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            preview_panel,
            width=560,
            height=160,
            background="#fafafa",
            highlightthickness=1,
            highlightbackground="#dedede",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_configure)
        ttk.Label(
            preview_panel,
            textvariable=self.preview_info_var,
            style="Muted.Panel.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        simulation_panel = ttk.LabelFrame(
            right_panel,
            text="Toolpath Simulation",
            style="Panel.TLabelframe",
            padding=12,
        )
        simulation_panel.grid(row=1, column=0, sticky="nsew")
        simulation_panel.columnconfigure(0, weight=1)
        simulation_panel.rowconfigure(0, weight=1)
        self.sim_canvas = tk.Canvas(
            simulation_panel,
            width=560,
            height=260,
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#dedede",
        )
        self.sim_canvas.grid(row=0, column=0, sticky="nsew")
        self.sim_canvas.bind("<Configure>", self._on_sim_canvas_configure)
        self.sim_canvas.bind("<MouseWheel>", self._on_sim_zoom)
        self.sim_canvas.bind("<Button-4>", self._on_sim_zoom)
        self.sim_canvas.bind("<Button-5>", self._on_sim_zoom)
        self.sim_canvas.bind("<ButtonPress-1>", self._on_sim_drag_start)
        self.sim_canvas.bind("<B1-Motion>", self._on_sim_drag_move)
        self.sim_canvas.bind("<ButtonRelease-1>", self._on_sim_drag_end)

        sim_controls = ttk.Frame(simulation_panel, style="TFrame")
        sim_controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.sim_play_button = ttk.Button(
            sim_controls, text="Play", width=8, command=self._toggle_sim_playback
        )
        self.sim_play_button.pack(side="left")
        self.sim_step_button = ttk.Button(
            sim_controls, text="Step", width=6, command=self._step_sim_playback
        )
        self.sim_step_button.pack(side="left", padx=(6, 0))
        self.sim_playback_reset_button = ttk.Button(
            sim_controls, text="Restart", width=8, command=self._reset_sim_playback
        )
        self.sim_playback_reset_button.pack(side="left", padx=(6, 0))
        ttk.Label(sim_controls, text="Speed", style="Muted.Panel.TLabel").pack(
            side="left", padx=(14, 4)
        )
        self.sim_speed_scale = ttk.Scale(
            sim_controls,
            from_=1.0,
            to=50.0,
            orient="horizontal",
            variable=self.sim_speed_var,
            length=90,
            command=self._on_sim_speed_change,
        )
        self.sim_speed_scale.pack(side="left")
        self.sim_speed_label = ttk.Label(
            sim_controls, text="5x", style="Muted.Panel.TLabel", width=4
        )
        self.sim_speed_label.pack(side="left", padx=(4, 0))

        sim_scrub_row = ttk.Frame(simulation_panel, style="TFrame")
        sim_scrub_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        sim_scrub_row.columnconfigure(0, weight=1)
        self.sim_scrubber = ttk.Scale(
            sim_scrub_row,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            variable=self.sim_progress_var,
            command=self._on_sim_scrub,
        )
        self.sim_scrubber.grid(row=0, column=0, sticky="ew")

        ttk.Label(
            simulation_panel,
            textvariable=self.sim_readout_var,
            style="Muted.Panel.TLabel",
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        sim_footer = ttk.Frame(simulation_panel, style="TFrame")
        sim_footer.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        sim_footer.columnconfigure(0, weight=1)
        ttk.Label(
            sim_footer,
            textvariable=self.sim_info_var,
            style="Muted.Panel.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.sim_reset_view_button = ttk.Button(
            sim_footer, text="Recenter", command=self._reset_sim_view
        )
        self.sim_reset_view_button.grid(row=0, column=1, sticky="e")
        self._clear_simulation()

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        actions.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            actions, textvariable=self.status_var, style="Status.TLabel"
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        self.log = tk.Text(
            self,
            height=4,
            state="disabled",
            background="#ffffff",
            foreground=TEXT_COLOR,
            relief="flat",
            borderwidth=1,
            padx=8,
            pady=6,
        )
        self.log.grid(row=3, column=0, sticky="ew", pady=(12, 0))

    def _path_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> ttk.Button:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=6
        )
        button = ttk.Button(parent, text="Browse", command=command)
        button.grid(row=row, column=1, sticky="w", pady=6)
        return button

    def _choose_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select drawing image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")],
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            self._show_error(
                f"Unsupported file type: {path.suffix or '(no extension)'}. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
            )
            return
        if cv2.imread(str(path)) is None:
            self._show_error(f"Not a valid image file: {path.name}")
            return
        self.input_var.set(str(path))
        self._load_preview(path)

    def _choose_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save G-code as",
            defaultextension=".nc",
            initialfile=Path(self.output_var.get()).name or "output.nc",
            filetypes=[("NC G-code", "*.nc"), ("All files", "*.*")],
        )
        if selected:
            self.output_var.set(selected)

    @staticmethod
    def _canvas_size(canvas: tk.Canvas) -> tuple[int, int]:
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            width = int(canvas.cget("width"))
            height = int(canvas.cget("height"))
        return width, height

    def _on_preview_canvas_configure(self, _event: tk.Event) -> None:
        if self._preview_resize_job is not None:
            self.root.after_cancel(self._preview_resize_job)
        self._preview_resize_job = self.root.after(120, self._redraw_preview)

    def _redraw_preview(self) -> None:
        self._preview_resize_job = None
        if self._current_preview_path is not None:
            self._load_preview(self._current_preview_path)

    def _on_sim_canvas_configure(self, _event: tk.Event) -> None:
        if self._sim_resize_job is not None:
            self.root.after_cancel(self._sim_resize_job)
        self._sim_resize_job = self.root.after(120, self._redraw_simulation)

    def _redraw_simulation(self) -> None:
        self._sim_resize_job = None
        if self._current_segments is not None:
            self._draw_toolpath(self._current_segments)
        else:
            self._clear_simulation()

    def _on_sim_zoom(self, event: tk.Event) -> str:
        if not self._current_segments:
            return "break"
        zooming_in = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
        factor = 1.15 if zooming_in else 1 / 1.15
        min_scale = self._sim_base_scale * 0.2
        max_scale = self._sim_base_scale * 20.0
        new_scale = min(max_scale, max(min_scale, self._sim_scale * factor))

        # Keep the world point under the cursor fixed on screen (Google Maps-style zoom).
        world_x = (event.x - self._sim_offset_x) / self._sim_scale
        world_y = (self._sim_offset_y - event.y) / self._sim_scale
        self._sim_scale = new_scale
        self._sim_offset_x = event.x - world_x * new_scale
        self._sim_offset_y = event.y + world_y * new_scale

        self._draw_toolpath(self._current_segments)
        return "break"

    def _on_sim_drag_start(self, event: tk.Event) -> None:
        if not self._current_segments:
            return
        self._sim_drag_last = (event.x, event.y)
        self.sim_canvas.configure(cursor="fleur")

    def _on_sim_drag_move(self, event: tk.Event) -> None:
        if self._sim_drag_last is None:
            return
        last_x, last_y = self._sim_drag_last
        self._sim_offset_x += event.x - last_x
        self._sim_offset_y += event.y - last_y
        self._sim_drag_last = (event.x, event.y)
        self._draw_toolpath(self._current_segments)

    def _on_sim_drag_end(self, _event: tk.Event) -> None:
        self._sim_drag_last = None
        self.sim_canvas.configure(cursor="")

    def _on_sim_speed_change(self, value_str: str) -> None:
        self.sim_speed_label.configure(text=f"{float(value_str):.0f}x")

    def _set_sim_playback_controls_state(self, state: str) -> None:
        for widget in (
            self.sim_play_button,
            self.sim_step_button,
            self.sim_playback_reset_button,
            self.sim_speed_scale,
            self.sim_scrubber,
        ):
            widget.configure(state=state)

    def _toggle_sim_playback(self) -> None:
        if not self._sim_frames:
            return
        if self._sim_playing:
            self._pause_sim_playback()
            return
        if self._sim_current_time >= self._sim_total_time:
            self._sim_current_time = 0.0
        self._sim_playing = True
        self.sim_play_button.configure(text="Pause")
        self._sim_last_tick = time.perf_counter()
        self._tick_sim_playback()

    def _pause_sim_playback(self) -> None:
        self._sim_playing = False
        if hasattr(self, "sim_play_button"):
            self.sim_play_button.configure(text="Play")
        if self._sim_after_id is not None:
            self.root.after_cancel(self._sim_after_id)
            self._sim_after_id = None

    def _tick_sim_playback(self) -> None:
        now = time.perf_counter()
        dt = now - self._sim_last_tick
        self._sim_last_tick = now
        self._sim_current_time = min(
            self._sim_total_time, self._sim_current_time + dt * self.sim_speed_var.get()
        )
        self._draw_toolpath(self._current_segments)
        if self._sim_current_time >= self._sim_total_time:
            self._pause_sim_playback()
            return
        self._sim_after_id = self.root.after(SIM_TICK_MS, self._tick_sim_playback)

    def _step_sim_playback(self) -> None:
        if not self._sim_frames:
            return
        self._pause_sim_playback()
        next_time = self._sim_total_time
        for frame in self._sim_frames:
            if frame.time > self._sim_current_time + 1e-9:
                next_time = frame.time
                break
        self._sim_current_time = next_time
        self._draw_toolpath(self._current_segments)

    def _reset_sim_playback(self) -> None:
        self._pause_sim_playback()
        self._sim_current_time = 0.0
        if self._current_segments is not None:
            self._draw_toolpath(self._current_segments)

    def _on_sim_scrub(self, value_str: str) -> None:
        if self._sim_syncing_progress or not self._sim_frames:
            return
        self._pause_sim_playback()
        fraction = max(0.0, min(1.0, float(value_str) / 100.0))
        self._sim_current_time = fraction * self._sim_total_time
        self._draw_toolpath(self._current_segments)

    def _reset_sim_view(self) -> None:
        if self._current_segments:
            self._fit_sim_view()
            self._draw_toolpath(self._current_segments)
        else:
            self._clear_simulation()

    def _fit_sim_view(self) -> None:
        all_points = [
            point for segment in self._current_segments for point in segment.points
        ]
        min_x = min(point[0] for point in all_points)
        max_x = max(point[0] for point in all_points)
        min_y = min(point[1] for point in all_points)
        max_y = max(point[1] for point in all_points)
        width_mm = max(max_x - min_x, 1e-6)
        height_mm = max(max_y - min_y, 1e-6)

        canvas_width, canvas_height = self._canvas_size(self.sim_canvas)
        margin = 20
        self._sim_base_scale = min(
            (canvas_width - 2 * margin) / width_mm,
            (canvas_height - 2 * margin) / height_mm,
        )
        self._sim_scale = self._sim_base_scale
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        self._sim_offset_x = canvas_width / 2 - center_x * self._sim_scale
        self._sim_offset_y = canvas_height / 2 + center_y * self._sim_scale

    def _load_preview(self, image_path: Path) -> None:
        self._current_preview_path = image_path
        self.preview_canvas.delete("all")
        canvas_width, canvas_height = self._canvas_size(self.preview_canvas)
        image = cv2.imread(str(image_path)) if image_path.is_file() else None
        if image is None:
            self.preview_photo = None
            self.preview_info_var.set("Select a PNG/JPG/BMP image to preview")
            self.preview_canvas.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text="No preview",
                fill=MUTED_COLOR,
                font=("Segoe UI", 12),
            )
            return

        height, width = image.shape[:2]
        margin = 20
        scale = min(
            (canvas_width - 2 * margin) / width,
            (canvas_height - 2 * margin) / height,
            1.0,
        )
        if scale < 1.0:
            image = cv2.resize(
                image,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        success, encoded = cv2.imencode(".png", image)
        if not success:
            self.preview_info_var.set("Unable to create preview")
            return
        encoded_data = base64.b64encode(encoded.tobytes()).decode("ascii")
        self.preview_photo = tk.PhotoImage(data=encoded_data)
        self.preview_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.preview_photo,
            anchor="center",
        )
        self.preview_info_var.set(f"{width} x {height} px  |  {image_path.name}")

    def _clear_simulation(self) -> None:
        self._pause_sim_playback()
        self._current_segments = None
        self._sim_frames = []
        self._sim_total_time = 0.0
        self._sim_cut_distance = 0.0
        self._sim_rapid_distance = 0.0
        self._sim_current_time = 0.0
        self._sim_scale = 1.0
        self._sim_base_scale = 1.0
        self._sim_offset_x = 0.0
        self._sim_offset_y = 0.0
        self.sim_readout_var.set("")
        self._sim_syncing_progress = True
        self.sim_progress_var.set(0.0)
        self._sim_syncing_progress = False
        if hasattr(self, "sim_play_button"):
            self._set_sim_playback_controls_state("disabled")
        self.sim_canvas.delete("all")
        canvas_width, canvas_height = self._canvas_size(self.sim_canvas)
        self.sim_canvas.create_text(
            canvas_width // 2,
            canvas_height // 2,
            text="No G-code to simulate yet",
            fill=MUTED_COLOR,
            font=("Segoe UI", 11),
        )
        self.sim_info_var.set("No simulation yet")

    def _load_toolpath(self, output_path: Path) -> None:
        try:
            gcode_text = output_path.read_text(encoding="ascii")
        except OSError:
            return
        self._pause_sim_playback()
        self._current_segments = parse_toolpath_segments(gcode_text)
        (
            self._sim_frames,
            self._sim_total_time,
            self._sim_cut_distance,
            self._sim_rapid_distance,
        ) = build_sim_timeline(self._current_segments)
        self._sim_current_time = 0.0
        self._fit_sim_view()
        self._set_sim_playback_controls_state(
            "normal" if self._sim_frames else "disabled"
        )
        self._draw_toolpath(self._current_segments)

    def _draw_toolpath(self, segments: list[Segment]) -> None:
        self.sim_canvas.delete("all")
        if not segments:
            self.sim_info_var.set("No toolpath to simulate")
            self.sim_readout_var.set("")
            return

        def to_canvas(point: Point) -> tuple[float, float]:
            canvas_x = point[0] * self._sim_scale + self._sim_offset_x
            canvas_y = -point[1] * self._sim_scale + self._sim_offset_y
            return canvas_x, canvas_y

        move_colors = {
            "linear": SIM_LINEAR_COLOR,
            "arc_cw": SIM_ARC_CW_COLOR,
            "arc_ccw": SIM_ARC_CCW_COLOR,
        }
        for kind, points, _feed in segments:
            flat = [coordinate for point in points for coordinate in to_canvas(point)]
            if kind == "rapid":
                self.sim_canvas.create_line(*flat, fill=SIM_RAPID_COLOR, dash=(4, 2), width=1)
            else:
                self.sim_canvas.create_line(
                    *flat,
                    fill=move_colors.get(kind, SIM_LINEAR_COLOR),
                    width=2,
                    capstyle="round",
                    joinstyle="round",
                )

        start_x, start_y = to_canvas(segments[0].points[0])
        self.sim_canvas.create_oval(
            start_x - 4, start_y - 4, start_x + 4, start_y + 4,
            fill=SUCCESS_COLOR, outline="",
        )
        end_x, end_y = to_canvas(segments[-1].points[-1])
        self.sim_canvas.create_oval(
            end_x - 4, end_y - 4, end_x + 4, end_y + 4,
            fill=ERROR_COLOR, outline="",
        )

        tool_x = tool_y = 0.0
        move_kind = "idle"
        move_feed = 0.0
        if self._sim_frames:
            trail = traveled_points(self._sim_frames, self._sim_current_time)
            tool_x, tool_y, move_kind, move_feed = sim_state_at_time(
                self._sim_frames, self._sim_current_time
            )
            if len(trail) >= 2:
                flat_trail = [coordinate for point in trail for coordinate in to_canvas(point)]
                self.sim_canvas.create_line(
                    *flat_trail,
                    fill=SIM_TRAVELED_COLOR,
                    width=3,
                    capstyle="round",
                    joinstyle="round",
                )
            tool_cx, tool_cy = to_canvas((tool_x, tool_y))
            self.sim_canvas.create_oval(
                tool_cx - 6, tool_cy - 6, tool_cx + 6, tool_cy + 6,
                fill="#ffffff", outline=SIM_TOOL_COLOR, width=2,
            )
            self.sim_canvas.create_line(
                tool_cx - 9, tool_cy, tool_cx + 9, tool_cy, fill=SIM_TOOL_COLOR
            )
            self.sim_canvas.create_line(
                tool_cx, tool_cy - 9, tool_cx, tool_cy + 9, fill=SIM_TOOL_COLOR
            )

        all_points = [point for _, points, _feed in segments for point in points]
        width_mm = max(point[0] for point in all_points) - min(point[0] for point in all_points)
        height_mm = max(point[1] for point in all_points) - min(point[1] for point in all_points)
        zoom_percent = (
            (self._sim_scale / self._sim_base_scale) * 100 if self._sim_base_scale else 100
        )
        self.sim_info_var.set(
            f"Area {width_mm:.1f} x {height_mm:.1f} mm  |  "
            f"Cut {self._sim_cut_distance:.0f} mm  |  Rapid {self._sim_rapid_distance:.0f} mm  |  "
            f"Zoom {zoom_percent:.0f}%"
        )

        move_labels = {
            "idle": "Idle",
            "rapid": "Rapid",
            "linear": "Cut",
            "arc_cw": "Arc CW",
            "arc_ccw": "Arc CCW",
        }
        progress_percent = (
            (self._sim_current_time / self._sim_total_time * 100.0)
            if self._sim_total_time > 0
            else 0.0
        )
        self.sim_readout_var.set(
            f"X {tool_x:.2f}  Y {tool_y:.2f} mm   |   Feed {move_feed:.0f} mm/min   |   "
            f"{move_labels.get(move_kind, move_kind)}   |   "
            f"{self._sim_current_time:.1f}s / {self._sim_total_time:.1f}s "
            f"({progress_percent:.0f}%)"
        )

        self._sim_syncing_progress = True
        self.sim_progress_var.set(progress_percent)
        self._sim_syncing_progress = False

    def _read_config(self) -> MachiningConfig:
        def read_float(variable: tk.StringVar, label: str) -> float:
            try:
                return float(variable.get().strip())
            except ValueError as error:
                raise ValueError(f"{label} must be a valid number.") from error

        def read_int(variable: tk.StringVar, label: str) -> int:
            try:
                return int(variable.get().strip())
            except ValueError as error:
                raise ValueError(f"{label} must be a valid integer.") from error

        config = MachiningConfig(
            cut_depth=read_float(self.cut_depth_var, "Cut depth"),
            plunge_feed=read_float(self.plunge_feed_var, "Plunge feed"),
            cut_feed=read_float(self.cut_feed_var, "Cut feed"),
            spindle_speed=read_int(self.spindle_speed_var, "Spindle speed"),
            safe_z=read_float(self.safe_z_var, "Safe Z"),
            approach_z=read_float(self.approach_z_var, "Approach Z"),
            tool_number=read_int(self.tool_number_var, "Tool number"),
            tool_offset=read_int(self.tool_offset_var, "Tool offset"),
            program_number=read_int(self.program_number_var, "Program number"),
        )
        validate_config(config)
        return config

    def _start_conversion(self) -> None:
        if self.running:
            return
        input_path = Path(self.input_var.get().strip()).expanduser()
        output_path = Path(self.output_var.get().strip()).expanduser()
        if not input_path.is_file():
            self._show_error(f"Input image not found: {input_path}")
            return
        if not output_path.name:
            self._show_error("Please choose an output G-code path.")
            return
        try:
            config = self._read_config()
        except ValueError as error:
            self._show_error(str(error))
            return

        self._set_running(True)
        self._append_log(f"Processing: {input_path}")
        worker = threading.Thread(
            target=self._conversion_worker,
            args=(input_path, output_path, config, self.strip_dimensions_var.get()),
            daemon=True,
        )
        worker.start()

    def _conversion_worker(
        self,
        input_path: Path,
        output_path: Path,
        config: MachiningConfig,
        strip_dimensions: bool,
    ) -> None:
        try:
            scale_factor, contour_count = convert_image_to_gcode(
                input_path, output_path, config, strip_dimensions=strip_dimensions
            )
        except Exception as error:  # Surface conversion errors in the GUI thread.
            self.result_queue.put(("error", error))
        else:
            self.result_queue.put(("success", (scale_factor, contour_count, output_path)))

    def _poll_results(self) -> None:
        try:
            result_type, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_results)
            return

        self._set_running(False)
        if result_type == "error":
            self._show_error(str(payload))
        else:
            scale_factor, contour_count, output_path = payload  # type: ignore[misc]
            self.status_var.set("G-code generated successfully")
            self.status_label.configure(style="Success.Status.TLabel")
            self._append_log(
                f"Created {output_path} | SF={scale_factor:.3f} pixel/mm | "
                f"contours={contour_count}"
            )
            self._load_toolpath(output_path)
        self.root.after(100, self._poll_results)

    def _set_running(self, running: bool) -> None:
        self.running = running
        state = "disabled" if running else "normal"
        for button in (
            self.input_browse_button,
            self.output_browse_button,
            self.open_output_button,
            self.reset_button,
            self.generate_button,
        ):
            button.configure(state=state)
        if running:
            self.status_var.set("Generating G-code...")
            self.status_label.configure(style="Status.TLabel")

    def _reset_defaults(self) -> None:
        self.input_var.set(str(GUI_DEFAULT_INPUT_PATH))
        self.output_var.set(str(GUI_DEFAULT_OUTPUT_PATH))
        self.cut_depth_var.set("-5.0")
        self.plunge_feed_var.set("100.0")
        self.cut_feed_var.set("300.0")
        self.spindle_speed_var.set("1500")
        self.safe_z_var.set("50.0")
        self.approach_z_var.set("2.0")
        self.tool_number_var.set("1")
        self.tool_offset_var.set("1")
        self.program_number_var.set("1000")
        self.strip_dimensions_var.set(False)
        self._load_preview(Path(self.input_var.get()))
        self._clear_simulation()
        self.status_var.set("Ready")
        self.status_label.configure(style="Status.TLabel")

    def _open_output_folder(self) -> None:
        folder = Path(self.output_var.get().strip()).expanduser().parent.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as error:
            self._show_error(f"Unable to open output folder: {error}")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _show_error(self, message: str) -> None:
        self.status_var.set("Conversion failed")
        self.status_label.configure(style="Error.Status.TLabel")
        self._append_log(message)
        messagebox.showerror("Image to G-Code", message, parent=self.root)

    def _close(self) -> None:
        if self.running and not messagebox.askyesno(
            "Conversion in progress",
            "A conversion is still running. Close the application anyway?",
            parent=self.root,
        ):
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ImageToGCodeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
