/* Custom accent accessibility. Existing --accent remains the user's original hex. */
(function () {
  "use strict";

  function luminance(rgb) {
    const linear = rgb.map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  }

  function contrast(a, b) {
    const left = luminance(a);
    const right = luminance(b);
    return (Math.max(left, right) + 0.05) / (Math.min(left, right) + 0.05);
  }

  function minimumContrast(color, surfaces) {
    return Math.min(...surfaces.map(surface => contrast(color, surface)));
  }

  function readableColor(color, surfaces) {
    if (minimumContrast(color, surfaces) >= 4.6) return color;
    const black = [0, 0, 0];
    const white = [255, 255, 255];
    const target = minimumContrast(black, surfaces) >= minimumContrast(white, surfaces) ? black : white;
    let low = 0;
    let high = 1;
    for (let step = 0; step < 20; step += 1) {
      const amount = (low + high) / 2;
      const mixed = color.map((channel, index) => Math.round(channel + (target[index] - channel) * amount));
      if (minimumContrast(mixed, surfaces) >= 4.6) high = amount;
      else low = amount;
    }
    return color.map((channel, index) => Math.round(channel + (target[index] - channel) * high));
  }

  function colors(hex, surfaces) {
    const accent = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16));
    const black = [0, 0, 0];
    const white = [255, 255, 255];
    const foreground = contrast(accent, black) >= contrast(accent, white) ? black : white;
    return { background: accent, foreground, readable: readableColor(accent, surfaces) };
  }

  const api = { colors, contrast };
  globalThis.SubDriveAccent = api;
  if (typeof document === "undefined") return;

  const defaultRoot = document.documentElement;
  const context = document.createElement("canvas").getContext("2d");
  const names = ["--accent-button-background", "--accent-button-text", "--accent-readable"];
  const signatures = new WeakMap();

  function rgba(value) {
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = value;
    context.fillRect(0, 0, 1, 1);
    return Array.from(context.getImageData(0, 0, 1, 1).data);
  }

  function css(rgb) {
    return "rgb(" + rgb.join(", ") + ")";
  }

  function refresh(root = defaultRoot) {
    const styles = getComputedStyle(root);
    const accent = styles.getPropertyValue("--accent").trim();
    const custom = root.dataset.accent === "custom" && /^#[0-9a-f]{6}$/i.test(accent);
    if (!custom) {
      signatures.delete(root);
      for (const name of names) {
        if (root.style.getPropertyValue(name)) root.style.removeProperty(name);
      }
      return;
    }
    const surfaces = ["--bg", "--surface", "--surface-2", "--surface-3"]
      .map(name => rgba(styles.getPropertyValue(name).trim()).slice(0, 3));
    const soft = rgba(styles.getPropertyValue("--accent-soft").trim());
    const opacity = soft[3] / 255;
    const tinted = surfaces.map(surface => surface.map((channel, index) =>
      Math.round(soft[index] * opacity + channel * (1 - opacity))));
    const backgrounds = surfaces.concat(tinted);
    const signature = accent + JSON.stringify(backgrounds);
    if (signature === signatures.get(root)) return;
    signatures.set(root, signature);
    const result = colors(accent, backgrounds);
    root.style.setProperty(names[0], css(result.background));
    root.style.setProperty(names[1], css(result.foreground));
    root.style.setProperty(names[2], css(result.readable));
  }

  api.refresh = refresh;
  new MutationObserver(() => refresh()).observe(defaultRoot, {
    attributes: true,
    attributeFilter: ["style", "data-theme", "data-accent"]
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => refresh());
  refresh();
})();
