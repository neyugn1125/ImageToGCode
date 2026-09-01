/**
 * Image & DXF CAD Vector Preview Inspector
 * Supports interactive Zoom In/Out, Pan/Drag, Grid, and CNC CAM X/Y Axes
 */

const AXIS_X_COLOR = '#ef4444'; // Red for +X
const AXIS_Y_COLOR = '#10b981'; // Green for +Y
const G54_TARGET_COLOR = '#dc2626';

export class ImagePreviewViewer {
  constructor(canvasElement, onCoordUpdate) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.onCoordUpdate = onCoordUpdate;

    this.image = null;
    this.isDxf = false;
    this.dxfFilename = '';
    this.analysis = null;

    // View Options
    this.showTags = true;
    this.showGrid = true;
    this.showAxes = true;

    // Transform State (Zoom & Pan)
    this.scale = 1.0;
    this.baseScale = 1.0;
    this.offsetX = 0.0;
    this.offsetY = 0.0;
    this.imgW = 0;
    this.imgH = 0;

    // Drag / Pan State
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.dragStartOffsetX = 0;
    this.dragStartOffsetY = 0;
    this.hasCustomTransform = false;

    this.canvas.style.cursor = 'crosshair';

    this._bindEvents();
    this._resizeCanvas();
  }

  _bindEvents() {
    window.addEventListener('resize', () => this._resizeCanvas());

    // Mouse Zoom (Wheel)
    this.canvas.addEventListener('wheel', (e) => this._onZoom(e), { passive: false });

    // Mouse Drag / Pan
    this.canvas.addEventListener('mousedown', (e) => this._onDragStart(e));
    window.addEventListener('mousemove', (e) => this._onDragMove(e));
    window.addEventListener('mouseup', (e) => this._onDragEnd(e));

    // Double-click to Fit View
    this.canvas.addEventListener('dblclick', () => this.fitView());

    // Leave canvas
    this.canvas.addEventListener('mouseleave', () => {
      if (!this.isDragging && this.onCoordUpdate) {
        this.onCoordUpdate(null);
      }
    });
  }

  _resizeCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(100, Math.floor(rect.width));
    const h = Math.max(100, Math.floor(rect.height));

    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;

    this.ctx.resetTransform();
    this.ctx.scale(dpr, dpr);
    this.displayWidth = w;
    this.displayHeight = h;

    if (!this.hasCustomTransform) {
      this.fitView();
    } else {
      this.render();
    }
  }

  loadImage(fileOrBlob) {
    this.isDxf = false;
    this.hasCustomTransform = false;
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(fileOrBlob);
      const img = new Image();
      img.onload = () => {
        this.image = img;
        this.imgW = img.naturalWidth || img.width;
        this.imgH = img.naturalHeight || img.height;
        this.fitView();
        resolve(img);
      };
      img.onerror = (err) => reject(err);
      img.src = url;
    });
  }

  loadDxf(file) {
    this.isDxf = true;
    this.image = null;
    this.dxfFilename = file.name;
    this.hasCustomTransform = false;
    this.fitView();
  }

  setAnalysis(analysisData) {
    this.analysis = analysisData;
    if (!this.hasCustomTransform) {
      this.fitView();
    } else {
      this.render();
    }
  }

  setShowTags(show) {
    this.showTags = Boolean(show);
    this.render();
  }

  setShowGrid(show) {
    this.showGrid = Boolean(show);
    this.render();
  }

  setShowAxes(show) {
    this.showAxes = Boolean(show);
    this.render();
  }

  fitView() {
    const w = this.displayWidth;
    const h = this.displayHeight;
    this.hasCustomTransform = false;

    if (this.isDxf) {
      const dxf = this.analysis ? this.analysis.dxf_preview : null;
      if (dxf) {
        const margin = 35;
        const rangeX = Math.max(1.0, dxf.max_x - dxf.min_x);
        const rangeY = Math.max(1.0, dxf.max_y - dxf.min_y);
        this.scale = Math.min((w - 2 * margin) / rangeX, (h - 2 * margin) / rangeY);
        this.baseScale = this.scale;
        const centerX = (dxf.min_x + dxf.max_x) / 2;
        const centerY = (dxf.min_y + dxf.max_y) / 2;
        this.offsetX = w / 2 - centerX * this.scale;
        this.offsetY = h / 2 + centerY * this.scale;
      } else {
        this.scale = 1.0;
        this.baseScale = 1.0;
        this.offsetX = w / 2;
        this.offsetY = h / 2;
      }
    } else if (this.image && this.imgW > 0 && this.imgH > 0) {
      const margin = 16;
      this.scale = Math.min((w - 2 * margin) / this.imgW, (h - 2 * margin) / this.imgH);
      this.baseScale = this.scale;
      const dispW = this.imgW * this.scale;
      const dispH = this.imgH * this.scale;
      this.offsetX = (w - dispW) / 2.0;
      this.offsetY = (h - dispH) / 2.0;
    } else {
      this.scale = 1.0;
      this.baseScale = 1.0;
      this.offsetX = 0;
      this.offsetY = 0;
    }

    this.render();
  }

  zoomIn(factor = 1.25) {
    this._applyZoomCenter(factor);
  }

  zoomOut(factor = 0.8) {
    this._applyZoomCenter(factor);
  }

  _applyZoomCenter(factor) {
    const cx = this.displayWidth / 2;
    const cy = this.displayHeight / 2;
    this._zoomAtPoint(cx, cy, factor);
  }

  _zoomAtPoint(cx, cy, factor) {
    const newScale = Math.min(Math.max(this.scale * factor, 0.05), 100.0);
    this.hasCustomTransform = true;

    if (this.isDxf) {
      const wx = (cx - this.offsetX) / this.scale;
      const wy = (this.offsetY - cy) / this.scale;
      this.scale = newScale;
      this.offsetX = cx - wx * newScale;
      this.offsetY = cy + wy * newScale;
    } else {
      const imgX = (cx - this.offsetX) / this.scale;
      const imgY = (cy - this.offsetY) / this.scale;
      this.scale = newScale;
      this.offsetX = cx - imgX * newScale;
      this.offsetY = cy - imgY * newScale;
    }

    this.render();
  }

  _onZoom(event) {
    event.preventDefault();
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.15 : 0.87;
    this._zoomAtPoint(mouseX, mouseY, factor);
  }

  _onDragStart(event) {
    if (event.button !== 0 && event.button !== 1) return; // Left or Middle click
    this.isDragging = true;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    this.dragStartOffsetX = this.offsetX;
    this.dragStartOffsetY = this.offsetY;
    this.canvas.style.cursor = 'grabbing';
  }

  _onDragMove(event) {
    if (this.isDragging) {
      this.hasCustomTransform = true;
      const dx = event.clientX - this.dragStartX;
      const dy = event.clientY - this.dragStartY;
      this.offsetX = this.dragStartOffsetX + dx;
      this.offsetY = this.dragStartOffsetY + dy;
      this.render();
    }
    this._updateCoordDisplay(event);
  }

  _onDragEnd(event) {
    if (this.isDragging) {
      this.isDragging = false;
      this.canvas.style.cursor = 'crosshair';
    }
  }

  _updateCoordDisplay(event) {
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;

    if (mouseX < 0 || mouseX > this.displayWidth || mouseY < 0 || mouseY > this.displayHeight) {
      if (this.onCoordUpdate) this.onCoordUpdate(null);
      return;
    }

    if (this.isDxf && this.analysis && this.analysis.dxf_preview) {
      const mmX = (mouseX - this.offsetX) / this.scale;
      const mmY = (this.offsetY - mouseY) / this.scale;

      if (this.onCoordUpdate) {
        this.onCoordUpdate({
          pxX: Math.round(mouseX),
          pxY: Math.round(mouseY),
          mmX: Number(mmX.toFixed(2)),
          mmY: Number(mmY.toFixed(2))
        });
      }
      return;
    }

    if (!this.image || this.imgW <= 0 || this.imgH <= 0) {
      if (this.onCoordUpdate) this.onCoordUpdate(null);
      return;
    }

    const imgX = (mouseX - this.offsetX) / this.scale;
    const imgY = (mouseY - this.offsetY) / this.scale;

    let mmInfo = null;
    if (this.analysis && this.analysis.scale_factor && this.analysis.g54_origin_px) {
      const [xMin, yMax] = this.analysis.g54_origin_px;
      const sf = this.analysis.scale_factor;
      const mmX = (imgX - xMin) / sf;
      const mmY = (yMax - imgY) / sf;
      mmInfo = { mmX: Number(mmX.toFixed(2)), mmY: Number(mmY.toFixed(2)) };
    }

    if (this.onCoordUpdate) {
      this.onCoordUpdate({
        pxX: Math.round(imgX),
        pxY: Math.round(imgY),
        ...mmInfo
      });
    }
  }

  render() {
    const ctx = this.ctx;
    const w = this.displayWidth;
    const h = this.displayHeight;

    ctx.clearRect(0, 0, w, h);

    if (!this.image && !this.isDxf) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px Inter, Segoe UI, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Select or drop a drawing image or DXF file to inspect', w / 2, h / 2);
      return;
    }

    if (this.isDxf) {
      this._renderDxfPreview(w, h);
      return;
    }

    // 1. Draw Raster Image
    this._renderRasterPreview(w, h);
  }

  _renderRasterPreview(w, h) {
    const ctx = this.ctx;
    const dispW = this.imgW * this.scale;
    const dispH = this.imgH * this.scale;

    // Technical background
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, w, h);

    // Raster base image
    ctx.drawImage(this.image, this.offsetX, this.offsetY, dispW, dispH);

    // Image frame border
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.strokeRect(this.offsetX, this.offsetY, dispW, dispH);

    // 2. Draw Grid & Axes for Calibrated / Uncalibrated Raster Image
    if (this.showGrid || this.showAxes) {
      this._drawRasterGridAndAxes(w, h);
    }

    // 3. Draw Detection Overlays
    if (this.showTags && this.analysis) {
      this._drawDetectionTags();
    }

    // Mini Navigation / Zoom Badge
    this._drawZoomBadge();
  }

  _drawRasterGridAndAxes(w, h) {
    const ctx = this.ctx;
    const analysis = this.analysis;

    if (analysis && analysis.g54_origin_px && analysis.scale_factor) {
      const [oxPx, oyPx] = analysis.g54_origin_px;
      const sf = analysis.scale_factor;
      const originCx = oxPx * this.scale + this.offsetX;
      const originCy = oyPx * this.scale + this.offsetY;

      // Metric Grid
      if (this.showGrid) {
        const mmStep = this._calculateAdaptiveGridStep(this.scale * sf);
        const pxStep = mmStep * sf * this.scale;

        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        ctx.setLineDash([]);

        // Vertical mm grid lines
        const startXIdx = Math.floor((0 - originCx) / pxStep) - 1;
        const endXIdx = Math.ceil((w - originCx) / pxStep) + 1;
        for (let i = startXIdx; i <= endXIdx; i++) {
          const cx = originCx + i * pxStep;
          if (cx >= 0 && cx <= w) {
            ctx.beginPath();
            ctx.moveTo(cx, 0);
            ctx.lineTo(cx, h);
            ctx.stroke();

            if (i !== 0) {
              ctx.fillStyle = '#94a3b8';
              ctx.font = '9px Inter, Segoe UI, sans-serif';
              ctx.textAlign = 'left';
              ctx.textBaseline = 'bottom';
              ctx.fillText((i * mmStep).toFixed(0), cx + 2, h - 2);
            }
          }
        }

        // Horizontal mm grid lines (Y goes UP in CNC)
        const startYIdx = Math.floor((0 - originCy) / -pxStep) - 1;
        const endYIdx = Math.ceil((h - originCy) / -pxStep) + 1;
        for (let j = startYIdx; j <= endYIdx; j++) {
          const cy = originCy - j * pxStep;
          if (cy >= 0 && cy <= h) {
            ctx.beginPath();
            ctx.moveTo(0, cy);
            ctx.lineTo(w, cy);
            ctx.stroke();

            if (j !== 0) {
              ctx.fillStyle = '#94a3b8';
              ctx.font = '9px Inter, Segoe UI, sans-serif';
              ctx.textAlign = 'left';
              ctx.textBaseline = 'top';
              ctx.fillText((j * mmStep).toFixed(0), 4, cy + 2);
            }
          }
        }
      }

      // Main CNC Axes (+X Red, +Y Green)
      if (this.showAxes) {
        // +X Axis
        if (originCy >= 0 && originCy <= h) {
          ctx.strokeStyle = AXIS_X_COLOR;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(0, originCy);
          ctx.lineTo(w, originCy);
          ctx.stroke();

          ctx.fillStyle = AXIS_X_COLOR;
          ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
          ctx.textAlign = 'right';
          ctx.textBaseline = 'bottom';
          ctx.fillText('+X (mm)', w - 8, originCy - 4);
        }

        // +Y Axis
        if (originCx >= 0 && originCx <= w) {
          ctx.strokeStyle = AXIS_Y_COLOR;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(originCx, 0);
          ctx.lineTo(originCx, h);
          ctx.stroke();

          ctx.fillStyle = AXIS_Y_COLOR;
          ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText('+Y (mm)', originCx + 6, 8);
        }
      }
    }
  }

  _renderDxfPreview(w, h) {
    const ctx = this.ctx;
    const dxf = this.analysis ? this.analysis.dxf_preview : null;

    // Background technical canvas
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, w, h);

    if (!dxf) {
      ctx.fillStyle = '#64748b';
      ctx.font = '13px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`Loading DXF vector geometry for ${this.dxfFilename}...`, w / 2, h / 2);
      return;
    }

    const toCanvasX = (x) => x * this.scale + this.offsetX;
    const toCanvasY = (y) => this.offsetY - y * this.scale;

    // 1. Adaptive Metric Grid
    if (this.showGrid) {
      const gridStep = this._calculateAdaptiveGridStep(this.scale);
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.setLineDash([]);

      const originCx = this.offsetX;
      const originCy = this.offsetY;

      const startXIdx = Math.floor((0 - originCx) / (gridStep * this.scale)) - 1;
      const endXIdx = Math.ceil((w - originCx) / (gridStep * this.scale)) + 1;
      for (let i = startXIdx; i <= endXIdx; i++) {
        const wx = i * gridStep;
        const cx = toCanvasX(wx);
        if (cx >= 0 && cx <= w) {
          ctx.beginPath();
          ctx.moveTo(cx, 0);
          ctx.lineTo(cx, h);
          ctx.stroke();

          if (i !== 0) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '9px Inter, Segoe UI, sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText(gridStep >= 1 ? wx.toFixed(0) : wx.toFixed(1), cx + 2, h - 2);
          }
        }
      }

      const startYIdx = Math.floor((0 - originCy) / (-gridStep * this.scale)) - 1;
      const endYIdx = Math.ceil((h - originCy) / (-gridStep * this.scale)) + 1;
      for (let j = startYIdx; j <= endYIdx; j++) {
        const wy = j * gridStep;
        const cy = toCanvasY(wy);
        if (cy >= 0 && cy <= h) {
          ctx.beginPath();
          ctx.moveTo(0, cy);
          ctx.lineTo(w, cy);
          ctx.stroke();

          if (j !== 0) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '9px Inter, Segoe UI, sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'top';
            ctx.fillText(gridStep >= 1 ? wy.toFixed(0) : wy.toFixed(1), 4, cy + 2);
          }
        }
      }
    }

    // 2. Main Axes (+X Red, +Y Green)
    if (this.showAxes) {
      const originCx = this.offsetX;
      const originCy = this.offsetY;

      // +X Axis
      if (originCy >= 0 && originCy <= h) {
        ctx.strokeStyle = AXIS_X_COLOR;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(0, originCy);
        ctx.lineTo(w, originCy);
        ctx.stroke();

        ctx.fillStyle = AXIS_X_COLOR;
        ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText('+X (mm)', w - 8, originCy - 4);
      }

      // +Y Axis
      if (originCx >= 0 && originCx <= w) {
        ctx.strokeStyle = AXIS_Y_COLOR;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(originCx, 0);
        ctx.lineTo(originCx, h);
        ctx.stroke();

        ctx.fillStyle = AXIS_Y_COLOR;
        ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('+Y (mm)', originCx + 6, 8);
      }
    }

    // 3. Draw Bounding Envelope Box (Blue Dashed)
    if (this.showTags) {
      const bx1 = toCanvasX(dxf.min_x);
      const by1 = toCanvasY(dxf.max_y);
      const bx2 = toCanvasX(dxf.max_x);
      const by2 = toCanvasY(dxf.min_y);

      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(bx1, by1, bx2 - bx1, by2 - by1);
      ctx.setLineDash([]);

      // Dimensions label
      ctx.fillStyle = '#2563eb';
      ctx.font = 'bold 10px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(`${dxf.width_mm.toFixed(1)} x ${dxf.height_mm.toFixed(1)} mm`, bx1 + 4, by1 - 4);
    }

    // 4. Draw DXF Vector Geometry (Lines, Circles, Arcs, Polylines)
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 1.8;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Lines
    if (dxf.lines && dxf.lines.length > 0) {
      ctx.beginPath();
      for (const line of dxf.lines) {
        const [x1, y1] = line.start;
        const [x2, y2] = line.end;
        ctx.moveTo(toCanvasX(x1), toCanvasY(y1));
        ctx.lineTo(toCanvasX(x2), toCanvasY(y2));
      }
      ctx.stroke();
    }

    // Circles
    if (dxf.circles && dxf.circles.length > 0) {
      for (const circle of dxf.circles) {
        const [cx, cy] = circle.center;
        const rPx = circle.radius * this.scale;
        ctx.beginPath();
        ctx.arc(toCanvasX(cx), toCanvasY(cy), rPx, 0, 2 * Math.PI);
        ctx.stroke();
      }
    }

    // Arcs
    if (dxf.arcs && dxf.arcs.length > 0) {
      for (const arc of dxf.arcs) {
        const [cx, cy] = arc.center;
        const rPx = arc.radius * this.scale;
        const startRad = (-arc.start_angle * Math.PI) / 180;
        const endRad = (-arc.end_angle * Math.PI) / 180;
        ctx.beginPath();
        ctx.arc(toCanvasX(cx), toCanvasY(cy), rPx, startRad, endRad, true);
        ctx.stroke();
      }
    }

    // Polylines
    if (dxf.polylines && dxf.polylines.length > 0) {
      for (const poly of dxf.polylines) {
        const pts = poly.points;
        if (pts.length < 2) continue;
        ctx.beginPath();
        ctx.moveTo(toCanvasX(pts[0][0]), toCanvasY(pts[0][1]));
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(toCanvasX(pts[i][0]), toCanvasY(pts[i][1]));
        }
        if (poly.closed) {
          ctx.closePath();
        }
        ctx.stroke();
      }
    }

    // 5. G54 Origin Crosshair (Red Target)
    if (this.showTags) {
      const g54X = toCanvasX(0);
      const g54Y = toCanvasY(0);

      ctx.strokeStyle = G54_TARGET_COLOR;
      ctx.lineWidth = 2;
      ctx.setLineDash([]);

      ctx.beginPath();
      ctx.arc(g54X, g54Y, 6, 0, 2 * Math.PI);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(g54X - 10, g54Y);
      ctx.lineTo(g54X + 10, g54Y);
      ctx.moveTo(g54X, g54Y - 10);
      ctx.lineTo(g54X, g54Y + 10);
      ctx.stroke();

      ctx.fillStyle = G54_TARGET_COLOR;
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('G54 (0,0)', g54X + 8, g54Y + 6);
    }

    // Badge
    this._drawZoomBadge('DXF Vector 1:1 mm');
  }

  _calculateAdaptiveGridStep(pixelsPerUnit) {
    const minPixelSpacing = 35;
    const targetUnitStep = minPixelSpacing / Math.max(pixelsPerUnit, 1e-4);
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
    for (const s of steps) {
      if (s >= targetUnitStep) return s;
    }
    return 1000;
  }

  _drawZoomBadge(extraLabel = null) {
    const ctx = this.ctx;
    const zoomPct = Math.round((this.scale / (this.baseScale || 1.0)) * 100);
    const text = extraLabel ? `${extraLabel} | ${zoomPct}%` : `Zoom: ${zoomPct}%`;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(8, 8, Math.max(100, text.length * 7 + 16), 22);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 10px Inter, Segoe UI, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 14, 19);
  }

  _imgToCanvas(pxX, pxY) {
    return [
      pxX * this.scale + this.offsetX,
      pxY * this.scale + this.offsetY
    ];
  }

  _drawDetectionTags() {
    const ctx = this.ctx;
    const analysis = this.analysis;

    // 1. Calibration square marker (Bright Green)
    if (analysis.calibration_bbox_px) {
      const [cx, cy, cw, ch] = analysis.calibration_bbox_px;
      const [c1x, c1y] = this._imgToCanvas(cx, cy);
      const [c2x, c2y] = this._imgToCanvas(cx + cw, cy + ch);
      const boxW = c2x - c1x;
      const boxH = c2y - c1y;

      ctx.strokeStyle = '#16a34a';
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.strokeRect(c1x, c1y, boxW, boxH);

      const tagText = '10x10 mm Calib';
      ctx.fillStyle = '#16a34a';
      ctx.fillRect(c1x, c1y - 18, 90, 18);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 10px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(tagText, c1x + 4, c1y - 9);
    }

    // 2. Machining envelope bounding box (Blue dashed)
    if (analysis.machining_bbox_px) {
      const [mx1, my1, mx2, my2] = analysis.machining_bbox_px;
      const [b1x, b1y] = this._imgToCanvas(mx1, my1);
      const [b2x, b2y] = this._imgToCanvas(mx2, my2);

      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(b1x, b1y, b2x - b1x, b2y - b1y);
      ctx.setLineDash([]);
    }

    // 3. G54 Origin point (Red Crosshair Target)
    if (analysis.g54_origin_px) {
      const [ox, oy] = analysis.g54_origin_px;
      const [cox, coy] = this._imgToCanvas(ox, oy);

      ctx.strokeStyle = G54_TARGET_COLOR;
      ctx.lineWidth = 2;
      ctx.setLineDash([]);

      ctx.beginPath();
      ctx.arc(cox, coy, 6, 0, 2 * Math.PI);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(cox - 10, coy);
      ctx.lineTo(cox + 10, coy);
      ctx.moveTo(cox, coy - 10);
      ctx.lineTo(cox, coy + 10);
      ctx.stroke();

      ctx.fillStyle = G54_TARGET_COLOR;
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('G54 (0,0)', cox + 8, coy + 6);
    }
  }
}
