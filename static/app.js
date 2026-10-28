"use strict";
/* ================= SubDrive 前端 ================= */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

let token = localStorage.getItem("subdrive_token") || "";
let me = null;
let curPath = ""; // "" = 根目录；否则 "a/b"
let curOwner = ""; // "" = 自己的网盘；否则正在浏览谁的共享文件夹
let quota = null;
let sharedMine = []; // 我创建的共享文件夹（来自 /api/shared/list，is_mine）

/* owner 只在浏览别人的共享目录时出现；服务端会按 owner+path 复核授权 */
const ownerQS = (prefix) =>
  curOwner ? prefix + "owner=" + encodeURIComponent(curOwner) : "";

/* ---- 加密文件夹（SDV1，格式见 CRYPTO.md）状态 ---- */
let vault = null; // 已解锁：{ path, key, manifest }；key 只在内存
let vaultRootPath = null; // 当前目录被识别为加密文件夹根时的路径（未解锁）
const vaultDirMarks = new Set(); // 已探明为加密文件夹的相对路径（用于列表锁徽章）

// 支持 ?token= 直达（便于分享调试/截图），用后即清理地址栏
{
  const u = new URL(location.href);
  const t = u.searchParams.get("token");
  if (t) {
    token = t;
    localStorage.setItem("subdrive_token", t);
    u.searchParams.delete("token");
    history.replaceState(null, "", u.pathname + u.search + u.hash);
  }
}

/* ---------------- 工具 ---------------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function fmtBytes(n) {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v >= 100 ? Math.round(v) : v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}
function fmtTime(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return String(s);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fmtDate(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return String(s);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast hidden"; }, 2600);
}
async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  let body = opts.body;
  if (body && typeof body === "object" && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const resp = await fetch(path, { method: opts.method || "GET", headers, body });
  let data = null;
  try { data = await resp.json(); } catch { /* 非 JSON */ }
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : data;
    const msg = (detail && detail.message) || (data && data.message) || `请求失败 (${resp.status})`;
    const e = new Error(msg);
    e.status = resp.status;
    e.code = detail && detail.error;
    if (resp.status === 401 && token) { /* 会话失效，回到登录页 */ logout(false); }
    throw e;
  }
  return data;
}

/* ---------------- 图标 ---------------- */
const ICONS = {
  folder: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5A2.5 2.5 0 0 1 5.5 3h4l2.2 2.7a1 1 0 0 0 .78.33H18.5A2.5 2.5 0 0 1 21 8.53v7.97a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m4.5 18 5.2-5.2a1.4 1.4 0 0 1 2 0l6.8 6.8"/></svg>',
  video: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m10.5 9.8 4.5 2.2-4.5 2.2z" fill="currentColor" stroke="none"/></svg>',
  audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18.5V6l10-2v11.5"/><circle cx="6.5" cy="18.5" r="2.5"/><circle cx="16.5" cy="15.5" r="2.5"/></svg>',
  doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/></svg>',
  zip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M12 7v2M12 11v2M12 15v2"/></svg>',
  code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m8.5 8.5-4 3.5 4 3.5M15.5 8.5l4 3.5-4 3.5"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3"/><path d="M9 7.5h6"/></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 11l5 5 5-5"/><path d="M4.5 20h15"/></svg>',
  rename: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17z"/><path d="m13.5 6.5 3 3"/></svg>',
  move: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12h13M13 6.5 18.5 12 13 17.5"/><path d="M3.5 5.5v13"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4.5A.5.5 0 0 1 9.5 4h5a.5.5 0 0 1 .5.5V7"/><path d="M6.5 7 7.4 19a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9L17.5 7"/><path d="M10 11v6M14 11v6"/></svg>',
  share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="17.5" cy="6" r="2.6"/><circle cx="6.5" cy="12" r="2.6"/><circle cx="17.5" cy="18" r="2.6"/><path d="m8.8 10.7 6.4-3.4M8.8 13.3l6.4 3.4"/></svg>',
  unshare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="17.5" cy="6" r="2.6"/><circle cx="6.5" cy="12" r="2.6"/><circle cx="17.5" cy="18" r="2.6"/><path d="m8.8 10.7 6.4-3.4M8.8 13.3l6.4 3.4"/><path d="M4 20 20 4"/></svg>',
};
function extOf(name) {
  return (name.split(".").pop() || "").toLowerCase();
}
function iconFor(entry) {
  if (entry.type === "dir") return { cls: "folder", svg: ICONS.folder };
  const ext = extOf(entry.name);
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "heic", "avif", "ico", "tiff"].includes(ext)) return { cls: "image", svg: ICONS.image };
  if (["mp4", "mov", "mkv", "webm", "avi", "m4v"].includes(ext)) return { cls: "video", svg: ICONS.video };
  if (["mp3", "wav", "flac", "m4a", "ogg", "aac", "opus"].includes(ext)) return { cls: "audio", svg: ICONS.audio };
  if (["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"].includes(ext)) return { cls: "zip", svg: ICONS.zip };
  if (ext === "pdf") return { cls: "pdf", svg: ICONS.doc };
  if (["doc", "docx", "odt", "rtf", "pages"].includes(ext)) return { cls: "word", svg: ICONS.doc };
  if (["xls", "xlsx", "csv", "ods", "numbers"].includes(ext)) return { cls: "excel", svg: ICONS.doc };
  if (["ppt", "pptx", "odp", "key"].includes(ext)) return { cls: "ppt", svg: ICONS.doc };
  if (["epub", "mobi", "azw3", "azw"].includes(ext)) return { cls: "ebook", svg: ICONS.book };
  if (ext === "md" || ext === "markdown") return { cls: "md", svg: ICONS.code };
  if (["js", "ts", "tsx", "jsx", "py", "json", "html", "css", "sh", "go", "rs", "java", "c", "h", "cpp", "sql", "yml", "yaml", "toml", "xml"].includes(ext)) return { cls: "code", svg: ICONS.code };
  if (["txt", "log", "ini", "conf"].includes(ext)) return { cls: "text", svg: ICONS.doc };
  return { cls: "file", svg: ICONS.file };
}

/* ---------------- 视图切换 ---------------- */
function show(view) {
  for (const id of ["view-auth", "view-drive", "view-admin"]) {
    $("#" + id).classList.toggle("hidden", id !== view);
  }
  window.scrollTo(0, 0);
}

/* ---------------- 登录 / 注册 ---------------- */
$("#tab-login").addEventListener("click", () => switchTab("login"));
$("#tab-register").addEventListener("click", () => switchTab("register"));
function switchTab(which) {
  $("#tab-login").classList.toggle("active", which === "login");
  $("#tab-register").classList.toggle("active", which === "register");
  $("#form-login").classList.toggle("hidden", which !== "login");
  $("#form-register").classList.toggle("hidden", which !== "register");
}

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#login-error");
  errEl.textContent = "";
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: { username: $("#login-username").value.trim(), password: $("#login-password").value },
    });
    setSession(data);
  } catch (err) {
    errEl.textContent = err.message;
  } finally { btn.disabled = false; }
});

$("#form-register").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#reg-error");
  errEl.textContent = "";
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: {
        invite_code: $("#reg-invite").value.trim(),
        username: $("#reg-username").value.trim(),
        nickname: $("#reg-nickname").value.trim(),
        password: $("#reg-password").value,
      },
    });
    setSession(data);
    toast("注册成功，你的网盘已开通 🎉");
  } catch (err) {
    errEl.textContent = err.message;
  } finally { btn.disabled = false; }
});

function setSession(data) {
  token = data.token;
  localStorage.setItem("subdrive_token", token);
  me = data.user;
  enterDrive();
}
function logout(callApi = true) {
  if (callApi && token) {
    api("/api/auth/logout", { method: "POST" }).catch(() => {});
  }
  token = ""; me = null; curPath = ""; curOwner = ""; sharedMine = [];
  localStorage.removeItem("subdrive_token");
  show("view-auth");
}
$("#btn-logout").addEventListener("click", () => logout(true));
$("#btn-my-cell").addEventListener("click", () => {
  if (!curOwner || !me) return;
  // 共享根是路径第一段；我那一格固定叫我的用户名
  const root = curPath.split("/")[0];
  curPath = (root ? root + "/" : "") + me.username;
  refreshList();
});

/* ---------------- 网盘 ---------------- */
async function enterDrive() {
  try {
    me = await api("/api/auth/me");
  } catch { show("view-auth"); return; }
  $("#user-avatar").textContent = (me.nickname || me.username).slice(0, 1);
  $("#user-name").textContent = me.nickname || me.username;
  $("#user-sub").textContent = "@" + me.username;
  $("#btn-admin").classList.toggle("hidden", !me.is_admin);
  show("view-drive");
  curOwner = "";
  await Promise.all([refreshList(), refreshQuota(), refreshShared()]);
  if (location.hash === "#admin" && me.is_admin) {
    show("view-admin");
    loadAdmin();
  }
}

/* ---------------- 共享文件夹 ---------------- */
async function refreshShared() {
  let folders = [];
  try { folders = (await api("/api/shared/list")).folders || []; } catch { folders = []; }
  sharedMine = folders.filter((f) => f.is_mine);
  const card = $("#shared-card");
  const list = $("#shared-list");
  list.innerHTML = "";
  card.classList.toggle("hidden", folders.length === 0);
  $("#shared-hint").textContent = folders.length
    ? "被授权的共享文件夹可查看、下载、上传；配额算上传者自己"
    : "";
  for (const f of folders) {
    const el = document.createElement("div");
    el.className = "shared-item" + (f.is_mine ? " mine" : "");
    el.innerHTML = `<span>🔗 ${esc(f.path)}</span>`
      + `<span class="si-owner">${f.is_mine ? "我创建" : esc(f.owner)}</span>`
      + `<span class="si-meta">${f.members.length ? f.members.length + " 人" : "全员"}</span>`;
    el.title = f.is_mine ? "点进入；在目录里点「管理共享」改名单" : `${f.owner} 分享给你`;
    el.addEventListener("click", () => enterShared(f));
    list.appendChild(el);
  }
}

function enterShared(f) {
  if (f.is_mine) { curOwner = ""; curPath = f.path; }
  else { curOwner = f.owner; curPath = ""; }
  vault = null;
  vaultRootPath = null;
  refreshList();
}

/* ---------------- 共享对话框 ---------------- */
function revokeShare(folder) {
  openModal("取消共享",
    `<p class="modal-text">「${esc(folder.path)}」将退回私有文件夹：成员立刻失去访问权限，目录里的内容全部保留。</p>`,
    "取消共享", async () => {
      try {
        await api("/api/shared/" + folder.id, { method: "DELETE" });
        toast("已取消共享");
        await refreshShared();
        refreshList();
      } catch (e) { toast(e.message, true); }
    }, true);
}

async function openShareDialog(path, grant) {
  let folders = [];
  try { folders = (await api("/api/shared/list")).folders || []; } catch (e) { toast(e.message, true); return; }
  const mineOne = folders.find((f) => f.is_mine && f.path === path) || null;
  const isMine = !!(grant && grant.is_mine) || !!mineOne;
  const members = (mineOne || grant || {}).members || [];
  const body = isMine
    ? `<p class="modal-hint">「${esc(path)}」已共享。不填成员＝所有注册成员可见；成员可查看、下载、上传（各自配额）。</p>
       <label class="field-label">授权成员用户名（每行一个，留空＝全员）</label>
       <textarea id="share-members" class="field-input" rows="5">${esc(members.join("\n"))}</textarea>`
    : `<p class="modal-hint">把「${esc(path)}」变成共享文件夹：名单内成员可查看、下载、上传，上传内容存进各自用户名子文件夹；配额算上传者自己。创建后即公开，可随时改名单或取消共享。</p>
       <label class="field-label">授权成员用户名（每行一个，留空＝全员）</label>
       <textarea id="share-members" class="field-input" rows="5" placeholder="alice
bob"></textarea>`;
  openModal("共享文件夹", body, isMine ? "保存名单" : "创建共享", async () => {
    const raw = ($("#share-members").value || "").split(/[\s,，、]+/).filter(Boolean);
    try {
      if (isMine) {
        await api("/api/shared/" + mineOne.id + "/members", {
          method: "POST", body: { members: raw },
        });
        toast("成员名单已更新");
      } else {
        await api("/api/shared/create", {
          method: "POST", body: { path: "/" + path, members: raw },
        });
        toast("已创建共享文件夹");
      }
      await refreshShared();
      refreshList();
    } catch (e) { toast(e.message, true); }
  });
}

async function refreshQuota() {
  try {
    quota = await api("/api/quota");
    const used = quota.used_bytes, total = quota.quota_bytes;
    const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
    $("#quota-text").textContent = `已用 ${fmtBytes(used)} / ${fmtBytes(total)}`;
    $("#quota-pct").textContent = `· ${pct.toFixed(pct >= 10 ? 0 : 1)}%`;
    const fill = $("#quota-fill");
    fill.style.width = pct + "%";
    fill.className = "quota-fill" + (pct >= 100 ? " full" : pct >= 85 ? " warn" : "");
  } catch { /* 静默 */ }
}

function renderCrumbs() {
  const nav = $("#crumbs");
  nav.innerHTML = "";
  const parts = curPath ? curPath.split("/") : [];
  const mk = (label, path, current, owner = curOwner) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "crumb" + (current ? " current" : "");
    b.textContent = label;
    b.addEventListener("click", () => { curPath = path; curOwner = owner; refreshList(); });
    return b;
  };
  if (curOwner) {
    // 别人的共享目录：第一格回到自己的网盘，第二格是共享根
    nav.appendChild(mk("我的网盘", "", false, ""));
    const sep0 = document.createElement("span");
    sep0.className = "crumb-sep";
    sep0.textContent = "›";
    nav.appendChild(sep0);
    nav.appendChild(mk(curOwner + " 的共享", "", parts.length === 0, curOwner));
    parts.forEach((p, i) => {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "›";
      nav.appendChild(sep);
      nav.appendChild(mk(p, parts.slice(0, i + 1).join("/"), i === parts.length - 1, curOwner));
    });
    return;
  }
  nav.appendChild(mk("我的网盘", "", parts.length === 0));
  parts.forEach((p, i) => {
    const sep = document.createElement("span");
    sep.className = "crumb-sep";
    sep.textContent = "›";
    nav.appendChild(sep);
    nav.appendChild(mk(p, parts.slice(0, i + 1).join("/"), i === parts.length - 1));
  });
}

let lastEntries = [];
async function refreshList() {
  // 导航离开加密文件夹 → 立即锁定（密钥只留在内存，离开即弃）
  if (vault && curPath !== vault.path) vault = null;
  renderCrumbs();
  $("#foreign-bar").classList.toggle("hidden", !curOwner);
  if (curOwner) $("#foreign-owner").textContent = curOwner;
  $("#list-loading").classList.remove("hidden");
  try {
    const data = await api("/api/files/list?path="
      + encodeURIComponent(curPath ? "/" + curPath : "") + ownerQS("&"));
    const entries = data.entries || [];
    lastEntries = entries;
    const isVaultRoot = !curOwner
      && entries.some((e) => e.type === "file" && e.name === ".sdvault.json");
    if (isVaultRoot) {
      vaultRootPath = curPath;
      vaultDirMarks.add(curPath);
      if (vault && vault.path === curPath) renderVaultEntries();
      else { vault = null; renderVaultLocked(); }
    } else {
      vaultRootPath = null;
      renderEntries(entries);
      probeVaultDirs(entries);
    }
    updateVaultChrome();
  } catch (e) {
    toast(e.message, true);
    renderEntries([]);
    updateVaultChrome();
  } finally {
    $("#list-loading").classList.add("hidden");
  }
}

/* 当前目录是否为加密文件夹根（锁定或已解锁）时，调整工具栏与横幅 */
function updateVaultChrome() {
  const atVault = vaultRootPath !== null && vaultRootPath === curPath;
  const unlocked = atVault && !!vault;
  $("#vault-bar").classList.toggle("hidden", !unlocked);
  $("#btn-mkdir").classList.toggle("hidden", atVault || !!curOwner);
  $("#btn-vault-new").classList.toggle("hidden", atVault || !!curOwner);
  $("#btn-upload").classList.toggle("hidden", atVault && !unlocked);
  $("#btn-upload-folder").classList.toggle("hidden", atVault && !unlocked);
  if (!atVault) $("#vault-lock").classList.add("hidden");
}

/* 探测子文件夹是否为加密文件夹（列表里加锁徽章）；只探一次并缓存 */
const probedDirs = new Set();
async function probeVaultDirs(entries) {
  for (const entry of entries) {
    if (entry.type !== "dir") continue;
    const rel = (curPath ? curPath + "/" : "") + entry.name;
    if (vaultDirMarks.has(rel) || probedDirs.has(rel)) continue;
    probedDirs.add(rel);
    try {
      const data = await api("/api/files/list?path=" + encodeURIComponent("/" + rel));
      if ((data.entries || []).some((e) => e.type === "file" && e.name === ".sdvault.json")) {
        vaultDirMarks.add(rel);
        if (curPath === (rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "")) {
          renderEntries(lastEntries); // 还在同一目录则刷新徽章
        }
      }
    } catch { /* 探测失败静默 */ }
  }
}

function renderEntries(entries) {
  const box = $("#file-list");
  box.innerHTML = "";
  $("#empty-state").classList.toggle("hidden", entries.length > 0);
  for (const entry of entries) {
    const { cls, svg } = iconFor(entry);
    const row = document.createElement("div");
    row.className = "row";
    const sizeText = entry.type === "dir" ? "—" : fmtBytes(entry.size);
    const timeText = fmtTime(entry.mtime);
    row.innerHTML = `
      <div class="row-main">
        <div class="file-icon ${cls}">${svg}</div>
        <div style="min-width:0">
          <div class="row-name">${esc(entry.name)}</div>
          <div class="row-sub">${entry.type === "dir" ? "文件夹" : sizeText} · ${fmtDate(entry.mtime)}</div>
        </div>
      </div>
      <span class="col-size">${sizeText}</span>
      <span class="col-time">${timeText}</span>
      <span class="col-act"></span>`;
    const rel = (curPath ? curPath + "/" : "") + entry.name;
    if (entry.type === "dir" && !curOwner && vaultDirMarks.has(rel)) {
      $(".file-icon", row).classList.add("vault-icon");
      $(".row-name", row).insertAdjacentHTML("beforeend",
        ' <span class="vault-badge">🔒 加密</span>');
      $(".row-sub", row).textContent = "加密文件夹 · 需密码打开";
    }
    const shared = entry.type === "dir" && !curOwner
      ? sharedMine.find((s) => s.path === rel) : null;
    if (shared) {
      $(".row-name", row).insertAdjacentHTML("beforeend",
        ' <span class="shared-badge">🔗 共享</span>');
    }
    const act = $(".col-act", row);
    if (entry.type === "file") {
      if (previewKind(entry.name)) {
        act.appendChild(actionBtn(ICONS.eye, "预览", () => openPreview(rel, entry)));
      }
      act.appendChild(actionBtn(ICONS.download, "下载", () => downloadFile(rel, entry.name)));
    }
    if (entry.type === "dir" && !curOwner && !vaultDirMarks.has(rel)) {
      act.appendChild(actionBtn(ICONS.share, shared ? "管理共享" : "共享此文件夹",
        () => openShareDialog(rel, shared)));
      if (shared) {
        act.appendChild(actionBtn(ICONS.unshare, "取消共享", () => revokeShare(shared), true));
      }
    }
    if (!curOwner) {
      act.appendChild(actionBtn(ICONS.rename, "重命名", () => renameItem(rel, entry.name)));
      act.appendChild(actionBtn(ICONS.move, "移动", () => moveItem(rel, entry.name)));
      act.appendChild(actionBtn(ICONS.trash, "删除", () => deleteItem(rel, entry.name), true));
    }
    row.addEventListener("click", (ev) => {
      if (ev.target.closest(".col-act")) return;
      if (entry.type === "dir") { curPath = rel; refreshList(); }
      else if (previewKind(entry.name)) openPreview(rel, entry);
      else downloadFile(rel, entry.name);
    });
    box.appendChild(row);
  }
}
function actionBtn(svg, title, fn, danger = false) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "icon-btn" + (danger ? " danger" : "");
  b.title = title;
  b.innerHTML = svg;
  b.addEventListener("click", (e) => { e.stopPropagation(); fn(); });
  return b;
}

async function downloadFile(rel, name) {
  try {
    const resp = await fetch("/api/files/download?path=" + encodeURIComponent("/" + rel) + ownerQS("&"), {
      headers: { Authorization: "Bearer " + token },
    });
    if (!resp.ok) {
      const d = await resp.json().catch(() => null);
      throw new Error((d && d.detail && d.detail.message) || "下载失败");
    }
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) { toast(e.message, true); }
}

/* ---- 弹窗 ---- */
let modalOkHandler = null;
function openModal(title, bodyHTML, okText, onOk, danger = false) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = bodyHTML;
  const ok = $("#modal-ok");
  ok.textContent = okText || "确定";
  ok.className = "btn-primary" + (danger ? " danger-btn" : "");
  modalOkHandler = onOk;
  $("#modal-overlay").classList.remove("hidden");
  const first = $("#modal-body input");
  if (first) { first.focus(); first.select(); }
}
function closeModal() { $("#modal-overlay").classList.add("hidden"); modalOkHandler = null; }
$("#modal-cancel").addEventListener("click", closeModal);
$("#modal-overlay").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeModal(); });
$("#modal-ok").addEventListener("click", async () => {
  if (!modalOkHandler) return closeModal();
  const ok = $("#modal-ok");
  ok.disabled = true;
  try { await modalOkHandler(); closeModal(); }
  catch (e) { toast(e.message, true); }
  finally { ok.disabled = false; }
});

function renameItem(rel, name) {
  openModal("重命名", `
    <label class="field"><span>新名称</span>
    <input id="m-name" type="text" value="${esc(name)}"></label>`,
    "保存", async () => {
      const newName = $("#m-name").value.trim();
      if (!newName || newName === name) return;
      await api("/api/files/rename", { method: "POST", body: { path: "/" + rel, new_name: newName } });
      toast("已重命名");
      refreshList();
    });
}
function deleteItem(rel, name) {
  openModal("删除", `<p class="modal-text">确定删除「${esc(name)}」吗？删除后文件会进入回收站，此操作无法在本页面撤销。</p>`,
    "删除", async () => {
      await api("/api/files/delete", { method: "POST", body: { path: "/" + rel } });
      toast("已删除");
      refreshList(); refreshQuota();
    }, true);
}
async function collectDirs() {
  const dirs = [""];
  async function walk(p) {
    const data = await api("/api/files/list?path=" + encodeURIComponent(p ? "/" + p : ""));
    for (const e of data.entries || []) {
      if (e.type === "dir") {
        const full = (p ? p + "/" : "") + e.name;
        dirs.push(full);
        await walk(full);
      }
    }
  }
  await walk("");
  return dirs;
}
async function moveItem(rel, name) {
  let dirs;
  try { dirs = await collectDirs(); } catch (e) { toast(e.message, true); return; }
  const srcDir = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
  dirs = dirs.filter((d) => d !== rel && d !== srcDir && !d.startsWith(rel + "/"));
  let chosen = "";
  openModal("移动到", `
    <p class="modal-text">把「${esc(name)}」移动到：</p>
    <div class="folder-pick">${dirs.map((d) =>
      `<button type="button" data-dir="${esc(d)}">📁 ${d === "" ? "我的网盘（根目录）" : esc("/" + d)}</button>`).join("")}
    </div>`, "移动", async () => {
      await api("/api/files/move", { method: "POST", body: { path: "/" + rel, dest_dir: chosen ? "/" + chosen : "" } });
      toast("已移动");
      refreshList();
    });
  $$("#modal-body .folder-pick button").forEach((b) => {
    if (b.dataset.dir === "") b.classList.add("selected");
    b.addEventListener("click", () => {
      chosen = b.dataset.dir;
      $$("#modal-body .folder-pick button").forEach((x) => x.classList.toggle("selected", x === b));
    });
  });
}

$("#btn-mkdir").addEventListener("click", () => {
  openModal("新建文件夹", `
    <label class="field"><span>文件夹名称</span>
    <input id="m-name" type="text" placeholder="例如：照片"></label>`,
    "创建", async () => {
      const name = $("#m-name").value.trim();
      if (!name) throw new Error("请输入名称");
      await api("/api/files/mkdir", { method: "POST", body: { path: curPath ? "/" + curPath : "", name } });
      toast("文件夹已创建");
      refreshList();
    });
});

$("#btn-chpw").addEventListener("click", () => {
  openModal("修改密码", `
    <label class="field"><span>当前密码</span><input id="m-old" type="password" autocomplete="current-password"></label>
    <label class="field"><span>新密码（至少 8 位）</span><input id="m-new" type="password" autocomplete="new-password"></label>`,
    "保存", async () => {
      await api("/api/auth/change-password", {
        method: "POST",
        body: { old_password: $("#m-old").value, new_password: $("#m-new").value },
      });
      toast("密码已修改，其他设备的登录已失效");
    });
});

/* ---- 上传 ----
 * 入队条目统一为 { file, relPath }：散文件 relPath 就是文件名；整文件夹上传时
 * relPath 是相对当前目录的完整相对路径（如 "照片/2026/a.jpg"）。目录计划
 * （相对路径 → 先建哪些目录、每个文件落到哪个目录）是纯逻辑，见
 * static/uploadplan.js（Node 测试：test_uploadplan.mjs）。 */
const uploadQueue = [];
let uploading = false;
let uploadsPendingRefresh = false; // 一批上传收尾后统一刷新列表 + 配额
const joinRel = (a, b) => (a && b ? a + "/" + b : a || b || "");

$("#btn-upload").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", (e) => {
  enqueueFiles([...e.target.files]);
  e.target.value = "";
});
$("#btn-upload-folder").addEventListener("click", () => $("#folder-input").click());
$("#folder-input").addEventListener("change", (e) => {
  const picked = [...e.target.files].map((f) => ({ file: f, relPath: f.webkitRelativePath || f.name }));
  e.target.value = "";
  enqueuePicked(picked);
});
const dz = $("#dropzone");
for (const ev of ["dragenter", "dragover"]) {
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragging"); });
}
for (const ev of ["dragleave", "drop"]) {
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    if (ev === "dragleave" && dz.contains(e.relatedTarget)) return;
    dz.classList.remove("dragging");
    if (ev === "drop") handleDrop(e.dataTransfer);
  });
}

/* 拖放：webkitGetAsEntry 必须在 drop 事件内同步调用（事件结束后条目即失效），
 * 目录遍历是异步的；不支持该 API 时回退为只收散文件（与旧行为一致）。 */
function handleDrop(dt) {
  if (!dt) return;
  const items = dt.items ? [...dt.items].filter((i) => i.kind === "file") : [];
  const entries = items.map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null));
  if (!items.length || entries.some((en) => en === null)) {
    enqueueFiles([...(dt.files || [])]);
    return;
  }
  collectDroppedEntries(entries)
    .then(({ files, dirs }) => enqueuePicked(files, dirs))
    .catch(() => enqueueFiles([...(dt.files || [])]));
}
async function collectDroppedEntries(rootEntries) {
  const files = [];
  const dirs = [];
  async function walk(entry, prefix) {
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej));
      files.push({ file, relPath: prefix + entry.name });
    } else if (entry.isDirectory) {
      const rel = prefix + entry.name;
      dirs.push(rel);
      const reader = entry.createReader();
      for (;;) { // readEntries 每批只返回一部分，必须读到空为止
        const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const child of batch) await walk(child, rel + "/");
      }
    }
  }
  for (const en of rootEntries) await walk(en, "");
  return { files, dirs };
}

/* 散文件入口（文件按钮 / 拖放回退）：relPath 即文件名，行为与旧版一致 */
function enqueueFiles(files) {
  enqueuePicked(files.map((f) => ({ file: f, relPath: f.name })));
}

/* 统一入队：加密文件夹根只收散文件（本地加密上传），带目录的内容跳过并说明；
 * 一般目录交给 enqueuePlanned 按计划先建目录、再逐个文件上传。 */
function enqueuePicked(entries, extraDirs = []) {
  if (!entries.length && !extraDirs.length) return;
  // 加密文件夹：已解锁走本地加密上传；未解锁直接拒绝（绝不允许明文落进去）
  if (vaultRootPath !== null && vaultRootPath === curPath) {
    const loose = entries.filter((en) => !en.relPath.includes("/"));
    const withDirs = entries.length - loose.length;
    if (vault && vault.path === curPath) {
      if (withDirs || extraDirs.length) toast("加密文件夹暂不支持整文件夹上传，已跳过文件夹内容", true);
      if (loose.length) vaultEnqueueFiles(loose.map((en) => en.file));
    } else {
      toast("加密文件夹已锁定，请先解锁再上传", true);
    }
    return;
  }
  enqueuePlanned(entries, extraDirs);
}

/* 确保单个目录存在（幂等）：
 * - stub 存储：已存在 → mkdir 接口回 409 conflict，视为成功；
 * - live（Seafile）：存储层把 Seafile 的报错包成了 502，无法凭状态码区分，
 *   故失败后用列表接口核对：目录确实已在就算成功，否则抛原始错误。 */
async function ensureDirOnce(parentRel, name) {
  try {
    await api("/api/files/mkdir", { method: "POST", body: { path: parentRel ? "/" + parentRel : "", name } });
    return;
  } catch (e) {
    if (e.status === 409 || e.code === "conflict") return;
    try {
      const data = await api("/api/files/list?path=" + encodeURIComponent(parentRel ? "/" + parentRel : ""));
      if ((data.entries || []).some((en) => en.type === "dir" && en.name === name)) return;
    } catch { /* 列表也失败时，抛原始 mkdir 错误 */ }
    throw e;
  }
}

/* 按目录计划入队：每个文件的目标目录在入队这一刻定死并写进队列项，
 * 之后用户再怎么切换文件夹，都不会把文件传错地方。建目录失败只影响
 * 其子树下的文件（逐个在面板里报错），不中断整批。 */
async function enqueuePlanned(entries, extraDirs = []) {
  const baseDir = curPath; // 入队时的当前目录即基准目录，本批不再受导航影响
  const plan = SubDriveUpload.planFolderUpload(
    entries.map((en) => ({ relPath: en.relPath, ref: en.file })), extraDirs);
  if (!plan.files.length && !plan.dirs.length) return;
  if (plan.files.length) $("#upload-panel").classList.remove("hidden");
  const rows = plan.files.map((pf) => {
    const item = document.createElement("div");
    item.className = "upload-item";
    item.innerHTML = `<div class="u-name">${esc(pf.relPath)}</div>
      <div class="u-bar"><div class="u-fill"></div></div>
      <div class="u-state">排队中…</div>`;
    $("#upload-items").appendChild(item);
    return { pf, item };
  });
  // 先自上而下建目录（plan.dirs 已保证父先于子）；某目录失败会传染其所有子目录
  const dirErrors = new Map();
  for (const dirRel of plan.dirs) {
    const segs = dirRel.split("/");
    let inherited = null;
    for (let i = 1; i < segs.length; i++) {
      const anc = segs.slice(0, i).join("/");
      if (dirErrors.has(anc)) { inherited = dirErrors.get(anc); break; }
    }
    if (inherited) { dirErrors.set(dirRel, inherited); continue; }
    const cut = dirRel.lastIndexOf("/");
    const parentRel = cut < 0 ? baseDir : joinRel(baseDir, dirRel.slice(0, cut));
    try {
      await ensureDirOnce(parentRel, segs[segs.length - 1]);
    } catch (e) {
      dirErrors.set(dirRel, e.message || "创建文件夹失败");
    }
  }
  if (!rows.length) { // 只拖入了空文件夹：目录已建好，给个明确反馈
    if (dirErrors.size) toast(`创建文件夹失败：${[...dirErrors.values()][0]}`, true);
    else toast("文件夹已创建");
    refreshList();
    return;
  }
  for (const { pf, item } of rows) {
    const failMsg = pf.dirRel ? dirErrors.get(pf.dirRel) : null;
    if (failMsg) {
      item.classList.add("failed");
      $(".u-state", item).textContent = failMsg;
      toast(`${pf.relPath}：${failMsg}`, true);
      uploadsPendingRefresh = true;
      continue;
    }
    uploadQueue.push({ file: pf.ref, item, targetDir: joinRel(baseDir, pf.dirRel), owner: curOwner });
  }
  pumpUploads();
}
function pumpUploads() {
  if (uploading) return;
  const next = uploadQueue.shift();
  if (!next) { // 队列排空：一批结束，统一刷新一次列表与配额
    if (uploadsPendingRefresh) { uploadsPendingRefresh = false; refreshList(); refreshQuota(); }
    return;
  }
  uploading = true;
  uploadOne(next).finally(() => { uploading = false; pumpUploads(); });
}
function uploadOne({ file, item, targetDir, owner }) {
  return new Promise((resolve) => {
    const fill = $(".u-fill", item);
    const state = $(".u-state", item);
    state.textContent = "上传中…";
    const xhr = new XMLHttpRequest();
    // 目标目录用入队时定死的 targetDir/owner，不读实时 curPath，避免上传途中导航传错地方
    xhr.open("POST", "/api/files/upload?path=" + encodeURIComponent(targetDir ? "/" + targetDir : "")
      + (owner ? "&owner=" + encodeURIComponent(owner) : ""));
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        fill.style.width = pct + "%";
        state.textContent = `上传中 ${pct}% · ${fmtBytes(file.size)}`;
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        fill.style.width = "100%";
        item.classList.add("done");
        state.textContent = "完成 ✓";
      } else {
        item.classList.add("failed");
        let msg = "上传失败";
        try { const d = JSON.parse(xhr.responseText); msg = (d.detail && d.detail.message) || d.message || msg; } catch { }
        state.textContent = msg;
        toast(`${file.name}：${msg}`, true);
      }
      uploadsPendingRefresh = true;
      resolve();
    });
    xhr.addEventListener("error", () => {
      item.classList.add("failed");
      state.textContent = "网络错误";
      uploadsPendingRefresh = true;
      resolve();
    });
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}
$("#upload-close").addEventListener("click", () => {
  $("#upload-panel").classList.add("hidden");
  $("#upload-items").innerHTML = "";
});

/* ================= 加密文件夹（SDV1） =================
 * 浏览器内加解密（static/vault.js）；服务器只存密文 blob，
 * 文件名只存在于加密清单里。密钥只在内存，导航离开/锁定即弃。 */
async function rawDownloadBytes(rel) {
  const resp = await fetch("/api/files/download?path=" + encodeURIComponent("/" + rel), {
    headers: { Authorization: "Bearer " + token },
  });
  if (!resp.ok) {
    const d = await resp.json().catch(() => null);
    throw new Error((d && d.detail && d.detail.message) || "读取失败");
  }
  return new Uint8Array(await resp.arrayBuffer());
}
async function uploadBytes(dirRel, filename, bytes) {
  const fd = new FormData();
  fd.append("file", new Blob([bytes]), filename);
  const resp = await fetch("/api/files/upload?path=" + encodeURIComponent(dirRel ? "/" + dirRel : ""), {
    method: "POST", headers: { Authorization: "Bearer " + token }, body: fd,
  });
  if (!resp.ok) {
    const d = await resp.json().catch(() => null);
    throw new Error((d && d.detail && d.detail.message) || `上传失败 (${resp.status})`);
  }
  return resp.json();
}
async function saveVaultManifest() {
  const blob = await SDVault.encryptBlob(vault.key, SDVault.serializeManifest(vault.manifest));
  await uploadBytes(vault.path, "manifest.enc", blob);
}

function renderVaultLocked() {
  $("#file-list").innerHTML = "";
  $("#empty-state").classList.add("hidden");
  $("#vault-lock").classList.remove("hidden");
}
function renderVaultEntries() {
  $("#vault-lock").classList.add("hidden");
  const box = $("#file-list");
  box.innerHTML = "";
  const files = vault.manifest.files;
  $("#empty-state").classList.toggle("hidden", files.length > 0);
  for (const f of files) {
    const { cls, svg } = iconFor({ type: "file", name: f.name });
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="row-main">
        <div class="file-icon ${cls}">${svg}</div>
        <div style="min-width:0">
          <div class="row-name">🔒 ${esc(f.name)}</div>
          <div class="row-sub">${fmtBytes(f.size)} · ${fmtDate(f.added_at)}</div>
        </div>
      </div>
      <span class="col-size">${fmtBytes(f.size)}</span>
      <span class="col-time">${fmtTime(f.added_at)}</span>
      <span class="col-act"></span>`;
    const act = $(".col-act", row);
    if (previewKind(f.name)) {
      act.appendChild(actionBtn(ICONS.eye, "预览（本地解密）", () => openVaultPreview(f)));
    }
    act.appendChild(actionBtn(ICONS.download, "下载并解密", () => vaultDownload(f)));
    act.appendChild(actionBtn(ICONS.rename, "重命名", () => vaultRename(f)));
    act.appendChild(actionBtn(ICONS.trash, "删除", () => vaultDelete(f), true));
    row.addEventListener("click", (ev) => {
      if (ev.target.closest(".col-act")) return;
      if (previewKind(f.name)) openVaultPreview(f);
      else vaultDownload(f);
    });
    box.appendChild(row);
  }
}

async function attemptUnlock(password) {
  const rel = vaultRootPath;
  const descBytes = await rawDownloadBytes(rel + "/.sdvault.json");
  const descriptor = SDVault.parseDescriptor(new TextDecoder().decode(descBytes));
  const key = await SDVault.unlockWithPassword(descriptor, password); // 密码错误在此抛错
  const manBytes = await rawDownloadBytes(rel + "/manifest.enc");
  const manifest = SDVault.parseManifest(await SDVault.decryptBlob(key, manBytes));
  vault = { path: rel, key, manifest };
  await refreshList();
  toast("加密文件夹已解锁");
}
$("#btn-vault-unlock").addEventListener("click", () => {
  openModal("解锁加密文件夹", `
    <label class="field"><span>文件夹密码</span>
    <input id="m-vpass" type="password" autocomplete="off" placeholder="创建时设置的文件夹密码"></label>
    <p class="modal-text">密码只在你的浏览器里用于解密，不会发送到服务器；密码错误将无法打开。</p>`,
    "解锁", async () => {
      const pw = $("#m-vpass").value;
      if (!pw) throw new Error("请输入文件夹密码");
      try {
        await attemptUnlock(pw);
      } catch (e) {
        throw new Error(e.message === "文件夹密码错误" ? "文件夹密码错误，请重试" : e.message);
      }
    });
});
$("#btn-vault-lock").addEventListener("click", () => {
  vault = null;
  refreshList();
  toast("已锁定，密钥已从内存清除");
});

$("#btn-vault-new").addEventListener("click", () => {
  openModal("新建加密文件夹", `
    <label class="field"><span>文件夹名称</span>
    <input id="m-vname" type="text" placeholder="例如：证件与合同"></label>
    <label class="field"><span>文件夹密码（至少 8 位，与登录密码相互独立）</span>
    <input id="m-vpass" type="password" autocomplete="new-password"></label>
    <label class="field"><span>再次输入密码</span>
    <input id="m-vpass2" type="password" autocomplete="new-password"></label>
    <p class="modal-text warn-text">⚠️ 文件名和内容会在你的浏览器里加密后才上传，服务器只看得到密文的大小与数量。
    <strong>文件夹密码一旦丢失将无法恢复，里面的数据会永久无法打开</strong>——任何人（包括我们）都无法帮你找回，请务必牢记或存入密码管理器。</p>`,
    "创建加密文件夹", async () => {
      const name = $("#m-vname").value.trim();
      const p1 = $("#m-vpass").value, p2 = $("#m-vpass2").value;
      if (!name) throw new Error("请输入文件夹名称");
      if (p1.length < 8) throw new Error("文件夹密码至少 8 位");
      if (p1 !== p2) throw new Error("两次输入的密码不一致");
      await createVault(name, p1);
      toast("加密文件夹已创建并解锁");
    });
});
async function createVault(name, password) {
  await api("/api/files/mkdir", { method: "POST", body: { path: curPath ? "/" + curPath : "", name } });
  const rel = (curPath ? curPath + "/" : "") + name;
  const { descriptor, key } = await SDVault.createDescriptor(password);
  await uploadBytes(rel, ".sdvault.json",
    new TextEncoder().encode(JSON.stringify(descriptor, null, 2)));
  await api("/api/files/mkdir", { method: "POST", body: { path: "/" + rel, name: "blobs" } });
  vault = { path: rel, key, manifest: SDVault.emptyManifest() };
  await saveVaultManifest();
  vaultDirMarks.add(rel);
  curPath = rel;
  await refreshList();
  refreshQuota();
}

async function vaultEnqueueFiles(files) {
  $("#upload-panel").classList.remove("hidden");
  for (const file of files) {
    const item = document.createElement("div");
    item.className = "upload-item";
    item.innerHTML = `<div class="u-name">🔒 ${esc(file.name)}</div>
      <div class="u-bar"><div class="u-fill"></div></div>
      <div class="u-state">排队中…</div>`;
    $("#upload-items").appendChild(item);
    try {
      await vaultEncryptUpload(file, item);
    } catch (e) {
      item.classList.add("failed");
      $(".u-state", item).textContent = e.message;
      toast(`${file.name}：${e.message}`, true);
    }
  }
  refreshQuota();
}
async function vaultEncryptUpload(file, item) {
  const state = $(".u-state", item);
  const fill = $(".u-fill", item);
  state.textContent = "本地加密中…";
  const plain = new Uint8Array(await file.arrayBuffer());
  const blob = await SDVault.encryptBlob(vault.key, plain);
  fill.style.width = "45%";
  state.textContent = "上传密文中…";
  const id = SDVault.randomId();
  await uploadBytes(vault.path + "/blobs", id + ".enc", blob); // 先 blob 后清单（CRYPTO.md §6）
  fill.style.width = "80%";
  state.textContent = "写入清单…";
  vault.manifest.files.push({
    id, name: file.name, size: plain.length,
    mime: file.type || "application/octet-stream",
    added_at: new Date().toISOString(),
  });
  await saveVaultManifest();
  fill.style.width = "100%";
  item.classList.add("done");
  state.textContent = "完成 ✓（已加密）";
  renderVaultEntries();
}
async function vaultDownload(entry) {
  try {
    const blobBytes = await rawDownloadBytes(vault.path + "/blobs/" + entry.id + ".enc");
    const plain = await SDVault.decryptBlob(vault.key, blobBytes);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([plain], { type: entry.mime || "application/octet-stream" }));
    a.download = entry.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) {
    toast("下载/解密失败：" + e.message, true);
  }
}
function vaultRename(entry) {
  openModal("重命名（仅修改显示名）", `
    <label class="field"><span>新名称</span>
    <input id="m-name" type="text" value="${esc(entry.name)}"></label>
    <p class="modal-text">显示名只存在于加密清单中，改名不触碰服务器上的密文。</p>`,
    "保存", async () => {
      const nn = $("#m-name").value.trim();
      if (!nn || nn === entry.name) return;
      entry.name = nn;
      await saveVaultManifest();
      toast("已重命名");
      renderVaultEntries();
    });
}
function vaultDelete(entry) {
  openModal("删除加密文件", `
    <p class="modal-text">确定删除「${esc(entry.name)}」吗？其密文将被删除，无法恢复。</p>`,
    "删除", async () => {
      vault.manifest.files = vault.manifest.files.filter((f) => f.id !== entry.id);
      await saveVaultManifest(); // 先改清单，再删 blob（CRYPTO.md §6）
      try {
        await api("/api/files/delete", {
          method: "POST",
          body: { path: "/" + vault.path + "/blobs/" + entry.id + ".enc" },
        });
      } catch { /* 孤儿 blob 由用量校准兜底 */ }
      toast("已删除");
      renderVaultEntries();
      refreshQuota();
    }, true);
}

/* ================= 文件预览 =================
 * 预览与下载走同一条后端路径安全链（/api/files/preview），
 * 媒体类用 ?token= 直链 + HTTP Range 播放；文本/Markdown 经 fetch 取回后本地渲染。
 * Markdown 渲染器先整体转义再套语法，原始 HTML 永远进不了 DOM。 */
const PREVIEW_TEXT_CAP = 512 * 1024;
function previewKind(name) {
  const ext = extOf(name);
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "avif", "ico"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  if (["mp4", "webm", "mov", "m4v"].includes(ext)) return "video";
  if (["mp3", "wav", "flac", "m4a", "ogg", "aac", "opus"].includes(ext)) return "audio";
  if (ext === "md" || ext === "markdown") return "markdown";
  if (["txt", "log", "json", "csv", "js", "ts", "tsx", "jsx", "py", "html", "css", "sh",
       "go", "rs", "java", "c", "h", "cpp", "sql", "yml", "yaml", "toml", "xml", "ini", "conf"]
      .includes(ext)) return "text";
  return null;
}
let previewCtx = null; // {rel,name} 普通文件 | {vaultEntry,name} 加密文件；objectUrl 待释放
function setPreviewContent(html) { $("#preview-body").innerHTML = html; }
function previewFallbackHtml(entry) {
  const big = entry && entry.size > PREVIEW_TEXT_CAP;
  return `<div class="pv-fallback"><div class="pv-fallback-icon">${ICONS.file}</div>
    <p>${big ? "文本文件过大，不适合在线预览。" : "该文件无法在线预览。"}</p>
    <p class="pv-fallback-sub">可以点右上角「下载」保存到本地查看。</p></div>`;
}
function closePreview() {
  $("#preview-overlay").classList.add("hidden");
  setPreviewContent(""); // 清空即停掉音视频
  if (previewCtx && previewCtx.objectUrl) URL.revokeObjectURL(previewCtx.objectUrl);
  previewCtx = null;
}
$("#preview-close").addEventListener("click", closePreview);
$("#preview-overlay").addEventListener("click", (e) => { if (e.target === e.currentTarget) closePreview(); });
$("#preview-download").addEventListener("click", () => {
  if (!previewCtx) return;
  if (previewCtx.vaultEntry) vaultDownload(previewCtx.vaultEntry);
  else downloadFile(previewCtx.rel, previewCtx.name);
});

function fillMediaPreview(kind, name, url) {
  if (kind === "image") setPreviewContent(`<img class="pv-img" src="${url}" alt="${esc(name)}">`);
  else if (kind === "pdf") setPreviewContent(`<iframe class="pv-frame" src="${url}" title="${esc(name)}"></iframe>`);
  else if (kind === "video") setPreviewContent(`<video class="pv-media" src="${url}" controls playsinline></video>`);
  else if (kind === "audio") setPreviewContent(
    `<div class="pv-audio"><div class="pv-audio-icon">${ICONS.audio}</div><audio src="${url}" controls></audio></div>`);
}
function fillTextPreview(kind, text) {
  if (kind === "markdown") setPreviewContent(`<div class="md-body">${renderMarkdown(text)}</div>`);
  else setPreviewContent(`<pre class="pv-text"><code>${esc(text)}</code></pre>`);
}
async function openPreview(rel, entry) {
  const kind = previewKind(entry.name);
  if (!kind) return downloadFile(rel, entry.name);
  previewCtx = { rel, name: entry.name };
  $("#preview-title").textContent = entry.name;
  $("#preview-overlay").classList.remove("hidden");
  if (kind === "text" || kind === "markdown") {
    if (entry.size > PREVIEW_TEXT_CAP) { setPreviewContent(previewFallbackHtml(entry)); return; }
    setPreviewContent('<div class="list-loading">加载中…</div>');
    try {
      const resp = await fetch("/api/files/preview?path=" + encodeURIComponent("/" + rel) + ownerQS("&"), {
        headers: { Authorization: "Bearer " + token },
      });
      if (!resp.ok) throw new Error("预览加载失败");
      fillTextPreview(kind, await resp.text());
    } catch { setPreviewContent(previewFallbackHtml(entry)); }
    return;
  }
  const url = "/api/files/preview?path=" + encodeURIComponent("/" + rel) + ownerQS("&") +
              "&token=" + encodeURIComponent(token);
  fillMediaPreview(kind, entry.name, url);
}
async function openVaultPreview(entry) {
  const kind = previewKind(entry.name);
  if (!kind) return vaultDownload(entry);
  previewCtx = { vaultEntry: entry, name: entry.name };
  $("#preview-title").textContent = "🔒 " + entry.name;
  $("#preview-overlay").classList.remove("hidden");
  setPreviewContent('<div class="list-loading">本地解密中…</div>');
  try {
    const blobBytes = await rawDownloadBytes(vault.path + "/blobs/" + entry.id + ".enc");
    const plain = await SDVault.decryptBlob(vault.key, blobBytes);
    if (kind === "text" || kind === "markdown") {
      if (plain.length > PREVIEW_TEXT_CAP) { setPreviewContent(previewFallbackHtml(entry)); return; }
      fillTextPreview(kind, new TextDecoder().decode(plain));
    } else {
      const url = URL.createObjectURL(new Blob([plain], { type: entry.mime || "application/octet-stream" }));
      previewCtx.objectUrl = url;
      fillMediaPreview(kind, entry.name, url);
    }
  } catch (e) {
    toast("预览解密失败：" + e.message, true);
    closePreview();
  }
}

/* ---- 极简 Markdown 渲染：先转义、后语法；链接仅放行 http/https/mailto ---- */
function isSafeLink(url) { return /^(https?:\/\/|mailto:)/i.test(url); }
function mdInline(t) {
  t = esc(t);
  t = t.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) =>
    isSafeLink(url) ? `<img alt="${alt}" src="${url}" loading="lazy">` : m);
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) =>
    isSafeLink(url) ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${txt}</a>` : txt);
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  t = t.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  return t;
}
function renderMarkdown(src) {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0, inUl = false, inOl = false;
  const closeLists = () => {
    if (inUl) { out.push("</ul>"); inUl = false; }
    if (inOl) { out.push("</ol>"); inOl = false; }
  };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      closeLists();
      const buf = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      out.push(`<pre class="md-code"><code>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { closeLists(); out.push(`<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { closeLists(); out.push("<hr>"); i++; continue; }
    const q = line.match(/^>\s?(.*)$/);
    if (q) { closeLists(); out.push(`<blockquote>${mdInline(q[1])}</blockquote>`); i++; continue; }
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    if (ul) {
      if (!inUl) { closeLists(); out.push("<ul>"); inUl = true; }
      out.push(`<li>${mdInline(ul[1])}</li>`); i++; continue;
    }
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ol) {
      if (!inOl) { closeLists(); out.push("<ol>"); inOl = true; }
      out.push(`<li>${mdInline(ol[1])}</li>`); i++; continue;
    }
    if (line.trim() === "") { closeLists(); i++; continue; }
    closeLists();
    out.push(`<p>${mdInline(line)}</p>`);
    i++;
  }
  closeLists();
  return out.join("\n");
}

/* ================= 上下行测速 ================= */
$("#btn-speed").addEventListener("click", () => {
  $("#speed-panel").classList.remove("hidden");
  $("#speed-note").textContent = me && me.storage_mode === "live"
    ? "经后端流式转发实测，与实际上传/下载走同一条链路；测速流量不占配额、不存文件。"
    : "⚠️ 当前为本地测试链路（stub 假存储）：测的是这台机器到后端的速度，不代表真实 Seafile / e2 的速度。测速流量不占配额。";
});
$("#speed-close").addEventListener("click", () => $("#speed-panel").classList.add("hidden"));

function fmtSpeed(bytes, seconds) {
  if (!seconds || seconds <= 0) return "—";
  const mbps = (bytes * 8) / seconds / 1e6;
  const mbs = bytes / seconds / 1048576;
  return `${mbs.toFixed(2)} MB/s · ${mbps.toFixed(1)} Mbps`;
}
$("#speed-run").addEventListener("click", async () => {
  const btn = $("#speed-run");
  const mb = Number($("#speed-size").value || 25);
  const total = mb * 1024 * 1024;
  const dFill = $("#speed-down-fill"), uFill = $("#speed-up-fill");
  const dVal = $("#speed-down-val"), uVal = $("#speed-up-val");
  const result = $("#speed-result");
  btn.disabled = true;
  dFill.style.width = "0%"; uFill.style.width = "0%";
  dVal.textContent = "测速中…"; uVal.textContent = "等待下载完成…";
  result.textContent = "";
  const stamp = new Date().toLocaleString();
  try {
    // 下载：流式读满并计字节
    const t0 = performance.now();
    const resp = await fetch(`/api/speed/download?mb=${mb}`, {
      headers: { Authorization: "Bearer " + token },
    });
    if (!resp.ok) {
      const d = await resp.json().catch(() => null);
      throw new Error((d && d.detail && d.detail.message) || `下载测速失败 (${resp.status})`);
    }
    const reader = resp.body.getReader();
    let got = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      got += value.length;
      dFill.style.width = Math.min(100, (got / total) * 100) + "%";
    }
    const downSec = (performance.now() - t0) / 1000;
    dVal.textContent = fmtSpeed(got, downSec);
    // 上传：生成等量数据，XHR 报进度；服务器只数不存
    uVal.textContent = "测速中…";
    const payload = new Uint8Array(total);
    for (let i = 0; i < total; i += 65536) {
      const chunk = payload.subarray(i, Math.min(total, i + 65536));
      for (let j = 0; j < chunk.length; j++) chunk[j] = (i + j) % 251;
    }
    const up = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const start = performance.now();
      xhr.open("POST", "/api/speed/upload");
      xhr.setRequestHeader("Authorization", "Bearer " + token);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) uFill.style.width = (e.loaded / e.total) * 100 + "%";
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve({ sec: (performance.now() - start) / 1000, resp: JSON.parse(xhr.responseText) });
        } else {
          let msg = `上传测速失败 (${xhr.status})`;
          try { const d = JSON.parse(xhr.responseText); msg = (d.detail && d.detail.message) || msg; } catch { }
          reject(new Error(msg));
        }
      });
      xhr.addEventListener("error", () => reject(new Error("上传测速网络错误")));
      xhr.send(new Blob([payload]));
    });
    uFill.style.width = "100%";
    uVal.textContent = fmtSpeed(up.resp.received_bytes, up.sec);
    result.innerHTML =
      `下载 ${fmtSpeed(got, downSec)}（${fmtBytes(got)}）<br>` +
      `上传 ${fmtSpeed(up.resp.received_bytes, up.sec)}（服务器确认收到 ${fmtBytes(up.resp.received_bytes)}，未存盘）<br>` +
      `<span class="speed-stamp">${stamp}</span>`;
  } catch (e) {
    result.textContent = "";
    toast(e.message, true);
    dVal.textContent = "—"; uVal.textContent = "—";
  } finally {
    btn.disabled = false;
  }
});

/* ---------------- 管理后台 ---------------- */
$("#btn-admin").addEventListener("click", () => { show("view-admin"); loadAdmin(); });
$("#btn-back-drive").addEventListener("click", () => { show("view-drive"); refreshList(); refreshQuota(); });

$("#form-invite").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/admin/invite-codes", {
      method: "POST",
      body: {
        note: $("#inv-note").value.trim(),
        expires_days: Number($("#inv-days").value || 7),
        max_uses: Number($("#inv-uses").value || 1),
      },
    });
    $("#new-code-text").textContent = data.code;
    $("#new-code-box").classList.remove("hidden");
    $("#inv-note").value = "";
    loadInvites();
  } catch (err) { toast(err.message, true); }
});
$("#btn-copy-code").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#new-code-text").textContent); toast("已复制"); }
  catch { toast("复制失败，请手动复制", true); }
});

function pillFor(status, usedCount, maxUses) {
  if (status === "active") return '<span class="pill ok">可用</span>';
  if (status === "used_up") return '<span class="pill mut">已用完</span>';
  if (status === "revoked") return '<span class="pill off">已撤销</span>';
  if (status === "expired") return '<span class="pill warn">已过期</span>';
  return `<span class="pill mut">${esc(status)}</span>`;
}
async function loadInvites() {
  const rows = await api("/api/admin/invite-codes");
  const tb = $("#invite-table tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${esc(r.code)}</code></td>
      <td>${esc(r.note || "—")}</td>
      <td>${pillFor(r.status, r.used_count, r.max_uses)}</td>
      <td>${r.used_count} / ${r.max_uses}</td>
      <td>${r.expires_at ? fmtTime(r.expires_at) : "永久"}</td>
      <td>${r.status === "active" ? `<button class="mini-btn danger" data-revoke="${r.id}">撤销</button>` : ""}</td>`;
    tb.appendChild(tr);
  }
  $$("[data-revoke]", tb).forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/api/admin/invite-codes/${b.dataset.revoke}/revoke`, { method: "POST" });
      toast("邀请码已撤销");
      loadInvites();
    } catch (e) { toast(e.message, true); }
  }));
}
async function loadUsers() {
  const [users, usage] = await Promise.all([api("/api/admin/users"), api("/api/admin/usage")]);
  const adminCount = users.filter((x) => x.is_admin).length;
  $("#admin-total").textContent = `全员总用量 ${fmtBytes(usage.total_used_bytes)}`;
  const tb = $("#user-table tbody");
  tb.innerHTML = "";
  for (const u of users) {
    const tr = document.createElement("tr");
    const pct = u.quota_bytes ? Math.min(100, Math.round((u.used_bytes / u.quota_bytes) * 100)) : 0;
    tr.innerHTML = `
      <td><div class="user-cell"><div class="avatar">${esc((u.nickname || u.username).slice(0, 1))}</div>
        <div>${esc(u.nickname || u.username)}${u.is_admin ? ' <span class="pill warn">管理员</span>' : ""}
        <small>@${esc(u.username)}</small></div></div></td>
      <td>${u.status === "active" ? '<span class="pill ok">正常</span>' : '<span class="pill off">已禁用</span>'}</td>
      <td class="usage-cell">${fmtBytes(u.used_bytes)} <span class="of">/ ${fmtBytes(u.quota_bytes)}（${pct}%）</span></td>
      <td>${u.last_login_at ? fmtTime(u.last_login_at) : "从未"}</td>
      <td></td>`;
    const act = tr.lastElementChild;
    const mkBtn = (label, fn, danger = false) => {
      const b = document.createElement("button");
      b.className = "mini-btn" + (danger ? " danger" : "");
      b.textContent = label;
      b.addEventListener("click", fn);
      act.appendChild(b);
    };
    mkBtn("设配额", async () => {
      openModal(`设置配额 · ${u.username}`, `
        <label class="field"><span>配额（GB，留空 = 系统默认）</span>
        <input id="m-gb" type="number" min="0" step="0.5" value="${u.quota_bytes ? (u.quota_bytes / 1073741824) : ""}"></label>`,
        "保存", async () => {
          const v = $("#m-gb").value;
          const bytes = v === "" ? null : Math.round(Number(v) * 1073741824);
          await api(`/api/admin/users/${u.id}/quota`, { method: "POST", body: { quota_bytes: bytes } });
          toast("配额已更新");
          loadUsers();
        });
    });
    mkBtn("校准", async () => {
      try {
        const r = await api(`/api/admin/users/${u.id}/recalibrate`, { method: "POST" });
        toast(`校准完成：${fmtBytes(r.used_bytes)}`);
        loadUsers();
      } catch (e) { toast(e.message, true); }
    });
    if (me && me.is_owner) {
      if (!u.is_admin) {
        mkBtn("设为管理员", async () => {
          openModal("设为管理员", `<p class="modal-text">将「${esc(u.username)}」设为管理员后，对方将能访问管理后台、管理用户与邀请码。确定吗？</p>`,
            "设为管理员", async () => {
              await api(`/api/admin/users/${u.id}/admin`, { method: "POST", body: { is_admin: true } });
              toast("已设为管理员");
              loadUsers();
            });
        });
      } else if (!u.is_owner && adminCount > 1) {
        mkBtn("取消管理员", async () => {
          openModal("取消管理员", `<p class="modal-text">取消「${esc(u.username)}」的管理员权限后，对方将无法访问管理后台。确定吗？</p>`,
            "取消管理员", async () => {
              await api(`/api/admin/users/${u.id}/admin`, { method: "POST", body: { is_admin: false } });
              toast("已取消管理员");
              loadUsers();
            }, true);
        }, true);
      }
    }
    if (u.status === "active") {
      mkBtn("禁用", async () => {
        openModal("禁用用户", `<p class="modal-text">禁用「${esc(u.username)}」后，其所有登录立即失效，但文件会保留。确定禁用吗？</p>`,
          "禁用", async () => {
            await api(`/api/admin/users/${u.id}/disable`, { method: "POST" });
            toast("已禁用");
            loadUsers();
          }, true);
      }, true);
    } else {
      mkBtn("启用", async () => {
        await api(`/api/admin/users/${u.id}/enable`, { method: "POST" });
        toast("已启用");
        loadUsers();
      });
    }
    tb.appendChild(tr);
  }
}
async function loadAdmin() {
  try { await Promise.all([loadInvites(), loadUsers()]); }
  catch (e) { toast(e.message, true); }
}

/* ---------------- 启动 ---------------- */
(async function boot() {
  if (token) {
    try { await enterDrive(); return; } catch { /* 落到登录页 */ }
  }
  show("view-auth");
})();
