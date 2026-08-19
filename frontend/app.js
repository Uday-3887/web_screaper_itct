const state = {
  jobs: [],
  selectedJob: null,
  currentView: "dashboard",
  pollTimer: null,
  dataRows: [],
  user: { name: "Admin", email: "Direct access" },
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const activeStatuses = new Set(["queued", "running", "stopping"]);
const DEVICE_ID_KEY = "itcyber-device-id";

function getDeviceId() {
  try {
    let deviceId = localStorage.getItem(DEVICE_ID_KEY);
    if (!deviceId) {
      if (globalThis.crypto?.randomUUID) {
        deviceId = globalThis.crypto.randomUUID();
      } else {
        deviceId = `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
      }
      localStorage.setItem(DEVICE_ID_KEY, deviceId);
    }
    return deviceId;
  } catch (error) {
    console.warn("Could not persist device id; using an in-memory id.", error);
    if (!state.deviceId) {
      state.deviceId = globalThis.crypto?.randomUUID?.() || `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    }
    return state.deviceId;
  }
}
function configuredApiBase() {
  const configured = String(
    window.ITCYBER_CONFIG?.apiBaseUrl || ""
  )
    .trim()
    .replace(/\/$/, "");

  if (!configured || configured.includes("YOUR-RAILWAY")) {
    return "";
  }

  try {
    const url = new URL(configured);

    const isLocal =
      url.hostname === "localhost" ||
      url.hostname === "127.0.0.1";

    if (
      url.protocol !== "https:" &&
      !(isLocal && url.protocol === "http:")
    ) {
      return "";
    }

    return url.origin;
  } catch (error) {
    console.error("Invalid backend URL:", error);
    return "";
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message, error = false) {
  const box = $("#toast");
  $("#toastText").textContent = message;
  $("#toastIcon").textContent = error ? "!" : "✓";
  box.classList.toggle("error", error);
  box.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove("show"), 3600);
}

async function api(path, options = {}) {
  const apiBase = configuredApiBase();
  if (!apiBase) throw new Error("Railway backend URL is not configured in frontend/config.js.");
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    mode: "cors",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Client-ID": getDeviceId(),
      ...(options.headers || {}),
    },
  });
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const error = new Error("Railway scraper backend is unavailable or returned an invalid response.");
    error.status = response.status;
    throw error;
  }
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

function initials(name) {
  const parts = String(name || "Admin").trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => part[0]).join("") || "AD").toUpperCase();
}

function renderUser(user = { name: "Admin", email: "Direct access" }) {
  state.user = user;
  const label = user?.name || "Admin";
  $("#userName").textContent = label;
  $("#userInitials").textContent = initials(label);
}

async function showApp(user = { name: "Admin", email: "Direct access" }) {
  renderUser(user);
  $("#appShell").classList.remove("hidden");
  setBackendStatus("online");
  await refreshJobs();
  if (!state.pollTimer) state.pollTimer = setInterval(refreshJobs, 1600);
}

function setBackendStatus(mode) {
  const pill = $("#enginePill");
  pill.classList.remove("online", "preview");
  if (mode === "online") {
    pill.classList.add("online");
    pill.querySelector("span").textContent = "Engine online";
    $("#sidebarEngineText").textContent = "Railway backend connected";
  } else {
    pill.querySelector("span").textContent = "Engine offline";
    $("#sidebarEngineText").textContent = "Check dashboard terminal";
  }
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function labelMode(mode) {
  return ({ none: "Google only", website: "Google + Website", full: "Full social" })[mode] || mode;
}

function statusBadge(status) {
  return `<span class="status-badge ${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function recordsFor(job) {
  return Number(job?.progress?.records || 0);
}

function renderMetrics() {
  const completed = state.jobs.filter((job) => job.status === "completed").length;
  const running = state.jobs.filter((job) => activeStatuses.has(job.status)).length;
  const records = state.jobs.reduce((sum, job) => sum + recordsFor(job), 0);
  $("#metricJobs").textContent = state.jobs.length;
  $("#metricCompleted").textContent = completed;
  $("#metricRunning").textContent = running;
  $("#metricRecords").textContent = records;
  $("#heroRecords").textContent = records;
  $("#metricJobsSub").textContent = state.jobs.length ? "Stored on Railway volume" : "No jobs yet";
  $("#metricRunningSub").textContent = running ? "Browser extraction active" : "Engine is idle";
}

function jobRow(job, compact = false) {
  const actions = `
    <button class="table-action" data-inspect="${escapeHtml(job.id)}">View</button>
    ${job.download_ready ? `<button class="table-action" data-download="${escapeHtml(job.id)}">Download</button>` : ""}
  `;
  if (compact) {
    return `<tr>
      <td class="job-name"><strong>${escapeHtml(job.query)}</strong><small>${escapeHtml(job.id)}</small></td>
      <td>${escapeHtml(labelMode(job.enrichment))}</td><td>${statusBadge(job.status)}</td>
      <td>${recordsFor(job)}</td><td>${escapeHtml(formatDate(job.created_at))}</td><td>${actions}</td>
    </tr>`;
  }
  return `<tr>
    <td class="job-name"><strong>${escapeHtml(job.query)}</strong><small>${escapeHtml(job.id)}</small></td>
    <td>${escapeHtml(job.max_results)}</td><td>${escapeHtml(labelMode(job.enrichment))}</td>
    <td>${statusBadge(job.status)}</td><td>${recordsFor(job)}</td>
    <td>${escapeHtml(formatDate(job.started_at || job.created_at))}</td><td>${actions}</td>
  </tr>`;
}

function renderJobs() {
  const recent = state.jobs.slice(0, 5);
  $("#recentJobsBody").innerHTML = recent.length ? recent.map((job) => jobRow(job, true)).join("") : `<tr><td colspan="6" class="empty-cell">No scraping jobs yet.</td></tr>`;

  const query = $("#jobSearch").value.trim().toLowerCase();
  const status = $("#statusFilter").value;
  const filtered = state.jobs.filter((job) => {
    const queryMatch = !query || `${job.query} ${job.id}`.toLowerCase().includes(query);
    const statusMatch = status === "all" || job.status === status;
    return queryMatch && statusMatch;
  });
  $("#allJobsBody").innerHTML = filtered.length ? filtered.map((job) => jobRow(job)).join("") : `<tr><td colspan="7" class="empty-cell">No jobs match this filter.</td></tr>`;

  const select = $("#dataJobSelect");
  const currentValue = select.value;
  const ready = state.jobs.filter((job) => job.download_ready);
  select.innerHTML = `<option value="">Choose a job…</option>${ready.map((job) => `<option value="${escapeHtml(job.id)}">${escapeHtml(job.query)} · ${escapeHtml(formatDate(job.created_at))}</option>`).join("")}`;
  if (ready.some((job) => job.id === currentValue)) select.value = currentValue;
}

function stageLabel(stage) {
  return ({
    queued: "Queued", starting: "Starting browser", discovering: "Discovering listings",
    extracting: "Reading Google details", enriching: "Enriching and checkpointing",
    completed: "Completed", failed: "Failed", stopped: "Stopped", stopping: "Stopping safely",
  })[stage] || "Working";
}

function renderActive(job) {
  const empty = $("#emptyActive");
  const panel = $("#activeJob");
  if (!job) {
    empty.classList.remove("hidden"); panel.classList.add("hidden");
    $("#liveDot").classList.remove("running"); $("#liveDot span").textContent = "Idle";
    return;
  }
  empty.classList.add("hidden"); panel.classList.remove("hidden");
  const progress = job.progress || {};
  const running = activeStatuses.has(job.status);
  $("#liveDot").classList.toggle("running", running);
  $("#liveDot span").textContent = running ? "Live" : job.status;
  $("#activeJobId").textContent = job.id;
  $("#activeQuery").textContent = job.query;
  $("#progressStage").textContent = stageLabel(progress.stage || job.status);
  $("#progressPercent").textContent = `${progress.percent || 0}%`;
  $("#progressBar").style.width = `${Math.max(0, Math.min(100, progress.percent || 0))}%`;
  $("#progressDiscovered").textContent = progress.discovered || 0;
  $("#progressCurrent").textContent = `${progress.current || 0} / ${progress.total || progress.discovery_target || 0}`;
  $("#progressRecords").textContent = progress.records || 0;
  $("#liveLogs").textContent = (job.logs || ["Waiting for scraper output…"]).slice(-60).join("\n");
  $("#liveLogs").scrollTop = $("#liveLogs").scrollHeight;
  $("#stopButton").classList.toggle("hidden", !running);
  $("#viewActiveData").classList.toggle("hidden", !job.download_ready);
  $("#downloadActive").classList.toggle("hidden", !job.download_ready);
  $("#startButton").disabled = state.jobs.some((item) => activeStatuses.has(item.status));
}

async function refreshJobs() {
  try {
    const payload = await api("/api/jobs");
    state.jobs = payload.jobs || [];
    renderMetrics(); renderJobs();
    const active = state.jobs.find((job) => activeStatuses.has(job.status));
    const preferred = active || (state.selectedJob && state.jobs.find((job) => job.id === state.selectedJob.id)) || state.jobs[0];
    if (preferred) {
      try { state.selectedJob = await api(`/api/jobs/${encodeURIComponent(preferred.id)}`); }
      catch { state.selectedJob = preferred; }
    } else state.selectedJob = null;
    renderActive(state.selectedJob);
  } catch (error) {
    setBackendStatus("offline");
    toast(error.message, true);
  }
}

function switchView(view) {
  state.currentView = view;
  $$(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  $("#pageTitle").textContent = ({ dashboard: "Scraper dashboard", jobs: "Scraping jobs", data: "Lead database", safety: "Safety & limits" })[view];
  $("#sidebar").classList.remove("open"); $("#sidebarBackdrop").classList.remove("show");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function startJob(event) {
  event.preventDefault();
  const maxResults = Number($("#maxResults").value);
  if (!Number.isInteger(maxResults) || maxResults < 1 || maxResults > 2000) {
    toast("Maximum results must be a whole number from 1 to 2000.", true);
    $("#maxResults").focus();
    return;
  }
  const payload = {
    query: $("#query").value,
    max_results: maxResults,
    enrichment: $("#enrichment").value,
    format: $("#format").value,
    max_website_pages: Number($("#websitePages").value),
    delay: 2.5,
  };
  $("#startButton").disabled = true;
  try {
    state.selectedJob = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    toast("Scraping job started on the Railway browser worker.");
    await refreshJobs();
  } catch (error) {
    toast(error.message, true); $("#startButton").disabled = false;
  }
}

async function stopJob() {
  if (!state.selectedJob) return;
  try {
    state.selectedJob = await api(`/api/jobs/${encodeURIComponent(state.selectedJob.id)}/stop`, { method: "POST", body: "{}" });
    renderActive(state.selectedJob); toast("Stop requested. Existing checkpoint data will be kept.");
  } catch (error) { toast(error.message, true); }
}

async function inspectJob(id) {
  const job = state.jobs.find((item) => item.id === id);
  if (!job) return;
  try { state.selectedJob = await api(`/api/jobs/${encodeURIComponent(id)}`); }
  catch (error) { return toast(error.message, true); }
  renderActive(state.selectedJob); switchView("dashboard");
  $("#activeJob").scrollIntoView({ behavior: "smooth", block: "center" });
}

async function downloadJob(id) {
  const apiBase = configuredApiBase();
  if (!apiBase) return toast("Railway backend URL is not configured in frontend/config.js.", true);
  try {
    const response = await fetch(`${apiBase}/api/jobs/${encodeURIComponent(id)}/download`, {
      mode: "cors",
      cache: "no-store",
      headers: {
        "X-Client-ID": getDeviceId(),
      },
    });
    if (!response.ok) {
      let message = `Download failed (${response.status}).`;
      try { message = (await response.json()).error || message; } catch { /* Use the status message. */ }
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = (match?.[1] || `itcyber-results-${id}`).replace(/[^a-zA-Z0-9._-]/g, "_");
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadData(jobId) {
  if (!jobId) {
    $("#dataHead").innerHTML = "";
    $("#dataBody").innerHTML = `<tr><td class="empty-cell">Choose a job with saved output to preview its data.</td></tr>`;
    $("#dataSummary").innerHTML = `<div><strong>0</strong><span>rows in file</span></div><p>No job selected</p>`;
    $("#dataDownload").classList.add("hidden");
    return;
  }
  try {
    const search = encodeURIComponent($("#dataSearch").value.trim());
    const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}/results?limit=2000&q=${search}`);
    renderData(payload.columns, payload.rows, payload.total, `${payload.filtered} matching row(s)`);
    $("#dataDownload").classList.remove("hidden");
    $("#dataDownload").dataset.jobId = jobId;
  } catch (error) { toast(error.message, true); }
}

function renderData(columns, rows, total, label) {
  $("#dataHead").innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column.replaceAll("_", " "))}</th>`).join("")}</tr>`;
  $("#dataBody").innerHTML = rows.length
    ? rows.map((row) => `<tr>${columns.map((column) => `<td title="${escapeHtml(row[column])}">${escapeHtml(row[column])}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${Math.max(1, columns.length)}" class="empty-cell">No matching rows.</td></tr>`;
  $("#dataSummary").innerHTML = `<div><strong>${total}</strong><span>rows in file</span></div><p>${escapeHtml(label)}</p>`;
}

function updateModeNote() {
  const mode = $("#enrichment").value;
  const copy = {
    none: ["Fast diagnostic mode", "collects Google Maps fields only. Use this first to confirm Maps works."],
    website: ["Balanced mode", "collects Google details and checks a small number of official website contact pages."],
    full: ["Full enrichment mode", "also visits discovered public company social pages and will take significantly longer."],
  }[mode];
  $("#modeNote p").innerHTML = `<strong>${copy[0]}:</strong> ${copy[1]}`;
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $$('[data-view-link]').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewLink)));
  $("#menuButton").addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#sidebarBackdrop").classList.add("show"); });
  $("#sidebarBackdrop").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#sidebarBackdrop").classList.remove("show"); });
  $("#themeButton").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("itcyber-theme", next);
    $("#themeButton").textContent = next === "dark" ? "☀" : "☾";
  });
  $$(".presets button").forEach((button) => button.addEventListener("click", () => { $("#query").value = button.dataset.query; $("#query").focus(); }));
  $("#enrichment").addEventListener("change", updateModeNote);
  $("#jobForm").addEventListener("submit", startJob);
  $("#stopButton").addEventListener("click", stopJob);
  $("#viewActiveData").addEventListener("click", () => { switchView("data"); $("#dataJobSelect").value = state.selectedJob.id; loadData(state.selectedJob.id); });
  $("#downloadActive").addEventListener("click", () => downloadJob(state.selectedJob.id));
  $("#dataDownload").addEventListener("click", (event) => downloadJob(event.currentTarget.dataset.jobId));
  $("#jobSearch").addEventListener("input", renderJobs);
  $("#statusFilter").addEventListener("change", renderJobs);
  $("#dataJobSelect").addEventListener("change", (event) => loadData(event.target.value));
  let searchTimer;
  $("#dataSearch").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadData($("#dataJobSelect").value), 300); });
  document.addEventListener("click", (event) => {
    const inspect = event.target.closest("[data-inspect]");
    const download = event.target.closest("[data-download]");
    if (inspect) inspectJob(inspect.dataset.inspect);
    if (download) downloadJob(download.dataset.download);
  });
}

async function init() {
  getDeviceId();
  const theme = localStorage.getItem("itcyber-theme") || "dark";
  document.documentElement.dataset.theme = theme;
  $("#themeButton").textContent = theme === "dark" ? "☀" : "☾";
  bindEvents();
  updateModeNote();
  renderUser({ name: "Admin", email: "Direct access" });
  $("#appShell").classList.remove("hidden");
  try {
    await api("/api/health");
    await showApp({ name: "Admin", email: "Direct access" });
  } catch (error) {
    setBackendStatus("offline");
    toast(error.message || "Railway backend is unavailable. Check config.js and Railway logs.", true);
  }
}

init();
