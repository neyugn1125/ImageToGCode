/**
 * Internationalization (i18n) Module
 * Supports Tiếng Việt (VI) and English (EN)
 */

export const translations = {
  vi: {
    // Header
    appTitle: "Chuyển ảnh sang G-Code",
    appSubtitle: "Tự động nhận diện biên dạng, phân cấp cắt gọt và mô phỏng CAM chuẩn Fanuc CNC",
    apiDocs: "Tài liệu API",

    // Section 1: Upload
    sec1Title: "1. Bản vẽ đầu vào hoặc File DXF",
    dropPrompt: "Kéo thả bản vẽ hoặc file DXF vào đây",
    dropOrBrowse: "hoặc chọn file từ máy tính",
    dropFormats: "Hỗ trợ định dạng PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "File đã chọn:",
    noFileSelected: "Chưa chọn file",

    // Section 2: Calibration
    sec2Title: "2. Căn chỉnh tỷ lệ & Kích thước",
    stripDimensions: "Loại bỏ đường gióng kích thước & chữ ký hiệu",
    refWidth: "Chiều rộng thực tế (mm)",
    refHeight: "Chiều cao thực tế (mm)",
    pixelsPerMm: "Tỷ lệ pixel / mm (px/mm)",

    // Section 3: Machining & Tool
    sec3Title: "3. Thông số gia công & Dao cụ",
    cutDepth: "Chiều sâu cắt Z (mm)",
    plungeFeed: "Bước tiến xuống dao (mm/phút)",
    cutFeed: "Bước tiến cắt (mm/phút)",
    spindleRpm: "Tốc độ trục chính (vòng/phút)",
    safeZ: "Cao độ an toàn Safe Z (mm)",
    approachZ: "Cao độ tiếp cận Approach Z (mm)",
    toolDia: "Đường kính dao Ø (mm)",
    toolNum: "Số hiệu dao (T)",
    toolOffset: "Bù chiều dài dao (H)",
    programNum: "Số chương trình (O)",

    // Action buttons
    btnGenerate: "Tạo mã G-Code",
    btnReset: "Mặc định",
    btnDownloadNc: "Tải file .NC",
    btnDownloadDxf: "Tải file .DXF",
    btnViewGcode: "Xem mã G-Code",

    // Panel 1: Preview
    previewTitle: "1. Xem trước Bản vẽ & DXF (Nhận diện & Tọa độ)",
    tagDetection: "Nhãn (G54/Bao)",
    tagGrid: "Lưới",
    tagAxes: "Trục (+X/+Y)",
    previewFit: "Vừa khung",
    previewDefaultText: "Chọn ảnh bản vẽ hoặc file DXF để xem trước (Cuộn: Zoom | Kéo: Pan | Nhấp đúp: Vừa khung)",
    previewEmpty: "Chưa có ảnh hoặc file DXF để xem trước",
    calibTag: "Chuẩn 10x10mm",
    g54Origin: "Gốc G54 (0,0)",

    // Panel 2: Simulation
    simTitle: "2. Mô phỏng đường chạy dao (Màn hình CAD/CAM)",
    simGrid: "Lưới & Trục",
    simRapids: "Chạy dao nhanh (G00)",
    simArrows: "Mũi tên hướng cắt",
    simCutter: "Đầu dao (Ø)",
    simPlay: "Phát",
    simPause: "Tạm dừng",
    simRestart: "Bắt đầu lại",
    simRecenter: "Căn giữa",
    simSpeed: "Tốc độ:",
    simDefaultText: "Chưa có đường chạy dao. Bấm 'Tạo mã G-Code' để bắt đầu mô phỏng.",
    simLoading: "Đang tải mô phỏng đường dao...",

    // Modal
    modalTitle: "Mã G-Code Fanuc CNC xuất ra",
    btnCopy: "Sao chép mã",
    btnClose: "Đóng",

    // Move types
    moveIdle: "Chờ",
    moveRapid: "Chạy dao nhanh (G00)",
    moveLinear: "Cắt thẳng (G01)",
    moveArcCw: "Cung tròn CW (G02)",
    moveArcCcw: "Cung tròn CCW (G03)",

    // Messages
    msgGenerating: "Đang tạo mã G-code và dữ liệu mô phỏng...",
    msgSuccess: "Đã tạo mã G-code và mô phỏng thành công!",
    msgCopied: "Đã sao chép toàn bộ mã G-code vào bộ nhớ tạm!",
    msgCopyError: "Không thể tự động sao chép mã",
    msgAnalyzing: "Đang phân tích hình học bản vẽ...",
  },
  en: {
    // Header
    appTitle: "Image to G-Code",
    appSubtitle: "Automatic 2D calibration, contour hierarchy sequencing, and standalone CAM simulation",
    apiDocs: "API Docs",

    // Section 1: Upload
    sec1Title: "1. Input Drawing or DXF",
    dropPrompt: "Drag & drop drawing or DXF file here",
    dropOrBrowse: "or browse file from computer",
    dropFormats: "Supports PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "Selected file:",
    noFileSelected: "No file chosen",

    // Section 2: Calibration
    sec2Title: "2. Calibration & Scale",
    stripDimensions: "Strip dimension annotations / text",
    refWidth: "Reference width (mm)",
    refHeight: "Reference height (mm)",
    pixelsPerMm: "Pixels per mm (px/mm)",

    // Section 3: Machining & Tool
    sec3Title: "3. Machining & Tool",
    cutDepth: "Cut depth Z (mm)",
    plungeFeed: "Plunge feed (mm/min)",
    cutFeed: "Cut feed (mm/min)",
    spindleRpm: "Spindle RPM",
    safeZ: "Safe Z (mm)",
    approachZ: "Approach Z (mm)",
    toolDia: "Tool diameter Ø (mm)",
    toolNum: "Tool number (T)",
    toolOffset: "Tool length offset (H)",
    programNum: "Program number (O)",

    // Action buttons
    btnGenerate: "Generate G-Code",
    btnReset: "Reset",
    btnDownloadNc: "Download .NC",
    btnDownloadDxf: "Download .DXF",
    btnViewGcode: "View G-code",

    // Panel 1: Preview
    previewTitle: "1. Image & DXF Preview (Source Drawing & Analysis)",
    tagDetection: "Tags (G54/Env)",
    tagGrid: "Grid",
    tagAxes: "Axes (+X/+Y)",
    previewFit: "Fit",
    previewDefaultText: "Select an image or DXF to preview (Scroll: Zoom | Drag: Pan | Dbl-click: Fit)",
    previewEmpty: "No image or DXF preview available",
    calibTag: "10x10 mm Calib",
    g54Origin: "G54 (0,0)",

    // Panel 2: Simulation
    simTitle: "2. Toolpath Simulation (Clean CAD/CAM View)",
    simGrid: "Grid & Axes",
    simRapids: "Rapids (G00)",
    simArrows: "Direction Arrows",
    simCutter: "Cutter (Ø)",
    simPlay: "Play",
    simPause: "Pause",
    simRestart: "Restart",
    simRecenter: "Fit View",
    simSpeed: "Speed:",
    simDefaultText: "No toolpath generated yet. Click 'Generate G-Code' to simulate.",
    simLoading: "Loading toolpath simulation...",

    // Modal
    modalTitle: "Fanuc CNC G-Code Output",
    btnCopy: "Copy to Clipboard",
    btnClose: "Close",

    // Move types
    moveIdle: "Idle",
    moveRapid: "Rapid (G00)",
    moveLinear: "Cut (G01)",
    moveArcCw: "Arc CW (G02)",
    moveArcCcw: "Arc CCW (G03)",

    // Messages
    msgGenerating: "Generating Fanuc G-code and simulation...",
    msgSuccess: "G-code and toolpath generated successfully!",
    msgCopied: "Copied full G-code to clipboard!",
    msgCopyError: "Unable to auto-copy to clipboard",
    msgAnalyzing: "Analyzing drawing geometry...",
  }
};

class I18nManager {
  constructor() {
    this.currentLang = localStorage.getItem('preferred_lang') || 'vi';
  }

  get lang() {
    return this.currentLang;
  }

  setLang(lang) {
    if (lang !== 'vi' && lang !== 'en') return;
    this.currentLang = lang;
    localStorage.setItem('preferred_lang', lang);
    this.updateDOM();
  }

  toggle() {
    const nextLang = this.currentLang === 'vi' ? 'en' : 'vi';
    this.setLang(nextLang);
    return nextLang;
  }

  t(key) {
    const dict = translations[this.currentLang] || translations.vi;
    return dict[key] !== undefined ? dict[key] : (translations.en[key] || key);
  }

  updateDOM() {
    document.documentElement.lang = this.currentLang;
    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const translation = this.t(key);
      if (translation !== undefined) {
        if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
          el.value = translation;
        } else if (el.hasAttribute('placeholder')) {
          el.placeholder = translation;
        } else {
          el.textContent = translation;
        }
      }
    });

    // Update flag and label on toggle button
    const langFlag = document.getElementById('lang-flag');
    const langText = document.getElementById('lang-text');
    if (langFlag && langText) {
      if (this.currentLang === 'vi') {
        langFlag.textContent = '🇻🇳';
        langText.textContent = 'Tiếng Việt';
      } else {
        langFlag.textContent = '🇬🇧';
        langText.textContent = 'English';
      }
    }
  }
}

export const i18n = new I18nManager();

