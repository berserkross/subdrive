"use strict";
/* ================= SubDrive 前端 ================= */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

/* ---------------- 国际化 ---------------- */
// 语言存在 localStorage，刷新后保持；任何非法值（含旧数据）都回落中文。
let lang = localStorage.getItem("subdrive_lang") === "en" ? "en" : "zh";
// 字典按「屏」分组，key 用点分命名；zh 是基准，en 必须与之等长（tests/e2e 会校验）。
const I18N = {
  zh: {
    "app.title": "SubDrive · 子用户网盘",
    "req.failed": "请求失败 ({status})",
    "lang.switch": "切换语言",

    "auth.brand": "子用户网盘",
    "auth.tag1": "你的私人文件空间",
    "auth.tag2": "简单、安全、随时取用",
    "auth.tabLogin": "登录",
    "auth.tabRegister": "注册",
    "auth.username": "用户名",
    "auth.password": "密码",
    "auth.phUsername": "你的用户名",
    "auth.login": "登 录",
    "auth.loginHint": "还没有账号？用邀请码在「注册」页开通。",
    "auth.invite": "邀请码",
    "auth.phInvite": "SD-XXXX-XXXX-…（首个用户免填）",
    "auth.phRegUsername": "3–24 位，小写字母开头",
    "auth.regUsernameNote": "仅小写字母、数字、下划线、连字符；注册后不可修改",
    "auth.nickname": "昵称（可选）",
    "auth.phNickname": "展示用的名字",
    "auth.phPassword": "至少 8 位",
    "auth.register": "注册并开通网盘",
    "auth.foot": "Ourmetaverse · 自托管服务",
    "auth.regDone": "注册成功，你的网盘已开通 🎉",

    "top.admin": "管理后台",
    "top.chipTitle": "点这里改名字",
    "top.chpw": "改密码",
    "top.logout": "退出",

    "quota.label": "存储空间",
    "quota.used": "已用 {used} / {total}",

    "scope.mine": "我的网盘",
    "scope.public": "公共区域",
    "crumbs.sharedOf": "{owner} 的共享",

    "toolbar.mkdir": "＋ 新建",
    "toolbar.upload": "⬆ 上传",
    "toolbar.uploadFiles": "上传文件",
    "toolbar.uploadFolder": "上传文件夹",
    "toolbar.speed": "⚡ 测速",

    "foreign.before": "你正在浏览",
    "foreign.after": "的共享文件夹；你上传或新建的内容会存进以你用户名命名的子文件夹。",
    "foreign.mine": "只看我的",

    "list.dropHint": "松开，把文件或文件夹放进来",
    "list.selectAll": "全选",
    "list.colName": "名称",
    "list.colSize": "大小",
    "list.colTime": "修改时间",
    "list.loading": "加载中…",
    "list.emptyTitle": "这里空空如也",
    "list.emptyHint": "点「上传文件 / 上传文件夹」，或把文件、文件夹直接拖到这里",
    "list.foot": "文件保存在你的专属空间里，只有你能访问。",
    "list.folder": "文件夹",
    "list.selectHint": "勾选后可批量操作",
    "list.vaultBadge": "🔒 加密",
    "list.vaultRowSub": "加密文件夹 · 需密码打开",
    "list.sharedBadge": "🔗 共享",
    "list.preview": "预览",
    "list.manageShare": "管理共享",
    "list.shareFolder": "共享此文件夹",

    "public.countOne": "1 个共享文件夹",
    "public.count": "{n} 个共享文件夹",
    "public.emptyTitle": "还没有你能进的共享文件夹",
    "public.emptyHint": "管理员可以在「＋ 新建」里勾「公开共享」建一个。",
    "public.hint": "点进去就是那个共享目录，可查看、下载、上传；配额算上传者自己",

    "shared.title": "共享文件夹",
    "shared.hint": "被授权的共享文件夹可查看、下载、上传；配额算上传者自己",
    "shared.unlimited": "不限",
    "shared.capMembers": "上限 {n} 人",
    "shared.noCap": "不限成员",
    "shared.memberCount": "{n} 人",
    "shared.allMembers": "全员",
    "shared.mineBadge": "我创建",
    "shared.itemTitleMine": "点进入；在目录里点「管理共享」改名单",
    "shared.itemTitleOther": "{owner} 分享给你",
    "shared.stop": "取消共享",
    "shared.stopBody": "「{path}」将退回私有文件夹：成员立刻失去访问权限，目录里的内容全部保留。",
    "shared.stopped": "已取消共享",
    "shared.dialogEdit": "「{path}」已共享。成员可查看、下载、上传（各自配额）；改名单立即生效。",
    "shared.dialogCreate": "把「{path}」变成共享文件夹：名单内成员可查看、下载、上传，上传内容存进各自用户名子文件夹；配额算上传者自己。创建后即公开，可随时改名单或取消共享。",
    "shared.membersUpdated": "成员名单已更新",
    "shared.create": "创建共享",
    "shared.created": "已创建共享文件夹",

    "picker.who": "谁能看到",
    "picker.limits": "上限",
    "picker.modeAll": "全部成员",
    "picker.modeSome": "仅指定成员",
    "picker.noteAll": "所有注册成员都能看到、下载、上传（各自配额）。",
    "picker.noteSome": "只有勾选的成员看得到；一个都不勾不会被当成「全员」。",
    "picker.searchPh": "搜索昵称或用户名…",
    "picker.count": "已选 {n} 人",
    "picker.clear": "清空勾选",
    "picker.empty": "没有匹配的成员",
    "picker.ownerSelf": "创建者本人，不用勾",
    "picker.disabled": "已禁用",
    "picker.errNone": "选了「仅指定成员」却一个都没勾：请勾选成员，或改选「全部成员」",
    "picker.loadFailed": "成员名单加载失败：{msg}",

    "limits.emptyEdit": "留空＝保持当前值",
    "limits.emptyDefault": "留空＝默认 {bytes}",
    "limits.capacity": "容量上限",
    "limits.members": "成员上限",
    "limits.capacityNote": "{empty}；这是整个共享目录的总量（所有人的文件加起来）",
    "limits.membersNote": "{empty}；默认 {def} 人，最多 {hard} 人",
    "limits.errCapacity": "容量上限必须大于 0",
    "limits.errMembers": "成员上限必须大于 0",

    "common.save": "保存",
    "common.cancel": "取消",
    "common.delete": "删除",
    "common.move": "移动",
    "common.download": "下载",
    "common.rename": "重命名",
    "common.ok": "确定",
    "common.close": "✕ 关闭",
    "common.root": "我的网盘（根目录）",

    "rename.title": "重命名",
    "rename.label": "新名称",
    "rename.done": "已重命名",
    "delete.title": "删除",
    "delete.body": "确定删除「{name}」吗？删除后文件会进入回收站，此操作无法在本页面撤销。",
    "delete.done": "已删除",
    "move.title": "移动到",
    "move.body": "把「{name}」移动到：",
    "move.done": "已移动",

    "batch.none": "已选 0 项",
    "batch.count": "已选 {n} 项",
    "batch.dlTitle": "下载选中的 {n} 个文件（文件夹会跳过）",
    "batch.dlNoFiles": "选中项里没有文件",
    "batch.deleteTitle": "批量删除",
    "batch.deleteBody": "删除选中的 {n} 项？文件夹会连同里面的内容一起删掉。",
    "batch.moveTitle": "批量移动",
    "batch.moveBody": "把选中的 {n} 项移动到：",
    "batch.deleted": "已删除 {ok} 项",
    "batch.deletedSome": "已删除 {ok} 项，{fail} 项失败：{msg}",
    "batch.moved": "已移动 {ok} 项",
    "batch.movedSome": "已移动 {ok} 项，{fail} 项失败：{msg}",
    "batch.downloaded": "已下载 {n} 个文件，跳过 {skipped} 个文件夹",

    "download.failed": "下载失败",
    "read.failed": "读取失败",

    "mkdir.title": "新建文件夹",
    "mkdir.name": "文件夹名称",
    "mkdir.namePh": "例如：照片",
    "mkdir.type": "类型",
    "mkdir.plain": "普通文件夹",
    "mkdir.vault": "🔒 加密文件夹",
    "mkdir.vaultPw": "文件夹密码（至少 8 位，与登录密码相互独立）",
    "mkdir.vaultPw2": "再次输入密码",
    "mkdir.warn1": "⚠️ 文件名与内容在你的浏览器里加密后才上传，服务器只看得到密文的大小与数量。",
    "mkdir.warn2": "文件夹密码一旦丢失将无法恢复",
    "mkdir.warn3": "，任何人都帮不了你，请存进密码管理器。",
    "mkdir.vis": "可见性",
    "mkdir.private": "私密（仅自己）",
    "mkdir.public": "公开共享",
    "mkdir.create": "创建",
    "mkdir.errName": "请输入名称",
    "mkdir.errPwLen": "文件夹密码至少 8 位",
    "mkdir.errPwDiff": "两次输入的密码不一致",
    "mkdir.vaultDone": "加密文件夹已创建并解锁",
    "mkdir.done": "文件夹已创建",
    "mkdir.sharedDone": "已创建公开共享文件夹",
    "mkdir.sharedFailed": "文件夹已建，但设为共享失败：{msg}",

    "chpw.title": "修改密码",
    "chpw.old": "当前密码",
    "chpw.new": "新密码（至少 8 位）",
    "chpw.done": "密码已修改，其他设备的登录已失效",
    "nick.title": "改名字",
    "nick.label": "显示名（昵称）",
    "nick.note": "登录名 @{user} 不变（它是路径与授权的锚点）；留空就回落到登录名。",
    "nick.done": "名字已更新",

    "upload.title": "上传进度",
    "upload.queued": "排队中…",
    "upload.mkdirFailShort": "创建文件夹失败",
    "upload.mkdirFail": "创建文件夹失败：{msg}",
    "upload.folderCreated": "文件夹已创建",
    "upload.uploading": "上传中…",
    "upload.skipped": "已跳过",
    "upload.progress": "上传中 {pct}% · {size}",
    "upload.done": "完成 ✓",
    "upload.failed": "上传失败",
    "upload.netError": "网络错误",
    "upload.failedStatus": "上传失败 ({status})",
    "upload.vaultNoFolders": "加密文件夹暂不支持整文件夹上传，已跳过文件夹内容",
    "upload.vaultLocked": "加密文件夹已锁定，请先解锁再上传",

    "conflict.title": "已经有同名文件",
    "conflict.body": "「{name}」在这个目录里已存在（{size}，{time}）。",
    "conflict.overwrite": "替换",
    "conflict.keep": "两者都保留",
    "conflict.skip": "跳过",

    "vault.title": "加密文件夹",
    "vault.barNote": " · 文件名与内容只在你的浏览器里解密；服务器只看得到密文的大小与数量。",
    "vault.lock": "锁定",
    "vault.lockedTitle": "这是一个加密文件夹",
    "vault.lockedBody1": "文件名与内容都经过加密，服务器上只存有密文。",
    "vault.lockedBody2": "输入这个文件夹的密码才能查看——密码只在你的浏览器里使用，不会发送给服务器。",
    "vault.unlockBtn": "输入密码解锁",
    "vault.unlocked": "加密文件夹已解锁",
    "vault.unlockTitle": "解锁加密文件夹",
    "vault.pwLabel": "文件夹密码",
    "vault.pwPh": "创建时设置的文件夹密码",
    "vault.pwNote": "密码只在你的浏览器里用于解密，不会发送到服务器；密码错误将无法打开。",
    "vault.unlock": "解锁",
    "vault.errNoPw": "请输入文件夹密码",
    "vault.errWrong": "文件夹密码错误，请重试",
    "vault.lockedToast": "已锁定，密钥已从内存清除",
    "vault.preview": "预览（本地解密）",
    "vault.download": "下载并解密",
    "vault.encrypting": "本地加密中…",
    "vault.uploading": "上传密文中…",
    "vault.manifest": "写入清单…",
    "vault.done": "完成 ✓（已加密）",
    "vault.dlFailed": "下载/解密失败：{msg}",
    "vault.renameTitle": "重命名（仅修改显示名）",
    "vault.renameNote": "显示名只存在于加密清单中，改名不触碰服务器上的密文。",
    "vault.deleteTitle": "删除加密文件",
    "vault.deleteBody": "确定删除「{name}」吗？其密文将被删除，无法恢复。",

    "preview.title": "预览",
    "preview.tooBig": "文本文件过大，不适合在线预览。",
    "preview.cannot": "该文件无法在线预览。",
    "preview.fallbackSub": "可以点右上角「下载」保存到本地查看。",
    "preview.loadFailed": "预览加载失败",
    "preview.decrypting": "本地解密中…",
    "preview.decryptFailed": "预览解密失败：{msg}",

    "speed.head": "⚡ 上下行测速",
    "speed.size": "数据量",
    "speed.run": "开始测速",
    "speed.down": "下载",
    "speed.up": "上传",
    "speed.noteLive": "经后端流式转发实测，与实际上传/下载走同一条链路；测速流量不占配额、不存文件。",
    "speed.noteStub": "⚠️ 当前为本地测试链路（stub 假存储）：测的是这台机器到后端的速度，不代表真实 Seafile / e2 的速度。测速流量不占配额。",
    "speed.running": "测速中…",
    "speed.waitDown": "等待下载完成…",
    "speed.failDown": "下载测速失败 ({status})",
    "speed.failUp": "上传测速失败 ({status})",
    "speed.errUp": "上传测速网络错误",
    "speed.resDown": "下载 {speed}（{size}）",
    "speed.resUp": "上传 {speed}（服务器确认收到 {size}，未存盘）",

    "admin.back": "← 返回网盘",
    "admin.sub": "邀请码 · 用户 · 用量",
    "admin.invites": "邀请码",
    "admin.notePh": "备注（发给谁）",
    "admin.validity": "有效期",
    "admin.days": "天",
    "admin.uses": "可用次数",
    "admin.issue": "签发新码",
    "admin.newCode": "新邀请码（请复制后发给对方）：",
    "admin.copy": "复制",
    "admin.thCode": "邀请码",
    "admin.thNote": "备注",
    "admin.thStatus": "状态",
    "admin.thUses": "使用",
    "admin.thExpires": "到期",
    "admin.users": "用户",
    "admin.thUser": "用户",
    "admin.thQuota": "用量 / 配额",
    "admin.thLastLogin": "最后登录",
    "admin.thActions": "操作",
    "admin.total": "全员总用量 {bytes}",
    "invite.ok": "可用",
    "invite.usedUp": "已用完",
    "invite.revoked": "已撤销",
    "invite.expired": "已过期",
    "invite.never": "永久",
    "invite.revoke": "撤销",
    "invite.revokedToast": "邀请码已撤销",
    "invite.copied": "已复制",
    "invite.copyFailed": "复制失败，请手动复制",
    "user.admin": "管理员",
    "user.active": "正常",
    "user.disabledPill": "已禁用",
    "user.never": "从未",
    "user.setQuota": "设配额",
    "user.recalc": "校准",
    "user.makeAdmin": "设为管理员",
    "user.unmakeAdmin": "取消管理员",
    "user.disable": "禁用",
    "user.enable": "启用",
    "user.quotaTitle": "设置配额 · {user}",
    "user.quotaLabel": "配额（GB，留空 = 系统默认）",
    "user.quotaSaved": "配额已更新",
    "user.recalcDone": "校准完成：{bytes}",
    "user.makeAdminBody": "将「{user}」设为管理员后，对方将能访问管理后台、管理用户与邀请码。确定吗？",
    "user.makeAdminDone": "已设为管理员",
    "user.unmakeAdminBody": "取消「{user}」的管理员权限后，对方将无法访问管理后台。确定吗？",
    "user.unmakeAdminDone": "已取消管理员",
    "user.disableTitle": "禁用用户",
    "user.disableBody": "禁用「{user}」后，其所有登录立即失效，但文件会保留。确定禁用吗？",
    "user.disabledToast": "已禁用",
    "user.enabledToast": "已启用",
    "modal.title": "标题",
  },
  en: {
    "app.title": "SubDrive · Personal drive",
    "req.failed": "Request failed ({status})",
    "lang.switch": "Switch language",

    "auth.brand": "Personal drive",
    "auth.tag1": "Your private file space",
    "auth.tag2": "Simple, secure, always within reach",
    "auth.tabLogin": "Sign in",
    "auth.tabRegister": "Sign up",
    "auth.username": "Username",
    "auth.password": "Password",
    "auth.phUsername": "Your username",
    "auth.login": "Sign in",
    "auth.loginHint": "No account yet? Use an invite code on the Sign up tab.",
    "auth.invite": "Invite code",
    "auth.phInvite": "SD-XXXX-XXXX-… (not needed for the first user)",
    "auth.phRegUsername": "3–24 chars, starting with a lowercase letter",
    "auth.regUsernameNote": "Lowercase letters, digits, underscore and hyphen only; cannot be changed later",
    "auth.nickname": "Nickname (optional)",
    "auth.phNickname": "Display name",
    "auth.phPassword": "At least 8 characters",
    "auth.register": "Create account",
    "auth.foot": "Ourmetaverse · Self-hosted service",
    "auth.regDone": "Signed up — your drive is ready 🎉",

    "top.admin": "Admin console",
    "top.chipTitle": "Click to change your display name",
    "top.chpw": "Change password",
    "top.logout": "Sign out",

    "quota.label": "Storage",
    "quota.used": "Used {used} / {total}",

    "scope.mine": "My drive",
    "scope.public": "Public area",
    "crumbs.sharedOf": "{owner}'s share",

    "toolbar.mkdir": "+ New",
    "toolbar.upload": "⬆ Upload",
    "toolbar.uploadFiles": "Upload files",
    "toolbar.uploadFolder": "Upload folder",
    "toolbar.speed": "⚡ Speed test",

    "foreign.before": "You are browsing a shared folder of",
    "foreign.after": "; anything you upload or create goes into a subfolder named after your username.",
    "foreign.mine": "Only mine",

    "list.dropHint": "Drop files or folders here",
    "list.selectAll": "Select all",
    "list.colName": "Name",
    "list.colSize": "Size",
    "list.colTime": "Modified",
    "list.loading": "Loading…",
    "list.emptyTitle": "Nothing here yet",
    "list.emptyHint": "Use “Upload files / Upload folder”, or drag files and folders here",
    "list.foot": "Your files live in your own space; only you can reach them.",
    "list.folder": "Folder",
    "list.selectHint": "Check rows to enable bulk actions",
    "list.vaultBadge": "🔒 Encrypted",
    "list.vaultRowSub": "Encrypted folder · password required",
    "list.sharedBadge": "🔗 Shared",
    "list.preview": "Preview",
    "list.manageShare": "Manage sharing",
    "list.shareFolder": "Share this folder",

    "public.countOne": "1 shared folder",
    "public.count": "{n} shared folders",
    "public.emptyTitle": "No shared folder you can enter yet",
    "public.emptyHint": "An admin can create one via \"+ New\" with \"Public share\" checked.",
    "public.hint": "Opens that shared folder: browse, download and upload; usage counts toward the uploader",

    "shared.title": "Shared folders",
    "shared.hint": "Shared folders you were granted: browse, download and upload; usage counts toward the uploader",
    "shared.unlimited": "Unlimited",
    "shared.capMembers": "max {n} members",
    "shared.noCap": "unlimited members",
    "shared.memberCount": "{n} members",
    "shared.allMembers": "everyone",
    "shared.mineBadge": "Created by me",
    "shared.itemTitleMine": "Click to open; use “Manage sharing” inside to edit the list",
    "shared.itemTitleOther": "Shared with you by {owner}",
    "shared.stop": "Stop sharing",
    "shared.stopBody": "“{path}” becomes a private folder again: members lose access immediately and all contents are kept.",
    "shared.stopped": "Sharing stopped",
    "shared.dialogEdit": "“{path}” is shared. Members can browse, download and upload on their own quota; member changes apply immediately.",
    "shared.dialogCreate": "Turn “{path}” into a shared folder: listed members can browse, download and upload, and their uploads go into subfolders named after them; usage counts toward the uploader. It is shared as soon as you create it, and you can edit the list or stop sharing at any time.",
    "shared.membersUpdated": "Member list updated",
    "shared.create": "Create share",
    "shared.created": "Shared folder created",

    "picker.who": "Who can see it",
    "picker.limits": "Limits",
    "picker.modeAll": "All members",
    "picker.modeSome": "Selected members only",
    "picker.noteAll": "Every registered member can browse, download and upload, each on their own quota.",
    "picker.noteSome": "Only checked members can see it; checking nobody is not treated as “everyone”.",
    "picker.searchPh": "Search nickname or username…",
    "picker.count": "{n} selected",
    "picker.clear": "Clear selection",
    "picker.empty": "No matching members",
    "picker.ownerSelf": "Owner — no need to check",
    "picker.disabled": "Disabled",
    "picker.errNone": "“Selected members only” is on but nobody is checked: check some members or switch to “All members”",
    "picker.loadFailed": "Failed to load the member list: {msg}",

    "limits.emptyEdit": "empty = keep the current value",
    "limits.emptyDefault": "empty = default {bytes}",
    "limits.capacity": "Capacity limit",
    "limits.members": "Member limit",
    "limits.capacityNote": "{empty}; this is the total for the whole shared folder, all members combined",
    "limits.membersNote": "{empty}; default {def}, hard maximum {hard}",
    "limits.errCapacity": "Capacity limit must be greater than 0",
    "limits.errMembers": "Member limit must be greater than 0",

    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.delete": "Delete",
    "common.move": "Move",
    "common.download": "Download",
    "common.rename": "Rename",
    "common.ok": "OK",
    "common.close": "✕ Close",
    "common.root": "My drive (root)",

    "rename.title": "Rename",
    "rename.label": "New name",
    "rename.done": "Renamed",
    "delete.title": "Delete",
    "delete.body": "Delete “{name}”? It moves to the recycle bin; this action cannot be undone here.",
    "delete.done": "Deleted",
    "move.title": "Move to",
    "move.body": "Move “{name}” to:",
    "move.done": "Moved",

    "batch.none": "0 selected",
    "batch.count": "{n} selected",
    "batch.dlTitle": "Download the {n} selected files (folders are skipped)",
    "batch.dlNoFiles": "No files in the selection",
    "batch.deleteTitle": "Delete selected",
    "batch.deleteBody": "Delete the {n} selected items? Folders are deleted together with their contents.",
    "batch.moveTitle": "Move selected",
    "batch.moveBody": "Move the {n} selected items to:",
    "batch.deleted": "Deleted {ok} item(s)",
    "batch.deletedSome": "Deleted {ok}; {fail} failed: {msg}",
    "batch.moved": "Moved {ok} item(s)",
    "batch.movedSome": "Moved {ok}; {fail} failed: {msg}",
    "batch.downloaded": "Downloaded {n} files; skipped {skipped} folders",

    "download.failed": "Download failed",
    "read.failed": "Failed to read",

    "mkdir.title": "New folder",
    "mkdir.name": "Folder name",
    "mkdir.namePh": "e.g. Photos",
    "mkdir.type": "Type",
    "mkdir.plain": "Regular folder",
    "mkdir.vault": "🔒 Encrypted folder",
    "mkdir.vaultPw": "Folder password (8+ characters, independent of your login password)",
    "mkdir.vaultPw2": "Repeat the password",
    "mkdir.warn1": "⚠️ Names and contents are encrypted in your browser before upload; the server sees only ciphertext size and count.",
    "mkdir.warn2": "A lost folder password cannot be recovered",
    "mkdir.warn3": ", nobody can help you, so keep it in a password manager.",
    "mkdir.vis": "Visibility",
    "mkdir.private": "Private (only me)",
    "mkdir.public": "Public share",
    "mkdir.create": "Create",
    "mkdir.errName": "Please enter a name",
    "mkdir.errPwLen": "The folder password must be at least 8 characters",
    "mkdir.errPwDiff": "The two passwords do not match",
    "mkdir.vaultDone": "Encrypted folder created and unlocked",
    "mkdir.done": "Folder created",
    "mkdir.sharedDone": "Public shared folder created",
    "mkdir.sharedFailed": "The folder was created, but sharing failed: {msg}",

    "chpw.title": "Change password",
    "chpw.old": "Current password",
    "chpw.new": "New password (8+ characters)",
    "chpw.done": "Password changed; sessions on other devices were signed out",
    "nick.title": "Change display name",
    "nick.label": "Display name (nickname)",
    "nick.note": "Your login name @{user} stays the same (it anchors paths and permissions); leave this empty to fall back to it.",
    "nick.done": "Display name updated",

    "upload.title": "Upload progress",
    "upload.queued": "Queued…",
    "upload.mkdirFailShort": "Failed to create the folder",
    "upload.mkdirFail": "Failed to create the folder: {msg}",
    "upload.folderCreated": "Folder created",
    "upload.uploading": "Uploading…",
    "upload.skipped": "Skipped",
    "upload.progress": "Uploading {pct}% · {size}",
    "upload.done": "Done ✓",
    "upload.failed": "Upload failed",
    "upload.netError": "Network error",
    "upload.failedStatus": "Upload failed ({status})",
    "upload.vaultNoFolders": "Whole-folder upload is not supported for encrypted folders; folder contents were skipped",
    "upload.vaultLocked": "The encrypted folder is locked; unlock it before uploading",

    "conflict.title": "A file with the same name already exists",
    "conflict.body": "“{name}” already exists in this folder ({size}, {time}).",
    "conflict.overwrite": "Replace",
    "conflict.keep": "Keep both",
    "conflict.skip": "Skip",

    "vault.title": "Encrypted folder",
    "vault.barNote": " · Names and contents are decrypted only in your browser; the server sees only ciphertext size and count.",
    "vault.lock": "Lock",
    "vault.lockedTitle": "This is an encrypted folder",
    "vault.lockedBody1": "Names and contents are encrypted; only ciphertext is stored on the server.",
    "vault.lockedBody2": "Enter this folder's password to view it — the password is used only in your browser and is never sent to the server.",
    "vault.unlockBtn": "Unlock with password",
    "vault.unlocked": "Encrypted folder unlocked",
    "vault.unlockTitle": "Unlock encrypted folder",
    "vault.pwLabel": "Folder password",
    "vault.pwPh": "The folder password set at creation",
    "vault.pwNote": "The password is used only in your browser for decryption and is never sent to the server; a wrong password will not open it.",
    "vault.unlock": "Unlock",
    "vault.errNoPw": "Please enter the folder password",
    "vault.errWrong": "Wrong folder password, please try again",
    "vault.lockedToast": "Locked; the key was cleared from memory",
    "vault.preview": "Preview (decrypted locally)",
    "vault.download": "Download and decrypt",
    "vault.encrypting": "Encrypting locally…",
    "vault.uploading": "Uploading ciphertext…",
    "vault.manifest": "Writing manifest…",
    "vault.done": "Done ✓ (encrypted)",
    "vault.dlFailed": "Download or decryption failed: {msg}",
    "vault.renameTitle": "Rename (display name only)",
    "vault.renameNote": "The display name lives only in the encrypted manifest; renaming never touches the ciphertext on the server.",
    "vault.deleteTitle": "Delete encrypted file",
    "vault.deleteBody": "Delete “{name}”? Its ciphertext will be deleted and cannot be recovered.",

    "preview.title": "Preview",
    "preview.tooBig": "This text file is too large for an in-browser preview.",
    "preview.cannot": "This file cannot be previewed in the browser.",
    "preview.fallbackSub": "Use “Download” at the top right to save it and open it locally.",
    "preview.loadFailed": "Preview failed to load",
    "preview.decrypting": "Decrypting locally…",
    "preview.decryptFailed": "Preview decryption failed: {msg}",

    "speed.head": "⚡ Upload / download speed test",
    "speed.size": "Data size",
    "speed.run": "Start test",
    "speed.down": "Download",
    "speed.up": "Upload",
    "speed.noteLive": "Measured through the backend's streaming relay, the same path real uploads and downloads use; test traffic does not consume quota and stores no files.",
    "speed.noteStub": "⚠️ This is the local test path (stub storage): it measures this machine's link to the backend, not real Seafile / e2 speed. Test traffic does not consume quota.",
    "speed.running": "Testing…",
    "speed.waitDown": "Waiting for the download…",
    "speed.failDown": "Download test failed ({status})",
    "speed.failUp": "Upload test failed ({status})",
    "speed.errUp": "Upload test network error",
    "speed.resDown": "Download {speed} ({size})",
    "speed.resUp": "Upload {speed} (server confirmed {size}, nothing stored)",

    "admin.back": "← Back to drive",
    "admin.sub": "Invites · Users · Usage",
    "admin.invites": "Invite codes",
    "admin.notePh": "Note (who it is for)",
    "admin.validity": "Valid for",
    "admin.days": "days",
    "admin.uses": "Uses",
    "admin.issue": "Issue code",
    "admin.newCode": "New invite code (copy it and send it over):",
    "admin.copy": "Copy",
    "admin.thCode": "Code",
    "admin.thNote": "Note",
    "admin.thStatus": "Status",
    "admin.thUses": "Uses",
    "admin.thExpires": "Expires",
    "admin.users": "Users",
    "admin.thUser": "User",
    "admin.thQuota": "Usage / Quota",
    "admin.thLastLogin": "Last login",
    "admin.thActions": "Actions",
    "admin.total": "Total usage {bytes}",
    "invite.ok": "Active",
    "invite.usedUp": "Used up",
    "invite.revoked": "Revoked",
    "invite.expired": "Expired",
    "invite.never": "Never",
    "invite.revoke": "Revoke",
    "invite.revokedToast": "Invite code revoked",
    "invite.copied": "Copied",
    "invite.copyFailed": "Copy failed — please copy it manually",
    "user.admin": "Admin",
    "user.active": "Active",
    "user.disabledPill": "Disabled",
    "user.never": "Never",
    "user.setQuota": "Set quota",
    "user.recalc": "Recalculate",
    "user.makeAdmin": "Make admin",
    "user.unmakeAdmin": "Remove admin",
    "user.disable": "Disable",
    "user.enable": "Enable",
    "user.quotaTitle": "Set quota · {user}",
    "user.quotaLabel": "Quota (GB, empty = system default)",
    "user.quotaSaved": "Quota updated",
    "user.recalcDone": "Recalculation done: {bytes}",
    "user.makeAdminBody": "Making “{user}” an admin gives them access to the admin console, user management and invite codes. Continue?",
    "user.makeAdminDone": "Now an admin",
    "user.unmakeAdminBody": "Removing admin rights from “{user}” blocks their access to the admin console. Continue?",
    "user.unmakeAdminDone": "Admin rights removed",
    "user.disableTitle": "Disable user",
    "user.disableBody": "Disabling “{user}” invalidates all their sessions but keeps their files. Continue?",
    "user.disabledToast": "Disabled",
    "user.enabledToast": "Enabled",
    "modal.title": "Title",
  },
};

// 后端消息保持中文（后端一行不改）。en 下按 detail.error 的 code 查这里的英文，
// 查不到就原样显示服务端文本——宁可露出中文，也不吞掉真实错误。
const ERROR_I18N = {
  unauthorized: "Please sign in first",
  account_disabled: "This account is disabled",
  admin_required: "Admin rights required",
  not_found: "Not found",
  path_rejected: "That path is not allowed",
  range_not_satisfiable: "Requested range is not available",
  bad_invite: "Invalid or expired invite code",
  bad_limit: "Invalid limit",
  bad_member: "Invalid member",
  bad_on_conflict: "Invalid conflict policy",
  bad_path: "Invalid path",
  bad_username: "Invalid username",
  cell_move: "This item cannot be moved",
  cell_rename: "This item cannot be renamed",
  last_admin: "The last admin cannot be removed",
  not_a_dir: "Not a folder",
  not_a_file: "Not a file",
  owner_protected: "The owner cannot be changed",
  shared_delete: "A shared folder cannot be deleted",
  shared_move: "A shared folder cannot be moved",
  shared_rename: "A shared folder cannot be renamed",
  too_many_members: "Too many members",
  username_taken: "That username is taken",
  weak_password: "Password is too weak",
  bad_credentials: "Wrong username or password",
  forbidden: "You do not have permission to do that",
  owner_required: "Only the owner can do that",
  already_shared: "Already shared",
  conflict: "Conflicts with existing data",
  speedtest_busy: "A speed test is already running",
  file_too_large: "File is too large",
  quota_exceeded: "Not enough quota left",
  shared_full: "The shared folder is full",
  speedtest_too_large: "Test size is too large",
  login_locked: "Too many failed attempts; try again later",
  rate_limited: "Too many requests; slow down",
  storage_error: "Storage layer error",
  range_error: "Invalid byte range",
  invalid_move: "A folder cannot be moved into itself",
  seafile_unreachable: "Storage backend unreachable",
  seafile_auth_failed: "Storage backend authentication failed",
};

// 插值用 split/join：这个项目不用模板字符串拼界面文案。
function t(key, vars) {
  const table = I18N[lang] || I18N.zh;
  let s = table[key];
  if (s === undefined) s = I18N.zh[key];
  if (s === undefined) return key;
  if (vars) {
    for (const k in vars) {
      if (Object.prototype.hasOwnProperty.call(vars, k)) {
        s = s.split("{" + k + "}").join(String(vars[k]));
      }
    }
  }
  return s;
}

// 静态文案靠 data-i18n / data-i18n-placeholder / data-i18n-title 标注，这里统一刷。
function applyLang() {
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.title = t("app.title");
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.getAttribute("data-i18n")); });
  $$("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  $$("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
  const btn = $("#lang-toggle");
  if (btn) {
    // 按钮显示「当前语言」：en 下是 EN，这样它自己不会污染「零中文」那类检查
    btn.textContent = lang === "en" ? "EN" : "中";
    btn.title = t("lang.switch");
    btn.setAttribute("aria-label", t("lang.switch"));
  }
}

/* 切语言后把 JS 拼出来的区域重画一遍（applyLang 只认 data-i18n 属性） */
function rerenderI18n() {
  if (!me) return;
  renderCrumbs();
  updateBatchBar();
  updateVaultChrome();
  refreshQuota();
  refreshShared();
  if (!$("#view-admin").classList.contains("hidden")) loadAdmin();
  else refreshList();
}

function setLang(next) {
  lang = next === "en" ? "en" : "zh";
  localStorage.setItem("subdrive_lang", lang);
  // 切换前写下的 toast 是旧语言原文，切完立刻收回，别让页面上留着另一种语言的字
  $("#toast").className = "toast hidden";
  // 关着的弹窗/预览层里还留着上一次渲染的旧语言 DOM（含 placeholder、title），清掉免得残留
  $("#modal-body").innerHTML = "";
  $("#preview-body").innerHTML = "";
  applyLang();
  rerenderI18n();
}

let token = localStorage.getItem("subdrive_token") || "";
let me = null;
let curPath = ""; // "" = 根目录；否则 "a/b"
let curOwner = ""; // "" = 自己的网盘；否则正在浏览谁的共享文件夹
let quota = null;
let sharedMine = []; // 我创建的共享文件夹（来自 /api/shared/list，is_mine）
const selected = new Set(); // 批量勾选：当前目录下的相对路径
let currentEntries = []; // 当前目录的条目，批量操作取 name/type 用

/* owner 只在浏览别人的共享目录时出现；服务端会按 owner+path 复核授权 */
const ownerQS = (prefix) =>
  curOwner ? prefix + "owner=" + encodeURIComponent(curOwner) : "";

/* 浏览别人的共享目录时，只有进到自己那一格（<共享目录>/…/<我的用户名>/）才给改名/移动/删除 */
const inOwnCell = () => !!curOwner && !!me && curPath.split("/").includes(me.username);
/* 那一格文件夹本身：名字就是归属标记，留着不给改 */
const isOwnCellDir = (entry) =>
  !!curOwner && !!me && entry.type === "dir" && entry.name === me.username;

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
    const code = detail && detail.error;
    // en 下先按 error code 查英文；查不到就显示服务端原文（后端消息保持中文，不改）
    const msg = (lang === "en" && code && ERROR_I18N[code])
      || (detail && detail.message) || (data && data.message)
      || t("req.failed", { status: resp.status });
    const e = new Error(msg);
    e.status = resp.status;
    e.code = code;
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
    toast(t("auth.regDone"));
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
  scope = "mine"; fromPublic = false;
  localStorage.removeItem("subdrive_token");
  show("view-auth");
}
$("#btn-logout").addEventListener("click", () => logout(true));
$("#user-chip").addEventListener("click", () => {
  if (!me) return;
  openModal(t("nick.title"),
    '<label class="field"><span>' + t("nick.label") + '</span>'
    + '<input id="nick-input" class="field-input" type="text" maxlength="40" value="'
    + esc(me.nickname || "") + '"></label>'
    + '<p class="field-note">' + t("nick.note", { user: esc(me.username) }) + '</p>',
    t("common.save"), async () => {
      const u = await api("/api/me/nickname", { method: "POST",
        body: { nickname: ($("#nick-input").value || "").trim() } });
      me = Object.assign(me || {}, u);
      $("#user-name").textContent = u.nickname || u.username;
      $("#user-avatar").textContent = (u.nickname || u.username).slice(0, 1);
      $("#user-sub").textContent = "@" + u.username;
      toast(t("nick.done"));
    });
});
$("#btn-my-cell").addEventListener("click", () => {
  if (!curOwner || !me) return;
  // 共享根是路径第一段；我那一格固定叫我的用户名
  const root = curPath.split("/")[0];
  curPath = (root ? root + "/" : "") + me.username;
  refreshList();
});
$("#nav-scope").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-scope]");
  if (btn) setScope(btn.getAttribute("data-scope"));
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
  scope = "mine";
  fromPublic = false;
  applyScope();
  curOwner = "";
  await Promise.all([refreshList(), refreshQuota(), refreshShared()]);
  if (location.hash === "#admin" && me.is_admin) {
    show("view-admin");
    loadAdmin();
  }
}

/* ---------------- 共享文件夹 / 公共区域 ---------------- */
let scope = "mine";      // mine | public：顶栏那两格
let fromPublic = false;  // 当前目录是从「公共区域」点进来的（面包屑第一格跟着变）

const FOLDER_SVG = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
  + '<path d="M3 7.2c0-1.2 1-2.2 2.2-2.2h3.1c.66 0 1.28.3 1.7.82l.86 1.06'
  + 'c.42.52 1.04.82 1.7.82h5.24A2.2 2.2 0 0 1 20 9.9v6.9A2.2 2.2 0 0 1 17.8 19H5.2A2.2 2.2 0 0 1 3 16.8V7.2Z"'
  + ' stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';

function sharedItemEl(f) {
  const el = document.createElement("div");
  el.className = "shared-item" + (f.is_mine ? " mine" : "");
  const capBytes = f.max_bytes ? fmtBytes(f.max_bytes) : t("shared.unlimited");
  const capMem = f.max_members ? t("shared.capMembers", { n: f.max_members }) : t("shared.noCap");
  const memText = f.members.length ? t("shared.memberCount", { n: f.members.length }) : t("shared.allMembers");
  const used = f.bytes || 0;
  const pct = f.max_bytes ? Math.min(100, (used / f.max_bytes) * 100) : 0;
  el.innerHTML = '<div class="si-icon">' + FOLDER_SVG + '</div>'
    + '<div class="si-body">'
    +   '<div class="si-head">'
    +     '<strong class="si-name">' + esc(f.path) + '</strong>'
    +     '<span class="si-owner">' + (f.is_mine ? t("shared.mineBadge") : esc(f.owner)) + '</span>'
    +   '</div>'
    +   '<div class="si-stats">'
    +     '<span class="si-meta">👥 ' + memText + ' · ' + capMem + '</span>'
    +     '<span class="si-size">' + fmtBytes(used) + ' / ' + capBytes + '</span>'
    +   '</div>'
    +   (f.max_bytes ? '<div class="si-bar"><i style="width:' + pct.toFixed(1) + '%"></i></div>' : '')
    + '</div>'
    + '<span class="si-go">›</span>';
  el.title = f.is_mine ? t("shared.itemTitleMine") : t("shared.itemTitleOther", { owner: f.owner });
  el.addEventListener("click", () => enterShared(f));
  return el;
}

async function refreshShared() {
  let folders = [];
  try {
    const res = await api("/api/shared/list");
    folders = res.folders || [];
    if (res.defaults) sharedDefaults = res.defaults;
  } catch { folders = []; }
  sharedMine = folders.filter((f) => f.is_mine);
  const card = $("#shared-card");
  const list = $("#shared-list");
  list.innerHTML = "";
  card.classList.toggle("hidden", scope !== "mine" || folders.length === 0);
  $("#shared-hint").textContent = folders.length
    ? t("shared.hint")
    : "";
  for (const f of folders) list.appendChild(sharedItemEl(f));
  const pub = $("#public-list");
  pub.innerHTML = "";
  for (const f of folders) pub.appendChild(sharedItemEl(f));
  $("#public-empty").classList.toggle("hidden", folders.length > 0);
  $("#public-count").textContent = folders.length
    ? t(folders.length === 1 ? "public.countOne" : "public.count", { n: folders.length })
    : "";
  $("#public-hint").textContent = folders.length
    ? t("public.hint")
    : "";
}

function applyScope() {
  const pub = scope === "public";
  document.body.classList.toggle("public-scope", pub);
  for (const b of document.querySelectorAll("#nav-scope .seg-btn")) {
    const on = b.getAttribute("data-scope") === scope;
    b.classList.toggle("selected", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  }
  $("#public-panel").classList.toggle("hidden", !pub);
  if (pub) {
    $("#shared-card").classList.add("hidden");
    $("#foreign-bar").classList.add("hidden");
    $("#vault-bar").classList.add("hidden");
  }
}

function setScope(next) {
  if (next === scope) {
    if (next === "public") refreshShared();
    return;
  }
  scope = next;
  fromPublic = false;
  if (next === "public") {
    // 公共区域是全局视图：先把当前位置清掉，免得点回「我的网盘」时还停在别人目录里
    curOwner = "";
    curPath = "";
    applyScope();
    refreshShared();
    return;
  }
  applyScope();
  refreshList();
}

function enterShared(f) {
  // 进的是那个共享目录本身：owner 是目录主人，path 是共享目录的相对路径。
  scope = "mine";
  fromPublic = true;
  applyScope();
  curOwner = f.is_mine ? "" : f.owner;
  curPath = f.path;
  vault = null;
  vaultRootPath = null;
  refreshList();
}

/* ---------------- 共享对话框 ---------------- */
function revokeShare(folder) {
  openModal(t("shared.stop"),
    '<p class="modal-text">' + t("shared.stopBody", { path: esc(folder.path) }) + '</p>',
    t("shared.stop"), async () => {
      try {
        await api("/api/shared/" + folder.id, { method: "DELETE" });
        toast(t("shared.stopped"));
        await refreshShared();
        refreshList();
      } catch (e) { toast(e.message, true); }
    }, true);
}


async function openShareDialog(path, grant) {
  let folders = [];
  try {
    const res = await api("/api/shared/list");
    folders = res.folders || [];
    if (res.defaults) sharedDefaults = res.defaults;
  } catch (e) { toast(e.message, true); return; }
  const mineOne = folders.find((f) => f.is_mine && f.path === path) || null;
  const isMine = !!(grant && grant.is_mine) || !!mineOne;
  const memberNames = (mineOne || grant || {}).members || [];
  await prepareShareUI();
  const body = isMine
    ? '<p class="modal-hint">' + t("shared.dialogEdit", { path: esc(path) }) + '</p>'
      + '<label class="field-label">' + t("picker.who") + '</label>' + memberPickerHTML("s")
      + '<label class="field-label">' + t("picker.limits") + '</label>' + limitsHTML("s", mineOne, "edit")
    : '<p class="modal-hint">' + t("shared.dialogCreate", { path: esc(path) }) + '</p>'
      + '<label class="field-label">' + t("picker.who") + '</label>' + memberPickerHTML("s");
  openModal(t("shared.title"), body, isMine ? t("common.save") : t("shared.create"), async () => {
    const members = readMemberPicker("s");
    if (isMine) {
      await api("/api/shared/" + mineOne.id + "/members", { method: "POST", body: { members } });
      // 上限只在填了数的时候才改，留空＝保持库里现状（不动默认值）
      const limits = readShareLimits("s");
      if (Object.keys(limits).length) {
        await api("/api/shared/" + mineOne.id, { method: "PATCH", body: limits });
      }
      toast(t("shared.membersUpdated"));
    } else {
      await api("/api/shared/create", { method: "POST", body: { path: "/" + path, members } });
      toast(t("shared.created"));
    }
    await refreshShared();
    refreshList();
  });
  const ownerName = (mineOne || grant || {}).owner || "";
  bindMemberPicker("s", dirCache || [], memberNames, ownerName);
}
async function refreshQuota() {
  try {
    quota = await api("/api/quota");
    const used = quota.used_bytes, total = quota.quota_bytes;
    const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
    $("#quota-text").textContent = t("quota.used", { used: fmtBytes(used), total: fmtBytes(total) });
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
  const sep = () => {
    const s = document.createElement("span");
    s.className = "crumb-sep";
    s.textContent = "›";
    nav.appendChild(s);
  };
  const mk = (label, path, current, owner = curOwner) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "crumb" + (current ? " current" : "");
    b.textContent = label;
    b.addEventListener("click", () => {
      fromPublic = false;
      curPath = path;
      curOwner = owner;
      refreshList();
    });
    return b;
  };
  const trail = (owner) => {
    parts.forEach((p, i) => {
      sep();
      nav.appendChild(mk(p, parts.slice(0, i + 1).join("/"),
        i === parts.length - 1, owner));
    });
  };
  if (fromPublic) {
    // 从「公共区域」点进来的目录：第一格回公共区域，而不是回到我的网盘
    const b = document.createElement("button");
    b.type = "button";
    b.className = "crumb";
    b.textContent = t("scope.public");
    b.addEventListener("click", () => setScope("public"));
    nav.appendChild(b);
    if (curOwner) {
      sep();
      nav.appendChild(mk(t("crumbs.sharedOf", { owner: curOwner }), "", parts.length === 0, curOwner));
    }
    trail(curOwner);
    return;
  }
  if (curOwner) {
    // 别人的共享目录：第一格回到自己的网盘，第二格是共享根
    nav.appendChild(mk(t("scope.mine"), "", false, ""));
    sep();
    nav.appendChild(mk(t("crumbs.sharedOf", { owner: curOwner }), "", parts.length === 0, curOwner));
    trail(curOwner);
    return;
  }
  nav.appendChild(mk(t("scope.mine"), "", parts.length === 0));
  trail("");
}

let lastEntries = [];
async function refreshList() {
  // 导航离开加密文件夹 → 立即锁定（密钥只留在内存，离开即弃）
  if (vault && curPath !== vault.path) vault = null;
  renderCrumbs();
  selected.clear();
  updateBatchBar();
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
  currentEntries = entries;
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
          <div class="row-sub">${entry.type === "dir" ? t("list.folder") : sizeText} · ${fmtDate(entry.mtime)}</div>
        </div>
      </div>
      <span class="col-size">${sizeText}</span>
      <span class="col-time">${timeText}</span>
      <span class="col-act"></span>`;
    const rel = (curPath ? curPath + "/" : "") + entry.name;
    const sel = document.createElement("label");
    sel.className = "sel-cell";
    sel.title = t("list.selectHint");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "row-sel";
    cb.checked = selected.has(rel);
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      if (cb.checked) selected.add(rel); else selected.delete(rel);
      row.classList.toggle("selected", cb.checked);
      updateBatchBar();
    });
    sel.appendChild(cb);
    row.insertBefore(sel, row.firstChild);
    row.classList.toggle("selected", cb.checked);
    if (entry.type === "dir" && !curOwner && vaultDirMarks.has(rel)) {
      $(".file-icon", row).classList.add("vault-icon");
      $(".row-name", row).insertAdjacentHTML("beforeend",
        ' <span class="vault-badge">' + t("list.vaultBadge") + '</span>');
      $(".row-sub", row).textContent = t("list.vaultRowSub");
    }
    const shared = entry.type === "dir" && !curOwner
      ? sharedMine.find((s) => s.path === rel) : null;
    if (shared) {
      $(".row-name", row).insertAdjacentHTML("beforeend",
        ' <span class="shared-badge">' + t("list.sharedBadge") + '</span>');
    }
    const act = $(".col-act", row);
    if (entry.type === "file") {
      if (previewKind(entry.name)) {
        act.appendChild(actionBtn(ICONS.eye, t("list.preview"), () => openPreview(rel, entry)));
      }
      act.appendChild(actionBtn(ICONS.download, t("common.download"), () => downloadFile(rel, entry.name)));
    }
    if (entry.type === "dir" && !curOwner && !vaultDirMarks.has(rel) && me.is_admin) {
      act.appendChild(actionBtn(ICONS.share, shared ? t("list.manageShare") : t("list.shareFolder"),
        () => openShareDialog(rel, shared)));
      if (shared) {
        act.appendChild(actionBtn(ICONS.unshare, t("shared.stop"), () => revokeShare(shared), true));
      }
    }
    if ((!curOwner || inOwnCell()) && !isOwnCellDir(entry)) {
      act.appendChild(actionBtn(ICONS.rename, t("common.rename"), () => renameItem(rel, entry.name)));
      act.appendChild(actionBtn(ICONS.move, t("common.move"), () => moveItem(rel, entry.name)));
      act.appendChild(actionBtn(ICONS.trash, t("common.delete"), () => deleteItem(rel, entry.name), true));
    }
    row.addEventListener("click", (ev) => {
      if (ev.target.closest(".col-act")) return;
      if (ev.target.closest(".sel-cell")) return;
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

/* ---------------- 批量操作（行首勾选 → 底部操作条） ---------------- */
function relOf(entry) { return (curPath ? curPath + "/" : "") + entry.name; }
function updateBatchBar() {
  const bar = $("#batch-bar");
  if (!bar) return;
  const n = selected.size;
  bar.classList.toggle("hidden", n === 0);
  $("#batch-count").textContent = t("batch.count", { n: n });
  const files = currentEntries.filter((e) => e.type === "file" && selected.has(relOf(e)));
  const dl = $("#batch-download");
  dl.disabled = files.length === 0;
  dl.title = files.length ? t("batch.dlTitle", { n: files.length }) : t("batch.dlNoFiles");
  const all = currentEntries.length > 0 && currentEntries.every((e) => selected.has(relOf(e)));
  const allBox = $("#sel-all");
  if (allBox) { allBox.checked = all; allBox.indeterminate = !all && n > 0; }
}
function clearSelection() {
  selected.clear();
  $$("#file-list .row").forEach((row) => {
    const cb = $(".row-sel", row);
    if (cb) cb.checked = false;
    row.classList.remove("selected");
  });
  updateBatchBar();
}
async function runBatch(list, fn, okKey, failKey) {
  let ok = 0, fail = 0, firstErr = "";
  for (const rel of list) {
    try { await fn(rel); ok++; } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  if (fail) toast(t(failKey, { ok: ok, fail: fail, msg: firstErr }), true);
  else toast(t(okKey, { ok: ok }));
}
function batchDelete() {
  const list = [...selected];
  if (!list.length) return;
  openModal(t("batch.deleteTitle"), '<p class="modal-text">' + t("batch.deleteBody", { n: list.length }) + '</p>',
    t("common.delete"), async () => {
      await runBatch(list, (rel) =>
        api("/api/files/delete" + ownerQS("?"), { method: "POST", body: { path: "/" + rel } }), "batch.deleted", "batch.deletedSome");
      refreshList();
      refreshQuota();
    }, true);
}
async function batchMove() {
  const list = [...selected];
  if (!list.length) return;
  /* 共享目录里只在自己的那一格里找落点（同 moveItem） */
  const parts = curPath.split("/");
  const idx = me ? parts.indexOf(me.username) : -1;
  const rootDir = curOwner && idx >= 0 ? parts.slice(0, idx + 1).join("/") : "";
  let dirs;
  try { dirs = await collectDirs(rootDir); } catch (e) { toast(e.message, true); return; }
  const srcDirs = new Set(list.map((rel) => (rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "")));
  dirs = dirs.filter((d) => !srcDirs.has(d) && !list.some((rel) => d === rel || d.startsWith(rel + "/")));
  let chosen = rootDir;
  openModal(t("batch.moveTitle"), `
    <p class="modal-text">${t("batch.moveBody", { n: list.length })}</p>
    <div class="folder-pick">${dirs.map((d) =>
      `<button type="button" data-dir="${esc(d)}">📁 ${d === "" ? t("common.root") : esc("/" + d)}</button>`).join("")}
    </div>`, t("common.move"), async () => {
      await runBatch(list, (rel) => api("/api/files/move" + ownerQS("?"),
        { method: "POST", body: { path: "/" + rel, dest_dir: chosen ? "/" + chosen : "" } }), "batch.moved", "batch.movedSome");
      refreshList();
    });
  $$("#modal-body .folder-pick button").forEach((b) => {
    if (b.dataset.dir === chosen) b.classList.add("selected");
    b.addEventListener("click", () => {
      chosen = b.dataset.dir;
      $$("#modal-body .folder-pick button").forEach((x) => x.classList.toggle("selected", x === b));
    });
  });
}
async function batchDownload() {
  const files = currentEntries.filter((e) => e.type === "file" && selected.has(relOf(e)));
  if (!files.length) return;
  const skipped = selected.size - files.length;
  for (const e of files) await downloadFile(relOf(e), e.name);
  if (skipped > 0) toast(t("batch.downloaded", { n: files.length, skipped: skipped }));
}
$("#sel-all").addEventListener("change", (e) => {
  const on = e.target.checked;
  currentEntries.forEach((entry) => {
    const rel = relOf(entry);
    if (on) selected.add(rel); else selected.delete(rel);
  });
  $$("#file-list .row").forEach((row) => {
    const cb = $(".row-sel", row);
    if (!cb) return;
    cb.checked = on;
    row.classList.toggle("selected", on);
  });
  updateBatchBar();
});
$("#batch-clear").addEventListener("click", clearSelection);
$("#batch-download").addEventListener("click", batchDownload);
$("#batch-move").addEventListener("click", batchMove);
$("#batch-delete").addEventListener("click", batchDelete);

async function downloadFile(rel, name) {
  try {
    const resp = await fetch("/api/files/download?path=" + encodeURIComponent("/" + rel) + ownerQS("&"), {
      headers: { Authorization: "Bearer " + token },
    });
    if (!resp.ok) {
      const d = await resp.json().catch(() => null);
      throw new Error((d && d.detail && d.detail.message) || t("download.failed"));
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
  ok.textContent = okText || t("common.ok");
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
  openModal(t("rename.title"), `
    <label class="field"><span>${t("rename.label")}</span>
    <input id="m-name" type="text" value="${esc(name)}"></label>`,
    t("common.save"), async () => {
      const newName = $("#m-name").value.trim();
      if (!newName || newName === name) return;
      await api("/api/files/rename" + ownerQS("?"),
        { method: "POST", body: { path: "/" + rel, new_name: newName } });
      toast(t("rename.done"));
      refreshList();
    });
}
function deleteItem(rel, name) {
  openModal(t("delete.title"), '<p class="modal-text">' + t("delete.body", { name: esc(name) }) + '</p>',
    t("common.delete"), async () => {
      await api("/api/files/delete" + ownerQS("?"), { method: "POST", body: { path: "/" + rel } });
      toast(t("delete.done"));
      refreshList(); refreshQuota();
    }, true);
}
async function collectDirs(root = "") {
  const dirs = [root];
  async function walk(p) {
    const data = await api("/api/files/list?path=" + encodeURIComponent(p ? "/" + p : "")
      + ownerQS("&"));
    for (const e of data.entries || []) {
      if (e.type === "dir") {
        const full = (p ? p + "/" : "") + e.name;
        dirs.push(full);
        await walk(full);
      }
    }
  }
  await walk(root);
  return dirs;
}
async function moveItem(rel, name) {
  /* 共享目录里只在自己的那一格里找落点：从我那一格开始走，列表才不会被 403 打断 */
  const parts = curPath.split("/");
  const idx = me ? parts.indexOf(me.username) : -1;
  const rootDir = curOwner && idx >= 0 ? parts.slice(0, idx + 1).join("/") : "";
  let dirs;
  try { dirs = await collectDirs(rootDir); } catch (e) { toast(e.message, true); return; }
  const srcDir = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
  dirs = dirs.filter((d) => d !== rel && d !== srcDir && !d.startsWith(rel + "/"));
  let chosen = rootDir;
  openModal(t("move.title"), `
    <p class="modal-text">${t("move.body", { name: esc(name) })}</p>
    <div class="folder-pick">${dirs.map((d) =>
      `<button type="button" data-dir="${esc(d)}">📁 ${d === "" ? t("common.root") : esc("/" + d)}</button>`).join("")}
    </div>`, t("common.move"), async () => {
      await api("/api/files/move" + ownerQS("?"),
        { method: "POST", body: { path: "/" + rel, dest_dir: chosen ? "/" + chosen : "" } });
      toast(t("move.done"));
      refreshList();
    });
  $$("#modal-body .folder-pick button").forEach((b) => {
    if (b.dataset.dir === chosen) b.classList.add("selected");
    b.addEventListener("click", () => {
      chosen = b.dataset.dir;
      $$("#modal-body .folder-pick button").forEach((x) => x.classList.toggle("selected", x === b));
    });
  });
}

/* 「＋ 新建」是唯一的建夹入口：普通文件夹（可当场设为公开共享）+ 加密文件夹
 * 合并进同一个弹窗，工具栏不再并排放「新建文件夹 / 加密文件夹 / 共享文件夹」。 */
/* ---------------- 授权成员与共享上限（新建弹窗 / 管理共享共用） ----------------
 * 为什么不给一个纯勾选列表：D32 定的是「授权表零行＝所有注册成员可见」。用户把勾
 * 全取消，在数据上等于「对全员公开」，与直觉正好相反。所以先用 radio 把两种意图分开，
 * 只有「仅指定成员」才出现勾选列表，且一个都没勾时直接拦住，不允许静默变成全员。
 * 上限：容量跨度四个数量级，spinner 按不动，用「数字 + GB/MB」；成员数是 1–200，
 * 数字框自带的上下箭头就够。默认值与硬顶从 /api/shared/list 的 defaults 来，不在前端
 * 写死——写死的话改环境变量之后界面就在骗人。 */
let dirCache = null;
let sharedDefaults = { max_bytes: 0, max_members: 20, hard_members: 200 };

async function loadDirectory(force) {
  if (dirCache && !force) return dirCache;
  dirCache = await api("/api/users/directory");
  return dirCache;
}

async function prepareShareUI() {
  try {
    if (!sharedDefaults.max_bytes) {
      const d = (await api("/api/shared/list")).defaults;
      if (d) sharedDefaults = d;
    }
    await loadDirectory();
  } catch (e) {
    toast(t("picker.loadFailed", { msg: e.message }), true);
  }
}

function memberPickerHTML(p) {
  return '<div class="member-picker">'
    + '<div class="seg" id="' + p + '-mode">'
    + '<button type="button" class="seg-btn selected" data-mode="all">' + t("picker.modeAll") + '</button>'
    + '<button type="button" class="seg-btn" data-mode="some">' + t("picker.modeSome") + '</button>'
    + '</div>'
    + '<p class="field-note" id="' + p + '-note">' + t("picker.noteAll") + '</p>'
    + '<div id="' + p + '-some" class="hidden">'
    + '<input id="' + p + '-search" class="field-input" type="text" placeholder="' + t("picker.searchPh") + '">'
    + '<div id="' + p + '-list" class="member-list"></div>'
    + '<div class="member-foot"><span id="' + p + '-count">' + t("picker.count", { n: 0 }) + '</span>'
    + '<button type="button" class="btn-ghost" id="' + p + '-clear">' + t("picker.clear") + '</button></div>'
    + '</div></div>';
}

function bindMemberPicker(p, users, selected, ownerName) {
  const sel = new Set(selected || []);
  const known = new Set(users.map((u) => u.username));
  const all = users.concat([...sel].filter((s) => !known.has(s))
    .map((s) => ({ username: s, nickname: s, disabled: true })));
  const box = $('#' + p + '-some');
  const list = $('#' + p + '-list');
  const note = $('#' + p + '-note');
  const modeBtns = $$('#' + p + '-mode .seg-btn');
  const count = () => { $('#' + p + '-count').textContent = t("picker.count", { n: sel.size }); };
  const render = (kw) => {
    const q = (kw || '').trim().toLowerCase();
    const rows = all.filter((u) => !q
      || u.nickname.toLowerCase().includes(q) || u.username.toLowerCase().includes(q));
    list.innerHTML = '';
    if (!rows.length) { list.innerHTML = '<p class="field-note">' + t("picker.empty") + '</p>'; return; }
    for (const u of rows) {
      const el = document.createElement('label');
      el.className = 'member-item';
      const isOwner = !!ownerName && u.username === ownerName;
      el.innerHTML = '<input type="checkbox" value="' + esc(u.username) + '"'
        + (isOwner ? ' disabled' : '') + '>'
        + '<span class="mi-nick">' + esc(u.nickname) + '</span>'
        + '<code class="mi-user">' + esc(u.username) + '</code>'
        + (isOwner ? '<span class="mi-off">' + t("picker.ownerSelf") + '</span>'
          : (u.disabled ? '<span class="mi-off">' + t("picker.disabled") + '</span>' : ''));
      const cb = el.querySelector('input');
      cb.checked = !isOwner && sel.has(u.username);
      if (!isOwner) {
        cb.addEventListener('change', () => {
          if (cb.checked) sel.add(u.username); else sel.delete(u.username);
          count();
        });
      }
      list.appendChild(el);
    }
  };
  modeBtns.forEach((b) => b.addEventListener('click', () => {
    modeBtns.forEach((x) => x.classList.toggle('selected', x === b));
    const some = b.dataset.mode === 'some';
    box.classList.toggle('hidden', !some);
    note.textContent = some
      ? t("picker.noteSome")
      : t("picker.noteAll");
  }));
  $('#' + p + '-search').addEventListener('input', (e) => render(e.target.value));
  $('#' + p + '-clear').addEventListener('click', () => {
    sel.clear();
    $$('#' + p + '-list input').forEach((c) => { c.checked = false; });
    count();
  });
  render('');
  count();
  if (sel.size) $('#' + p + '-mode .seg-btn[data-mode="some"]').click();
}

function readMemberPicker(p) {
  const some = !$('#' + p + '-some').classList.contains('hidden');
  if (!some) return [];
  const picked = $$('#' + p + '-list input:checked').map((c) => c.value);
  if (!picked.length) {
    throw new Error(t("picker.errNone"));
  }
  return picked;
}

function limitsHTML(p, cur, variant) {
  const def = sharedDefaults;
  const b = (cur && cur.max_bytes) || 0;
  const useGb = !b || b % 1073741824 === 0;
  const capVal = b ? (useGb ? b / 1073741824 : b / 1048576) : '';
  const emptyNote = variant === 'edit' ? t("limits.emptyEdit") : t("limits.emptyDefault", { bytes: fmtBytes(def.max_bytes) });
  return '<div class="limit-row">'
    + '<label class="field"><span>' + t("limits.capacity") + '</span><div class="limit-inline">'
    + '<input id="' + p + '-cap" class="field-input" type="number" min="0" step="0.1" value="' + capVal + '">'
    + '<select id="' + p + '-unit" class="field-input">'
    + '<option value="gb"' + (useGb ? ' selected' : '') + '>GB</option>'
    + '<option value="mb"' + (useGb ? '' : ' selected') + '>MB</option>'
    + '</select></div>'
    + '<small class="field-note">' + t("limits.capacityNote", { empty: emptyNote }) + '</small></label>'
    + '<label class="field"><span>' + t("limits.members") + '</span>'
    + '<input id="' + p + '-maxmem" class="field-input" type="number" min="0" step="1" max="' + def.hard_members + '" value="'
    + (cur && cur.max_members ? cur.max_members : '') + '">'
    + '<small class="field-note">' + t("limits.membersNote", { empty: emptyNote, def: def.max_members, hard: def.hard_members }) + '</small></label>'
    + '</div>';
}

function readShareLimits(p) {
  const out = {};
  const capEl = $('#' + p + '-cap');
  if (capEl) {
    const raw = (capEl.value || '').trim();
    if (raw) {
      const unit = $('#' + p + '-unit').value === 'gb' ? 1073741824 : 1048576;
      const v = Math.round(Number(raw) * unit);
      if (!Number.isFinite(v) || v < 1) throw new Error(t("limits.errCapacity"));
      out.max_bytes = v;
    }
  }
  const mmEl = $('#' + p + '-maxmem');
  if (mmEl) {
    const raw = (mmEl.value || '').trim();
    if (raw) {
      const v = Math.floor(Number(raw));
      if (!Number.isFinite(v) || v < 1) throw new Error(t("limits.errMembers"));
      out.max_members = v;
    }
  }
  return out;
}
$("#btn-mkdir").addEventListener("click", async () => {
  const canShare = !!(me && me.is_admin); // B1：只有管理员能开共享目录
  let kind = "plain";
  let vis = "private";
  if (canShare) await prepareShareUI();
  openModal(t("mkdir.title"), `
    <label class="field"><span>${t("mkdir.name")}</span>
    <input id="m-name" type="text" placeholder="${t("mkdir.namePh")}"></label>
    <div class="field"><span>${t("mkdir.type")}</span>
      <div class="seg" id="m-kind">
        <button type="button" class="seg-btn selected" data-kind="plain">${t("mkdir.plain")}</button>
        <button type="button" class="seg-btn" data-kind="vault">${t("mkdir.vault")}</button>
      </div>
    </div>
    <div id="m-vault-box" class="hidden">
      <label class="field"><span>${t("mkdir.vaultPw")}</span>
      <input id="m-vpass" type="password" autocomplete="new-password"></label>
      <label class="field"><span>${t("mkdir.vaultPw2")}</span>
      <input id="m-vpass2" type="password" autocomplete="new-password"></label>
      <p class="modal-text warn-text">${t("mkdir.warn1")}
      <strong>${t("mkdir.warn2")}</strong>${t("mkdir.warn3")}</p>
    </div>
    <div id="m-plain-box">
      <div class="field"><span>${t("mkdir.vis")}</span>
        <div class="seg" id="m-vis">
          <button type="button" class="seg-btn selected" data-vis="private">${t("mkdir.private")}</button>
          ${canShare ? '<button type="button" class="seg-btn" data-vis="shared">' + t("mkdir.public") + '</button>' : ""}
        </div>
      </div>
      ${canShare ? `<div id="m-share-box" class="hidden">
        <label class="field-label">${t("picker.who")}</label>
        ${memberPickerHTML("m")}
        <label class="field-label">${t("picker.limits")}</label>
        ${limitsHTML("m", null, "create")}
      </div>` : ""}
    </div>`,
    t("mkdir.create"), async () => {
      const name = $("#m-name").value.trim();
      if (!name) throw new Error(t("mkdir.errName"));
      const base = curPath ? "/" + curPath : "";
      if (kind === "vault") {
        const p1 = $("#m-vpass").value, p2 = $("#m-vpass2").value;
        if (p1.length < 8) throw new Error(t("mkdir.errPwLen"));
        if (p1 !== p2) throw new Error(t("mkdir.errPwDiff"));
        await createVault(name, p1);
        toast(t("mkdir.vaultDone"));
        return;
      }
      await api("/api/files/mkdir", { method: "POST", body: { path: base, name } });
      if (vis !== "shared") {
        toast(t("mkdir.done"));
        refreshList();
        return;
      }
      const body = {
        path: "/" + ((curPath ? curPath + "/" : "") + name),
        members: readMemberPicker("m"),
      };
      Object.assign(body, readShareLimits("m"));
      try {
        await api("/api/shared/create", { method: "POST", body });
        toast(t("mkdir.sharedDone"));
        await refreshShared();
      } catch (e) {
        toast(t("mkdir.sharedFailed", { msg: e.message }), true);
      }
      refreshList();
    });
  const pick = (sel, attr, onPick) => {
    $$(sel).forEach((b) => b.addEventListener("click", () => {
      onPick(b.dataset[attr]);
      $$(sel).forEach((x) => x.classList.toggle("selected", x === b));
    }));
  };
  pick("#m-kind .seg-btn", "kind", (v) => {
    kind = v;
    $("#m-vault-box").classList.toggle("hidden", v !== "vault");
    $("#m-plain-box").classList.toggle("hidden", v === "vault");
  });
  if (canShare) {
    pick("#m-vis .seg-btn", "vis", (v) => {
      vis = v;
      $("#m-share-box").classList.toggle("hidden", v !== "shared");
    });
    bindMemberPicker("m", dirCache || [], [], me ? me.username : "");
  }
});

$("#btn-chpw").addEventListener("click", () => {
  openModal(t("chpw.title"), `
    <label class="field"><span>${t("chpw.old")}</span><input id="m-old" type="password" autocomplete="current-password"></label>
    <label class="field"><span>${t("chpw.new")}</span><input id="m-new" type="password" autocomplete="new-password"></label>`,
    t("common.save"), async () => {
      await api("/api/auth/change-password", {
        method: "POST",
        body: { old_password: $("#m-old").value, new_password: $("#m-new").value },
      });
      toast(t("chpw.done"));
    });
});

/* ---- 上传 ----
 * 入队条目统一为 { file, relPath }：散文件 relPath 就是文件名；整文件夹上传时
 * relPath 是相对当前目录的完整相对路径（如 "照片/2026/a.jpg"）。目录计划
 * （相对路径 → 先建哪些目录、每个文件落到哪个目录）是纯逻辑，见
 * static/uploadplan.js（Node 测试：tests/test_uploadplan.mjs）。 */
const uploadQueue = [];
let uploading = false;
let uploadsPendingRefresh = false; // 一批上传收尾后统一刷新列表 + 配额
const joinRel = (a, b) => (a && b ? a + "/" + b : a || b || "");

/* 上传入口合成一个按钮 + 小菜单（上传文件 / 上传文件夹） */
$("#btn-upload").addEventListener("click", (e) => {
  e.stopPropagation();
  $("#upload-menu").classList.toggle("hidden");
});
$("#btn-upload-files").addEventListener("click", () => {
  $("#upload-menu").classList.add("hidden");
  $("#file-input").click();
});
document.addEventListener("click", (e) => {
  const t = e.target;
  if (!(t instanceof Element) || !t.closest(".menu-wrap")) $("#upload-menu").classList.add("hidden");
});
$("#file-input").addEventListener("change", (e) => {
  enqueueFiles([...e.target.files]);
  e.target.value = "";
});
$("#btn-upload-folder").addEventListener("click", () => {
  $("#upload-menu").classList.add("hidden");
  $("#folder-input").click();
});
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
      if (withDirs || extraDirs.length) toast(t("upload.vaultNoFolders"), true);
      if (loose.length) vaultEnqueueFiles(loose.map((en) => en.file));
    } else {
      toast(t("upload.vaultLocked"), true);
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
      <div class="u-state">${t("upload.queued")}</div>`;
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
      dirErrors.set(dirRel, e.message || t("upload.mkdirFailShort"));
    }
  }
  if (!rows.length) { // 只拖入了空文件夹：目录已建好，给个明确反馈
    if (dirErrors.size) toast(t("upload.mkdirFail", { msg: [...dirErrors.values()][0] }), true);
    else toast(t("upload.folderCreated"));
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
/* 同名文件先问一声（Win11 式三选一）：替换 / 两者都保留 / 跳过 */
function askConflict(name, old) {
  return new Promise((resolve) => {
    const pick = (v) => { $("#modal-overlay").classList.add("hidden"); resolve(v); };
    openModal(t("conflict.title"), `
      <p class="modal-text">${t("conflict.body", { name: esc(name), size: fmtBytes(old.size), time: fmtDate(old.mtime) })}</p>
      <div class="conflict-actions">
        <button type="button" class="btn-primary" data-v="overwrite">${t("conflict.overwrite")}</button>
        <button type="button" data-v="rename">${t("conflict.keep")}</button>
        <button type="button" data-v="skip">${t("conflict.skip")}</button>
      </div>`, t("conflict.overwrite"), async () => pick("overwrite"));
    $$("#modal-body .conflict-actions button").forEach((b) =>
      b.addEventListener("click", () => pick(b.dataset.v)));
    // 点取消 / 点遮罩 也当「跳过」，否则上传队列会卡在这个 Promise 上
    $("#modal-cancel").addEventListener("click", () => resolve("skip"), { once: true });
    $("#modal-overlay").addEventListener("click",
      (e) => { if (e.target === e.currentTarget) resolve("skip"); }, { once: true });
  });
}
async function uploadOne({ file, item, targetDir, owner }) {
  const fill = $(".u-fill", item);
  const state = $(".u-state", item);
  state.textContent = t("upload.uploading");
  /* 同名先问。只在个人空间探：共享目录的服务端落点是 <目录>/<我>/，前端不复制那套规则（D34） */
  let onConflict = "overwrite";
  let expected = -1;
  if (!owner) {
    try {
      const old = await api("/api/files/detail?path="
        + encodeURIComponent("/" + ((targetDir ? targetDir + "/" : "") + file.name)));
      if (old && old.type === "file") {
        const choice = await askConflict(file.name, old);
        if (choice === "skip") {
          state.textContent = t("upload.skipped");
          uploadsPendingRefresh = true;
          return;
        }
        onConflict = choice;
        if (choice === "overwrite") expected = old.size;
      }
    } catch (e) { /* 404 = 没有同名文件，照常上传 */ }
  }
  await new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    // 目标目录用入队时定死的 targetDir/owner，不读实时 curPath，避免上传途中导航传错地方
    xhr.open("POST", "/api/files/upload?path=" + encodeURIComponent(targetDir ? "/" + targetDir : "")
      + (owner ? "&owner=" + encodeURIComponent(owner) : "")
      + "&on_conflict=" + onConflict
      + (expected >= 0 ? "&expected_old_size=" + expected : ""));
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        fill.style.width = pct + "%";
        state.textContent = t("upload.progress", { pct: pct, size: fmtBytes(file.size) });
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        fill.style.width = "100%";
        item.classList.add("done");
        state.textContent = t("upload.done");
      } else {
        item.classList.add("failed");
        let msg = t("upload.failed");
        try { const d = JSON.parse(xhr.responseText); msg = (d.detail && d.detail.message) || d.message || msg; } catch { }
        state.textContent = msg;
        toast(`${file.name}：${msg}`, true);
      }
      uploadsPendingRefresh = true;
      resolve();
    });
    xhr.addEventListener("error", () => {
      item.classList.add("failed");
      state.textContent = t("upload.netError");
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
    throw new Error((d && d.detail && d.detail.message) || t("read.failed"));
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
    throw new Error((d && d.detail && d.detail.message) || t("upload.failedStatus", { status: resp.status }));
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
      act.appendChild(actionBtn(ICONS.eye, t("vault.preview"), () => openVaultPreview(f)));
    }
    act.appendChild(actionBtn(ICONS.download, t("vault.download"), () => vaultDownload(f)));
    act.appendChild(actionBtn(ICONS.rename, t("common.rename"), () => vaultRename(f)));
    act.appendChild(actionBtn(ICONS.trash, t("common.delete"), () => vaultDelete(f), true));
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
  toast(t("vault.unlocked"));
}
$("#btn-vault-unlock").addEventListener("click", () => {
  openModal(t("vault.unlockTitle"), `
    <label class="field"><span>${t("vault.pwLabel")}</span>
    <input id="m-vpass" type="password" autocomplete="off" placeholder="${t("vault.pwPh")}"></label>
    <p class="modal-text">${t("vault.pwNote")}</p>`,
    t("vault.unlock"), async () => {
      const pw = $("#m-vpass").value;
      if (!pw) throw new Error(t("vault.errNoPw"));
      try {
        await attemptUnlock(pw);
      } catch (e) {
        throw new Error(e.message === "文件夹密码错误" ? t("vault.errWrong") : e.message);
      }
    });
});
$("#btn-vault-lock").addEventListener("click", () => {
  vault = null;
  refreshList();
  toast(t("vault.lockedToast"));
});

/* 加密文件夹的创建入口已并入「＋ 新建」，这里只保留底层构建函数。 */
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
      <div class="u-state">${t("upload.queued")}</div>`;
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
  state.textContent = t("vault.encrypting");
  const plain = new Uint8Array(await file.arrayBuffer());
  const blob = await SDVault.encryptBlob(vault.key, plain);
  fill.style.width = "45%";
  state.textContent = t("vault.uploading");
  const id = SDVault.randomId();
  await uploadBytes(vault.path + "/blobs", id + ".enc", blob); // 先 blob 后清单（CRYPTO.md §6）
  fill.style.width = "80%";
  state.textContent = t("vault.manifest");
  vault.manifest.files.push({
    id, name: file.name, size: plain.length,
    mime: file.type || "application/octet-stream",
    added_at: new Date().toISOString(),
  });
  await saveVaultManifest();
  fill.style.width = "100%";
  item.classList.add("done");
  state.textContent = t("vault.done");
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
    toast(t("vault.dlFailed", { msg: e.message }), true);
  }
}
function vaultRename(entry) {
  openModal(t("vault.renameTitle"), `
    <label class="field"><span>${t("rename.label")}</span>
    <input id="m-name" type="text" value="${esc(entry.name)}"></label>
    <p class="modal-text">${t("vault.renameNote")}</p>`,
    t("common.save"), async () => {
      const nn = $("#m-name").value.trim();
      if (!nn || nn === entry.name) return;
      entry.name = nn;
      await saveVaultManifest();
      toast(t("rename.done"));
      renderVaultEntries();
    });
}
function vaultDelete(entry) {
  openModal(t("vault.deleteTitle"), `
    <p class="modal-text">${t("vault.deleteBody", { name: esc(entry.name) })}</p>`,
    t("common.delete"), async () => {
      vault.manifest.files = vault.manifest.files.filter((f) => f.id !== entry.id);
      await saveVaultManifest(); // 先改清单，再删 blob（CRYPTO.md §6）
      try {
        await api("/api/files/delete", {
          method: "POST",
          body: { path: "/" + vault.path + "/blobs/" + entry.id + ".enc" },
        });
      } catch { /* 孤儿 blob 由用量校准兜底 */ }
      toast(t("delete.done"));
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
    <p>${big ? t("preview.tooBig") : t("preview.cannot")}</p>
    <p class="pv-fallback-sub">${t("preview.fallbackSub")}</p></div>`;
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
    setPreviewContent('<div class="list-loading">' + t("list.loading") + '</div>');
    try {
      const resp = await fetch("/api/files/preview?path=" + encodeURIComponent("/" + rel) + ownerQS("&"), {
        headers: { Authorization: "Bearer " + token },
      });
      if (!resp.ok) throw new Error(t("preview.loadFailed"));
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
  setPreviewContent('<div class="list-loading">' + t("preview.decrypting") + '</div>');
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
    toast(t("preview.decryptFailed", { msg: e.message }), true);
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
    ? t("speed.noteLive")
    : t("speed.noteStub");
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
  dVal.textContent = t("speed.running"); uVal.textContent = t("speed.waitDown");
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
      throw new Error((d && d.detail && d.detail.message) || t("speed.failDown", { status: resp.status }));
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
    uVal.textContent = t("speed.running");
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
          let msg = t("speed.failUp", { status: xhr.status });
          try { const d = JSON.parse(xhr.responseText); msg = (d.detail && d.detail.message) || msg; } catch { }
          reject(new Error(msg));
        }
      });
      xhr.addEventListener("error", () => reject(new Error(t("speed.errUp"))));
      xhr.send(new Blob([payload]));
    });
    uFill.style.width = "100%";
    uVal.textContent = fmtSpeed(up.resp.received_bytes, up.sec);
    result.innerHTML =
      `${t("speed.resDown", { speed: fmtSpeed(got, downSec), size: fmtBytes(got) })}<br>` +
      `${t("speed.resUp", { speed: fmtSpeed(up.resp.received_bytes, up.sec), size: fmtBytes(up.resp.received_bytes) })}<br>` +
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
  try { await navigator.clipboard.writeText($("#new-code-text").textContent); toast(t("invite.copied")); }
  catch { toast(t("invite.copyFailed"), true); }
});

function pillFor(status, usedCount, maxUses) {
  if (status === "active") return '<span class="pill ok">' + t("invite.ok") + '</span>';
  if (status === "used_up") return '<span class="pill mut">' + t("invite.usedUp") + '</span>';
  if (status === "revoked") return '<span class="pill off">' + t("invite.revoked") + '</span>';
  if (status === "expired") return '<span class="pill warn">' + t("invite.expired") + '</span>';
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
      <td>${r.expires_at ? fmtTime(r.expires_at) : t("invite.never")}</td>
      <td>${r.status === "active" ? '<button class="mini-btn danger" data-revoke="' + r.id + '">' + t("invite.revoke") + '</button>' : ""}</td>`;
    tb.appendChild(tr);
  }
  $$("[data-revoke]", tb).forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/api/admin/invite-codes/${b.dataset.revoke}/revoke`, { method: "POST" });
      toast(t("invite.revokedToast"));
      loadInvites();
    } catch (e) { toast(e.message, true); }
  }));
}
async function loadUsers() {
  const [users, usage] = await Promise.all([api("/api/admin/users"), api("/api/admin/usage")]);
  const adminCount = users.filter((x) => x.is_admin).length;
  $("#admin-total").textContent = t("admin.total", { bytes: fmtBytes(usage.total_used_bytes) });
  const tb = $("#user-table tbody");
  tb.innerHTML = "";
  for (const u of users) {
    const tr = document.createElement("tr");
    const pct = u.quota_bytes ? Math.min(100, Math.round((u.used_bytes / u.quota_bytes) * 100)) : 0;
    tr.innerHTML = `
      <td><div class="user-cell"><div class="avatar">${esc((u.nickname || u.username).slice(0, 1))}</div>
        <div>${esc(u.nickname || u.username)}${u.is_admin ? ' <span class="pill warn">' + t("user.admin") + '</span>' : ""}
        <small>@${esc(u.username)}</small></div></div></td>
      <td>${u.status === "active" ? '<span class="pill ok">' + t("user.active") + '</span>' : '<span class="pill off">' + t("user.disabledPill") + '</span>'}</td>
      <td class="usage-cell">${fmtBytes(u.used_bytes)} <span class="of">/ ${fmtBytes(u.quota_bytes)}（${pct}%）</span></td>
      <td>${u.last_login_at ? fmtTime(u.last_login_at) : t("user.never")}</td>
      <td></td>`;
    const act = tr.lastElementChild;
    const mkBtn = (label, fn, danger = false) => {
      const b = document.createElement("button");
      b.className = "mini-btn" + (danger ? " danger" : "");
      b.textContent = label;
      b.addEventListener("click", fn);
      act.appendChild(b);
    };
    mkBtn(t("user.setQuota"), async () => {
      openModal(t("user.quotaTitle", { user: u.username }), `
        <label class="field"><span>${t("user.quotaLabel")}</span>
        <input id="m-gb" type="number" min="0" step="0.5" value="${u.quota_bytes ? (u.quota_bytes / 1073741824) : ""}"></label>`,
        t("common.save"), async () => {
          const v = $("#m-gb").value;
          const bytes = v === "" ? null : Math.round(Number(v) * 1073741824);
          await api(`/api/admin/users/${u.id}/quota`, { method: "POST", body: { quota_bytes: bytes } });
          toast(t("user.quotaSaved"));
          loadUsers();
        });
    });
    mkBtn(t("user.recalc"), async () => {
      try {
        const r = await api(`/api/admin/users/${u.id}/recalibrate`, { method: "POST" });
        toast(t("user.recalcDone", { bytes: fmtBytes(r.used_bytes) }));
        loadUsers();
      } catch (e) { toast(e.message, true); }
    });
    if (me && me.is_owner) {
      if (!u.is_admin) {
        mkBtn(t("user.makeAdmin"), async () => {
          openModal(t("user.makeAdmin"), '<p class="modal-text">' + t("user.makeAdminBody", { user: esc(u.username) }) + '</p>',
            t("user.makeAdmin"), async () => {
              await api(`/api/admin/users/${u.id}/admin`, { method: "POST", body: { is_admin: true } });
              toast(t("user.makeAdminDone"));
              loadUsers();
            });
        });
      } else if (!u.is_owner && adminCount > 1) {
        mkBtn(t("user.unmakeAdmin"), async () => {
          openModal(t("user.unmakeAdmin"), '<p class="modal-text">' + t("user.unmakeAdminBody", { user: esc(u.username) }) + '</p>',
            t("user.unmakeAdmin"), async () => {
              await api(`/api/admin/users/${u.id}/admin`, { method: "POST", body: { is_admin: false } });
              toast(t("user.unmakeAdminDone"));
              loadUsers();
            }, true);
        }, true);
      }
    }
    if (u.status === "active") {
      mkBtn(t("user.disable"), async () => {
        openModal(t("user.disableTitle"), '<p class="modal-text">' + t("user.disableBody", { user: esc(u.username) }) + '</p>',
          t("user.disable"), async () => {
            await api(`/api/admin/users/${u.id}/disable`, { method: "POST" });
            toast(t("user.disabledToast"));
            loadUsers();
          }, true);
      }, true);
    } else {
      mkBtn(t("user.enable"), async () => {
        await api(`/api/admin/users/${u.id}/enable`, { method: "POST" });
        toast(t("user.enabledToast"));
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
// 语言胶囊显示当前语言，点一下即切换；setLang 会同步 localStorage 与静态属性
$("#lang-toggle").addEventListener("click", () => {
  setLang(lang === "en" ? "zh" : "en");
});

(async function boot() {
  applyLang();
  if (token) {
    try { await enterDrive(); return; } catch { /* 落到登录页 */ }
  }
  show("view-auth");
})();
