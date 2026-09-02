const state = {
  page: 1,
  pageSize: 10,
  totalPages: 1,
  total: 0,
  cases: [],
  trends: [],
  search: "",
};

const elements = {
  themeToggle: document.querySelector("#theme-toggle"),
  themeIcon: document.querySelector(".theme-icon"),
  langfuseLink: document.querySelector("#langfuse-link"),
  metricTotal: document.querySelector("#metric-total"),
  metricWeek: document.querySelector("#metric-week"),
  metricClassification: document.querySelector("#metric-classification"),
  metricPriority: document.querySelector("#metric-priority"),
  metricTicket: document.querySelector("#metric-ticket"),
  metricLatest: document.querySelector("#metric-latest"),
  trendChart: document.querySelector("#trend-chart"),
  form: document.querySelector("#support-form"),
  ticketId: document.querySelector('input[name="ticket_id"]'),
  runButton: document.querySelector("#run-button"),
  runLabel: document.querySelector("#run-label"),
  formStatus: document.querySelector("#form-status"),
  resultCount: document.querySelector("#result-count"),
  historySearch: document.querySelector("#history-search"),
  refreshButton: document.querySelector("#refresh-button"),
  historyBody: document.querySelector("#history-body"),
  tableEmpty: document.querySelector("#table-empty"),
  emptyTitle: document.querySelector("#empty-title"),
  emptyMessage: document.querySelector("#empty-message"),
  pageSummary: document.querySelector("#page-summary"),
  previousPage: document.querySelector("#previous-page"),
  nextPage: document.querySelector("#next-page"),
  dialog: document.querySelector("#case-dialog"),
  closeDialog: document.querySelector("#close-dialog"),
  toast: document.querySelector("#toast"),
};

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  elements.themeIcon.textContent = theme === "dark" ? "☀" : "☾";
  const themeAction = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  elements.themeToggle.setAttribute("aria-label", themeAction);
  elements.themeToggle.title = themeAction;
  localStorage.setItem("customer-support-theme", theme);
}

function initializeTheme() {
  const saved = localStorage.getItem("customer-support-theme");
  const preferred = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  applyTheme(saved === "light" || saved === "dark" ? saved : preferred);
}

function generateTicketId() {
  const uniquePart = crypto.randomUUID().replaceAll("-", "").slice(0, 8).toUpperCase();
  return `CS-${uniquePart}`;
}

function resetTicketId() {
  elements.ticketId.value = generateTicketId();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.ok) return response.json();
  let message = `Request failed with status ${response.status}`;
  try {
    const payload = await response.json();
    message = typeof payload.detail === "string" ? payload.detail : message;
  } catch {
    // Keep the status-based message when a proxy returns non-JSON content.
  }
  throw new Error(message);
}

async function loadUiConfig() {
  try {
    const config = await api("/api/ui-config");
    if (config.langfuse_project_url) {
      elements.langfuseLink.href = config.langfuse_project_url;
      elements.langfuseLink.hidden = false;
    }
  } catch {
    // Traces remain hidden when UI configuration is unavailable.
  }
}

function formatDate(value, options = {}) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: options.short ? undefined : "short",
  }).format(new Date(value));
}

function humanize(value) {
  return value ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—";
}

function shortId(value) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function preview(value, length = 88) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, length);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function groupValues(items, selector) {
  const totals = new Map();
  items.forEach((item) => {
    const key = selector(item) || "unknown";
    totals.set(key, (totals.get(key) || 0) + 1);
  });
  return [...totals.entries()].sort((left, right) => right[1] - left[1]);
}

function renderDonut(donutId, totalId, legendId, entries, colors, unit) {
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  let cursor = 0;
  const stops = entries.map(([, count], index) => {
    const start = cursor;
    cursor += total ? (count / total) * 100 : 0;
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  document.querySelector(`#${donutId}`).style.background = stops.length
    ? `conic-gradient(${stops.join(", ")})`
    : "conic-gradient(var(--border) 0 100%)";
  document.querySelector(`#${totalId}`).textContent = String(total);
  const legend = document.querySelector(`#${legendId}`);
  legend.replaceChildren();
  (entries.length ? entries : [[`No ${unit} yet`, 0]]).forEach(([name, count], index) => {
    const item = document.createElement("li");
    const marker = document.createElement("i");
    marker.style.background = colors[index % colors.length];
    item.append(marker, element("span", "", humanize(name)), element("strong", "", String(count)));
    legend.append(item);
  });
}

function renderBars(targetId, entries) {
  const target = document.querySelector(`#${targetId}`);
  target.replaceChildren();
  const display = entries.length ? entries.slice(0, 5) : [["No completed cases", 0]];
  const maximum = Math.max(1, ...display.map(([, count]) => count));
  display.forEach(([name, count]) => {
    const row = element("div", "insight-row");
    const heading = document.createElement("div");
    heading.append(element("span", "", humanize(name)), element("strong", "", String(count)));
    const track = element("div", "insight-track");
    const bar = document.createElement("i");
    bar.style.width = `${count ? Math.max(8, (count / maximum) * 100) : 0}%`;
    track.append(bar);
    row.append(heading, track);
    target.append(row);
  });
}

function renderInsights() {
  renderDonut(
    "priority-donut",
    "priority-total",
    "priority-legend",
    groupValues(state.cases, (item) => item.priority),
    ["var(--danger)", "var(--amber)", "var(--primary)", "var(--green)"],
    "cases",
  );
  renderBars("classification-bars", groupValues(state.cases, (item) => item.classification));
}

function renderMetrics() {
  elements.metricTotal.textContent = state.total.toLocaleString();
  elements.metricWeek.textContent = state.trends
    .slice(-7)
    .reduce((total, point) => total + point.runs, 0)
    .toLocaleString();
  const latest = state.cases[0];
  elements.metricClassification.textContent = latest ? humanize(latest.classification) : "—";
  elements.metricClassification.title = latest ? latest.classification : "";
  elements.metricPriority.textContent = latest ? `${humanize(latest.priority)} priority` : "No completed case";
  elements.metricTicket.textContent = latest?.ticket_id ?? "—";
  elements.metricLatest.textContent = latest
    ? formatDate(latest.created_at, { short: true })
    : "PostgreSQL persistence";
  renderInsights();
}

function renderTrendChart() {
  elements.trendChart.replaceChildren();
  const maximum = Math.max(1, ...state.trends.map((point) => point.runs));
  state.trends.forEach((point, index) => {
    const column = element("div", "trend-column");
    const value = element("span", "trend-value", String(point.runs));
    const bar = element("div", "trend-bar");
    const height = point.runs === 0 ? 3 : Math.max(12, (point.runs / maximum) * 155);
    bar.style.height = `${height}px`;
    bar.title = `${point.runs} completed case${point.runs === 1 ? "" : "s"} on ${point.day}`;
    const day = element(
      "span",
      "trend-day",
      index % 2 === 0
        ? new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" })
            .format(new Date(`${point.day}T00:00:00`))
        : "",
    );
    column.append(value, bar, day);
    elements.trendChart.append(column);
  });
}

function renderHistory() {
  elements.historyBody.replaceChildren();
  elements.tableEmpty.hidden = state.cases.length !== 0;
  elements.emptyTitle.textContent = state.search
    ? "No matching support workflows"
    : "No completed support cases yet";
  elements.emptyMessage.textContent = state.search
    ? "Try a different ticket, category, workflow ID, case ID, or response term."
    : "Run the workflow to create the first case.";
  const countLabel = `${state.total.toLocaleString()} case${state.total === 1 ? "" : "s"}`;
  elements.resultCount.textContent = state.search ? `${countLabel} found` : countLabel;

  state.cases.forEach((supportCase) => {
    const row = document.createElement("tr");
    const completed = document.createElement("td");
    completed.append(
      element("strong", "", formatDate(supportCase.created_at)),
      element("span", "status-pill", "Completed"),
    );

    const input = document.createElement("td");
    const inputWrap = element("div", "input-cell");
    inputWrap.append(
      element("strong", "", supportCase.ticket_id),
      element("span", "", preview(supportCase.subject) || "Legacy case input"),
    );
    input.append(inputWrap);

    const output = document.createElement("td");
    const outputWrap = element("div", "output-cell");
    outputWrap.append(
      element("strong", "", `${humanize(supportCase.classification)} · ${humanize(supportCase.priority)}`),
      element("span", "", preview(supportCase.recommended_response) || "Completed response"),
    );
    output.append(outputWrap);

    const workflow = element("td", "mono id-cell", shortId(supportCase.workflow_id));
    workflow.title = supportCase.workflow_id;
    const action = document.createElement("td");
    const button = element("button", "view-button", "View");
    button.type = "button";
    button.addEventListener("click", () => openCase(supportCase));
    action.append(button);
    row.append(completed, input, output, workflow, action);
    elements.historyBody.append(row);
  });

  elements.pageSummary.textContent = `Page ${state.page} of ${state.totalPages}`;
  elements.previousPage.disabled = state.page <= 1;
  elements.nextPage.disabled = state.page >= state.totalPages;
}

function openCase(supportCase) {
  document.querySelector("#dialog-title").textContent = `${supportCase.ticket_id} support case`;
  document.querySelector("#detail-ticket").textContent = supportCase.ticket_id;
  document.querySelector("#detail-classification").textContent = humanize(supportCase.classification);
  document.querySelector("#detail-priority").textContent = humanize(supportCase.priority);
  document.querySelector("#detail-created").textContent = formatDate(supportCase.created_at);
  document.querySelector("#detail-case-id").textContent = supportCase.case_id;
  document.querySelector("#detail-workflow-id").textContent = supportCase.workflow_id;
  document.querySelector("#detail-input").textContent = JSON.stringify({
    ticket_id: supportCase.ticket_id,
    subject: supportCase.subject || "Not retained for this legacy case",
    message: supportCase.message || "Not retained for this legacy case",
    customer_tier: supportCase.customer_tier,
  }, null, 2);
  document.querySelector("#detail-output").textContent = supportCase.recommended_response;
  document.querySelector("#detail-evidence").textContent = JSON.stringify({
    classification: supportCase.classification,
    priority: supportCase.priority,
    reason: supportCase.classification_reason,
    knowledge_citations: supportCase.knowledge_citations,
    request_id: supportCase.request_id,
  }, null, 2);
  elements.dialog.showModal();
}

function showToast(message, type = "success") {
  elements.toast.textContent = message;
  elements.toast.className = `toast visible ${type}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    elements.toast.className = "toast";
  }, 4200);
}

async function loadDashboard({ includeTrends = true } = {}) {
  elements.refreshButton.disabled = true;
  try {
    const requests = [
      api(
        `/api/cases?page=${state.page}&page_size=${state.pageSize}`
        + (state.search ? `&search=${encodeURIComponent(state.search)}` : ""),
      ),
    ];
    if (includeTrends) requests.push(api("/api/cases/trends?days=14"));
    const [cases, trends] = await Promise.all(requests);
    state.cases = cases.items;
    state.total = cases.total;
    state.totalPages = cases.total_pages;
    if (trends) state.trends = trends;
    renderMetrics();
    renderTrendChart();
    renderHistory();
  } catch (error) {
    showToast(error.message, "error");
    elements.tableEmpty.hidden = false;
  } finally {
    elements.refreshButton.disabled = false;
  }
}

async function runSupport(event) {
  event.preventDefault();
  if (!elements.form.reportValidity()) return;
  const data = new FormData(elements.form);
  const payload = {
    ticket_id: String(data.get("ticket_id")).trim(),
    subject: String(data.get("subject")).trim(),
    message: String(data.get("message")).trim(),
    customer_tier: String(data.get("customer_tier")),
    user_id: String(data.get("user_id")).trim() || "customer-support-ui",
    conversation_id: String(data.get("conversation_id")).trim() || "customer-support-ui",
  };

  elements.runButton.disabled = true;
  elements.runButton.classList.add("is-running");
  elements.runLabel.textContent = "Support workflow running…";
  elements.formStatus.className = "form-status";
  elements.formStatus.textContent = "Agents are validating, classifying, retrieving guidance, and composing a response.";
  try {
    await api("/support/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.page = 1;
    state.search = "";
    elements.historySearch.value = "";
    await loadDashboard();
    elements.formStatus.className = "form-status success";
    elements.formStatus.textContent = "Workflow completed. The new case is first in run history.";
    showToast(`${payload.ticket_id} completed successfully.`);
    resetTicketId();
  } catch (error) {
    elements.formStatus.className = "form-status error";
    elements.formStatus.textContent = error.message;
    showToast(`Workflow failed: ${error.message}`, "error");
  } finally {
    elements.runButton.disabled = false;
    elements.runButton.classList.remove("is-running");
    elements.runLabel.textContent = "Start support workflow";
  }
}

elements.themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
elements.form.addEventListener("submit", runSupport);
elements.refreshButton.addEventListener("click", () => loadDashboard());
let searchTimer;
elements.historySearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = elements.historySearch.value.trim();
    state.page = 1;
    loadDashboard({ includeTrends: false });
  }, 300);
});
elements.previousPage.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadDashboard({ includeTrends: false });
  }
});
elements.nextPage.addEventListener("click", () => {
  if (state.page < state.totalPages) {
    state.page += 1;
    loadDashboard({ includeTrends: false });
  }
});
elements.closeDialog.addEventListener("click", () => elements.dialog.close());
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) elements.dialog.close();
});

initializeTheme();
resetTicketId();
loadUiConfig();
loadDashboard();
