const state = {
  jobs: [], agents: [], approvals: [], connectors: [], internships: [], searches: [], alarms: [],
  selectedJobId: null, selectedJob: null, selectedInternshipId: null, selectedInternship: null,
  resumeReady: false, resume: null, sharedJobPage: null,
  careerView: "opportunities", internshipFilters: { query: "", stage: "all", sort: "match" },
  chat: [], chatBusy: false, mode: "labyrinth",
  weather: null, focusOpen: false, orbitPrevious: null, delegatedJobs: {}, ringingAlarm: null,
  gestures: { tracker: null, starting: false, hands: 0, mode: "idle" },
  orbit: { angle: -12, tilt: 50, zoom: 1.02, panX: "0px", panY: "0px", dragging: false, x: 0, y: 0 }
};
const $ = (selector) => document.querySelector(selector);
let handControlsModulePromise = null;
let labyrinthScene = null;
let labyrinthScenePromise = null;
let alarmAudioContext = null;
const loadHandControlsModule = () => {
  if (!handControlsModulePromise) handControlsModulePromise = import("/hand-controls.js?v=4");
  return handControlsModulePromise;
};
const loadLabyrinthScene = () => {
  if (!labyrinthScenePromise) labyrinthScenePromise = import("/labyrinth-scene.js?v=22");
  return labyrinthScenePromise;
};

// Mobile browsers and split-screen windows change the *visible* frame without
// always updating 100vh. Keep one authoritative height in CSS so the world,
// drawers, chat, and dialogs all resize together (including when a phone
// keyboard opens).
function syncViewportFrame() {
  const viewport = window.visualViewport;
  const width = Math.max(320, Math.round(viewport?.width || window.innerWidth));
  const height = Math.max(320, Math.round(viewport?.height || window.innerHeight));
  document.documentElement.style.setProperty("--app-width", `${width}px`);
  document.documentElement.style.setProperty("--app-height", `${height}px`);
  document.documentElement.toggleAttribute("data-short-frame", height <= 620);
  document.documentElement.toggleAttribute("data-narrow-frame", width <= 760);
}

syncViewportFrame();
window.addEventListener("resize", syncViewportFrame, { passive: true });
window.addEventListener("orientationchange", syncViewportFrame, { passive: true });
window.visualViewport?.addEventListener("resize", syncViewportFrame, { passive: true });

async function startLabyrinthScene() {
  if (labyrinthScene) return labyrinthScene;
  try {
    const { ShepardLabyrinthScene } = await loadLabyrinthScene();
    labyrinthScene = new ShepardLabyrinthScene($("#labyrinth-stage"), {
      getCamera: () => state.orbit,
      reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches
    });
    labyrinthScene.syncDomains();
    syncLabyrinth();
    return labyrinthScene;
  } catch (error) {
    console.warn("The projected Labyrinth could not start; using the accessible fallback.", error);
    return null;
  }
}
const escapeHTML = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
})[char]);

function renderInlineMarkdown(value = "") {
  let html = escapeHTML(value);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return html;
}

function tableCells(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function renderMarkdown(value = "") {
  const lines = String(value).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = "";
  let codeLines = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (!listType) return;
    blocks.push(`</${listType}>`);
    listType = "";
  };
  const openList = (type) => {
    if (listType === type) return;
    closeList();
    blocks.push(`<${type}>`);
    listType = type;
  };
  const flushFlow = () => {
    flushParagraph();
    closeList();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (codeLines !== null) {
      if (/^\s*```/.test(line)) {
        blocks.push(`<pre><code>${escapeHTML(codeLines.join("\n"))}</code></pre>`);
        codeLines = null;
      } else {
        codeLines.push(line);
      }
      continue;
    }
    if (/^\s*```/.test(line)) {
      flushFlow();
      codeLines = [];
      continue;
    }
    if (!line.trim()) {
      flushFlow();
      continue;
    }
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushFlow();
      blocks.push("<hr>");
      continue;
    }
    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
    if (heading) {
      flushFlow();
      const level = Math.min(6, heading[1].length + 2);
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const next = lines[index + 1] || "";
    const tableDivider = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;
    if (line.includes("|") && tableDivider.test(next)) {
      flushFlow();
      const headers = tableCells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      index -= 1;
      blocks.push(`<div class="message-table-wrap"><table><thead><tr>${headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, cellIndex) => `<td>${renderInlineMarkdown(row[cellIndex] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    const listItem = line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/);
    if (listItem) {
      flushParagraph();
      openList(listItem[2] ? "ol" : "ul");
      blocks.push(`<li>${renderInlineMarkdown(listItem[3])}</li>`);
      continue;
    }
    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushFlow();
      blocks.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }
    closeList();
    paragraph.push(line);
  }
  if (codeLines !== null) blocks.push(`<pre><code>${escapeHTML(codeLines.join("\n"))}</code></pre>`);
  flushFlow();
  return blocks.join("");
}

async function api(path, options = {}) {
  const config = { ...options, headers: { ...(options.headers || {}) } };
  if (config.body && typeof config.body !== "string") {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.className = "toast"; }, 3200);
}

function storeChat() {
  localStorage.setItem("shepard-chat", JSON.stringify(state.chat.slice(-30)));
}

function loadStoredChat() {
  try {
    const stored = JSON.parse(localStorage.getItem("shepard-chat") || "[]");
    if (Array.isArray(stored)) state.chat = stored.filter((message) =>
      ["user", "assistant"].includes(message.role) && typeof message.content === "string"
    ).map((message) => ({
      role: message.role,
      content: message.content,
      sources: Array.isArray(message.sources) ? message.sources.filter((source) =>
        source && typeof source.title === "string" && /^https?:\/\//.test(source.url || "")
      ).slice(0, 2) : []
    })).slice(-30);
  } catch { state.chat = []; }
}

function setMode(mode) {
  const selected = mode === "chat" ? "chat" : "labyrinth";
  state.mode = selected;
  document.body.dataset.appMode = selected;
  document.querySelectorAll("[data-mode]").forEach((button) => {
    const active = button.dataset.mode === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#mode-labyrinth").hidden = false;
  $("#mode-chat").hidden = selected !== "chat";
  $("#workspace-title").textContent = selected === "chat" ? "Direct Channel" : "The Labyrinth";
  if (selected === "chat" && state.gestures.tracker) stopGestureControls();
  if (selected === "chat") requestAnimationFrame(() => {
    $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
    $("#chat-input").focus();
  });
  syncWorldBackdrop();
}

function syncWorldBackdrop() {
  const active = document.body.classList.contains("world-menu-open")
    || Boolean(document.body.dataset.workspacePanel)
    || state.mode === "chat";
  $("#world-overlay-backdrop").hidden = !active;
  $("#world-menu-button").setAttribute("aria-expanded", String(document.body.classList.contains("world-menu-open")));
}

function openWorldMenu() {
  document.body.classList.add("world-menu-open");
  syncWorldBackdrop();
  window.setTimeout(() => $(".rail .nav-link")?.focus(), 180);
}

function closeWorldMenu() {
  document.body.classList.remove("world-menu-open");
  syncWorldBackdrop();
}

function openWorkspacePanel(panel) {
  setMode("labyrinth");
  document.body.dataset.workspacePanel = panel;
  closeWorldMenu();
  syncWorldBackdrop();
  requestAnimationFrame(() => document.querySelector(`[data-panel-close="${panel}"]`)?.focus());
}

function closeWorkspacePanel() {
  delete document.body.dataset.workspacePanel;
  syncWorldBackdrop();
  $("#world-menu-button")?.focus();
}

function returnToLabyrinth() {
  closeWorldMenu();
  closeWorkspacePanel();
  setMode("labyrinth");
  if (state.focusOpen) leaveShepardFocus();
}

function displayStatus(status) {
  return status.replaceAll("_", " ");
}

function timeAgo(value) {
  if (!value) return "";
  const delta = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function shortDate(value) {
  if (!value) return "No deadline listed";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function formatAlarmTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown time";
  return parsed.toLocaleString([], {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
  });
}

function repeatLabel(kind) {
  return ({ none: "Once", daily: "Daily", weekdays: "Weekdays", weekly: "Weekly" })[kind] || kind;
}

function renderAlarms() {
  const active = state.alarms.filter((alarm) => alarm.status === "active");
  const visible = state.alarms.filter((alarm) => alarm.status === "active").slice(0, 12);
  const count = $("#alarm-count");
  count.textContent = active.length;
  count.hidden = active.length === 0;
  $("#alarms-button").classList.toggle("has-alarms", active.length > 0);
  $("#alarm-next-copy").textContent = active.length
    ? `Next: ${formatAlarmTime(active[0].scheduled_for)}` : "Nothing scheduled";
  $("#alarm-list").innerHTML = visible.length ? visible.map((alarm) => `
    <article class="alarm-row" data-alarm-id="${escapeHTML(alarm.id)}">
      <span class="alarm-row-mark" aria-hidden="true"></span>
      <div><strong>${escapeHTML(alarm.label)}</strong><time>${escapeHTML(formatAlarmTime(alarm.scheduled_for))}</time></div>
      <span class="alarm-repeat">${escapeHTML(repeatLabel(alarm.repeat_kind))}</span>
      <button class="text-button" type="button" data-alarm-dismiss="${escapeHTML(alarm.id)}">Dismiss</button>
    </article>`).join("") : `
    <div class="alarm-empty"><span aria-hidden="true">☼</span><strong>Your morning is clear.</strong><p>Set an alarm above and Shepard will keep it close.</p></div>`;
}

function primeAlarmAudio() {
  if (!alarmAudioContext) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) alarmAudioContext = new AudioContext();
  }
  if (alarmAudioContext?.state === "suspended") alarmAudioContext.resume().catch(() => {});
}

function playAlarmChime() {
  primeAlarmAudio();
  if (!alarmAudioContext) return;
  const start = alarmAudioContext.currentTime;
  [523.25, 659.25, 783.99, 1046.5].forEach((frequency, index) => {
    const oscillator = alarmAudioContext.createOscillator();
    const gain = alarmAudioContext.createGain();
    oscillator.type = index % 2 ? "sine" : "triangle";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start + index * .16);
    gain.gain.linearRampToValueAtTime(.12, start + index * .16 + .025);
    gain.gain.exponentialRampToValueAtTime(.001, start + index * .16 + .48);
    oscillator.connect(gain).connect(alarmAudioContext.destination);
    oscillator.start(start + index * .16);
    oscillator.stop(start + index * .16 + .5);
  });
}

async function ringAlarm(alarm) {
  if (state.ringingAlarm || alarm.status !== "active") return;
  state.ringingAlarm = alarm;
  try {
    const updated = await api(`/api/alarms/${encodeURIComponent(alarm.id)}/fire`, {
      method: "POST", body: {}
    });
    state.alarms = state.alarms.map((item) => item.id === updated.id ? updated : item);
    renderAlarms();
  } catch (error) {
    state.ringingAlarm = null;
    toast(error.message, true);
    return;
  }
  $("#ring-alarm-label").textContent = alarm.label;
  $("#ring-alarm-time").textContent = `Due ${formatAlarmTime(alarm.scheduled_for)}`;
  if (!$("#alarm-ring-dialog").open) $("#alarm-ring-dialog").showModal();
  playAlarmChime();
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification("Shepard's bell", { body: alarm.label, tag: alarm.id });
  }
}

function checkAlarms() {
  if (state.ringingAlarm || document.visibilityState === "hidden") return;
  const now = Date.now();
  const due = state.alarms.find((alarm) =>
    alarm.status === "active" && new Date(alarm.scheduled_for).getTime() <= now
  );
  if (due) ringAlarm(due);
}

function renderMetrics() {
  const active = state.jobs.filter((job) => ["planning", "running"].includes(job.status)).length;
  const complete = state.jobs.filter((job) => job.status === "completed").length;
  const pending = state.approvals.filter((approval) => approval.status === "pending").length;
  $("#metric-active").textContent = active;
  $("#metric-complete").textContent = complete;
  $("#metric-agents").textContent = Math.max(0, state.agents.length - 1);
  $("#metric-approvals").textContent = pending;
}

function setCareerView(view, { focus = false } = {}) {
  const allowed = new Set(["opportunities", "scout", "resume", "import"]);
  const next = allowed.has(view) ? view : "opportunities";
  state.careerView = next;
  document.querySelectorAll("[data-career-view]").forEach((button) => {
    const active = button.dataset.careerView === next;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll("[data-career-panel]").forEach((panel) => {
    const active = panel.dataset.careerPanel === next;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  if (next !== "opportunities") $("#internships")?.classList.remove("career-detail-open");
  if (focus) document.querySelector(`[data-career-panel="${next}"] h3`)?.focus?.();
}

function filteredInternships() {
  const query = state.internshipFilters.query.trim().toLowerCase();
  const stage = state.internshipFilters.stage;
  const rows = state.internships.filter((item) => {
    if (stage !== "all" && item.stage !== stage) return false;
    if (!query) return true;
    const haystack = [
      item.title, item.source_title, item.company, item.location, item.match_summary, item.notes
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const timestamp = (value) => {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const deadline = (value) => {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER;
  };
  rows.sort((left, right) => {
    if (state.internshipFilters.sort === "updated") return timestamp(right.updated_at) - timestamp(left.updated_at);
    if (state.internshipFilters.sort === "deadline") return deadline(left.deadline) - deadline(right.deadline);
    if (state.internshipFilters.sort === "company") return String(left.company || "").localeCompare(String(right.company || ""));
    const scoreDelta = Number(right.match_score ?? -1) - Number(left.match_score ?? -1);
    return scoreDelta || timestamp(right.updated_at) - timestamp(left.updated_at);
  });
  return rows;
}

function renderResumeDesk() {
  const review = state.resume?.review || null;
  const status = review?.status || (state.resumeReady ? "ready" : "missing");
  const badge = $("#resume-review-status");
  badge.textContent = displayStatus(status);
  badge.className = `status-badge ${status}`;
  $("#resume-filename").textContent = review?.filename || (state.resumeReady ? "Existing local résumé" : "No uploaded résumé");
  $("#resume-review-button").disabled = !state.resumeReady || ["queued", "running"].includes(status);
  const terms = Array.isArray(review?.search_terms) ? review.search_terms : [];
  const roles = Array.isArray(review?.target_roles) ? review.target_roles : [];
  const profile = $("#resume-search-profile");
  const chips = [...roles.map((item) => `Role: ${item}`), ...terms.map((item) => item)];
  profile.hidden = !chips.length;
  profile.innerHTML = chips.map((item) => `<span>${escapeHTML(item)}</span>`).join("");
  const critiquePanel = $("#resume-critique-panel");
  critiquePanel.hidden = !review?.critique;
  $("#resume-critique").innerHTML = review?.critique ? renderMarkdown(review.critique) : "";
  if (!$("#scout-query").value && roles.length) $("#scout-query").value = roles[0];
  if (!$("#scout-location").value && review?.location_preferences?.length) {
    $("#scout-location").value = review.location_preferences[0];
  }
}

function renderActiveScout() {
  const search = state.searches[0] || null;
  const badge = $("#active-scout-status");
  badge.textContent = search ? search.status : "not running";
  badge.className = `status-badge ${search?.status || "saved"}`;
  $("#active-scout-actions").hidden = !search;
  if (!search) {
    $("#active-scout-meta").innerHTML = "<span>Finish the résumé critique, then choose a focused query.</span>";
    return;
  }
  if (!$("#active-scout-form").contains(document.activeElement)) {
    $("#scout-query").value = search.query || "";
    $("#scout-location").value = search.location || "";
    $("#scout-interval").value = String(search.interval_hours || 24);
    $("#scout-min-score").value = String(search.min_score ?? 55);
  }
  const lastRun = search.last_run_at ? new Date(search.last_run_at).toLocaleString() : "not yet";
  const nextRun = search.next_run_at ? new Date(search.next_run_at).toLocaleString() : "not scheduled";
  $("#active-scout-meta").innerHTML = search.last_error
    ? `<span class="error-copy">Last run failed: ${escapeHTML(search.last_error)}</span>`
    : `<span>Last: ${escapeHTML(lastRun)} · saved ${escapeHTML(search.last_result_count || 0)} · next: ${escapeHTML(nextRun)}</span>`;
  $("#active-scout-toggle").textContent = search.status === "active" ? "Pause" : "Resume";
  $("#active-scout-start").textContent = "Create another search";
}

function renderInternshipSummary() {
  const activeStages = new Set(["reviewed", "approved_to_apply", "applied", "interview", "offer"]);
  $("#internship-stat-total").textContent = state.internships.filter((item) => item.stage !== "archived").length;
  $("#internship-stat-ready").textContent = state.internships.filter((item) => activeStages.has(item.stage)).length;
  $("#internship-stat-applied").textContent = state.internships.filter((item) => ["applied", "interview", "offer"].includes(item.stage)).length;
  $("#resume-state").textContent = state.resumeReady ? "✓ Résumé ready" : "Résumé missing";
  $("#resume-state").classList.toggle("missing", !state.resumeReady);
  const shared = state.sharedJobPage;
  const card = $("#shared-job-card");
  card.classList.toggle("ready", Boolean(shared));
  $("#shared-job-title").textContent = shared ? shared.title : "Share a job page first";
  const link = $("#shared-job-url");
  if (shared) {
    link.hidden = false;
    link.href = shared.url;
    link.textContent = shared.url;
    $("#shared-job-state").textContent = `Shared ${timeAgo(new Date(Number(shared.shared_at) * 1000).toISOString())}. Shepard will analyze only this page.`;
  } else {
    link.hidden = true;
    link.removeAttribute("href");
    link.textContent = "";
    $("#shared-job-state").innerHTML = "Open one internship in Chrome, click the Shepard Bridge, and choose <b>Share current page</b>.";
  }
  $("#import-internship-button").disabled = !shared || !state.resumeReady;
}

function renderInternships() {
  const list = $("#internships-list");
  renderInternshipSummary();
  const visible = filteredInternships();
  $("#internship-count").textContent = `${visible.length} of ${state.internships.length} shown`;
  if (!visible.length) {
    const hasFilters = Boolean(state.internshipFilters.query) || state.internshipFilters.stage !== "all";
    list.innerHTML = hasFilters
      ? '<div class="internship-empty"><strong>No matches in this view</strong><p>Try a broader search or choose a different stage.</p></div>'
      : '<div class="internship-empty"><strong>The field is open</strong><p>Start Active Scout or bring Shepard a live job posting to plant the first opportunity.</p></div>';
    return;
  }
  list.innerHTML = visible.map((item) => {
    const score = item.match_score === null || item.match_score === undefined ? "—" : item.match_score;
    const company = item.company || "Company not identified";
    const title = item.title || item.source_title || "Untitled opportunity";
    return `
      <button class="internship-card${item.id === state.selectedInternshipId ? " selected" : ""}" data-internship-id="${escapeHTML(item.id)}">
        <span class="match-score ${item.match_score === null || item.match_score === undefined ? "pending" : ""}"><strong>${escapeHTML(score)}</strong><small>match</small></span>
        <span class="internship-card-copy">
          <span class="internship-card-head"><span class="status-badge ${escapeHTML(item.stage)}">${escapeHTML(displayStatus(item.stage))}</span><time>${escapeHTML(timeAgo(item.updated_at))}</time></span>
          <strong>${escapeHTML(title)}</strong><small>${escapeHTML(company)}${item.location ? ` · ${escapeHTML(item.location)}` : ""}</small>
          <span class="deadline-label">${escapeHTML(shortDate(item.deadline))}</span>
        </span>
      </button>`;
  }).join("");
}

async function refreshFilteredInternships() {
  const visible = filteredInternships();
  const selectedIsVisible = visible.some((item) => item.id === state.selectedInternshipId);
  if (!selectedIsVisible) {
    state.selectedInternshipId = visible[0]?.id || null;
    state.selectedInternship = null;
  }
  renderInternships();
  if (!selectedIsVisible) await loadInternship(state.selectedInternshipId);
}

function approvalStatusFor(item) {
  if (!item?.approval_id) return null;
  return state.approvals.find((approval) => approval.id === item.approval_id)?.status || null;
}

function renderInternshipDetail() {
  const panel = $("#internship-detail");
  const item = state.selectedInternship;
  if (!item) {
    panel.className = "internship-detail empty-state";
    panel.innerHTML = '<div class="empty-glyph" aria-hidden="true">◎</div><h3>No internship selected</h3><p>Share a job page to start the five-Sheep review pipeline.</p>';
    return;
  }
  const title = item.title || item.source_title || "Untitled opportunity";
  const approvalStatus = approvalStatusFor(item);
  const job = item.job;
  const tasks = Array.isArray(job?.tasks) ? job.tasks.map((task) => `
    <div class="internship-task"><span class="task-sheep">${escapeHTML(task.sheep_id)}</span><div><strong>${escapeHTML(task.title)}</strong><small>${escapeHTML(displayStatus(task.status))}</small></div></div>`).join("") : "";
  const analysis = item.analysis_status === "completed" || item.analysis_status === "pre_scored"
    ? `<div class="internship-report message-body result-markdown">${renderMarkdown(item.match_summary || "Review completed without a written synthesis.")}</div>`
    : `<div class="analysis-progress"><span class="thinking-dots"><i></i><i></i><i></i></span><strong>${item.analysis_status === "failed" ? "Review needs attention" : "The Sheep are reviewing this job"}</strong><p>${escapeHTML(item.next_action || "Wayfinder, Scout, Scribe, Reviewer, and Steward are moving through the route.")}</p></div>`;
  const approvalButton = item.analysis_status === "pre_scored"
    ? '<button class="primary-button" type="button" data-internship-action="review">Run full five-Sheep review</button>'
    : item.analysis_status === "completed" && !["approved", "pending"].includes(approvalStatus)
    ? '<button class="primary-button" type="button" data-internship-action="approval">Request application approval</button>'
    : approvalStatus === "pending"
      ? '<a class="ghost-button internship-anchor" href="#approvals">Review pending approval</a>'
      : approvalStatus === "approved"
        ? '<span class="authorization-note">✓ Preparation authorized. Final submission still requires you.</span>'
        : "";
  const stageButtons = ["saved", "reviewed", "applied", "interview", "offer", "archived"].map((stage) => `
    <button type="button" class="stage-button${item.stage === stage ? " active" : ""}" data-internship-stage="${stage}">${escapeHTML(displayStatus(stage))}</button>`).join("");
  panel.className = "internship-detail";
  panel.innerHTML = `
    <div class="internship-detail-header">
      <div><span class="status-badge ${escapeHTML(item.stage)}">${escapeHTML(displayStatus(item.stage))}</span><h3>${escapeHTML(title)}</h3><p>${escapeHTML(item.company || "Company not identified")}${item.location ? ` · ${escapeHTML(item.location)}` : ""}</p></div>
      <div class="detail-score"><strong>${item.match_score ?? "—"}</strong><span>/ 100</span></div>
    </div>
    <div class="internship-facts">
      <span><small>Deadline</small><strong>${escapeHTML(shortDate(item.deadline))}</strong></span>
      <span><small>Source</small><a href="${escapeHTML(item.source_url)}" target="_blank" rel="noopener noreferrer">Open job page ↗</a></span>
      <span><small>Analysis</small><strong>${escapeHTML(displayStatus(item.analysis_status))}</strong></span>
    </div>
    ${item.notes ? `<div class="owner-notes"><span>YOUR NOTES</span><p>${escapeHTML(item.notes)}</p></div>` : ""}
    ${tasks ? `<div class="internship-route"><span class="section-number">THE FLOCK'S ROUTE</span>${tasks}</div>` : ""}
    <div class="next-action"><span>NEXT ACTION</span><p>${escapeHTML(item.next_action || "Review the opportunity and choose the next stage.")}</p></div>
    <div class="internship-actions">${approvalButton}</div>
    <div class="stage-control"><span>TRACKING STAGE</span><div>${stageButtons}</div></div>
    <div class="internship-analysis"><span class="section-number">SHEPARD'S NOTES</span>${analysis}</div>`;
}

async function loadInternship(internshipId) {
  if (!internshipId) {
    state.selectedInternship = null;
    renderInternshipDetail();
    return;
  }
  try {
    state.selectedInternship = await api(`/api/internships/${encodeURIComponent(internshipId)}`);
    renderInternshipDetail();
  } catch (error) {
    toast(error.message, true);
  }
}

function renderJobs() {
  const list = $("#jobs-list");
  $("#job-count").textContent = `${state.jobs.length} job${state.jobs.length === 1 ? "" : "s"}`;
  if (!state.jobs.length) {
    list.innerHTML = '<div class="job-detail empty-state"><div class="empty-glyph">⌁</div><h3>The Labyrinth is quiet</h3><p>Dispatch a goal to create the first job.</p></div>';
    return;
  }
  list.innerHTML = state.jobs.map((job) => `
    <button class="job-card${job.id === state.selectedJobId ? " selected" : ""}" data-job-id="${escapeHTML(job.id)}">
      <div class="job-card-head"><span class="status-badge ${escapeHTML(job.status)}">${escapeHTML(displayStatus(job.status))}</span><time>${escapeHTML(timeAgo(job.created_at))}</time></div>
      <p>${escapeHTML(job.goal)}</p>
      <time>${escapeHTML(job.id)}</time>
    </button>`).join("");
}

function renderJobDetail() {
  const panel = $("#job-detail");
  const job = state.selectedJob;
  if (!job) return;
  const tasks = job.tasks.map((task) => `
    <div class="trace-item">
      <div class="trace-meta"><span>${escapeHTML(task.sheep_id)}</span><span class="status-badge ${escapeHTML(task.status)}">${escapeHTML(displayStatus(task.status))}</span></div>
      <strong>${escapeHTML(task.title)}</strong>
      <p>${escapeHTML(task.instructions)}</p>
    </div>`).join("");
  const final = job.final_output
    ? `<div class="final-output"><span class="section-number">BACK FROM THE FLOCK</span><div class="message-body result-markdown">${renderMarkdown(job.final_output)}</div></div>`
    : `<div class="final-output"><span class="section-number">BACK FROM THE FLOCK</span><p class="muted-label">${["planning", "running"].includes(job.status) ? "Work is still moving through the Labyrinth." : "No final result was produced."}</p></div>`;
  panel.className = "job-detail";
  panel.innerHTML = `
    <div class="job-card-head"><span class="status-badge ${escapeHTML(job.status)}">${escapeHTML(displayStatus(job.status))}</span><time>${escapeHTML(timeAgo(job.created_at))}</time></div>
    <p class="detail-goal">${escapeHTML(job.goal)}</p>
    ${job.plan_summary ? `<p class="muted-label">${escapeHTML(job.plan_summary)}</p>` : ""}
    <div class="task-trace">${tasks || '<p class="muted-label">Shepard is creating the plan…</p>'}</div>
    ${final}`;
  syncLabyrinth();
}

function syncLabyrinth() {
  const tasks = state.selectedJob?.tasks || [];
  const activeTasks = tasks.filter((task) => ["queued", "running", "waiting_approval"].includes(task.status));
  const councilActive = state.selectedJob?.goal?.startsWith("Weekly Sunday Council")
    && ["planning", "running"].includes(state.selectedJob.status);
  const activeIds = councilActive
    ? new Set(state.agents.filter((agent) => agent.kind === "sheep").map((agent) => agent.id))
    : new Set(activeTasks.map((task) => task.sheep_id));
  document.querySelectorAll("[data-domain-id]").forEach((domain) => {
    domain.classList.toggle("working", activeIds.has(domain.dataset.domainId));
  });
  document.querySelectorAll("[data-route-id]").forEach((route) => {
    route.classList.toggle("working", activeIds.has(route.dataset.routeId));
  });
  labyrinthScene?.setActive(activeIds);
  $(".labyrinth-visual")?.classList.toggle("labyrinth-coordinating", activeIds.size > 0);
  const assistants = $("#focus-assistants");
  if (assistants) {
    const names = councilActive
      ? state.agents.filter((agent) => agent.kind === "sheep").map((agent) => agent.name)
      : activeTasks.map((task) => state.agents.find((agent) => agent.id === task.sheep_id)?.name || task.sheep_id);
    assistants.textContent = names.length
      ? councilActive
        ? "The full flock is gathered for the Sunday council"
        : `${[...new Set(names)].join(", ")} ${names.length === 1 ? "is" : "are"} approaching the roots`
      : "The flock is listening";
  }
  const status = $("#console-status-copy");
  if (!status) return;
  if (councilActive) {
    status.textContent = "The full flock is gathering with Shepard";
  } else if (state.selectedJob?.status === "planning") {
    status.textContent = "Shepard is mapping the route";
  } else if (activeTasks.length) {
    const names = [...new Set(activeTasks.map((task) => task.sheep_id))];
    status.textContent = `${names.join(", ")} ${names.length === 1 ? "is" : "are"} moving through the Labyrinth`;
  } else if (state.selectedJob?.status === "waiting_approval") {
    status.textContent = "The Gatekeeper is waiting for you";
  } else {
    status.textContent = "All domains are ready";
  }
}

function renderAgents() {
  $("#agents-grid").innerHTML = state.agents.map((agent) => `
    <button class="agent-card" data-agent-id="${escapeHTML(agent.id)}">
      <div class="agent-card-head"><span class="agent-initial">${escapeHTML(agent.name.slice(0, 1).toUpperCase())}</span><span class="agent-kind">${escapeHTML(agent.kind)}</span></div>
      <h3>${escapeHTML(agent.name)}</h3>
      <p>${escapeHTML(agent.role)}</p>
      <span class="agent-model">${escapeHTML(agent.model)}</span>
    </button>`).join("");
}

function renderLabyrinth() {
  const sheep = state.agents.filter((agent) => agent.kind === "sheep");
  const routes = [];
  const domains = [];
  const defaultDomains = {
    scout: "Northreach", scribe: "Scriptorium", builder: "Forge",
    reviewer: "Watchtower", steward: "Chronicle", browser: "Waystation"
  };
  const defaultBuildings = {
    scout: "farm", scribe: "scriptorium", builder: "forge",
    reviewer: "tower", steward: "keep", browser: "tower"
  };
  const buildingCycle = ["farm", "scriptorium", "forge", "tower", "keep"];
  const outerCount = sheep.length <= 8 ? sheep.length : Math.min(9, Math.ceil(sheep.length / 2));
  sheep.forEach((agent, index) => {
    const inner = sheep.length > 8 && index >= outerCount;
    const ringIndex = inner ? index - outerCount : index;
    const ringCount = inner ? sheep.length - outerCount : outerCount;
    const radius = inner ? 30 : 40;
    const worldRadius = inner ? .56 : .79;
    const startAngle = ringCount === 5 && !inner ? -126 : -90;
    const angle = startAngle + (360 / Math.max(1, ringCount)) * ringIndex;
    const radians = angle * Math.PI / 180;
    const x = 50 + radius * Math.cos(radians);
    const y = 50 + radius * Math.sin(radians);
    const realm = defaultDomains[agent.id] || agent.role.split(/[,.]/)[0].slice(0, 18) || "New Domain";
    const building = defaultBuildings[agent.id] || buildingCycle[index % buildingCycle.length];
    routes.push(`<div class="route" data-route-id="${escapeHTML(agent.id)}" style="--angle:${angle}deg;--route-length:${radius}%;"><span class="route-signal"></span><span class="route-sheep route-sprite-${index % 5}"></span></div>`);
    domains.push(`
      <button class="domain" data-domain-id="${escapeHTML(agent.id)}" data-domain-angle="${angle.toFixed(3)}" data-world-radius="${worldRadius}" style="--x:${x.toFixed(2)}%;--y:${y.toFixed(2)}%;--delay:-${(index * .61).toFixed(2)}s" aria-label="Open ${escapeHTML(agent.name)}'s domain">
        <span class="domain-zone"></span><span class="domain-building building-${building}" aria-hidden="true"></span><span class="pixel-sheep sprite-${index % 5}" aria-hidden="true"></span>
        <strong>${escapeHTML(agent.name)}</strong><small>${escapeHTML(realm)}</small>
      </button>`);
  });
  $("#route-layer").innerHTML = routes.join("");
  $("#domain-layer").innerHTML = domains.join("");
  $("#labyrinth-world").classList.toggle("labyrinth-expanded", sheep.length > 8);
  $("#scene-domain-count").textContent = `${sheep.length} domain${sheep.length === 1 ? "" : "s"} locked`;
  labyrinthScene?.syncDomains();
  updateWorldDepth();
  syncLabyrinth();
}

function renderApprovals() {
  const list = $("#approvals-list");
  const pending = state.approvals.filter((approval) => approval.status === "pending");
  if (!pending.length) {
    list.innerHTML = '<div class="job-detail empty-state"><div class="empty-glyph">✓</div><h3>No decisions waiting</h3><p>Sensitive actions will appear here before anything happens.</p></div>';
    return;
  }
  list.innerHTML = pending.map((approval) => `
    <article class="approval-row">
      <div><span class="status-badge ${escapeHTML(approval.status)}">${escapeHTML(approval.status)}</span><h3>${escapeHTML(approval.capability)}</h3><p>${escapeHTML(approval.description)}</p></div>
      ${approval.status === "pending" ? `<div class="approval-actions"><button class="ghost-button deny-button" data-approval="${escapeHTML(approval.id)}" data-decision="denied">Deny</button><button class="primary-button" data-approval="${escapeHTML(approval.id)}" data-decision="approved">Approve</button></div>` : ""}
    </article>`).join("");
}

function renderChat() {
  const messages = state.chat.length ? state.chat : [{
    role: "assistant", content: "I’m here. Tell me what you’re building, deciding, or trying to get done."
  }];
  const markup = messages.map((message) => `
    <article class="chat-message ${escapeHTML(message.role)}">
      <span class="message-avatar">${message.role === "user" ? "YOU" : "S"}</span>
      <div><small>${message.role === "user" ? "You" : "Shepard"}</small><div class="message-body">${renderMarkdown(message.content)}</div>${Array.isArray(message.sources) && message.sources.length ? `
        <div class="message-sources">${message.sources.map((source) => `<a href="${escapeHTML(source.url)}" target="_blank" rel="noopener noreferrer">Open ${escapeHTML(source.title || "source")} ↗</a>`).join("")}</div>` : ""}</div>
    </article>`).join("") + (state.chatBusy ? `
    <article class="chat-message assistant thinking" id="chat-thinking">
      <span class="message-avatar">S</span><div><small>Shepard</small><div class="message-body"><p><span class="thinking-dots"><i></i><i></i><i></i></span></p></div></div>
    </article>` : "");
  [$("#chat-messages"), $("#focus-chat-messages")].forEach((container) => {
    if (!container) return;
    container.innerHTML = markup;
    requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });
  });
  $(".labyrinth-visual")?.classList.toggle("labyrinth-thinking", state.chatBusy);
}

function connectorActionLabel(connector) {
  if (connector.status === "connected") return "Connected";
  if (connector.status === "license_required") return "Requirements";
  if (connector.id === "chrome") return connector.status === "ready_to_connect" ? "Pair" : "Install";
  if (["linkedin-jobs", "handshake", "job-sites", "outlook-web"].includes(connector.id)) {
    if (connector.status === "manual_only") return "How to use";
    return connector.status === "browser_ready" ? "Use Chrome" : "Set up Chrome";
  }
  if (connector.status === "ready_to_connect") return "Connect";
  if (connector.status === "setup_required") return "Set up";
  return "Coming next";
}

function renderConnectors() {
  const connected = state.connectors.filter((connector) => connector.status === "connected").length;
  $("#connected-count").textContent = connected;
  $(".connection-pulse").classList.toggle("connected", connected > 0);
  $("#connectors-grid").innerHTML = state.connectors.map((connector) => `
    <article class="connector-card" style="--connector-color:${escapeHTML(connector.color)}">
      <span class="connector-icon" aria-hidden="true">${escapeHTML(connector.monogram)}</span>
      <div>
        <strong>${escapeHTML(connector.name)}</strong>
        <small>${escapeHTML(connector.description)}</small>
        <span class="connector-state ${escapeHTML(connector.status)}">${escapeHTML(displayStatus(connector.status))}</span>
      </div>
      <button class="ghost-button" type="button" data-connector-id="${escapeHTML(connector.id)}" data-connector-status="${escapeHTML(connector.status)}" ${connector.status === "planned" || connector.status === "connected" ? "disabled" : ""}>${connectorActionLabel(connector)}</button>
    </article>`).join("");
}

async function loadConnectors() {
  try {
    const result = await api("/api/connectors");
    state.connectors = result.connectors;
    $("#google-redirect-uri").textContent = result.google_redirect_uri;
    renderConnectors();
  } catch (error) {
    $("#connectors-grid").innerHTML = `<div class="job-detail empty-state"><h3>Connections unavailable</h3><p>${escapeHTML(error.message)}</p></div>`;
  }
}

function applyOrbit() {
  const world = $("#labyrinth-world");
  world.style.setProperty("--orbit", `${state.orbit.angle}deg`);
  world.style.setProperty("--orbit-neg", `${-state.orbit.angle}deg`);
  world.style.setProperty("--tilt", `${state.orbit.tilt}deg`);
  world.style.setProperty("--tilt-neg", `${-state.orbit.tilt}deg`);
  world.style.setProperty("--zoom", state.orbit.zoom);
  world.style.setProperty("--pan-x", state.orbit.panX || "0px");
  world.style.setProperty("--pan-y", state.orbit.panY || "0px");
  labyrinthScene?.touch();
  updateWorldDepth();
}

function updateWorldDepth() {
  const world = $("#labyrinth-world");
  if (!world) return;
  const expanded = world.classList.contains("labyrinth-expanded");
  const baseScale = expanded ? .82 : 1;
  document.querySelectorAll(".domain[data-domain-angle]").forEach((domain) => {
    const baseAngle = Number(domain.dataset.domainAngle || 0);
    const radians = (baseAngle + state.orbit.angle) * Math.PI / 180;
    const depth = (Math.sin(radians) + 1) / 2;
    domain.style.zIndex = String(Math.round(7 + depth * 26));
    domain.style.setProperty("--domain-scale", (baseScale * (.9 + depth * .13)).toFixed(3));
    domain.style.setProperty("--depth-light", (.76 + depth * .3).toFixed(3));
    domain.style.setProperty("--depth-saturation", (.78 + depth * .3).toFixed(3));
    domain.style.setProperty("--depth-opacity", (.7 + depth * .3).toFixed(3));
    domain.style.setProperty("--depth-shadow", `${Math.round(3 + depth * 8)}px`);
    domain.style.setProperty("--depth-blur", `${Math.round(3 + depth * 6)}px`);

    const route = document.querySelector(`.route[data-route-id="${CSS.escape(domain.dataset.domainId)}"]`);
    if (route) {
      route.style.zIndex = String(Math.round(3 + depth * 8));
      const traveler = route.querySelector(".route-sheep");
      if (traveler) {
        traveler.style.transform = `rotateZ(${-(baseAngle + state.orbit.angle)}deg) rotateX(${-state.orbit.tilt}deg)`;
      }
    }
  });

  const orbitRadians = state.orbit.angle * Math.PI / 180;
  const root = $(".root-domain");
  if (root) {
    root.style.zIndex = "18";
    root.style.setProperty("--root-world-scale", "1");
    root.style.setProperty("--root-light", (.92 + Math.cos(orbitRadians) * .08).toFixed(3));
  }
}

function updateGestureStatus({ hands = 0, mode = "idle", activation = "idle", error = "" } = {}) {
  state.gestures.hands = hands;
  state.gestures.mode = mode;
  $("#labyrinth-stage")?.classList.toggle("gesture-controlling", mode === "orbit" || mode === "zoom");
  const status = $("#gesture-status");
  const cameraState = $("#gesture-camera-state");
  if (error) {
    status.textContent = error;
    cameraState.textContent = "Camera off";
    return;
  }
  cameraState.textContent = state.gestures.tracker ? "Camera active · processed here" : "Camera off";
  if (!hands) status.textContent = "Show one hand";
  else if (mode === "orbit" && activation === "palm") status.textContent = "Open hand · orbiting";
  else if (mode === "zoom" && activation === "palm") status.textContent = "Two open hands · zooming";
  else if (mode === "orbit") status.textContent = "Pinch · orbiting";
  else if (mode === "zoom") status.textContent = "Two hands · zooming";
  else status.textContent = `${hands} hand${hands === 1 ? "" : "s"} detected · open your palm`;
}

function stopGestureControls({ keepPanel = false } = {}) {
  state.gestures.tracker?.stop();
  state.gestures.tracker = null;
  state.gestures.starting = false;
  const button = $("#gesture-toggle");
  button.disabled = false;
  button.classList.remove("active");
  button.setAttribute("aria-pressed", "false");
  $("#gesture-toggle-copy").textContent = "Hand controls";
  $("#labyrinth-stage")?.classList.remove("gesture-controlling");
  if (!keepPanel) $("#gesture-panel").hidden = true;
  updateGestureStatus();
}

async function startGestureControls() {
  if (state.gestures.tracker || state.gestures.starting) return;
  const button = $("#gesture-toggle");
  state.gestures.starting = true;
  button.disabled = true;
  $("#gesture-panel").hidden = false;
  $("#gesture-toggle-copy").textContent = "Starting…";
  $("#gesture-camera-state").textContent = "Requesting camera…";
  try {
    const { ShepardHandTracker } = await loadHandControlsModule();
    const tracker = new ShepardHandTracker($("#gesture-video"), $("#gesture-overlay"), {
      onRotate(dx, dy) {
        if (state.focusOpen) return;
        state.orbit.angle += dx * 420;
        state.orbit.tilt = Math.max(30, Math.min(74, state.orbit.tilt - dy * 205));
        applyOrbit();
      },
      onZoom(factor) {
        if (state.focusOpen) return;
        state.orbit.zoom = Math.max(.72, Math.min(1.42, state.orbit.zoom / factor));
        applyOrbit();
      },
      onStatus: updateGestureStatus
    });
    state.gestures.tracker = tracker;
    await tracker.start();
    button.classList.add("active");
    button.setAttribute("aria-pressed", "true");
    $("#gesture-toggle-copy").textContent = "Gestures on";
    updateGestureStatus();
    toast("Smooth hand controls are on—one hand orbits, two hands zoom");
  } catch (error) {
    const denied = error?.name === "NotAllowedError";
    stopGestureControls({ keepPanel: true });
    updateGestureStatus({ error: denied ? "Camera permission denied" : "Hand tracking could not start" });
    toast(denied ? "Allow camera access to use hand controls" : error.message, true);
  } finally {
    state.gestures.starting = false;
    button.disabled = false;
  }
}

function toggleGestureControls() {
  if (state.gestures.tracker) stopGestureControls();
  else startGestureControls();
}

function enterShepardFocus() {
  if (state.focusOpen) return;
  state.focusOpen = true;
  state.orbitPrevious = { ...state.orbit, dragging: false };
  const compact = window.matchMedia("(max-width: 760px)").matches;
  state.orbit = {
    ...state.orbit, angle: 0, tilt: compact ? 34 : 27, zoom: compact ? 1.28 : 1.72,
    panX: compact ? "0px" : "-22%", panY: compact ? "22px" : "0px", dragging: false
  };
  $(".labyrinth-visual").classList.add("shepard-focused");
  $("#shepard-focus-panel").hidden = false;
  applyOrbit();
  renderChat();
  window.setTimeout(() => $("#focus-chat-input").focus(), 420);
}

function leaveShepardFocus() {
  if (!state.focusOpen) return;
  state.focusOpen = false;
  if (state.orbitPrevious) state.orbit = { ...state.orbitPrevious, dragging: false };
  state.orbitPrevious = null;
  $(".labyrinth-visual").classList.remove("shepard-focused");
  $("#shepard-focus-panel").hidden = true;
  applyOrbit();
}

function weatherKind(code) {
  if (code >= 95) return { className: "weather-storm", icon: "ϟ", label: "Storm" };
  if ((code >= 71 && code <= 77) || (code >= 85 && code <= 86)) return { className: "weather-snow", icon: "✣", label: "Snow" };
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return { className: "weather-rain", icon: "≋", label: "Rain" };
  if ((code >= 1 && code <= 3) || code === 45 || code === 48) return { className: "weather-cloudy", icon: "☁", label: "Cloudy" };
  return { className: "weather-clear", icon: "☀", label: "Clear" };
}

function setTimeSky(isDay = null) {
  const visual = $(".labyrinth-visual");
  visual.classList.remove("sky-day", "sky-dawn", "sky-dusk", "sky-night");
  const hour = new Date().getHours();
  let sky = "sky-night";
  if (hour >= 5 && hour < 8) sky = "sky-dawn";
  else if (hour >= 17 && hour < 20) sky = "sky-dusk";
  else if (isDay === 1 || (isDay === null && hour >= 8 && hour < 17)) sky = "sky-day";
  visual.classList.add(sky);
}

function applyWeather(weather) {
  const current = weather.current || {};
  const kind = weatherKind(Number(current.weather_code || 0));
  const visual = $(".labyrinth-visual");
  visual.classList.remove("weather-clear", "weather-cloudy", "weather-rain", "weather-snow", "weather-storm");
  visual.classList.add(kind.className);
  setTimeSky(Number(current.is_day));
  $("#weather-icon").textContent = kind.icon;
  const temperature = Number.isFinite(Number(current.temperature_2m)) ? `${Math.round(Number(current.temperature_2m))}°F` : "";
  $("#weather-copy").textContent = `${kind.label}${temperature ? ` · ${temperature}` : ""}`;
  $("#weather-status").title = "Live local weather. Location is not stored.";
}

function requestWeather() {
  setTimeSky();
  if (!navigator.geolocation) {
    $("#weather-copy").textContent = "Time-based sky";
    return;
  }
  $("#weather-copy").textContent = "Locating…";
  navigator.geolocation.getCurrentPosition(async (position) => {
    try {
      const params = new URLSearchParams({
        lat: position.coords.latitude.toFixed(4), lon: position.coords.longitude.toFixed(4)
      });
      state.weather = await api(`/api/weather?${params}`);
      applyWeather(state.weather);
    } catch (error) {
      $("#weather-copy").textContent = "Time-based sky";
      toast(`Live weather unavailable: ${error.message}`, true);
    }
  }, () => {
    $("#weather-copy").textContent = "Time-based sky";
    $("#weather-status").title = "Location was not shared. Tap to try again.";
  }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 900000 });
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    const ready = health.ollama === "online";
    $("#rail-status-dot").className = `status-dot${ready ? "" : " offline"}`;
    $("#rail-status-label").textContent = ready ? "Shepard online" : "Ollama offline";
    $("#rail-status-copy").textContent = ready ? `${health.models.length} local models` : "Check local service";
  } catch {
    $("#rail-status-dot").className = "status-dot offline";
    $("#rail-status-label").textContent = "Control center offline";
  }
}

async function loadJob(jobId) {
  if (!jobId) return;
  try {
    state.selectedJob = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderJobDetail();
    if (state.selectedJob.status === "completed" && state.delegatedJobs[jobId] === "pending") {
      const result = (state.selectedJob.final_output || "The delegated work finished without a written result.").slice(0, 20000);
      state.chat.push({ role: "assistant", content: `The Sheep have returned to the roots with their result:\n\n${result}` });
      state.delegatedJobs[jobId] = "delivered";
      storeChat();
      renderChat();
      toast("The Sheep returned with a result");
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadAll(silent = false) {
  try {
    const [jobs, agents, approvals, internships, resume, searches, alarms] = await Promise.all([
      api("/api/jobs"), api("/api/agents"), api("/api/approvals?status=all"), api("/api/internships"),
      api("/api/resume"), api("/api/internship-searches"), api("/api/alarms")
    ]);
    state.jobs = jobs.jobs;
    state.agents = agents.agents;
    state.approvals = approvals.approvals;
    state.internships = internships.internships;
    state.resumeReady = internships.resume_ready;
    state.resume = resume;
    state.searches = searches.searches;
    state.alarms = alarms.alarms;
    state.sharedJobPage = internships.shared_page;
    const activeCouncil = state.jobs.find((job) => job.goal.startsWith("Weekly Sunday Council") && ["planning", "running"].includes(job.status));
    if (activeCouncil) state.selectedJobId = activeCouncil.id;
    if (!state.selectedJobId && state.jobs.length) state.selectedJobId = state.jobs[0].id;
    if (!state.internships.some((item) => item.id === state.selectedInternshipId)) {
      state.selectedInternshipId = state.internships[0]?.id || null;
    }
    renderMetrics(); renderJobs(); renderAgents(); renderLabyrinth(); renderApprovals(); renderInternships();
    renderResumeDesk(); renderActiveScout();
    renderAlarms(); checkAlarms();
    if (state.selectedJobId) await loadJob(state.selectedJobId);
    await loadInternship(state.selectedInternshipId);
    if (!silent) toast("Labyrinth refreshed");
  } catch (error) {
    toast(error.message, true);
  }
}

function openAgentDialog(agentId) {
  const agent = state.agents.find((item) => item.id === agentId);
  if (!agent) return;
  $("#agent-id").value = agent.id;
  $("#agent-name").value = agent.name;
  $("#agent-role").value = agent.role;
  $("#agent-model").value = agent.model;
  $("#agent-persona").value = agent.persona;
  $("#dialog-title").textContent = `Customize ${agent.name}`;
  $("#save-agent").textContent = "Save character";
  $("#agent-dialog").showModal();
}

function openCreateDialog() {
  $("#agent-id").value = "";
  $("#agent-name").value = "";
  $("#agent-role").value = "";
  $("#agent-model").value = "qwen3:8b";
  $("#agent-persona").value = "";
  $("#dialog-title").textContent = "Create a Sheep";
  $("#save-agent").textContent = "Create Sheep";
  $("#agent-dialog").showModal();
}

$("#goal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#dispatch-button");
  const goal = $("#goal-input").value.trim();
  if (!goal) return;
  button.disabled = true;
  button.querySelector("span").textContent = "Dispatching…";
  try {
    const result = await api("/api/jobs", { method: "POST", body: { goal } });
    state.selectedJobId = result.job_id;
    $("#goal-input").value = "";
    toast("Goal entered the Labyrinth");
    await loadAll(true);
    document.querySelector("#jobs").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Ask the flock";
  }
});

$("#goal-input").addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") $("#goal-form").requestSubmit();
});

$("#jobs-list").addEventListener("click", async (event) => {
  const card = event.target.closest("[data-job-id]");
  if (!card) return;
  state.selectedJobId = card.dataset.jobId;
  renderJobs();
  await loadJob(state.selectedJobId);
});

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("The résumé file could not be read"));
    reader.readAsDataURL(file);
  });
}

$("#resume-upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#resume-file").files[0];
  if (!file) return;
  const button = $("#resume-upload-button");
  button.disabled = true;
  button.textContent = "Uploading…";
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error("Résumé uploads are limited to 5 MB");
    const result = await api("/api/resume", {
      method: "POST",
      body: { filename: file.name, content_base64: await fileAsBase64(file) }
    });
    state.selectedJobId = result.job_id;
    toast("Résumé saved locally; Scout and Reviewer are critiquing it");
    await loadAll(true);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Upload & critique";
  }
});

$("#resume-review-button").addEventListener("click", async () => {
  const button = $("#resume-review-button");
  button.disabled = true;
  try {
    const result = await api("/api/resume/review", { method: "POST", body: {} });
    state.selectedJobId = result.job_id;
    toast("A fresh résumé critique is running");
    await loadAll(true);
  } catch (error) {
    toast(error.message, true);
  }
});

$("#active-scout-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#active-scout-start");
  button.disabled = true;
  try {
    await api("/api/internship-searches", {
      method: "POST",
      body: {
        query: $("#scout-query").value.trim(),
        location: $("#scout-location").value.trim(),
        interval_hours: Number($("#scout-interval").value),
        min_score: Number($("#scout-min-score").value)
      }
    });
    toast("Active Scout started; the first search is running now");
    await loadAll(true);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#active-scout-run").addEventListener("click", async () => {
  const search = state.searches[0];
  if (!search) return;
  const button = $("#active-scout-run");
  button.disabled = true;
  try {
    const result = await api(`/api/internship-searches/${encodeURIComponent(search.id)}/run`, {
      method: "POST", body: {}
    });
    toast(result.run_queued ? "Scout is searching now" : "That search is already running");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#active-scout-toggle").addEventListener("click", async () => {
  const search = state.searches[0];
  if (!search) return;
  const nextStatus = search.status === "active" ? "paused" : "active";
  try {
    await api(`/api/internship-searches/${encodeURIComponent(search.id)}`, {
      method: "PATCH", body: { status: nextStatus }
    });
    toast(`Active Scout ${nextStatus === "active" ? "resumed" : "paused"}`);
    await loadAll(true);
  } catch (error) {
    toast(error.message, true);
  }
});

$("#internship-intake-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#import-internship-button");
  button.disabled = true;
  button.textContent = "Starting the route…";
  try {
    const result = await api("/api/internships", {
      method: "POST",
      body: {
        title: $("#internship-title").value.trim(),
        company: $("#internship-company").value.trim(),
        deadline: $("#internship-deadline").value,
        notes: $("#internship-notes").value.trim()
      }
    });
    state.selectedInternshipId = result.internship_id;
    state.selectedJobId = result.job_id;
    $("#internship-intake-form").reset();
    toast("Five Sheep are reviewing the opportunity");
    await loadAll(true);
    setCareerView("opportunities");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = !state.sharedJobPage || !state.resumeReady;
    button.innerHTML = 'Analyze shared job <span aria-hidden="true">↗</span>';
  }
});

$("#internships-list").addEventListener("click", async (event) => {
  const card = event.target.closest("[data-internship-id]");
  if (!card) return;
  state.selectedInternshipId = card.dataset.internshipId;
  renderInternships();
  await loadInternship(state.selectedInternshipId);
  $("#internships")?.classList.add("career-detail-open");
});

document.querySelectorAll("[data-career-view]").forEach((button) => {
  button.addEventListener("click", () => setCareerView(button.dataset.careerView));
});

$("#internship-filter-query").addEventListener("input", (event) => {
  state.internshipFilters.query = event.target.value;
  refreshFilteredInternships();
});

$("#internship-filter-stage").addEventListener("change", (event) => {
  state.internshipFilters.stage = event.target.value;
  refreshFilteredInternships();
});

$("#internship-sort").addEventListener("change", (event) => {
  state.internshipFilters.sort = event.target.value;
  refreshFilteredInternships();
});

$("#career-mobile-back").addEventListener("click", () => {
  $("#internships")?.classList.remove("career-detail-open");
  $("#internship-filter-query")?.focus();
});

$("#internship-detail").addEventListener("click", async (event) => {
  const approvalButton = event.target.closest('[data-internship-action="approval"]');
  const reviewButton = event.target.closest('[data-internship-action="review"]');
  const stageButton = event.target.closest("[data-internship-stage]");
  if (!state.selectedInternshipId || (!approvalButton && !reviewButton && !stageButton)) return;
  const button = approvalButton || reviewButton || stageButton;
  button.disabled = true;
  try {
    if (reviewButton) {
      const result = await api(`/api/internships/${encodeURIComponent(state.selectedInternshipId)}/review`, {
        method: "POST", body: {}
      });
      state.selectedJobId = result.job_id;
      toast("Five Sheep are now reviewing this discovery");
      await loadAll(true);
    } else if (approvalButton) {
      const result = await api(`/api/internships/${encodeURIComponent(state.selectedInternshipId)}/approval`, {
        method: "POST", body: {}
      });
      state.selectedJobId = result.job_id;
      toast("Gatekeeper approval is ready for your decision");
      await loadAll(true);
      document.querySelector("#approvals").scrollIntoView({ behavior: "smooth" });
    } else {
      await api(`/api/internships/${encodeURIComponent(state.selectedInternshipId)}`, {
        method: "PATCH", body: { stage: stageButton.dataset.internshipStage }
      });
      toast(`Application moved to ${displayStatus(stageButton.dataset.internshipStage)}`);
      await loadAll(true);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#agents-grid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-agent-id]");
  if (card) openAgentDialog(card.dataset.agentId);
});

$("#labyrinth-stage").addEventListener("click", (event) => {
  const domain = event.target.closest("[data-domain-id]");
  if (!domain) return;
  if (domain.dataset.domainId === "shepard") enterShepardFocus();
  else openAgentDialog(domain.dataset.domainId);
});

$("#labyrinth-stage").addEventListener("pointerover", (event) => {
  const domain = event.target.closest(".domain[data-domain-id]");
  labyrinthScene?.setHovered(domain?.dataset.domainId || null);
});

$("#labyrinth-stage").addEventListener("pointerout", (event) => {
  if (!event.relatedTarget?.closest?.(".domain[data-domain-id]")) labyrinthScene?.setHovered(null);
});

$("#labyrinth-stage").addEventListener("pointerdown", (event) => {
  if (state.focusOpen || event.target.closest("button")) return;
  state.orbit.dragging = true;
  state.orbit.x = event.clientX;
  state.orbit.y = event.clientY;
  event.currentTarget.classList.add("dragging");
  event.currentTarget.setPointerCapture(event.pointerId);
});

$("#labyrinth-stage").addEventListener("pointermove", (event) => {
  if (!state.orbit.dragging) return;
  const dx = event.clientX - state.orbit.x;
  const dy = event.clientY - state.orbit.y;
  state.orbit.x = event.clientX;
  state.orbit.y = event.clientY;
  state.orbit.angle += dx * .48;
  state.orbit.tilt = Math.max(30, Math.min(74, state.orbit.tilt - dy * .28));
  applyOrbit();
});

function stopOrbit(event) {
  state.orbit.dragging = false;
  event.currentTarget.classList.remove("dragging");
}

$("#labyrinth-stage").addEventListener("pointerup", stopOrbit);
$("#labyrinth-stage").addEventListener("pointercancel", stopOrbit);
$("#labyrinth-stage").addEventListener("wheel", (event) => {
  if (state.focusOpen) return;
  event.preventDefault();
  state.orbit.zoom = Math.max(.72, Math.min(1.35, state.orbit.zoom - event.deltaY * .0007));
  applyOrbit();
}, { passive: false });
$("#labyrinth-stage").addEventListener("dblclick", () => {
  if (state.focusOpen) return;
  state.orbit = { ...state.orbit, angle: -12, tilt: 50, zoom: 1.02, panX: "0px", panY: "0px" };
  applyOrbit();
  toast("Orbit reset");
});

$("#leave-roots-button").addEventListener("click", leaveShepardFocus);
$("#leave-chat-button").addEventListener("click", returnToLabyrinth);
$("#gesture-toggle").addEventListener("click", toggleGestureControls);
$("#weather-status").addEventListener("click", requestWeather);
$("#council-button").addEventListener("click", async () => {
  const button = $("#council-button");
  button.disabled = true;
  try {
    const result = await api("/api/council", { method: "POST", body: {} });
    state.selectedJobId = result.job_id;
    state.delegatedJobs[result.job_id] = "pending";
    toast("Every Sheep is gathering at the roots");
    await loadAll(true);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const agentId = $("#agent-id").value;
    const body = {
      name: $("#agent-name").value,
      role: $("#agent-role").value,
      model: $("#agent-model").value,
      persona: $("#agent-persona").value
    };
    await api(agentId ? `/api/agents/${encodeURIComponent(agentId)}` : "/api/agents", {
      method: agentId ? "PATCH" : "POST", body
    });
    $("#agent-dialog").close();
    toast(agentId ? "Character profile saved" : "A new Sheep entered the Labyrinth");
    await loadAll(true);
  } catch (error) { toast(error.message, true); }
});

$("#add-sheep-button").addEventListener("click", openCreateDialog);

$("#approvals-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-approval]");
  if (!button) return;
  try {
    await api(`/api/approvals/${encodeURIComponent(button.dataset.approval)}`, {
      method: "POST", body: { decision: button.dataset.decision }
    });
    toast(`Action ${button.dataset.decision}`);
    await loadAll(true);
  } catch (error) { toast(error.message, true); }
});

document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));

const workspacePanels = {
  command: $(".command-console"),
  internships: $(".internships-panel"),
  jobs: $(".workspace-grid"),
  sheep: $(".agents-panel"),
  approvals: $(".approvals-panel")
};

Object.entries(workspacePanels).forEach(([name, panel]) => {
  if (!panel || panel.querySelector(".workspace-panel-close")) return;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "workspace-panel-close workspace-return-button";
  close.dataset.panelClose = name;
  close.setAttribute("aria-label", `Back to the Labyrinth from ${name}`);
  close.innerHTML = '<span aria-hidden="true">←</span><span>Back to Labyrinth</span>';
  close.addEventListener("click", returnToLabyrinth);
  panel.prepend(close);
});

$(".brand").addEventListener("click", (event) => {
  event.preventDefault();
  returnToLabyrinth();
});

$("#world-menu-button").addEventListener("click", () => {
  if (document.body.classList.contains("world-menu-open")) closeWorldMenu();
  else openWorldMenu();
});
$("#world-menu-close").addEventListener("click", closeWorldMenu);
$("#world-overlay-backdrop").addEventListener("click", () => {
  closeWorldMenu();
  closeWorkspacePanel();
  if (state.mode === "chat") setMode("labyrinth");
});
document.querySelectorAll("[data-workspace-panel]").forEach((button) => {
  button.addEventListener("click", () => openWorkspacePanel(button.dataset.workspacePanel));
});
document.querySelectorAll("[data-world-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.worldAction;
    closeWorldMenu();
    closeWorkspacePanel();
    if (action === "chat") setMode("chat");
    else if (action === "connections") $("#connections-button").click();
    else if (action === "alarms") $("#alarms-button").click();
  });
});

async function sendChat(input) {
  if (state.chatBusy) return;
  const content = input.value.trim();
  if (!content) return;
  state.chat.push({ role: "user", content });
  input.value = "";
  state.chatBusy = true;
  storeChat();
  renderChat();
  $("#chat-send-button").disabled = true;
  $("#focus-chat-send").disabled = true;
  try {
    const result = await api("/api/chat", { method: "POST", body: { messages: state.chat.slice(-24) } });
    state.chat.push({ role: "assistant", content: result.reply, sources: result.sources || [] });
    if (result.job_id) {
      state.selectedJobId = result.job_id;
      state.delegatedJobs[result.job_id] = "pending";
      toast("A Sheep team is moving toward the roots");
      await loadAll(true);
    }
    storeChat();
  } catch (error) {
    state.chat.push({ role: "assistant", content: `I couldn’t complete that request: ${error.message}` });
    toast(error.message, true);
  } finally {
    state.chatBusy = false;
    $("#chat-send-button").disabled = false;
    $("#focus-chat-send").disabled = false;
    renderChat();
    input.focus();
  }
}

function bindChatForm(formSelector, inputSelector) {
  const form = $(formSelector);
  const input = $(inputSelector);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat(input);
  });
  input.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") form.requestSubmit();
  });
}

bindChatForm("#chat-form", "#chat-input");
bindChatForm("#focus-chat-form", "#focus-chat-input");

$("#clear-chat-button").addEventListener("click", () => {
  state.chat = [];
  storeChat();
  renderChat();
  toast("Conversation cleared");
});

function alarmInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

$("#alarms-button").addEventListener("click", () => {
  primeAlarmAudio();
  if (!$("#alarm-time").value) $("#alarm-time").value = alarmInputValue(new Date(Date.now() + 10 * 60000));
  $("#alarms-dialog").showModal();
  requestAnimationFrame(() => $("#alarm-label").focus());
});

$("#close-alarms").addEventListener("click", () => $("#alarms-dialog").close());

$("#alarm-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#create-alarm-button");
  const scheduled = new Date($("#alarm-time").value);
  if (Number.isNaN(scheduled.getTime())) return toast("Choose a valid alarm time", true);
  button.disabled = true;
  button.textContent = "Setting…";
  try {
    const alarm = await api("/api/alarms", {
      method: "POST",
      body: {
        label: $("#alarm-label").value.trim(),
        scheduled_for: scheduled.toISOString(),
        repeat_kind: $("#alarm-repeat").value
      }
    });
    state.alarms.push(alarm);
    state.alarms.sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for));
    renderAlarms();
    $("#alarm-form").reset();
    $("#alarm-time").value = alarmInputValue(new Date(Date.now() + 10 * 60000));
    toast(`Alarm set for ${formatAlarmTime(alarm.scheduled_for)}`);
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
    checkAlarms();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Set alarm";
  }
});

$("#alarm-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-alarm-dismiss]");
  if (!button) return;
  button.disabled = true;
  try {
    const updated = await api(`/api/alarms/${encodeURIComponent(button.dataset.alarmDismiss)}`, {
      method: "PATCH", body: { status: "dismissed" }
    });
    state.alarms = state.alarms.map((alarm) => alarm.id === updated.id ? updated : alarm);
    renderAlarms();
    toast("Alarm dismissed");
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
  }
});

$("#dismiss-alarm").addEventListener("click", () => {
  $("#alarm-ring-dialog").close();
  state.ringingAlarm = null;
  window.setTimeout(checkAlarms, 250);
});

$("#snooze-alarm").addEventListener("click", async () => {
  const alarm = state.ringingAlarm;
  if (!alarm) return;
  const button = $("#snooze-alarm");
  button.disabled = true;
  try {
    const updated = await api(`/api/alarms/${encodeURIComponent(alarm.id)}`, {
      method: "PATCH",
      body: { status: "active", scheduled_for: new Date(Date.now() + 10 * 60000).toISOString() }
    });
    state.alarms = state.alarms.map((item) => item.id === updated.id ? updated : item);
    $("#alarm-ring-dialog").close();
    state.ringingAlarm = null;
    renderAlarms();
    toast("Snoozed for 10 minutes");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.addEventListener("pointerdown", primeAlarmAudio, { once: true });

$("#connections-button").addEventListener("click", async () => {
  $("#connections-dialog").showModal();
  await loadConnectors();
});

function hideConnectorSetups() {
  $("#connector-setup").hidden = true;
  $("#claude-setup").hidden = true;
  $("#gemini-setup").hidden = true;
  $("#outlook-web-setup").hidden = true;
  $("#chrome-setup").hidden = true;
  $("#job-sites-setup").hidden = true;
}

function revealConnectorSetup(selector) {
  hideConnectorSetups();
  const panel = $(selector);
  panel.hidden = false;
  requestAnimationFrame(() => panel.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  return panel;
}

$("#close-connections").addEventListener("click", () => {
  hideConnectorSetups();
  $("#connections-dialog").close();
});
$("#dismiss-setup").addEventListener("click", hideConnectorSetups);
$("#dismiss-claude-setup").addEventListener("click", hideConnectorSetups);
$("#dismiss-gemini-setup").addEventListener("click", hideConnectorSetups);
$("#dismiss-outlook-web-setup").addEventListener("click", hideConnectorSetups);
$("#dismiss-chrome-setup").addEventListener("click", hideConnectorSetups);
$("#dismiss-job-sites-setup").addEventListener("click", hideConnectorSetups);

$("#claude-setup").addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiKey = $("#claude-api-key").value.trim();
  const button = $("#connect-claude-button");
  const status = $("#claude-setup-status");
  if (!apiKey) return;
  button.disabled = true;
  button.textContent = "Checking key…";
  status.className = "setup-status";
  status.textContent = "Testing the key with Anthropic…";
  try {
    const result = await api("/api/connectors/claude/connect", {
      method: "POST", body: { api_key: apiKey }
    });
    const modelOptions = $("#model-options");
    new Set(result.model_names || []).forEach((model) => {
      if (![...modelOptions.options].some((option) => option.value === model)) {
        const option = document.createElement("option");
        option.value = model;
        modelOptions.append(option);
      }
    });
    $("#claude-api-key").value = "";
    status.className = "setup-status good";
    status.textContent = `Connected. ${result.models.length} Claude model${result.models.length === 1 ? "" : "s"} available.`;
    toast("Claude is connected to Shepard");
    await loadConnectors();
  } catch (error) {
    status.className = "setup-status error";
    status.textContent = error.message;
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Connect Claude";
  }
});

$("#gemini-setup").addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiKey = $("#gemini-api-key").value.trim();
  const button = $("#connect-gemini-button");
  const status = $("#gemini-setup-status");
  if (!apiKey) return;
  button.disabled = true;
  button.textContent = "Checking key…";
  status.className = "setup-status";
  status.textContent = "Testing the key with Google AI…";
  try {
    const result = await api("/api/connectors/gemini/connect", {
      method: "POST", body: { api_key: apiKey }
    });
    const modelOptions = $("#model-options");
    new Set(result.model_names || []).forEach((model) => {
      if (![...modelOptions.options].some((option) => option.value === model)) {
        const option = document.createElement("option");
        option.value = model;
        modelOptions.append(option);
      }
    });
    $("#gemini-api-key").value = "";
    status.className = "setup-status good";
    status.textContent = `Connected. ${result.models.length} Gemini model${result.models.length === 1 ? "" : "s"} available.`;
    toast("Gemini is connected to Shepard");
    await loadConnectors();
  } catch (error) {
    status.className = "setup-status error";
    status.textContent = error.message;
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Connect Gemini";
  }
});

$("#pair-chrome-button").addEventListener("click", async () => {
  const button = $("#pair-chrome-button");
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    const result = await api("/api/connectors/chrome/pair", { method: "POST", body: {} });
    $("#chrome-extension-path").textContent = result.extension_path;
    $("#chrome-pairing-code").textContent = result.pairing_code;
    $("#chrome-pairing-row").hidden = false;
    toast("Pairing code ready—paste it into the Chrome extension");
    await loadConnectors();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Generate pairing code";
  }
});

$("#connectors-grid").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-connector-id]");
  if (!button || button.disabled) return;
  if (button.dataset.connectorId === "claude") {
    revealConnectorSetup("#claude-setup");
    window.setTimeout(() => $("#claude-api-key").focus(), 220);
    return;
  }
  if (button.dataset.connectorId === "gemini") {
    revealConnectorSetup("#gemini-setup");
    window.setTimeout(() => $("#gemini-api-key").focus(), 220);
    return;
  }
  if (button.dataset.connectorId === "outlook-web") {
    revealConnectorSetup(
      button.dataset.connectorStatus === "browser_ready"
        ? "#outlook-web-setup" : "#chrome-setup"
    );
    return;
  }
  if (button.dataset.connectorId === "chrome") {
    revealConnectorSetup("#chrome-setup");
    return;
  }
  if (["linkedin-jobs", "handshake", "job-sites"].includes(button.dataset.connectorId)) {
    revealConnectorSetup(
      ["browser_ready", "manual_only"].includes(button.dataset.connectorStatus)
        ? "#job-sites-setup" : "#chrome-setup"
    );
    return;
  }
  if (button.dataset.connectorId !== "google-calendar") {
    toast("That bridge is planned, but not active yet");
    return;
  }
  if (button.dataset.connectorStatus === "setup_required") {
    revealConnectorSetup("#connector-setup");
    return;
  }
  button.disabled = true;
  button.textContent = "Opening…";
  const authWindow = window.open("", "shepard-google-calendar", "width=620,height=760");
  try {
    if (!authWindow) throw new Error("Allow pop-ups to open Google authorization");
    const result = await api("/api/connectors/google-calendar/connect", { method: "POST", body: {} });
    authWindow.location.href = result.authorization_url;
    toast("Finish authorization in the Google window");
    let checks = 0;
    const connectionPoll = setInterval(async () => {
      checks += 1;
      await loadConnectors();
      const google = state.connectors.find((connector) => connector.id === "google-calendar");
      if (google?.status === "connected") {
        clearInterval(connectionPoll);
        if (!authWindow.closed) authWindow.close();
        toast("Google Calendar connected with read-only access");
      } else if (checks >= 60 || authWindow.closed) {
        clearInterval(connectionPoll);
      }
    }, 2000);
  } catch (error) {
    if (authWindow) authWindow.close();
    toast(error.message, true);
  } finally {
    await loadConnectors();
  }
});

$("#refresh-button").addEventListener("click", () => loadAll());
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (document.body.classList.contains("world-menu-open")) {
      closeWorldMenu();
      return;
    }
    if (document.body.dataset.workspacePanel) {
      closeWorkspacePanel();
      return;
    }
    if (state.mode === "chat") {
      setMode("labyrinth");
      return;
    }
    if (state.focusOpen) {
      leaveShepardFocus();
      return;
    }
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
  if (event.key.toLowerCase() === "g") toggleGestureControls();
  else if (event.key.toLowerCase() === "r" && !state.focusOpen) {
    state.orbit = { ...state.orbit, angle: -12, tilt: 50, zoom: 1.02, panX: "0px", panY: "0px" };
    applyOrbit();
    toast("Orbit reset");
  } else if (["+", "="].includes(event.key) && !state.focusOpen) {
    state.orbit.zoom = Math.min(1.42, state.orbit.zoom + .08);
    applyOrbit();
  } else if (["-", "_"].includes(event.key) && !state.focusOpen) {
    state.orbit.zoom = Math.max(.72, state.orbit.zoom - .08);
    applyOrbit();
  }
});
window.addEventListener("pagehide", () => stopGestureControls());
setInterval(() => loadAll(true), 4000);
setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }, 1000);
setInterval(checkAlarms, 1000);

loadStoredChat();
renderChat();
setMode(state.mode);
applyOrbit();
startLabyrinthScene();
setTimeSky();
requestWeather();
loadHealth();
loadAll(true);
if ("requestIdleCallback" in window) requestIdleCallback(() => loadHandControlsModule().catch(() => {}));
else window.setTimeout(() => loadHandControlsModule().catch(() => {}), 700);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
