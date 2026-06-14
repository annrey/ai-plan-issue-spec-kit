const columns = [
  { id: "backlog", label: "Backlog", hint: "Ideas and deferred work" },
  { id: "todo", label: "Todo", hint: "Ready for an agent or human" },
  { id: "in_progress", label: "In Progress", hint: "Claimed and being changed" },
  { id: "blocked", label: "Blocked", hint: "Needs a decision or dependency" },
  { id: "needs_review", label: "Needs Review", hint: "Waiting for triage" },
  { id: "in_review", label: "In Review", hint: "Ready for validation" },
  { id: "done", label: "Done", hint: "Accepted work" },
];

const allStatuses = columns.map((column) => column.id);
const priorities = ["P0", "P1", "P2", "P3", "none"];
const categories = ["foundation", "feature", "implementation", "validation", "operations", "manual"];
const realtimeEvents = [
  "issue.created",
  "issue.updated",
  "comment.created",
  "activity.created",
  "presence.updated",
  "board.exported",
];

const actorId = localStorage.getItem("ai-plan-issue-actor") || `web-${Math.random().toString(16).slice(2, 8)}`;
localStorage.setItem("ai-plan-issue-actor", actorId);

const state = {
  issues: [],
  actors: [],
  filter: "all",
  module: "all",
  selectedId: null,
  selectedDetail: null,
  session: null,
  eventSource: null,
};

const board = document.querySelector("#board");
const issueCount = document.querySelector("#issue-count");
const metrics = document.querySelector("#metrics");
const moduleFilter = document.querySelector("#module-filter");
const moduleList = document.querySelector("#module-list");
const moduleCount = document.querySelector("#module-count");
const hierarchy = document.querySelector("#hierarchy");
const parentCount = document.querySelector("#parent-count");
const actorList = document.querySelector("#actor-list");
const actorCount = document.querySelector("#actor-count");
const connectionStatus = document.querySelector("#connection-status");
const drawer = document.querySelector("#drawer");
const drawerId = document.querySelector("#drawer-id");
const drawerTitle = document.querySelector("#drawer-title");
const detailMeta = document.querySelector("#detail-meta");
const relations = document.querySelector("#relations");
const issueMd = document.querySelector("#issue-md");
const comments = document.querySelector("#comments");
const activity = document.querySelector("#activity");
const statusSelect = document.querySelector("#status-select");
const prioritySelect = document.querySelector("#priority-select");
const categorySelect = document.querySelector("#category-select");
const assigneeInput = document.querySelector("#assignee-input");
const moduleInput = document.querySelector("#module-input");
const toast = document.querySelector("#toast");
const modalBackdrop = document.querySelector("#modal-backdrop");

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  setTimeout(() => toast.classList.remove("visible"), 2400);
}

function apiPath(path) {
  return path.startsWith("/api/") ? path : `/api/v1${path}`;
}

async function api(path, options = {}) {
  const response = await fetch(apiPath(path), {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Request failed: ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function truncate(text, length = 96) {
  if (!text) return "";
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
}

function formatStatus(value) {
  return String(value || "backlog").replaceAll("_", " ");
}

function issueTypeLabel(issue) {
  return issue.issue_type === "parent" ? "Parent" : "Step";
}

function initials(value) {
  if (!value) return "AI";
  return (
    value
      .split(/[-_\s]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "AI"
  );
}

function issueById(issueId) {
  return state.issues.find((issue) => issue.id === issueId);
}

function childrenOf(issue) {
  const childIds = new Set(issue.children || []);
  return state.issues
    .filter((candidate) => candidate.parent_id === issue.id || childIds.has(candidate.id))
    .sort(compareIssues);
}

function progressFor(issue) {
  const children = childrenOf(issue);
  if (!children.length) {
    return issue.status === "done" ? { done: 1, total: 1, percent: 100 } : { done: 0, total: 1, percent: 0 };
  }
  const done = children.filter((child) => child.status === "done").length;
  return { done, total: children.length, percent: Math.round((done / children.length) * 100) };
}

function compareIssues(a, b) {
  const parentA = a.parent_id || a.id;
  const parentB = b.parent_id || b.id;
  return (
    parentA.localeCompare(parentB) ||
    Number(a.order || 0) - Number(b.order || 0) ||
    a.id.localeCompare(b.id)
  );
}

function visibleIssues() {
  return state.issues
    .filter((issue) => {
      if (state.module !== "all" && (issue.module || "module") !== state.module) return false;
      if (state.filter === "parent") return issue.issue_type === "parent";
      if (state.filter === "step") return issue.issue_type !== "parent";
      if (state.filter === "claimed") return Boolean(issue.claimed_by || issue.assignee);
      if (state.filter === "review") return issue.status === "needs_review" || issue.status === "in_review";
      return true;
    })
    .sort(compareIssues);
}

function renderSelect(select, values, selected) {
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value.replaceAll("_", " ");
    option.selected = value === selected;
    select.append(option);
  });
}

function setConnection(label, online) {
  connectionStatus.textContent = label;
  connectionStatus.classList.toggle("online", online);
  connectionStatus.classList.toggle("offline", !online);
}

function renderActors() {
  actorCount.textContent = state.actors.length;
  actorList.innerHTML = "";
  if (!state.actors.length) {
    actorList.innerHTML = '<div class="empty-state compact-empty">No active actors</div>';
    return;
  }
  state.actors.forEach((actor) => {
    const item = document.createElement("div");
    item.className = `actor-row actor-${escapeHtml(actor.kind || "human")}`;
    item.innerHTML = `
      <span class="avatar small-avatar">${initials(actor.display_name || actor.actor)}</span>
      <span>
        <strong>${escapeHtml(actor.display_name || actor.actor)}</strong>
        <em>${escapeHtml(actor.issue_id || actor.kind || "online")}</em>
      </span>
    `;
    actorList.append(item);
  });
}

function renderModuleFilter() {
  const modules = Array.from(new Set(state.issues.map((issue) => issue.module || "module"))).sort();
  const selected = modules.includes(state.module) ? state.module : "all";
  state.module = selected;
  moduleFilter.innerHTML = "";
  [{ id: "all", label: "All modules" }, ...modules.map((name) => ({ id: name, label: name }))].forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    option.selected = item.id === selected;
    moduleFilter.append(option);
  });
}

function renderMetrics() {
  const total = state.issues.length;
  const parents = state.issues.filter((issue) => issue.issue_type === "parent").length;
  const steps = total - parents;
  const active = state.issues.filter((issue) => issue.status === "in_progress").length;
  const blocked = state.issues.filter((issue) => issue.status === "blocked").length;
  const review = state.issues.filter((issue) => issue.status === "needs_review" || issue.status === "in_review").length;
  const done = state.issues.filter((issue) => issue.status === "done").length;
  const donePct = total ? Math.round((done / total) * 100) : 0;

  metrics.innerHTML = [
    ["Total", total],
    ["Parents", parents],
    ["Steps", steps],
    ["Active", active],
    ["Review", review],
    ["Blocked", blocked],
    ["Done", `${donePct}%`],
  ]
    .map(
      ([label, value]) => `
        <div class="metric">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `,
    )
    .join("");
}

function renderModules() {
  const modules = new Map();
  state.issues.forEach((issue) => {
    const name = issue.module || "module";
    const current = modules.get(name) || { total: 0, active: 0, done: 0 };
    current.total += 1;
    if (issue.status === "in_progress") current.active += 1;
    if (issue.status === "done") current.done += 1;
    modules.set(name, current);
  });

  moduleCount.textContent = modules.size;
  moduleList.innerHTML = "";
  Array.from(modules.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .forEach(([name, stats]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `module-row${state.module === name ? " active" : ""}`;
      button.innerHTML = `
        <span class="module-name">${escapeHtml(name)}</span>
        <span class="module-stats">${stats.done}/${stats.total} done</span>
      `;
      button.addEventListener("click", () => {
        state.module = state.module === name ? "all" : name;
        renderAll();
      });
      moduleList.append(button);
    });
}

function renderHierarchy() {
  const parents = state.issues
    .filter((issue) => issue.issue_type === "parent")
    .filter((issue) => state.module === "all" || issue.module === state.module)
    .sort(compareIssues);
  parentCount.textContent = parents.length;
  hierarchy.innerHTML = "";

  if (!parents.length) {
    hierarchy.innerHTML = '<div class="empty-state">No parent issues.</div>';
    return;
  }

  parents.forEach((parent) => {
    const progress = progressFor(parent);
    const item = document.createElement("div");
    item.className = "hierarchy-item";
    item.innerHTML = `
      <button class="hierarchy-parent" type="button">
        <span>
          <strong>${escapeHtml(parent.id)}</strong>
          ${escapeHtml(parent.title)}
        </span>
        <em>${progress.done}/${progress.total}</em>
      </button>
      <div class="progress-track"><span style="width:${progress.percent}%"></span></div>
      <div class="hierarchy-children"></div>
    `;
    item.querySelector(".hierarchy-parent").addEventListener("click", () => openIssue(parent.id));
    const childList = item.querySelector(".hierarchy-children");
    childrenOf(parent).forEach((child) => {
      const childButton = document.createElement("button");
      childButton.type = "button";
      childButton.className = `hierarchy-child status-${child.status}`;
      childButton.textContent = `${child.id} ${child.title}`;
      childButton.addEventListener("click", () => openIssue(child.id));
      childList.append(childButton);
    });
    hierarchy.append(item);
  });
}

function renderBoard() {
  const issues = visibleIssues();
  issueCount.textContent = `${issues.length} of ${state.issues.length} Issues`;
  board.innerHTML = "";
  columns.forEach((column) => {
    const columnIssues = issues.filter((issue) => issue.status === column.id);
    const section = document.createElement("section");
    section.className = "column";
    section.dataset.status = column.id;
    section.innerHTML = `
      <div class="column-header">
        <div class="column-title">
          <span class="status-pill">${column.label}</span>
          <span>${columnIssues.length}</span>
        </div>
        <span class="column-hint">${column.hint}</span>
      </div>
      <div class="cards"></div>
    `;
    const cards = section.querySelector(".cards");
    if (!columnIssues.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No issues";
      cards.append(empty);
    } else {
      columnIssues.forEach((issue) => cards.append(renderCard(issue)));
    }
    board.append(section);
  });
}

function renderCard(issue) {
  const progress = progressFor(issue);
  const childCount = childrenOf(issue).length;
  const sourceTasks = issue.source?.task_ids?.join(", ") || (issue.source?.manual ? "manual" : "none");
  const activeActors = state.actors.filter((actor) => actor.issue_id === issue.id);
  const button = document.createElement("button");
  button.type = "button";
  button.className = `card ${issue.issue_type === "parent" ? "parent-card" : "step-card"}`;
  button.innerHTML = `
    <div class="card-topline">
      <span class="card-id">${escapeHtml(issue.id)}${issue.parent_id ? ` / ${escapeHtml(issue.parent_id)}` : ""}</span>
      <span class="type-badge">${issueTypeLabel(issue)}</span>
    </div>
    <div class="card-title">${escapeHtml(issue.title)}</div>
    <div class="card-summary">${escapeHtml(truncate(issue.summary || ""))}</div>
    <div class="card-meta">
      <span>${escapeHtml(issue.category || "implementation")}</span>
      <span>${escapeHtml(issue.milestone || "milestone")}</span>
      <span>${escapeHtml(sourceTasks)}</span>
    </div>
    ${
      issue.issue_type === "parent"
        ? `<div class="card-progress"><div class="progress-track"><span style="width:${progress.percent}%"></span></div><small>${progress.done}/${progress.total} child issues done</small></div>`
        : `<div class="card-parent">Parent ${escapeHtml(issue.parent_id || "none")}</div>`
    }
    <div class="card-footer">
      <span class="avatar">${initials(issue.assignee || issue.claimed_by || "AI")}</span>
      <span class="priority ${issue.priority}">${issue.priority === "none" ? "No priority" : issue.priority}</span>
      <span class="module-tag">${escapeHtml(issue.module || "module")}</span>
      ${issue.assignee ? `<span class="assignee-tag">Assigned ${escapeHtml(issue.assignee)}</span>` : ""}
      ${issue.claimed_by ? `<span class="claimed-tag">Claimed ${escapeHtml(issue.claimed_by)}</span>` : ""}
      ${activeActors.length ? `<span class="presence-tag">${activeActors.length} online</span>` : ""}
      ${childCount ? `<span class="child-count">${childCount} children</span>` : ""}
    </div>
  `;
  button.addEventListener("click", () => openIssue(issue.id));
  return button;
}

function renderAll() {
  renderModuleFilter();
  renderMetrics();
  renderModules();
  renderHierarchy();
  renderBoard();
  renderActors();
}

async function loadSession() {
  state.session = await api("/session");
  state.actors = state.session.actors || [];
  renderActors();
}

async function loadIssues() {
  const index = await api("/issues");
  state.issues = (index.issues || []).sort(compareIssues);
  renderAll();
}

async function openIssue(issueId) {
  const detail = await api(`/issues/${encodeURIComponent(issueId)}`);
  state.selectedId = issueId;
  state.selectedDetail = detail;
  renderDrawer();
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  sendPresence(issueId);
}

function renderDrawer() {
  const detail = state.selectedDetail;
  if (!detail) return;
  const issue = detail.issue;
  drawerId.textContent = `${issue.id} · ${issueTypeLabel(issue)} · ${formatStatus(issue.status)} · r${issue.revision}`;
  drawerTitle.textContent = issue.title;
  issueMd.textContent = detail.issue_md || "No issue.md content.";
  renderDetailMeta(issue);
  renderRelations(issue);
  renderSelect(statusSelect, allStatuses, issue.status);
  renderSelect(prioritySelect, priorities, issue.priority);
  renderSelect(categorySelect, categories, issue.category || "implementation");
  assigneeInput.value = issue.assignee || "";
  moduleInput.value = issue.module || "";
  document.querySelector("#add-child-btn").disabled = issue.issue_type !== "parent";
  renderTimeline(comments, detail.comments, "body");
  renderTimeline(activity, detail.activity, "body", "action");
}

function renderDetailMeta(issue) {
  const progress = progressFor(issue);
  const sourceTasks = issue.source?.task_ids?.join(", ") || (issue.source?.manual ? "manual" : "none");
  const entries = [
    ["Status", formatStatus(issue.status)],
    ["Priority", issue.priority],
    ["Category", issue.category || "implementation"],
    ["Module", issue.module || "module"],
    ["Milestone", issue.milestone || "manual"],
    ["Assignee", issue.assignee || "none"],
    ["Claimed", issue.claimed_by || "none"],
    ["Revision", issue.revision || 1],
    ["Source", sourceTasks],
  ];
  if (issue.issue_type === "parent") {
    entries.push(["Progress", `${progress.done}/${progress.total} done`]);
  }

  detailMeta.innerHTML = entries
    .map(
      ([label, value]) => `
        <div class="meta-item">
          <span>${label}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function relationButton(issue) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `relation-chip status-${issue.status}`;
  button.textContent = `${issue.id} ${issue.title}`;
  button.addEventListener("click", () => openIssue(issue.id));
  return button;
}

function renderRelations(issue) {
  relations.innerHTML = "";

  const groups = [
    ["Parent", issue.parent_id ? [issueById(issue.parent_id)].filter(Boolean) : []],
    ["Children", childrenOf(issue)],
    ["Dependencies", (issue.depends_on || []).map(issueById).filter(Boolean)],
  ];

  groups.forEach(([label, items]) => {
    const group = document.createElement("div");
    group.className = "relation-group";
    group.innerHTML = `<div class="relation-label">${label}</div>`;
    const list = document.createElement("div");
    list.className = "relation-list";
    if (!items.length) {
      const empty = document.createElement("span");
      empty.className = "relation-empty";
      empty.textContent = "none";
      list.append(empty);
    } else {
      items.forEach((item) => list.append(relationButton(item)));
    }
    group.append(list);
    relations.append(group);
  });
}

function renderTimeline(target, entries, bodyKey, actionKey) {
  target.innerHTML = "";
  if (!entries || entries.length === 0) {
    const empty = document.createElement("div");
    empty.className = "timeline-item";
    empty.textContent = "No entries yet.";
    target.append(empty);
    return;
  }
  entries.slice().reverse().forEach((entry) => {
    const item = document.createElement("div");
    item.className = "timeline-item";
    const heading = actionKey && entry[actionKey] ? `${entry[actionKey]} · ` : "";
    item.innerHTML = `
      <div class="timeline-meta">${heading}${escapeHtml(entry.author || "unknown")} · ${escapeHtml(entry.ts || "")}</div>
      <div>${escapeHtml(entry[bodyKey] || "")}</div>
    `;
    target.append(item);
  });
}

async function handleApiError(error, selectedIssueId = state.selectedId) {
  if (error.status === 409) {
    showToast("Issue changed elsewhere. Reloaded latest revision.");
    await loadIssues();
    if (selectedIssueId) await openIssue(selectedIssueId);
    return;
  }
  if (error.status === 401) {
    showToast("Project token required. Open the authenticated URL printed by the server.");
    return;
  }
  showToast(error.message);
}

async function updateSelected(fields) {
  if (!state.selectedId || !state.selectedDetail) return;
  try {
    const updated = await api(`/issues/${encodeURIComponent(state.selectedId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        ...fields,
        author: actorId,
        expected_revision: state.selectedDetail.issue.revision,
      }),
    });
    const index = state.issues.findIndex((issue) => issue.id === updated.id);
    if (index >= 0) state.issues[index] = updated;
    renderAll();
    await openIssue(updated.id);
  } catch (error) {
    await handleApiError(error);
  }
}

async function updateTextField(field, value) {
  if (!state.selectedDetail) return;
  const current = state.selectedDetail.issue[field] || "";
  const next = value.trim();
  if (next === current) return;
  await updateSelected({ [field]: next || null });
}

async function sendPresence(issueId = state.selectedId) {
  if (!state.session?.authenticated) return;
  try {
    const presence = await api("/presence", {
      method: "POST",
      body: JSON.stringify({
        actor: actorId,
        display_name: actorId,
        kind: "human",
        issue_id: issueId || null,
      }),
    });
    state.actors = [presence, ...state.actors.filter((actor) => actor.actor !== presence.actor)];
    renderActors();
  } catch {
    // Presence should not block board usage.
  }
}

function connectEvents() {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource("/api/v1/events");
  state.eventSource = source;
  source.onopen = () => setConnection("Live", true);
  source.onerror = () => setConnection("Reconnecting", false);
  realtimeEvents.forEach((eventType) => {
    source.addEventListener(eventType, async (message) => {
      const event = JSON.parse(message.data);
      if (event.type === "presence.updated") {
        const actor = event.payload;
        state.actors = [actor, ...state.actors.filter((item) => item.actor !== actor.actor)];
        renderAll();
        return;
      }
      await loadIssues();
      if (state.selectedId) await openIssue(state.selectedId);
    });
  });
}

function openNewIssueModal(defaults = {}) {
  renderSelect(document.querySelector("#new-status"), allStatuses, defaults.status || "backlog");
  renderSelect(document.querySelector("#new-priority"), priorities, defaults.priority || "P2");
  renderSelect(document.querySelector("#new-category"), categories, defaults.category || "implementation");
  document.querySelector("#new-title").value = defaults.title || "";
  document.querySelector("#new-summary").value = defaults.summary || "";
  document.querySelector("#new-module").value = defaults.module || "";
  document.querySelector("#new-parent").value = defaults.parent_id || "";
  modalBackdrop.hidden = false;
  document.querySelector("#new-title").focus();
}

document.querySelector("#view-filters").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-filter]");
  if (!button) return;
  state.filter = button.dataset.filter;
  document.querySelectorAll("#view-filters button").forEach((item) => {
    item.classList.toggle("active", item === button);
  });
  renderAll();
});

moduleFilter.addEventListener("change", () => {
  state.module = moduleFilter.value;
  renderAll();
});

document.querySelector("#refresh-btn").addEventListener("click", async () => {
  await loadSession();
  await loadIssues();
  showToast("Board refreshed");
});

document.querySelector("#drawer-close").addEventListener("click", () => {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  state.selectedId = null;
  state.selectedDetail = null;
  sendPresence(null);
});

statusSelect.addEventListener("change", async () => {
  await updateSelected({ status: statusSelect.value });
  showToast("Status updated");
});

prioritySelect.addEventListener("change", async () => {
  await updateSelected({ priority: prioritySelect.value });
  showToast("Priority updated");
});

categorySelect.addEventListener("change", async () => {
  await updateSelected({ category: categorySelect.value });
  showToast("Category updated");
});

assigneeInput.addEventListener("change", async () => updateTextField("assignee", assigneeInput.value));
assigneeInput.addEventListener("blur", async () => updateTextField("assignee", assigneeInput.value));
assigneeInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    await updateTextField("assignee", assigneeInput.value);
  }
});

moduleInput.addEventListener("change", async () => updateTextField("module", moduleInput.value));
moduleInput.addEventListener("blur", async () => updateTextField("module", moduleInput.value));
moduleInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    await updateTextField("module", moduleInput.value);
  }
});

document.querySelector("#comment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = document.querySelector("#comment-body").value.trim();
  if (!body || !state.selectedId || !state.selectedDetail) return;
  try {
    await api(`/issues/${encodeURIComponent(state.selectedId)}/comments`, {
      method: "POST",
      body: JSON.stringify({
        author: actorId,
        body,
        expected_revision: state.selectedDetail.issue.revision,
      }),
    });
    document.querySelector("#comment-body").value = "";
    await openIssue(state.selectedId);
    showToast("Comment added");
  } catch (error) {
    await handleApiError(error);
  }
});

document.querySelector("#claim-btn").addEventListener("click", async () => {
  if (!state.selectedId || !state.selectedDetail) return;
  try {
    await api(`/issues/${encodeURIComponent(state.selectedId)}/claim`, {
      method: "POST",
      body: JSON.stringify({
        agent: actorId,
        expected_revision: state.selectedDetail.issue.revision,
      }),
    });
    await openIssue(state.selectedId);
    await loadIssues();
    showToast("Issue claimed");
  } catch (error) {
    await handleApiError(error);
  }
});

document.querySelector("#add-child-btn").addEventListener("click", () => {
  const issue = state.selectedDetail?.issue;
  if (!issue || issue.issue_type !== "parent") return;
  openNewIssueModal({
    parent_id: issue.id,
    module: issue.module || "",
    category: issue.category || "implementation",
    priority: issue.priority || "P2",
    status: "todo",
  });
});

document.querySelector("#copy-run-btn").addEventListener("click", async () => {
  if (!state.selectedId) return;
  const command = `ai-plan-issue detail ${state.selectedId}`;
  try {
    await navigator.clipboard.writeText(command);
    showToast("Run command copied");
  } catch {
    showToast(command);
  }
});

document.querySelector("#new-issue-btn").addEventListener("click", () => openNewIssueModal());

document.querySelector("#modal-close").addEventListener("click", () => {
  modalBackdrop.hidden = true;
});

document.querySelector("#new-issue-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const parentId = document.querySelector("#new-parent").value.trim() || null;
  const parent = parentId ? issueById(parentId) : null;
  const payload = {
    title: document.querySelector("#new-title").value.trim(),
    summary: document.querySelector("#new-summary").value.trim(),
    status: document.querySelector("#new-status").value,
    priority: document.querySelector("#new-priority").value,
    category: document.querySelector("#new-category").value,
    parent_id: parentId,
    module: document.querySelector("#new-module").value.trim() || null,
    author: actorId,
    expected_parent_revision: parent?.revision,
  };
  try {
    await api("/issues", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    modalBackdrop.hidden = true;
    await loadIssues();
    showToast("Issue created");
  } catch (error) {
    await handleApiError(error, parentId);
  }
});

async function boot() {
  try {
    setConnection("Connecting", false);
    await loadSession();
    await loadIssues();
    connectEvents();
    await sendPresence(null);
    setInterval(() => sendPresence(state.selectedId), 45000);
  } catch (error) {
    board.innerHTML = `<div class="column"><strong>Could not load issues</strong><p>${escapeHtml(error.message)}</p></div>`;
    setConnection("Offline", false);
  }
}

boot();
