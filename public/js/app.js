import { ImagePreviewViewer } from './preview.js';
import { CncSimulator } from './simulator.js';
import { i18n, renderAllIcons } from './i18n.js';

class ImageToGCodeWebApp {
  constructor() {
    this.selectedFile = null;

    this._initElements();
    this._initViewers();
    this._bindEvents();
    this._loadDefaultPreset();

    // Initialize UI language and ensure all icons render
    i18n.updateDOM();
    renderAllIcons();
  }

  _initElements() {
    this.btnLangToggle = document.getElementById('btn-lang-toggle');
    // Form Inputs
    this.imageInput = document.getElementById('image-input');
    this.dropZone = document.getElementById('drop-zone');
    this.fileNameDisplay = document.getElementById('file-name-display');

    this.stripDimensionsCheck = document.getElementById('strip-dimensions');
    this.refWidthInput = document.getElementById('ref-width');
    this.refHeightInput = document.getElementById('ref-height');
    this.pixelsPerMmInput = document.getElementById('pixels-per-mm');

    this.cutDepthInput = document.getElementById('cut-depth');
    this.plungeFeedInput = document.getElementById('plunge-feed');
    this.cutFeedInput = document.getElementById('cut-feed');
    this.spindleRpmInput = document.getElementById('spindle-rpm');
    this.safeZInput = document.getElementById('safe-z');
    this.approachZInput = document.getElementById('approach-z');
    this.toolDiaInput = document.getElementById('tool-dia');
    this.toolNumberInput = document.getElementById('tool-number');
    this.toolOffsetInput = document.getElementById('tool-offset');
    this.cutterOffsetDInput = document.getElementById('cutter-offset-d');
    this.cutterCompSelect = document.getElementById('cutter-comp');
    this.programNumberInput = document.getElementById('program-number');

    // Buttons
    this.generateBtn = document.getElementById('btn-generate');
    this.resetBtn = document.getElementById('btn-reset');
    this.quickCopyGcodeBtn = document.getElementById('btn-quick-copy-gcode');
    this.downloadNcBtn = document.getElementById('btn-download-nc');
    this.downloadDxfBtn = document.getElementById('btn-download-dxf');
    this.viewGcodeBtn = document.getElementById('btn-view-gcode');

    // Preview Canvas & Controls
    this.previewCanvas = document.getElementById('preview-canvas');
    this.previewInfo = document.getElementById('preview-info');
    this.previewCoords = document.getElementById('preview-coords');
    this.showTagsCheck = document.getElementById('toggle-show-tags');
    this.togglePreviewGrid = document.getElementById('toggle-preview-grid');
    this.togglePreviewAxes = document.getElementById('toggle-preview-axes');
    this.btnPreviewZoomIn = document.getElementById('btn-preview-zoom-in');
    this.btnPreviewZoomOut = document.getElementById('btn-preview-zoom-out');
    this.btnPreviewFit = document.getElementById('btn-preview-fit');

    // Simulator Canvas & Controls
    this.simCanvas = document.getElementById('sim-canvas');
    this.simPlayBtn = document.getElementById('btn-sim-play');
    this.simStepBackBtn = document.getElementById('btn-sim-step-back');
    this.simStepForwardBtn = document.getElementById('btn-sim-step-forward');
    this.simRestartBtn = document.getElementById('btn-sim-restart');
    this.simRecenterBtn = document.getElementById('btn-sim-recenter');
    this.simSpeedSlider = document.getElementById('sim-speed-slider');
    this.simSpeedLabel = document.getElementById('sim-speed-label');
    this.simScrubber = document.getElementById('sim-scrubber');
    this.simDroReadout = document.getElementById('sim-dro-readout');
    this.simSummary = document.getElementById('sim-summary');

    // Simulator Toggles
    this.toggleGrid = document.getElementById('toggle-grid');
    this.toggleRapids = document.getElementById('toggle-rapids');
    this.toggleArrows = document.getElementById('toggle-arrows');
    this.toggleCutter = document.getElementById('toggle-cutter');

    // Modal
    this.gcodeModal = document.getElementById('gcode-modal');
    this.gcodeModalContent = document.getElementById('gcode-modal-content');
    this.closeModalBtn = document.getElementById('btn-close-modal');
    this.closeModalBottomBtn = document.getElementById('btn-close-modal-bottom');
    this.copyGcodeBtn = document.getElementById('btn-copy-gcode');

    // Status Banner / Toast
    this.statusBanner = document.getElementById('status-banner');
  }

  _initViewers() {
    this.previewViewer = new ImagePreviewViewer(this.previewCanvas, (coord) => {
      if (!coord) {
        this.previewCoords.textContent = '';
        return;
      }
      let text = `Cursor: ${coord.pxX}, ${coord.pxY} px`;
      if (coord.mmX !== undefined && coord.mmY !== undefined) {
        text += `  |  G54: X=${coord.mmX.toFixed(2)}, Y=${coord.mmY.toFixed(2)} mm`;
      }
      this.previewCoords.textContent = text;
    });

    this.simulator = new CncSimulator(this.simCanvas, {
      onProgressUpdate: (percent, curTime, totalTime) => {
        this.simScrubber.value = percent.toFixed(1);
      },
      onStatusUpdate: (state) => {
        const moveNames = {
          idle: 'IDLE',
          rapid: 'RAPID (G00)',
          linear: 'LINEAR CUT (G01)',
          arc_cw: 'CIRCULAR CW (G02)',
          arc_ccw: 'CIRCULAR CCW (G03)'
        };
        const kindLabel = moveNames[state.kind] || (state.kind ? state.kind.toUpperCase() : 'IDLE');
        this.simDroReadout.textContent = `X: ${state.x.toFixed(2).padStart(6, ' ')} mm   Y: ${state.y.toFixed(2).padStart(6, ' ')} mm   Z: ${state.z.toFixed(2).padStart(5, ' ')} mm   |   F: ${Math.round(state.feed).toString().padStart(4, ' ')} mm/min   |   ${kindLabel}   |   ${state.currentTime.toFixed(1)}s / ${state.totalTime.toFixed(1)}s (${Math.round(state.progress)}%)`;
      }
    });
  }

  _bindEvents() {
    // Language Switcher Synchronization
    window.addEventListener('languageChanged', () => {
      this._updateLanguageUI();
    });

    // Image Upload
    this.imageInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        this._handleFileSelected(e.target.files[0]);
      }
    });

    // Drag and drop
    this.dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.dropZone.classList.add('border-blue-500', 'bg-blue-50');
    });

    this.dropZone.addEventListener('dragleave', () => {
      this.dropZone.classList.remove('border-blue-500', 'bg-blue-50');
    });

    this.dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      this.dropZone.classList.remove('border-blue-500', 'bg-blue-50');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        this._handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    // Main Conversion
    this.generateBtn.addEventListener('click', () => this._performConversion());
    this.resetBtn.addEventListener('click', () => this._loadDefaultPreset());

    // Downloads & Exports
    if (this.quickCopyGcodeBtn) {
      this.quickCopyGcodeBtn.addEventListener('click', () => this._quickCopyGcode());
    }
    this.downloadNcBtn.addEventListener('click', () => this._downloadNcFile());
    this.downloadDxfBtn.addEventListener('click', () => this._downloadDxfFile());
    this.viewGcodeBtn.addEventListener('click', () => this._openGcodeModal());

    // Preview Toggles & Zoom Controls
    if (this.showTagsCheck) {
      this.showTagsCheck.addEventListener('change', (e) => {
        this.previewViewer.setShowTags(e.target.checked);
      });
    }
    if (this.togglePreviewGrid) {
      this.togglePreviewGrid.addEventListener('change', (e) => {
        this.previewViewer.setShowGrid(e.target.checked);
      });
    }
    if (this.togglePreviewAxes) {
      this.togglePreviewAxes.addEventListener('change', (e) => {
        this.previewViewer.setShowAxes(e.target.checked);
      });
    }
    if (this.btnPreviewZoomIn) {
      this.btnPreviewZoomIn.addEventListener('click', () => this.previewViewer.zoomIn());
    }
    if (this.btnPreviewZoomOut) {
      this.btnPreviewZoomOut.addEventListener('click', () => this.previewViewer.zoomOut());
    }
    if (this.btnPreviewFit) {
      this.btnPreviewFit.addEventListener('click', () => this.previewViewer.fitView());
    }

    this.stripDimensionsCheck.addEventListener('change', () => {
      if (this.selectedFile) {
        this._analyzeSelectedImage();
      }
    });

    // Tool Diameter change syncs to simulator
    this.toolDiaInput.addEventListener('input', (e) => {
      this.simulator.setToolDiameter(e.target.value);
    });

    // Simulator View Toggles
    const updateSimToggles = () => {
      this.simulator.setViewToggles({
        showGrid: this.toggleGrid.checked,
        showRapids: this.toggleRapids.checked,
        showArrows: this.toggleArrows.checked,
        showCutter: this.toggleCutter.checked
      });
    };
    this.toggleGrid.addEventListener('change', updateSimToggles);
    this.toggleRapids.addEventListener('change', updateSimToggles);
    this.toggleArrows.addEventListener('change', updateSimToggles);
    this.toggleCutter.addEventListener('change', updateSimToggles);

    // Playback Controls
    this.simPlayBtn.addEventListener('click', () => {
      this.simulator.togglePlay();
      this._updatePlayButtonState();
    });

    this.simStepBackBtn.addEventListener('click', () => {
      this.simulator.stepBackward();
      this._updatePlayButtonState();
    });

    this.simStepForwardBtn.addEventListener('click', () => {
      this.simulator.stepForward();
      this._updatePlayButtonState();
    });

    this.simRestartBtn.addEventListener('click', () => {
      this.simulator.restart();
      this._updatePlayButtonState();
    });

    this.simRecenterBtn.addEventListener('click', () => {
      this.simulator.fitView();
      this.simulator.render();
    });

    this.simSpeedSlider.addEventListener('input', (e) => {
      const speed = Number(e.target.value) || 5;
      this.simSpeedLabel.textContent = `${speed}x`;
      this.simulator.setSpeed(speed);
    });

    this.simScrubber.addEventListener('input', (e) => {
      this.simulator.seek(Number(e.target.value) / 100.0);
      this._updatePlayButtonState();
    });

    // Modal Events
    if (this.closeModalBtn) {
      this.closeModalBtn.addEventListener('click', () => {
        this.gcodeModal.classList.add('hidden');
      });
    }
    if (this.closeModalBottomBtn) {
      this.closeModalBottomBtn.addEventListener('click', () => {
        this.gcodeModal.classList.add('hidden');
      });
    }

    this.copyGcodeBtn.addEventListener('click', async () => {
      if (this.conversionResult && this.conversionResult.gcode) {
        await navigator.clipboard.writeText(this.conversionResult.gcode);
        const span = this.copyGcodeBtn.querySelector('span');
        if (span) {
          span.textContent = i18n.lang === 'vi' ? 'Đã sao chép!' : 'Copied!';
        }
        setTimeout(() => {
          if (span) {
            span.textContent = i18n.t('btnCopy');
          }
        }, 1800);
      }
    });
  }

  _updateLanguageUI() {
    this.previewViewer.render();
    this.simulator.render();
    if (!this.selectedFile) {
      this.previewInfo.textContent = i18n.t('previewDefaultText');
      this.fileNameDisplay.textContent = i18n.t('noFileSelected');
    }
    if (!this.conversionResult) {
      this.simSummary.textContent = i18n.t('simDefaultText');
    }
    this._updatePlayButtonState();
  }

  _loadDefaultPreset() {
    this.cutDepthInput.value = '-5.0';
    this.plungeFeedInput.value = '100.0';
    this.cutFeedInput.value = '300.0';
    this.spindleRpmInput.value = '1500';
    this.safeZInput.value = '50.0';
    this.approachZInput.value = '2.0';
    this.toolDiaInput.value = '3.0';
    this.toolNumberInput.value = '1';
    this.toolOffsetInput.value = '1';
    if (this.cutterOffsetDInput) this.cutterOffsetDInput.value = '1';
    if (this.cutterCompSelect) this.cutterCompSelect.value = 'G40';
    this.programNumberInput.value = '1000';
    this.stripDimensionsCheck.checked = false;
    this.refWidthInput.value = '';
    this.refHeightInput.value = '';
    this.pixelsPerMmInput.value = '';
    this.simulator.setToolDiameter(3.0);
    if (this.quickCopyGcodeBtn) this.quickCopyGcodeBtn.disabled = true;
  }

  async _handleFileSelected(file) {
    this.selectedFile = file;
    this.fileNameDisplay.textContent = file.name;
    const isDxf = file.name.toLowerCase().endsWith('.dxf');

    // Adapt UI for DXF vs Image
    this.stripDimensionsCheck.disabled = isDxf;
    this.refWidthInput.disabled = isDxf;
    this.refHeightInput.disabled = isDxf;
    this.pixelsPerMmInput.disabled = isDxf;

    try {
      if (isDxf) {
        this.previewViewer.loadDxf(file);
        this.previewInfo.textContent = `DXF CAD File | ${file.name}`;
      } else {
        await this.previewViewer.loadImage(file);
        this.previewInfo.textContent = `${this.previewViewer.imgW} x ${this.previewViewer.imgH} px | ${file.name}`;
      }
      await this._analyzeSelectedImage();
    } catch (err) {
      this._showStatus(`Error loading file: ${err.message}`, 'error');
    }
  }

  async _analyzeSelectedImage() {
    if (!this.selectedFile) return;

    const isDxf = this.selectedFile.name.toLowerCase().endsWith('.dxf');
    const formData = new FormData();
    formData.append('image', this.selectedFile);
    formData.append('strip_dimensions', this.stripDimensionsCheck.checked);
    if (!isDxf) {
      if (this.refWidthInput.value.trim()) formData.append('reference_width_mm', this.refWidthInput.value.trim());
      if (this.refHeightInput.value.trim()) formData.append('reference_height_mm', this.refHeightInput.value.trim());
      if (this.pixelsPerMmInput.value.trim()) formData.append('pixels_per_mm', this.pixelsPerMmInput.value.trim());
    }

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Analysis failed (${response.status})`);
      }

      const analysis = await response.json();
      this.previewViewer.setAnalysis(analysis);

      const parts = [];
      if (isDxf) {
        parts.push(`DXF CAD Envelope: ${analysis.image_width} x ${analysis.image_height} mm`);
      } else {
        parts.push(`${analysis.image_width} x ${analysis.image_height} px`);
      }
      parts.push(this.selectedFile.name);

      if (!isDxf && analysis.scale_factor) {
        parts.push(`SF=${analysis.scale_factor.toFixed(2)} px/mm`);
      }
      if (analysis.contour_count > 0) {
        parts.push(`${analysis.contour_count} entity/contour(s)`);
      }
      this.previewInfo.textContent = parts.join('  |  ');
    } catch (err) {
      console.warn('Quick analysis note:', err.message);
    }
  }

  async _performConversion() {
    if (!this.selectedFile) {
      this._showStatus(i18n.lang === 'vi' ? 'Vui lòng chọn hoặc tải lên bản vẽ trước.' : 'Please select or upload a drawing image first.', 'warning');
      return;
    }

    this._setBusy(true);
    this._showStatus(i18n.t('msgGenerating'), 'info');

    const formData = new FormData();
    formData.append('image', this.selectedFile);
    formData.append('cut_depth', this.cutDepthInput.value.trim() || '-5.0');
    formData.append('plunge_feed', this.plungeFeedInput.value.trim() || '100.0');
    formData.append('cut_feed', this.cutFeedInput.value.trim() || '300.0');
    formData.append('spindle_speed', this.spindleRpmInput.value.trim() || '1500');
    formData.append('safe_z', this.safeZInput.value.trim() || '50.0');
    formData.append('approach_z', this.approachZInput.value.trim() || '2.0');
    formData.append('tool_diameter', this.toolDiaInput.value.trim() || '3.0');
    formData.append('tool_number', this.toolNumberInput.value.trim() || '1');
    formData.append('tool_offset', this.toolOffsetInput.value.trim() || '1');
    if (this.cutterOffsetDInput) formData.append('cutter_offset_d', this.cutterOffsetDInput.value.trim() || '1');
    if (this.cutterCompSelect) formData.append('cutter_comp', this.cutterCompSelect.value || 'CAM');
    formData.append('program_number', this.programNumberInput.value.trim() || '1000');
    formData.append('strip_dimensions', this.stripDimensionsCheck.checked);

    if (this.refWidthInput.value.trim()) formData.append('reference_width_mm', this.refWidthInput.value.trim());
    if (this.refHeightInput.value.trim()) formData.append('reference_height_mm', this.refHeightInput.value.trim());
    if (this.pixelsPerMmInput.value.trim()) formData.append('pixels_per_mm', this.pixelsPerMmInput.value.trim());

    try {
      const response = await fetch('/api/convert', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Conversion failed (${response.status})`);
      }

      const result = await response.json();
      this.conversionResult = result;

      // Update Preview with analysis
      this.previewViewer.setAnalysis(result.analysis);

      // Update Simulator with toolpath
      const toolDia = Number(this.toolDiaInput.value) || 3.0;
      this.simulator.setSegments(result.segments, toolDia);

      // Enable actions
      if (this.quickCopyGcodeBtn) this.quickCopyGcodeBtn.disabled = false;
      this.downloadNcBtn.disabled = false;
      this.downloadDxfBtn.disabled = !result.dxf_base64;
      this.viewGcodeBtn.disabled = false;
      this.simPlayBtn.disabled = false;
      this.simStepBackBtn.disabled = false;
      this.simStepForwardBtn.disabled = false;
      this.simRestartBtn.disabled = false;
      this.simScrubber.disabled = false;

      // Summary text
      const t = result.timeline;
      if (i18n.lang === 'vi') {
        this.simSummary.textContent = `Bao phôi: ${t.envelope_width_mm.toFixed(1)} x ${t.envelope_height_mm.toFixed(1)} mm  |  Chiều dài cắt: ${t.cut_distance_mm.toFixed(0)} mm  |  Chạy dao nhanh: ${t.rapid_distance_mm.toFixed(0)} mm  |  Thời gian: ${t.total_time_s.toFixed(1)}s`;
      } else {
        this.simSummary.textContent = `Envelope: ${t.envelope_width_mm.toFixed(1)} x ${t.envelope_height_mm.toFixed(1)} mm  |  Cut Distance: ${t.cut_distance_mm.toFixed(0)} mm  |  Rapid: ${t.rapid_distance_mm.toFixed(0)} mm  |  Time: ${t.total_time_s.toFixed(1)}s`;
      }

      this._showStatus(i18n.t('msgSuccess'), 'success');
    } catch (err) {
      this._showStatus(`Error: ${err.message}`, 'error');
    } finally {
      this._setBusy(false);
    }
  }

  async _quickCopyGcode() {
    if (!this.conversionResult || !this.conversionResult.gcode) return;
    try {
      await navigator.clipboard.writeText(this.conversionResult.gcode);
      const span = this.quickCopyGcodeBtn ? this.quickCopyGcodeBtn.querySelector('span') : null;
      if (span) {
        span.textContent = i18n.lang === 'vi' ? 'Đã sao chép!' : 'Copied!';
      }
      this._showStatus(
        i18n.lang === 'vi'
          ? 'Đã sao chép toàn bộ chương trình G-Code vào bộ nhớ tạm.'
          : 'Copied entire G-Code program to clipboard.',
        'success'
      );
      setTimeout(() => {
        if (span) {
          span.textContent = i18n.t('btnQuickCopyGcode');
        }
      }, 1800);
    } catch (err) {
      this._showStatus(`Clipboard error: ${err.message}`, 'error');
    }
  }

  _downloadNcFile() {
    if (!this.conversionResult || !this.conversionResult.gcode) return;
    const blob = new Blob([this.conversionResult.gcode], { type: 'text/plain;charset=utf-8' });
    const filename = `${this.conversionResult.filename_base || 'drawing'}.nc`;
    this._triggerDownload(blob, filename);
  }

  _downloadDxfFile() {
    if (!this.conversionResult || !this.conversionResult.dxf_base64) return;
    const byteCharacters = atob(this.conversionResult.dxf_base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: 'application/dxf' });
    const filename = `${this.conversionResult.filename_base || 'drawing'}.dxf`;
    this._triggerDownload(blob, filename);
  }

  _triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  _openGcodeModal() {
    if (!this.conversionResult || !this.conversionResult.gcode) return;
    this.gcodeModalContent.textContent = this.conversionResult.gcode;
    this.gcodeModal.classList.remove('hidden');
  }

  _setBusy(busy) {
    this.generateBtn.disabled = busy;
    const labelSpan = this.generateBtn.querySelector('span');
    if (busy) {
      this.generateBtn.classList.add('opacity-70', 'cursor-not-allowed');
      if (labelSpan) {
        labelSpan.textContent = i18n.lang === 'vi' ? 'Đang tạo mã G-Code...' : 'Generating G-Code...';
      }
    } else {
      this.generateBtn.classList.remove('opacity-70', 'cursor-not-allowed');
      if (labelSpan) {
        labelSpan.textContent = i18n.t('btnGenerate');
      }
    }
  }

  _updatePlayButtonState() {
    const isPlaying = this.simulator && this.simulator.isPlaying;
    const playText = this.simPlayBtn.querySelector('span');
    if (playText) {
      playText.textContent = isPlaying ? i18n.t('simPause') : i18n.t('simPlay');
    } else {
      this.simPlayBtn.textContent = isPlaying ? i18n.t('simPause') : i18n.t('simPlay');
    }
  }

  _showStatus(message, type = 'info') {
    const colorClasses = {
      info: 'bg-blue-50 text-blue-700 border-blue-200',
      success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      warning: 'bg-amber-50 text-amber-700 border-amber-200',
      error: 'bg-rose-50 text-rose-700 border-rose-200'
    };

    this.statusBanner.className = `p-3 rounded-lg border text-sm transition-all duration-200 ${colorClasses[type] || colorClasses.info}`;
    this.statusBanner.textContent = message;
  }
}

// Bootstrap on DOM ready or immediately if already interactive/complete
function initApp() {
  if (!window._imageToGcodeApp) {
    window._imageToGcodeApp = new ImageToGCodeWebApp();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
