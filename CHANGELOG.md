# Nhật ký thay đổi

Các thay đổi đáng chú ý của dự án được ghi lại trong tệp này. Định dạng dựa
trên [Keep a Changelog](https://keepachangelog.com/vi-VN/1.1.0/).

## [Unreleased]

### Thêm mới

- Bổ sung cơ chế **Bù bán kính dao (Cutter Radius Compensation)** đa năng:
  - **CAM tự bù (Computer Compensation - `CAM`)**: Tự động tính toán quỹ đạo tâm dao bù trực tiếp kích thước theo đường kính dao (`--tool-diameter`). Biên dạng ngoài được mở rộng $+R_{dao}$, hốc kín bên trong co ngót $-R_{dao}$. Lỗ tròn hạ dao an toàn tại tâm và phay tròn $R_{cut} = R - R_{dao}$.
  - **Bù dao Controller (`G41` / `G42`)**: Xuất mã G41 (bù trái) hoặc G42 (bù phải) kèm D-code (`--cutter-offset-d`), có đoạn vào dao/ra dao (lead-in/lead-out) an toàn trong không khí tự do.
  - **Tắt bù (`G40`)**: Chạy dao trực tiếp theo đường danh nghĩa của bản vẽ.
- Thuật toán **Xâu chuỗi thực thể DXF tự động (`DXF Entity Chaining`)**:
  - Tự động dò tìm và ghép nối các thực thể `LINE`, `ARC`, `LWPOLYLINE` rời rạc có đầu mút tiếp giáp thành các chuỗi biên dạng kín hoàn chỉnh (`DxfChain`).
  - Loại bỏ hoàn toàn hiện tượng rãnh then (slot) hoặc góc bo bị cắt vụn với nhiều lần lao/rút dao ngắt quãng.
- Thuật toán **Bù dao giải tích bảo toàn cung tròn (`Analytic Arc Offset`)**:
  - Giải tích hình học giao điểm tiếp tuyến giữa đường thẳng bù và cung tròn bù.
  - Bảo toàn 100% các lệnh nội suy tròn **`G02` / `G03`** chuẩn Fanuc, tuyệt đối không băm nhỏ cung tròn thành các đoạn thẳng `G01`.
- Hỗ trợ ứng dụng Web hiện đại chạy bằng FastAPI (`api/index.py`) với giao diện trực quan, mô phỏng đường chạy dao trên Canvas 2D thời gian thực, hỗ trợ kéo thả file và đa ngôn ngữ (Tiếng Việt / English).
- Bổ sung các tham số `--tool-diameter`, `--cutter-comp`, `--cutter-offset-d` trên CLI, GUI Tkinter Desktop (`app.py`) và Web App.

### Thay đổi

- Tái cấu trúc codebase sang kiến trúc mô-đun chuẩn mực trong thư mục `core/`:
  - `core/cam/`: Hình học CAM, bù polygon, pháp tuyến và winding.
  - `core/dxf/`: Đọc, kiểm tra tính hợp lệ và trích xuất thực thể DXF.
  - `core/post/`: Fanuc post-processor, chaining thực thể, bộ phân tích cú pháp mô phỏng G-code.
  - `core/vision/`: Xử lý ảnh, trích xuất contour, làm mượt và hiệu chuẩn scale.
- Cải tiến thuật toán phân loại cha/con (`_classify_contours` và `_classify_dxf_entities`):
  - Kết hợp kiểm tra diện tích đa giác với kiểm tra toàn bộ đỉnh nằm trong đường bao, khắc phục lỗi nhận nhầm do trọng tâm lệch của các hình bất đối xứng.
- Tự động sắp xếp thứ tự gia công thông minh: phay toàn bộ các lỗ và hốc bên trong trước, phay biên dạng ngoài bao quanh sau cùng.
- Hỗ trợ scale ảnh không có metadata bằng `--reference-width-mm`,
  `--reference-height-mm` hoặc `--pixels-per-mm`; nếu không có nguồn scale,
  pipeline dừng trước khi tạo G-code.
- GUI có panel nhập scale tham chiếu và tùy chọn loại chú thích kích thước trước
  khi tracing.
- Bổ sung các bản vẽ mẫu trong `input/samples/` để kiểm tra nhiều dạng chi
  tiết và contour lồng nhau.
- GUI có mô phỏng đường chạy dao với phát, tạm dừng, từng bước, tua đến vị
  trí bất kỳ, zoom/pan và màu riêng cho rapid, cắt thẳng và cung tròn.
- Nhận diện ô vuông hiệu chuẩn bằng `black ratio` để phân biệt ô chuẩn đen đặc
  với hình vuông biên dạng có phần ruột trắng.
- Bổ sung pipeline hai giai đoạn `Image -> DXF -> G-Code` bằng `ezdxf`, đồng
  thời nhận trực tiếp file `.dxf` từ CLI.
- Tạo thư mục artifact riêng cho mỗi lần chạy, chứa cả file DXF trung gian và
  G-code cuối cùng.
- Hỗ trợ ô chuẩn rỗng theo quy tắc góc dưới-trái và bù độ dày nét bằng trung
  bình độ rộng contour ngoài/trong.

### Sửa lỗi

- Khắc phục lỗi rãnh then (slot) trong file DXF bị tự động đóng một đường thẳng ngang đầu và cung tròn bị cắt riêng đè ra ngoài.
- Khắc phục lỗi biến cung tròn thành nhiều đoạn thẳng nhỏ `G01` khi bật chế độ bù dao CAM.
- Khắc phục lỗi `AttributeError: 'ImageToGCodeApp' object has no attribute 'tool_diameter_var'` gây crash giao diện Tkinter `app.py`.
- Khắc phục lỗi giá trị gửi lên từ dropdown bù dao trên Web UI khiến chương trình chạy ở chế độ tắt bù danh nghĩa.
- Khắc phục lỗi lẹm dao và vết khuyết cạnh huyền khi vào dao bằng cách chuyển sang chế độ bù CAM trực tiếp hoặc lead-in trong không khí tự do.

## [Release] - 2026-08-18

### Thêm mới

- Phát hành pipeline Python chuyển ảnh raster 2D thành G-code Fanuc cho phay
  biên dạng.
- Tự động phát hiện ô vuông chuẩn 10 x 10 mm, tính scale factor và đặt gốc
  G54 tại góc dưới trái của bounding box chi tiết.
- Nhận dạng contour theo hierarchy, gia công contour con trước contour cha,
  nhận dạng hình tròn và sinh cung `G02` với I/J tương đối.
- Sinh đầy đủ header/footer Fanuc, lệnh thay dao, bù chiều dài dao, spindle,
  coolant, plunge, cắt và retract.
- Cung cấp giao diện Tkinter trên Windows để chọn ảnh, nhập thông số gia công,
  xem preview và tạo file G-code.
- Cung cấp `build_windows.bat` để đóng gói ứng dụng thành
  `dist/ImageToGCode.exe` bằng PyInstaller.

### Tài liệu và kiểm thử

- Thêm README tiếng Việt với hướng dẫn cài đặt, CLI, GUI, build Windows và
  cảnh báo an toàn trước khi chạy chương trình trên máy thật.
- Thêm bộ kiểm thử tự động cho hiệu chuẩn, bounding box, hierarchy, contour
  tròn, tham số không hợp lệ, header/footer và smoke test sinh file `.nc`.
