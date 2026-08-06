/* launcher.js — AI Organization Factory Desktop Entry (Phase 15A-3b)。
   原生 JS, 无框架 (KISS 约束)。
   数据源 = factory-runtime (经 Tauri bridge invoke), Desktop 不维护任何状态;
   不在本端保存 Company/Agent/Knowledge 数据。
   错误文案 = 用户语言 (Rust 侧 friendly_error 已转换; 本端只兜底)。 */

"use strict";

/* ---------- 常量 ---------- */
var STATUS_POLL_MS = 2000;   // 状态轮询间隔 (2s)
var LOG_LINES = 200;         // 日志行数
var HEALTH_FUTURE = [        // 预留未来健康项 (不实现, 仅占位)
  { name: "Organization", status: "即将上线" },
  { name: "Agents", status: "即将上线" },
  { name: "Knowledge", status: "即将上线" },
  { name: "Learning", status: "即将上线" }
];

/* ---------- Tauri bridge (withGlobalTauri) ---------- */
function tauriInvoke(cmd, args) {
  var api = window.__TAURI__ && window.__TAURI__.core;
  if (!api || !api.invoke) {
    return Promise.reject("Factory startup failed: 无法连接本地工厂服务。");
  }
  return api.invoke(cmd, args || {});
}

/* ---------- DOM 助手 ---------- */
function $(id) { return document.getElementById(id); }

function setText(id, text) { $(id).textContent = text; }

function setHidden(id, hidden) { $(id).hidden = !!hidden; }

/* ---------- 状态渲染 ---------- */
var currentStatus = null;
var pollTimer = null;
var activeTab = "runtime";

function statusLabel(st) {
  switch (st) {
    case "ready": return "READY";
    case "starting": return "STARTING";
    case "stopping": return "STOPPING";
    case "stopped": return "STOPPED";
    case "failed": return "FAILED";
    default: return (st || "IDLE").toUpperCase();
  }
}

function formatUptime(secs) {
  if (secs === null || secs === undefined) return "—";
  var h = Math.floor(secs / 3600);
  var m = Math.floor((secs % 3600) / 60);
  var s = Math.floor(secs % 60);
  if (h > 0) return h + "h " + m + "m";
  if (m > 0) return m + "m " + s + "s";
  return s + "s";
}

function friendlyText(err) {
  if (typeof err === "string" && err.length > 0) return err;
  if (err && typeof err.message === "string" && err.message.length > 0) return err.message;
  return "Factory startup failed: 发生未知错误, 请重试。";
}

function renderStatus(st) {
  currentStatus = st;
  var label = statusLabel(st.status);
  var badge = $("status-badge");
  badge.textContent = label;
  badge.className = "badge " + (st.status || "idle");
  badge.setAttribute("data-status", st.status || "idle");
  setText("st-runtime", label);
  setText("st-version", st.version || "—");
  setText("st-port", st.port ? String(st.port) : "—");
}

function renderHealth(hd) {
  if (!hd || !hd.components) return;
  var ul = $("health-list");
  ul.innerHTML = "";
  hd.components.forEach(function (c) {
    var li = document.createElement("li");
    var name = document.createElement("span");
    name.className = "h-name";
    name.textContent = c.name;
    var st = document.createElement("span");
    st.className = "h-status " + (c.ok ? "ok" : "bad");
    st.textContent = (c.ok ? "✓ " : "✗ ") + c.status;
    li.appendChild(name);
    li.appendChild(st);
    if (!c.ok && c.reason) {
      var reason = document.createElement("span");
      reason.className = "h-reason";
      reason.textContent = c.reason;
      li.appendChild(reason);
    }
    if (!c.ok && c.suggestion) {
      var sugg = document.createElement("span");
      sugg.className = "h-suggestion";
      sugg.textContent = c.suggestion;
      li.appendChild(sugg);
    }
    if (!c.ok) {
      var btn = document.createElement("button");
      btn.className = "h-retry";
      btn.textContent = "Retry";
      btn.addEventListener("click", function () { refreshHealth(); });
      li.appendChild(btn);
    }
    ul.appendChild(li);
  });
  HEALTH_FUTURE.forEach(function (f) {
    var li = document.createElement("li");
    li.className = "future";
    var name = document.createElement("span");
    name.className = "h-name";
    name.textContent = f.name;
    var st = document.createElement("span");
    st.className = "h-status";
    st.textContent = f.status;
    li.appendChild(name);
    li.appendChild(st);
    ul.appendChild(li);
  });
  setText("st-uptime", formatUptime(hd.uptime_secs));
}

/* ---------- 首次启动流程 ---------- */
function setLaunchState(mode, message) {
  if (message) setText("launch-message", message);
  setHidden("btn-open-console", mode !== "ready");
  setHidden("btn-retry", mode !== "failed");
  setHidden("launch-error", mode !== "failed");
  if (mode === "ready") setText("launch-message", "Factory 已就绪。");
}

function showLaunchError(msg) {
  setText("launch-error", msg);
  setHidden("launch-error", false);
}

function startFactory() {
  setLaunchState("busy", "Initializing Factory…");
  setHidden("launch-error", true);
  return tauriInvoke("runtime_start")
    .then(function (raw) {
      var st = JSON.parse(raw);
      if (st.status === "failed") {
        setLaunchState("failed", "Factory startup failed");
        showLaunchError("Factory startup failed: 工厂服务启动失败。");
        showRecovery(true);
        return;
      }
      currentStatus = st;
      renderStatus(st);
      setLaunchState("ready", "");
      showRecovery(false);
      refreshHealth();
    })
    .catch(function (err) {
      setLaunchState("failed", "Factory startup failed");
      showLaunchError(friendlyText(err));
      showRecovery(true);
    });
}

/* ---------- 轮询 (2s) ---------- */
function pollTick() {
  tauriInvoke("runtime_status")
    .then(function (raw) {
      var st = JSON.parse(raw);
      renderStatus(st);
      if (st.status === "failed" || st.status === "stopped") {
        showRecovery(true);
        if (st.status === "failed") {
          setLaunchState("failed", "Factory startup failed");
          showLaunchError("Factory startup failed: 工厂服务运行异常。");
        }
      } else if (st.status === "ready") {
        showRecovery(false);
        setLaunchState("ready", "");
      }
      refreshHealth();
    })
    .catch(function () { /* 轮询失败静默, 下次重试 */ });
}

function refreshHealth() {
  tauriInvoke("health_detail")
    .then(function (raw) { renderHealth(JSON.parse(raw)); })
    .catch(function () { /* 静默 */ });
}

/* ---------- Health Retry ---------- */
function retryHealth() { refreshHealth(); }

/* ---------- Recovery ---------- */
function showRecovery(show) { setHidden("recovery-panel", !show); }

function restartRuntime() {
  var btn = $("btn-restart");
  btn.disabled = true;
  btn.textContent = "Restarting…";
  setHidden("recovery-result", true);
  tauriInvoke("runtime_restart")
    .then(function (raw) {
      var st = JSON.parse(raw);
      renderStatus(st);
      if (st.status === "ready") {
        setText("recovery-result", "恢复完成: 工厂服务已重新就绪。");
        showRecovery(false);
        setLaunchState("ready", "");
        refreshHealth();
      } else {
        setText("recovery-result", "恢复未完成: 工厂服务未就绪 (" + statusLabel(st.status) + ")。");
        setHidden("recovery-result", false);
      }
    })
    .catch(function (err) {
      setText("recovery-result", friendlyText(err));
      setHidden("recovery-result", false);
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Restart Runtime";
    });
}

/* ---------- Logs (3 tab, Troubleshooting) ---------- */
function renderLogs(bundle) {
  var lines = bundle && bundle[activeTab] ? bundle[activeTab] : [];
  var view = $("log-view");
  if (lines.length === 0) {
    view.textContent = "(暂无日志)";
    return;
  }
  view.textContent = lines.join("\n");
}

function loadLogs() {
  setText("log-view", "(加载中…)");
  tauriInvoke("runtime_logs", { lines: LOG_LINES })
    .then(function (raw) { renderLogs(JSON.parse(raw)); })
    .catch(function (err) { setText("log-view", friendlyText(err)); });
}

function switchTab(tab) {
  activeTab = tab;
  var tabs = document.querySelectorAll(".tab");
  for (var i = 0; i < tabs.length; i++) {
    var isActive = tabs[i].getAttribute("data-tab") === tab;
    tabs[i].className = "tab" + (isActive ? " active" : "");
    tabs[i].setAttribute("aria-selected", isActive ? "true" : "false");
  }
  loadLogs();
}

/* ---------- Console 打开 ---------- */
function openConsole() {
  if (!currentStatus || !currentStatus.port) return;
  tauriInvoke("open_console", { port: currentStatus.port }).catch(function () {});
}

/* ---------- 事件绑定 (阶段 1: status/health; logs/recovery 阶段 2 启用) ---------- */
function bindEvents() {
  $("btn-open-console").addEventListener("click", openConsole);
  $("btn-retry").addEventListener("click", startFactory);
}

/* ---------- 初始化: 已有 runtime 直接渲染, 否则首次启动 ---------- */
function init() {
  bindEvents();
  tauriInvoke("runtime_status")
    .then(function (raw) {
      var st = JSON.parse(raw);
      if (st.status === "ready" || st.status === "starting") {
        currentStatus = st;
        renderStatus(st);
        setLaunchState("ready", "");
        refreshHealth();
      } else {
        startFactory();
      }
    })
    .catch(function () { startFactory(); });
  pollTimer = setInterval(pollTick, STATUS_POLL_MS);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
