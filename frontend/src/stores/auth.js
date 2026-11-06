import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { get, post } from "@/api/client.js";
import { config } from "@/config.js";

function messageReadKey(username) {
  return `fusionlab_last_read_message_${username}`;
}

function messageSequence(message) {
  const match = String(message.id || "").match(/(\d+)$/);
  return match ? Number(match[1]) : 0;
}

const DEFAULT_USER = { username: "demo", role: "user", role_name: "普通用户" };
const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
const avatarStorageKey = (username) => `fusionlab_avatar_${encodeURIComponent(username)}`;

function normalizeAvatarUrl(url) {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("http://") || url.startsWith("https://")) return url;
  const base = config.apiBaseUrl.replace(/\/$/, "");
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
}

export const useAuthStore = defineStore("auth", () => {
  const user = ref({ ...DEFAULT_USER });
  const authenticated = ref(false);
  const avatarUrl = ref("");

  const loginModalOpen = ref(false);
  const loginStatus = ref("");
  const loginStatusState = ref("");
  const loginPending = ref(false);

  // 未读红点：hasUnread 是真实状态；unreadTick 对应原版 updateMessageIndicator() 的每一次调用
  const hasUnread = ref(false);
  const unreadTick = ref(0);

  let unreadTimer = null;

  const displayName = computed(
    () => user.value.display_name || user.value.nickname || user.value.username
  );
  const accountId = computed(
    () =>
      user.value.account_id ||
      user.value.student_id ||
      (/^\d+$/.test(String(user.value.username || "")) ? user.value.username : "—")
  );
  const roleName = computed(() => user.value.role_name || "Engineering Workspace");
  const avatarText = computed(() => String(displayName.value || "").slice(0, 1).toUpperCase());
  const isAdmin = computed(() => user.value.role === "admin");
  const loginStatusClass = computed(() =>
    loginStatusState.value ? `status ${loginStatusState.value}` : "status"
  );

  function loadUserAvatar(username) {
    const backendAvatar = user.value?.avatar || "";
    avatarUrl.value = backendAvatar
      ? normalizeAvatarUrl(backendAvatar)
      : username
        ? localStorage.getItem(avatarStorageKey(username)) || ""
        : "";
  }

  async function saveAvatar(file) {
    if (!authenticated.value || !user.value.username) throw new Error("请先登录后再更换头像");
    if (!file || !file.type.startsWith("image/")) throw new Error("请选择图片文件");
    if (file.size > AVATAR_MAX_BYTES) throw new Error("图片不能超过 2 MB");

    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result !== "string") {
          reject(new Error("图片读取失败"));
          return;
        }
        resolve(reader.result);
      };
      reader.onerror = () => reject(new Error("图片读取失败"));
      reader.readAsDataURL(file);
    });

    const result = await post("/api/users/me/avatar", { avatar: dataUrl });
    if (result.user) user.value = result.user;
    const nextAvatar = result.user?.avatar || "";
    avatarUrl.value = nextAvatar ? normalizeAvatarUrl(nextAvatar) : dataUrl;
    localStorage.removeItem(avatarStorageKey(user.value.username));
  }

  async function removeAvatar() {
    if (user.value.username) localStorage.removeItem(avatarStorageKey(user.value.username));
    if (!authenticated.value) {
      avatarUrl.value = "";
      return;
    }
    const result = await post("/api/users/me/avatar", { avatar: "/static/avatar_default.png" });
    if (result.user) user.value = result.user;
    avatarUrl.value = normalizeAvatarUrl(result.user?.avatar || "/static/avatar_default.png");
  }

  function openLogin(message = "") {
    loginModalOpen.value = true;
    loginStatus.value = message;
    loginStatusState.value = message ? "error" : "";
  }

  function closeLogin() {
    loginModalOpen.value = false;
  }

  /** 原版 updateMessageIndicator(hasUnread) */
  function updateMessageIndicator(next) {
    hasUnread.value = Boolean(next);
    unreadTick.value += 1;
  }

  function markMessagesRead(messages) {
    if (!authenticated.value || !Array.isArray(messages)) return;
    const username = user.value.username;
    const latestSequence = messages
      .filter((message) => message.recipient_username === username && message.sender_username !== username)
      .reduce((latest, message) => Math.max(latest, messageSequence(message)), 0);
    const key = messageReadKey(username);
    const lastRead = Number(localStorage.getItem(key) || 0);
    if (latestSequence > lastRead) localStorage.setItem(key, String(latestSequence));
    updateMessageIndicator(false);
  }

  async function refreshMessageIndicator() {
    if (!authenticated.value) return;
    const username = user.value.username;
    try {
      const result = await get("/api/messages");
      if (!authenticated.value || user.value.username !== username || !Array.isArray(result.messages)) return;
      const lastRead = Number(localStorage.getItem(messageReadKey(username)) || 0);
      const next = result.messages.some(
        (message) =>
          message.recipient_username === username &&
          message.sender_username !== username &&
          messageSequence(message) > lastRead
      );
      updateMessageIndicator(next);
    } catch (error) {
      if (error && error.status === 401) {
        authenticated.value = false;
        updateMessageIndicator(false);
        stopUnreadPolling();
      }
    }
  }

  function startUnreadPolling() {
    if (unreadTimer) window.clearInterval(unreadTimer);
    void refreshMessageIndicator();
    unreadTimer = window.setInterval(refreshMessageIndicator, 30000);
  }

  function stopUnreadPolling() {
    if (unreadTimer) window.clearInterval(unreadTimer);
    unreadTimer = null;
    updateMessageIndicator(false);
  }

  async function login(username, password, selectedRole = "student") {
    loginPending.value = true;
    loginStatus.value = "正在登录…";
    loginStatusState.value = "loading";
    try {
      const expectedRole = selectedRole === "teacher" ? "admin" : "user";
      const result = await post("/api/auth/login", { username: String(username).trim(), password });
      if (!result.authenticated || !result.user) throw new Error("登录响应无效");
      if (result.user.role !== expectedRole) {
        if (result.token) {
          localStorage.setItem("fusionlab_token", result.token);
          try {
            await post("/api/auth/logout", {});
          } finally {
            localStorage.removeItem("fusionlab_token");
          }
        }
        throw new Error(selectedRole === "teacher" ? "该账号不是教师账号" : "该账号不是学生账号");
      }
      if (result.token) localStorage.setItem("fusionlab_token", result.token);
      user.value = result.user;
      authenticated.value = true;
      loadUserAvatar(result.user.username);
      startUnreadPolling();
      return true;
    } catch (error) {
      loginStatus.value = `登录失败：${error.message}`;
      loginStatusState.value = "error";
      return false;
    } finally {
      loginPending.value = false;
    }
  }

  /** 原版 data-logout 事件委托里的逻辑 */
  async function logout() {
    await post("/api/auth/logout", {});
    localStorage.removeItem("fusionlab_token");
    authenticated.value = false;
    avatarUrl.value = "";
    stopUnreadPolling();
    user.value = { ...DEFAULT_USER };
  }

  /** 原版 initialize() 的第一段：读取 /api/auth/me */
  async function bootstrap() {
    try {
      const result = await get("/api/auth/me");
      if (result.user) user.value = result.user;
      authenticated.value = Boolean(result.authenticated);
      loadUserAvatar(authenticated.value ? result.user?.username : "");
    } catch (error) {
      if (error && error.status === 401) {
        authenticated.value = false;
        user.value = { ...DEFAULT_USER };
        avatarUrl.value = "";
      }
      loginStatus.value = `账号状态读取失败：${error.message}`;
    }
    if (authenticated.value) startUnreadPolling();
  }

  return {
    user,
    authenticated,
    avatarUrl,
    loginModalOpen,
    loginStatus,
    loginStatusState,
    loginPending,
    hasUnread,
    unreadTick,
    displayName,
    accountId,
    roleName,
    avatarText,
    isAdmin,
    loginStatusClass,
    openLogin,
    closeLogin,
    updateMessageIndicator,
    markMessagesRead,
    refreshMessageIndicator,
    startUnreadPolling,
    stopUnreadPolling,
    login,
    saveAvatar,
    removeAvatar,
    logout,
    bootstrap
  };
});
