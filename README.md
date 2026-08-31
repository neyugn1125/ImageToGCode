# Image/DXF to G-Code

Công cụ chuyển ảnh raster 2D hoặc bản vẽ DXF thành G-code Fanuc cho phay biên
dạng CNC. CLI dùng pipeline hai giai đoạn `Image -> DXF -> G-Code`; ứng dụng
vẫn hỗ trợ giao diện GUI trên Windows cho luồng ảnh.

> **Cảnh báo:** Hãy mô phỏng hoặc dry-run chương trình trên controller trước khi chạy máy thật. Phần mềm chưa áp dụng bù bán kính dao, bù kerf, chia nhiều lớp chiều sâu hoặc kiểm tra va chạm.

## Tính năng

- Đọc ảnh PNG, JPG, JPEG, BMP, TIFF hoặc nhận trực tiếp file DXF.
- Tự động phát hiện ô vuông chuẩn rỗng 10 x 10 mm theo quy tắc góc dưới trái
  (`min(x - y)`). Ảnh cũ dùng ô chuẩn đen đặc vẫn được hỗ trợ.
- Bù độ dày nét ô chuẩn theo
  `true_width_px = (w_outer + w_inner) / 2.0`, sau đó tính
  `SF = true_width_px / 10.0`.
- Đặt gốc G54 tại góc dưới trái của bounding box chi tiết gia công.
- Loại ô chuẩn khỏi bounding box và đường chạy dao.
- Làm mượt contour bằng `cv2.approxPolyDP` với epsilon mặc định bằng `0.005 * perimeter` để loại bỏ bậc pixel trên cạnh chéo; với contour cong dài, epsilon được giới hạn ở 1 pixel để tránh tạo các đoạn thẳng thô. Contour ô chuẩn được giữ nguyên để không ảnh hưởng hiệu chuẩn.
- Sắp xếp contour theo hierarchy, gia công contour con trước contour cha.
- Nhận dạng hình tròn bằng circularity `> 0.88`.
- Xuất DXF theo đơn vị millimeter với entity `CIRCLE` hoặc `LWPOLYLINE` đóng.
- Sinh đúng hai cung 180 độ `G02` với I/J tương đối cho mỗi `CIRCLE`, tránh
  lỗi nội suy full-circle trên controller.
- Sinh `G01` theo từng đỉnh `LWPOLYLINE`, luôn thêm lệnh quay về điểm đầu và
  retract sau mỗi đường chạy dao.
- Tạo thư mục riêng cho mỗi lần chạy theo mẫu
  `output/<filename>_<YYYYMMDD_HHMMSS>/`, chứa cả `.dxf` và `.nc`.
- Kiểm tra tham số gia công trước khi xử lý.
- Hỗ trợ scale tường minh cho ảnh không có metadata bằng kích thước tham chiếu
  hoặc `pixels per mm`; không tự suy đoán DPI vì DPI không cho biết kích thước
  chi tiết nếu ảnh đã bị resize.
- Có thể loại nét kích thước, đường dóng, mũi tên và chữ bằng
  `--strip-dimensions` trước khi lấy contour.

## Pipeline xử lý

```text
Ảnh -> OpenCV/approxPolyDP -> hiệu chuẩn + đổi trục Y -> DXF millimeter
DXF đầu vào -----------------------------------------> sao chép DXF
                                                        |
                                                        v
                             ezdxf -> CIRCLE/LWPOLYLINE -> G-code Fanuc
```

Với contour tròn, chương trình dùng `cv2.minEnclosingCircle()` để lấy tâm và bán kính. Tọa độ được đổi sang mm theo:

```text
X_mm = (X_px - x_min) / SF
Y_mm = (y_max - Y_px) / SF
R_mm = R_px / SF
```

Hai cung 180 độ dùng I/J là vector tương đối từ điểm bắt đầu đến tâm cung.
Contour chuẩn không xuất hiện trong DXF hoặc G-code.

## Yêu cầu hệ thống

- Python 3.10 trở lên.
- OpenCV-Python.
- NumPy.
- ezdxf.
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

1. Một ô vuông rỗng, song song với trục ảnh, đại diện cho kích thước 10 x 10 mm.
2. Một hoặc nhiều hình chi tiết cần gia công.
3. Nền sáng, tương phản rõ với chi tiết.

Nếu có nhiều ô vuông rỗng phù hợp, chương trình chọn ô nằm dưới-trái nhất theo
điểm số `x - y`. Độ rộng centerline của nét được dùng để loại sai số do độ dày
nét. Với ảnh cũ dùng ô chuẩn đen đặc, `black ratio` vẫn phân biệt ô chuẩn với
hình vuông chỉ vẽ biên.

### Ảnh không có metadata hoặc ô chuẩn

Một ảnh raster không chứa thông tin kích thước vật lý thì không thể tự suy ra
scale tuyệt đối từ số pixel. Chọn một trong các cách sau:

```bash
# Biết kích thước bao gia công theo cả hai chiều (mm)
python run.py --input drawings/part.png --output-dir output \
  --reference-width-mm 100 --reference-height-mm 100

# Hoặc biết trực tiếp độ phân giải raster
python run.py --input drawings/part.png --output-dir output \
  --pixels-per-mm 16.54
```

Có thể chỉ cung cấp một chiều `--reference-width-mm` hoặc
`--reference-height-mm`; khi cung cấp cả hai, hai tỉ lệ phải khớp trong phạm
vi 5%. `--pixels-per-mm` không dùng đồng thời với kích thước tham chiếu.
Thứ tự ưu tiên là `pixels per mm`, kích thước tham chiếu, metadata vector
diagrams.net, rồi ô vuông 10 x 10 mm. Nếu không có bất kỳ nguồn scale nào,
chương trình dừng với lỗi rõ ràng và không tạo file G-code.

Với bản vẽ có đường kích thước/chữ, bật tùy chọn sau và vẫn cung cấp kích
thước thật của chi tiết:

```bash
python run.py --input drawings/part.png --output-dir output \
  --reference-width-mm 100 --reference-height-mm 100 --strip-dimensions
```

## Chạy bằng CLI

Đặt ảnh tại `input/input.png`, sau đó chạy:

```bash
python run.py
```

Mỗi lần chạy tạo một thư mục mới, ví dụ:

```text
output/input_20260823_143015/
├── input.dxf
└── input.nc
```

Các tham số CLI:

| Tham số | Mặc định | Mô tả |
| --- | ---: | --- |
| `--input` | `input/input.png` | Ảnh hoặc DXF đầu vào |
| `--output-dir` | `output` | Thư mục gốc chứa các thư mục lần chạy |
| `--cut-depth` | `-5.0` | Chiều sâu cắt Z, phải âm |
| `--plunge-feed` | `100.0` | Feed khi plunge, mm/min |
| `--cut-feed` | `300.0` | Feed khi cắt, mm/min |
| `--spindle-speed` | `1500` | Tốc độ trục chính, RPM |
| `--safe-z` | `50.0` | Cao độ an toàn |
| `--approach-z` | `2.0` | Cao độ tiếp cận |
| `--tool-number` | `1` | Số dao |
| `--tool-offset` | `1` | Offset chiều dài dao H |
| `--program-number` | `1000` | Số chương trình Fanuc |
| `--reference-width-mm` | *(trống)* | Chiều rộng bao gia công đã biết, mm |
| `--reference-height-mm` | *(trống)* | Chiều cao bao gia công đã biết, mm |
| `--pixels-per-mm` | *(trống)* | Scale raster tường minh, ưu tiên cao nhất |
| `--strip-dimensions` | tắt | Loại bỏ đường kích thước, đường gióng, mũi tên và chữ số đo trước khi tracing |

`--output` là alias của `--output-dir` để tương thích câu lệnh cũ. Ví dụ chạy
từ ảnh và ghi artifact sang thư mục khác:

```bash
python run.py --input drawings/part.png --output-dir nc --cut-depth -2.5 --cut-feed 250 --spindle-speed 2200
```

Đầu vào DXF đi thẳng tới post-processor và bản gốc được sao chép vào thư mục
lần chạy:

```bash
python run.py --input drawings/part.dxf --output-dir output
```

## Chạy giao diện GUI

```bash
python app.py
```

Trong cửa sổ ứng dụng:

1. Nhấn **Browse** ở mục Input image và chọn ảnh trực tiếp.
2. Chọn tên file G-code ở mục Output G-code.
3. Nhập thông số dao và thông số gia công.
4. Nếu ảnh không có ô chuẩn hoặc metadata, nhập Reference width/height (mm)
   hoặc Pixels per mm trong panel **Scale reference**. Hai cách này không dùng
   đồng thời.
5. Với bản vẽ có chú thích kích thước, bật **Remove dimension annotations**.
6. Nhấn **Generate G-Code**.

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

Bộ kiểm thử bao gồm hiệu chuẩn hollow/centerline, scale tường minh cho ảnh
không metadata, bounding box G54, hierarchy child-first, xuất DXF, direct DXF
input, hai cung `G02`, đóng polyline, header/footer và quản lý thư mục output.

## Cấu trúc dự án

```text
.
├── app.py                  # Giao diện Tkinter
├── run.py                  # Image -> DXF -> G-code, post-processor và CLI
├── requirements.txt        # Dependency Python
├── build_windows.bat       # Đóng gói ImageToGCode.exe
├── input/input.png         # Ảnh mẫu mặc định
└── tests/
    ├── test_image_to_gcode.py
    └── test_dxf_pipeline.py
```
