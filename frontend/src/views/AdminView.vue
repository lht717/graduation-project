<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { get, patch, post, put, remove } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";

defineOptions({ name: "AdminView" });

const router = useRouter();
const auth = useAuthStore();
const adminSection = ref("dashboard");
const lastRefreshed = ref(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }));
const dashboardStatus = ref("");
const sectionTitles = {
  dashboard: "学习看板",
  users: "学生管理",
  roles: "角色管理",
  virtualMachines: "虚拟机管理",
  courses: "课程管理",
  experiments: "实验管理",
  basics: "基础信息"
};
const sectionTitle = computed(() => sectionTitles[adminSection.value] || "学习看板");

const stats = [
  { label: "实验", value: 21, tone: "violet", icon: "验" },
  { label: "学生", value: 2, tone: "green", icon: "学" },
  { label: "实验容器", value: 10, tone: "orange", icon: "容" }
];
const recentExperiments = [];
const recentRecords = [];

const users = ref([]);
const searchQuery = ref("");
const usersStatus = ref("");
const usersStatusState = ref("");
const roleUsers = ref([]);
const rolesStatus = ref("");
const rolesStatusState = ref("");
const loadingRoles = ref(false);
const hasRolesData = ref(false);

const systemRoles = [
  { role: "admin", name: "管理员", description: "管理学生账号、平台基础信息与实验教学内容。" },
  { role: "user", name: "普通用户", description: "登录实验平台，查看实验并使用已开放的实验工作台。" }
];

const roleCounts = computed(() => ({
  admin: roleUsers.value.filter((item) => item.role === "admin").length,
  user: roleUsers.value.filter((item) => item.role === "user").length
}));

const rolesStatusClass = computed(() =>
  rolesStatusState.value ? `status ${rolesStatusState.value}` : "status"
);

const userFormOpen = ref(false);
const passwordFormOpen = ref(false);
const messageFormOpen = ref(false);

const editingUsername = ref(null);
const passwordUsername = ref(null);
const messageUsername = ref(null);
const messageTargetLabel = ref("");

const userAccount = ref("");
const userDisplayName = ref("");
const userPassword = ref("");
const userFormStatus = ref("");
const userFormStatusState = ref("");
const savingUser = ref(false);

const userNewPassword = ref("");
const userConfirmPassword = ref("");
const passwordFormStatus = ref("");
const passwordFormStatusState = ref("");
const savingPassword = ref(false);

const adminMessageContent = ref("");
const adminMessageStatus = ref("");
const adminMessageStatusState = ref("");
const sendingMessage = ref(false);

const usersStatusClass = computed(() =>
  usersStatusState.value ? `status ${usersStatusState.value}` : "status"
);
const userFormStatusClass = computed(() =>
  userFormStatusState.value ? `status ${userFormStatusState.value}` : "status"
);
const passwordFormStatusClass = computed(() =>
  passwordFormStatusState.value ? `status ${passwordFormStatusState.value}` : "status"
);
const adminMessageStatusClass = computed(() =>
  adminMessageStatusState.value ? `status ${adminMessageStatusState.value}` : "status"
);

const messageFormTitle = computed(() =>
  messageUsername.value ? `发送私信给：${messageTargetLabel.value}` : "发送私信"
);
const userFormTitle = computed(() =>
  editingUsername.value ? `编辑用户：${editingUsername.value}` : "新增普通用户"
);
const passwordFormTitle = computed(() =>
  passwordUsername.value ? `修改用户密码：${passwordUsername.value}` : "修改用户密码"
);

const filteredUsers = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase();
  return users.value.filter((item) =>
    `${item.username} ${item.account_id || ""} ${item.display_name || ""}`
      .toLocaleLowerCase()
      .includes(query)
  );
});

const emptyText = computed(() =>
  users.value.length ? "没有匹配的用户" : "暂无普通用户"
);

function setStatus(target, message, state = "") {
  target.value = message;
  if (target === usersStatus) usersStatusState.value = state;
  else if (target === userFormStatus) userFormStatusState.value = state;
  else if (target === passwordFormStatus) passwordFormStatusState.value = state;
  else if (target === adminMessageStatus) adminMessageStatusState.value = state;
}

function registeredDate(item) {
  const date = item.registered_at ? new Date(item.registered_at) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("zh-CN") : "—";
}

function selectSection(section) {
  adminSection.value = section;
  dashboardStatus.value = "";
  if (section === "users") void loadUsers();
  if (section === "roles") void loadRoles();
}

function refreshDashboard() {
  lastRefreshed.value = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  if (adminSection.value === "users") void loadUsers();
  else if (adminSection.value === "roles") void loadRoles();
  else dashboardStatus.value = "当前展示示例数据，尚未连接看板数据接口。";
}

function closeForms() {
  userFormOpen.value = false;
  passwordFormOpen.value = false;
  messageFormOpen.value = false;
  editingUsername.value = null;
  passwordUsername.value = null;
  messageUsername.value = null;
  messageTargetLabel.value = "";
}

function resetUserForm() {
  userAccount.value = "";
  userDisplayName.value = "";
  userPassword.value = "";
}

async function loadUsers() {
  setStatus(usersStatus, "正在加载用户…", "loading");
  try {
    const result = await get("/api/admin/users");
    if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
    users.value = result.users.filter((item) => item.role !== "admin");
    setStatus(usersStatus, `加载成功，共 ${users.value.length} 位普通用户。`, "success");
  } catch (error) {
    users.value = [];
    setStatus(usersStatus, `用户列表加载失败：${error.message}`, "error");
  }
}

async function loadRoles() {
  loadingRoles.value = true;
  rolesStatus.value = "正在加载角色信息…";
  rolesStatusState.value = "loading";
  try {
    const result = await get("/api/admin/users");
    if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
    roleUsers.value = result.users;
    hasRolesData.value = true;
    rolesStatus.value = `角色信息已更新，共 ${result.users.length} 个账号。`;
    rolesStatusState.value = "success";
  } catch (error) {
    roleUsers.value = [];
    hasRolesData.value = false;
    rolesStatus.value = `角色信息加载失败：${error.message}`;
    rolesStatusState.value = "error";
  } finally {
    loadingRoles.value = false;
  }
}

function openCreateForm() {
  closeForms();
  editingUsername.value = null;
  resetUserForm();
  setStatus(userFormStatus, "");
  userFormOpen.value = true;
}

function openEditForm(item) {
  closeForms();
  editingUsername.value = item.username;
  userAccount.value = item.account_id || item.student_id || item.username;
  userDisplayName.value = item.display_name || item.nickname || "";
  userPassword.value = "";
  setStatus(userFormStatus, "");
  userFormOpen.value = true;
}

async function onAction(action, item) {
  if (action === "edit") {
    openEditForm(item);
    return;
  }
  if (action === "password") {
    closeForms();
    passwordUsername.value = item.username;
    userNewPassword.value = "";
    userConfirmPassword.value = "";
    setStatus(passwordFormStatus, "");
    passwordFormOpen.value = true;
    return;
  }
  if (action === "message") {
    closeForms();
    messageUsername.value = item.username;
    messageTargetLabel.value = item.display_name || item.username;
    adminMessageContent.value = "";
    setStatus(adminMessageStatus, "");
    messageFormOpen.value = true;
    return;
  }
  if (action === "delete" && window.confirm(`确定删除普通用户“${item.username}”吗？此操作不可撤销。`)) {
    setStatus(usersStatus, `正在删除用户 ${item.username}…`, "loading");
    try {
      await remove(`/api/admin/users/${encodeURIComponent(item.username)}`);
      setStatus(usersStatus, `用户 ${item.username} 已删除。`, "success");
      await loadUsers();
    } catch (error) {
      setStatus(usersStatus, `删除失败：${error.message}`, "error");
    }
  }
}

async function submitUserForm() {
  const account = userAccount.value.trim();
  const name = userDisplayName.value.trim();
  savingUser.value = true;
  setStatus(userFormStatus, editingUsername.value ? "正在保存用户信息…" : "正在创建用户…", "loading");
  try {
    const successMessage = editingUsername.value ? "用户信息已更新。" : "用户创建成功。";
    if (editingUsername.value) {
      await patch(`/api/admin/users/${encodeURIComponent(editingUsername.value)}`, { display_name: name });
    } else {
      await post("/api/admin/users", {
        username: account,
        account_id: account,
        display_name: name,
        password: userPassword.value,
        role: "user"
      });
    }
    await loadUsers();
    if (usersStatusState.value === "success") setStatus(usersStatus, successMessage, "success");
    resetUserForm();
    closeForms();
  } catch (error) {
    setStatus(userFormStatus, `操作失败：${error.message}`, "error");
  } finally {
    savingUser.value = false;
  }
}

async function submitPasswordForm() {
  if (userNewPassword.value !== userConfirmPassword.value) {
    setStatus(passwordFormStatus, "两次输入的新密码不一致。", "error");
    return;
  }
  savingPassword.value = true;
  setStatus(passwordFormStatus, "正在修改密码…", "loading");
  try {
    await put(`/api/admin/users/${encodeURIComponent(passwordUsername.value)}/password`, {
      new_password: userNewPassword.value
    });
    setStatus(usersStatus, `用户 ${passwordUsername.value} 密码修改成功。`, "success");
    userNewPassword.value = "";
    userConfirmPassword.value = "";
    closeForms();
  } catch (error) {
    setStatus(passwordFormStatus, `修改密码失败：${error.message}`, "error");
  } finally {
    savingPassword.value = false;
  }
}

function onAdminMessageEnter(event) {
  if (event.shiftKey) return;
  event.preventDefault();
  if (!sendingMessage.value) void submitAdminMessage();
}

async function submitAdminMessage() {
  const content = adminMessageContent.value.trim();
  if (!content || !messageUsername.value) {
    setStatus(adminMessageStatus, "请输入消息内容。", "error");
    return;
  }
  sendingMessage.value = true;
  setStatus(adminMessageStatus, "正在发送私信…", "loading");
  try {
    await post("/api/messages", {
      recipient: messageUsername.value,
      subject: "管理员私信",
      content
    });
    adminMessageContent.value = "";
    router.push("/message");
  } catch (error) {
    setStatus(adminMessageStatus, `私信发送失败：${error.message}`, "error");
  } finally {
    sendingMessage.value = false;
  }
}

</script>

<template>
  <section id="adminView" class="admin-shell">
    <aside class="admin-sidebar">
      <a class="admin-logo" href="#home" @click.prevent="router.push('/home')">
        <span class="admin-logo-mark">F</span><span>Fusion <b>Lab</b></span>
      </a>
      <nav class="admin-menu" aria-label="管理端导航">
        <div class="admin-menu-group">
          <span class="admin-menu-label">系统管理</span>
          <button :class="{ active: adminSection === 'dashboard' }" @click="selectSection('dashboard')"><span class="admin-menu-icon">看</span>学习看板</button>
        </div>
        <div class="admin-menu-group">
          <span class="admin-menu-label">基础信息</span>
          <button :class="{ active: adminSection === 'users' }" @click="selectSection('users')"><span class="admin-menu-icon">学</span>学生管理</button>
          <button :class="{ active: adminSection === 'roles' }" @click="selectSection('roles')"><span class="admin-menu-icon">权</span>角色管理</button>
        </div>
        <div class="admin-menu-group">
          <span class="admin-menu-label">虚拟机管理</span>
          <button :class="{ active: adminSection === 'virtualMachines' }" @click="selectSection('virtualMachines')"><span class="admin-menu-icon">云</span>虚拟机管理</button>
        </div>
        <div class="admin-menu-group">
          <span class="admin-menu-label">实验管理</span>
          <button :class="{ active: adminSection === 'experiments' }" @click="selectSection('experiments')"><span class="admin-menu-icon">验</span>实验管理</button>
        </div>
      </nav>
      <button class="admin-back-link" @click="router.push('/dashboard')"><span>←</span> 返回实验平台</button>
    </aside>

    <div class="admin-main">
      <header class="admin-topbar">
        <div class="admin-breadcrumb"><span>管理端</span><i>/</i><b>{{ sectionTitle }}</b></div>
        <div class="admin-top-actions">
          <button class="admin-refresh" type="button" aria-label="刷新" @click="refreshDashboard"><span>↻</span>刷新</button>
          <div class="admin-user-summary">
            <span class="admin-user-avatar">{{ auth.avatarText }}</span>
            <span><b>{{ auth.displayName }}</b><small>在线实验概览</small></span>
          </div>
        </div>
      </header>

      <main class="admin-content">
        <template v-if="adminSection === 'dashboard'">
          <div class="admin-welcome">
            <div><p class="admin-eyebrow">FUSION LAB · LEARNING CENTER</p><h1>学习看板</h1><p>欢迎回来，{{ auth.displayName }}。这里是平台实验教学概览。</p></div>
            <span class="admin-updated">更新于 {{ lastRefreshed }}</span>
          </div>
          <p v-if="dashboardStatus" class="admin-dashboard-status" role="status">{{ dashboardStatus }}</p>

          <section class="admin-stat-grid" aria-label="平台统计">
            <article v-for="stat in stats" :key="stat.label" :class="['admin-stat-card', `tone-${stat.tone}`]">
              <span class="admin-stat-icon">{{ stat.icon }}</span>
              <span class="admin-stat-label">{{ stat.label }}</span>
              <b class="admin-stat-value">{{ stat.value }}</b>
              <span class="admin-stat-foot">平台累计</span>
            </article>
          </section>

          <section class="admin-dashboard-card admin-quick-card">
            <div class="admin-card-heading"><div><h2>快捷入口</h2><p>快速访问常用管理功能</p></div></div>
            <div class="admin-quick-grid">
              <button @click="selectSection('experiments')"><span class="quick-icon quick-violet">验</span><span><b>实验管理</b><small>维护实验内容</small></span><i>›</i></button>
              <button @click="selectSection('users')"><span class="quick-icon quick-green">学</span><span><b>学生管理</b><small>管理学生账号</small></span><i>›</i></button>
              <button @click="selectSection('virtualMachines')"><span class="quick-icon quick-orange">云</span><span><b>虚拟机</b><small>查看实验容器</small></span><i>›</i></button>
            </div>
          </section>

          <section class="admin-dashboard-card admin-recent-experiments">
            <div class="admin-card-heading"><div><h2>最近实验</h2><p>最近更新的实验内容</p></div><button class="admin-text-link" @click="selectSection('experiments')">全部实验 <span>›</span></button></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验名称</th><th>学时</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-if="!recentExperiments.length"><td colspan="3" class="admin-empty">暂无实验内容</td></tr>
                <tr v-for="experiment in recentExperiments" :key="experiment.name"><td class="table-primary">{{ experiment.name }}</td><td>{{ experiment.hours }} 学时</td><td><button class="admin-row-action" @click="selectSection('experiments')">编辑</button></td></tr>
              </tbody>
            </table></div>
          </section>

          <section class="admin-dashboard-card admin-record-card">
            <div class="admin-card-heading"><div><h2>最近实验记录</h2><p>学生近期实验容器运行状态</p></div><button class="admin-text-link" @click="selectSection('virtualMachines')">容器管理 <span>›</span></button></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验</th><th>学员</th><th>状态</th><th>时间</th></tr></thead>
              <tbody>
                <tr v-if="!recentRecords.length"><td colspan="4" class="admin-empty">暂无实验记录</td></tr>
                <tr v-for="record in recentRecords" :key="`${record.experiment}-${record.time}`"><td class="table-primary">{{ record.experiment }}</td><td>{{ record.student }}</td><td><span :class="['admin-state-tag', record.status === '运行中' ? 'state-running' : 'state-missing']"><i></i>{{ record.status }}</span></td><td>{{ record.time }}</td></tr>
              </tbody>
            </table></div>
          </section>
        </template>

        <template v-else-if="adminSection === 'users'">
          <header class="admin-page-heading"><div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>学生管理</h1><p>管理普通用户账号、名称和密码。</p></div><button class="btn btn-primary" id="showCreateUser" type="button" @click="openCreateForm">新增学生</button></header>
          <section class="account-card admin-card">
            <div class="message-list-head"><h2>学生账号</h2></div>
            <div class="admin-user-toolbar"><label class="sr-only" for="userSearch">搜索用户</label><input id="userSearch" v-model="searchQuery" type="search" placeholder="搜索账号或自定义名称"><button class="btn btn-outline" id="refreshUsers" type="button" @click="loadUsers">刷新</button></div>
            <p :class="usersStatusClass" id="usersStatus" role="status" aria-live="polite">{{ usersStatus }}</p>
            <div class="admin-table-wrap">
              <table class="admin-user-table">
                <thead><tr><th>账号（学号）</th><th>自定义名称</th><th>注册时间</th><th>操作</th></tr></thead>
                <tbody id="usersTableBody">
                  <tr v-if="!filteredUsers.length"><td colspan="4" class="admin-empty">{{ emptyText }}</td></tr>
                  <tr v-for="item in filteredUsers" :key="item.username">
                    <td>{{ item.account_id || item.student_id || item.username || "—" }}</td><td>{{ item.display_name || item.nickname || "—" }}</td><td>{{ registeredDate(item) }}</td>
                    <td class="admin-user-actions">
                      <button type="button" class="btn btn-outline" data-action="edit" :data-username="item.username" @click="onAction('edit', item)">编辑</button>
                      <button type="button" class="btn btn-outline" data-action="message" :data-username="item.username" @click="onAction('message', item)">私信</button>
                      <button type="button" class="btn btn-outline" data-action="password" :data-username="item.username" @click="onAction('password', item)">改密码</button>
                      <button type="button" class="btn btn-danger" data-action="delete" :data-username="item.username" @click="onAction('delete', item)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !messageFormOpen }" id="messagePanel">
            <h2 id="messageFormTitle">{{ messageFormTitle }}</h2>
            <form id="adminMessageForm" @submit.prevent="submitAdminMessage">
              <div class="field"><label for="adminMessageContent">消息内容</label><textarea id="adminMessageContent" v-model="adminMessageContent" rows="4" maxlength="2000" required placeholder="输入要发送给用户的私信" @keydown.enter="onAdminMessageEnter"></textarea></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="sendAdminMessage" :disabled="sendingMessage">发送私信</button><button class="btn btn-outline" type="button" id="cancelAdminMessage" @click="closeForms">取消</button></div>
              <p :class="adminMessageStatusClass" id="adminMessageStatus" role="status" aria-live="polite">{{ adminMessageStatus }}</p>
            </form>
          </section>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !userFormOpen }" id="userFormPanel">
            <h2 id="userFormTitle">{{ userFormTitle }}</h2>
            <form id="userForm" @submit.prevent="submitUserForm">
              <div class="field"><label for="userAccount">账号（学号）</label><input id="userAccount" v-model="userAccount" name="username" inputmode="numeric" pattern="[0-9]+" autocomplete="off" required :readonly="!!editingUsername"></div>
              <div class="field"><label for="userDisplayName">自定义名称</label><input id="userDisplayName" v-model="userDisplayName" name="display_name" maxlength="40" required></div>
              <div class="field" id="initialPasswordField" :class="{ hidden: !!editingUsername }"><label for="userPassword">初始密码</label><input id="userPassword" v-model="userPassword" name="password" type="password" minlength="8" autocomplete="new-password" :required="!editingUsername"></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="saveUserButton" :disabled="savingUser">{{ editingUsername ? "保存修改" : "创建用户" }}</button><button class="btn btn-outline" type="button" id="cancelUserForm" @click="closeForms">取消</button></div>
              <p :class="userFormStatusClass" id="userFormStatus" role="status" aria-live="polite">{{ userFormStatus }}</p>
            </form>
          </section>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !passwordFormOpen }" id="passwordPanel">
            <h2 id="passwordFormTitle">{{ passwordFormTitle }}</h2>
            <form id="passwordForm" @submit.prevent="submitPasswordForm">
              <div class="field"><label for="userNewPassword">新密码</label><input id="userNewPassword" v-model="userNewPassword" type="password" minlength="8" autocomplete="new-password" required></div>
              <div class="field"><label for="userConfirmPassword">确认新密码</label><input id="userConfirmPassword" v-model="userConfirmPassword" type="password" minlength="8" autocomplete="new-password" required></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" :disabled="savingPassword">确认修改</button><button class="btn btn-outline" type="button" id="cancelPasswordForm" @click="closeForms">取消</button></div>
              <p :class="passwordFormStatusClass" id="passwordFormStatus" role="status" aria-live="polite">{{ passwordFormStatus }}</p>
            </form>
          </section>
        </template>

        <template v-else-if="adminSection === 'roles'">
          <header class="admin-page-heading">
            <div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>角色管理</h1><p>查看系统内置角色及其账号数量。</p></div>
            <button class="btn btn-outline" type="button" aria-label="刷新角色信息" :disabled="loadingRoles" @click="loadRoles">{{ loadingRoles ? "刷新中…" : "刷新" }}</button>
          </header>
          <p :class="rolesStatusClass" role="status" aria-live="polite">{{ rolesStatus }}</p>
          <section class="admin-role-grid" aria-label="系统角色">
            <article v-for="role in systemRoles" :key="role.role" class="admin-dashboard-card admin-role-card">
              <div class="admin-role-card-heading">
                <span class="admin-role-icon">{{ role.role === "admin" ? "管" : "学" }}</span>
                <span class="admin-role-type">系统内置</span>
              </div>
              <h2>{{ role.name }}</h2>
              <p>{{ role.description }}</p>
              <div class="admin-role-count">
                <span>当前账号</span>
                <strong>{{ hasRolesData ? roleCounts[role.role] : "—" }}</strong>
              </div>
            </article>
          </section>
          <p class="admin-role-note">当前角色为系统内置角色，角色新增与权限配置暂未接入。</p>
        </template>

        <section v-else class="admin-dashboard-card admin-empty-state">
          <span class="admin-empty-icon">{{ adminSection === 'virtualMachines' ? '云' : adminSection === 'experiments' ? '验' : '课' }}</span>
          <h1>{{ sectionTitle }}</h1>
          <p>该管理模块目前尚未接入业务接口，学习看板中的示例数据仅用于展示。</p>
          <button class="btn btn-outline" @click="selectSection('dashboard')">返回学习看板</button>
        </section>
      </main>
    </div>
  </section>
</template>
