import { get, patch, post, put, remove } from "./api.js";
import { createRouter } from "./router.js";
import { mountProfileView } from "./views/profile.js";
import { mountMessageView } from "./views/message.js";
import { mountAdminView } from "./views/admin.js";
import { createWorkspace } from "./views/workspace.js";

const viewElements = {
  home: document.querySelector("#landingView"),
  dashboard: document.querySelector("#dashboardView"),
  workspace: document.querySelector("#experimentView"),
  profile: document.querySelector("#profileView"),
  message: document.querySelector("#messageView"),
  admin: document.querySelector("#adminView")
};
const loginModal = document.querySelector("#loginModal");
const loginStatus = document.querySelector("#loginStatus");
let currentUser = { username: "demo", role: "user", role_name: "普通用户" };
let authenticated = false;
let workspace;
let unreadCheckTimer = null;

function messageReadKey(username) {
  return `fusionlab_last_read_message_${username}`;
}

function messageSequence(message) {
  const match = String(message.id || "").match(/(\d+)$/);
  return match ? Number(match[1]) : 0;
}

function updateMessageIndicator(hasUnread) {
  document.querySelectorAll('[data-route="message"]').forEach((link) => {
    link.classList.toggle("has-unread", hasUnread);
    link.setAttribute("aria-label", hasUnread ? "私信，有未读消息" : "私信");
  });
}

function markMessagesRead(messages, username) {
  if (!authenticated || currentUser.username !== username) return;
  const latestSequence = messages
    .filter((message) => message.recipient_username === username && message.sender_username !== username)
    .reduce((latest, message) => Math.max(latest, messageSequence(message)), 0);
  const key = messageReadKey(username);
  const lastRead = Number(localStorage.getItem(key) || 0);
  if (latestSequence > lastRead) localStorage.setItem(key, String(latestSequence));
  updateMessageIndicator(false);
}

async function refreshMessageIndicator() {
  if (!authenticated) return;
  const username = currentUser.username;
  try {
    const result = await get("/api/messages");
    if (!authenticated || currentUser.username !== username || !Array.isArray(result.messages)) return;
    const lastRead = Number(localStorage.getItem(messageReadKey(username)) || 0);
    const hasUnread = result.messages.some((message) =>
      message.recipient_username === username &&
      message.sender_username !== username &&
      messageSequence(message) > lastRead
    );
    updateMessageIndicator(hasUnread);
  } catch {
    // Keep the last known indicator state when the message endpoint is unavailable.
  }
}

function startUnreadPolling() {
  if (unreadCheckTimer) window.clearInterval(unreadCheckTimer);
  void refreshMessageIndicator();
  unreadCheckTimer = window.setInterval(refreshMessageIndicator, 30000);
}

function stopUnreadPolling() {
  if (unreadCheckTimer) window.clearInterval(unreadCheckTimer);
  unreadCheckTimer = null;
  updateMessageIndicator(false);
}

function openLogin(message = "") {
  loginModal.classList.remove("hidden");
  loginStatus.textContent = message;
  loginStatus.className = message ? "status error" : "status";
}

function closeLogin() {
  loginModal.classList.add("hidden");
}

function updateDashboardIdentity() {
  const displayName = currentUser.display_name || currentUser.nickname || currentUser.username;
  const accountId = currentUser.account_id || currentUser.student_id ||
    (/^\d+$/.test(String(currentUser.username || "")) ? currentUser.username : "—");
  document.querySelectorAll("#dashboardUsername, [data-user-name]").forEach((element) => {
    element.textContent = displayName;
  });
  document.querySelectorAll("#dashboardAccount, [data-user-account]").forEach((element) => {
    element.textContent = accountId;
  });
  document.querySelectorAll("#dashboardAvatar, [data-user-avatar]").forEach((element) => {
    element.textContent = displayName.slice(0, 1).toUpperCase();
  });
  document.querySelectorAll("#dashboardRole, [data-user-role]").forEach((element) => {
    element.textContent = currentUser.role_name || "Engineering Workspace";
  });
  document.querySelectorAll(".admin-nav").forEach((link) => {
    link.classList.toggle("hidden", currentUser.role !== "admin");
  });
}

function showView(route) {
  if (["dashboard", "workspace", "profile", "message", "admin"].includes(route) && !authenticated) {
    openLogin("请先登录后访问该页面。");
    router.navigate("home", true);
    return;
  }
  if (route === "admin" && currentUser.role !== "admin") {
    router.navigate("dashboard", true);
    return;
  }
  Object.entries(viewElements).forEach(([name, element]) => {
    element.classList.toggle("hidden", name !== route);
  });
  closeLogin();
  if (route === "profile") mountProfileView(viewElements.profile, {
    user: currentUser,
    api: { get, post },
    onUserUpdated: updateDashboardIdentity
  });
  if (route === "message") {
    const username = currentUser.username;
    void mountMessageView(viewElements.message, {
      user: currentUser,
      api: { get, post },
      onMessagesRead: (messages) => markMessagesRead(messages, username)
    });
  }
  if (route === "admin") mountAdminView(viewElements.admin, {
    user: currentUser,
    api: { get, post, put, patch, remove },
    navigate: router.navigate
  });
  if (route === "workspace") workspace.activate();
}

const router = createRouter(showView);
workspace = createWorkspace({ get, post }, router.navigate);

document.querySelector("#openLogin").addEventListener("click", () => openLogin());
document.querySelector("#heroEnter").addEventListener("click", () => openLogin());
document.querySelector("#scrollCapabilities").addEventListener("click", () => {
  document.querySelector("#capabilities").scrollIntoView({ behavior: "smooth" });
});
document.querySelector("#cancelLogin").addEventListener("click", closeLogin);
document.querySelector("#openExperiment").addEventListener("click", () => router.navigate("workspace"));
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-logout]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();

  const status = button.parentElement.querySelector("[data-logout-status]");
  button.disabled = true;
  status.textContent = "正在退出…";
  status.className = "status logout-status loading";
  try {
    await post("/api/auth/logout", {});
    localStorage.removeItem("fusionlab_token");
    authenticated = false;
    stopUnreadPolling();
    currentUser = { username: "demo", role: "user", role_name: "普通用户" };
    router.navigate("home");
    updateDashboardIdentity();
  } catch (error) {
    status.textContent = `退出登录失败：${error.message}`;
    status.className = "status logout-status error";
  } finally {
    button.disabled = false;
  }
});
document.querySelector("#loginBtn").addEventListener("click", async () => {
  const button = document.querySelector("#loginBtn");
  button.disabled = true;
  loginStatus.textContent = "正在登录…";
  loginStatus.className = "status loading";
  try {
    const result = await post("/api/auth/login", {
      username: document.querySelector("#username").value.trim(),
      password: document.querySelector("#password").value
    });
    if (!result.authenticated || !result.user) throw new Error("登录响应无效");
    if (result.token) localStorage.setItem("fusionlab_token", result.token);
    currentUser = result.user;
    authenticated = true;
    updateDashboardIdentity();
    startUnreadPolling();
    router.navigate("dashboard");
  } catch (error) {
    loginStatus.textContent = `登录失败：${error.message}`;
    loginStatus.className = "status error";
  } finally {
    button.disabled = false;
  }
});

async function initialize() {
  try {
    const result = await get("/api/auth/me");
    if (result.user) currentUser = result.user;
    authenticated = Boolean(result.authenticated);
  } catch (error) {
    loginStatus.textContent = `账号状态读取失败：${error.message}`;
  }
  updateDashboardIdentity();
  if (authenticated) startUnreadPolling();
  const initialRoute = router.initialRoute();
  if (initialRoute !== "home" && !authenticated) {
    router.navigate("home", true);
    openLogin("请先登录后访问该页面。");
    return;
  }
  router.navigate(initialRoute, true);
  if (new URLSearchParams(window.location.search).get("openLogin") === "1") openLogin();
}

void initialize();
