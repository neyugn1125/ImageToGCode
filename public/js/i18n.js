/**
 * Internationalization (i18n) Module
 * Supports Tiếng Việt (VI) and English (EN) with full icon & emoji resilience
 */

export const translations = {
  vi: {
    // Header
    appTitle: "Chuyển ảnh sang G-Code",
    appSubtitle: "Tự động nhận diện biên dạng, phân cấp cắt gọt và mô phỏng CAM chuẩn Fanuc CNC",
    apiDocs: "Tài liệu API",

    // Section 1: Upload
    sec1Title: "1. 📁 Bản vẽ đầu vào hoặc File DXF",
    dropPrompt: "Kéo thả bản vẽ hoặc file DXF vào đây",
    dropOrBrowse: "hoặc chọn file từ máy tính",
    dropFormats: "Hỗ trợ định dạng PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "File đã chọn:",
    noFileSelected: "Chưa chọn file",

    // Section 2: Calibration
    sec2Title: "2. 📐 Căn chỉnh tỷ lệ & Kích thước",
    stripDimensions: "Loại bỏ đường gióng kích thước & chữ ký hiệu",
    refWidth: "Chiều rộng thực tế (mm)",
    refHeight: "Chiều cao thực tế (mm)",
    pixelsPerMm: "Tỷ lệ pixel / mm (px/mm)",

    // Section 3: Machining & Tool
    sec3Title: "3. ⚙️ Thông số gia công & Dao cụ",
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
    btnReset: "🔄 Mặc định",
    btnDownloadNc: "📥 Tải file .NC",
    btnDownloadDxf: "💾 Tải file .DXF",
    btnViewGcode: "📄 Xem mã G-Code",

    // Panel 1: Preview
    previewTitle: "1. 🖼️ Xem trước Bản vẽ & DXF (Nhận diện & Tọa độ)",
    tagDetection: "Nhãn (G54/Bao)",
    tagGrid: "Lưới",
    tagAxes: "Trục (+X/+Y)",
    previewFit: "🎯 Vừa khung",
    previewDefaultText: "Chọn ảnh bản vẽ hoặc file DXF để xem trước (Cuộn: Zoom | Kéo: Pan | Nhấp đúp: Vừa khung)",
    previewEmpty: "Chưa có ảnh hoặc file DXF để xem trước",
    calibTag: "Chuẩn 10x10mm",
    g54Origin: "Gốc G54 (0,0)",

    // Panel 2: Simulation
    simTitle: "2. 🎬 Mô phỏng đường chạy dao (Màn hình CAD/CAM)",
    simGrid: "Lưới & Trục",
    simRapids: "Chạy dao nhanh (G00)",
    simArrows: "Mũi tên hướng cắt",
    simCutter: "Đầu dao (Ø)",
    simPlay: "▶️ Phát",
    simPause: "⏸️ Tạm dừng",
    simRestart: "🔄 Bắt đầu lại",
    simRecenter: "Căn giữa",
    simSpeed: "Tốc độ:",
    simDefaultText: "Chưa có đường chạy dao. Bấm 'Tạo mã G-Code' để bắt đầu mô phỏng.",
    simLoading: "Đang tải mô phỏng đường dao...",

    // Modal
    modalTitle: "📄 Mã G-Code Fanuc CNC xuất ra",
    btnCopy: "Sao chép mã",
    btnClose: "✕ Đóng",

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
    sec1Title: "1. 📁 Input Drawing or DXF",
    dropPrompt: "Drag & drop drawing or DXF file here",
    dropOrBrowse: "or browse file from computer",
    dropFormats: "Supports PNG, JPG, BMP, TIFF, DXF",
    selectedFileLabel: "Selected file:",
    noFileSelected: "No file chosen",

    // Section 2: Calibration
    sec2Title: "2. 📐 Calibration & Scale",
    stripDimensions: "Strip dimension annotations / text",
    refWidth: "Reference width (mm)",
    refHeight: "Reference height (mm)",
    pixelsPerMm: "Pixels per mm (px/mm)",

    // Section 3: Machining & Tool
    sec3Title: "3. ⚙️ Machining & Tool",
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
    btnReset: "🔄 Reset defaults",
    btnDownloadNc: "📥 Download .NC",
    btnDownloadDxf: "💾 Download .DXF",
    btnViewGcode: "📄 View G-code",

    // Panel 1: Preview
    previewTitle: "1. 🖼️ Image & DXF Preview (Source Drawing & Analysis)",
    tagDetection: "Tags (G54/Env)",
    tagGrid: "Grid",
    tagAxes: "Axes (+X/+Y)",
    previewFit: "🎯 Fit",
    previewDefaultText: "Select an image or DXF to preview (Scroll: Zoom | Drag: Pan | Dbl-click: Fit)",
    previewEmpty: "No image or DXF preview available",
    calibTag: "10x10 mm Calib",
    g54Origin: "G54 (0,0)",

    // Panel 2: Simulation
    simTitle: "2. 🎬 Toolpath Simulation (Clean CAD/CAM View)",
    simGrid: "Grid & Axes",
    simRapids: "Rapids (G00)",
    simArrows: "Direction Arrows",
    simCutter: "Cutter (Ø)",
    simPlay: "▶️ Play",
    simPause: "⏸️ Pause",
    simRestart: "🔄 Restart",
    simRecenter: "Fit View",
    simSpeed: "Speed:",
    simDefaultText: "No toolpath generated yet. Click 'Generate G-Code' to simulate.",
    simLoading: "Loading toolpath simulation...",

    // Modal
    modalTitle: "📄 Fanuc CNC G-Code Output",
    btnCopy: "Copy to Clipboard",
    btnClose: "✕ Close",

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
    'play': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-play"><polygon points="6 3 20 12 6 21 6 3"/></svg>',
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
      localStorage.setItem('preferred_lang', lang);
    }
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
    if (typeof document === 'undefined') return;
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

    // Refresh icons so any dynamically rendered elements get crisp icons
    renderAllIcons();
  }
}

export const i18n = new I18nManager();
