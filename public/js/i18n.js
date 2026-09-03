/**
 * Internationalization (i18n) Module
 * Standard CNC Terminology for Fanuc Machining & CAM Simulation
 * Supports Tiếng Việt (VI) and English (EN)
 */

export const translations = {
  vi: {
    // Tiêu đề đầu trang
    appTitle: "Chuyển ảnh sang G-Code",
    appSubtitle: "Tự động nhận dạng biên dạng hình học, thiết lập thứ tự cắt và mô phỏng quỹ đạo CAM chuẩn Fanuc CNC",
    apiDocs: "Tài liệu API",

    // Mục 1: Nạp file bản vẽ / CAD
    sec1Title: "1. Bản vẽ chi tiết hoặc File 2D CAD (DXF)",
    dropPrompt: "Kéo thả file bản vẽ (ảnh) hoặc file CAD .DXF vào đây",
    dropOrBrowse: "hoặc bấm để chọn file từ máy tính",
    dropFormats: "Định dạng hỗ trợ: PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "File bản vẽ đã chọn:",
    noFileSelected: "Chưa nạp file bản vẽ",
    stripDimensions: "Tự động lọc bỏ đường gióng kích thước & chữ ghi chú (chỉ lấy biên dạng)",

    // Mục 2: Căn chuẩn tỷ lệ & Kích thước phôi
    sec2Title: "2. Căn chuẩn tỷ lệ & Kích thước phôi",
    refWidth: "Kích thước chuẩn phương X (mm)",
    refHeight: "Kích thước chuẩn phương Y (mm)",
    pixelsPerMm: "Độ phân giải tỷ lệ (px/mm)",

    // Mục 3: Chế độ cắt & Thông số dao phay
    sec3Title: "3. Chế độ cắt & Thông số dao phay",
    cutDepth: "Chiều sâu cắt Z (mm) [Z Final]",
    plungeFeed: "Bước tiến xuống dao Fz (mm/phút)",
    cutFeed: "Bước tiến cắt gọt F (mm/phút)",
    spindleRpm: "Tốc độ trục chính S (vòng/phút)",
    safeZ: "Mặt phẳng lùi dao an toàn (Safe Z mm)",
    approachZ: "Mặt phẳng tiếp cận phôi (Approach Z mm)",
    toolDia: "Đường kính dao phay Ø (mm)",
    toolNum: "Số hiệu ổ dao (T)",
    toolOffset: "Mã bù chiều dài dao (H)",
    programNum: "Số thứ tự chương trình (O)",

    // Các nút chức năng
    btnGenerate: "Xuất chương trình G-Code",
    btnReset: "Khôi phục thông số chuẩn",
    btnDownloadNc: "Tải file NC (Fanuc)",
    btnDownloadDxf: "Xuất file CAD (.DXF)",
    btnViewGcode: "Xem khối lệnh G-Code",

    // Khung 1: Kiểm tra hình học & Gốc phôi G54
    previewTitle: "1. Kiểm tra hình học bản vẽ & Tọa độ gốc phôi (G54)",
    tagDetection: "Gốc G54 / Phôi bao",
    tagGrid: "Lưới tọa độ",
    tagAxes: "Hệ trục máy (+X/+Y)",
    previewFit: "Vừa khung",
    previewDefaultText: "Nạp bản vẽ 2D hoặc file DXF để kiểm tra biên dạng (Cuộn: Zoom | Kéo chuột: Pan | Nhấp đúp: Vừa khung)",
    previewEmpty: "Chưa có dữ liệu hình học hoặc file CAD để hiển thị",
    calibTag: "Chuẩn đo 10x10 mm",
    g54Origin: "Gốc gia công G54 (X0, Y0)",

    // Khung 2: Mô phỏng quỹ đạo gia công CAM
    simTitle: "2. Mô phỏng đường chạy dao CNC (Kiểm tra quỹ đạo CAM)",
    simGrid: "Lưới & Hệ trục",
    simRapids: "Chạy dao nhanh (G00)",
    simArrows: "Hướng chạy dao",
    simCutter: "Vết cắt dao phay (Ø)",
    simPlay: "Mô phỏng",
    simPause: "Tạm dừng",
    simRestart: "Chạy lại từ đầu",
    simRecenter: "Căn giữa phôi",
    simSpeed: "Tốc độ mô phỏng:",
    simDefaultText: "Chưa có quỹ đạo cắt. Bấm 'Xuất chương trình G-Code' để kiểm tra mô phỏng.",
    simLoading: "Đang tính toán quỹ đạo gia công và biên dịch mô phỏng...",

    // Thanh xuất file
    outputFormatsLabel: "Định dạng xuất: Chương trình Fanuc CNC (.NC / ISO 6983) & Bản vẽ 2D CAD (.DXF)",

    // Hộp thoại khối lệnh G-Code
    modalTitle: "Chương trình gia công CNC Fanuc (Chuẩn ISO 6983)",
    btnCopy: "Sao chép khối lệnh",
    btnClose: "Đóng",

    // Kiểu chuyển động CNC (DRO Readout - Luôn giữ nguyên tiếng Anh chuẩn công nghiệp)
    moveIdle: "IDLE",
    moveRapid: "RAPID (G00)",
    moveLinear: "LINEAR CUT (G01)",
    moveArcCw: "CIRCULAR CW (G02)",
    moveArcCcw: "CIRCULAR CCW (G03)",

    // Thông báo trạng thái
    msgGenerating: "Đang phân tích biên dạng hình học và xuất khối lệnh G-Code...",
    msgSuccess: "Đã xuất chương trình G-Code và nạp quỹ đạo mô phỏng thành công!",
    msgCopied: "Đã sao chép toàn bộ chương trình NC vào clipboard!",
    msgCopyError: "Không thể tự động sao chép chương trình",
    msgAnalyzing: "Đang quét nhận dạng đường bao phôi và phân cấp biên dạng cắt (Trong/Ngoài)...",
  },
  en: {
    // Header
    appTitle: "Image to G-Code",
    appSubtitle: "Automatic 2D contour detection, hierarchy sequencing, and Fanuc CNC CAM simulation",
    apiDocs: "API Docs",

    // Section 1: Upload
    sec1Title: "1. Part Drawing or 2D CAD File (DXF)",
    dropPrompt: "Drag & drop drawing or DXF file here",
    dropOrBrowse: "or browse file from computer",
    dropFormats: "Supported formats: PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "Selected drawing file:",
    noFileSelected: "No drawing file loaded",
    stripDimensions: "Auto-filter dimension lines & text annotations (contours only)",

    // Section 2: Calibration
    sec2Title: "2. Scale Calibration & Workpiece Size",
    refWidth: "Reference Dimension X (mm)",
    refHeight: "Reference Dimension Y (mm)",
    pixelsPerMm: "Scale Factor (px/mm)",

    // Section 3: Machining Parameters
    sec3Title: "3. Cutting Parameters & End Mill Spec",
    cutDepth: "Final Cutting Depth Z (mm)",
    plungeFeed: "Plunge Feedrate Fz (mm/min)",
    cutFeed: "Cutting Feedrate F (mm/min)",
    spindleRpm: "Spindle Speed S (RPM)",
    safeZ: "Retract Plane (Safe Z mm)",
    approachZ: "Approach Plane (Approach Z mm)",
    toolDia: "End Mill Diameter Ø (mm)",
    toolNum: "Tool Station Number (T)",
    toolOffset: "Height Offset Code (H)",
    programNum: "Program Number (O)",

    // Action buttons
    btnGenerate: "Generate G-Code Program",
    btnReset: "Reset Parameters",
    btnDownloadNc: "Download .NC (Fanuc)",
    btnDownloadDxf: "Export 2D CAD (.DXF)",
    btnViewGcode: "Inspect G-Code Blocks",

    // Panel 1: Preview
    previewTitle: "1. Geometry Inspection & Work Coordinate (G54)",
    tagDetection: "G54 Origin / Bounds",
    tagGrid: "Coordinate Grid",
    tagAxes: "Machine Axes (+X/+Y)",
    previewFit: "Fit View",
    previewDefaultText: "Load 2D drawing or DXF to inspect geometry (Scroll: Zoom | Drag: Pan | Dbl-click: Fit)",
    previewEmpty: "No geometry or CAD file available to display",
    calibTag: "10x10 mm Calib",
    g54Origin: "G54 Work Zero (X0, Y0)",

    // Panel 2: Simulation
    simTitle: "2. CNC Toolpath Simulation & Verification (CAM)",
    simGrid: "Grid & Axes",
    simRapids: "Rapid Traverse (G00)",
    simArrows: "Cutting Direction",
    simCutter: "Cutter Kerf (Ø)",
    simPlay: "Simulate",
    simPause: "Pause",
    simRestart: "Restart",
    simRecenter: "Center Workpiece",
    simSpeed: "Simulation Speed:",
    simDefaultText: "No toolpath generated yet. Click 'Generate G-Code Program' to simulate.",
    simLoading: "Calculating toolpaths and loading simulation...",

    // Export bar
    outputFormatsLabel: "Output Formats: Fanuc CNC Program (.NC / ISO 6983) & 2D CAD (.DXF)",

    // Modal
    modalTitle: "Fanuc CNC NC Program Output (ISO 6983)",
    btnCopy: "Copy Program",
    btnClose: "Close",

    // Move types
    moveIdle: "IDLE",
    moveRapid: "RAPID (G00)",
    moveLinear: "LINEAR CUT (G01)",
    moveArcCw: "CIRCULAR CW (G02)",
    moveArcCcw: "CIRCULAR CCW (G03)",

    // Messages
    msgGenerating: "Analyzing geometry and generating Fanuc G-code...",
    msgSuccess: "G-code program and CAM toolpath generated successfully!",
    msgCopied: "Copied full NC program to clipboard!",
    msgCopyError: "Unable to auto-copy to clipboard",
    msgAnalyzing: "Scanning contours and classifying cutting hierarchy (Pockets/Islands)...",
  }
};

/**
 * Bulletproof Icon Rendering Helper
 * Uses Lucide if loaded, otherwise falls back to pure inline SVGs
 */
export function renderAllIcons() {
  if (typeof window !== 'undefined' && window.lucide && typeof window.lucide.createIcons === 'function') {
    try {
      window.lucide.createIcons();
    } catch (e) {
      console.warn('Lucide createIcons error:', e);
    }
  }

  // Built-in inline SVG icon fallback for all used Lucide icons
  const ICON_SVGS = {
    'file-code': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-file-code"><path d="M10 12.5 8 15l2 2.5"/><path d="m14 12.5 2 2.5-2 2.5"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/></svg>',
    'upload-cloud': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-upload-cloud"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>',
    'ruler': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-ruler"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/></svg>',
    'settings-2': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-settings-2"><path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/></svg>',
    'image': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-image"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>',
    'activity': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-activity"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.48 12H2"/></svg>',
    'play': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-play"><polygon points="6 3 20 12 6 21 6 3"/></svg>',
    'pause': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pause"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
    'rotate-ccw': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-rotate-ccw"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>',
    'maximize': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-maximize"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
    'code': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-code"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    'download': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-download"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
    'file-text': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-file-text"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>',
    'copy': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-copy"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
    'x': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-x"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
  };

  if (typeof document !== 'undefined') {
    document.querySelectorAll('i[data-lucide]').forEach((el) => {
      const iconName = el.getAttribute('data-lucide');
      const svgStr = ICON_SVGS[iconName];
      if (svgStr) {
        const temp = document.createElement('div');
        temp.innerHTML = svgStr;
        const svg = temp.firstElementChild;
        if (svg) {
          const cls = el.getAttribute('class') || '';
          svg.setAttribute('class', cls);
          svg.setAttribute('data-lucide-rendered', iconName);
          el.replaceWith(svg);
        }
      }
    });
  }
}

class I18nManager {
  constructor() {
    this.currentLang = (typeof localStorage !== 'undefined' && localStorage.getItem('preferred_lang')) || 'vi';
  }

  get lang() {
    return this.currentLang;
  }

  setLang(lang) {
    if (lang !== 'vi' && lang !== 'en') return;
    this.currentLang = lang;
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem('preferred_lang', lang);
      } catch (e) {
        console.warn('Cannot write to localStorage:', e);
      }
    }
    this.updateDOM();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang: this.currentLang } }));
    }
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
    if (typeof document === 'undefined') return;
    document.documentElement.lang = this.currentLang;

    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach((el) => {
      try {
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
      } catch (err) {
        console.warn('i18n translation error on element:', el, err);
      }
    });

    // Update flag, label, and title on toggle button
    const btnLang = document.getElementById('btn-lang-toggle');
    const langFlag = document.getElementById('lang-flag');
    const langText = document.getElementById('lang-text');
    if (langFlag && langText) {
      if (this.currentLang === 'vi') {
        langFlag.textContent = '🇻🇳';
        langText.textContent = 'Tiếng Việt';
        if (btnLang) btnLang.title = 'Chuyển sang English / Switch to English';
      } else {
        langFlag.textContent = '🇬🇧';
        langText.textContent = 'English';
        if (btnLang) btnLang.title = 'Chuyển sang Tiếng Việt / Switch to Vietnamese';
      }
    }

    // Refresh icons so any dynamically rendered elements get crisp icons
    renderAllIcons();
  }
}

export const i18n = new I18nManager();

// Single-source event binding for language toggle button
export function bindLangToggle() {
  const btn = document.getElementById('btn-lang-toggle');
  if (btn) {
    btn.onclick = (e) => {
      if (e) e.preventDefault();
      i18n.toggle();
    };
  }
}

// Global hook
if (typeof window !== 'undefined') {
  window.i18n = i18n;
  window.toggleLanguage = () => i18n.toggle();
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindLangToggle);
  } else {
    bindLangToggle();
  }
}
