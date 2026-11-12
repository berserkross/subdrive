/* SubDrive 自由画布。旧外观数据继续由 applyLook / applyBlocks 管理。 */
(function () {
  "use strict";

  const STORAGE_KEY = "subdrive_canvas";
  const MAX_STICKERS = 32;
  const MAX_IMAGE_LENGTH = 2 * 1024 * 1024;
  const MAX_TOTAL_IMAGE_LENGTH = 4 * 1024 * 1024;
  const SELECTORS = {
    quota: ".quota-card",
    scope: "#nav-scope",
    toolbar: ".toolbar",
    shared: "#shared-card",
    files: "#dropzone",
    foot: ".drive-foot"
  };
  const PROPERTIES = ["--canvas-x", "--canvas-y", "--canvas-width", "--canvas-height"];
  let current = null;
  let main = null;
  let resizeObserver = null;
  let mutationObserver = null;
  let scheduled = 0;
  let stickerLayer = null;
  let nodes = new Map();
  const originalBackgrounds = new Map();

  function bounded(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function rectangle(value, width, height) {
    if (!value || typeof value !== "object") return null;
    if (![value.x, value.y, value.w, value.h].every(Number.isFinite)) return null;
    const x = bounded(value.x, 0, width - 16);
    const y = bounded(value.y, 0, height - 16);
    return {
      x: Math.round(x * 100) / 100,
      y: Math.round(y * 100) / 100,
      w: Math.round(bounded(value.w, 16, width - x) * 100) / 100,
      h: Math.round(bounded(value.h, 16, height - y) * 100) / 100
    };
  }

  function safeImage(value) {
    return typeof value === "string" && value.length <= MAX_IMAGE_LENGTH &&
      /^data:image\/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
  }

  function normalize(value) {
    if (!value || typeof value !== "object" || value.v !== 1) return null;
    if (!Number.isFinite(value.width) || !Number.isFinite(value.height)) return null;
    if (value.width <= 0 || value.height <= 0) return null;
    if (value.stickers != null && !Array.isArray(value.stickers)) return null;
    if ((value.stickers || []).length > MAX_STICKERS) return null;
    const width = bounded(value.width, 240, 8192);
    const height = bounded(value.height, 240, 32768);
    const blocks = {};
    for (const id of Object.keys(SELECTORS)) {
      const rect = rectangle(value.blocks?.[id], width, height);
      if (rect) {
        const item = value.blocks[id];
        blocks[id] = { ...rect, fit: item.fit === "contain" ? "contain" : "cover",
          imageX: Number.isFinite(item.imageX) ? bounded(item.imageX, 0, 100) : 50,
          imageY: Number.isFinite(item.imageY) ? bounded(item.imageY, 0, 100) : 50 };
      }
    }
    const stickers = [];
    const ids = new Set();
    let totalLength = 0;
    for (const candidate of value.stickers || []) {
      const rect = rectangle(candidate, width, height);
      if (!rect || !safeImage(candidate.image)) return null;
      totalLength += candidate.image.length;
      if (totalLength > MAX_TOTAL_IMAGE_LENGTH) return null;
      const originalId = typeof candidate.id === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(candidate.id)
        ? candidate.id : "sticker-" + stickers.length;
      let id = originalId;
      while (ids.has(id)) id += "-copy";
      ids.add(id);
      stickers.push({ id, image: candidate.image, ...rect });
    }
    return { v: 1, snap: value.snap === true, width, height, blocks, stickers };
  }

  function read() {
    try {
      return normalize(JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"));
    } catch {
      return null;
    }
  }

  function write(value) {
    if (value === null) {
      localStorage.removeItem(STORAGE_KEY);
      apply(null);
      return null;
    }
    const clean = normalize(value);
    if (!clean) throw new TypeError("Invalid SubDrive canvas");
    // setItem 是单次替换。容量不足时抛错，保留原键值与当前画布。
    localStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
    apply(clean);
    return clean;
  }

  function setPixel(node, property, value) {
    const pixels = Math.round(value * 100) / 100 + "px";
    if (node.style.getPropertyValue(property) !== pixels) node.style.setProperty(property, pixels);
  }

  function clear() {
    if (scheduled) cancelAnimationFrame(scheduled);
    scheduled = 0;
    resizeObserver?.disconnect();
    mutationObserver?.disconnect();
    resizeObserver = null;
    mutationObserver = null;
    stickerLayer?.remove();
    stickerLayer = null;
    for (const node of nodes.values()) {
      node.classList.remove("canvas-module");
      for (const property of PROPERTIES) node.style.removeProperty(property);
      const background = originalBackgrounds.get(node);
      node.style.backgroundSize = background.size;
      node.style.backgroundPosition = background.position;
    }
    nodes.clear();
    originalBackgrounds.clear();
    if (main) {
      main.classList.remove("canvas-active", "canvas-desktop");
      main.style.removeProperty("--canvas-content-height");
    }
    current = null;
  }

  function schedule() {
    if (scheduled || !current || !main) return;
    scheduled = requestAnimationFrame(() => {
      scheduled = 0;
      layout();
    });
  }

  function visible(node) {
    return node.getClientRects().length > 0 && getComputedStyle(node).display !== "none";
  }

  function layout() {
    if (!current || !main || !main.clientWidth || !main.getClientRects().length) return;
    main.classList.add("canvas-desktop");
    const ratio = main.clientWidth / current.width;
    const flowHeight = [...main.children].filter(node =>
      node !== stickerLayer && !node.classList.contains("canvas-module") && visible(node)
    ).reduce((total, node) => {
      const style = getComputedStyle(node);
      return total + node.offsetHeight + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
    }, 0);
    const rows = [];
    for (const [id, node] of nodes) {
      const rect = current.blocks[id];
      if (node.style.backgroundSize !== rect.fit) node.style.backgroundSize = rect.fit;
      const imagePosition = rect.imageX + "% " + rect.imageY + "%";
      if (node.style.backgroundPosition !== imagePosition) node.style.backgroundPosition = imagePosition;
      setPixel(node, "--canvas-x", rect.x * ratio);
      setPixel(node, "--canvas-width", rect.w * ratio);
      setPixel(node, "--canvas-height", rect.h * ratio);
      if (!visible(node)) continue;
      rows.push({ node, x: rect.x * ratio, w: rect.w * ratio,
        baseY: rect.y * ratio + flowHeight, baseH: rect.h * ratio, actualH: node.offsetHeight });
    }
    rows.sort((a, b) => a.baseY - b.baseY);
    let bottom = 0;
    for (let index = 0; index < rows.length; index++) {
      const row = rows[index];
      row.top = row.baseY;
      for (let previous = 0; previous < index; previous++) {
        const above = rows[previous];
        const intersects = row.x < above.x + above.w && row.x + row.w > above.x;
        const originalGap = row.baseY - above.baseY - above.baseH;
        if (intersects && originalGap >= -1) {
          row.top = Math.max(row.top, above.top + above.actualH + Math.max(0, originalGap));
        }
      }
      setPixel(row.node, "--canvas-y", row.top);
      bottom = Math.max(bottom, row.top + row.actualH);
    }
    for (let index = 0; index < current.stickers.length; index++) {
      const sticker = current.stickers[index];
      const image = stickerLayer.children[index];
      setPixel(image, "--canvas-x", sticker.x * ratio);
      setPixel(image, "--canvas-y", sticker.y * ratio + flowHeight);
      setPixel(image, "--canvas-width", sticker.w * ratio);
      setPixel(image, "--canvas-height", sticker.h * ratio);
      bottom = Math.max(bottom, (sticker.y + sticker.h) * ratio + flowHeight);
    }
    // 没有布局数据的业务提示与新增模块保留在流中，其高度继续计入父容器。
    setPixel(main, "--canvas-content-height", Math.max(current.height * ratio, bottom + 32, flowHeight));
  }

  function apply(value = read()) {
    clear();
    current = normalize(value);
    main = document.querySelector(".drive-main");
    if (!current || !main) return;
    if (!Object.keys(current.blocks).length && !current.stickers.length) {
      current = null;
      return;
    }
    main.classList.add("canvas-active");
    for (const [id, selector] of Object.entries(SELECTORS)) {
      const node = main.querySelector(selector);
      if (!node || !current.blocks[id]) continue;
      nodes.set(id, node);
      originalBackgrounds.set(node, { size: node.style.backgroundSize, position: node.style.backgroundPosition });
      node.classList.add("canvas-module");
    }
    stickerLayer = document.createElement("div");
    stickerLayer.className = "canvas-stickers";
    stickerLayer.setAttribute("aria-hidden", "true");
    for (const sticker of current.stickers) {
      const image = document.createElement("img");
      image.className = "canvas-sticker";
      image.src = sticker.image;
      image.alt = "";
      image.draggable = false;
      stickerLayer.append(image);
    }
    main.append(stickerLayer);
    resizeObserver = new ResizeObserver(schedule);
    resizeObserver.observe(main);
    for (const node of nodes.values()) resizeObserver.observe(node);
    mutationObserver = new MutationObserver(schedule);
    mutationObserver.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "hidden"] });
    layout();
  }

  window.addEventListener("resize", schedule, { passive: true });
  window.addEventListener("storage", event => {
    if (event.key === STORAGE_KEY || event.key === null) apply();
  });
  function cleanClone(clone) {
    const root = clone.matches?.(".drive-main") ? clone : clone.querySelector(".drive-main");
    if (!root) return clone;
    root.classList.remove("canvas-active", "canvas-desktop");
    root.style.removeProperty("--canvas-content-height");
    root.querySelectorAll(".canvas-stickers").forEach(node => node.remove());
    for (const [id, selector] of Object.entries(SELECTORS)) {
      const node = root.querySelector(selector);
      if (!node) continue;
      node.classList.remove("canvas-module");
      for (const property of PROPERTIES) node.style.removeProperty(property);
      const background = originalBackgrounds.get(nodes.get(id));
      if (background) {
        node.style.backgroundSize = background.size;
        node.style.backgroundPosition = background.position;
      }
    }
    return clone;
  }
  window.SubDriveCanvas = Object.freeze({ key: STORAGE_KEY, read, write, normalize, apply, clear, cleanClone, refresh: schedule });
})();
