import { i18n } from './i18n.js';

const SIM_GRID_COLOR = '#e2e8f0';
const SIM_AXIS_X_COLOR = '#ef4444';
const SIM_AXIS_Y_COLOR = '#22c55e';
const SIM_RAPID_COLOR = '#94a3b8';
const SIM_LINEAR_COLOR = '#16a34a';
const SIM_ARC_CW_COLOR = '#2563eb';
const SIM_ARC_CCW_COLOR = '#ea580c';
const SIM_TRAVELED_COLOR = '#f59e0b';
const SIM_TOOL_OUTLINE = '#c2410c';
const SIM_TOOL_FILL = 'rgba(255, 237, 213, 0.7)';
const SIM_TOOL_CENTER = '#0f172a';
const RAPID_DISPLAY_FEED = 3000.0;

export class CncSimulator {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.onStatusUpdate = options.onStatusUpdate || null;
    this.onProgressUpdate = options.onProgressUpdate || null;

    // View Transforms
    this.scale = 1.0;
    this.baseScale = 1.0;
    this.offsetX = 0.0;
    this.offsetY = 0.0;
    this.displayWidth = 0;
    this.displayHeight = 0;

    // Pan state
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;

    // Toolpath & Simulation state
    this.segments = [];
    this.frames = [];
    this.totalTime = 0.0;
    this.currentTime = 0.0;
    this.isPlaying = false;
    this.playbackSpeed = 5.0;
    this.toolDiameter = 3.0;
    this.animFrameId = null;
    this.lastTickTime = 0;

    // View options
    this.showGrid = true;
    this.showRapids = true;
    this.showArrows = true;
    this.showCutter = true;

    this._bindEvents();
    this._resizeCanvas();
  }

  _bindEvents() {
    window.addEventListener('resize', () => this._resizeCanvas());

    // Mouse zoom
    this.canvas.addEventListener('wheel', (e) => this._onZoom(e), { passive: false });

    // Mouse pan
    this.canvas.addEventListener('mousedown', (e) => this._onDragStart(e));
    window.addEventListener('mousemove', (e) => this._onDragMove(e));
    window.addEventListener('mouseup', (e) => this._onDragEnd(e));
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

    if (this.segments.length > 0) {
      this.render();
    } else {
      this._renderEmpty();
    }
  }

  setSegments(segments, toolDiameter = 3.0) {
    this.pause();
    this.segments = segments || [];
    this.toolDiameter = Number(toolDiameter) || 3.0;
    this.currentTime = 0.0;

    this._buildTimeline();
    this.fitView();
    this.render();
  }

  setToolDiameter(dia) {
    this.toolDiameter = Math.max(0.1, Number(dia) || 3.0);
    this.render();
  }

  setViewToggles({ showGrid, showRapids, showArrows, showCutter }) {
    if (showGrid !== undefined) this.showGrid = Boolean(showGrid);
    if (showRapids !== undefined) this.showRapids = Boolean(showRapids);
    if (showArrows !== undefined) this.showArrows = Boolean(showArrows);
    if (showCutter !== undefined) this.showCutter = Boolean(showCutter);
    this.render();
  }

  fitView() {
    if (!this.segments || this.segments.length === 0) return;

    const allPoints = this.segments.flatMap((s) => s.points);
    if (allPoints.length === 0) return;

    const xs = allPoints.map((p) => p[0]);
    const ys = allPoints.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const widthMm = Math.max(maxX - minX, 1e-4);
    const heightMm = Math.max(maxY - minY, 1e-4);
    const margin = 35;

    this.baseScale = Math.min(
      (this.displayWidth - 2 * margin) / widthMm,
      (this.displayHeight - 2 * margin) / heightMm
    );
    this.scale = this.baseScale;

    const centerX = (minX + maxX) / 2.0;
    const centerY = (minY + maxY) / 2.0;
    this.offsetX = this.displayWidth / 2.0 - centerX * this.scale;
    this.offsetY = this.displayHeight / 2.0 + centerY * this.scale;
  }

  _buildTimeline() {
    this.frames = [];
    this.totalTime = 0.0;
    if (!this.segments || this.segments.length === 0) return;

    let timeAcc = 0.0;
    let prevPoint = this.segments[0].points[0] || [0, 0];

    // Initial frame
    this.frames.push({
      time: 0.0,
      x: prevPoint[0],
      y: prevPoint[1],
      z: 50.0,
      kind: 'idle',
      feed: 0.0
    });

    for (const segment of this.segments) {
      const feed = segment.kind === 'rapid' ? RAPID_DISPLAY_FEED : Math.max(1.0, segment.feed);
      const speedMmPerSec = feed / 60.0;

      for (const pt of segment.points) {
        const dist = Math.hypot(pt[0] - prevPoint[0], pt[1] - prevPoint[1]);
        const moveTime = dist / speedMmPerSec;
        timeAcc += moveTime;

        this.frames.push({
          time: timeAcc,
          x: pt[0],
          y: pt[1],
          z: segment.z_depth !== undefined ? segment.z_depth : 0.0,
          kind: segment.kind,
          feed: segment.feed
        });
        prevPoint = pt;
      }
    }

    this.totalTime = Math.max(timeAcc, 0.01);
  }

  _onZoom(e) {
    if (this.segments.length === 0) return;
    e.preventDefault();

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomingIn = e.deltaY < 0;
    const factor = zoomingIn ? 1.15 : 1 / 1.15;
    const newScale = Math.min(this.baseScale * 40.0, Math.max(this.baseScale * 0.1, this.scale * factor));

    const worldX = (mouseX - this.offsetX) / this.scale;
    const worldY = (this.offsetY - mouseY) / this.scale;

    this.scale = newScale;
    this.offsetX = mouseX - worldX * newScale;
    this.offsetY = mouseY + worldY * newScale;

    this.render();
  }

  _onDragStart(e) {
    if (this.segments.length === 0) return;
    this.isDragging = true;
    this.dragStartX = e.clientX;
    this.dragStartY = e.clientY;
    this.canvas.classList.add('panning');
  }

  _onDragMove(e) {
    if (!this.isDragging) return;
    const dx = e.clientX - this.dragStartX;
    const dy = e.clientY - this.dragStartY;
    this.dragStartX = e.clientX;
    this.dragStartY = e.clientY;

    this.offsetX += dx;
    this.offsetY += dy;
    this.render();
  }

  _onDragEnd() {
    this.isDragging = false;
    this.canvas.classList.remove('panning');
  }

  // Playback Control
  play() {
    if (this.segments.length === 0) return;
    if (this.currentTime >= this.totalTime) {
      this.currentTime = 0.0;
    }
    this.isPlaying = true;
    this.lastTickTime = performance.now();
    this._loop();
  }

  pause() {
    this.isPlaying = false;
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  togglePlay() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  stepForward() {
    this.pause();
    for (const frame of this.frames) {
      if (frame.time > this.currentTime + 1e-4) {
        this.currentTime = frame.time;
        break;
      }
    }
    this.render();
  }

  stepBackward() {
    this.pause();
    let prevTime = 0.0;
    for (const frame of this.frames) {
      if (frame.time < this.currentTime - 1e-4) {
        prevTime = frame.time;
      } else {
        break;
      }
    }
    this.currentTime = prevTime;
    this.render();
  }

  restart() {
    this.pause();
    this.currentTime = 0.0;
    this.render();
  }

  seek(fraction) {
    this.pause();
    this.currentTime = Math.max(0.0, Math.min(1.0, fraction)) * this.totalTime;
    this.render();
  }

  setSpeed(multiplier) {
    this.playbackSpeed = Math.max(1.0, Math.min(50.0, Number(multiplier) || 5.0));
  }

  _loop() {
    if (!this.isPlaying) return;

    const now = performance.now();
    const dt = (now - this.lastTickTime) / 1000.0;
    this.lastTickTime = now;

    this.currentTime = Math.min(this.totalTime, this.currentTime + dt * this.playbackSpeed);
    this.render();

    if (this.currentTime >= this.totalTime) {
      this.pause();
      return;
    }

    this.animFrameId = requestAnimationFrame(() => this._loop());
  }

  _toCanvas(pt) {
    return [
      pt[0] * this.scale + this.offsetX,
      -pt[1] * this.scale + this.offsetY
    ];
  }

  _renderEmpty() {
    const ctx = this.ctx;
    const w = this.displayWidth;
    const h = this.displayHeight;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '14px Inter, Segoe UI, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(i18n.t('simDefaultText'), w / 2, h / 2);
  }

  render() {
    const ctx = this.ctx;
    const w = this.displayWidth;
    const h = this.displayHeight;

    ctx.clearRect(0, 0, w, h);

    if (this.segments.length === 0) {
      this._renderEmpty();
      return;
    }

    // 1. Grid & Axes
    if (this.showGrid) {
      this._drawGrid(w, h);
    }

    // 2. Toolpath Segments
    this._drawToolpathSegments();

    // 3. Dynamic Tool Position & Trail
    this._drawDynamicTool();
  }

  _drawGrid(w, h) {
    const ctx = this.ctx;
    if (this.scale <= 1e-4) return;

    const targetPx = 60.0;
    const rawStep = targetPx / this.scale;
    const steps = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0];
    let gridStep = steps[steps.length - 1];
    for (const s of steps) {
      if (s >= rawStep) {
        gridStep = s;
        break;
      }
    }

    const minWorldX = (0 - this.offsetX) / this.scale;
    const maxWorldX = (w - this.offsetX) / this.scale;
    const minWorldY = (this.offsetY - h) / this.scale;
    const maxWorldY = (this.offsetY - 0) / this.scale;

    const startXIdx = Math.floor(minWorldX / gridStep);
    const endXIdx = Math.ceil(maxWorldX / gridStep);
    const startYIdx = Math.floor(minWorldY / gridStep);
    const endYIdx = Math.ceil(maxWorldY / gridStep);

    ctx.strokeStyle = SIM_GRID_COLOR;
    ctx.lineWidth = 1;
    ctx.setLineDash([]);

    // Vertical grid lines
    for (let i = startXIdx; i <= endXIdx; i++) {
      const wx = i * gridStep;
      const cx = wx * this.scale + this.offsetX;
      if (cx >= 0 && cx <= w) {
        ctx.beginPath();
        ctx.moveTo(cx, 0);
        ctx.lineTo(cx, h);
        ctx.stroke();

        if (i !== 0 && Math.abs(wx) >= 1e-4) {
          ctx.fillStyle = '#94a3b8';
          ctx.font = '10px Inter, Segoe UI, sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'bottom';
          ctx.fillText(gridStep >= 1 ? wx.toFixed(0) : wx.toFixed(1), cx + 3, h - 4);
        }
      }
    }

    // Horizontal grid lines
    for (let i = startYIdx; i <= endYIdx; i++) {
      const wy = i * gridStep;
      const cy = -wy * this.scale + this.offsetY;
      if (cy >= 0 && cy <= h) {
        ctx.beginPath();
        ctx.moveTo(0, cy);
        ctx.lineTo(w, cy);
        ctx.stroke();

        if (i !== 0 && Math.abs(wy) >= 1e-4) {
          ctx.fillStyle = '#94a3b8';
          ctx.font = '10px Inter, Segoe UI, sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(gridStep >= 1 ? wy.toFixed(0) : wy.toFixed(1), 6, cy + 3);
        }
      }
    }

    // Main Axes G54
    const originCx = this.offsetX;
    const originCy = this.offsetY;

    // +X Axis (Red)
    if (originCy >= 0 && originCy <= h) {
      ctx.strokeStyle = SIM_AXIS_X_COLOR;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, originCy);
      ctx.lineTo(w, originCy);
      ctx.stroke();

      ctx.fillStyle = SIM_AXIS_X_COLOR;
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText('+X (mm)', w - 8, originCy - 4);
    }

    // +Y Axis (Green)
    if (originCx >= 0 && originCx <= w) {
      ctx.strokeStyle = SIM_AXIS_Y_COLOR;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(originCx, 0);
      ctx.lineTo(originCx, h);
      ctx.stroke();

      ctx.fillStyle = SIM_AXIS_Y_COLOR;
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('+Y (mm)', originCx + 6, 8);
    }

    // G54 Target Origin Icon
    if (originCx >= 0 && originCx <= w && originCy >= 0 && originCy <= h) {
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(originCx, originCy, 5, 0, 2 * Math.PI);
      ctx.stroke();

      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 11px Inter, Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('G54 (0,0)', originCx + 7, originCy + 7);
    }
  }

  _drawToolpathSegments() {
    const ctx = this.ctx;

    for (const segment of this.segments) {
      if (segment.points.length < 2) continue;

      if (segment.kind === 'rapid') {
        if (!this.showRapids) continue;
        ctx.strokeStyle = SIM_RAPID_COLOR;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
      } else if (segment.kind === 'arc_cw') {
        ctx.strokeStyle = SIM_ARC_CW_COLOR;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
      } else if (segment.kind === 'arc_ccw') {
        ctx.strokeStyle = SIM_ARC_CCW_COLOR;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
      } else {
        ctx.strokeStyle = SIM_LINEAR_COLOR;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
      }

      ctx.beginPath();
      const [startCx, startCy] = this._toCanvas(segment.points[0]);
      ctx.moveTo(startCx, startCy);

      for (let i = 1; i < segment.points.length; i++) {
        const [cx, cy] = this._toCanvas(segment.points[i]);
        ctx.lineTo(cx, cy);
      }
      ctx.stroke();

      // Draw direction chevrons
      if (this.showArrows && segment.kind !== 'rapid') {
        this._drawDirectionChevrons(segment.points, ctx.strokeStyle);
      }
    }

    // Start Node (Green) and End Node (Red)
    if (this.segments.length > 0) {
      const [sx, sy] = this._toCanvas(this.segments[0].points[0]);
      ctx.fillStyle = '#16a34a';
      ctx.beginPath();
      ctx.arc(sx, sy, 4, 0, 2 * Math.PI);
      ctx.fill();

      const lastSeg = this.segments[this.segments.length - 1];
      const [ex, ey] = this._toCanvas(lastSeg.points[lastSeg.points.length - 1]);
      ctx.fillStyle = '#dc2626';
      ctx.beginPath();
      ctx.arc(ex, ey, 4, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  _drawDirectionChevrons(points, color) {
    const ctx = this.ctx;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);

    for (let i = 0; i < points.length - 1; i++) {
      const [cx1, cy1] = this._toCanvas(points[i]);
      const [cx2, cy2] = this._toCanvas(points[i + 1]);

      const dx = cx2 - cx1;
      const dy = cy2 - cy1;
      const length = Math.hypot(dx, dy);
      if (length < 24.0) continue;

      const mx = (cx1 + cx2) / 2.0;
      const my = (cy1 + cy2) / 2.0;
      const ux = dx / length;
      const uy = dy / length;
      const nx = -uy;
      const ny = ux;

      const arrowLen = 5.0;
      const arrowW = 3.5;

      const tipX = mx + ux * (arrowLen * 0.5);
      const tipY = my + uy * (arrowLen * 0.5);
      const w1X = mx - ux * (arrowLen * 0.5) + nx * arrowW;
      const w1Y = my - uy * (arrowLen * 0.5) + ny * arrowW;
      const w2X = mx - ux * (arrowLen * 0.5) - nx * arrowW;
      const w2Y = my - uy * (arrowLen * 0.5) - ny * arrowW;

      ctx.beginPath();
      ctx.moveTo(w1X, w1Y);
      ctx.lineTo(tipX, tipY);
      ctx.lineTo(w2X, w2Y);
      ctx.stroke();
    }
  }

  _drawDynamicTool() {
    if (this.frames.length === 0) return;

    // Interpolate current tool state
    let curState = this.frames[0];
    let prevFrame = this.frames[0];
    let nextFrame = this.frames[this.frames.length - 1];

    for (let i = 0; i < this.frames.length - 1; i++) {
      if (this.currentTime >= this.frames[i].time && this.currentTime <= this.frames[i + 1].time) {
        prevFrame = this.frames[i];
        nextFrame = this.frames[i + 1];
        const span = nextFrame.time - prevFrame.time;
        const alpha = span > 1e-6 ? (this.currentTime - prevFrame.time) / span : 0.0;
        curState = {
          x: prevFrame.x + (nextFrame.x - prevFrame.x) * alpha,
          y: prevFrame.y + (nextFrame.y - prevFrame.y) * alpha,
          z: prevFrame.z + (nextFrame.z - prevFrame.z) * alpha,
          kind: nextFrame.kind,
          feed: nextFrame.feed
        };
        break;
      }
    }

    if (this.currentTime >= nextFrame.time) {
      curState = nextFrame;
    }

    const [toolCx, toolCy] = this._toCanvas([curState.x, curState.y]);
    const ctx = this.ctx;

    // 1. Circular Cutter Profile (Ø)
    if (this.showCutter && this.toolDiameter > 0) {
      const radiusPx = (this.toolDiameter / 2.0) * this.scale;
      if (radiusPx >= 1.0) {
        ctx.fillStyle = SIM_TOOL_FILL;
        ctx.strokeStyle = SIM_TOOL_OUTLINE;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.arc(toolCx, toolCy, radiusPx, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      }
    }

    // 2. Tool Center Crosshair
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = SIM_TOOL_CENTER;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(toolCx, toolCy, 4, 0, 2 * Math.PI);
    ctx.fill();
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(toolCx - 7, toolCy);
    ctx.lineTo(toolCx + 7, toolCy);
    ctx.moveTo(toolCx, toolCy - 7);
    ctx.lineTo(toolCx, toolCy + 7);
    ctx.stroke();

    // Callbacks for UI updates
    const progressPercent = this.totalTime > 0 ? (this.currentTime / this.totalTime) * 100.0 : 0.0;

    if (this.onProgressUpdate) {
      this.onProgressUpdate(progressPercent, this.currentTime, this.totalTime);
    }

    if (this.onStatusUpdate) {
      this.onStatusUpdate({
        x: curState.x,
        y: curState.y,
        z: curState.z,
        feed: curState.feed,
        kind: curState.kind,
        progress: progressPercent,
        currentTime: this.currentTime,
        totalTime: this.totalTime
      });
    }
  }
}

