# Image to G-Code

Công cụ chuyển ảnh raster 2D thành G-code Fanuc cho phay biên dạng CNC. Ứng dụng hỗ trợ cả dòng lệnh Python và giao diện GUI trên Windows.

> **Cảnh báo:** Hãy mô phỏng hoặc dry-run chương trình trên controller trước khi chạy máy thật. Phần mềm chưa áp dụng bù bán kính dao, bù kerf, chia nhiều lớp chiều sâu hoặc kiểm tra va chạm.

## Tính năng

- Đọc ảnh PNG, JPG, JPEG, BMP, TIFF.
- Tự động phát hiện ô vuông chuẩn màu đen 10 x 10 mm.
- Tính scale factor theo công thức `SF = width_px / 10.0`.
- Đặt gốc G54 tại góc dưới trái của bounding box chi tiết gia công.
- Loại ô chuẩn khỏi bounding box và đường chạy dao.
- Làm mượt contour bằng `cv2.approxPolyDP` với epsilon mặc định bằng `0.001 * perimeter`.
- Sắp xếp contour theo hierarchy, gia công contour con trước contour cha.
- Nhận dạng hình tròn bằng circularity `> 0.88`.
- Sinh hai cung `G02` với I/J tương đối cho contour tròn, không nội suy hình tròn bằng hàng loạt G01.
- Sinh G01 cho các contour còn lại, đóng kín từng contour và retract sau mỗi đường chạy dao.
- Kiểm tra tham số gia công trước khi xử lý.

## Pipeline xử lý

```text
Ảnh đầu vào
    -> grayscale
    -> Gaussian Blur 5x5
    -> Otsu THRESH_BINARY_INV
    -> RETR_TREE / CHAIN_APPROX_SIMPLE
    -> làm mượt contour
    -> tìm ô chuẩn 10 x 10 mm
    -> tính SF và gốc G54
    -> nhận dạng hình tròn hoặc contour thường
    -> sinh G-code Fanuc
```

Với contour tròn, chương trình dùng `cv2.minEnclosingCircle()` để lấy tâm và bán kính. Tọa độ được đổi sang mm theo:

```text
X_mm = (X_px - x_min) / SF
Y_mm = (y_max - Y_px) / SF
R_mm = R_px / SF
```

Hai cung 180 độ dùng I/J là vector tương đối từ điểm bắt đầu đến tâm cung. Contour chuẩn không xuất hiện trong G-code.

## Yêu cầu hệ thống

- Python 3.10 trở lên.
- OpenCV-Python.
- NumPy.
- Tkinter nếu chạy giao diện GUI. Trên Windows, Tkinter thường đi kèm Python.

## Cài đặt

```bash
git clone <URL_REPOSITORY>
cd cnc
python -m venv .venv
```

Kích hoạt môi trường ảo:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate
```

Cài dependency:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Chuẩn bị ảnh

Ảnh cần có:

1. Một ô vuông đen đặc, song song với trục ảnh, đại diện cho kích thước 10 x 10 mm.
2. Một hoặc nhiều hình chi tiết cần gia công.
3. Nền sáng, tương phản rõ với chi tiết.

Chỉ nên có một ô vuông phù hợp với điều kiện hiệu chuẩn. Nếu có nhiều ô vuông, chương trình dừng và báo lỗi để tránh chọn sai scale factor. Không đặt các hình vuông gia công có cùng đặc điểm với ô chuẩn nếu chúng có thể bị nhận dạng nhầm.

## Chạy bằng CLI

Đặt ảnh tại `input/input.png`, sau đó chạy:

```bash
python run.py
```

File mặc định được tạo tại `output/output.nc`.

Các tham số CLI:

| Tham số | Mặc định | Mô tả |
| --- | ---: | --- |
| `--input` | `input/input.png` | Ảnh đầu vào |
| `--output` | `output/output.nc` | File G-code đầu ra |
| `--cut-depth` | `-5.0` | Chiều sâu cắt Z, phải âm |
| `--plunge-feed` | `100.0` | Feed khi plunge, mm/min |
| `--cut-feed` | `300.0` | Feed khi cắt, mm/min |
| `--spindle-speed` | `1500` | Tốc độ trục chính, RPM |
| `--safe-z` | `50.0` | Cao độ an toàn |
| `--approach-z` | `2.0` | Cao độ tiếp cận |
| `--tool-number` | `1` | Số dao |
| `--tool-offset` | `1` | Offset chiều dài dao H |
| `--program-number` | `1000` | Số chương trình Fanuc |

Ví dụ ghi output sang vị trí khác:

```bash
python run.py --input drawings/part.png --output nc/part.nc --cut-depth -2.5 --cut-feed 250 --spindle-speed 2200
```

## Chạy giao diện GUI

```bash
python app.py
```

Trong cửa sổ ứng dụng:

1. Nhấn **Browse** ở mục Input image và chọn ảnh trực tiếp.
2. Chọn tên file G-code ở mục Output G-code.
3. Nhập thông số dao và thông số gia công.
4. Nhấn **Generate G-Code**.

GUI có preview ảnh, hiển thị trạng thái xử lý và nút mở thư mục output. Thư mục cha của output được tự động tạo khi sinh G-code.

## Đóng gói thành EXE Windows

Trên Windows, mở Command Prompt trong thư mục dự án và chạy:

```bat
build_windows.bat
```

Script sẽ cài PyInstaller và tạo:

```text
dist/ImageToGCode.exe
```

Đây là file one-file có thể chép sang máy Windows khác. Máy đích không cần cài Python, nhưng cần controller hoặc simulator CNC phù hợp để kiểm tra chương trình. Khi dùng đường dẫn mặc định, ứng dụng dùng thư mục `input` và `output` nằm cạnh file EXE; GUI cũng cho phép chọn đường dẫn khác trực tiếp.

## Chạy kiểm thử

```bash
python -m unittest discover -s tests -v
```

Bộ kiểm thử bao gồm hiệu chuẩn, bounding box G54, hierarchy child-first, loại ô chuẩn, nhận dạng hình tròn, tham số không hợp lệ, header/footer và smoke test sinh file `.nc`.

## Cấu trúc dự án

```text
.
├── app.py                  # Giao diện Tkinter
├── run.py                  # Pipeline xử lý và CLI
├── requirements.txt        # Dependency Python
├── build_windows.bat       # Đóng gói ImageToGCode.exe
├── input/input.png         # Ảnh mẫu mặc định
├── output/output.nc        # G-code mẫu được sinh
└── tests/
    └── test_image_to_gcode.py
```
