const TAU = Math.PI * 2;
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const radians = (degrees) => degrees * Math.PI / 180;

function shortestAngleDistance(a, b) {
  return Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
}

function roundedRect(context, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.roundRect(x, y, width, height, r);
}

export class ShepardLabyrinthScene {
  constructor(stage, { getCamera, reducedMotion = false } = {}) {
    this.stage = stage;
    this.getCamera = getCamera || (() => ({ angle: -12, tilt: 50, zoom: 1 }));
    this.reducedMotion = reducedMotion;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "labyrinth-canvas";
    this.canvas.setAttribute("aria-hidden", "true");
    this.context = this.canvas.getContext("2d", { alpha: true });
    this.stage.prepend(this.canvas);

    this.width = 1;
    this.height = 1;
    this.pixelRatio = 1;
    this.domains = [];
    this.activeDomains = new Set();
    this.hoveredDomain = null;
    this.lastInteractionAt = performance.now();
    this.startedAt = performance.now();
    this.frame = 0;
    this.visible = true;
    this.sheepImage = new Image();
    this.sheepImage.src = "/assets/sheep-sprites.png";

    this.wallBlocks = this.buildMaze();
    this.particles = this.buildParticles(124);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.stage);
    this.visibilityObserver = new IntersectionObserver(([entry]) => {
      this.visible = Boolean(entry?.isIntersecting);
    }, { threshold: 0.02 });
    this.visibilityObserver.observe(this.stage);
    this.resize();
    this.stage.classList.add("scene-ready");
    this.animate = this.animate.bind(this);
    this.frame = requestAnimationFrame(this.animate);
  }

  destroy() {
    cancelAnimationFrame(this.frame);
    this.resizeObserver.disconnect();
    this.visibilityObserver.disconnect();
    this.canvas.remove();
  }

  touch() {
    this.lastInteractionAt = performance.now();
  }

  setActive(ids) {
    this.activeDomains = new Set(ids || []);
  }

  setHovered(id) {
    this.hoveredDomain = id || null;
  }

  syncDomains() {
    this.domains = [...this.stage.querySelectorAll(".domain[data-domain-angle]")].map((element, index) => ({
      id: element.dataset.domainId,
      element,
      angle: radians(Number(element.dataset.domainAngle || 0)),
      radius: Number(element.dataset.worldRadius || 0.79),
      index
    }));
    this.positionBillboards(performance.now());
  }

  resize() {
    const bounds = this.stage.getBoundingClientRect();
    this.width = Math.max(1, Math.round(bounds.width));
    this.height = Math.max(1, Math.round(bounds.height));
    this.pixelRatio = clamp(window.devicePixelRatio || 1, 1, 2);
    this.canvas.width = Math.round(this.width * this.pixelRatio);
    this.canvas.height = Math.round(this.height * this.pixelRatio);
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.context.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
  }

  buildParticles(count) {
    let seed = 9173;
    const random = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    return Array.from({ length: count }, (_, index) => {
      const angle = random() * TAU;
      const radius = 0.16 + random() * 0.85;
      return {
        x: Math.cos(angle) * radius,
        z: Math.sin(angle) * radius,
        y: 0.035 + random() * 0.34,
        phase: random() * TAU,
        size: 0.45 + random() * 1.65,
        amber: index % 7 === 0
      };
    });
  }

  buildMaze() {
    const blocks = [];
    const rings = [
      { radius: .96, gaps: [-1.56, .12, 2.62], tone: "amber", height: .078 },
      { radius: .84, gaps: [-2.68, -.72, 1.18], tone: "slate", height: .067 },
      { radius: .72, gaps: [-1.44, .55, 2.88], tone: "amber", height: .07 },
      { radius: .60, gaps: [-2.32, -.15, 1.62], tone: "slate", height: .062 },
      { radius: .48, gaps: [-1.03, .92, 2.73], tone: "amber", height: .066 },
      { radius: .36, gaps: [-2.55, -.42, 1.96], tone: "slate", height: .058 },
      { radius: .24, gaps: [-1.58, .18, 2.58], tone: "amber", height: .062 }
    ];
    rings.forEach((ring, ringIndex) => {
      const segments = 84;
      const gapWidth = ringIndex === 0 ? .12 : .145;
      for (let index = 0; index < segments; index += 1) {
        const center = (index + .5) / segments * TAU - Math.PI;
        if (ring.gaps.some((gap) => shortestAngleDistance(center, gap) < gapWidth)) continue;
        const start = index / segments * TAU - Math.PI + .006;
        const end = (index + 1) / segments * TAU - Math.PI - .006;
        blocks.push({
          type: "arc",
          radius: ring.radius,
          width: ringIndex === 0 ? .026 : .021,
          start,
          end,
          height: ring.height,
          tone: ring.tone,
          ringIndex
        });
      }
    });

    const spokes = [
      [-1.56, .84, .96], [-1.56, .48, .72], [-1.56, .12, .36],
      [-.72, .72, .84], [-.72, .24, .60], [.12, .84, .96], [.12, .36, .72],
      [.92, .48, .84], [1.62, .60, .96], [1.62, .24, .48], [2.58, .72, .96],
      [2.58, .36, .60], [-2.55, .60, .84], [-2.55, .24, .48], [-1.03, .36, .72]
    ];
    spokes.forEach(([angle, inner, outer], index) => blocks.push({
      type: "radial", angle, inner, outer, width: .022, height: .062,
      tone: index % 3 === 0 ? "amber" : "slate", ringIndex: 8
    }));
    return blocks;
  }

  cameraAt(time) {
    const source = this.getCamera() || {};
    const idle = !this.reducedMotion && !source.dragging && time - this.lastInteractionAt > 1800;
    const breath = idle ? Math.sin((time - this.startedAt) * .00011) * 1.8 : 0;
    return {
      yaw: radians(Number(source.angle || 0) + breath),
      tilt: radians(clamp(Number(source.tilt || 50), 26, 74)),
      zoom: clamp(Number(source.zoom || 1), .68, 1.8),
      panX: String(source.panX || "0").includes("%") ? parseFloat(source.panX) / 100 : 0,
      panY: String(source.panY || "0").includes("px") ? parseFloat(source.panY) : 0,
      focused: this.stage.closest(".labyrinth-visual")?.classList.contains("shepard-focused") || false
    };
  }

  project(point, camera) {
    const cosYaw = Math.cos(camera.yaw);
    const sinYaw = Math.sin(camera.yaw);
    const x = point.x * cosYaw - point.z * sinYaw;
    const z = point.x * sinYaw + point.z * cosYaw;
    const flat = Math.cos(camera.tilt);
    const lift = Math.sin(camera.tilt);
    const depth = z * lift + (point.y || 0) * flat;
    const perspective = clamp(1 + depth * .14, .82, 1.18);
    const base = Math.min(this.width, this.height) * .455 * camera.zoom;
    const centerX = this.width * (.5 + camera.panX);
    const centerY = this.height * .515 + camera.panY;
    return {
      x: centerX + x * base * perspective,
      y: centerY + (z * flat - (point.y || 0) * lift) * base * perspective,
      depth,
      scale: perspective * camera.zoom
    };
  }

  ringPoint(radius, angle, y = 0) {
    return { x: Math.cos(angle) * radius, z: Math.sin(angle) * radius, y };
  }

  pathCircle(context, radius, y, camera, start = 0, end = TAU, steps = 120) {
    for (let index = 0; index <= steps; index += 1) {
      const angle = start + (end - start) * (index / steps);
      const point = this.project(this.ringPoint(radius, angle, y), camera);
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    }
  }

  drawGround(context, camera) {
    const center = this.project({ x: 0, z: 0, y: 0 }, camera);
    const radius = Math.min(this.width, this.height) * .46 * camera.zoom;
    const glow = context.createRadialGradient(center.x, center.y, 0, center.x, center.y, radius);
    glow.addColorStop(0, "rgba(23,54,58,.38)");
    glow.addColorStop(.38, "rgba(11,29,38,.34)");
    glow.addColorStop(.76, "rgba(6,14,23,.22)");
    glow.addColorStop(1, "rgba(3,8,14,0)");
    context.fillStyle = glow;
    context.beginPath();
    this.pathCircle(context, 1.04, 0, camera);
    context.closePath();
    context.fill();

    [1.02, .90, .78, .66, .54, .42, .30, .18].forEach((ring, index) => {
      context.beginPath();
      this.pathCircle(context, ring, .002, camera);
      context.strokeStyle = index % 2
        ? "rgba(91,220,214,.055)"
        : "rgba(245,185,66,.065)";
      context.lineWidth = index === 0 ? 1.3 : .7;
      context.stroke();
    });

    for (let index = 0; index < 24; index += 1) {
      const angle = index / 24 * TAU;
      const inner = this.project(this.ringPoint(.17, angle, .003), camera);
      const outer = this.project(this.ringPoint(1.01, angle, .003), camera);
      context.beginPath();
      context.moveTo(inner.x, inner.y);
      context.lineTo(outer.x, outer.y);
      context.strokeStyle = index % 6 === 0 ? "rgba(109,214,209,.085)" : "rgba(109,214,209,.025)";
      context.lineWidth = index % 6 === 0 ? .8 : .45;
      context.stroke();
    }
  }

  blockPoints(block, height = block.height) {
    if (block.type === "arc") {
      const inner = block.radius - block.width / 2;
      const outer = block.radius + block.width / 2;
      return [
        this.ringPoint(inner, block.start, height),
        this.ringPoint(outer, block.start, height),
        this.ringPoint(outer, block.end, height),
        this.ringPoint(inner, block.end, height)
      ];
    }
    const side = block.width / 2;
    const normal = block.angle + Math.PI / 2;
    const offsetX = Math.cos(normal) * side;
    const offsetZ = Math.sin(normal) * side;
    const inner = this.ringPoint(block.inner, block.angle, height);
    const outer = this.ringPoint(block.outer, block.angle, height);
    return [
      { x: inner.x - offsetX, z: inner.z - offsetZ, y: height },
      { x: inner.x + offsetX, z: inner.z + offsetZ, y: height },
      { x: outer.x + offsetX, z: outer.z + offsetZ, y: height },
      { x: outer.x - offsetX, z: outer.z - offsetZ, y: height }
    ];
  }

  drawWalls(context, camera) {
    const visible = this.wallBlocks.map((block) => {
      const top = this.blockPoints(block);
      const floor = top.map((point) => ({ ...point, y: 0 }));
      const projectedTop = top.map((point) => this.project(point, camera));
      const projectedFloor = floor.map((point) => this.project(point, camera));
      const depth = projectedTop.reduce((sum, point) => sum + point.depth, 0) / projectedTop.length;
      return { block, top: projectedTop, floor: projectedFloor, depth };
    }).sort((a, b) => a.depth - b.depth);

    visible.forEach(({ block, top, floor, depth }) => {
      const near = clamp((depth + 1.1) / 2.2, 0, 1);
      const amber = block.tone === "amber";
      context.beginPath();
      context.moveTo(floor[1].x, floor[1].y);
      context.lineTo(floor[2].x, floor[2].y);
      context.lineTo(top[2].x, top[2].y);
      context.lineTo(top[1].x, top[1].y);
      context.closePath();
      context.fillStyle = amber
        ? `rgba(58,46,30,${.42 + near * .28})`
        : `rgba(28,37,49,${.48 + near * .3})`;
      context.fill();

      context.beginPath();
      top.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
      context.closePath();
      context.fillStyle = amber
        ? `rgba(151,125,76,${.58 + near * .28})`
        : `rgba(92,108,126,${.58 + near * .27})`;
      context.shadowColor = amber ? "rgba(245,185,66,.18)" : "rgba(109,214,209,.12)";
      context.shadowBlur = 7 + near * 7;
      context.fill();
      context.shadowBlur = 0;
      context.strokeStyle = amber ? "rgba(245,204,119,.28)" : "rgba(158,187,205,.22)";
      context.lineWidth = .55 + near * .7;
      context.stroke();
    });
  }

  drawDomainPads(context, camera, time) {
    this.domains.forEach((domain) => {
      const point = this.ringPoint(domain.radius, domain.angle, .008);
      const center = this.project(point, camera);
      const edge = this.project({ x: point.x + .105, z: point.z, y: .008 }, camera);
      const radius = Math.max(10, Math.abs(edge.x - center.x));
      const active = this.activeDomains.has(domain.id);
      const hovered = this.hoveredDomain === domain.id;
      const pulse = .5 + Math.sin(time * .003 + domain.index) * .5;
      context.save();
      context.translate(center.x, center.y);
      context.scale(1, .42 + Math.cos(camera.tilt) * .18);
      context.beginPath();
      context.arc(0, 0, radius * (active ? 1.2 : 1), 0, TAU);
      context.fillStyle = active
        ? `rgba(109,214,209,${.075 + pulse * .045})`
        : hovered ? "rgba(245,185,66,.09)" : "rgba(13,32,36,.16)";
      context.strokeStyle = active
        ? `rgba(109,214,209,${.45 + pulse * .3})`
        : hovered ? "rgba(245,185,66,.5)" : "rgba(109,214,209,.14)";
      context.lineWidth = active ? 1.4 : .8;
      context.fill();
      context.stroke();
      context.restore();
    });
  }

  drawRoutes(context, camera, time) {
    this.domains.forEach((domain) => {
      if (!this.activeDomains.has(domain.id)) return;
      const origin = this.ringPoint(domain.radius, domain.angle, .045);
      const start = this.project(origin, camera);
      const end = this.project({ x: 0, z: 0, y: .07 }, camera);
      const bend = this.project(this.ringPoint(domain.radius * .42, domain.angle + .24, .12), camera);
      context.beginPath();
      context.moveTo(start.x, start.y);
      context.quadraticCurveTo(bend.x, bend.y, end.x, end.y);
      context.strokeStyle = "rgba(109,214,209,.22)";
      context.lineWidth = 1.1;
      context.setLineDash([3, 7]);
      context.lineDashOffset = -time * .018;
      context.shadowColor = "rgba(109,214,209,.7)";
      context.shadowBlur = 7;
      context.stroke();
      context.setLineDash([]);
      context.shadowBlur = 0;

      const progress = ((time * .00019 + domain.index * .31) % 1);
      const inverse = 1 - progress;
      const x = inverse * inverse * start.x + 2 * inverse * progress * bend.x + progress * progress * end.x;
      const y = inverse * inverse * start.y + 2 * inverse * progress * bend.y + progress * progress * end.y;
      const size = 24 + progress * 7;
      if (this.sheepImage.complete && this.sheepImage.naturalWidth) {
        const frames = Math.max(1, Math.round(this.sheepImage.naturalWidth / this.sheepImage.naturalHeight));
        const frameWidth = this.sheepImage.naturalWidth / frames;
        const frame = domain.index % frames;
        context.drawImage(
          this.sheepImage, frame * frameWidth, 0, frameWidth, this.sheepImage.naturalHeight,
          x - size / 2, y - size * .72, size, size
        );
      } else {
        context.fillStyle = "#f5b942";
        context.beginPath();
        context.arc(x, y, 3.2, 0, TAU);
        context.fill();
      }
    });
  }

  drawCore(context, camera, time) {
    const center = this.project({ x: 0, z: 0, y: .035 }, camera);
    const pulse = .5 + Math.sin(time * .0022) * .5;
    const glow = context.createRadialGradient(center.x, center.y, 0, center.x, center.y, 74 + pulse * 14);
    glow.addColorStop(0, `rgba(109,214,209,${.26 + pulse * .12})`);
    glow.addColorStop(.28, "rgba(245,185,66,.12)");
    glow.addColorStop(1, "rgba(5,11,18,0)");
    context.fillStyle = glow;
    context.fillRect(center.x - 100, center.y - 100, 200, 200);

    for (let index = 0; index < 3; index += 1) {
      context.beginPath();
      const offset = this.reducedMotion ? 0 : time * (.00008 + index * .000025) * (index % 2 ? -1 : 1);
      this.pathCircle(context, .16 + index * .035, .028 + index * .009, { ...camera, yaw: camera.yaw + offset }, 0, TAU, 64);
      context.strokeStyle = index === 1 ? "rgba(245,185,66,.26)" : "rgba(109,214,209,.22)";
      context.lineWidth = 1;
      context.stroke();
    }
  }

  drawParticles(context, camera, time) {
    this.particles
      .map((particle) => {
        const rise = this.reducedMotion ? 0 : Math.sin(time * .0007 + particle.phase) * .035;
        const point = this.project({ ...particle, y: particle.y + rise }, camera);
        return { particle, point };
      })
      .sort((a, b) => a.point.depth - b.point.depth)
      .forEach(({ particle, point }) => {
        const alpha = clamp(.16 + (point.depth + 1) * .12, .1, .42);
        context.fillStyle = particle.amber
          ? `rgba(245,185,66,${alpha})`
          : `rgba(109,214,209,${alpha})`;
        context.beginPath();
        context.arc(point.x, point.y, particle.size * clamp(point.scale, .7, 1.3), 0, TAU);
        context.fill();
      });
  }

  positionBillboards(time) {
    if (!this.width || !this.height) return;
    const camera = this.cameraAt(time);
    this.domains.forEach((domain) => {
      const world = this.ringPoint(domain.radius, domain.angle, .085);
      const point = this.project(world, camera);
      const depth = clamp((point.depth + 1) / 2, 0, 1);
      const scale = clamp((.76 + depth * .25) * Math.sqrt(camera.zoom), .62, 1.24);
      domain.element.style.left = `${point.x}px`;
      domain.element.style.top = `${point.y}px`;
      domain.element.style.transform = `translate(-50%, -58%) scale(${scale.toFixed(3)})`;
      domain.element.style.zIndex = String(Math.round(12 + depth * 48));
      domain.element.style.setProperty("--depth-light", (.78 + depth * .28).toFixed(3));
      domain.element.style.setProperty("--depth-opacity", (.72 + depth * .28).toFixed(3));
    });

    const root = this.stage.querySelector(".root-domain");
    if (root) {
      const point = this.project({ x: 0, z: 0, y: .12 }, camera);
      const baseScale = camera.focused ? 1.08 : clamp(.86 + camera.zoom * .12, .92, 1.12);
      root.style.left = `${point.x}px`;
      root.style.top = `${point.y}px`;
      root.style.transform = `translate(-50%, -52%) scale(${baseScale.toFixed(3)})`;
      root.style.zIndex = "42";
    }
  }

  draw(time) {
    const context = this.context;
    if (!context) return;
    const camera = this.cameraAt(time);
    context.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
    context.clearRect(0, 0, this.width, this.height);
    context.save();
    this.drawGround(context, camera);
    this.drawDomainPads(context, camera, time);
    this.drawWalls(context, camera);
    this.drawRoutes(context, camera, time);
    this.drawCore(context, camera, time);
    this.drawParticles(context, camera, time);
    context.restore();
    this.positionBillboards(time);
  }

  animate(time) {
    if (this.visible) this.draw(time);
    this.frame = requestAnimationFrame(this.animate);
  }
}

