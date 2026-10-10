const TASKS_MODULE = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/+esm";
const WASM_ROOT = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm";
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

const WRIST = 0;
const THUMB_TIP = 4;
const INDEX_MCP = 5;
const INDEX_PIP = 6;
const INDEX_TIP = 8;
const MIDDLE_MCP = 9;
const MIDDLE_PIP = 10;
const MIDDLE_TIP = 12;
const RING_MCP = 13;
const RING_PIP = 14;
const RING_TIP = 16;
const PINKY_MCP = 17;
const PINKY_PIP = 18;
const PINKY_TIP = 20;
// A generous hysteresis window makes a pinch engage quickly without flickering
// off when the fingers move a few pixels apart during a fast gesture.
const PINCH_ON = 0.37;
const PINCH_OFF = 0.52;
const TRACKING_SMOOTHING = 0.66;
const FAST_TRACKING_SMOOTHING = 0.84;
const FAST_MOVEMENT_THRESHOLD = 0.018;
const FINGERTIPS = [THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP];
const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [0, 9], [9, 10], [10, 11], [11, 12],
  [0, 13], [13, 14], [14, 15], [15, 16],
  [0, 17], [17, 18], [18, 19], [19, 20],
  [5, 9], [9, 13], [13, 17], [17, 0]
];

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function isFingerExtended(points, tip, pip) {
  return distance(points[tip], points[WRIST]) > distance(points[pip], points[WRIST]) * 1.12;
}

function isOpenPalm(points) {
  const extended = [
    [INDEX_TIP, INDEX_PIP],
    [MIDDLE_TIP, MIDDLE_PIP],
    [RING_TIP, RING_PIP],
    [PINKY_TIP, PINKY_PIP]
  ].filter(([tip, pip]) => isFingerExtended(points, tip, pip)).length;
  return extended >= 3;
}

export class ShepardHandTracker {
  constructor(video, overlay, callbacks) {
    this.video = video;
    this.overlay = overlay;
    this.callbacks = callbacks;
    this.landmarker = null;
    this.stream = null;
    this.frame = 0;
    this.running = false;
    this.lastVideoTime = -1;
    this.handStates = new Map();
    this.previousMode = "idle";
    this.previousGestureSignature = "idle";
    this.previousSpinPoint = null;
    this.previousZoomDistance = null;
    this.lastStatus = { hands: 0, mode: "idle", activation: "idle" };
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Camera controls are not available in this browser");
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        frameRate: { ideal: 60 },
        facingMode: "user"
      },
      audio: false
    });
    this.video.srcObject = this.stream;
    await this.video.play();

    const { FilesetResolver, HandLandmarker } = await import(TASKS_MODULE);
    const fileset = await FilesetResolver.forVisionTasks(WASM_ROOT);
    const options = {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
      runningMode: "VIDEO",
      numHands: 2,
      minHandDetectionConfidence: 0.48,
      minHandPresenceConfidence: 0.48,
      minTrackingConfidence: 0.5
    };
    try {
      this.landmarker = await HandLandmarker.createFromOptions(fileset, options);
    } catch {
      this.landmarker = await HandLandmarker.createFromOptions(fileset, {
        ...options,
        baseOptions: { ...options.baseOptions, delegate: "CPU" }
      });
    }
    this.running = true;
    this.loop();
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.frame);
    this.landmarker?.close();
    this.landmarker = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video.pause();
    this.video.srcObject = null;
    this.handStates.clear();
    this.previousMode = "idle";
    this.previousGestureSignature = "idle";
    this.previousSpinPoint = null;
    this.previousZoomDistance = null;
    this.lastVideoTime = -1;
    this.overlay.getContext("2d")?.clearRect(0, 0, this.overlay.width, this.overlay.height);
    this.emitStatus({ hands: 0, mode: "idle", activation: "idle" });
  }

  loop = () => {
    if (!this.running) return;
    this.frame = requestAnimationFrame(this.loop);
    if (!this.landmarker || this.video.readyState < 2) return;
    if (this.video.currentTime === this.lastVideoTime) return;
    this.lastVideoTime = this.video.currentTime;
    const result = this.landmarker.detectForVideo(this.video, performance.now());
    const labels = result.handedness.map((entry, index) => entry[0]?.categoryName || `hand-${index}`);
    this.processHands(result.landmarks, labels);
    this.drawOverlay(result.landmarks);
  };

  processHands(landmarks, labels) {
    const controls = [];
    const seen = new Set();
    landmarks.forEach((points, index) => {
      const label = labels[index] || `hand-${index}`;
      seen.add(label);
      const handSize = distance(points[WRIST], points[MIDDLE_MCP]);
      if (handSize < 1e-6) return;
      const ratio = distance(points[THUMB_TIP], points[INDEX_TIP]) / handSize;
      const pinchPoint = {
        x: 1 - (points[THUMB_TIP].x + points[INDEX_TIP].x) / 2,
        y: (points[THUMB_TIP].y + points[INDEX_TIP].y) / 2
      };
      // Track the center of the knuckle line instead of a fingertip. This makes
      // full-hand control steadier and lets every finger remain available as a
      // visible part of the gesture.
      const palmAnchors = [INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP];
      const palmPoint = {
        x: 1 - palmAnchors.reduce((sum, landmark) => sum + points[landmark].x, 0) / palmAnchors.length,
        y: palmAnchors.reduce((sum, landmark) => sum + points[landmark].y, 0) / palmAnchors.length
      };
      const indexExtended = isFingerExtended(points, INDEX_TIP, INDEX_PIP);
      const openPalm = isOpenPalm(points);
      let hand = this.handStates.get(label);
      if (!hand) {
        hand = {
          pinching: false,
          openPalm: false,
          controlActive: false,
          activation: "idle",
          point: palmPoint,
          missedFrames: 0
        };
        this.handStates.set(label, hand);
      }
      hand.missedFrames = 0;
      // A pinch only counts while the index finger is out. A closed fist can
      // therefore release the scene instead of accidentally looking like a pinch.
      if (hand.pinching && (!indexExtended || ratio > PINCH_OFF)) hand.pinching = false;
      else if (!hand.pinching && indexExtended && ratio < PINCH_ON) hand.pinching = true;
      const activation = openPalm ? "palm" : hand.pinching ? "pinch" : "idle";
      const raw = openPalm ? palmPoint : pinchPoint;
      if (activation !== hand.activation) hand.point = raw;
      const movement = distance(hand.point, raw);
      const smoothing = movement > FAST_MOVEMENT_THRESHOLD
        ? FAST_TRACKING_SMOOTHING
        : TRACKING_SMOOTHING;
      hand.point = {
        x: hand.point.x + (raw.x - hand.point.x) * smoothing,
        y: hand.point.y + (raw.y - hand.point.y) * smoothing
      };
      hand.openPalm = openPalm;
      hand.activation = activation;
      hand.controlActive = activation !== "idle";
      if (hand.controlActive) controls.push({ label, point: hand.point, activation });
    });
    for (const [label, hand] of this.handStates.entries()) {
      if (seen.has(label)) continue;
      hand.missedFrames = (hand.missedFrames || 0) + 1;
      // Hold an active gesture through one dropped camera frame so control does not stutter.
      if (hand.missedFrames === 1 && hand.controlActive) {
        controls.push({ label, point: hand.point, activation: hand.activation });
      }
      else this.handStates.delete(label);
    }

    const mode = controls.length >= 2 ? "zoom" : controls.length === 1 ? "orbit" : "idle";
    const activation = controls.length
      ? controls.every((control) => control.activation === "palm") ? "palm" : "pinch"
      : "idle";
    const signature = `${mode}:${controls.map((control) => `${control.label}-${control.activation}`).sort().join("|")}`;
    if (signature !== this.previousGestureSignature) {
      this.previousSpinPoint = null;
      this.previousZoomDistance = null;
      this.previousGestureSignature = signature;
    }
    this.previousMode = mode;
    if (mode === "orbit") {
      const point = controls[0].point;
      if (this.previousSpinPoint) {
        const dx = point.x - this.previousSpinPoint.x;
        const dy = point.y - this.previousSpinPoint.y;
        if (Math.abs(dx) > 1e-4 || Math.abs(dy) > 1e-4) this.callbacks.onRotate(dx, dy);
      }
      this.previousSpinPoint = point;
    } else if (mode === "zoom") {
      const currentDistance = distance(controls[0].point, controls[1].point);
      if (this.previousZoomDistance && currentDistance > 1e-4) {
        const factor = Math.min(1.18, Math.max(0.85, this.previousZoomDistance / currentDistance));
        this.callbacks.onZoom(factor);
      }
      this.previousZoomDistance = currentDistance;
    }
    this.emitStatus({ hands: landmarks.length, mode, activation });
  }

  emitStatus(status) {
    if (status.hands === this.lastStatus.hands
      && status.mode === this.lastStatus.mode
      && status.activation === this.lastStatus.activation) return;
    this.lastStatus = status;
    this.callbacks.onStatus(status);
  }

  drawOverlay(hands) {
    const context = this.overlay.getContext("2d");
    if (!context) return;
    const { width, height } = this.overlay;
    context.clearRect(0, 0, width, height);
    hands.forEach((points) => {
      const thumb = points[THUMB_TIP];
      const index = points[INDEX_TIP];
      const handSize = distance(points[WRIST], points[MIDDLE_MCP]);
      const pinching = handSize > 1e-6 && distance(thumb, index) / handSize < PINCH_ON;
      const openPalm = isOpenPalm(points);
      const active = openPalm || pinching;
      const project = (point) => ({ x: (1 - point.x) * width, y: point.y * height });

      context.strokeStyle = active ? "rgba(245,185,66,.9)" : "rgba(109,214,209,.72)";
      context.lineWidth = active ? 2.6 : 1.5;
      context.lineCap = "round";
      context.lineJoin = "round";
      HAND_CONNECTIONS.forEach(([from, to]) => {
        const start = project(points[from]);
        const end = project(points[to]);
        context.beginPath();
        context.moveTo(start.x, start.y);
        context.lineTo(end.x, end.y);
        context.stroke();
      });

      points.forEach((point, landmarkIndex) => {
        const { x, y } = project(point);
        const fingertip = FINGERTIPS.includes(landmarkIndex);
        context.fillStyle = fingertip
          ? active ? "#f5b942" : "#6dd6d1"
          : active ? "rgba(255,226,157,.92)" : "rgba(196,249,245,.82)";
        context.beginPath();
        context.arc(x, y, fingertip ? active ? 4.8 : 3.8 : 2, 0, Math.PI * 2);
        context.fill();
      });
    });
  }
}
