const state = {
  user: null,
  csrfToken: document.cookie.split('; ').find((item) => item.startsWith('canvas_csrf='))?.split('=').slice(1).join('=') || null,
  dashboard: null,
  currentCourse: null,
  courseTab: "home",
  history: [],
  calendarDate: new Date(),
  calendarItems: [],
  calendarFilter: "all",
  conversations: [],
  selectedConversationId: null,
  inboxBox: "inbox",
  account: null,
  accountView: "profile",
};

const loginScreen = document.querySelector("#login-screen");
const appShell = document.querySelector("#app-shell");
const mainContent = document.querySelector("#main-content");
const navigationTray = document.querySelector("#navigation-tray");
const dialog = document.querySelector("#dialog");
const dialogTitle = document.querySelector("#dialog-title");
const dialogBody = document.querySelector("#dialog-body");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function request(path, options = {}) {
  const { headers = {}, ...requestOptions } = options;
  const isFormData = requestOptions.body instanceof FormData;
  const response = await fetch(path, {
    ...requestOptions,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(state.csrfToken ? { "X-CSRF-Token": state.csrfToken } : {}),
      ...headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(response.status >= 500 || typeof data.detail !== 'string'
      ? "Canvas could not complete this request." : data.detail);
    error.status = response.status;
    throw error;
  }
  return data;
}

function initials(name) {
  return name.split(" ").filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function localeCode() {
  return window.CanvasI18n?.getLocale() === "vi" ? "vi-VN" : "en-US";
}

function formatDate(value, withTime = true) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(localeCode(), {
    month: "short",
    day: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  }).format(new Date(value));
}

function formatLongDate(value) {
  return new Intl.DateTimeFormat(localeCode(), {
    weekday: "short", month: "long", day: "numeric", year: "numeric",
  }).format(new Date(value));
}

function formatTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat(localeCode(), {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function calendarTimeLabel(item) {
  const startsAt = formatTime(item.starts_at);
  if (item.type === "assignment") {
    return localeCode() === "vi-VN" ? `${startsAt} · Hạn nộp` : `${startsAt} · Due`;
  }
  return item.ends_at ? `${startsAt}–${formatTime(item.ends_at)}` : startsAt;
}

function eventTimeline(item) {
  const range = calendarTimeLabel(item);
  const duration = item.duration_minutes
    ? ` · ${item.duration_minutes} ${localeCode() === "vi-VN" ? "phút" : "min"}`
    : "";
  return `${formatLongDate(item.starts_at)} · ${range}${duration}`;
}

function setActiveNav(target) {
  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.nav === target);
  });
}

function showLoading() {
  mainContent.innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Loading...</p></div>';
}

function showError(error) {
  mainContent.innerHTML = `<div class="error-state"><h2>Something went wrong</h2><p>${escapeHtml(error.message)}</p><button class="Button" data-retry>Retry</button></div>`;
  document.querySelector("[data-retry]")?.addEventListener("click", loadDashboard);
}

function showFlash(message) {
  const flash = document.querySelector("#flash-message");
  flash.textContent = message;
  flash.classList.remove("hidden");
  window.setTimeout(() => flash.classList.add("hidden"), 2600);
}

function openDialog(title, body) {
  dialogTitle.textContent = title;
  dialogBody.innerHTML = body;
  dialog.classList.remove("hidden");
}

function closeDialog() {
  dialog.classList.add("hidden");
}

function closeTray() {
  navigationTray.classList.add("hidden");
  navigationTray.innerHTML = "";
}

function recordHistory(label, action) {
  state.history = [
    { label, action, at: new Date().toISOString() },
    ...state.history.filter((item) => item.label !== label),
  ].slice(0, 12);
}

async function syncAccountLocale() {
  try {
    state.account = await request("/api/account");
    window.CanvasI18n?.setLocale(state.account.profile.language);
  } catch (_) {
    // A temporary Account API failure must not prevent the user from signing in.
  }
}

async function login(email, password) {
  const error = document.querySelector("#login-error");
  error.textContent = "";
  try {
    const data = await request("/api/session", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    state.user = data.user;
    state.csrfToken = data.csrf_token;
    sessionStorage.removeItem("canvas_access_token");
    sessionStorage.removeItem("canvas_csrf_token");
    localStorage.setItem("canvas_user_id", data.user.id);
    document.querySelector("#nav-avatar").textContent = initials(data.user.name);
    loginScreen.classList.add("hidden");
    appShell.classList.remove("hidden");
    await syncAccountLocale();
    await loadDashboard();
  } catch (err) {
    error.textContent = err.message;
  }
}

document.querySelector("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  login(document.querySelector("#email").value, document.querySelector("#password").value);
});

document.querySelector("#forgot-password").addEventListener("click", () => {
  openDialog(
    "Forgot Password?",
    '<p>Enter your Email and we\'ll send you a link to change your password.</p><label class="ic-Label" for="forgot-email">Email</label><input id="forgot-email" class="ic-Input" type="email"><div style="text-align:right"><button class="Button Button--primary" data-request-password>Request Password</button></div>',
  );
  document.querySelector("[data-request-password]").addEventListener("click", () => {
    closeDialog();
    showFlash("Password recovery is not configured for this installation.");
  });
});

function dashboardCard(course) {
  return `
    <article class="ic-DashboardCard" style="--course-color:${course.color}" data-course-id="${course.id}">
      <div class="ic-DashboardCard__header">
        <div class="ic-DashboardCard__header_hero"></div>
        <button class="ic-DashboardCard__header-button" aria-label="Course card options">⋮</button>
        <button class="ic-DashboardCard__link" data-open-course="${course.id}">
          <div class="ic-DashboardCard__header_content">
            <h2 class="ic-DashboardCard__header-title">${escapeHtml(course.name)}</h2>
            <div class="ic-DashboardCard__header-subtitle">${escapeHtml(course.code)}</div>
            <div class="ic-DashboardCard__header-term">${escapeHtml(course.term)}</div>
          </div>
        </button>
      </div>
      <nav class="ic-DashboardCard__action-container" aria-label="Actions for ${escapeHtml(course.name)}">
        <button class="ic-DashboardCard__action" title="Announcements" data-card-tab="announcements" data-card-course="${course.id}">♢</button>
        <button class="ic-DashboardCard__action" title="Assignments" data-card-tab="assignments" data-card-course="${course.id}">▤</button>
        <button class="ic-DashboardCard__action" title="Discussions" data-card-tab="discussions" data-card-course="${course.id}">◯</button>
        <button class="ic-DashboardCard__action" title="Files" data-card-tab="files" data-card-course="${course.id}">▱</button>
      </nav>
    </article>`;
}

function bindCourseLinks() {
  document.querySelectorAll("[data-open-course]").forEach((button) => {
    button.addEventListener("click", () => loadCourse(Number(button.dataset.openCourse), "home"));
  });
  document.querySelectorAll("[data-card-tab]").forEach((button) => {
    button.addEventListener("click", () => loadCourse(Number(button.dataset.cardCourse), button.dataset.cardTab));
  });
}

function sidebarItems(items, icon) {
  if (!items.length) return '<p class="muted">Nothing for now</p>';
  return items.map((item) => `
    <div class="sidebar-item">
      <span class="sidebar-icon">${icon}</span>
      <div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.course_code)} · ${formatDate(item.due_at)}</small></div>
    </div>`).join("");
}

async function loadDashboard() {
  closeTray();
  showLoading();
  setActiveNav("dashboard");
  try {
    state.dashboard = await request(`/api/dashboard/${state.user.id}`);
    state.currentCourse = null;
    recordHistory("Dashboard", loadDashboard);
    mainContent.innerHTML = `
      <div class="content-header">
        <h1>Dashboard</h1>
        <div class="content-header-actions"><button class="Button" data-global-search>Search</button>${state.user.role === "instructor" ? '<button class="Button Button--primary" data-new-course>+ Course</button>' : ""}</div>
      </div>
      <div class="dashboard-layout">
        <section class="ic-DashboardCard__box">
          <div class="ic-DashboardCard__box__container">
            ${state.dashboard.courses.map(dashboardCard).join("")}
          </div>
        </section>
        <aside class="dashboard-sidebar">
          <section><h2>To Do</h2>${sidebarItems(state.dashboard.todos, "▤")}</section>
          <section><h2>Recent Feedback</h2>${sidebarItems(state.dashboard.recent_feedback, "✓")}</section>
        </aside>
      </div>`;
    bindCourseLinks();
    document.querySelector("[data-new-course]")?.addEventListener("click", openCourseCreator);
    document.querySelector("[data-global-search]")?.addEventListener("click", openGlobalSearch);
  } catch (error) {
    showError(error);
  }
}

function openAccountTray() {
  const user = state.user;
  navigationTray.innerHTML = `
    <div class="tray-header"><h2>Account</h2><button class="close-button" aria-label="Close">×</button></div>
    <div class="tray-profile"><div class="tray-avatar" style="background:${user.avatar_color}">${initials(user.name)}</div><h3>${escapeHtml(user.name)}</h3><p>${escapeHtml(user.email)}</p></div>
    <ul class="tray-list"><li><button data-account-view="notifications">Notifications</button></li><li><button data-account-view="profile">Profile</button></li><li><button data-account-view="files">Files</button></li><li><button data-account-view="settings">Settings</button></li><li><button data-logout>Logout</button></li></ul>`;
  navigationTray.classList.remove("hidden");
  navigationTray.querySelector(".close-button").addEventListener("click", closeTray);
  navigationTray.querySelectorAll("[data-account-view]").forEach((button) => {
    button.addEventListener("click", () => loadAccount(button.dataset.accountView));
  });
  navigationTray.querySelector("[data-logout]").addEventListener("click", logout);
}

const accountSections = [
  ["notifications", "Notifications"],
  ["profile", "Profile"],
  ["files", "Files"],
  ["settings", "Settings"],
];

const notificationLabels = {
  course_activities: ["Course Activities", "Assignments, grades and course content changes"],
  discussions: ["Discussions", "New topics, replies and mentions"],
  conversations: ["Conversations", "Inbox messages and replies"],
  scheduling: ["Scheduling", "Due dates and calendar changes"],
};

function accountNavigation() {
  return `<nav class="account-nav" aria-label="Account Navigation"><ul>${accountSections.map(([key, label]) => `<li><button class="${state.accountView === key ? "active" : ""}" data-account-section="${key}">${label}</button></li>`).join("")}</ul></nav>`;
}

function bindAccountNavigation() {
  document.querySelectorAll("[data-account-section]").forEach((button) => {
    button.addEventListener("click", () => loadAccount(button.dataset.accountSection, false));
  });
}

function humanFileSize(bytes) {
  if (!bytes) return "0 bytes";
  const units = ["bytes", "KB", "MB", "GB"];
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / (1024 ** unit);
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

async function loadAccount(view = "profile", refresh = true) {
  closeTray();
  setActiveNav("account");
  state.accountView = view;
  showLoading();
  try {
    if (refresh || !state.account) state.account = await request("/api/account");
    recordHistory(`Account: ${accountSections.find(([key]) => key === view)?.[1] || "Profile"}`, () => loadAccount(view));
    renderAccount();
  } catch (error) {
    showError(error);
  }
}

function renderAccount() {
  mainContent.innerHTML = `<div class="account-shell">${accountNavigation()}<section class="account-main" id="account-main"></section></div>`;
  bindAccountNavigation();
  const root = document.querySelector("#account-main");
  if (state.accountView === "notifications") renderAccountNotifications(root);
  else if (state.accountView === "files") renderAccountFiles(root);
  else if (state.accountView === "settings") renderAccountSettings(root);
  else renderAccountProfile(root);
}

function renderAccountProfile(root) {
  const { user, profile } = state.account;
  root.innerHTML = `${courseHeader("Profile", '<button class="Button Button--primary" data-edit-profile>Edit Profile</button>')}
    <div class="profile-summary">
      <div class="profile-avatar-large" style="background:${user.avatar_color}">${initials(profile.display_name)}</div>
      <div><h2>${escapeHtml(profile.display_name)}</h2><p class="muted">${escapeHtml(user.email)}</p><span class="pill">${user.role === "instructor" ? "Instructor" : "Student"}</span></div>
    </div>
    <section class="account-panel"><h2>Biography</h2><p>${profile.bio ? escapeHtml(profile.bio).replaceAll("\n", "<br>") : '<span class="muted">No biography has been added.</span>'}</p></section>
    <section class="account-panel"><h2>Ways to Contact</h2><div class="account-detail-row"><span>Email</span><strong>${escapeHtml(user.email)}</strong></div>${profile.pronouns ? `<div class="account-detail-row"><span>Pronouns</span><strong>${escapeHtml(profile.pronouns)}</strong></div>` : ""}</section>`;
  document.querySelector("[data-edit-profile]").addEventListener("click", openProfileEditor);
}

function openProfileEditor() {
  const { user, profile } = state.account;
  openDialog("Edit Profile", `<form id="account-profile-form">
    <label class="ic-Label" for="account-full-name">Full Name</label><input class="ic-Input" id="account-full-name" value="${escapeHtml(user.name)}" minlength="2" required>
    <label class="ic-Label" for="account-display-name">Display Name</label><input class="ic-Input" id="account-display-name" value="${escapeHtml(profile.display_name)}" minlength="2" required>
    <label class="ic-Label" for="account-pronouns">Pronouns</label><input class="ic-Input" id="account-pronouns" value="${escapeHtml(profile.pronouns)}" maxlength="64">
    <label class="ic-Label" for="account-bio">Biography</label><textarea class="ic-Input text-area" id="account-bio" maxlength="2000" rows="6">${escapeHtml(profile.bio)}</textarea>
    <div class="dialog-actions"><button class="Button" type="button" data-cancel-profile>Cancel</button><button class="Button Button--primary">Save Profile</button></div>
  </form>`);
  document.querySelector("[data-cancel-profile]").addEventListener("click", closeDialog);
  document.querySelector("#account-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.account = await request("/api/account/profile", {
      method: "PUT",
      body: JSON.stringify({
        full_name: document.querySelector("#account-full-name").value,
        display_name: document.querySelector("#account-display-name").value,
        pronouns: document.querySelector("#account-pronouns").value,
        bio: document.querySelector("#account-bio").value,
        timezone: profile.timezone,
        language: profile.language,
      }),
    });
    state.user = state.account.user;
    document.querySelector("#nav-avatar").textContent = initials(state.user.name);
    closeDialog();
    renderAccount();
    showFlash("Profile updated");
  });
}

function notificationSelect(category, value) {
  const options = [["immediately", "Notify me right away"], ["daily", "Daily summary"], ["weekly", "Weekly summary"], ["off", "Notifications off"]];
  return `<select class="ic-Input notification-select" data-notification="${category}">${options.map(([key, label]) => `<option value="${key}" ${value === key ? "selected" : ""}>${label}</option>`).join("")}</select>`;
}

function renderAccountNotifications(root) {
  root.innerHTML = `${courseHeader("Notification Settings")}<p class="muted">Choose how often Canvas sends notifications for each activity group.</p>
    <form id="notification-form"><table class="canvas-table notification-table"><thead><tr><th>Activity</th><th>Email frequency</th></tr></thead><tbody>${Object.entries(notificationLabels).map(([key, [title, description]]) => `<tr><td><strong>${title}</strong><span class="content-row-meta">${description}</span></td><td>${notificationSelect(key, state.account.notifications[key])}</td></tr>`).join("")}</tbody></table><div class="account-actions"><button class="Button Button--primary">Save Settings</button></div></form>`;
  document.querySelector("#notification-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const preferences = Object.fromEntries([...document.querySelectorAll("[data-notification]")].map((select) => [select.dataset.notification, select.value]));
    const result = await request("/api/account/notifications", { method: "PUT", body: JSON.stringify({ preferences }) });
    state.account.notifications = result.notifications;
    showFlash("Notification settings saved");
  });
}

function renderAccountFiles(root) {
  const { files, storage } = state.account;
  const rows = files.map((file) => `<div class="content-row"><span class="content-row-icon">▱</span><div><a class="content-row-title" href="${file.download_url}" target="_blank">${escapeHtml(file.name)}</a><span class="content-row-meta">${humanFileSize(file.size_bytes)} · ${formatDate(file.created_at)}</span></div><button class="Button Button--small" data-delete-personal-file="${file.id}">Delete</button></div>`).join("");
  root.innerHTML = `${courseHeader("My Files", '<button class="Button Button--primary" data-upload-personal-file>Upload</button>')}<div class="storage-meter"><div><strong>${humanFileSize(storage.used_bytes)}</strong> of ${humanFileSize(storage.quota_bytes)} used</div><progress max="${storage.quota_bytes}" value="${storage.used_bytes}"></progress></div><div class="item-group">${rows || '<div class="empty-state"><p>No personal files.</p></div>'}</div><input class="hidden" id="personal-file-input" type="file" accept=".csv,.doc,.docx,.jpeg,.jpg,.pdf,.png,.ppt,.pptx,.txt,.xlsx,.zip">`;
  const input = document.querySelector("#personal-file-input");
  document.querySelector("[data-upload-personal-file]").addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    if (!input.files[0]) return;
    const form = new FormData();
    form.append("upload", input.files[0]);
    await request("/api/account/files", { method: "POST", body: form });
    showFlash("File uploaded");
    await loadAccount("files");
  });
  document.querySelectorAll("[data-delete-personal-file]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm("Delete this file?")) return;
    await request(`/api/account/files/${button.dataset.deletePersonalFile}`, { method: "DELETE" });
    showFlash("File deleted");
    await loadAccount("files");
  }));
}

function renderAccountSettings(root) {
  const { user, profile } = state.account;
  root.innerHTML = `${courseHeader("Settings")}
    <section class="account-panel"><h2>Account Settings</h2><form id="account-settings-form" class="settings-form"><label class="ic-Label" for="settings-email">Email</label><input class="ic-Input" id="settings-email" value="${escapeHtml(user.email)}" disabled><span class="content-row-meta">Your login email is managed by the institution.</span><div class="form-grid"><div><label class="ic-Label" for="settings-timezone">Time Zone</label><select class="ic-Input" id="settings-timezone"><option value="Asia/Ho_Chi_Minh" ${profile.timezone === "Asia/Ho_Chi_Minh" ? "selected" : ""}>Hanoi (GMT+7)</option><option value="UTC" ${profile.timezone === "UTC" ? "selected" : ""}>UTC</option></select></div><div><label class="ic-Label" for="settings-language">Language</label><select class="ic-Input" id="settings-language"><option value="en" ${profile.language === "en" ? "selected" : ""}>English</option><option value="vi" ${profile.language === "vi" ? "selected" : ""}>Tiếng Việt</option></select></div></div><div class="account-actions"><button class="Button Button--primary">Update Settings</button></div></form></section>
    <section class="account-panel"><h2>Change Password</h2><form id="password-form" class="settings-form"><label class="ic-Label" for="current-password">Current Password</label><input class="ic-Input" id="current-password" type="password" autocomplete="current-password" required><label class="ic-Label" for="new-password">New Password</label><input class="ic-Input" id="new-password" type="password" minlength="8" autocomplete="new-password" required><label class="ic-Label" for="confirm-password">Confirm New Password</label><input class="ic-Input" id="confirm-password" type="password" minlength="8" autocomplete="new-password" required><p class="form-error" id="password-error"></p><div class="account-actions"><button class="Button">Change Password</button></div></form></section>`;
  document.querySelector("#account-settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.account = await request("/api/account/profile", { method: "PUT", body: JSON.stringify({ full_name: user.name, display_name: profile.display_name, pronouns: profile.pronouns, bio: profile.bio, timezone: document.querySelector("#settings-timezone").value, language: document.querySelector("#settings-language").value }) });
    window.CanvasI18n?.setLocale(state.account.profile.language);
    showFlash("Account settings updated");
    renderAccount();
  });
  document.querySelector("#password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const currentPassword = document.querySelector("#current-password").value;
    const newPassword = document.querySelector("#new-password").value;
    const confirmation = document.querySelector("#confirm-password").value;
    const error = document.querySelector("#password-error");
    if (newPassword !== confirmation) { error.textContent = "New passwords do not match."; return; }
    try {
      await request("/api/account/password", { method: "PUT", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      event.target.reset();
      error.textContent = "";
      showFlash("Password changed. Other sessions were signed out.");
    } catch (err) { error.textContent = err.message; }
  });
}

function openCoursesTray() {
  navigationTray.innerHTML = `
    <div class="tray-header"><h2>Courses</h2><button class="close-button" aria-label="Close">×</button></div>
    <ul class="tray-list">
      ${state.dashboard.courses.map((course) => `<li><button data-tray-course="${course.id}">${escapeHtml(course.name)}</button></li>`).join("")}
      <li><button data-all-courses>All Courses</button></li>
    </ul>`;
  navigationTray.classList.remove("hidden");
  navigationTray.querySelector(".close-button").addEventListener("click", closeTray);
  navigationTray.querySelectorAll("[data-tray-course]").forEach((button) => {
    button.addEventListener("click", () => loadCourse(Number(button.dataset.trayCourse), "home"));
  });
  navigationTray.querySelector("[data-all-courses]").addEventListener("click", renderAllCourses);
}

function openHelpTray() {
  navigationTray.innerHTML = `
    <div class="tray-header"><h2>Help</h2><button class="close-button" aria-label="Close">×</button></div>
    <ul class="tray-list"><li><button>Search the Canvas Guides</button></li><li><button>Report a Problem</button></li><li><button>Ask Your Instructor a Question</button></li><li><button>Submit a Feature Idea</button></li></ul>`;
  navigationTray.classList.remove("hidden");
  navigationTray.querySelector(".close-button").addEventListener("click", closeTray);
}

function openCourseCreator() {
  openDialog("Start a New Course", '<form id="course-creator"><label class="ic-Label" for="new-course-name">Course Name</label><input class="ic-Input" id="new-course-name" required><label class="ic-Label" for="new-course-code">Course Code</label><input class="ic-Input" id="new-course-code" required><label class="ic-Label" for="new-course-term">Term</label><input class="ic-Input" id="new-course-term" value="2026–2027" required><label class="ic-Label" for="new-course-color">Color</label><input class="ic-Input color-input" id="new-course-color" type="color" value="#0374b5"><div class="dialog-actions"><button class="Button" type="button" data-cancel-course>Cancel</button><button class="Button Button--primary">Create Course</button></div></form>');
  document.querySelector("[data-cancel-course]").addEventListener("click", closeDialog);
  document.querySelector("#course-creator").addEventListener("submit", async (event) => {
    event.preventDefault();
    const course = await request("/api/courses", {
      method: "POST",
      body: JSON.stringify({
        user_id: state.user.id,
        name: document.querySelector("#new-course-name").value,
        code: document.querySelector("#new-course-code").value,
        term: document.querySelector("#new-course-term").value,
        color: document.querySelector("#new-course-color").value,
        published: true,
      }),
    });
    closeDialog();
    showFlash("Course created");
    await loadDashboard();
    openCourseActivityEditor(course.id);
  });
}

function openGlobalSearch() {
  openDialog("Search", '<form id="global-search-form"><label class="ic-Label" for="global-search-query">Search courses and content</label><input class="ic-Input" id="global-search-query" minlength="2" required><div class="dialog-actions"><button class="Button Button--primary">Search</button></div></form><div id="global-search-results"></div>');
  document.querySelector("#global-search-form").addEventListener("submit", async (event) => { event.preventDefault(); const results = await request(`/api/search?q=${encodeURIComponent(document.querySelector("#global-search-query").value)}&user_id=${state.user.id}`); document.querySelector("#global-search-results").innerHTML = results.map((item) => `<button class="content-row search-result" data-search-course="${item.course_id}" data-search-type="${item.type}"><span class="content-row-icon">⌕</span><div><span class="content-row-title">${escapeHtml(item.title)}</span><span class="content-row-meta">${escapeHtml(item.type)}</span></div><span>›</span></button>`).join("") || '<p class="muted">No results found.</p>'; document.querySelectorAll("[data-search-course]").forEach((button) => button.addEventListener("click", () => { closeDialog(); const type = button.dataset.searchType; const tabMap = { assignment: "assignments", announcement: "announcements", discussion: "discussions", page: "pages", outcome: "outcomes", quiz: "quizzes", syllabus: "syllabus" }; loadCourse(Number(button.dataset.searchCourse), tabMap[type] || "home"); })); });
}

function renderAllCourses() {
  closeTray();
  setActiveNav("courses");
  recordHistory("All Courses", renderAllCourses);
  mainContent.innerHTML = `
    <div class="content-header"><h1>All Courses</h1></div>
    <h2 style="font-size:20px;font-weight:400">Courses</h2>
    <table class="canvas-table">
      <thead><tr><th>Favorite</th><th>Course</th><th>Nickname</th><th>Term</th><th>Enrolled as</th></tr></thead>
      <tbody>${state.dashboard.courses.map((course) => `<tr><td><span class="star">★</span></td><td><a href="#" data-open-course="${course.id}">${escapeHtml(course.name)}</a></td><td></td><td>${escapeHtml(course.term)}</td><td>${course.enrollment_role === "student" ? "Student" : "Teacher"}</td></tr>`).join("")}</tbody>
    </table>`;
  bindCourseLinks();
}

const courseTabs = [
  ["home", "Home"], ["announcements", "Announcements"], ["assignments", "Assignments"],
  ["discussions", "Discussions"], ["grades", "Grades"], ["people", "People"],
  ["pages", "Pages"], ["files", "Files"], ["syllabus", "Syllabus"],
  ["outcomes", "Outcomes"], ["quizzes", "Quizzes"], ["modules", "Modules"],
  ["planner", "Planner"], ["analytics", "Analytics"],
  ["pacewise", "PaceWise"],
];

async function loadCourse(courseId, tab = "home") {
  closeTray();
  showLoading();
  setActiveNav("courses");
  try {
    state.currentCourse = await request(`/api/courses/${courseId}?user_id=${state.user.id}`);
    state.courseTab = tab;
    recordHistory(`${state.currentCourse.course.code}: ${tabName(tab)}`, () => loadCourse(courseId, tab));
    renderCourseShell();
  } catch (error) {
    showError(error);
  }
}

function tabName(tab) {
  return courseTabs.find(([key]) => key === tab)?.[1] || "Home";
}

function renderCourseShell() {
  const { course } = state.currentCourse;
  const tabs = [...courseTabs];
  if (state.user.role === "instructor") tabs.push(["settings", "Settings"]);
  mainContent.innerHTML = `
    <div class="breadcrumbs"><a href="#" data-dashboard-link>Dashboard</a> &gt; ${escapeHtml(course.code)} &gt; ${tabName(state.courseTab)}</div>
    <div class="course-shell">
      <nav class="course-nav" aria-label="Course Navigation"><ul>${tabs.map(([key, label]) => `<li><button class="${state.courseTab === key ? "active" : ""}" data-course-tab="${key}">${label}</button></li>`).join("")}</ul></nav>
      <section class="course-main" id="course-main"></section>
    </div>`;
  document.querySelector("[data-dashboard-link]").addEventListener("click", (event) => { event.preventDefault(); loadDashboard(); });
  document.querySelectorAll("[data-course-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.courseTab = button.dataset.courseTab;
      recordHistory(`${course.code}: ${tabName(state.courseTab)}`, () => loadCourse(course.id, state.courseTab));
      renderCourseShell();
    });
  });
  renderCourseTab();
}

function courseHeader(title, actions = "") {
  return `<div class="content-header"><h1>${escapeHtml(title)}</h1><div class="content-header-actions">${actions}</div></div>`;
}

function submissionTimingText(item) {
  if (!item.submitted_at || !item.due_at) return "";
  const differenceMinutes = Math.round((new Date(item.due_at).getTime() - new Date(item.submitted_at).getTime()) / 60000);
  if (Math.abs(differenceMinutes) < 1) return "Submitted on time";
  return differenceMinutes > 0
    ? `Submitted ${differenceMinutes} min early`
    : `Submitted ${Math.abs(differenceMinutes)} min late`;
}

function assignmentRows(assignments, allowSubmit = false) {
  if (!assignments.length) return '<div class="empty-state"><p>No assignments found.</p></div>';
  return assignments.map((item) => {
    const submissionTiming = submissionTimingText(item);
    return `
    <div class="content-row">
      <span class="content-row-icon">▤</span>
      <div><span class="content-row-title">${escapeHtml(item.title)}</span><span class="content-row-meta">${escapeHtml(item.assignment_group?.name || "Assignments")} · Due ${formatDate(item.due_at)} · ${item.points_possible} pts${item.lock_at ? ` · Locks ${formatDate(item.lock_at)}` : ""}${item.override_target ? ` · ${escapeHtml(item.override_target)} override` : ""}${submissionTiming ? ` · ${escapeHtml(submissionTiming)}` : ""}</span></div>
      <div class="row-actions">${state.user.role === "instructor" ? `<button class="Button Button--small" data-assignment-override="${item.id}">Override</button><button class="Button Button--small" data-assignment-edit="${item.id}">Edit</button><button class="Button Button--small" data-assignment-delete="${item.id}">Delete</button>` : allowSubmit ? `<button class="Button" data-submit="${item.id}">${["submitted", "late"].includes(item.state) ? "Resubmit Assignment" : "Submit Assignment"}</button>` : `<span class="published-icon">✓</span>`}</div>
    </div>`;
  }).join("");
}

function renderCourseTab() {
  const root = document.querySelector("#course-main");
  const data = state.currentCourse;
  const { course, assignments, resources, people, gradebook } = data;
  const tab = state.courseTab;

  if (tab === "home") {
    root.innerHTML = `${courseHeader(course.name)}<div class="course-home-grid"><div class="course-home"><h2>${escapeHtml(course.name)}</h2><p>Welcome to ${escapeHtml(course.name)}.</p><div class="item-group"><div class="item-group-header"><h3>Coming Up</h3></div>${assignmentRows(assignments.slice(0, 3))}</div></div><aside class="course-options">${state.user.role === "instructor" ? '<button class="Button">Course Status: Published</button><button class="Button">Import Existing Content</button><button class="Button">Choose Home Page</button><button class="Button">View Course Stream</button>' : '<button class="Button">View Course Calendar</button><button class="Button">View Course Notifications</button>'}<h3>To Do</h3>${assignments.slice(0, 3).map((item) => `<a href="#" data-tab-assignment>${escapeHtml(item.title)}</a><small class="content-row-meta">${formatDate(item.due_at)}</small>`).join("")}</aside></div>`;
  } else if (tab === "assignments") {
    renderAssignmentsTab(root);
  } else if (tab === "modules") {
    renderModulesTab(root);
  } else if (tab === "grades") {
    root.innerHTML = renderGrades(course, assignments, gradebook);
    bindGradebookActions();
  } else if (tab === "people") {
    root.innerHTML = `${courseHeader("People", state.user.role === "instructor" ? '<button class="Button" data-manage-sections>Sections</button><button class="Button" data-manage-groups>Groups</button><button class="Button Button--primary" data-add-person>+ People</button>' : "")}<table class="canvas-table"><thead><tr><th>Name</th><th>Login ID</th><th>Role</th><th>Last Activity</th><th></th></tr></thead><tbody>${people.map((person) => `<tr><td><div class="person"><span class="person-avatar">${initials(person.name)}</span><a href="#">${escapeHtml(person.name)}</a></div></td><td>${escapeHtml(person.email)}</td><td>${person.role === "student" ? "Student" : "Teacher"}</td><td>—</td><td>${state.user.role === "instructor" && person.id !== state.user.id ? `<button class="Button Button--small" data-remove-person="${person.id}">Remove</button>` : ""}</td></tr>`).join("")}</tbody></table>`;
    bindPeopleActions();
  } else if (tab === "files") {
    root.innerHTML = `${courseHeader("Files", state.user.role === "instructor" ? '<button class="Button Button--primary" data-upload-file>Upload</button><button class="Button" data-add-link>+ Link</button>' : "")}<div class="item-group">${resources.map((item) => `<div class="content-row"><span class="content-row-icon">▱</span><div><a class="content-row-title" href="${escapeHtml(item.source_url)}${item.source_url.startsWith("/api/files/") ? `?user_id=${state.user.id}` : ""}" target="_blank">${escapeHtml(item.title)}</a><span class="content-row-meta">${escapeHtml(item.kind)}${item.latest_version ? ` · v${item.latest_version.version} · ${item.latest_version.checksum_sha256.slice(0, 10)}…` : ""}</span></div>${state.user.role === "instructor" ? `<button class="Button Button--small" data-resource-versions="${item.id}">Versions</button><button class="Button Button--small" data-delete-resource="${item.id}">Delete</button>` : '<span class="published-icon">✓</span>'}</div>`).join("") || '<div class="empty-state"><p>No files.</p></div>'}</div>`;
    bindFileActions();
  } else if (tab === "syllabus") {
    root.innerHTML = renderCourseContentPage("syllabus") + `<div class="item-group"><div class="item-group-header"><h3>Course Summary</h3></div>${assignmentRows(assignments)}</div>`;
    bindCourseContentActions("syllabus");
  } else if (tab === "settings") {
    renderCourseSettings(root);
  } else if (tab === "pacewise") {
    renderPacewiseTab(root);
  } else if (tab === "planner") {
    renderPlannerTab(root);
  } else if (tab === "analytics") {
    renderAnalyticsTab(root);
  } else {
    root.innerHTML = renderCourseContentPage(tab);
    bindCourseContentActions(tab);
  }
}

function renderPacewiseTab(root) {
  const course = state.currentCourse.course;
  root.innerHTML = `${courseHeader("PaceWise")}<div class="empty-state"><h2>Open PaceWise</h2><p>Continue with your current course and ${escapeHtml(state.user.role)} role.</p><button class="Button Button--primary" data-launch-pacewise>Open PaceWise</button></div>`;
  document.querySelector("[data-launch-pacewise]").addEventListener("click", async () => {
    const button = document.querySelector("[data-launch-pacewise]");
    button.disabled = true;
    button.textContent = "Preparing secure launch...";
    try {
      const launch = await request(`/api/pacewise/launch/${course.id}`, { method: "POST" });
      window.location.assign(launch.launch_url);
    } catch (error) {
      button.disabled = false;
      button.textContent = "Open PaceWise";
      showFlash(error.message);
    }
  });
}

async function launchGlobalPaceWise() {
  closeTray();
  setActiveNav("pacewise");
  showLoading();
  try {
    if (!state.dashboard) {
      state.dashboard = await request(`/api/dashboard/${state.user.id}`);
    }
    const courses = state.dashboard.courses || [];
    if (!courses.length) {
      throw new Error("You need at least one course enrollment to open PaceWise.");
    }

    // This course is only the initial context. PaceWise verifies the launch and
    // expands the authenticated session to every course enrolled by this user.
    const initialCourse = courses[0];
    const launch = await request(`/api/pacewise/launch/${initialCourse.id}`, { method: "POST" });
    window.location.assign(launch.launch_url);
  } catch (error) {
    mainContent.innerHTML = `${courseHeader("PaceWise")}<div class="error-state"><h2>Could not open PaceWise</h2><p>${escapeHtml(error.message)}</p><button class="Button" data-retry-pacewise>Retry</button></div>`;
    document.querySelector("[data-retry-pacewise]")?.addEventListener("click", launchGlobalPaceWise);
  }
}

async function renderPlannerTab(root) {
  root.innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Loading planner...</p></div>';
  try {
    const [allItems, appointments] = await Promise.all([
      request("/api/planner"),
      request(`/api/courses/${state.currentCourse.course.id}/appointment-groups`),
    ]);
    const items = allItems.filter((item) => item.course_id === state.currentCourse.course.id);
    const appointmentAction = state.user.role === "instructor" ? '<button class="Button" data-new-appointment>+ Appointment group</button>' : "";
    root.innerHTML = `${courseHeader("Planner", `${appointmentAction}<button class="Button Button--primary" data-new-planner-item>+ To-do</button>`)}<div class="item-group">${items.map((item) => `<div class="content-row"><span class="content-row-icon">${item.completed ? "✓" : "○"}</span><div><span class="content-row-title">${escapeHtml(item.title)}</span><span class="content-row-meta">${item.due_at ? formatDate(item.due_at) : "No due date"}</span></div><div class="row-actions"><button class="Button Button--small" data-toggle-planner="${item.id}">${item.completed ? "Reopen" : "Complete"}</button><button class="Button Button--small" data-delete-planner="${item.id}">Delete</button></div></div>`).join("") || '<div class="empty-state"><p>No planner items for this course.</p></div>'}</div><div class="item-group"><div class="item-group-header"><h2>Appointments</h2></div>${appointments.map((item) => `<div class="content-row"><span class="content-row-icon">◷</span><div><span class="content-row-title">${escapeHtml(item.title)}</span><span class="content-row-meta">${formatDate(item.starts_at)} · ${item.slot_minutes} minute slots · ${item.participants_per_slot} per slot</span></div>${state.user.role === "student" ? `<button class="Button Button--small" data-reserve-appointment="${item.id}" data-starts-at="${item.starts_at}">Reserve first slot</button>` : ""}</div>`).join("") || '<div class="empty-state"><p>No appointment groups.</p></div>'}</div>`;
    document.querySelector("[data-new-planner-item]").addEventListener("click", () => {
      openDialog("Add to-do", '<form id="planner-editor"><label class="ic-Label" for="planner-title">Title</label><input class="ic-Input" id="planner-title" required><label class="ic-Label" for="planner-due">Due</label><input class="ic-Input" id="planner-due" type="datetime-local"><div class="dialog-actions"><button class="Button Button--primary">Add</button></div></form>');
      document.querySelector("#planner-editor").addEventListener("submit", async (event) => { event.preventDefault(); const due = document.querySelector("#planner-due").value; await request("/api/planner", { method: "POST", body: JSON.stringify({ course_id: state.currentCourse.course.id, title: document.querySelector("#planner-title").value, due_at: due ? new Date(due).toISOString() : null }) }); closeDialog(); await renderPlannerTab(root); });
    });
    document.querySelectorAll("[data-toggle-planner]").forEach((button) => button.addEventListener("click", async () => { const item = items.find((entry) => entry.id === Number(button.dataset.togglePlanner)); await request(`/api/planner/${item.id}`, { method: "PUT", body: JSON.stringify({ course_id: item.course_id, assignment_id: item.assignment_id, title: item.title, due_at: item.due_at, completed: !item.completed }) }); await renderPlannerTab(root); }));
    document.querySelectorAll("[data-delete-planner]").forEach((button) => button.addEventListener("click", async () => { await request(`/api/planner/${button.dataset.deletePlanner}`, { method: "DELETE" }); await renderPlannerTab(root); }));
    document.querySelectorAll("[data-reserve-appointment]").forEach((button) => button.addEventListener("click", async () => { await request(`/api/appointment-groups/${button.dataset.reserveAppointment}/reservations`, { method: "POST", body: JSON.stringify({ starts_at: button.dataset.startsAt }) }); showFlash("Appointment reserved"); }));
    document.querySelector("[data-new-appointment]")?.addEventListener("click", () => {
      openDialog("Create appointment group", '<form id="appointment-editor"><label class="ic-Label" for="appointment-title">Title</label><input class="ic-Input" id="appointment-title" required><div class="form-grid"><label>Starts<input class="ic-Input" id="appointment-starts" type="datetime-local" required></label><label>Ends<input class="ic-Input" id="appointment-ends" type="datetime-local" required></label><label>Slot minutes<input class="ic-Input" id="appointment-slot" type="number" min="5" value="30"></label><label>People per slot<input class="ic-Input" id="appointment-capacity" type="number" min="1" value="1"></label></div><div class="dialog-actions"><button class="Button Button--primary">Create</button></div></form>');
      document.querySelector("#appointment-editor").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/appointment-groups`, { method: "POST", body: JSON.stringify({ title: document.querySelector("#appointment-title").value, starts_at: new Date(document.querySelector("#appointment-starts").value).toISOString(), ends_at: new Date(document.querySelector("#appointment-ends").value).toISOString(), slot_minutes: Number(document.querySelector("#appointment-slot").value), participants_per_slot: Number(document.querySelector("#appointment-capacity").value) }) }); closeDialog(); await renderPlannerTab(root); });
    });
  } catch (error) { root.innerHTML = `<div class="error-state"><p>${escapeHtml(error.message)}</p></div>`; }
}

async function renderAnalyticsTab(root) {
  root.innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Loading analytics...</p></div>';
  try {
    const analytics = await request(`/api/courses/${state.currentCourse.course.id}/analytics`);
    const rows = Object.entries(analytics.by_type || {}).map(([type, count]) => `<tr><td>${escapeHtml(type)}</td><td>${count}</td></tr>`).join("");
    root.innerHTML = `${courseHeader("Course Analytics")}<div class="stat-grid"><article class="stat-card"><strong>${analytics.events}</strong><span>Events</span></article><article class="stat-card"><strong>${analytics.active_users}</strong><span>Active learners</span></article><article class="stat-card"><strong>${Math.round(analytics.duration_seconds / 60)}</strong><span>Active minutes</span></article><article class="stat-card"><strong>${analytics.submissions || 0}</strong><span>Submissions</span></article></div><table class="canvas-table"><thead><tr><th>Activity</th><th>Count</th></tr></thead><tbody>${rows || '<tr><td colspan="2">No activity recorded.</td></tr>'}</tbody></table>`;
  } catch (error) { root.innerHTML = `<div class="error-state"><p>${escapeHtml(error.message)}</p></div>`; }
}

function renderGrades(course, assignments, gradebook) {
  if (state.user.role === "student") {
    const own = gradebook.find((row) => row.user_id === state.user.id);
    return `${courseHeader("Grades for " + course.name)}<table class="canvas-table"><thead><tr><th>Name</th><th>Due</th><th>Status</th><th>Score</th><th>Out of</th></tr></thead><tbody>${assignments.map((assignment) => { const grade = own?.grades.find((item) => item.assignment_id === assignment.id); return `<tr><td><a href="#">${escapeHtml(assignment.title)}</a></td><td>${formatDate(assignment.due_at)}</td><td>${escapeHtml(assignment.state)}</td><td>${grade?.score ?? "—"}</td><td>${assignment.points_possible}</td></tr>`; }).join("")}</tbody></table>`;
  }
  return `${courseHeader("Gradebook", '<button class="Button" data-export-grades>Export CSV</button>')}<div style="overflow:auto"><table class="canvas-table"><thead><tr><th>Student Name</th>${assignments.map((assignment) => `<th><button class="grade-heading" data-speedgrader="${assignment.id}">${escapeHtml(assignment.title)}</button><span class="content-row-meta">Out of ${assignment.points_possible}</span></th>`).join("")}</tr></thead><tbody>${gradebook.map((row) => `<tr><td><a href="#">${escapeHtml(row.name)}</a></td>${row.grades.map((grade) => `<td><button class="grade-cell" data-grade-assignment="${grade.assignment_id}" data-grade-student="${row.user_id}">${grade.score ?? "—"}</button></td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

const contentKinds = {
  announcements: { kind: "announcement", title: "Announcements", singular: "Announcement", icon: "♢" },
  discussions: { kind: "discussion", title: "Discussions", singular: "Discussion", icon: "◯" },
  pages: { kind: "page", title: "Pages", singular: "Page", icon: "▧" },
  outcomes: { kind: "outcome", title: "Outcomes", singular: "Outcome", icon: "◎" },
  quizzes: { kind: "quiz", title: "Quizzes", singular: "Quiz", icon: "✓" },
  syllabus: { kind: "syllabus", title: "Syllabus", singular: "Syllabus", icon: "▤" },
};

function renderCourseContentPage(tab) {
  const config = contentKinds[tab];
  if (!config) return `${courseHeader(tabName(tab))}<div class="empty-state"><p>No content is available.</p></div>`;
  const items = state.currentCourse.content[config.kind] || [];
  const createButton = state.user.role === "instructor"
    ? `<button class="Button Button--primary" data-content-create>+ ${config.singular}</button>`
    : "";
  const rows = items.map((item) => `
    <div class="content-row content-row-expanded">
      <span class="content-row-icon">${config.icon}</span>
      <button class="content-title-button" data-content-view="${item.id}">
        <span class="content-row-title">${escapeHtml(item.title)}</span>
        <span class="content-row-meta">${item.due_at ? `Due ${formatDate(item.due_at)} · ` : ""}${item.points_possible != null ? `${item.points_possible} pts · ` : ""}${formatDate(item.created_at)}</span>
      </button>
      <div class="row-actions">
        <span class="published-icon" title="Published">${item.published ? "✓" : "○"}</span>
        ${state.user.role === "instructor" ? `<button class="Button Button--small" data-content-edit="${item.id}">Edit</button><button class="Button Button--small" data-content-delete="${item.id}">Delete</button>` : ""}
      </div>
    </div>`).join("");
  return `${courseHeader(config.title, createButton)}<div class="item-group"><div class="item-group-header"><h2>${config.title}</h2></div>${rows || `<div class="empty-state"><p>No ${config.title.toLowerCase()} are available.</p></div>`}</div>`;
}

function bindCourseContentActions(tab) {
  const config = contentKinds[tab];
  if (!config) return;
  const items = state.currentCourse.content[config.kind] || [];
  document.querySelector("[data-content-create]")?.addEventListener("click", () => openContentEditor(tab));
  document.querySelectorAll("[data-content-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items.find((entry) => entry.id === Number(button.dataset.contentView));
      if (tab === "discussions") return openDiscussion(item);
      if (tab === "quizzes") return openQuiz(item);
      if (tab === "outcomes") return openOutcome(item);
      openDialog(item.title, `<div class="canvas-content-body">${escapeHtml(item.body).replaceAll("\n", "<br>")}</div>${item.due_at ? `<p class="muted">Due ${formatDate(item.due_at)}</p>` : ""}`);
    });
  });
  document.querySelectorAll("[data-content-edit]").forEach((button) => {
    button.addEventListener("click", () => openContentEditor(tab, items.find((entry) => entry.id === Number(button.dataset.contentEdit))));
  });
  document.querySelectorAll("[data-content-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = items.find((entry) => entry.id === Number(button.dataset.contentDelete));
      if (!window.confirm(`Delete "${item.title}"?`)) return;
      await request(`/api/courses/${state.currentCourse.course.id}/content/${config.kind}/${item.id}?user_id=${state.user.id}`, { method: "DELETE" });
      showFlash(`${config.singular} deleted`);
      await loadCourse(state.currentCourse.course.id, tab);
    });
  });
}

function inputDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function openContentEditor(tab, item = null) {
  const config = contentKinds[tab];
  openDialog(`${item ? "Edit" : "New"} ${config.singular}`, `
    <form id="content-editor">
      <label class="ic-Label" for="content-title">Title</label>
      <input class="ic-Input" id="content-title" value="${escapeHtml(item?.title || "")}" required>
      <label class="ic-Label" for="content-body">Content</label>
      <textarea class="ic-Input text-area" id="content-body" rows="7">${escapeHtml(item?.body || "")}</textarea>
      ${["quiz", "outcome"].includes(config.kind) ? `<label class="ic-Label" for="content-points">Points</label><input class="ic-Input" id="content-points" type="number" min="0" step="0.5" value="${item?.points_possible ?? ""}">` : ""}
      ${config.kind === "quiz" ? `<label class="ic-Label" for="content-due">Due</label><input class="ic-Input" id="content-due" type="datetime-local" value="${inputDateTime(item?.due_at)}">` : ""}
      <label class="remember"><input id="content-published" type="checkbox" ${item?.published === false ? "" : "checked"}> Published</label>
      <div class="dialog-actions"><button class="Button" type="button" data-cancel-editor>Cancel</button><button class="Button Button--primary" type="submit">Save</button></div>
    </form>`);
  document.querySelector("[data-cancel-editor]").addEventListener("click", closeDialog);
  document.querySelector("#content-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      user_id: state.user.id,
      title: document.querySelector("#content-title").value,
      body: document.querySelector("#content-body").value,
      points_possible: document.querySelector("#content-points")?.value ? Number(document.querySelector("#content-points").value) : null,
      due_at: document.querySelector("#content-due")?.value ? new Date(document.querySelector("#content-due").value).toISOString() : null,
      published: document.querySelector("#content-published").checked,
    };
    const url = `/api/courses/${state.currentCourse.course.id}/content/${config.kind}${item ? `/${item.id}` : ""}`;
    await request(url, { method: item ? "PUT" : "POST", body: JSON.stringify(payload) });
    closeDialog();
    showFlash(`${config.singular} saved`);
    await loadCourse(state.currentCourse.course.id, tab);
  });
}

async function openDiscussion(item) {
  const replies = await request(`/api/discussions/${item.id}/replies?user_id=${state.user.id}`);
  openDialog(item.title, `<div class="canvas-content-body discussion-prompt">${escapeHtml(item.body).replaceAll("\n", "<br>")}</div><div class="discussion-thread">${replies.map((reply) => `<article class="discussion-reply ${reply.parent_id ? "nested" : ""}"><span class="person-avatar">${initials(reply.author.name)}</span><div><strong>${escapeHtml(reply.author.name)}</strong><time>${formatDate(reply.created_at)}</time><p>${escapeHtml(reply.body)}</p><div class="reply-actions"><button class="link-button" data-reply-to="${reply.id}">Reply</button><button class="link-button" data-like-reply="${reply.id}">Like (${reply.likes})</button></div></div></article>`).join("") || '<p class="muted">No replies yet.</p>'}</div><form id="discussion-reply-form"><label class="ic-Label" for="discussion-reply-body">Reply</label><textarea class="ic-Input text-area" id="discussion-reply-body" required></textarea><input type="hidden" id="discussion-parent"><div class="dialog-actions"><span class="muted" id="reply-context"></span><button class="Button Button--primary">Post Reply</button></div></form>`);
  document.querySelectorAll("[data-reply-to]").forEach((button) => button.addEventListener("click", () => { document.querySelector("#discussion-parent").value = button.dataset.replyTo; document.querySelector("#reply-context").textContent = "Replying to a message"; document.querySelector("#discussion-reply-body").focus(); }));
  document.querySelectorAll("[data-like-reply]").forEach((button) => button.addEventListener("click", async () => { await request(`/api/discussions/replies/${button.dataset.likeReply}/like?user_id=${state.user.id}`, { method: "POST" }); await openDiscussion(item); }));
  document.querySelector("#discussion-reply-form").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/discussions/${item.id}/replies`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, body: document.querySelector("#discussion-reply-body").value, parent_id: Number(document.querySelector("#discussion-parent").value) || null }) }); await openDiscussion(item); });
}

async function openQuiz(item) {
  const questions = await request(`/api/quizzes/${item.id}/questions?user_id=${state.user.id}`);
  if (state.user.role === "instructor") {
    openDialog(item.title, `<p>${escapeHtml(item.body)}</p><div class="quiz-questions">${questions.map((question, index) => `<article class="quiz-question"><strong>Question ${index + 1}</strong><p>${escapeHtml(question.prompt)}</p><small>${question.points} pts · Correct: ${escapeHtml(question.correct_answer)}</small><button class="Button Button--small" data-delete-question="${question.id}">Delete</button></article>`).join("") || '<p class="muted">No questions.</p>'}</div><button class="Button Button--primary" data-new-question>+ New Question</button>`);
    document.querySelector("[data-new-question]").addEventListener("click", () => openQuestionEditor(item));
    document.querySelectorAll("[data-delete-question]").forEach((button) => button.addEventListener("click", async () => { await request(`/api/quizzes/${item.id}/questions/${button.dataset.deleteQuestion}?user_id=${state.user.id}`, { method: "DELETE" }); await openQuiz(item); }));
    return;
  }
  openDialog(item.title, `<form id="quiz-attempt"><p>${escapeHtml(item.body)}</p>${questions.map((question, index) => `<fieldset class="quiz-question"><legend>${index + 1}. ${escapeHtml(question.prompt)} <small>${question.points} pts</small></legend>${question.options.map((option) => `<label><input type="radio" name="question-${question.id}" value="${escapeHtml(option)}" required> ${escapeHtml(option)}</label>`).join("")}</fieldset>`).join("")}<div class="dialog-actions"><button class="Button Button--primary">Submit Quiz</button></div></form>`);
  document.querySelector("#quiz-attempt").addEventListener("submit", async (event) => { event.preventDefault(); const answers = {}; questions.forEach((question) => { answers[String(question.id)] = new FormData(event.target).get(`question-${question.id}`); }); const result = await request(`/api/quizzes/${item.id}/attempts`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, answers }) }); openDialog("Quiz Results", `<div class="quiz-result"><strong>${result.score} / ${result.points_possible}</strong><p>Your attempt has been graded.</p></div>`); });
}

function openQuestionEditor(quiz) {
  openDialog("New Question", '<form id="question-editor"><label class="ic-Label" for="question-prompt">Question</label><textarea class="ic-Input text-area" id="question-prompt" required></textarea><label class="ic-Label" for="question-options">Options (one per line)</label><textarea class="ic-Input text-area" id="question-options" required></textarea><label class="ic-Label" for="question-answer">Correct Answer</label><input class="ic-Input" id="question-answer" required><label class="ic-Label" for="question-points">Points</label><input class="ic-Input" id="question-points" type="number" min="0" step="0.5" value="1" required><div class="dialog-actions"><button class="Button Button--primary">Create Question</button></div></form>');
  document.querySelector("#question-editor").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/quizzes/${quiz.id}/questions`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, prompt: document.querySelector("#question-prompt").value, options: document.querySelector("#question-options").value.split("\n").map((value) => value.trim()).filter(Boolean), correct_answer: document.querySelector("#question-answer").value.trim(), points: Number(document.querySelector("#question-points").value) }) }); await openQuiz(quiz); });
}

async function openOutcome(item) {
  const mastery = await request(`/api/courses/${state.currentCourse.course.id}/mastery?user_id=${state.user.id}`);
  const result = mastery.find((entry) => entry.outcome_id === item.id);
  const alignment = state.user.role === "instructor" ? `<form id="outcome-align"><label class="ic-Label" for="outcome-assignment">Align an assignment</label><select class="ic-Input" id="outcome-assignment">${state.currentCourse.assignments.map((assignment) => `<option value="${assignment.id}">${escapeHtml(assignment.title)}</option>`).join("")}</select><button class="Button Button--primary">Align</button></form>` : "";
  openDialog(item.title, `<p>${escapeHtml(item.body)}</p><div class="mastery-card"><strong>${result?.mastery == null ? "Not yet assessed" : `${result.mastery}% mastery`}</strong><span>${result?.aligned_assignments || 0} aligned assignments</span></div>${alignment}`);
  document.querySelector("#outcome-align")?.addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/outcomes/${item.id}/alignments`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, assignment_id: Number(document.querySelector("#outcome-assignment").value) }) }); showFlash("Outcome aligned"); await openOutcome(item); });
}

async function renderAssignmentsTab(root) {
  root.innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Loading assignments...</p></div>';
  try {
    [state.assignmentGroups, state.courseGroupCategories] = await Promise.all([
      request(`/api/courses/${state.currentCourse.course.id}/assignment-groups`),
      request(`/api/courses/${state.currentCourse.course.id}/groups`),
    ]);
    const actions = state.user.role === "instructor"
      ? '<button class="Button" data-new-rubric>+ Rubric</button><button class="Button" data-new-assignment-group>+ Group</button><button class="Button Button--primary" data-new-assignment>+ Assignment</button>'
      : "";
    const groups = state.assignmentGroups.map((group) => `<span class="pill">${escapeHtml(group.name)} · ${group.group_weight}%${group.drop_lowest ? ` · drop ${group.drop_lowest} lowest` : ""}</span>`).join(" ");
    root.innerHTML = `${courseHeader("Assignments", actions)}${groups ? `<div class="notice">${groups}</div>` : ""}<div class="item-group"><div class="item-group-header"><h2>Assignments</h2><span>⋮</span></div>${assignmentRows(state.currentCourse.assignments, state.user.role === "student")}</div>`;
    bindSubmitButtons();
    bindAssignmentActions();
  } catch (error) {
    root.innerHTML = `<div class="error-state"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function openAssignmentGroupEditor() {
  openDialog("Add Assignment Group", '<form id="assignment-group-editor"><label class="ic-Label" for="assignment-group-name">Name</label><input class="ic-Input" id="assignment-group-name" required><div class="form-grid"><label>Weight %<input class="ic-Input" id="assignment-group-weight" type="number" min="0" max="100" value="0"></label><label>Drop lowest<input class="ic-Input" id="assignment-group-drop" type="number" min="0" value="0"></label></div><div class="dialog-actions"><button class="Button Button--primary">Create Group</button></div></form>');
  document.querySelector("#assignment-group-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    await request(`/api/courses/${state.currentCourse.course.id}/assignment-groups`, {
      method: "POST",
      body: JSON.stringify({
        name: document.querySelector("#assignment-group-name").value,
        group_weight: Number(document.querySelector("#assignment-group-weight").value),
        drop_lowest: Number(document.querySelector("#assignment-group-drop").value),
      }),
    });
    closeDialog();
    await renderAssignmentsTab(document.querySelector("#course-main"));
  });
}

function openRubricEditor() {
  const assignmentOptions = state.currentCourse.assignments.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  openDialog("Create and attach rubric", `<form id="rubric-editor"><label class="ic-Label" for="rubric-title">Rubric name</label><input class="ic-Input" id="rubric-title" value="Learning evidence rubric" required><label class="ic-Label" for="rubric-assignment">Assignment</label><select class="ic-Input" id="rubric-assignment">${assignmentOptions}</select><fieldset class="canvas-fieldset"><legend>Criteria</legend><div class="form-grid"><label>Criterion 1<input class="ic-Input" id="rubric-c1" value="Conceptual understanding" required></label><label>Points<input class="ic-Input" id="rubric-p1" type="number" min="1" value="5" required></label><label>Criterion 2<input class="ic-Input" id="rubric-c2" value="Reasoning and process" required></label><label>Points<input class="ic-Input" id="rubric-p2" type="number" min="1" value="5" required></label></div></fieldset><div class="dialog-actions"><button class="Button Button--primary">Create and attach</button></div></form>`);
  document.querySelector("#rubric-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const criterion = (nameId, pointsId) => { const points = Number(document.querySelector(pointsId).value); return { description: document.querySelector(nameId).value, points, ratings: [{ description: "Meets", points }, { description: "Developing", points: Math.round(points * 0.6 * 10) / 10 }, { description: "Missing", points: 0 }] }; };
    const rubric = await request(`/api/courses/${state.currentCourse.course.id}/rubrics`, { method: "POST", body: JSON.stringify({ title: document.querySelector("#rubric-title").value, criteria: [criterion("#rubric-c1", "#rubric-p1"), criterion("#rubric-c2", "#rubric-p2")] }) });
    await request(`/api/assignments/${document.querySelector("#rubric-assignment").value}/rubric/${rubric.id}`, { method: "PUT", body: "{}" });
    closeDialog();
    showFlash("Rubric attached");
    await loadCourse(state.currentCourse.course.id, "assignments");
  });
}

async function openAssignmentOverrideEditor(assignment) {
  const [sections, groupCategories] = await Promise.all([
    request(`/api/courses/${state.currentCourse.course.id}/sections`),
    request(`/api/courses/${state.currentCourse.course.id}/groups`),
  ]);
  const options = [
    ...state.currentCourse.people.filter((person) => person.role === "student").map((person) => `<option value="student:${person.id}">Student · ${escapeHtml(person.name)}</option>`),
    ...sections.map((section) => `<option value="section:${section.id}">Section · ${escapeHtml(section.name)}</option>`),
    ...groupCategories.flatMap((category) => category.groups.map((group) => `<option value="group:${group.id}">Group · ${escapeHtml(group.name)}</option>`)),
  ].join("");
  openDialog(`Deadline override: ${assignment.title}`, `<form id="assignment-override-editor"><label class="ic-Label" for="override-target">Applies to</label><select class="ic-Input" id="override-target">${options}</select><label class="ic-Label" for="override-title">Title</label><input class="ic-Input" id="override-title" value="Extended deadline" required><div class="form-grid"><label>Due<input class="ic-Input" id="override-due" type="datetime-local" value="${inputDateTime(assignment.due_at)}"></label><label>Available from<input class="ic-Input" id="override-unlock" type="datetime-local" value="${inputDateTime(assignment.unlock_at || assignment.due_at)}"></label><label>Locks<input class="ic-Input" id="override-lock" type="datetime-local" value="${inputDateTime(assignment.lock_at || assignment.due_at)}"></label></div><div class="dialog-actions"><button class="Button Button--primary">Save Override</button></div></form>`);
  document.querySelector("#assignment-override-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const [targetType, targetId] = document.querySelector("#override-target").value.split(":");
    const toIso = (id) => document.querySelector(id).value ? new Date(document.querySelector(id).value).toISOString() : null;
    await request(`/api/assignments/${assignment.id}/overrides`, { method: "POST", body: JSON.stringify({ title: document.querySelector("#override-title").value, target_type: targetType, target_id: Number(targetId), due_at: toIso("#override-due"), unlock_at: toIso("#override-unlock"), lock_at: toIso("#override-lock") }) });
    closeDialog();
    showFlash("Deadline override saved");
  });
}

function assignmentPayload(item = null) {
  const groups = (state.assignmentGroups || []).map((group) => `<option value="${group.id}" ${item?.assignment_group?.id === group.id ? "selected" : ""}>${escapeHtml(group.name)} (${group.group_weight}%)</option>`).join("");
  const groupCategories = (state.courseGroupCategories || []).map((category) => `<option value="${category.id}" ${item?.group_category_id === category.id ? "selected" : ""}>${escapeHtml(category.name)}</option>`).join("");
  return `
    <form id="assignment-editor">
      <label class="ic-Label" for="assignment-title">Assignment Name</label>
      <input class="ic-Input" id="assignment-title" value="${escapeHtml(item?.title || "")}" required>
      <label class="ic-Label" for="assignment-description">Description</label>
      <textarea class="ic-Input text-area" id="assignment-description" rows="6">${escapeHtml(item?.description || "")}</textarea>
      <div class="form-grid">
        <div><label class="ic-Label" for="assignment-points">Points</label><input class="ic-Input" id="assignment-points" type="number" min="0" step="0.5" value="${item?.points_possible ?? 10}" required></div>
        <div><label class="ic-Label" for="assignment-due">Due</label><input class="ic-Input" id="assignment-due" type="datetime-local" value="${inputDateTime(item?.due_at || new Date())}" required></div>
        <div><label class="ic-Label" for="assignment-unlock">Available from</label><input class="ic-Input" id="assignment-unlock" type="datetime-local" value="${inputDateTime(item?.unlock_at || new Date())}"></div>
        <div><label class="ic-Label" for="assignment-lock">Locks</label><input class="ic-Input" id="assignment-lock" type="datetime-local" value="${inputDateTime(item?.lock_at || item?.due_at || new Date())}"></div>
        <div><label class="ic-Label" for="assignment-group">Assignment group</label><select class="ic-Input" id="assignment-group"><option value="">None</option>${groups}</select></div>
        <div><label class="ic-Label" for="assignment-grading-type">Grading type</label><select class="ic-Input" id="assignment-grading-type"><option value="points">Points</option><option value="percent">Percentage</option><option value="pass_fail">Complete/Incomplete</option></select></div>
        <div><label class="ic-Label" for="assignment-group-category">Group assignment</label><select class="ic-Input" id="assignment-group-category"><option value="">Individual</option>${groupCategories}</select></div>
      </div>
      <fieldset class="canvas-fieldset"><legend>Submission Types</legend>
        <label><input type="checkbox" name="submission-type" value="online_text_entry" ${(item?.submission_types || ["online_text_entry"]).includes("online_text_entry") ? "checked" : ""}> Text Entry</label>
        <label><input type="checkbox" name="submission-type" value="online_url" ${(item?.submission_types || []).includes("online_url") ? "checked" : ""}> Website URL</label>
        <label><input type="checkbox" name="submission-type" value="online_upload" ${(item?.submission_types || []).includes("online_upload") ? "checked" : ""}> File Upload</label>
      </fieldset>
      <label class="remember"><input id="assignment-peer-review" type="checkbox" ${item?.peer_reviews ? "checked" : ""}> Require peer reviews</label>
      <label class="remember"><input id="assignment-published" type="checkbox" ${item?.published === false ? "" : "checked"}> Published</label>
      <div class="dialog-actions"><button class="Button" type="button" data-cancel-assignment>Cancel</button><button class="Button Button--primary" type="submit">Save</button></div>
    </form>`;
}

function openAssignmentEditor(item = null) {
  openDialog(item ? "Edit Assignment" : "Add Assignment", assignmentPayload(item));
  document.querySelector("[data-cancel-assignment]").addEventListener("click", closeDialog);
  document.querySelector("#assignment-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submissionTypes = [...document.querySelectorAll('[name="submission-type"]:checked')].map((input) => input.value);
    if (!submissionTypes.length) return showFlash("Select at least one submission type");
    const payload = {
      user_id: state.user.id,
      title: document.querySelector("#assignment-title").value,
      description: document.querySelector("#assignment-description").value,
      due_at: new Date(document.querySelector("#assignment-due").value).toISOString(),
      points_possible: Number(document.querySelector("#assignment-points").value),
      submission_types: submissionTypes,
      published: document.querySelector("#assignment-published").checked,
    };
    const base = `/api/courses/${state.currentCourse.course.id}/assignments`;
    const saved = await request(item ? `${base}/${item.id}` : base, { method: item ? "PUT" : "POST", body: JSON.stringify(payload) });
    const optionalDate = (selector) => document.querySelector(selector).value ? new Date(document.querySelector(selector).value).toISOString() : null;
    await request(`/api/assignments/${saved.id}/policy`, {
      method: "PUT",
      body: JSON.stringify({
        assignment_group_id: Number(document.querySelector("#assignment-group").value) || null,
        unlock_at: optionalDate("#assignment-unlock"),
        lock_at: optionalDate("#assignment-lock"),
        grading_type: document.querySelector("#assignment-grading-type").value,
        peer_reviews: document.querySelector("#assignment-peer-review").checked,
        group_category_id: Number(document.querySelector("#assignment-group-category").value) || null,
      }),
    });
    closeDialog();
    showFlash("Assignment saved");
    await loadCourse(state.currentCourse.course.id, "assignments");
  });
}

function bindAssignmentActions() {
  document.querySelector("[data-new-assignment]")?.addEventListener("click", () => openAssignmentEditor());
  document.querySelector("[data-new-rubric]")?.addEventListener("click", openRubricEditor);
  document.querySelector("[data-new-assignment-group]")?.addEventListener("click", openAssignmentGroupEditor);
  document.querySelectorAll("[data-assignment-override]").forEach((button) => button.addEventListener("click", () => {
    openAssignmentOverrideEditor(state.currentCourse.assignments.find((item) => item.id === Number(button.dataset.assignmentOverride)));
  }));
  document.querySelectorAll("[data-assignment-edit]").forEach((button) => button.addEventListener("click", () => {
    openAssignmentEditor(state.currentCourse.assignments.find((item) => item.id === Number(button.dataset.assignmentEdit)));
  }));
  document.querySelectorAll("[data-assignment-delete]").forEach((button) => button.addEventListener("click", async () => {
    const item = state.currentCourse.assignments.find((entry) => entry.id === Number(button.dataset.assignmentDelete));
    if (!window.confirm(`Delete "${item.title}" and its submissions?`)) return;
    await request(`/api/courses/${state.currentCourse.course.id}/assignments/${item.id}?user_id=${state.user.id}`, { method: "DELETE" });
    showFlash("Assignment deleted");
    await loadCourse(state.currentCourse.course.id, "assignments");
  }));
}

function openSubmissionEditor(assignment) {
  openDialog(`Submit: ${assignment.title}`, `
    <form id="submission-editor">
      <p class="muted">Choose one or more submission types allowed by this assignment.</p>
      ${assignment.submission_types.includes("online_text_entry") ? '<label class="ic-Label" for="submission-text">Text Entry</label><textarea class="ic-Input text-area" id="submission-text" rows="7"></textarea>' : ""}
      ${assignment.submission_types.includes("online_url") ? '<label class="ic-Label" for="submission-url">Website URL</label><input class="ic-Input" id="submission-url" type="url" placeholder="https://">' : ""}
      ${assignment.submission_types.includes("online_upload") ? '<label class="ic-Label" for="submission-file">Files (up to 10)</label><input class="ic-Input" id="submission-file" type="file" multiple accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.zip">' : ""}
      ${state.user?.demo_submission_timing_enabled ? `<fieldset class="canvas-fieldset demo-timing-fieldset">
        <legend>Demo submission time</legend>
        <p class="muted">Use real time, or simulate an outcome relative to this assignment's deadline.</p>
        <input id="demo-submission-offset" type="hidden" value="">
        <div class="demo-timing-options" role="group" aria-label="Demo submission time">
          <button class="Button Button--small Button--primary" type="button" data-demo-offset="">Real time</button>
          <button class="Button Button--small" type="button" data-demo-offset="-60">60 min early</button>
          <button class="Button Button--small" type="button" data-demo-offset="0">On time</button>
          <button class="Button Button--small" type="button" data-demo-offset="60">60 min late</button>
        </div>
      </fieldset>` : ""}
      <div class="dialog-actions"><button class="Button" type="button" data-cancel-submission>Cancel</button><button class="Button Button--primary" type="submit">Submit Assignment</button></div>
    </form>`);
  document.querySelector("[data-cancel-submission]").addEventListener("click", closeDialog);
  document.querySelectorAll("[data-demo-offset]").forEach((button) => button.addEventListener("click", () => {
    document.querySelector("#demo-submission-offset").value = button.dataset.demoOffset;
    document.querySelectorAll("[data-demo-offset]").forEach((option) => option.classList.toggle("Button--primary", option === button));
  }));
  document.querySelector("#submission-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = [...(document.querySelector("#submission-file")?.files || [])];
    const textEntry = document.querySelector("#submission-text")?.value || "";
    const websiteUrl = document.querySelector("#submission-url")?.value || "";
    const demoOffsetValue = document.querySelector("#demo-submission-offset")?.value ?? "";
    const demoOffset = demoOffsetValue === "" ? null : Number(demoOffsetValue);
    let submission;
    if (files.length) {
      const form = new FormData();
      form.append("user_id", state.user.id);
      if (demoOffset !== null) form.append("demo_submission_offset_minutes", String(demoOffset));
      files.forEach((file) => form.append("uploads", file));
      submission = await request(`/api/assignments/${assignment.id}/submissions/files`, { method: "POST", body: form });
    } else {
      submission = await request(`/api/assignments/${assignment.id}/submissions`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, text_entry: textEntry, website_url: websiteUrl, demo_submission_offset_minutes: demoOffset }) });
    }
    closeDialog();
    showFlash(submissionTimingText({ submitted_at: submission.submitted_at, due_at: assignment.due_at }) || "Submission received");
    await loadCourse(state.currentCourse.course.id, "assignments");
  });
}

async function renderModulesTab(root) {
  root.innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Loading modules...</p></div>';
  try {
    const modules = await request(`/api/courses/${state.currentCourse.course.id}/modules?user_id=${state.user.id}`);
    const actions = state.user.role === "instructor" ? '<button class="Button Button--primary" data-new-module>+ Module</button>' : "";
    root.innerHTML = `${courseHeader("Modules", actions)}${modules.map((module) => `<section class="item-group"><div class="item-group-header"><div><h2>${escapeHtml(module.name)}</h2><span class="content-row-meta">${module.prerequisite_module_ids.length ? `Prerequisites: ${module.prerequisite_module_ids.join(", ")}` : "No prerequisite"}</span></div><div class="row-actions"><span class="published-icon">${module.published ? "✓" : "○"}</span>${state.user.role === "instructor" ? `<button class="Button Button--small" data-module-rules="${module.id}">Rules</button><button class="Button Button--small" data-add-module-item="${module.id}">+ Item</button><button class="Button Button--small" data-delete-module="${module.id}">Delete</button>` : ""}</div></div>${module.items.map((item) => { const requirement = module.requirements.find((entry) => entry.module_item_id === item.id); return `<div class="content-row"><span class="content-row-icon">▧</span><div><span class="content-row-title">${escapeHtml(item.title)}</span><span class="content-row-meta">${escapeHtml(item.item_type)}${requirement ? ` · ${escapeHtml(requirement.requirement_type)} · ${escapeHtml(requirement.status)}` : ""}</span></div>${state.user.role === "instructor" ? `<button class="Button Button--small" data-delete-module-item="${item.id}" data-module-id="${module.id}">Delete</button>` : requirement?.status === "completed" ? '<span class="published-icon">✓ Complete</span>' : `<button class="Button Button--small" data-complete-module-item="${item.id}">Mark done</button>`}</div>`; }).join("") || '<div class="empty-state"><p>No items in this module.</p></div>'}</section>`).join("") || '<div class="empty-state"><p>No modules have been added.</p></div>'}`;
    bindModuleActions(modules);
  } catch (error) { root.innerHTML = `<div class="error-state"><p>${escapeHtml(error.message)}</p></div>`; }
}

function bindModuleActions(modules) {
  document.querySelector("[data-new-module]")?.addEventListener("click", () => openModuleEditor());
  document.querySelectorAll("[data-module-rules]").forEach((button) => button.addEventListener("click", () => openModuleRulesEditor(modules.find((item) => item.id === Number(button.dataset.moduleRules)), modules)));
  document.querySelectorAll("[data-complete-module-item]").forEach((button) => button.addEventListener("click", async () => {
    await request(`/api/module-items/${button.dataset.completeModuleItem}/progress`, { method: "PUT", body: JSON.stringify({ status: "completed" }) });
    await renderModulesTab(document.querySelector("#course-main"));
  }));
  document.querySelectorAll("[data-add-module-item]").forEach((button) => button.addEventListener("click", () => openModuleItemEditor(Number(button.dataset.addModuleItem))));
  document.querySelectorAll("[data-delete-module]").forEach((button) => button.addEventListener("click", async () => {
    const module = modules.find((item) => item.id === Number(button.dataset.deleteModule));
    if (!window.confirm(`Delete module "${module.name}"?`)) return;
    await request(`/api/courses/${state.currentCourse.course.id}/modules/${module.id}?user_id=${state.user.id}`, { method: "DELETE" });
    renderModulesTab(document.querySelector("#course-main"));
  }));
  document.querySelectorAll("[data-delete-module-item]").forEach((button) => button.addEventListener("click", async () => {
    await request(`/api/courses/${state.currentCourse.course.id}/modules/${button.dataset.moduleId}/items/${button.dataset.deleteModuleItem}?user_id=${state.user.id}`, { method: "DELETE" });
    renderModulesTab(document.querySelector("#course-main"));
  }));
}

function openModuleRulesEditor(module, modules) {
  const prerequisites = modules.filter((item) => item.id !== module.id).map((item) => `<option value="${item.id}" ${module.prerequisite_module_ids.includes(item.id) ? "selected" : ""}>${escapeHtml(item.name)}</option>`).join("");
  const requirements = module.items.map((item) => { const current = module.requirements.find((entry) => entry.module_item_id === item.id); return `<div class="form-grid"><span>${escapeHtml(item.title)}</span><select class="ic-Input" data-module-requirement="${item.id}"><option value="must_view">View</option><option value="must_submit" ${current?.requirement_type === "must_submit" ? "selected" : ""}>Submit</option><option value="must_mark_done" ${current?.requirement_type === "must_mark_done" ? "selected" : ""}>Mark done</option><option value="must_score" ${current?.requirement_type === "must_score" ? "selected" : ""}>Minimum score</option></select><input class="ic-Input" data-module-min-score="${item.id}" type="number" min="0" placeholder="Minimum score" value="${current?.min_score ?? ""}"></div>`; }).join("");
  openDialog(`Module rules: ${module.name}`, `<form id="module-rules-editor"><label class="remember"><input id="module-sequential" type="checkbox" ${module.sequential_progress ? "checked" : ""}> Require sequential progress</label><label class="ic-Label" for="module-prerequisites">Prerequisite modules</label><select class="ic-Input" id="module-prerequisites" multiple>${prerequisites}</select><fieldset class="canvas-fieldset"><legend>Completion requirements</legend>${requirements || "No module items"}</fieldset><div class="dialog-actions"><button class="Button Button--primary">Save Rules</button></div></form>`);
  document.querySelector("#module-rules-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const prerequisiteIds = [...document.querySelector("#module-prerequisites").selectedOptions].map((option) => Number(option.value));
    const rules = [...document.querySelectorAll("[data-module-requirement]")].map((select) => ({ module_item_id: Number(select.dataset.moduleRequirement), requirement_type: select.value, min_score: Number(document.querySelector(`[data-module-min-score="${select.dataset.moduleRequirement}"]`).value) || null }));
    await request(`/api/modules/${module.id}/rules`, { method: "PUT", body: JSON.stringify({ prerequisite_module_ids: prerequisiteIds, requirements: rules, sequential_progress: document.querySelector("#module-sequential").checked }) });
    closeDialog();
    await renderModulesTab(document.querySelector("#course-main"));
  });
}

function openModuleEditor() {
  openDialog("Add Module", '<form id="module-editor"><label class="ic-Label" for="module-name">Module Name</label><input class="ic-Input" id="module-name" required><div class="dialog-actions"><button class="Button" type="button" data-cancel-module>Cancel</button><button class="Button Button--primary">Add Module</button></div></form>');
  document.querySelector("[data-cancel-module]").addEventListener("click", closeDialog);
  document.querySelector("#module-editor").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/modules`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, name: document.querySelector("#module-name").value }) }); closeDialog(); renderModulesTab(document.querySelector("#course-main")); });
}

function openModuleItemEditor(moduleId) {
  const snapshot = state.currentCourse;
  const references = { assignment: snapshot.assignments || [], resource: snapshot.resources || [], page: snapshot.content?.page || [], quiz: snapshot.content?.quiz || [], discussion: snapshot.content?.discussion || [] };
  openDialog("Add Module Item", `<form id="module-item-editor"><label class="ic-Label" for="module-item-title">Name</label><input class="ic-Input" id="module-item-title" required><label class="ic-Label" for="module-item-type">Type</label><select class="ic-Input" id="module-item-type"><option value="page">Page</option><option value="assignment">Assignment</option><option value="quiz">Quiz</option><option value="discussion">Discussion</option><option value="resource">File or Link</option><option value="external_url">External URL</option></select><label class="ic-Label" for="module-item-content">Course content</label><select class="ic-Input" id="module-item-content" required></select><label class="ic-Label" for="module-item-url">URL (external links only)</label><input class="ic-Input" id="module-item-url" type="url"><div class="dialog-actions"><button class="Button" type="button" data-cancel-module-item>Cancel</button><button class="Button Button--primary">Add Item</button></div></form>`);
  const typeSelect = document.querySelector("#module-item-type");
  const contentSelect = document.querySelector("#module-item-content");
  const urlInput = document.querySelector("#module-item-url");
  const refreshReferences = () => {
    const external = typeSelect.value === "external_url";
    contentSelect.disabled = external;
    contentSelect.required = !external;
    urlInput.required = external;
    urlInput.disabled = !external;
    contentSelect.innerHTML = '<option value="">Select existing course content</option>' + (references[typeSelect.value] || []).map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  };
  typeSelect.addEventListener("change", refreshReferences);
  contentSelect.addEventListener("change", () => {
    const title = document.querySelector("#module-item-title");
    if (!title.value) title.value = contentSelect.selectedOptions[0]?.textContent || "";
  });
  refreshReferences();
  document.querySelector("[data-cancel-module-item]").addEventListener("click", closeDialog);
  document.querySelector("#module-item-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    await request(`/api/courses/${state.currentCourse.course.id}/modules/${moduleId}/items`, {
      method: "POST",
      body: JSON.stringify({ user_id: state.user.id, title: document.querySelector("#module-item-title").value, item_type: typeSelect.value, content_id: contentSelect.disabled ? null : Number(contentSelect.value), external_url: urlInput.disabled ? "" : urlInput.value }),
    });
    closeDialog();
    renderModulesTab(document.querySelector("#course-main"));
  });
}

function bindFileActions() {
  if (state.user.role === "instructor") {
    document.querySelectorAll("[data-resource-versions]").forEach((button) => {
      const id = button.dataset.resourceVersions;
      button.insertAdjacentHTML("afterend", `<button class="Button Button--small" data-replace-resource="${id}">Replace file</button><button class="Button Button--small" data-resource-access="${id}">Access</button>`);
    });
  }
  document.querySelectorAll("[data-replace-resource]").forEach((button) => button.addEventListener("click", () => {
    openDialog("Replace file", '<form id="replace-file-form"><label class="ic-Label" for="replacement-file">New version (maximum 20 MB)</label><input id="replacement-file" class="ic-Input" type="file" required accept=".pdf,.docx,.pptx,.txt,.md"><p>The current file permissions are preserved.</p><div class="dialog-actions"><button class="Button" type="button" data-cancel-file>Cancel</button><button class="Button Button--primary">Save version</button></div></form>');
    document.querySelector("[data-cancel-file]").addEventListener("click", closeDialog);
    document.querySelector("#replace-file-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(); form.append("user_id", state.user.id); form.append("upload", document.querySelector("#replacement-file").files[0]);
      await request(`/api/courses/${state.currentCourse.course.id}/resources/${button.dataset.replaceResource}/upload`, { method: "PUT", body: form });
      closeDialog(); await loadCourse(state.currentCourse.course.id, "files");
    });
  }));
  document.querySelectorAll("[data-resource-access]").forEach((button) => button.addEventListener("click", () => {
    openDialog("File access", '<form id="file-access-form"><label class="ic-Label" for="resource-access-mode">Availability</label><select class="ic-Input" id="resource-access-mode"><option value="published">Allow access</option><option value="hidden">Revoke access</option></select><label class="ic-Label" for="resource-access-user">Student ID (leave blank for the whole course)</label><input class="ic-Input" id="resource-access-user" type="number" min="1"><p>Revocation also stops PaceWise from retrieving this file.</p><div class="dialog-actions"><button class="Button" type="button" data-cancel-file>Cancel</button><button class="Button Button--primary">Save access</button></div></form>');
    document.querySelector("[data-cancel-file]").addEventListener("click", closeDialog);
    document.querySelector("#file-access-form").addEventListener("submit", async (event) => {
      event.preventDefault(); const userId = document.querySelector("#resource-access-user").value;
      await request(`/api/resources/${button.dataset.resourceAccess}/access`, { method: "PUT", body: JSON.stringify({ published: document.querySelector("#resource-access-mode").value === "published", target_user_id: userId ? Number(userId) : null }) });
      closeDialog(); await loadCourse(state.currentCourse.course.id, "files");
    });
    const resource = state.currentCourse.resources.find((item) => String(item.id) === button.dataset.resourceAccess);
    const scopes = resource?.access_scope || [];
    document.querySelector("#resource-access-mode").value = scopes.length && !scopes.some((scope) => (scope.permission || "read") === "read") ? "hidden" : "published";
    const singleUser = scopes.length === 1 && scopes[0].type === "user" ? scopes[0].id : "";
    document.querySelector("#resource-access-user").value = singleUser;
  }));
  document.querySelectorAll("[data-resource-versions]").forEach((button) => button.addEventListener("click", async () => {
    const versions = await request(`/api/resources/${button.dataset.resourceVersions}/versions`);
    openDialog("File versions", `<table class="canvas-table"><thead><tr><th>Version</th><th>Checksum</th><th>Size</th><th>Created</th></tr></thead><tbody>${versions.map((version) => `<tr><td>v${version.version}</td><td><code>${escapeHtml(version.checksum_sha256.slice(0, 16))}…</code></td><td>${version.size_bytes} bytes</td><td>${formatDate(version.created_at)}</td></tr>`).join("")}</tbody></table>`);
  }));
  document.querySelector("[data-upload-file]")?.addEventListener("click", () => {
    openDialog("Upload File", '<form id="file-upload-form"><label class="ic-Label" for="course-file">Choose a file (maximum 20 MB)</label><input class="ic-Input" id="course-file" type="file" required accept=".pdf,.doc,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg,.zip"><div class="dialog-actions"><button class="Button" type="button" data-cancel-file>Cancel</button><button class="Button Button--primary">Upload</button></div></form>');
    document.querySelector("[data-cancel-file]").addEventListener("click", closeDialog);
    document.querySelector("#file-upload-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(); form.append("user_id", state.user.id); form.append("upload", document.querySelector("#course-file").files[0]); await request(`/api/courses/${state.currentCourse.course.id}/resources/upload`, { method: "POST", body: form }); closeDialog(); await loadCourse(state.currentCourse.course.id, "files"); });
  });
  document.querySelector("[data-add-link]")?.addEventListener("click", () => {
    openDialog("Add Link", '<form id="resource-link-form"><label class="ic-Label" for="resource-title">Name</label><input class="ic-Input" id="resource-title" required><label class="ic-Label" for="resource-url">URL</label><input class="ic-Input" id="resource-url" type="url" required><div class="dialog-actions"><button class="Button" type="button" data-cancel-link>Cancel</button><button class="Button Button--primary">Add</button></div></form>');
    document.querySelector("[data-cancel-link]").addEventListener("click", closeDialog);
    document.querySelector("#resource-link-form").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/resources`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, title: document.querySelector("#resource-title").value, kind: "link", source_url: document.querySelector("#resource-url").value }) }); closeDialog(); await loadCourse(state.currentCourse.course.id, "files"); });
  });
  document.querySelectorAll("[data-delete-resource]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Delete this file or link?")) return; await request(`/api/courses/${state.currentCourse.course.id}/resources/${button.dataset.deleteResource}?user_id=${state.user.id}`, { method: "DELETE" }); await loadCourse(state.currentCourse.course.id, "files"); }));
}

async function bindPeopleActions() {
  document.querySelector("[data-manage-sections]")?.addEventListener("click", openSectionsManager);
  document.querySelector("[data-manage-groups]")?.addEventListener("click", openGroupsManager);
  document.querySelector("[data-add-person]")?.addEventListener("click", async () => {
    const users = (await request("/api/users")).filter((user) => !state.currentCourse.people.some((person) => person.id === user.id));
    openDialog("Add People", `<form id="add-person-form"><label class="ic-Label" for="person-user">User</label><select class="ic-Input" id="person-user" required>${users.map((user) => `<option value="${user.id}">${escapeHtml(user.name)} (${escapeHtml(user.email)})</option>`).join("")}</select><label class="ic-Label" for="person-role">Role</label><select class="ic-Input" id="person-role"><option value="student">Student</option><option value="instructor">Teacher</option></select><div class="dialog-actions"><button class="Button" type="button" data-cancel-person>Cancel</button><button class="Button Button--primary">Add</button></div></form>`);
    document.querySelector("[data-cancel-person]").addEventListener("click", closeDialog);
    document.querySelector("#add-person-form").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/enrollments`, { method: "POST", body: JSON.stringify({ user_id: state.user.id, member_id: Number(document.querySelector("#person-user").value), role: document.querySelector("#person-role").value }) }); closeDialog(); await loadCourse(state.currentCourse.course.id, "people"); });
  });
  document.querySelectorAll("[data-remove-person]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Remove this enrollment?")) return; await request(`/api/courses/${state.currentCourse.course.id}/enrollments/${button.dataset.removePerson}?user_id=${state.user.id}`, { method: "DELETE" }); await loadCourse(state.currentCourse.course.id, "people"); }));
}

async function openSectionsManager() {
  const sections = await request(`/api/courses/${state.currentCourse.course.id}/sections`);
  openDialog("Course Sections", `<div class="item-group">${sections.map((section) => `<div class="content-row"><div><strong>${escapeHtml(section.name)}</strong><span class="content-row-meta">${section.member_ids.length} members</span></div></div>`).join("")}</div><form id="section-editor"><label class="ic-Label" for="section-name">New section</label><input class="ic-Input" id="section-name" required><div class="dialog-actions"><button class="Button Button--primary">Create</button></div></form>`);
  document.querySelector("#section-editor").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/sections`, { method: "POST", body: JSON.stringify({ name: document.querySelector("#section-name").value }) }); await openSectionsManager(); });
}

async function openGroupsManager() {
  const categories = await request(`/api/courses/${state.currentCourse.course.id}/groups`);
  openDialog("Course Groups", `<div class="item-group">${categories.map((category) => `<div class="content-row"><div><strong>${escapeHtml(category.name)}</strong><span class="content-row-meta">${category.groups.map((group) => `${escapeHtml(group.name)} (${group.member_ids.length})`).join(" · ") || "No groups"}</span></div></div>`).join("")}</div><form id="group-category-editor"><label class="ic-Label" for="group-category-name">New group set</label><input class="ic-Input" id="group-category-name" required><label class="remember"><input id="group-self-signup" type="checkbox"> Allow self sign-up</label><div class="dialog-actions"><button class="Button Button--primary">Create</button></div></form>`);
  document.querySelector("#group-category-editor").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${state.currentCourse.course.id}/group-categories`, { method: "POST", body: JSON.stringify({ name: document.querySelector("#group-category-name").value, self_signup: document.querySelector("#group-self-signup").checked }) }); await openGroupsManager(); });
}

function renderCourseSettings(root) {
  const course = state.currentCourse.course;
  root.innerHTML = `${courseHeader("Course Details")}<form id="course-settings" class="item-group settings-form"><label class="ic-Label" for="settings-name">Name</label><input class="ic-Input" id="settings-name" value="${escapeHtml(course.name)}" required><label class="ic-Label" for="settings-code">Course Code</label><input class="ic-Input" id="settings-code" value="${escapeHtml(course.code)}" required><label class="ic-Label" for="settings-term">Term</label><input class="ic-Input" id="settings-term" value="${escapeHtml(course.term)}" required><label class="ic-Label" for="settings-color">Course Color</label><input class="ic-Input color-input" id="settings-color" type="color" value="${escapeHtml(course.color)}"><label class="remember"><input id="settings-published" type="checkbox" checked> Published</label><div class="dialog-actions"><button class="Button Button--primary">Update Course Details</button><button class="Button Button--danger" type="button" data-delete-course>Delete This Course</button></div></form>`;
  document.querySelector("#course-settings").addEventListener("submit", async (event) => { event.preventDefault(); await request(`/api/courses/${course.id}/settings`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, code: document.querySelector("#settings-code").value, name: document.querySelector("#settings-name").value, term: document.querySelector("#settings-term").value, color: document.querySelector("#settings-color").value, published: document.querySelector("#settings-published").checked }) }); showFlash("Course settings updated"); await loadDashboard(); });
  document.querySelector("[data-delete-course]").addEventListener("click", async () => { if (!window.confirm(`Permanently delete ${course.name}?`)) return; await request(`/api/courses/${course.id}?user_id=${state.user.id}`, { method: "DELETE" }); showFlash("Course deleted"); await loadDashboard(); });
}

function bindGradebookActions() {
  document.querySelectorAll("[data-speedgrader]").forEach((button) => button.addEventListener("click", () => openSpeedGrader(Number(button.dataset.speedgrader))));
  document.querySelectorAll("[data-grade-assignment]").forEach((button) => button.addEventListener("click", () => openGradeEditor(Number(button.dataset.gradeAssignment), Number(button.dataset.gradeStudent))));
  document.querySelector("[data-export-grades]")?.addEventListener("click", exportGrades);
}

async function openSpeedGrader(assignmentId) {
  const assignment = state.currentCourse.assignments.find((item) => item.id === assignmentId);
  const submissions = await request(`/api/assignments/${assignmentId}/submissions?user_id=${state.user.id}`);
  openDialog(`SpeedGrader: ${assignment.title}`, `<div class="speedgrader-list">${submissions.map((submission) => `<button class="content-row" data-speedgrade-student="${submission.user_id}"><span class="person-avatar">${initials(submission.student_name)}</span><div><span class="content-row-title">${escapeHtml(submission.student_name)}</span><span class="content-row-meta">${submission.workflow_state} · ${submission.score ?? "Not graded"}</span></div><span>›</span></button>`).join("") || '<div class="empty-state"><p>No submissions yet.</p></div>'}</div>`);
  document.querySelectorAll("[data-speedgrade-student]").forEach((button) => button.addEventListener("click", () => openGradeEditor(assignmentId, Number(button.dataset.speedgradeStudent))));
}

async function openGradeEditor(assignmentId, studentId) {
  const assignment = state.currentCourse.assignments.find((item) => item.id === assignmentId);
  const student = state.currentCourse.people.find((item) => item.id === studentId);
  const submissions = await request(`/api/assignments/${assignmentId}/submissions?user_id=${state.user.id}`);
  const submission = submissions.find((item) => item.user_id === studentId);
  const rubricFields = assignment.rubric?.criteria.map((criterion) => `<label>${escapeHtml(criterion.description)}<input class="ic-Input" data-rubric-criterion="${criterion.id}" type="number" min="0" max="${criterion.points}" step="0.1" value="0"><small>out of ${criterion.points}</small></label>`).join("") || '<p class="muted">No rubric attached.</p>';
  openDialog(`Grade: ${student?.name || "Student"}`, `<div class="submission-preview"><h3>${escapeHtml(assignment.title)}</h3>${submission?.text_entry ? `<p>${escapeHtml(submission.text_entry)}</p>` : ""}${submission?.website_url ? `<p><a href="${escapeHtml(submission.website_url)}" target="_blank">Open submitted URL</a></p>` : ""}${submission?.file_url ? `<p><a href="${escapeHtml(submission.file_url)}?user_id=${state.user.id}" target="_blank">Download ${escapeHtml(submission.file_name)}</a></p>` : ""}${!submission ? '<p class="muted">This student has not submitted.</p>' : ""}${submission ? '<button class="Button Button--small" type="button" data-submission-history>Attempts & comments</button>' : ""}</div><form id="grade-editor"><label class="ic-Label" for="grade-score">Grade out of ${assignment.points_possible}</label><input class="ic-Input" id="grade-score" type="number" min="0" max="${assignment.points_possible}" step="0.1" value="${submission?.score ?? ""}" required><label class="ic-Label" for="grade-comment">Assignment Comments</label><textarea class="ic-Input text-area" id="grade-comment">${escapeHtml(submission?.instructor_comment || "")}</textarea><fieldset class="canvas-fieldset"><legend>${escapeHtml(assignment.rubric?.title || "Rubric")}</legend><div class="form-grid">${rubricFields}</div></fieldset><div class="dialog-actions"><button class="Button Button--primary">Update Grade</button></div></form>`);
  document.querySelector("[data-submission-history]")?.addEventListener("click", async () => { const history = await request(`/api/submissions/${submission.id}/history`); openDialog("Submission history", `<h3>Attempts</h3>${history.attempts.map((attempt) => `<div class="notice">Attempt ${attempt.attempt} · ${formatDate(attempt.submitted_at)} · ${attempt.attachments.length} file(s)</div>`).join("")}<h3>Comments</h3>${history.comments.map((comment) => `<p><strong>${escapeHtml(comment.author)}</strong>: ${escapeHtml(comment.body)}</p>`).join("") || '<p class="muted">No comments.</p>'}`); });
  document.querySelector("#grade-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const legacyRubric = {};
    const graded = await request(`/api/assignments/${assignmentId}/submissions/${studentId}/grade`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, score: Number(document.querySelector("#grade-score").value), comment: document.querySelector("#grade-comment").value, rubric: legacyRubric }) });
    const ratings = {};
    document.querySelectorAll("[data-rubric-criterion]").forEach((input) => { ratings[input.dataset.rubricCriterion] = Number(input.value); });
    if (assignment.rubric && Object.keys(ratings).length) await request(`/api/submissions/${graded.id}/rubric-assessment`, { method: "PUT", body: JSON.stringify({ ratings }) });
    closeDialog();
    showFlash("Grade updated");
    await loadCourse(state.currentCourse.course.id, "grades");
  });
}

function exportGrades() {
  const assignments = state.currentCourse.assignments;
  const rows = [["Student", ...assignments.map((item) => item.title)], ...state.currentCourse.gradebook.map((row) => [row.name, ...row.grades.map((grade) => grade.score ?? "")])];
  const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
  const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = `${state.currentCourse.course.code}-grades.csv`; link.click(); URL.revokeObjectURL(link.href);
}

function bindSubmitButtons() {
  document.querySelectorAll("[data-submit]").forEach((button) => {
    button.addEventListener("click", async () => {
      openSubmissionEditor(state.currentCourse.assignments.find((item) => item.id === Number(button.dataset.submit)));
    });
  });
}

async function renderCalendar() {
  closeTray();
  setActiveNav("calendar");
  recordHistory("Calendar", renderCalendar);
  showLoading();
  state.calendarItems = await request(`/api/calendar/${state.user.id}`);
  paintCalendar();
}

function paintCalendar() {
  const current = state.calendarDate;
  const year = current.getFullYear();
  const month = current.getMonth();
  const firstDay = new Date(year, month, 1);
  const gridStart = new Date(year, month, 1 - firstDay.getDay());
  const cells = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + index);
    const events = state.calendarItems.filter((item) => {
      const due = new Date(item.starts_at);
      const visible = state.calendarFilter === "all" || String(item.course_id || "personal") === state.calendarFilter;
      return visible && due.getFullYear() === day.getFullYear() && due.getMonth() === day.getMonth() && due.getDate() === day.getDate();
    });
    const dateKey = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 12).toISOString();
    return `<div class="calendar-cell ${day.getMonth() !== month ? "outside" : ""}" data-calendar-date="${dateKey}"><span class="calendar-day">${day.getDate()}</span>${events.map((item) => `<button class="calendar-event" style="--event-color:${item.color}" data-calendar-item="${item.id}" draggable="${item.editable}"><span class="calendar-event-time">${escapeHtml(calendarTimeLabel(item))}</span><span>${escapeHtml(item.title)}</span></button>`).join("")}</div>`;
  }).join("");
  const filter = `<select class="Button" data-calendar-filter><option value="all">All Calendars</option><option value="personal" ${state.calendarFilter === "personal" ? "selected" : ""}>${escapeHtml(state.user.name)}</option>${state.dashboard.courses.map((course) => `<option value="${course.id}" ${state.calendarFilter === String(course.id) ? "selected" : ""}>${escapeHtml(course.name)}</option>`).join("")}</select>`;
  const weekdays = localeCode() === "vi-VN"
    ? ["CN", "T2", "T3", "T4", "T5", "T6", "T7"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const activityButton = state.user.role === "instructor"
    ? '<button class="Button Button--primary" data-new-course-activity>+ Course activity</button>'
    : "";
  mainContent.innerHTML = `${courseHeader("Calendar", `${filter}<button class="Button" data-calendar-today>Today</button><button class="Button" data-new-event>+ Personal event</button>${activityButton}`)}<div class="calendar-toolbar"><button class="Button" data-calendar-prev>‹</button><h2>${new Intl.DateTimeFormat(localeCode(), { month: "long", year: "numeric" }).format(current)}</h2><button class="Button" data-calendar-next>›</button></div><p class="muted calendar-hint">Drag a personal event to another day to reschedule it.</p><div class="calendar-grid">${weekdays.map((day) => `<div class="calendar-cell calendar-weekday">${day}</div>`).join("")}${cells}</div>`;
  document.querySelector("[data-calendar-prev]").addEventListener("click", () => { state.calendarDate = new Date(year, month - 1, 1); paintCalendar(); });
  document.querySelector("[data-calendar-next]").addEventListener("click", () => { state.calendarDate = new Date(year, month + 1, 1); paintCalendar(); });
  document.querySelector("[data-calendar-today]").addEventListener("click", () => { state.calendarDate = new Date(); paintCalendar(); });
  document.querySelector("[data-new-event]").addEventListener("click", () => openCalendarEditor());
  document.querySelector("[data-new-course-activity]")?.addEventListener("click", () => openCourseActivityEditor());
  document.querySelector("[data-calendar-filter]").addEventListener("change", (event) => { state.calendarFilter = event.target.value; paintCalendar(); });
  document.querySelectorAll("[data-calendar-item]").forEach((button) => {
    button.addEventListener("click", () => openCalendarItem(state.calendarItems.find((item) => item.id === button.dataset.calendarItem)));
  });
  document.querySelectorAll('[data-calendar-item][draggable="true"]').forEach((button) => button.addEventListener("dragstart", (event) => event.dataTransfer.setData("text/plain", button.dataset.calendarItem)));
  document.querySelectorAll("[data-calendar-date]").forEach((cell) => {
    cell.addEventListener("dragover", (event) => event.preventDefault());
    cell.addEventListener("drop", async (event) => {
      event.preventDefault();
      const item = state.calendarItems.find((entry) => entry.id === event.dataTransfer.getData("text/plain"));
      if (!item?.editable) return;
      const oldDate = new Date(item.starts_at); const target = new Date(cell.dataset.calendarDate); target.setHours(oldDate.getHours(), oldDate.getMinutes(), 0, 0);
      await request(`/api/calendar/${item.source_id}`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, course_id: item.course_id, title: item.title, description: item.description || "", starts_at: target.toISOString(), ends_at: null, repeat_count: 1 }) });
      await renderCalendar();
    });
  });
}

function openCourseActivityEditor(preselectedCourseId = null) {
  const instructorCourses = state.dashboard.courses.filter((course) => course.enrollment_role === "instructor");
  if (!instructorCourses.length) {
    showFlash("Create a course before adding course activities");
    return;
  }
  const start = new Date(state.calendarDate);
  start.setHours(9, 0, 0, 0);
  const end = new Date(start.getTime() + 90 * 60 * 1000);
  const courseOptions = instructorCourses.map((course) => (
    `<option value="${course.id}" ${Number(preselectedCourseId) === course.id ? "selected" : ""}>${escapeHtml(course.code)} · ${escapeHtml(course.name)}</option>`
  )).join("");
  openDialog("Add Course Activity", `
    <form id="course-activity-editor">
      <label class="ic-Label" for="activity-course">Course</label>
      <select class="ic-Input" id="activity-course">${courseOptions}</select>
      <label class="ic-Label" for="activity-type">Activity type</label>
      <select class="ic-Input" id="activity-type">
        <option value="class_session">Online class</option>
        <option value="lecture_video">Lecture video</option>
        <option value="quiz">Quiz</option>
        <option value="assignment">Homework assignment</option>
        <option value="midterm">Midterm exam</option>
        <option value="final_exam">Final exam</option>
      </select>
      <label class="ic-Label" for="activity-title">Title</label>
      <input class="ic-Input" id="activity-title" required>
      <label class="ic-Label" for="activity-description">Description</label>
      <textarea class="ic-Input text-area" id="activity-description" rows="3"></textarea>
      <label class="ic-Label" for="activity-start" id="activity-start-label">Starts</label>
      <input class="ic-Input" id="activity-start" type="datetime-local" value="${inputDateTime(start)}" required>
      <div data-activity-end-row>
        <label class="ic-Label" for="activity-end">Ends</label>
        <input class="ic-Input" id="activity-end" type="datetime-local" value="${inputDateTime(end)}" required>
      </div>
      <div data-activity-repeat-row>
        <label class="ic-Label" for="activity-repeat">Repeat weekly</label>
        <input class="ic-Input" id="activity-repeat" type="number" min="1" max="52" value="1">
      </div>
      <div class="hidden" data-activity-source-row>
        <label class="ic-Label" for="activity-source">Video URL (optional)</label>
        <input class="ic-Input" id="activity-source" type="url" placeholder="https://...">
      </div>
      <div class="hidden" data-activity-points-row>
        <label class="ic-Label" for="activity-points">Points</label>
        <input class="ic-Input" id="activity-points" type="number" min="0" step="0.5" value="10">
      </div>
      <div class="dialog-actions">
        <button class="Button" type="button" data-cancel-course-activity>Cancel</button>
        <button class="Button Button--primary" type="submit">Add activity</button>
      </div>
    </form>`);

  const typeInput = document.querySelector("#activity-type");
  const updateFields = () => {
    const type = typeInput.value;
    const isAssignment = type === "assignment";
    document.querySelector("#activity-start-label").textContent = isAssignment ? "Due date" : "Starts";
    document.querySelector("[data-activity-end-row]").classList.toggle("hidden", isAssignment);
    document.querySelector("#activity-end").required = !isAssignment;
    document.querySelector("[data-activity-repeat-row]").classList.toggle("hidden", type !== "class_session");
    document.querySelector("[data-activity-source-row]").classList.toggle("hidden", type !== "lecture_video");
    document.querySelector("[data-activity-points-row]").classList.toggle("hidden", !["quiz", "assignment", "midterm", "final_exam"].includes(type));
  };
  typeInput.addEventListener("change", updateFields);
  updateFields();
  document.querySelector("[data-cancel-course-activity]").addEventListener("click", closeDialog);
  document.querySelector("#course-activity-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const activityType = typeInput.value;
    const courseId = Number(document.querySelector("#activity-course").value);
    await request(`/api/courses/${courseId}/activities`, {
      method: "POST",
      body: JSON.stringify({
        user_id: state.user.id,
        activity_type: activityType,
        title: document.querySelector("#activity-title").value,
        description: document.querySelector("#activity-description").value,
        starts_at: new Date(document.querySelector("#activity-start").value).toISOString(),
        ends_at: activityType === "assignment" ? null : new Date(document.querySelector("#activity-end").value).toISOString(),
        repeat_count: activityType === "class_session" ? Number(document.querySelector("#activity-repeat").value) : 1,
        source_url: document.querySelector("#activity-source").value,
        points_possible: Number(document.querySelector("#activity-points").value || 0),
      }),
    });
    closeDialog();
    showFlash("Course activity added for all enrolled users");
    await renderCalendar();
  });
}

function openCalendarItem(item) {
  if (item.type === "assignment") {
    loadCourse(item.course_id, "assignments");
    return;
  }
  const isOnlineClass = item.event_kind === "class_session";
  const attendanceLabels = localeCode() === "vi-VN"
    ? { scheduled: "Chưa ghi nhận", attended: "Đã tham gia", absent: "Vắng" }
    : { scheduled: "Not recorded", attended: "Attended", absent: "Absent" };
  const attendanceStatus = attendanceLabels[item.attendance_status] || attendanceLabels.scheduled;
  const safeJoinUrl = typeof item.join_url === "string" && item.join_url.startsWith("/api/calendar/events/")
    ? item.join_url
    : null;
  const onlineClassPanel = isOnlineClass ? `
    <section class="online-class-panel">
      <p><strong>${localeCode() === "vi-VN" ? "Trạng thái tham dự" : "Attendance"}:</strong> ${escapeHtml(attendanceStatus)}</p>
      ${safeJoinUrl ? `<a class="Button Button--primary" href="${escapeHtml(safeJoinUrl)}" target="_blank" rel="noopener">${localeCode() === "vi-VN" ? "Vào phòng học online" : "Join online class"}</a>` : ""}
      <div class="dialog-actions attendance-actions">
        <button class="Button" data-attendance-status="attended">${localeCode() === "vi-VN" ? "Đã tham gia" : "Attended"}</button>
        <button class="Button" data-attendance-status="absent">${localeCode() === "vi-VN" ? "Đánh dấu vắng" : "Mark absent"}</button>
        <button class="Button" data-attendance-status="scheduled">${localeCode() === "vi-VN" ? "Đặt lại" : "Reset"}</button>
      </div>
    </section>` : "";
  const actions = item.editable
    ? '<div class="dialog-actions"><button class="Button" data-edit-event>Edit</button><button class="Button" data-delete-event>Delete</button></div>'
    : '<p class="muted">Lịch học do nhà trường cung cấp và không thể chỉnh sửa.</p>';
  openDialog(item.title, `<p>${escapeHtml(item.description || "No details")}</p><p class="event-timeline"><strong>${localeCode() === "vi-VN" ? "Thời gian" : "Time"}:</strong> ${escapeHtml(eventTimeline(item))}</p>${onlineClassPanel}${actions}`);
  document.querySelectorAll("[data-attendance-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      await request(`/api/calendar/events/${item.source_id}/attendance`, {
        method: "PATCH",
        body: JSON.stringify({ status: button.dataset.attendanceStatus }),
      });
      closeDialog();
      showFlash(localeCode() === "vi-VN" ? "Đã cập nhật trạng thái tham dự" : "Attendance updated");
      await renderCalendar();
    });
  });
  if (!item.editable) return;
  document.querySelector("[data-edit-event]").addEventListener("click", () => openCalendarEditor(item));
  document.querySelector("[data-delete-event]").addEventListener("click", async () => {
    if (!window.confirm(`Delete "${item.title}"?`)) return;
    await request(`/api/calendar/${item.source_id}?user_id=${state.user.id}`, { method: "DELETE" });
    closeDialog();
    await renderCalendar();
  });
}

function openCalendarEditor(item = null) {
  openDialog(`${item ? "Edit" : "New"} Event`, `
    <form id="calendar-editor">
      <label class="ic-Label" for="event-title">Title</label><input class="ic-Input" id="event-title" value="${escapeHtml(item?.title || "")}" required>
      <label class="ic-Label" for="event-date">Date and time</label><input class="ic-Input" id="event-date" type="datetime-local" value="${inputDateTime(item?.starts_at || state.calendarDate)}" required>
      <label class="ic-Label" for="event-course">Calendar</label><select class="ic-Input" id="event-course"><option value="">${escapeHtml(state.user.name)}</option>${state.dashboard.courses.map((course) => `<option value="${course.id}" ${item?.course_id === course.id ? "selected" : ""}>${escapeHtml(course.name)}</option>`).join("")}</select>
      <label class="ic-Label" for="event-description">Details</label><textarea class="ic-Input text-area" id="event-description" rows="5">${escapeHtml(item?.description || "")}</textarea>
      ${item ? "" : '<label class="ic-Label" for="event-repeat">Repeat weekly</label><select class="ic-Input" id="event-repeat"><option value="1">Does not repeat</option><option value="2">2 weeks</option><option value="4">4 weeks</option><option value="8">8 weeks</option><option value="12">12 weeks</option></select>'}
      <div class="dialog-actions"><button class="Button" type="button" data-cancel-event>Cancel</button><button class="Button Button--primary" type="submit">Submit</button></div>
    </form>`);
  document.querySelector("[data-cancel-event]").addEventListener("click", closeDialog);
  document.querySelector("#calendar-editor").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      user_id: state.user.id,
      course_id: document.querySelector("#event-course").value ? Number(document.querySelector("#event-course").value) : null,
      title: document.querySelector("#event-title").value,
      description: document.querySelector("#event-description").value,
      starts_at: new Date(document.querySelector("#event-date").value).toISOString(),
      ends_at: null,
      repeat_count: Number(document.querySelector("#event-repeat")?.value || 1),
    };
    await request(`/api/calendar${item ? `/${item.source_id}` : ""}`, { method: item ? "PUT" : "POST", body: JSON.stringify(payload) });
    closeDialog();
    showFlash("Event saved");
    await renderCalendar();
  });
}

async function renderInbox() {
  closeTray();
  setActiveNav("inbox");
  recordHistory("Inbox", renderInbox);
  showLoading();
  state.conversations = await request(`/api/inbox/${state.user.id}?box=${state.inboxBox}`);
  if (!state.selectedConversationId && state.conversations.length) state.selectedConversationId = state.conversations[0].id;
  paintInbox();
}

function paintInbox() {
  const selected = state.conversations.find((item) => item.id === state.selectedConversationId);
  const list = state.conversations.map((conversation) => {
    const others = conversation.participants.filter((participant) => participant.id !== state.user.id);
    const lastMessage = conversation.messages.at(-1);
    return `<button class="conversation-list-item ${selected?.id === conversation.id ? "selected" : ""} ${conversation.unread ? "unread" : ""}" data-conversation="${conversation.id}"><strong>${conversation.unread ? "● " : ""}${escapeHtml(others.map((item) => item.name).join(", ") || state.user.name)}</strong><span>${escapeHtml(conversation.subject)}</span><small>${escapeHtml(lastMessage?.body || "")}</small></button>`;
  }).join("");
  const detail = selected ? `
    <div class="conversation-detail">
      <header><h2>${escapeHtml(selected.subject)}</h2><span>${escapeHtml(selected.participants.map((item) => item.name).join(", "))}</span></header>
      <div class="message-thread">${selected.messages.map((message) => `<article class="message"><div class="person-avatar">${initials(message.sender.name)}</div><div><strong>${escapeHtml(message.sender.name)}</strong><time>${formatDate(message.created_at)}</time><p>${escapeHtml(message.body).replaceAll("\n", "<br>")}</p>${message.attachments.map((file) => `<a href="${escapeHtml(file.file_url)}?user_id=${state.user.id}" target="_blank">📎 ${escapeHtml(file.file_name)}</a>`).join("")}</div></article>`).join("")}</div>
      <form class="reply-box" id="reply-form"><textarea class="ic-Input text-area" id="reply-body" rows="4" placeholder="Reply"></textarea><input id="reply-attachment" type="file" accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.zip"><div><button class="Button" type="button" data-toggle-unread>${selected.unread ? "Mark Read" : "Mark Unread"}</button><button class="Button" type="button" data-archive>${selected.archived ? "Move to Inbox" : "Archive"}</button><button class="Button Button--primary" type="submit">Send</button></div></form>
    </div>` : '<div class="inbox-empty"><div><div style="font-size:42px">✉</div><p>No conversations selected</p></div></div>';
  mainContent.innerHTML = `${courseHeader("Inbox", '<button class="Button Button--primary" data-compose>Compose a new message</button>')}<div class="inbox-toolbar">${[["inbox", "Inbox"], ["unread", "Unread"], ["sent", "Sent"], ["archived", "Archived"]].map(([key, label]) => `<button class="Button ${state.inboxBox === key ? "Button--primary" : ""}" data-inbox-box="${key}">${label}</button>`).join("")}</div><div class="inbox-layout"><div class="inbox-list">${list || '<div class="empty-state"><p>No conversations.</p></div>'}</div>${detail}</div>`;
  document.querySelector("[data-compose]").addEventListener("click", openComposeMessage);
  document.querySelectorAll("[data-inbox-box]").forEach((button) => button.addEventListener("click", () => { state.inboxBox = button.dataset.inboxBox; state.selectedConversationId = null; renderInbox(); }));
  document.querySelectorAll("[data-conversation]").forEach((button) => {
    button.addEventListener("click", async () => { state.selectedConversationId = Number(button.dataset.conversation); await request(`/api/inbox/${state.selectedConversationId}/state`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, unread: false }) }); const conversation = state.conversations.find((item) => item.id === state.selectedConversationId); conversation.unread = false; paintInbox(); });
  });
  document.querySelector("#reply-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = document.querySelector("#reply-body").value.trim();
    const file = document.querySelector("#reply-attachment").files[0];
    if (!body && !file) return;
    if (file) { const form = new FormData(); form.append("sender_id", state.user.id); form.append("body", body); form.append("upload", file); await request(`/api/inbox/${selected.id}/attachments`, { method: "POST", body: form }); await renderInbox(); }
    else { const updated = await request(`/api/inbox/${selected.id}/messages`, { method: "POST", body: JSON.stringify({ sender_id: state.user.id, body }) }); state.conversations = state.conversations.map((item) => item.id === updated.id ? updated : item); paintInbox(); }
  });
  document.querySelector("[data-toggle-unread]")?.addEventListener("click", async () => { await request(`/api/inbox/${selected.id}/state`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, unread: !selected.unread }) }); await renderInbox(); });
  document.querySelector("[data-archive]")?.addEventListener("click", async () => { await request(`/api/inbox/${selected.id}/state`, { method: "PUT", body: JSON.stringify({ user_id: state.user.id, archived: !selected.archived }) }); state.selectedConversationId = null; await renderInbox(); });
}

async function openComposeMessage() {
  const users = (await request("/api/users")).filter((user) => user.id !== state.user.id);
  openDialog("Compose Message", `
    <form id="compose-form">
      <label class="ic-Label" for="message-recipient">To (Ctrl/Cmd-click to select a group)</label><select class="ic-Input multi-select" id="message-recipient" multiple required>${users.map((user) => `<option value="${user.id}">${escapeHtml(user.name)}</option>`).join("")}</select>
      <label class="ic-Label" for="message-subject">Subject</label><input class="ic-Input" id="message-subject" required>
      <label class="ic-Label" for="message-body">Message</label><textarea class="ic-Input text-area" id="message-body" rows="7" required></textarea>
      <div class="dialog-actions"><button class="Button" type="button" data-cancel-message>Cancel</button><button class="Button Button--primary" type="submit">Send</button></div>
    </form>`);
  document.querySelector("[data-cancel-message]").addEventListener("click", closeDialog);
  document.querySelector("#compose-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const conversation = await request("/api/inbox", {
      method: "POST",
      body: JSON.stringify({
        sender_id: state.user.id,
        recipient_ids: [...document.querySelector("#message-recipient").selectedOptions].map((option) => Number(option.value)),
        subject: document.querySelector("#message-subject").value,
        body: document.querySelector("#message-body").value,
      }),
    });
    closeDialog();
    state.selectedConversationId = conversation.id;
    await renderInbox();
    showFlash("Message sent");
  });
}

function renderHistory() {
  closeTray();
  setActiveNav("history");
  mainContent.innerHTML = `${courseHeader("Recent History")}<div class="item-group">${state.history.map((item, index) => `<button class="content-row" data-history="${index}" style="width:100%;background:#fff;border-left:0;border-right:0;border-top:0;text-align:left"><span class="content-row-icon">◷</span><div><span class="content-row-title">${escapeHtml(item.label)}</span><span class="content-row-meta">${formatLongDate(item.at)}</span></div><span>›</span></button>`).join("") || '<div class="empty-state"><p>No recent page views.</p></div>'}</div>`;
  document.querySelectorAll("[data-history]").forEach((button) => button.addEventListener("click", () => state.history[Number(button.dataset.history)].action()));
}

async function logout() {
  try {
    await request("/api/session", { method: "DELETE" });
  } catch (error) {
    if (error.status !== 401) {
      window.alert("Chưa đăng xuất được Canvas. Hãy thử lại khi kết nối ổn định.");
      return;
    }
  }
  sessionStorage.removeItem("canvas_access_token");
  sessionStorage.removeItem("canvas_csrf_token");
  localStorage.removeItem("canvas_user_id");
  state.user = null;
  state.csrfToken = null;
  state.dashboard = null;
  state.currentCourse = null;
  state.history = [];
  closeTray();
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  document.querySelector("#password").value = "";
}

document.querySelectorAll("[data-nav]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector(".ic-app-header").classList.remove("open");
    const target = button.dataset.nav;
    if (target === "dashboard") loadDashboard();
    else if (target === "account") openAccountTray();
    else if (target === "courses") openCoursesTray();
    else if (target === "calendar") renderCalendar();
    else if (target === "inbox") renderInbox();
    else if (target === "pacewise") launchGlobalPaceWise();
    else if (target === "history") renderHistory();
    else if (target === "help") openHelpTray();
  });
});

document.querySelector("#mobile-menu").addEventListener("click", () => {
  document.querySelector(".ic-app-header").classList.toggle("open");
});
document.querySelector("#dialog-close").addEventListener("click", closeDialog);
dialog.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(); });

async function restoreSession() {
  sessionStorage.removeItem("canvas_access_token");
  sessionStorage.removeItem("canvas_csrf_token");
  try {
    const data = await request("/api/session/me");
    state.user = data.user;
    document.querySelector("#nav-avatar").textContent = initials(state.user.name);
    loginScreen.classList.add("hidden");
    appShell.classList.remove("hidden");
    await syncAccountLocale();
    await loadDashboard();
  } catch (_) {
    sessionStorage.removeItem("canvas_access_token");
    sessionStorage.removeItem("canvas_csrf_token");
    localStorage.removeItem("canvas_user_id");
    state.csrfToken = null;
  }
}

restoreSession();
