#!/usr/bin/env python3
"""Windows-friendly GUI entry point for the Image to G-Code converter."""

from __future__ import annotations

import base64
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

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


APP_DIRECTORY = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
GUI_DEFAULT_INPUT_PATH = APP_DIRECTORY / DEFAULT_INPUT_PATH
GUI_DEFAULT_OUTPUT_PATH = APP_DIRECTORY / DEFAULT_OUTPUT_PATH


class ImageToGCodeApp(ttk.Frame):
    """Desktop interface around the existing conversion pipeline."""

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        self.root = root
        self.root.title("Image to G-Code | Fanuc CNC")
        self.root.geometry("1040x760")
        self.root.minsize(900, 680)
        self.root.configure(bg=WINDOW_BACKGROUND)

        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.preview_photo: tk.PhotoImage | None = None
        self.running = False

        self.input_var = tk.StringVar(value=str(GUI_DEFAULT_INPUT_PATH))
        self.output_var = tk.StringVar(value=str(GUI_DEFAULT_OUTPUT_PATH))
        self.status_var = tk.StringVar(value="Ready")
        self.preview_info_var = tk.StringVar(value="Chọn một ảnh để xem preview")
        self.cut_depth_var = tk.StringVar(value="-5.0")
        self.plunge_feed_var = tk.StringVar(value="100.0")
        self.cut_feed_var = tk.StringVar(value="300.0")
        self.spindle_speed_var = tk.StringVar(value="1500")
        self.safe_z_var = tk.StringVar(value="50.0")
        self.approach_z_var = tk.StringVar(value="2.0")
        self.tool_number_var = tk.StringVar(value="1")
        self.tool_offset_var = tk.StringVar(value="1")
        self.program_number_var = tk.StringVar(value="1000")

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
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)
        self.grid(sticky="nsew", padx=24, pady=20)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ttk.Label(header, text="Image to G-Code", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Fanuc profile milling with automatic 10 x 10 mm calibration",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        paths_panel = ttk.LabelFrame(
            content, text="Files", style="Panel.TLabelframe", padding=16
        )
        paths_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
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
        ttk.Label(
            paths_panel,
            text=(
                "The calibration square is detected automatically and excluded "
                "from toolpath output."
            ),
            style="Muted.Panel.TLabel",
            wraplength=520,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(16, 0))

        preview_panel = ttk.LabelFrame(
            content, text="Preview", style="Panel.TLabelframe", padding=12
        )
        preview_panel.grid(row=0, column=1, sticky="nsew")
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            preview_panel,
            width=440,
            height=300,
            background="#fafafa",
            highlightthickness=1,
            highlightbackground="#dedede",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            preview_panel,
            textvariable=self.preview_info_var,
            style="Muted.Panel.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        settings = ttk.LabelFrame(
            self, text="Machining parameters", style="Panel.TLabelframe", padding=16
        )
        settings.grid(row=2, column=0, sticky="ew", pady=(16, 12))
        for column in range(6):
            settings.columnconfigure(column, weight=1)
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
            row, column = divmod(index, 6)
            cell = ttk.Frame(settings, style="TFrame")
            cell.grid(row=row, column=column, sticky="ew", padx=5, pady=4)
            cell.columnconfigure(0, weight=1)
            ttk.Label(cell, text=label).grid(row=0, column=0, sticky="w")
            ttk.Entry(cell, textvariable=variable, width=15).grid(
                row=1, column=0, sticky="ew", pady=(4, 0)
            )

        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            actions, textvariable=self.status_var, style="Status.TLabel"
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=130)
        self.progress.grid(row=0, column=1, padx=(12, 12))
        self.open_output_button = ttk.Button(
            actions, text="Open output folder", command=self._open_output_folder
        )
        self.open_output_button.grid(row=0, column=2, padx=(0, 8))
        self.reset_button = ttk.Button(
            actions, text="Reset", command=self._reset_defaults
        )
        self.reset_button.grid(row=0, column=3, padx=(0, 8))
        self.generate_button = ttk.Button(
            actions,
            text="Generate G-Code",
            style="Accent.TButton",
            command=self._start_conversion,
        )
        self.generate_button.grid(row=0, column=4)

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
        self.log.grid(row=4, column=0, sticky="ew", pady=(12, 0))

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
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=6
        )
        button = ttk.Button(parent, text="Browse", command=command)
        button.grid(row=row, column=2, sticky="e", padx=(10, 0), pady=6)
        return button

    def _choose_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select drawing image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.input_var.set(selected)
            self._load_preview(Path(selected))

    def _choose_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save G-code as",
            defaultextension=".nc",
            initialfile=Path(self.output_var.get()).name or "output.nc",
            filetypes=[("NC G-code", "*.nc"), ("All files", "*.*")],
        )
        if selected:
            self.output_var.set(selected)

    def _load_preview(self, image_path: Path) -> None:
        self.preview_canvas.delete("all")
        image = cv2.imread(str(image_path)) if image_path.is_file() else None
        if image is None:
            self.preview_photo = None
            self.preview_info_var.set("Chọn một ảnh PNG/JPG/BMP để xem preview")
            self.preview_canvas.create_text(
                220, 150, text="No preview", fill=MUTED_COLOR, font=("Segoe UI", 12)
            )
            return

        height, width = image.shape[:2]
        scale = min(420 / width, 280 / height, 1.0)
        if scale < 1.0:
            image = cv2.resize(
                image,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        success, encoded = cv2.imencode(".png", image)
        if not success:
            self.preview_info_var.set("Không thể tạo preview")
            return
        encoded_data = base64.b64encode(encoded.tobytes()).decode("ascii")
        self.preview_photo = tk.PhotoImage(data=encoded_data)
        canvas_width = int(self.preview_canvas.cget("width"))
        canvas_height = int(self.preview_canvas.cget("height"))
        self.preview_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.preview_photo,
            anchor="center",
        )
        self.preview_info_var.set(f"{width} x {height} px  |  {image_path.name}")

    def _read_config(self) -> MachiningConfig:
        def read_float(variable: tk.StringVar, label: str) -> float:
            try:
                return float(variable.get().strip())
            except ValueError as error:
                raise ValueError(f"{label} phải là một số hợp lệ.") from error

        def read_int(variable: tk.StringVar, label: str) -> int:
            try:
                return int(variable.get().strip())
            except ValueError as error:
                raise ValueError(f"{label} phải là số nguyên hợp lệ.") from error

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
            self._show_error(f"Không tìm thấy ảnh đầu vào: {input_path}")
            return
        if not output_path.name:
            self._show_error("Hãy chọn đường dẫn output G-code.")
            return
        try:
            config = self._read_config()
        except ValueError as error:
            self._show_error(str(error))
            return

        self._set_running(True)
        self._append_log(f"Đang xử lý: {input_path}")
        worker = threading.Thread(
            target=self._conversion_worker,
            args=(input_path, output_path, config),
            daemon=True,
        )
        worker.start()

    def _conversion_worker(
        self, input_path: Path, output_path: Path, config: MachiningConfig
    ) -> None:
        try:
            scale_factor, contour_count = convert_image_to_gcode(
                input_path, output_path, config
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
                f"Đã tạo {output_path} | SF={scale_factor:.3f} pixel/mm | "
                f"contours={contour_count}"
            )
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
            self.progress.start(10)
        else:
            self.progress.stop()

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
        self._load_preview(Path(self.input_var.get()))
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
            self._show_error(f"Không thể mở thư mục output: {error}")

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
