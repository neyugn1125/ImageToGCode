# Image/DXF to G-Code

Công cụ chuyển ảnh raster 2D hoặc bản vẽ DXF thành G-code Fanuc cho phay biên
dạng CNC. Hỗ trợ đầy đủ **bù bán kính dao (Cutter Radius Compensation)** qua
thuật toán CAM hoặc mã G41/G42. Cung cấp cả giao diện Web (FastAPI), GUI Desktop
(Tkinter trên Windows) và CLI.

> **Khuyến nghị an toàn:** Hãy mô phỏng hoặc dry-run chương trình trên controller / phần mềm mô phỏng trước khi chạy phôi thật.

## Tính năng

- **Đa dạng nguồn đầu vào**: Đọc ảnh raster (PNG, JPG, JPEG, BMP, TIFF) hoặc nhận trực tiếp file vector DXF (`.dxf`).
- **Bù bán kính dao tự động (Cutter Radius Compensation)**:
  - **CAM tự bù (`CAM` - khuyên dùng)**: Tự động tính toán đường tâm dao trực tiếp theo đường kính dao (`--tool-diameter`). Biên dạng ngoài được mở rộng $+R_{dao}$, hốc kín bên trong co lại $-R_{dao}$, lỗ tròn hạ dao tại tâm và phay tròn $R_{cut} = R - R_{dao}$.
  - **Bù máy Controller (`G41` / `G42`)**: Xuất lệnh bù trái (`G41`) hoặc bù phải (`G42`) kèm thanh ghi `D`, có đoạn vào dao / ra dao (lead-in / lead-out) an toàn trong không khí tự do.
  - **Tắt bù (`G40`)**: Chạy dao trực tiếp theo đường danh nghĩa của bản vẽ.
- **Xâu chuỗi thực thể DXF tự động (`DXF Entity Chaining`)**:
  - Dò tìm và kết nối các thực thể `LINE`, `ARC`, `LWPOLYLINE` rời rạc có đầu mút tiếp giáp nhau thành các chuỗi biên dạng kín liên tục (`DxfChain`).
  - Giữ nguyên vẹn các rãnh then (slots) và góc bo cung tròn, loại bỏ hiện tượng bị kẻ nét thẳng đóng ngang đầu rãnh hoặc nhấc dao nhiều lần ngắt quãng.
- **Bù dao giải tích bảo toàn cung tròn (`Analytic Arc Offset`)**:
  - Tính toán tiếp xúc hình học chính xác giữa đường thẳng bù và cung tròn bù.
  - Bảo toàn 100% các lệnh nội suy tròn chuẩn Fanuc **`G02` / `G03`**, không băm nhỏ cung tròn thành các đoạn thẳng `G01`.
- **Giao diện Web tương tác & Mô phỏng 2D**:
  - Ứng dụng Web FastAPI (`api/index.py`), hỗ trợ xem trước bản vẽ, mô phỏng dao thời gian thực trên Canvas 2D, tùy chỉnh thông số và hỗ trợ đa ngôn ngữ (Tiếng Việt / English).
- **Tự động phát hiện hiệu chuẩn**: Ô vuông chuẩn rỗng 10 x 10 mm theo quy tắc góc dưới trái (`min(x - y)`), bù độ dày nét bằng trung bình độ rộng contour ngoài/trong. Hỗ trợ ô chuẩn đen đặc cũ.
- **Định vị gốc phôi G54**: Tự động đặt gốc G54 tại góc dưới trái của bounding box chi tiết gia công.
- **Sắp xếp thứ tự gia công tối ưu**: Gia công toàn bộ các lỗ và hốc bên trong trước, phay biên dạng ngoài bao quanh sau cùng.
- **Làm mượt contour thông minh**: Dùng `cv2.approxPolyDP` với epsilon thích ứng để khử bậc pixel trên cạnh chéo mà vẫn giữ sắc nét góc và đầu bo.
- **Sinh G-code chuẩn Fanuc**: Đầy đủ header/footer, đổi dao, bù chiều dài dao `G43`, trục chính, tưới nguội, plunge feed, cut feed và an toàn Z.
- **Quản lý Artifacts**: Tạo thư mục riêng cho mỗi lần chạy theo mẫu `output/<filename>_<YYYYMMDD_HHMMSS>/`, chứa cả `.dxf` và `.nc`.

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
| `--tool-diameter` | `3.0` | Đường kính dao phay (mm), dùng cho chế độ bù dao |
| `--cutter-comp` | `CAM` | Chế độ bù bán kính dao: `CAM` (CAM tự bù), `G41` (bù trái), `G42` (bù phải), `G40` (tắt bù) |
| `--cutter-offset-d` | `1` | Số hiệu thanh ghi bù dao D (khi chọn G41/G42) |
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
python run.py --input drawings/part.png --output-dir nc --tool-diameter 3.0 --cutter-comp CAM --cut-depth -2.5 --cut-feed 250 --spindle-speed 2200
```

Đầu vào DXF đi thẳng tới post-processor và bản gốc được sao chép vào thư mục
lần chạy:

```bash
python run.py --input drawings/part.dxf --output-dir output --tool-diameter 3.0 --cutter-comp CAM
```

## Chạy giao diện Web (FastAPI)

Ứng dụng cung cấp giao diện Web hiện đại với khả năng mô phỏng dao 2D tương tác:

```bash
# Khởi động server Web
uvicorn api.index:app --reload --port 8000
```

Mở trình duyệt tại địa chỉ `http://localhost:8000`:
- Kéo thả file ảnh hoặc file DXF trực tiếp vào khung tải lên.
- Tùy chỉnh thông số dao (`Tool diameter Ø`), tốc độ, bước tiến và chế độ bù dao (`CAM tự bù`, `G41`, `G42`, `G40`).
- Quan sát đường chạy dao mô phỏng trực quan trên Canvas 2D thời gian thực.
- Tải về file G-code (`.nc`) và DXF trung gian chỉ với 1 cú click.

## Chạy giao diện Desktop GUI (Tkinter)

```bash
python app.py
```

Trong cửa sổ ứng dụng:

1. Nhấn **Browse** ở mục Input image và chọn ảnh trực tiếp.
2. Chọn tên file G-code ở mục Output G-code.
3. Nhập thông số dao (`Tool diameter Ø`), chọn chế độ bù dao (`Cutter compensation`: `CAM`, `G41`, `G42`, `G40`) và thông số gia công.
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
input, chaining thực thể DXF, bù dao giải tích, hai cung `G02`, đóng polyline,
header/footer và quản lý thư mục output.

## Cấu trúc dự án

```text
.
├── api/                    # Backend Web API (FastAPI)
│   └── index.py            # Entrypoint API phục vụ Web App & Vercel
├── core/                   # Các gói xử lý lõi (Core Processing Modules)
│   ├── cam/                # Hình học CAM, offset đa giác, winding
│   ├── dxf/                # Đọc DXF, trích xuất entity, validation
│   ├── post/               # Fanuc post-processor, chaining, parser mô phỏng
│   └── vision/             # Xử lý ảnh, contour, hiệu chuẩn scale
├── public/                 # Tài nguyên Web tĩnh (CSS, JS đa ngôn ngữ, icons)
│   ├── css/style.css
│   └── js/app.js, i18n.js
├── index.html              # Giao diện Web SPA
├── app.py                  # Giao diện Tkinter Desktop
├── run.py                  # CLI chuyển đổi Image -> DXF -> G-code
├── requirements.txt        # Dependency Python
├── build_windows.bat       # Đóng gói ImageToGCode.exe
├── input/                  # File ảnh và DXF mẫu đầu vào
└── tests/                  # Bộ unit tests tự động
    ├── test_api.py
    ├── test_dxf_pipeline.py
    ├── test_image_to_gcode.py
    └── ...
```
