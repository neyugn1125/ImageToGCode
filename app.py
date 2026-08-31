#!/usr/bin/env python3
"""Windows & Linux-friendly GUI entry point for the Image to G-Code converter."""

from __future__ import annotations

import base64
import bisect
import math
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, NamedTuple

import cv2

from core.config import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    MachiningConfig,
    validate_config,
)
from core.pipeline import convert_image_to_gcode
from core.post import (
    Frame,
    Point,
    Segment,
    build_sim_timeline,
    parse_toolpath_segments,
    sim_state_at_time,
    traveled_points,
)
from core.vision import (
    ImageAnalysisResult,
    analyze_image,
)


WINDOW_BACKGROUND = "#f3f3f3"
PANEL_BACKGROUND = "#ffffff"
TEXT_COLOR = "#1f1f1f"
MUTED_COLOR = "#5f6368"
ACCENT_COLOR = "#0067c0"
SUCCESS_COLOR = "#107c10"
ERROR_COLOR = "#c42b1c"

# CAD Simulation Palette
SIM_CANVAS_BG = "#ffffff"
SIM_GRID_COLOR = "#e9ecef"
SIM_AXIS_X_COLOR = "#ea4335"
SIM_AXIS_Y_COLOR = "#34a853"
SIM_RAPID_COLOR = "#9aa0a6"
SIM_LINEAR_COLOR = "#1e8e3e"
SIM_ARC_CW_COLOR = "#1a73e8"
SIM_ARC_CCW_COLOR = "#e37400"
SIM_TRAVELED_COLOR = "#ff8c00"
SIM_TOOL_OUTLINE = "#e65100"
SIM_TOOL_FILL = "#fff3e0"
SIM_TOOL_CENTER = "#202124"
SIM_TICK_MS = 35
RAPID_DISPLAY_FEED = 3000.0


APP_DIRECTORY = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
GUI_DEFAULT_INPUT_PATH = APP_DIRECTORY / DEFAULT_INPUT_PATH
GUI_DEFAULT_OUTPUT_PATH = APP_DIRECTORY / DEFAULT_OUTPUT_PATH
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}



class ImageToGCodeApp(ttk.Frame):
    """Desktop interface with dual separated Image Preview and Toolpath Simulation."""

    def __init__(self, root: tk.Tk) -> None:
        root.title("Image to G-Code | Fanuc CNC")
        root.geometry("1180x920")
        root.minsize(980, 780)
        root.configure(bg=WINDOW_BACKGROUND)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        super().__init__(root, padding=(18, 12))
        self.root = root
        self.grid(row=0, column=0, sticky="nsew")

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.preview_photo: tk.PhotoImage | None = None
        self.running = False
        self._current_preview_path: Path | None = None
        self._current_analysis: ImageAnalysisResult | None = None
        self._current_segments: list[Segment] | None = None
        self._preview_scale = 1.0
        self._preview_img_offset_x = 0.0
        self._preview_img_offset_y = 0.0
        self._preview_img_w = 0
        self._preview_img_h = 0
        self._preview_resize_job: str | None = None
        self._sim_resize_job: str | None = None

        self._sim_scale = 1.0
        self._sim_base_scale = 1.0
        self._sim_offset_x = 0.0
        self._sim_offset_y = 0.0
        self._last_sim_canvas_w = 0
        self._last_sim_canvas_h = 0
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

        # Form Variables
        self.input_var = tk.StringVar(value=str(GUI_DEFAULT_INPUT_PATH))
        self.output_var = tk.StringVar(value=str(GUI_DEFAULT_OUTPUT_PATH))
        self.status_var = tk.StringVar(value="Ready")
        self.preview_info_var = tk.StringVar(value="Select an image to preview")
        self.preview_coord_var = tk.StringVar(value="")
        self.sim_info_var = tk.StringVar(value="No simulation yet")
        self.sim_readout_var = tk.StringVar(value="")
        self.sim_speed_var = tk.DoubleVar(value=5.0)
        self.sim_progress_var = tk.DoubleVar(value=0.0)

        # Machining & Tool Config
        self.cut_depth_var = tk.StringVar(value="-5.0")
        self.plunge_feed_var = tk.StringVar(value="100.0")
        self.cut_feed_var = tk.StringVar(value="300.0")
        self.spindle_speed_var = tk.StringVar(value="1500")
        self.safe_z_var = tk.StringVar(value="50.0")
        self.approach_z_var = tk.StringVar(value="2.0")
        self.tool_number_var = tk.StringVar(value="1")
        self.tool_offset_var = tk.StringVar(value="1")
        self.tool_diameter_var = tk.StringVar(value="3.0")
        self.program_number_var = tk.StringVar(value="1000")
        self.strip_dimensions_var = tk.BooleanVar(value=False)
        self.reference_width_var = tk.StringVar(value="")
        self.reference_height_var = tk.StringVar(value="")
        self.pixels_per_mm_var = tk.StringVar(value="")

        # View Toggles
        self.show_detection_tags_var = tk.BooleanVar(value=True)
        self.show_grid_var = tk.BooleanVar(value=True)
        self.show_rapids_var = tk.BooleanVar(value=True)
        self.show_arrows_var = tk.BooleanVar(value=True)
        self.show_cutter_var = tk.BooleanVar(value=True)

        self._configure_styles()
        self._build_ui()
        self._load_preview(Path(self.input_var.get()))
        self.root.after(100, self._poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

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
            font=("Segoe UI", 19, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=WINDOW_BACKGROUND,
            foreground=MUTED_COLOR,
            font=("Segoe UI", 9),
        )
        style.configure("Panel.TLabel", background=PANEL_BACKGROUND, foreground=TEXT_COLOR)
        style.configure("Muted.Panel.TLabel", background=PANEL_BACKGROUND, foreground=MUTED_COLOR)
        style.configure("Readout.Panel.TLabel", background=PANEL_BACKGROUND, foreground=TEXT_COLOR, font=("Consolas", 9, "bold"))
        style.configure("Panel.TCheckbutton", background=PANEL_BACKGROUND, foreground=TEXT_COLOR)
        style.configure("TEntry", padding=(6, 3))
        style.configure("TButton", padding=(8, 4), font=("Segoe UI", 9))
        style.configure(
            "Accent.TButton",
            background=ACCENT_COLOR,
            foreground="white",
            padding=(14, 7),
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
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Top Header
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="Image to G-Code | Fanuc CNC", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Automatic 2D calibration, contour hierarchy sequencing, and standalone CAM toolpath simulation",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(1, 0))

        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=0, minsize=350)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # ----------------- LEFT COLUMN: CONTROLS & PARAMETERS -----------------
        left_column = ttk.Frame(content, style="TFrame", width=350)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_column.columnconfigure(0, weight=1)

        paths_panel = ttk.LabelFrame(
            left_column, text="Files", style="Panel.TLabelframe", padding=10
        )
        paths_panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        paths_panel.columnconfigure(1, weight=1)
        self.input_browse_button = self._path_row(
            paths_panel, 0, "Input image", self.input_var, self._choose_input
        )
        self.output_browse_button = self._path_row(
            paths_panel, 1, "Output G-code", self.output_var, self._choose_output
        )
        self.strip_dimensions_check = ttk.Checkbutton(
            paths_panel,
            text="Remove dimension annotations before tracing",
            variable=self.strip_dimensions_var,
            style="Panel.TCheckbutton",
            command=self._on_strip_dimensions_toggled,
        )
        self.strip_dimensions_check.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        scale_panel = ttk.LabelFrame(
            left_column, text="Scale reference (optional)", style="Panel.TLabelframe", padding=10
        )
        scale_panel.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        scale_panel.columnconfigure(0, weight=1)
        scale_fields = [
            ("Reference width (mm)", self.reference_width_var),
            ("Reference height (mm)", self.reference_height_var),
            ("Pixels per mm", self.pixels_per_mm_var),
        ]
        for index, (label, variable) in enumerate(scale_fields):
            cell = ttk.Frame(scale_panel, style="TFrame")
            cell.grid(row=index, column=0, sticky="ew", pady=1)
            cell.columnconfigure(1, weight=1)
            ttk.Label(cell, text=label).grid(row=0, column=0, sticky="w")
            ttk.Entry(cell, textvariable=variable, width=11).grid(
                row=0, column=1, sticky="e"
            )

        settings = ttk.LabelFrame(
            left_column, text="Machining & Tool parameters", style="Panel.TLabelframe", padding=10
        )
        settings.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        settings.columnconfigure(0, weight=1)
        fields = [
            ("Cut depth Z (mm)", self.cut_depth_var),
            ("Plunge feed (mm/min)", self.plunge_feed_var),
            ("Cut feed (mm/min)", self.cut_feed_var),
            ("Spindle RPM", self.spindle_speed_var),
            ("Safe Z (mm)", self.safe_z_var),
            ("Approach Z (mm)", self.approach_z_var),
            ("Tool diameter Ø (mm)", self.tool_diameter_var),
            ("Tool number", self.tool_number_var),
            ("Tool offset H", self.tool_offset_var),
            ("Program number O", self.program_number_var),
        ]
        for index, (label, variable) in enumerate(fields):
            cell = ttk.Frame(settings, style="TFrame")
            cell.grid(row=index, column=0, sticky="ew", pady=1)
            cell.columnconfigure(1, weight=1)
            ttk.Label(cell, text=label).grid(row=0, column=0, sticky="w")
            ttk.Entry(cell, textvariable=variable, width=11).grid(
                row=0, column=1, sticky="e"
            )

        button_row = ttk.Frame(left_column, style="TFrame")
        button_row.grid(row=3, column=0, sticky="sew")
        self.generate_button = ttk.Button(
            button_row,
            text="Generate G-Code",
            style="Accent.TButton",
            command=self._start_conversion,
        )
        self.generate_button.pack(fill="x")
        self.reset_button = ttk.Button(
            button_row, text="Reset defaults", command=self._reset_defaults
        )
        self.reset_button.pack(fill="x", pady=(5, 0))
        self.open_output_button = ttk.Button(
            button_row, text="Open output folder", command=self._open_output_folder
        )
        self.open_output_button.pack(fill="x", pady=(5, 0))

        # ----------------- RIGHT COLUMN: 2 SEPARATE PANELS -----------------
        right_panel = ttk.Frame(content, style="TFrame")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)  # Preview
        right_panel.rowconfigure(1, weight=2)  # Simulator

        # 1. Image Preview Panel (Analysis & Detection Inspector)
        preview_panel = ttk.LabelFrame(
            right_panel, text="1. Image Preview (Source Drawing & Analysis)", style="Panel.TLabelframe", padding=8
        )
        preview_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(1, weight=1)

        preview_top_bar = ttk.Frame(preview_panel, style="TFrame")
        preview_top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        preview_top_bar.columnconfigure(0, weight=1)
        self.show_tags_check = ttk.Checkbutton(
            preview_top_bar,
            text="Show detection tags (10x10mm Calib, G54, Envelope)",
            variable=self.show_detection_tags_var,
            style="Panel.TCheckbutton",
            command=self._redraw_preview,
        )
        self.show_tags_check.grid(row=0, column=0, sticky="w")

        self.preview_canvas = tk.Canvas(
            preview_panel,
            width=560,
            height=160,
            background="#fafafa",
            highlightthickness=1,
            highlightbackground="#dedede",
        )
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_configure)
        self.preview_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.preview_canvas.bind("<Leave>", self._on_preview_mouse_leave)

        preview_footer = ttk.Frame(preview_panel, style="TFrame")
        preview_footer.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        preview_footer.columnconfigure(0, weight=1)
        preview_footer.columnconfigure(1, weight=1)
        ttk.Label(
            preview_footer,
            textvariable=self.preview_info_var,
            style="Muted.Panel.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            preview_footer,
            textvariable=self.preview_coord_var,
            style="Muted.Panel.TLabel",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        # 2. Toolpath Simulation Panel (Standalone Clean CAD/CAM View)
        simulation_panel = ttk.LabelFrame(
            right_panel,
            text="2. Toolpath Simulation (Clean CAD/CAM View)",
            style="Panel.TLabelframe",
            padding=8,
        )
        simulation_panel.grid(row=1, column=0, sticky="nsew")
        simulation_panel.columnconfigure(0, weight=1)
        simulation_panel.rowconfigure(1, weight=1)

        # View Toggles Bar
        view_bar = ttk.Frame(simulation_panel, style="TFrame")
        view_bar.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        view_toggles = [
            ("Grid & Axes", self.show_grid_var),
            ("Rapids (G00)", self.show_rapids_var),
            ("Direction Arrows", self.show_arrows_var),
            ("Cutter Profile (Ø)", self.show_cutter_var),
        ]
        for idx, (label_text, var) in enumerate(view_toggles):
            chk = ttk.Checkbutton(
                view_bar,
                text=label_text,
                variable=var,
                style="Panel.TCheckbutton",
                command=self._redraw_simulation,
            )
            chk.pack(side="left", padx=(0 if idx == 0 else 12, 0))

        self.sim_canvas = tk.Canvas(
            simulation_panel,
            width=560,
            height=260,
            background=SIM_CANVAS_BG,
            highlightthickness=1,
            highlightbackground="#dedede",
        )
        self.sim_canvas.grid(row=1, column=0, sticky="nsew")
        self.sim_canvas.bind("<Configure>", self._on_sim_canvas_configure)
        self.sim_canvas.bind("<MouseWheel>", self._on_sim_zoom)
        self.sim_canvas.bind("<Button-4>", self._on_sim_zoom)
        self.sim_canvas.bind("<Button-5>", self._on_sim_zoom)
        self.sim_canvas.bind("<ButtonPress-1>", self._on_sim_drag_start)
        self.sim_canvas.bind("<B1-Motion>", self._on_sim_drag_move)
        self.sim_canvas.bind("<ButtonRelease-1>", self._on_sim_drag_end)

        # Playback Controls Bar
        sim_controls = ttk.Frame(simulation_panel, style="TFrame")
        sim_controls.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.sim_play_button = ttk.Button(
            sim_controls, text="Play", width=6, command=self._toggle_sim_playback
        )
        self.sim_play_button.pack(side="left")
        self.sim_step_back_button = ttk.Button(
            sim_controls, text="|<", width=3, command=self._step_back_sim_playback
        )
        self.sim_step_back_button.pack(side="left", padx=(3, 0))
        self.sim_step_button = ttk.Button(
            sim_controls, text=">|", width=3, command=self._step_sim_playback
        )
        self.sim_step_button.pack(side="left", padx=(3, 0))
        self.sim_playback_reset_button = ttk.Button(
            sim_controls, text="Restart", width=7, command=self._reset_sim_playback
        )
        self.sim_playback_reset_button.pack(side="left", padx=(5, 0))

        ttk.Label(sim_controls, text="Speed", style="Muted.Panel.TLabel").pack(
            side="left", padx=(10, 3)
        )
        self.sim_speed_scale = ttk.Scale(
            sim_controls,
            from_=1.0,
            to=50.0,
            orient="horizontal",
            variable=self.sim_speed_var,
            length=85,
            command=self._on_sim_speed_change,
        )
        self.sim_speed_scale.pack(side="left")
        self.sim_speed_label = ttk.Label(
            sim_controls, text="5x", style="Muted.Panel.TLabel", width=4
        )
        self.sim_speed_label.pack(side="left", padx=(3, 0))

        self.sim_reset_view_button = ttk.Button(
            sim_controls, text="Recenter", width=8, command=self._reset_sim_view
        )
        self.sim_reset_view_button.pack(side="right")

        # Scrubber Row
        sim_scrub_row = ttk.Frame(simulation_panel, style="TFrame")
        sim_scrub_row.grid(row=3, column=0, sticky="ew", pady=(3, 0))
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

        # Live Real-time Readout (Monospace font, clean non-stretching container)
        readout_frame = ttk.Frame(simulation_panel, style="TFrame")
        readout_frame.grid(row=4, column=0, sticky="ew", pady=(3, 0))
        readout_frame.columnconfigure(0, weight=1)
        ttk.Label(
            readout_frame,
            textvariable=self.sim_readout_var,
            style="Readout.Panel.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Simulation Footer Summary
        sim_footer = ttk.Frame(simulation_panel, style="TFrame")
        sim_footer.grid(row=5, column=0, sticky="ew", pady=(3, 0))
        sim_footer.columnconfigure(0, weight=1)
        ttk.Label(
            sim_footer,
            textvariable=self.sim_info_var,
            style="Muted.Panel.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._clear_simulation()

        # Bottom Global Status & Log
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            actions, textvariable=self.status_var, style="Status.TLabel"
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        self.log = tk.Text(
            self,
            height=3,
            state="disabled",
            background="#ffffff",
            foreground=TEXT_COLOR,
            relief="flat",
            borderwidth=1,
            padx=6,
            pady=3,
        )
        self.log.grid(row=3, column=0, sticky="ew", pady=(6, 0))

    def _path_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> ttk.Button:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        button = ttk.Button(parent, text="Browse", command=command)
        button.grid(row=row, column=1, sticky="w", pady=3)
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

    def _on_strip_dimensions_toggled(self) -> None:
        if self._current_preview_path is not None:
            self._load_preview(self._current_preview_path)

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
        self._preview_resize_job = self.root.after(100, self._redraw_preview)

    def _redraw_preview(self) -> None:
        self._preview_resize_job = None
        if self._current_preview_path is not None:
            self._load_preview(self._current_preview_path)

    def _on_preview_mouse_move(self, event: tk.Event) -> None:
        if self._preview_img_w <= 0 or self._preview_img_h <= 0:
            return
        img_x = (event.x - self._preview_img_offset_x) / self._preview_scale
        img_y = (event.y - self._preview_img_offset_y) / self._preview_scale
        if 0 <= img_x < self._preview_img_w and 0 <= img_y < self._preview_img_h:
            px_text = f"Cursor: {int(img_x)}, {int(img_y)} px"
            if (
                self._current_analysis is not None
                and self._current_analysis.scale_factor is not None
                and self._current_analysis.g54_origin_px is not None
            ):
                x_min, y_max = self._current_analysis.g54_origin_px
                sf = self._current_analysis.scale_factor
                mm_x = (img_x - x_min) / sf
                mm_y = (y_max - img_y) / sf
                self.preview_coord_var.set(f"{px_text}  |  G54: X={mm_x:.2f}, Y={mm_y:.2f} mm")
            else:
                self.preview_coord_var.set(px_text)
        else:
            self.preview_coord_var.set("")

    def _on_preview_mouse_leave(self, _event: tk.Event) -> None:
        self.preview_coord_var.set("")

    def _load_preview(self, image_path: Path) -> None:
        self._current_preview_path = image_path
        self.preview_canvas.delete("all")
        canvas_width, canvas_height = self._canvas_size(self.preview_canvas)
        image = cv2.imread(str(image_path)) if image_path.is_file() else None
        if image is None:
            self.preview_photo = None
            self._current_analysis = None
            self._preview_img_w = self._preview_img_h = 0
            self.preview_info_var.set("Select a PNG/JPG/BMP image to preview")
            self.preview_canvas.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text="No image preview available",
                fill=MUTED_COLOR,
                font=("Segoe UI", 11),
            )
            return

        orig_h, orig_w = image.shape[:2]
        self._preview_img_w = orig_w
        self._preview_img_h = orig_h

        # Run analysis to extract calibration, envelope, and G54 origin
        try:
            ref_w, ref_h, px_mm = self._read_scale_reference_safe()
            self._current_analysis = analyze_image(
                image_path,
                strip_dimensions=self.strip_dimensions_var.get(),
                reference_width_mm=ref_w,
                reference_height_mm=ref_h,
                pixels_per_mm=px_mm,
            )
        except Exception:
            self._current_analysis = None

        margin = 15
        scale = min(
            (canvas_width - 2 * margin) / max(orig_w, 1),
            (canvas_height - 2 * margin) / max(orig_h, 1),
            1.0,
        )
        self._preview_scale = scale
        disp_w = max(1, int(orig_w * scale))
        disp_h = max(1, int(orig_h * scale))
        self._preview_img_offset_x = (canvas_width - disp_w) / 2.0
        self._preview_img_offset_y = (canvas_height - disp_h) / 2.0

        resized_img = cv2.resize(image, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        success, encoded = cv2.imencode(".png", resized_img)
        if not success:
            self.preview_info_var.set("Unable to create image preview")
            return
        encoded_data = base64.b64encode(encoded.tobytes()).decode("ascii")
        self.preview_photo = tk.PhotoImage(data=encoded_data)
        self.preview_canvas.create_image(
            int(self._preview_img_offset_x),
            int(self._preview_img_offset_y),
            image=self.preview_photo,
            anchor="nw",
        )

        # Draw detection overlays if enabled
        if self.show_detection_tags_var.get() and self._current_analysis is not None:
            self._draw_detection_tags_on_preview()

        info_parts = [f"{orig_w} x {orig_h} px", image_path.name]
        if self._current_analysis is not None:
            if self._current_analysis.scale_factor is not None:
                info_parts.append(f"SF={self._current_analysis.scale_factor:.2f} px/mm")
            if self._current_analysis.contour_count > 0:
                info_parts.append(f"{self._current_analysis.contour_count} contour(s)")
        self.preview_info_var.set("  |  ".join(info_parts))

    def _draw_detection_tags_on_preview(self) -> None:
        analysis = self._current_analysis
        if analysis is None:
            return

        def img_to_canvas(px_x: float, px_y: float) -> tuple[float, float]:
            return (
                px_x * self._preview_scale + self._preview_img_offset_x,
                px_y * self._preview_scale + self._preview_img_offset_y,
            )

        # 1. Calibration square marker (Bright Green)
        if analysis.calibration_bbox_px is not None:
            cx, cy, cw, ch = analysis.calibration_bbox_px
            c_x1, c_y1 = img_to_canvas(cx, cy)
            c_x2, c_y2 = img_to_canvas(cx + cw, cy + ch)
            self.preview_canvas.create_rectangle(
                c_x1, c_y1, c_x2, c_y2, outline="#107c10", width=2
            )
            tag_label = "10x10 mm Calib"
            self.preview_canvas.create_rectangle(
                c_x1, c_y1 - 16, c_x1 + 84, c_y1, fill="#107c10", outline=""
            )
            self.preview_canvas.create_text(
                c_x1 + 4, c_y1 - 8, text=tag_label, fill="white", font=("Segoe UI", 8, "bold"), anchor="w"
            )

        # 2. Machining envelope bounding box (Blue dashed)
        if analysis.machining_bbox_px is not None:
            mx1, my1, mx2, my2 = analysis.machining_bbox_px
            bx1, by1 = img_to_canvas(mx1, my1)
            bx2, by2 = img_to_canvas(mx2, my2)
            self.preview_canvas.create_rectangle(
                bx1, by1, bx2, by2, outline="#0078d4", width=1, dash=(4, 3)
            )

        # 3. G54 Origin point (Red Crosshair Target)
        if analysis.g54_origin_px is not None:
            ox, oy = analysis.g54_origin_px
            cox, coy = img_to_canvas(ox, oy)
            self.preview_canvas.create_oval(
                cox - 6, coy - 6, cox + 6, coy + 6, outline="#d93025", width=2
            )
            self.preview_canvas.create_line(
                cox - 9, coy, cox + 9, coy, fill="#d93025", width=1.5
            )
            self.preview_canvas.create_line(
                cox, coy - 9, cox, coy + 9, fill="#d93025", width=1.5
            )
            self.preview_canvas.create_text(
                cox + 8, coy - 8, text="G54 (0,0)", fill="#d93025", font=("Segoe UI", 8, "bold"), anchor="sw"
            )

    def _read_scale_reference_safe(self) -> tuple[float | None, float | None, float | None]:
        def parse(var: tk.StringVar) -> float | None:
            text = var.get().strip()
            if not text:
                return None
            try:
                val = float(text)
                return val if math.isfinite(val) and val > 0 else None
            except ValueError:
                return None

        return parse(self.reference_width_var), parse(self.reference_height_var), parse(self.pixels_per_mm_var)

    def _get_tool_diameter(self) -> float:
        try:
            val = float(self.tool_diameter_var.get().strip())
            return max(0.0, val) if math.isfinite(val) else 3.0
        except ValueError:
            return 3.0

    # ----------------- SIMULATION CANVAS RENDERING -----------------

    def _on_sim_canvas_configure(self, event: tk.Event) -> None:
        new_w, new_h = event.width, event.height
        if new_w <= 1 or new_h <= 1:
            return
        if abs(new_w - self._last_sim_canvas_w) <= 2 and abs(new_h - self._last_sim_canvas_h) <= 2:
            return
        self._last_sim_canvas_w = new_w
        self._last_sim_canvas_h = new_h
        if self._sim_resize_job is not None:
            self.root.after_cancel(self._sim_resize_job)
        self._sim_resize_job = self.root.after(100, self._redraw_simulation)

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
        min_scale = self._sim_base_scale * 0.15
        max_scale = self._sim_base_scale * 30.0
        new_scale = min(max_scale, max(min_scale, self._sim_scale * factor))

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
            self.sim_step_back_button,
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
        self._draw_dynamic_tool()
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
        self._draw_dynamic_tool()

    def _step_back_sim_playback(self) -> None:
        if not self._sim_frames:
            return
        self._pause_sim_playback()
        prev_time = 0.0
        for frame in self._sim_frames:
            if frame.time < self._sim_current_time - 1e-9:
                prev_time = frame.time
            else:
                break
        self._sim_current_time = prev_time
        self._draw_dynamic_tool()

    def _reset_sim_playback(self) -> None:
        self._pause_sim_playback()
        self._sim_current_time = 0.0
        if self._current_segments is not None:
            self._draw_dynamic_tool()

    def _on_sim_scrub(self, value_str: str) -> None:
        if self._sim_syncing_progress or not self._sim_frames:
            return
        self._pause_sim_playback()
        fraction = max(0.0, min(1.0, float(value_str) / 100.0))
        self._sim_current_time = fraction * self._sim_total_time
        self._draw_dynamic_tool()

    def _reset_sim_view(self) -> None:
        if self._current_segments:
            self._fit_sim_view()
            self._draw_toolpath(self._current_segments)
        else:
            self._clear_simulation()

    def _fit_sim_view(self) -> None:
        if not self._current_segments:
            return
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
        margin = 35
        self._sim_base_scale = min(
            (canvas_width - 2 * margin) / width_mm,
            (canvas_height - 2 * margin) / height_mm,
        )
        self._sim_scale = self._sim_base_scale
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        self._sim_offset_x = canvas_width / 2 - center_x * self._sim_scale
        self._sim_offset_y = canvas_height / 2 + center_y * self._sim_scale

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
            text="No toolpath generated yet. Click 'Generate G-Code' to simulate.",
            fill=MUTED_COLOR,
            font=("Segoe UI", 11),
        )
        self.sim_info_var.set("No simulation yet")

    def _draw_sim_grid(self, canvas_width: int, canvas_height: int) -> None:
        """Render responsive metric grid and G54 (X/Y) coordinate axes."""
        if self._sim_scale <= 1e-6:
            return

        target_px = 60.0
        raw_step = target_px / self._sim_scale
        steps = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0]
        grid_step = steps[-1]
        for s in steps:
            if s >= raw_step:
                grid_step = s
                break

        min_world_x = (0 - self._sim_offset_x) / self._sim_scale
        max_world_x = (canvas_width - self._sim_offset_x) / self._sim_scale
        min_world_y = (self._sim_offset_y - canvas_height) / self._sim_scale
        max_world_y = (self._sim_offset_y - 0) / self._sim_scale

        start_x_idx = math.floor(min_world_x / grid_step)
        end_x_idx = math.ceil(max_world_x / grid_step)
        start_y_idx = math.floor(min_world_y / grid_step)
        end_y_idx = math.ceil(max_world_y / grid_step)

        # Draw Grid Lines
        for idx in range(start_x_idx, end_x_idx + 1):
            wx = idx * grid_step
            cx = wx * self._sim_scale + self._sim_offset_x
            if 0 <= cx <= canvas_width:
                self.sim_canvas.create_line(
                    cx, 0, cx, canvas_height, fill=SIM_GRID_COLOR, width=1, tags="static_scene"
                )
                if idx != 0 and abs(wx) >= 1e-4:
                    label = f"{wx:.0f}" if grid_step >= 1.0 else f"{wx:.1f}"
                    self.sim_canvas.create_text(
                        cx + 2, canvas_height - 8, text=label, fill="#a0a0a0", font=("Segoe UI", 7), anchor="sw", tags="static_scene"
                    )

        for idx in range(start_y_idx, end_y_idx + 1):
            wy = idx * grid_step
            cy = -wy * self._sim_scale + self._sim_offset_y
            if 0 <= cy <= canvas_height:
                self.sim_canvas.create_line(
                    0, cy, canvas_width, cy, fill=SIM_GRID_COLOR, width=1, tags="static_scene"
                )
                if idx != 0 and abs(wy) >= 1e-4:
                    label = f"{wy:.0f}" if grid_step >= 1.0 else f"{wy:.1f}"
                    self.sim_canvas.create_text(
                        6, cy - 2, text=label, fill="#a0a0a0", font=("Segoe UI", 7), anchor="nw", tags="static_scene"
                    )

        # Draw Main G54 Axes
        origin_cx = self._sim_offset_x
        origin_cy = self._sim_offset_y

        # X-Axis (Red)
        if 0 <= origin_cy <= canvas_height:
            self.sim_canvas.create_line(
                0, origin_cy, canvas_width, origin_cy, fill=SIM_AXIS_X_COLOR, width=1.5, tags="static_scene"
            )
            self.sim_canvas.create_text(
                canvas_width - 8, origin_cy - 4, text="+X (mm)", fill=SIM_AXIS_X_COLOR, font=("Segoe UI", 8, "bold"), anchor="se", tags="static_scene"
            )

        # Y-Axis (Green)
        if 0 <= origin_cx <= canvas_width:
            self.sim_canvas.create_line(
                origin_cx, 0, origin_cx, canvas_height, fill=SIM_AXIS_Y_COLOR, width=1.5, tags="static_scene"
            )
            self.sim_canvas.create_text(
                origin_cx + 4, 8, text="+Y (mm)", fill=SIM_AXIS_Y_COLOR, font=("Segoe UI", 8, "bold"), anchor="nw", tags="static_scene"
            )

        # Origin Symbol G54
        if 0 <= origin_cx <= canvas_width and 0 <= origin_cy <= canvas_height:
            self.sim_canvas.create_oval(
                origin_cx - 5, origin_cy - 5, origin_cx + 5, origin_cy + 5, outline="#202124", width=1.5, tags="static_scene"
            )
            self.sim_canvas.create_text(
                origin_cx + 6, origin_cy + 6, text="G54 (0,0)", fill="#202124", font=("Segoe UI", 8, "bold"), anchor="nw", tags="static_scene"
            )

    def _draw_direction_arrows(self, points: list[Point], color: str) -> None:
        """Draw subtle chevrons along path moves to show cutting direction."""
        for p1, p2 in zip(points, points[1:]):
            cx1 = p1[0] * self._sim_scale + self._sim_offset_x
            cy1 = -p1[1] * self._sim_scale + self._sim_offset_y
            cx2 = p2[0] * self._sim_scale + self._sim_offset_x
            cy2 = -p2[1] * self._sim_scale + self._sim_offset_y

            dx = cx2 - cx1
            dy = cy2 - cy1
            length = math.hypot(dx, dy)
            if length < 22.0:
                continue

            mx = (cx1 + cx2) / 2.0
            my = (cy1 + cy2) / 2.0
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux

            arrow_len = 5.0
            arrow_w = 3.5
            tip_x = mx + ux * (arrow_len * 0.5)
            tip_y = my + uy * (arrow_len * 0.5)
            w1_x = mx - ux * (arrow_len * 0.5) + nx * arrow_w
            w1_y = my - uy * (arrow_len * 0.5) + ny * arrow_w
            w2_x = mx - ux * (arrow_len * 0.5) - nx * arrow_w
            w2_y = my - uy * (arrow_len * 0.5) - ny * arrow_w

            self.sim_canvas.create_line(
                w1_x, w1_y, tip_x, tip_y, w2_x, w2_y, fill=color, width=1.5, joinstyle="miter", tags="static_scene"
            )

    def _to_canvas(self, point: Point) -> tuple[float, float]:
        canvas_x = point[0] * self._sim_scale + self._sim_offset_x
        canvas_y = -point[1] * self._sim_scale + self._sim_offset_y
        return canvas_x, canvas_y

    def _draw_toolpath(self, segments: list[Segment]) -> None:
        """Render complete static scene and dynamic tool position."""
        self.sim_canvas.delete("all")
        if not segments:
            self.sim_info_var.set("No toolpath to simulate")
            self.sim_readout_var.set("")
            return

        canvas_width, canvas_height = self._canvas_size(self.sim_canvas)

        # 1. Grid & Coordinate Axes
        if self.show_grid_var.get():
            self._draw_sim_grid(canvas_width, canvas_height)

        move_colors = {
            "linear": SIM_LINEAR_COLOR,
            "arc_cw": SIM_ARC_CW_COLOR,
            "arc_ccw": SIM_ARC_CCW_COLOR,
        }

        # 2. Draw Toolpath Segments
        show_rapids = self.show_rapids_var.get()
        show_arrows = self.show_arrows_var.get()

        for kind, points, _feed, _z in segments:
            if kind == "rapid":
                if show_rapids:
                    flat = [coord for pt in points for coord in self._to_canvas(pt)]
                    self.sim_canvas.create_line(
                        *flat, fill=SIM_RAPID_COLOR, dash=(4, 2), width=1, tags="static_scene"
                    )
            else:
                flat = [coord for pt in points for coord in self._to_canvas(pt)]
                c = move_colors.get(kind, SIM_LINEAR_COLOR)
                self.sim_canvas.create_line(
                    *flat,
                    fill=c,
                    width=2,
                    capstyle="butt",
                    joinstyle="miter",
                    tags="static_scene",
                )
                if show_arrows:
                    self._draw_direction_arrows(points, c)

        # Start (Green) and End (Red) Nodes
        start_x, start_y = self._to_canvas(segments[0].points[0])
        self.sim_canvas.create_oval(
            start_x - 4, start_y - 4, start_x + 4, start_y + 4,
            fill=SUCCESS_COLOR, outline="", tags="static_scene"
        )
        end_x, end_y = self._to_canvas(segments[-1].points[-1])
        self.sim_canvas.create_oval(
            end_x - 4, end_y - 4, end_x + 4, end_y + 4,
            fill=ERROR_COLOR, outline="", tags="static_scene"
        )

        all_points = [point for _, pts, _feed, _z in segments for point in pts]
        width_mm = max(pt[0] for pt in all_points) - min(pt[0] for pt in all_points)
        height_mm = max(pt[1] for pt in all_points) - min(pt[1] for pt in all_points)
        zoom_percent = (
            (self._sim_scale / self._sim_base_scale) * 100 if self._sim_base_scale else 100
        )
        self.sim_info_var.set(
            f"Envelope: {width_mm:.1f} x {height_mm:.1f} mm  |  "
            f"Cut Distance: {self._sim_cut_distance:.0f} mm  |  Rapid: {self._sim_rapid_distance:.0f} mm  |  "
            f"Zoom: {zoom_percent:.0f}%"
        )

        # Draw dynamic tool overlay
        self._draw_dynamic_tool()

    def _draw_dynamic_tool(self) -> None:
        """Update ONLY the tool position, trail, and readout without redrawing the whole canvas."""
        self.sim_canvas.delete("dynamic_tool")
        if not self._sim_frames:
            return

        tool_dia = self._get_tool_diameter()
        trail = traveled_points(self._sim_frames, self._sim_current_time)
        tool_x, tool_y, tool_z, move_kind, move_feed = sim_state_at_time(
            self._sim_frames, self._sim_current_time
        )

        # 1. Traveled Trail
        if len(trail) >= 2:
            flat_trail = [coord for pt in trail for coord in self._to_canvas(pt)]
            self.sim_canvas.create_line(
                *flat_trail,
                fill=SIM_TRAVELED_COLOR,
                width=3,
                capstyle="butt",
                joinstyle="miter",
                tags="dynamic_tool",
            )

        tool_cx, tool_cy = self._to_canvas((tool_x, tool_y))

        # 2. Circular Cutter Profile
        if self.show_cutter_var.get() and tool_dia > 0:
            tool_r_px = (tool_dia / 2.0) * self._sim_scale
            if tool_r_px >= 1.0:
                self.sim_canvas.create_oval(
                    tool_cx - tool_r_px,
                    tool_cy - tool_r_px,
                    tool_cx + tool_r_px,
                    tool_cy + tool_r_px,
                    outline=SIM_TOOL_OUTLINE,
                    fill=SIM_TOOL_FILL,
                    width=1.5,
                    tags="dynamic_tool",
                )

        # 3. Center Crosshair
        self.sim_canvas.create_oval(
            tool_cx - 4, tool_cy - 4, tool_cx + 4, tool_cy + 4,
            fill="#ffffff", outline=SIM_TOOL_CENTER, width=1.5, tags="dynamic_tool"
        )
        self.sim_canvas.create_line(
            tool_cx - 7, tool_cy, tool_cx + 7, tool_cy, fill=SIM_TOOL_CENTER, tags="dynamic_tool"
        )
        self.sim_canvas.create_line(
            tool_cx, tool_cy - 7, tool_cx, tool_cy + 7, fill=SIM_TOOL_CENTER, tags="dynamic_tool"
        )

        # 4. Status Readout & Scrubber Update
        move_labels = {
            "idle": "Idle",
            "rapid": "Rapid (G00)",
            "linear": "Cut (G01)",
            "arc_cw": "Arc CW (G02)",
            "arc_ccw": "Arc CCW (G03)",
        }
        progress_percent = (
            (self._sim_current_time / self._sim_total_time * 100.0)
            if self._sim_total_time > 0
            else 0.0
        )
        self.sim_readout_var.set(
            f"X: {tool_x:6.2f} mm   Y: {tool_y:6.2f} mm   Z: {tool_z:5.2f} mm   |   "
            f"F: {move_feed:5.0f} mm/min   |   "
            f"{move_labels.get(move_kind, move_kind):<14}   |   "
            f"{self._sim_current_time:5.1f}s / {self._sim_total_time:5.1f}s ({progress_percent:3.0f}%)"
        )

        self._sim_syncing_progress = True
        self.sim_progress_var.set(progress_percent)
        self._sim_syncing_progress = False

    # ----------------- CONVERSION WORKER & POLL -----------------

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

    def _read_scale_reference(self) -> tuple[float | None, float | None, float | None]:
        def read_optional(variable: tk.StringVar, label: str) -> float | None:
            text = variable.get().strip()
            if not text:
                return None
            try:
                value = float(text)
            except ValueError as error:
                raise ValueError(f"{label} must be a valid number.") from error
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be greater than 0.")
            return value

        reference_width = read_optional(self.reference_width_var, "Reference width")
        reference_height = read_optional(self.reference_height_var, "Reference height")
        pixels_per_mm = read_optional(self.pixels_per_mm_var, "Pixels per mm")
        if pixels_per_mm is not None and (
            reference_width is not None or reference_height is not None
        ):
            raise ValueError(
                "Pixels per mm cannot be combined with reference dimensions."
            )
        return reference_width, reference_height, pixels_per_mm

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
            scale_reference = self._read_scale_reference()
        except ValueError as error:
            self._show_error(str(error))
            return

        self._set_running(True)
        self._append_log(f"Processing: {input_path}")
        worker = threading.Thread(
            target=self._conversion_worker,
            args=(
                input_path,
                output_path,
                config,
                self.strip_dimensions_var.get(),
                scale_reference,
            ),
            daemon=True,
        )
        worker.start()

    def _conversion_worker(
        self,
        input_path: Path,
        output_path: Path,
        config: MachiningConfig,
        strip_dimensions: bool,
        scale_reference: tuple[float | None, float | None, float | None],
    ) -> None:
        temporary_path: Path | None = None
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=str(output_path.parent),
            )
            os.close(fd)
            temporary_path = Path(temporary_name)
            reference_width, reference_height, pixels_per_mm = scale_reference
            scale_factor, contour_count = convert_image_to_gcode(
                input_path,
                temporary_path,
                config,
                strip_dimensions=strip_dimensions,
                reference_width_mm=reference_width,
                reference_height_mm=reference_height,
                pixels_per_mm=pixels_per_mm,
            )
            os.replace(temporary_path, output_path)
            temporary_path = None
        except Exception as error:
            self.result_queue.put(("error", error))
        else:
            self.result_queue.put(("success", (scale_factor, contour_count, output_path)))
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def _poll_results(self) -> None:
        try:
            result_type, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_results)
            return

        self._set_running(False)
        if result_type == "error":
            self._show_error(str(payload))
        elif result_type == "toolpath_ready":
            _output_path, segments = payload  # type: ignore[misc]
            self._apply_toolpath(segments)  # type: ignore[arg-type]
        elif result_type == "toolpath_error":
            self._append_log(f"Unable to load toolpath simulation: {payload}")
        else:
            scale_factor, contour_count, output_path = payload  # type: ignore[misc]
            self.status_var.set("G-code generated successfully")
            self.status_label.configure(style="Success.Status.TLabel")
            self._append_log(
                f"Created {output_path} | SF={scale_factor:.3f} px/mm | "
                f"contours={contour_count}"
            )
            self._load_toolpath(output_path)
        self.root.after(100, self._poll_results)

    def _load_toolpath(self, output_path: Path) -> None:
        self.sim_info_var.set("Loading toolpath simulation...")
        worker = threading.Thread(
            target=self._toolpath_worker,
            args=(output_path,),
            daemon=True,
        )
        worker.start()

    def _toolpath_worker(self, output_path: Path) -> None:
        try:
            gcode_text = output_path.read_text(encoding="ascii")
            segments = parse_toolpath_segments(gcode_text)
        except (OSError, UnicodeError) as error:
            self.result_queue.put(("toolpath_error", error))
            return

        self.result_queue.put(("toolpath_ready", (output_path, segments)))

    def _apply_toolpath(self, segments: list[Segment]) -> None:
        self._pause_sim_playback()
        self._current_segments = segments
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

    def _set_running(self, running: bool) -> None:
        self.running = running
        state = "disabled" if running else "normal"
        for button in (
            self.input_browse_button,
            self.output_browse_button,
            self.strip_dimensions_check,
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
        self.tool_diameter_var.set("3.0")
        self.tool_number_var.set("1")
        self.tool_offset_var.set("1")
        self.program_number_var.set("1000")
        self.strip_dimensions_var.set(False)
        self.reference_width_var.set("")
        self.reference_height_var.set("")
        self.pixels_per_mm_var.set("")
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
