/**
 * Image Preview & Vision Analysis Inspector
 */

export class ImagePreviewViewer {
  constructor(canvasElement, onCoordUpdate) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.onCoordUpdate = onCoordUpdate;

    this.image = null;
    this.analysis = null;
    this.showTags = true;

    this.scale = 1.0;
    this.offsetX = 0.0;
    this.offsetY = 0.0;
    this.imgW = 0;
    this.imgH = 0;

    this._bindEvents();
    this._resizeCanvas();
  }

  _bindEvents() {
    window.addEventListener('resize', () => this._resizeCanvas());

    this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
    this.canvas.addEventListener('mouseleave', () => {
      if (this.onCoordUpdate) this.onCoordUpdate(null);
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

    this.render();
  }

  loadImage(fileOrBlob) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(fileOrBlob);
      const img = new Image();
      img.onload = () => {
        this.image = img;
        this.imgW = img.naturalWidth || img.width;
        this.imgH = img.naturalHeight || img.height;
        this.render();
        resolve(img);
      };
      img.onerror = (err) => reject(err);
      img.src = url;
    });
  }

  setAnalysis(analysisData) {
    this.analysis = analysisData;
    this.render();
  }

  setShowTags(show) {
    this.showTags = Boolean(show);
    this.render();
  }

  _onMouseMove(event) {
    if (!this.image || this.imgW <= 0 || this.imgH <= 0) return;

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;

    const imgX = (mouseX - this.offsetX) / this.scale;
    const imgY = (mouseY - this.offsetY) / this.scale;

    if (imgX >= 0 && imgX <= this.imgW && imgY >= 0 && imgY <= this.imgH) {
      let mmInfo = null;
      if (this.analysis && this.analysis.scale_factor && this.analysis.g54_origin_px) {
        const [xMin, yMax] = this.analysis.g54_origin_px;
        const sf = this.analysis.scale_factor;
        const mmX = (imgX - xMin) / sf;
        const mmY = (yMax - imgY) / sf;
        mmInfo = { mmX, mmY };
      }

      if (this.onCoordUpdate) {
        this.onCoordUpdate({
          pxX: Math.round(imgX),
          pxY: Math.round(imgY),
          ...mmInfo
        });
      }
    } else {
      if (this.onCoordUpdate) this.onCoordUpdate(null);
    }
  }

  render() {
    const ctx = this.ctx;
    const w = this.displayWidth;
    const h = this.displayHeight;

    ctx.clearRect(0, 0, w, h);

    if (!this.image) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px Inter, Segoe UI, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Select or drop a drawing image to inspect', w / 2, h / 2);
      return;
    }

    const margin = 12;
    const scale = Math.min(
      (w - 2 * margin) / Math.max(this.imgW, 1),
      (h - 2 * margin) / Math.max(this.imgH, 1),
      1.0
    );
    this.scale = scale;

    const dispW = Math.max(1, this.imgW * scale);
    const dispH = Math.max(1, this.imgH * scale);
    this.offsetX = (w - dispW) / 2.0;
    this.offsetY = (h - dispH) / 2.0;

    // Draw base image
    ctx.drawImage(this.image, this.offsetX, this.offsetY, dispW, dispH);

    // Draw visual detection tags
    if (this.showTags && this.analysis) {
      this._drawDetectionTags();
    }
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

      // Badge label
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

      ctx.strokeStyle = '#dc2626';
      ctx.lineWidth = 2;
      ctx.setLineDash([]);

      // Circle
      ctx.beginPath();
      ctx.arc(cox, coy, 6, 0, 2 * Math.PI);
      ctx.stroke();

      // Crosshair lines
      ctx.beginPath();
      ctx.moveTo(cox - 10, coy);
      ctx.lineTo(cox + 10, coy);
      ctx.moveTo(cox, coy - 10);
      ctx.lineTo(cox, coy + 10);
      ctx.stroke();

      // Text label
      ctx.fillStyle = '#dc2626';
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('G54 (0,0)', cox + 8, coy + 6);
    }
  }
}

