// ================= 全局变量 =================
let eventSource = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let activeTasks = {};
let taskTimers = {};
let currentTaskFilter = "active";
let lastTasksList = [];
const notifiedTaskIds = new Set();
const expandedConfigTasks = new Set();  // 记录展开的配置任务ID

// 默认提示音 (引用本地文件)
const DEFAULT_DING_SOUND = "/bo.mp3";
// 自动修复：如果 localStorage 中存储的是旧的 base64 格式，则清除并使用新的默认提示音
let storedSound = localStorage.getItem("pdf2zh_custom_sound");
if (storedSound && storedSound.startsWith("data:audio/mp3;base64,")) {
  localStorage.removeItem("pdf2zh_custom_sound");
  storedSound = null;
}
let currentSoundSrc = storedSound || DEFAULT_DING_SOUND;
let audioObj = new Audio(currentSoundSrc);
let isSoundMuted = localStorage.getItem("pdf2zh_sound_muted") === "true";

// ================= Tab 切换 =================
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const content = document.getElementById('tab-' + tabId);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');
  // 保存当前标签页到 localStorage
  localStorage.setItem('pdf2zh_current_tab', tabId);
}

// ================= 声音控制 =================
function initSoundControl() {
  const checkbox = document.getElementById("soundCheckbox");
  const btn = document.getElementById("soundBtn");
  const icon = document.getElementById("soundIcon");
  const text = document.getElementById("soundText");
  checkbox.checked = !isSoundMuted;
  updateSoundUI();
  checkbox.addEventListener("change", (e) => {
    isSoundMuted = !e.target.checked;
    localStorage.setItem("pdf2zh_sound_muted", isSoundMuted);
    updateSoundUI();
    if (!isSoundMuted) playDing(true);
  });
  function updateSoundUI() {
    if (isSoundMuted) { btn.classList.add("muted"); icon.textContent = "\u{1F515}"; text.textContent = "已静音"; }
    else { btn.classList.remove("muted"); icon.textContent = "\u{1F514}"; text.textContent = "提示音"; }
  }
}
function handleSoundUpload(input) {
  const file = input.files[0];
  if (!file) return;
  if (file.size > 500 * 1024) { alert("音频文件过大！请上传小于 500KB 的文件。"); return; }
  const reader = new FileReader();
  reader.onload = function (e) {
    try {
      localStorage.setItem("pdf2zh_custom_sound", e.target.result);
      currentSoundSrc = e.target.result;
      audioObj = new Audio(currentSoundSrc);
      alert("自定义提示音设置成功！");
      if (!isSoundMuted) playDing(true);
    } catch (err) { alert("保存失败：浏览器存储空间不足。"); }
  };
  reader.readAsDataURL(file);
}
function resetDefaultSound() {
  if (confirm("确定要恢复默认提示音吗？")) {
    localStorage.removeItem("pdf2zh_custom_sound");
    currentSoundSrc = DEFAULT_DING_SOUND;
    audioObj = new Audio(currentSoundSrc);
    if (!isSoundMuted) playDing(true);
  }
}
function playDing(force = false) {
  if (!isSoundMuted || force) { audioObj.currentTime = 0; audioObj.play().catch(() => {}); }
}

// ================= 工具函数 =================
function getFileTypeLabel(filename) {
  const lower = filename.toLowerCase();
  if (lower.includes('crop-compare') || lower.includes('crop.compare')) return { code: 'crop-compare', desc: '裁剪对照(双栏专用)' };
  if (lower.includes('mono-cut') || lower.includes('mono.cut')) return { code: 'mono-cut', desc: '译文裁剪' };
  if (lower.includes('dual-cut') || lower.includes('dual.cut')) return { code: 'dual-cut', desc: '双语裁剪' };
  if (lower.includes('lr_dual')) return { code: 'LR_dual', desc: '左右双语' };
  if (lower.includes('tb_dual')) return { code: 'TB_dual', desc: '上下双语' };
  if (lower.includes('compare')) return { code: 'compare', desc: '左右对照' };
  if (lower.includes('mono')) return { code: 'mono', desc: '纯译文' };
  if (lower.includes('dual')) return { code: 'dual', desc: '双语对照' };
  return { code: '', desc: '文件' };
}
function formatTime(isoString) {
  if (!isoString) return "-";
  return new Date(isoString).toLocaleString("zh-CN", { year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit" });
}
function calculateDuration(startTime, endTime) {
  if (!startTime || !endTime) return "-";
  return formatDuration(Math.floor((new Date(endTime) - new Date(startTime)) / 1000));
}
function formatDuration(seconds) {
  const m = Math.floor(seconds / 60), s = seconds % 60;
  return `${m}分${s.toString().padStart(2,"0")}秒`;
}
// 渲染配置摘要 HTML
function renderConfigHtml(cfg) {
  if (!cfg) return '';
  const labels = {
    sourceLang:'源语言', targetLang:'目标语言', outputTypes:'输出类型',
    threadNum:'线程数', babeldoc:'BabelDoc', qps:'QPS',
    dualMode:'双语模式', noWatermark:'去水印', ocr:'OCR', poolSize:'并发池',
    skipLastPages:'跳过末页'
  };
  return Object.entries(cfg).map(([k,v]) => {
    const label = labels[k] || k;
    let val = v;
    if (Array.isArray(v)) val = v.join(', ') || '-';
    if (typeof v === 'boolean') val = v ? '是' : '否';
    return `<div class="config-row"><span class="config-key">${label}</span><span class="config-val">${val}</span></div>`;
  }).join('');
}

// ================= 任务计时器 =================
function updateTaskTimer(taskId, startTimeStr) {
  if (taskTimers[taskId]) clearInterval(taskTimers[taskId]);
  if (!startTimeStr) return;
  const startTime = new Date(startTimeStr).getTime();
  const el = document.getElementById(`elapsedTime-${taskId}`);
  if (!el) return;
  el.textContent = formatDuration(Math.floor((Date.now() - startTime) / 1000));
  taskTimers[taskId] = setInterval(() => {
    el.textContent = formatDuration(Math.floor((Date.now() - startTime) / 1000));
  }, 1000);
}
function stopTaskTimer(taskId) {
  if (taskTimers[taskId]) { clearInterval(taskTimers[taskId]); delete taskTimers[taskId]; }
}

// ================= PDF 预览 =================
function openPdfPreview(url, filename) {
  if (window.event) window.event.stopPropagation();
  document.getElementById("pdfModalTitle").textContent = "预览: " + filename;
  document.getElementById("pdfFrame").src = url;
  document.getElementById("pdfModal").style.display = "flex";
}
function closePdfPreview() {
  document.getElementById("pdfModal").style.display = "none";
  document.getElementById("pdfFrame").src = "";
}
document.getElementById("pdfModal").addEventListener("click", function(e) { if (e.target === this) closePdfPreview(); });

// ================= 历史记录管理 =================
const STORAGE_KEY = "pdf2zh_history_v2";
function getLocalHistory() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch(e) { return []; } }
function saveLocalHistory(h) { localStorage.setItem(STORAGE_KEY, JSON.stringify(h)); }
function clearLocalHistory() { if (confirm("确定要清空所有本地历史记录吗？")) { localStorage.removeItem(STORAGE_KEY); displayHistory([]); } }
function mergeHistory(serverHistory) {
  let local = getLocalHistory();
  const map = new Map();
  local.forEach(i => map.set(i.fileName + i.startTime, i));
  serverHistory.forEach(i => map.set(i.fileName + i.startTime, i));
  const merged = Array.from(map.values()).sort((a,b) => new Date(b.startTime) - new Date(a.startTime));
  saveLocalHistory(merged);
  return merged;
}
async function cancelTask(taskId) {
  if (!confirm("确认取消该任务? wenyi 运行时是共享的, 全部运行中的 wenyi 任务都会被停止。")) return;
  try {
    const res = await fetch("/api/task/cancel", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({taskId}),
    });
    const data = await res.json();
    if (!res.ok) alert(data.message || "取消失败");
  } catch (e) { alert("取消请求失败: " + e); }
}
function toggleHistoryItem(el) { el.classList.toggle("expanded"); }
function toggleTaskConfig(btn) {
  const detail = btn.nextElementSibling;
  if (detail) {
    detail.classList.toggle('show');
    btn.textContent = detail.classList.contains('show') ? '收起配置 ▲' : '查看翻译配置 ▼';
    // 记录展开状态
    const taskId = btn.closest('.task-card')?.id?.replace('task-', '');
    if (taskId) {
      if (detail.classList.contains('show')) expandedConfigTasks.add(taskId);
      else expandedConfigTasks.delete(taskId);
    }
  }
}

// ================= 界面状态规范化 =================
function normalizeTaskState(task) {
  const raw = (task.status || "").toString(), isActive = !!task.active;
  if (isActive) return { state:"active", badgeText:"翻译中", badgeClass:"active" };
  const low = raw.toLowerCase();
  if (raw==="完成"||raw==="翻译成功"||low==="success") return { state:"success", badgeText:"成功", badgeClass:"completed" };
  if (raw==="失败"||raw==="翻译失败"||raw==="报错"||low==="failed"||low==="error") return { state:"failed", badgeText:"失败", badgeClass:"failed" };
  if (low==="cancelled"||raw==="已取消") return { state:"cancelled", badgeText:"已取消", badgeClass:"failed" };
  return { state:"idle", badgeText: raw||"等待中", badgeClass:"" };
}
function sortTasks(tasks) {
  return tasks.slice().sort((a,b) => {
    const aa = a.active?0:1, bb = b.active?0:1;
    if (aa !== bb) return aa - bb;
    return (b.startTime?new Date(b.startTime).getTime():0) - (a.startTime?new Date(a.startTime).getTime():0);
  });
}
function filterTasks(tasks) {
  if (currentTaskFilter==="all") return tasks;
  if (currentTaskFilter==="active") return tasks.filter(t => !!t.active);
  if (currentTaskFilter==="success") return tasks.filter(t => normalizeTaskState(t).state==="success");
  if (currentTaskFilter==="failed") return tasks.filter(t => normalizeTaskState(t).state==="failed");
  return tasks;
}

// ================= 更新任务列表 =================
function updateTasks(tasksList) {
  lastTasksList = Array.isArray(tasksList) ? tasksList : [];
  const tasksContainer = document.getElementById("tasksContainer");
  const taskCount = document.getElementById("taskCount");
  const taskStats = document.getElementById("taskStats");
  const badge = document.getElementById("tabTaskBadge");

  const activeCount = tasksList.filter(t => !!t.active).length;
  const successCount = tasksList.filter(t => normalizeTaskState(t).state==="success").length;
  const failedCount = tasksList.filter(t => normalizeTaskState(t).state==="failed").length;
  taskCount.textContent = `${activeCount} 个活动任务`;
  taskCount.className = `status-badge ${activeCount > 0 ? "active" : "idle"}`;
  taskStats.textContent = `进行中 ${activeCount} \u00b7 成功 ${successCount} \u00b7 失败 ${failedCount}`;
  // 更新 tab badge
  if (activeCount > 0) { badge.textContent = activeCount; badge.style.display = 'inline'; }
  else { badge.style.display = 'none'; }

  const sorted = sortTasks(tasksList), shown = filterTasks(sorted);
  if (shown.length === 0) {
    tasksContainer.innerHTML = '<div style="text-align:center;padding:40px;color:#999"><p>暂无符合筛选条件的任务</p></div>';
  } else {
    tasksContainer.innerHTML = shown.map(task => {
      const taskId = task.taskId || "unknown", isActive = !!task.active;
      const n = normalizeTaskState(task);
      let progress = Number.isFinite(task.progress) ? task.progress : parseInt(task.progress||"0",10);
      if (!Number.isFinite(progress)) progress = 0;
      if (n.state==="success") progress = 100;
      let cardClass = "task-card", badgeClass = "task-badge", badgeText = n.badgeText;
      if (n.state==="active") { badgeClass+=" active"; updateTaskTimer(taskId, task.startTime); }
      else if (n.state==="success") { cardClass+=" completed"; badgeClass+=" completed"; stopTaskTimer(taskId); }
      else if (n.state==="failed") { cardClass+=" failed"; badgeClass+=" failed"; stopTaskTimer(taskId); }
      else { stopTaskTimer(taskId); }
      let elapsed = "-";
      if (task.startTime) {
        if (isActive) elapsed = `<span id="elapsedTime-${taskId}">计算中...</span>`;
        else { elapsed = formatDuration(Math.floor(((task.endTime?new Date(task.endTime):new Date()) - new Date(task.startTime)) / 1000)); }
      }
      let msgHtml = "";
      if (task.message) { let mc = "task-message"; if(n.state==="failed") mc+=" error"; else if(n.state==="success") mc+=" success"; msgHtml = `<div class="${mc}" style="display:block">${task.message}</div>`; }
      // 配置摘要
      let cfgHtml = '';
      if (task.config) {
        const isExpanded = expandedConfigTasks.has(taskId);
        cfgHtml = `<div class="task-config-toggle ${isExpanded?'expanded':''}" onclick="toggleTaskConfig(this)">${isExpanded ? '收起配置 ▲' : '查看翻译配置 ▼'}</div><div class="task-config-detail ${isExpanded?'show':''} config-display">${renderConfigHtml(task.config)}</div>`;
      }
      const cancelBtn = (isActive && task.engine === "wenyi")
        ? `<button class="action-btn" style="margin-left:8px;padding:2px 10px;font-size:12px" title="停止 wenyi 运行时(会取消全部运行中的 wenyi 任务)" onclick="cancelTask('${taskId}')">取消</button>`
        : "";
      return `<div class="${cardClass}" id="task-${taskId}">
        <div class="task-header"><div class="task-filename">${task.fileName||"未知文件"}</div>${cancelBtn}<div class="${badgeClass}">${badgeText}</div></div>
        <div class="task-progress-bar"><div class="task-progress-fill" style="width:${progress}%"></div></div>
        <div class="task-info">
          <div class="task-info-item"><div class="task-info-label">进度</div><div class="task-info-value">${progress}%</div></div>
          <div class="task-info-item"><div class="task-info-label">开始</div><div class="task-info-value">${formatTime(task.startTime)}</div></div>
          <div class="task-info-item"><div class="task-info-label">引擎</div><div class="task-info-value">${task.engine||"-"}</div></div>
          <div class="task-info-item"><div class="task-info-label">服务</div><div class="task-info-value">${task.service||"-"}</div></div>
          <div class="task-info-item"><div class="task-info-label">模型</div><div class="task-info-value" title="${task.modelName||'-'}">${task.modelName||'默认模型'}</div></div>
          <div class="task-info-item"><div class="task-info-label">耗时</div><div class="task-info-value">${elapsed}</div></div>
        </div>
        ${msgHtml}${cfgHtml}
      </div>`;
    }).join("");
  }
  // 提示音 & 历史刷新
  tasksList.forEach(task => {
    const st = normalizeTaskState(task).state;
    if (!task.active && (st==="success"||st==="failed") && !notifiedTaskIds.has(task.taskId)) {
      playDing(); notifiedTaskIds.add(task.taskId); setTimeout(syncHistory, 1500);
    }
  });
  activeTasks = {};
  tasksList.forEach(task => { activeTasks[task.taskId] = task; });
}

// ================= SSE 连接 =================
function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/events");
  eventSource.onopen = function () {
    document.getElementById("connectionStatus").className = "connection-status connected";
    document.getElementById("connectionStatus").textContent = "\u25cf 已连接";
    reconnectAttempts = 0;
  };
  eventSource.onmessage = function (event) {
    try { const data = JSON.parse(event.data); if (data.type === "tasks") updateTasks(data.data); } catch(e) {}
  };
  eventSource.onerror = function () {
    document.getElementById("connectionStatus").className = "connection-status disconnected";
    document.getElementById("connectionStatus").textContent = "\u25cf 未连接";
    eventSource.close();
    Object.keys(taskTimers).forEach(id => stopTaskTimer(id));
    reconnectAttempts++;
    if (reconnectAttempts < maxReconnectAttempts) setTimeout(connectSSE, 3000);
  };
}

// ================= 历史记录渲染 =================
async function syncHistory() {
  try {
    const resp = await fetch("/api/history"), result = await resp.json();
    displayHistory(result.status==="success" ? mergeHistory(result.history) : getLocalHistory());
  } catch(e) { displayHistory(getLocalHistory()); }
}
function displayHistory(history) {
  const el = document.getElementById("historyList");
  if (!history || history.length===0) {
    el.innerHTML = '<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg><p>暂无翻译记录</p></div>';
    return;
  }
  el.innerHTML = history.map(item => {
    const isSuccess = item.status==="success", sc = isSuccess?"success":"failed", st = isSuccess?"成功":"失败";
    const duration = calculateDuration(item.startTime, item.endTime), timeStr = formatTime(item.startTime);
    // 文件按钮
    let filesHtml = "";
    if (isSuccess && item.fileList && item.fileList.length > 0) {
      filesHtml = `<div class="history-files" onclick="event.stopPropagation()">${item.fileList.map(file => {
        const url = `/translatedFile/${encodeURIComponent(file)}`, ft = getFileTypeLabel(file);
        const tag = ft.code ? `<span class="file-type-tag"><span class="ft-code">${ft.code}</span><span class="ft-desc">${ft.desc}</span></span>` : `<span class="file-type-tag"><span class="ft-desc">${ft.desc}</span></span>`;
        return `<div class="file-action-group">${tag}<a href="${url}" class="file-btn download" download title="下载 ${ft.code||file}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>下载</a><button onclick="openPdfPreview('${url}?preview=true','${file}')" class="file-btn preview" title="预览 ${ft.code||file}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>预览</button></div>`;
      }).join("")}</div>`;
    }
    let errorHtml = !isSuccess && item.error ? `<div class="error-message"><strong>错误信息:</strong> ${item.error}</div>` : "";
    // 配置摘要
    let cfgSection = "";
    if (item.config) {
      cfgSection = `<div style="margin-top:10px"><strong style="font-size:13px;color:#333">翻译配置:</strong><div class="config-display" style="margin-top:6px">${renderConfigHtml(item.config)}</div></div>`;
    }
    return `<div class="history-item ${sc}" onclick="toggleHistoryItem(this)">
      <div class="history-summary"><div><div class="history-filename">${item.fileName||"未知文件"}</div><div class="history-time">${timeStr}</div></div><div style="display:flex;align-items:center"><span class="status-dot ${sc}"></span><span class="status-text">${st}</span></div></div>
      <div class="history-details">
        <div class="meta-grid"><div><strong>引擎:</strong> ${item.engine||"-"}</div><div><strong>服务:</strong> ${item.service||"-"}</div><div><strong>模型:</strong> ${item.modelName||'默认模型'}</div><div><strong>耗时:</strong> ${duration}</div><div><strong>结束:</strong> ${formatTime(item.endTime)}</div></div>
        ${cfgSection}${filesHtml}${errorHtml}
      </div>
    </div>`;
  }).join("");
}

// ================= 加载服务器配置 =================
async function loadServerConfig() {
  const el = document.getElementById("serverConfigDisplay");
  try {
    const resp = await fetch("/api/config"), result = await resp.json();
    if (result.status === "success") {
      const c = result.config;
      const labels = { version:"服务器版本", port:"端口号", enable_venv:"虚拟环境", env_tool:"环境工具", enable_mirror:"镜像加速", mirror_source:"镜像源", skip_install:"跳过安装", enable_winexe:"Win EXE 模式" };
      el.innerHTML = Object.entries(c).map(([k,v]) => `<div class="config-row"><span class="config-key">${labels[k]||k}</span><span class="config-val">${v}</span></div>`).join("");
    } else { el.innerHTML = '<div style="color:#999;padding:10px 0">无法获取配置</div>'; }
  } catch(e) { el.innerHTML = '<div style="color:#ddd;padding:10px 0">暂不可用</div>'; }
}

// ================= 初始化 =================
window.addEventListener("load", function () {
  // 恢复上次标签页
  const savedTab = localStorage.getItem('pdf2zh_current_tab');
  if (savedTab) switchTab(savedTab);
  // Tab 切换
  document.getElementById("tabNav").addEventListener("click", e => {
    const btn = e.target.closest(".tab-btn[data-tab]");
    if (btn) switchTab(btn.dataset.tab);
  });
  // 任务筛选
  const filterEl = document.getElementById("taskFilter");
  if (filterEl) {
    filterEl.addEventListener("click", e => {
      const btn = e.target.closest("button[data-filter]");
      if (!btn) return;
      currentTaskFilter = btn.dataset.filter;
      Array.from(filterEl.querySelectorAll(".seg-btn")).forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      updateTasks(lastTasksList);
    });
  }
  displayHistory(getLocalHistory());
  connectSSE();
  syncHistory();
  initSoundControl();
  loadServerConfig();
});
window.addEventListener("beforeunload", function () {
  if (eventSource) eventSource.close();
  Object.keys(taskTimers).forEach(id => stopTaskTimer(id));
});
