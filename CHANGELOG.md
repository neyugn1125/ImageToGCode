# Nhật ký thay đổi

Các thay đổi đáng chú ý của dự án được ghi lại trong tệp này. Định dạng dựa
trên [Keep a Changelog](https://keepachangelog.com/vi-VN/1.1.0/).

## [Unreleased]

### Thêm mới

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

### Thay đổi

- Ưu tiên scale tường minh trước metadata diagrams.net và ô vuông hiệu chuẩn;
  khi có cả hai kích thước tham chiếu, kiểm tra sai lệch tỉ lệ tối đa 5%.
- Lọc residue, nét dài mảnh và thành phần chú thích bên ngoài contour bao khi
  bật `--strip-dimensions`, đồng thời giữ hierarchy lỗ/vật liệu của chi tiết.
- Làm mượt contour mạnh hơn để loại bậc pixel trên cạnh chéo, đồng thời giữ
  nguyên contour của ô vuông hiệu chuẩn 10 x 10 mm. Giới hạn sai số làm mượt
  contour cong dài ở 1 pixel để ellipse và đầu bo không bị phân thành các
  đoạn thẳng thô theo chu vi.
- Contour tròn được xuất theo chiều winding bằng `G02` hoặc `G03`, thay vì
  luôn dùng `G02`.
- Cải thiện xử lý contour của bản vẽ dạng nét: loại vòng biên dư, dựng lại
  hierarchy sau khi lọc và giữ đúng thứ tự gia công contour con trước contour
  cha.
- GUI tải dữ liệu mô phỏng ở luồng nền và hiển thị các đỉnh đường chạy dao
  với đầu mút phẳng, giúp không làm treo giao diện và giữ góc sắc.
- Quá trình ghi G-code trên GUI dùng tệp tạm rồi thay thế nguyên tử; thư mục
  output được tạo tự động và tệp tạm được dọn khi có lỗi.
- Tham số mặc định của CLI lấy trực tiếp từ `MachiningConfig`; dependency
  NumPy và OpenCV được giới hạn major version tương thích.
- Script đóng gói Windows dừng ngay khi một bước cài đặt hoặc build thất bại.
- Post-processor DXF xuất mỗi `CIRCLE` bằng hai cung 180 độ `G02` với I/J tương
  đối, và đóng nghiêm ngặt mọi `LWPOLYLINE` bằng một lệnh `G01` về điểm đầu.

### Kiểm thử

- Bổ sung kiểm thử cho làm mượt contour tam giác raster, cung tròn thuận/nghịch
  chiều, xử lý hierarchy sau khi loại vòng biên và kiểm tra scale factor bằng
  không, gần không hoặc không hữu hạn.
- Bổ sung kiểm thử phân biệt ô chuẩn đen đặc và hình vuông chỉ vẽ biên.
- Bổ sung kiểm thử xuất/đọc DXF, direct DXF input, thư mục output duy nhất, hai
  cung tròn và đóng kín polyline.

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
