/* 全屏编辑器和现有外观系统之间的适配。 */
(function () {
  "use strict";
  let frame = null;
  let previousFocus = null;
  const text = {
    zh: { open: "打开全屏编辑器", title: "积木编辑器", saved: "布局已保存", failed: "保存失败，浏览器存储空间可能不足", cancel: "关闭编辑器" },
    hant: { open: "開啟全螢幕編輯器", title: "積木編輯器", saved: "佈局已儲存", failed: "儲存失敗，瀏覽器儲存空間可能不足", cancel: "關閉編輯器" },
    en: { open: "Open full-screen editor", title: "Layout editor", saved: "Layout saved", failed: "Could not save. Browser storage may be full.", cancel: "Close editor" }
  };
  const strings = () => text[lang] || text.zh;
  const image = value => typeof value === "string" && /^data:image\/(png|jpeg|webp|gif|avif);base64,[a-z0-9+/=]+$/i.test(value) ? value : "";
  const color = value => typeof value === "string" && /^#[a-f0-9]{6}$/i.test(value) ? value : "";

  function cleanBlocks(source) {
    const result = {};
    for (const [index, def] of BLOCK_DEFS.entries()) {
      const value = source && source[def.id] || {};
      result[def.id] = {
        visible: def.id === "topbar" || value.visible !== false,
        order: Number.isFinite(Number(value.order)) ? Number(value.order) : index,
        bg: color(value.bg), fg: color(value.fg),
        radius: value.radius === null || value.radius === undefined ? null : Math.max(0, Math.min(32, Number(value.radius) || 0)),
        image: image(value.image)
      };
    }
    return result;
  }

  function saveAppearance(look, canvas) {
    const keys = [LOOK_KEY, "subdrive_canvas"];
    const previous = keys.map(key => localStorage.getItem(key));
    try {
      localStorage.setItem(LOOK_KEY, JSON.stringify(look));
      SubDriveCanvas.write(canvas);
    } catch (error) {
      keys.forEach((key, index) => {
        if (previous[index] === null) localStorage.removeItem(key);
        else localStorage.setItem(key, previous[index]);
      });
      throw error;
    }
    applyLook();
    refreshLookUI();
  }

  function stateFromLook() {
    const look = lookState();
    const canvas = SubDriveCanvas.read();
    const blocks = {};
    for (const def of BLOCK_DEFS) {
      const value = look.blocks?.[def.id] || {};
      const geometry = canvas?.blocks?.[def.id] || {};
      blocks[def.id] = { ...value, fit: geometry.fit || "cover",
        x: geometry.imageX ?? 50, y: geometry.imageY ?? 50 };
    }
    return {
      preset: currentTheme() === "dark" || currentTheme() === "auto" &&
        matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      order: BLOCK_DEFS.filter(def => def.orderable)
        .sort((a, b) => (Number(blocks[a.id].order) || 0) - (Number(blocks[b.id].order) || 0)).map(def => def.id),
      blocks, canvas
    };
  }

  function previewHTML() {
    const clone = document.querySelector("#view-drive").cloneNode(true);
    SubDriveCanvas.cleanClone(clone);
    clone.classList.remove("hidden");
    clone.querySelectorAll("[data-canvas-sticker], .canvas-sticker").forEach(node => node.remove());
    const main = clone.querySelector(".drive-main");
    main.classList.remove("canvas-active", "sd-canvas");
    main.removeAttribute("style");
    for (const def of BLOCK_DEFS) {
      const node = clone.querySelector(def.sel);
      if (!node) continue;
      node.removeAttribute("style");
      // 隐藏的模块在编辑器中由草稿状态控制。
      if (def.id === "shared") node.classList.remove("hidden");
    }
    clone.querySelectorAll("script").forEach(node => node.remove());
    const links = [...document.querySelectorAll('link[rel="stylesheet"]')]
      .filter(node => !node.href.includes("canvas-runtime")).map(node => node.outerHTML).join("");
    const theme = currentTheme() === "auto" ? "" : ' data-theme="' + currentTheme() + '"';
    const root = document.documentElement;
    const accent = root.getAttribute("data-accent") || "";
    const accentStyle = ["--accent", "--accent-2", "--accent-grad", "--accent-soft",
      "--accent-button-background", "--accent-button-text", "--accent-readable"]
      .map(key => key + ":" + root.style.getPropertyValue(key)).filter(entry => !entry.endsWith(":")).join(";");
    const bodyStyle = document.body.cloneNode(false).style;
    bodyStyle.removeProperty("overflow");
    const density = lookState().density === "compact" ? ' class="dense"' : "";
    return '<!doctype html><html lang="' + (lang === "en" ? "en" : lang === "hant" ? "zh-Hant" : "zh-CN") +
      '"' + theme + ' data-accent="' + esc(accent) + '" style="' + esc(accentStyle) +
      '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
      links + '<link rel="stylesheet" href="/static/blocks-preview.css?v=40"></head><body' + density +
      ' style="' + esc(bodyStyle.cssText) + '">' +
      clone.outerHTML + '</body></html>';
  }

  function close() {
    frame?.remove();
    frame = null;
    delete window.SUBDRIVE_EDITOR_BOOT;
    document.body.style.removeProperty("overflow");
    previousFocus?.focus();
  }

  function draftPackage(state, themeChanged) {
    const blocks = cleanBlocks(state.blocks);
    const canvas = SubDriveCanvas.normalize(state.canvas);
    if (state.canvas != null && !canvas) throw new Error("Invalid canvas");
    state.order.forEach((id, order) => { if (blocks[id]) blocks[id].order = order; });
    for (const [id, geometry] of Object.entries(canvas?.blocks || {})) {
      const value = state.blocks?.[id] || {};
      geometry.fit = value.fit === "contain" ? "contain" : "cover";
      geometry.imageX = Number.isFinite(value.x) ? Math.max(0, Math.min(100, value.x)) : 50;
      geometry.imageY = Number.isFinite(value.y) ? Math.max(0, Math.min(100, value.y)) : 50;
    }
    const look = { ...lookState(), blocks };
    if (themeChanged) look.bg = state.preset === "paper" ? "#f4eee1" : "";
    const theme = themeChanged ? state.preset === "dark" ? "dark" : "light" : currentTheme();
    return { v: 1, kind: "subdrive-look", theme, accent: currentAccent(), look, canvas };
  }

  function open() {
    if (frame) return;
    previousFocus = document.activeElement;
    window.SUBDRIVE_EDITOR_BOOT = { preview: previewHTML(), state: stateFromLook(), lang, draftPackage,
      refreshAccent: window.SubDriveAccent?.refresh };
    frame = document.createElement("iframe");
    frame.id = "full-block-editor";
    frame.title = strings().title;
    frame.src = "/static/blocks-editor-" + lang + ".html?v=40";
    frame.style.cssText = "position:fixed;inset:0;width:100%;height:100dvh;border:0;background:#fff;z-index:1000";
    document.body.append(frame);
    document.body.style.overflow = "hidden";
    frame.focus();
  }

  window.addEventListener("message", event => {
    if (!frame || event.source !== frame.contentWindow || event.origin !== location.origin) return;
    if (event.data?.type === "subdrive-editor-close") { close(); return; }
    if (event.data?.type !== "subdrive-editor-save") return;
    try {
      const draft = draftPackage(event.data.state, event.data.themeChanged);
      saveAppearance(draft.look, draft.canvas);
      if (event.data.themeChanged) setTheme(draft.theme);
      close();
      toast(strings().saved);
    } catch {
      frame.contentWindow.postMessage({ type: "subdrive-editor-error", message: strings().failed }, location.origin);
      toast(strings().failed, true);
    }
  });
  window.SubDriveEditor = { open, close, cleanBlocks, saveAppearance, buttonLabel: () => strings().open };
})();
